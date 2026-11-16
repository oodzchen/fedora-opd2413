#!/usr/bin/env python3
"""Native Qt6 (PySide6) ZSL Multi-Frame RAW10 HDR+ Camera App for OPD2413."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import gc
import mmap
from pathlib import Path
import sys
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.insert(0, "/usr/libexec/opd2413")
from hdrplus_isp import (  # noqa: E402
    SENSOR_PROFILES,
    process_raw10_burst,
    save_jpeg_with_exif,
)


def _extract_meta(req_meta: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in req_meta.items():
        ks = k.name if hasattr(k, "name") else str(k)
        try:
            if hasattr(v, "value") and isinstance(getattr(v, "value"), (int, float, bool)):
                out[ks] = v.value
            elif hasattr(v, "__len__") and not isinstance(v, (str, bytes)):
                out[ks] = [
                    x.value if hasattr(x, "value") else (float(x) if isinstance(x, float) else int(x))
                    for x in v
                ]
            elif isinstance(v, (int, float, bool)):
                out[ks] = v
            else:
                out[ks] = str(v)
        except Exception:
            out[ks] = str(v)
    return out


class ViewfinderCanvas(QtWidgets.QWidget):
    """Aspect-preserving viewfinder canvas with optional rule-of-thirds grid and tap-to-focus."""

    clicked = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._image: Optional[QtGui.QImage] = None
        self._show_grid = False
        self._flash_alpha = 0.0
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_frame(self, img: QtGui.QImage) -> None:
        self._image = img
        self.update()

    def set_grid(self, enabled: bool) -> None:
        self._show_grid = enabled
        self.update()

    def trigger_flash(self) -> None:
        self._flash_alpha = 0.65
        self.update()
        QtCore.QTimer.singleShot(45, self._fade_flash)

    def _fade_flash(self) -> None:
        self._flash_alpha = max(0.0, self._flash_alpha - 0.16)
        self.update()
        if self._flash_alpha > 0.01:
            QtCore.QTimer.singleShot(35, self._fade_flash)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QtGui.QColor("#0b0d10"))

        if self._image is not None and not self._image.isNull():
            target = QtCore.QRectF(self.rect())
            img_sz = QtCore.QSizeF(self._image.size())
            scaled = img_sz.scaled(target.size(), QtCore.Qt.KeepAspectRatio)
            x = target.x() + (target.width() - scaled.width()) * 0.5
            y = target.y() + (target.height() - scaled.height()) * 0.5
            draw_rect = QtCore.QRectF(x, y, scaled.width(), scaled.height())
            painter.drawImage(draw_rect, self._image)

            if self._show_grid:
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 90), 1.0)
                painter.setPen(pen)
                for frac in (1.0 / 3.0, 2.0 / 3.0):
                    gx = draw_rect.x() + draw_rect.width() * frac
                    gy = draw_rect.y() + draw_rect.height() * frac
                    painter.drawLine(QtCore.QPointF(gx, draw_rect.top()), QtCore.QPointF(gx, draw_rect.bottom()))
                    painter.drawLine(QtCore.QPointF(draw_rect.left(), gy), QtCore.QPointF(draw_rect.right(), gy))

            if self._flash_alpha > 0.01:
                painter.fillRect(draw_rect, QtGui.QColor(255, 255, 255, int(self._flash_alpha * 255)))


class CameraController(QtCore.QObject):
    """Background libcamera ZSL dual-stream controller + async HDR+ processor."""

    frame_ready = QtCore.Signal(QtGui.QImage, dict)
    camera_error = QtCore.Signal(str)
    camera_started = QtCore.Signal(str, int, int)
    photo_saved = QtCore.Signal(str, QtGui.QImage, str)
    capture_busy = QtCore.Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._active_model = "sc820cs"
        self._mirror_preview = True
        self._hdr_frames = 8
        self._ev_comp = 0.0
        self._refocus_pending = False
        self._ring: Deque[Tuple[bytes, Dict[str, Any]]] = deque(maxlen=8)
        self._pending_post: Optional[Tuple[int, int, str, bool, float, List[Tuple[bytes, Dict[str, Any]]], int, int, int]] = None
        self._save_lock = threading.Lock()
        self._available_models: List[str] = []

    def probe_available(self) -> List[str]:
        import libcamera as lc
        cm = lc.CameraManager.singleton()
        mods = [str(c.properties.get(lc.properties.Model) or "") for c in cm.cameras]
        self._available_models = [m for m in ("sc1300cs", "sc820cs") if m in mods]
        return self._available_models

    def start_camera(self, model: str, mirror_front: bool = True) -> None:
        self.stop_camera()
        self._active_model = model
        self._mirror_preview = mirror_front
        self._stop_event.clear()
        with self._lock:
            self._ring.clear()
            self._pending_post = None
            self._refocus_pending = False
        self._thread = threading.Thread(target=self._run_loop, name=f"cam-{model}", daemon=True)
        self._thread.start()

    def set_mirror_front(self, enabled: bool) -> None:
        self._mirror_preview = enabled

    def set_ev_comp(self, ev: float) -> None:
        with self._lock:
            self._ev_comp = float(ev)

    def trigger_refocus(self) -> None:
        with self._lock:
            self._refocus_pending = True

    def stop_camera(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=4.0)
        self._thread = None

    @staticmethod
    def _filter_focus_consistent(
        frame_items: List[Tuple[bytes, Dict[str, Any]]],
        max_delta_diopter: float = 0.20,
    ) -> List[Tuple[bytes, Dict[str, Any]]]:
        if len(frame_items) <= 1 or "LensPosition" not in frame_items[-1][1]:
            return frame_items
        ref_lp = float(frame_items[-1][1]["LensPosition"])
        kept = [
            item for item in frame_items
            if "LensPosition" not in item[1]
            or abs(float(item[1]["LensPosition"]) - ref_lp) <= max_delta_diopter
        ]
        if len(kept) >= 2:
            return kept
        return [frame_items[-1]]

    def trigger_shutter(self, hdr_mode: bool, mirror_front: bool) -> None:
        target_frames = self._hdr_frames if hdr_mode else 1
        with self._lock:
            if self._pending_post is not None:
                return
            recent = list(self._ring)
            if not recent:
                return
            ev_comp = self._ev_comp
            if target_frames == 1:
                frames = [recent[-1]]
                post_needed = 0
            else:
                # Use up to 4 most recent frames + wait for remaining ~4 post-shutter frames (~0.13s)
                pre = recent[-4:] if len(recent) >= 4 else recent
                frames = list(pre)
                post_needed = max(0, target_frames - len(frames))
            self._pending_post = (
                post_needed,
                target_frames,
                self._active_model,
                mirror_front,
                ev_comp,
                frames,
                0,
                0,
                0,
            )
        self.capture_busy.emit(True, "Capturing RAW burst..." if hdr_mode else "Processing...")

    def _run_loop(self) -> None:
        import libcamera as lc

        cm = lc.CameraManager.singleton()
        cam = None
        for c in cm.cameras:
            if str(c.properties.get(lc.properties.Model) or "") == self._active_model:
                cam = c
                break
        if cam is None:
            self.camera_error.emit(f"Camera {self._active_model} unavailable")
            return

        ctrl_names = {c.name if hasattr(c, "name") else str(c) for c in cam.controls}
        has_af = "AfMode" in ctrl_names and "LensPosition" in ctrl_names
        profile = SENSOR_PROFILES[self._active_model]
        reqs = []
        alloc = None
        acquired = False
        started = False

        try:
            cam.acquire()
            acquired = True
            cfg = cam.generate_configuration([lc.StreamRole.Viewfinder, lc.StreamRole.Raw])
            cfg.at(0).pixel_format = lc.formats.XRGB8888
            cfg.at(0).size = lc.Size(*profile.preview_size)
            cfg.at(1).size = lc.Size(*profile.raw_size)
            cfg.validate()
            cam.configure(cfg)

            vf_sc = cfg.at(0)
            raw_sc = cfg.at(1)
            vw, vh, vstride, vsize = vf_sc.size.width, vf_sc.size.height, vf_sc.stride, vf_sc.frame_size
            vfmt = str(vf_sc.pixel_format)
            rw, rh, rstride, rsize = raw_sc.size.width, raw_sc.size.height, raw_sc.stride, raw_sc.frame_size

            alloc = lc.FrameBufferAllocator(cam)
            s_vf = vf_sc.stream
            s_raw = raw_sc.stream
            if alloc.allocate(s_vf) <= 0 or alloc.allocate(s_raw) <= 0:
                raise RuntimeError("Failed to allocate libcamera ZSL dual buffers")

            buf_vf = alloc.buffers(s_vf)
            buf_raw = alloc.buffers(s_raw)
            for idx in range(min(len(buf_vf), len(buf_raw))):
                req = cam.create_request(idx)
                req.add_buffer(s_vf, buf_vf[idx])
                req.add_buffer(s_raw, buf_raw[idx])
                reqs.append(req)

            cam.start()
            started = True
            for idx, req in enumerate(reqs):
                if has_af and idx == 0:
                    req.set_control(lc.controls.AfMode, lc.controls.AfModeEnum.Continuous)
                    req.set_control(lc.controls.AfTrigger, lc.controls.AfTriggerEnum.Start)
                cam.queue_request(req)

            self.camera_started.emit(self._active_model, vw, vh)

            fps_times: Deque[float] = deque(maxlen=15)
            last_vf_emit = 0.0

            while not self._stop_event.is_set():
                ready = cm.get_ready_requests()
                if not ready:
                    time.sleep(0.002)
                    continue

                for req in ready:
                    if req.status != lc.Request.Status.Complete:
                        if not self._stop_event.is_set():
                            req.reuse()
                            cam.queue_request(req)
                        continue

                    now = time.monotonic()
                    fps_times.append(now)
                    fps = (len(fps_times) - 1) / max(1e-4, fps_times[-1] - fps_times[0]) if len(fps_times) > 1 else 0.0
                    meta = _extract_meta(req.metadata)

                    # Read compact RAW10 bytes into ZSL ring
                    fb_raw = req.buffers[s_raw]
                    p_raw = fb_raw.planes[0]
                    with mmap.mmap(p_raw.fd, rsize, mmap.MAP_SHARED, mmap.PROT_READ) as mm:
                        raw_bytes = bytes(mm[:rsize])

                    dispatch_job = None
                    do_refocus = False
                    with self._lock:
                        self._ring.append((raw_bytes, meta))
                        if self._refocus_pending:
                            self._refocus_pending = False
                            do_refocus = True
                        if self._pending_post is not None:
                            post_left, tot_f, mdl, mir, evc, flist, _, _, _ = self._pending_post
                            if post_left > 0:
                                flist.append((raw_bytes, meta))
                                post_left -= 1
                            if post_left <= 0:
                                clean_list = self._filter_focus_consistent(list(flist)) if tot_f > 1 else list(flist)
                                dispatch_job = (len(clean_list), mdl, mir, evc, clean_list, rw, rh, rstride)
                                self._pending_post = None
                            else:
                                self._pending_post = (post_left, tot_f, mdl, mir, evc, flist, rw, rh, rstride)

                    if dispatch_job is not None:
                        threading.Thread(
                            target=self._process_and_save,
                            args=dispatch_job,
                            daemon=True,
                        ).start()

                    # Throttle UI QImage dispatch slightly to avoid backlog on busy UI
                    if now - last_vf_emit >= 0.020:
                        last_vf_emit = now
                        fb_vf = req.buffers[s_vf]
                        p_vf = fb_vf.planes[0]
                        with mmap.mmap(p_vf.fd, vsize, mmap.MAP_SHARED, mmap.PROT_READ) as mm:
                            row = np.frombuffer(mm[:vsize], dtype=np.uint8).reshape(vh, vstride)
                            if "XRGB8888" in vfmt or "ARGB8888" in vfmt:
                                bgra = row[:, : vw * 4].reshape(vh, vw, 4)
                                rgb = bgra[:, :, 2::-1]
                            else:
                                rgba = row[:, : vw * 4].reshape(vh, vw, 4)
                                rgb = rgba[:, :, :3]
                            if self._active_model == "sc820cs" and self._mirror_preview:
                                rgb = rgb[:, ::-1]
                            rgb = np.ascontiguousarray(rgb)
                        qimg = QtGui.QImage(rgb.data, vw, vh, vw * 3, QtGui.QImage.Format_RGB888).copy()
                        hud = {
                            "fps": round(fps, 1),
                            "exp_us": int(meta.get("ExposureTime", 0) or 0),
                            "again": round(float(meta.get("AnalogueGain", 1.0) or 1.0), 1),
                            "ct": int(meta.get("ColourTemperature", 0) or 0),
                            "has_af": has_af,
                            "af_state": meta.get("AfState"),
                            "lens_pos": meta.get("LensPosition"),
                        }
                        self.frame_ready.emit(qimg, hud)

                    if not self._stop_event.is_set():
                        req.reuse()
                        if do_refocus and has_af:
                            req.set_control(lc.controls.AfMode, lc.controls.AfModeEnum.Continuous)
                            req.set_control(lc.controls.AfTrigger, lc.controls.AfTriggerEnum.Start)
                        cam.queue_request(req)
        except Exception as exc:
            if not self._stop_event.is_set():
                self.camera_error.emit(str(exc))
        finally:
            if started:
                try:
                    cam.stop()
                except Exception:
                    pass
                _ = cm.get_ready_requests()
            reqs.clear()
            alloc = None
            gc.collect()
            if acquired:
                try:
                    cam.release()
                except Exception:
                    pass

    def _process_and_save(
        self,
        tot_frames: int,
        model: str,
        mirror_front: bool,
        ev_comp: float,
        frame_items: List[Tuple[bytes, Dict[str, Any]]],
        rw: int,
        rh: int,
        rstride: int,
    ) -> None:
        self.capture_busy.emit(True, f"HDR+ merging ({tot_frames} frames)..." if tot_frames > 1 else "Processing RAW...")
        with self._save_lock:
            try:
                t0 = time.monotonic()
                raw_list = [f[0] for f in frame_items]
                meta = frame_items[-1][1]
                profile = SENSOR_PROFILES[model]
                rgb_u8, stats = process_raw10_burst(
                    raw_list,
                    rw,
                    rh,
                    rstride,
                    model,
                    metadata=meta,
                    mirror_selfie=(mirror_front and model == "sc820cs"),
                    ev_comp=ev_comp,
                )
                pic_dir = Path.home() / "Pictures" / "OPD_Camera"
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                side = "FRONT" if model == "sc820cs" else "REAR"
                tag = "HDR" if tot_frames > 1 else "RAW1"
                out_path = pic_dir / f"IMG_{ts}_{side}_{tag}.jpg"
                save_jpeg_with_exif(
                    rgb_u8,
                    out_path,
                    profile,
                    metadata=meta,
                    quality=95,
                    mode_tag="HDR+" if tot_frames > 1 else "SingleRAW",
                )
                elapsed_s = time.monotonic() - t0
                thumb_np = cv2.resize(rgb_u8, (160, 120), interpolation=cv2.INTER_AREA)
                thumb_np = np.ascontiguousarray(thumb_np)
                thumb_q = QtGui.QImage(thumb_np.data, 160, 120, 160 * 3, QtGui.QImage.Format_RGB888).copy()
                msg = f"Saved {out_path.name} ({elapsed_s:.2f}s)"
                self.photo_saved.emit(str(out_path), thumb_q, msg)
            except Exception as exc:
                self.camera_error.emit(f"HDR+ error: {exc}")
            finally:
                self.capture_busy.emit(False, "Ready")


class CameraMainWindow(QtWidgets.QMainWindow):
    """Touch-friendly tablet HDR+ Camera GUI."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OPD2413 HDR+ Camera")
        self.setWindowIcon(QtGui.QIcon.fromTheme("camera-photo"))
        self.resize(1120, 760)
        self.setStyleSheet(
            """
            QMainWindow { background-color: #0b0d10; color: #f0f4f8; }
            QPushButton {
                background-color: #1f242c; color: #f0f4f8;
                border: 1px solid #353d49; border-radius: 20px;
                padding: 8px 16px; font-size: 14px; font-weight: 500;
            }
            QPushButton:hover { background-color: #2b323d; }
            QPushButton:checked { background-color: #2c6bed; border-color: #4f86f7; }
            QComboBox {
                background-color: #1f242c; color: #f0f4f8;
                border: 1px solid #353d49; border-radius: 16px;
                padding: 6px 12px; font-size: 13px; font-weight: 500;
            }
            QComboBox QAbstractItemView {
                background-color: #1f242c; color: #f0f4f8;
                selection-background-color: #2c6bed;
            }
            QLabel { color: #d8dee6; font-size: 13px; }
            """
        )

        self._ctrl = CameraController()
        self._available = self._ctrl.probe_available()
        self._current_model = "sc820cs" if "sc820cs" in self._available else (self._available[0] if self._available else "sc820cs")
        self._hdr_mode = True
        self._mirror_front = True
        self._last_photo_path: Optional[str] = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(10)

        # Top HUD bar
        top = QtWidgets.QHBoxLayout()
        self._hud_label = QtWidgets.QLabel("Initializing camera...")
        self._hud_label.setStyleSheet("font-family: monospace; color: #b7c2d0;")
        top.addWidget(self._hud_label, 1)

        self._combo_ev = QtWidgets.QComboBox()
        for label, val in (("EV -0.5", -0.5), ("EV 0.0", 0.0), ("EV +0.5", 0.5), ("EV +1.0", 1.0)):
            self._combo_ev.addItem(label, val)
        self._combo_ev.setCurrentIndex(1)
        self._combo_ev.currentIndexChanged.connect(self._on_ev_changed)
        top.addWidget(self._combo_ev)

        self._btn_refocus = QtWidgets.QPushButton("Refocus")
        self._btn_refocus.setVisible(self._current_model == "sc1300cs")
        self._btn_refocus.clicked.connect(self._on_refocus)
        top.addWidget(self._btn_refocus)

        self._btn_mode = QtWidgets.QPushButton("HDR+ 8x")
        self._btn_mode.setCheckable(True)
        self._btn_mode.setChecked(True)
        self._btn_mode.clicked.connect(self._toggle_mode)
        top.addWidget(self._btn_mode)

        self._btn_mirror = QtWidgets.QPushButton("Selfie Mirror")
        self._btn_mirror.setCheckable(True)
        self._btn_mirror.setChecked(True)
        self._btn_mirror.clicked.connect(self._toggle_mirror)
        top.addWidget(self._btn_mirror)

        self._btn_grid = QtWidgets.QPushButton("Grid")
        self._btn_grid.setCheckable(True)
        self._btn_grid.clicked.connect(lambda c: self._canvas.set_grid(c))
        top.addWidget(self._btn_grid)
        root.addLayout(top)

        # Main live viewfinder
        self._canvas = ViewfinderCanvas()
        self._canvas.clicked.connect(self._on_refocus)
        root.addWidget(self._canvas, 1)

        # Bottom control dock
        dock = QtWidgets.QHBoxLayout()
        dock.setSpacing(18)

        self._btn_thumb = QtWidgets.QPushButton("")
        self._btn_thumb.setFixedSize(68, 52)
        self._btn_thumb.setIconSize(QtCore.QSize(64, 48))
        self._btn_thumb.setStyleSheet("border-radius: 10px; padding: 0px; background-color: #16191f;")
        self._btn_thumb.setToolTip("Open last photo")
        self._btn_thumb.clicked.connect(self._open_last_photo)
        dock.addWidget(self._btn_thumb)

        self._status_label = QtWidgets.QLabel("Ready")
        self._status_label.setMinimumWidth(180)
        dock.addWidget(self._status_label)

        dock.addStretch(1)

        self._btn_shutter = QtWidgets.QPushButton("")
        self._btn_shutter.setFixedSize(78, 78)
        self._btn_shutter.setStyleSheet(
            """
            QPushButton {
                background-color: #f4f6f8;
                border: 5px solid #596373;
                border-radius: 39px;
            }
            QPushButton:pressed {
                background-color: #b8c2cf;
            }
            """
        )
        self._btn_shutter.clicked.connect(self._on_shutter)
        dock.addWidget(self._btn_shutter)

        dock.addStretch(1)

        self._btn_switch = QtWidgets.QPushButton("Switch Cam")
        self._btn_switch.setEnabled(len(self._available) > 1)
        self._btn_switch.clicked.connect(self._switch_camera)
        dock.addWidget(self._btn_switch)

        root.addLayout(dock)

        self._ctrl.frame_ready.connect(self._on_frame)
        self._ctrl.camera_started.connect(self._on_started)
        self._ctrl.camera_error.connect(self._on_error)
        self._ctrl.photo_saved.connect(self._on_saved)
        self._ctrl.capture_busy.connect(self._on_busy)

        QtCore.QTimer.singleShot(80, lambda: self._ctrl.start_camera(self._current_model, self._mirror_front))

    def _toggle_mode(self, checked: bool) -> None:
        self._hdr_mode = checked
        self._btn_mode.setText("HDR+ 8x" if checked else "Single RAW")

    def _toggle_mirror(self, checked: bool) -> None:
        self._mirror_front = checked
        self._ctrl.set_mirror_front(checked)

    def _on_ev_changed(self) -> None:
        val = self._combo_ev.currentData()
        if val is not None:
            self._ctrl.set_ev_comp(float(val))

    def _on_refocus(self) -> None:
        if self._current_model == "sc1300cs":
            self._ctrl.trigger_refocus()

    def _switch_camera(self) -> None:
        if len(self._available) < 2:
            return
        idx = self._available.index(self._current_model)
        self._current_model = self._available[(idx + 1) % len(self._available)]
        self._btn_mirror.setVisible(self._current_model == "sc820cs")
        self._btn_refocus.setVisible(self._current_model == "sc1300cs")
        self._hud_label.setText(f"Switching to {SENSOR_PROFILES[self._current_model].display_name}...")
        self._ctrl.start_camera(self._current_model, self._mirror_front)

    def _on_shutter(self) -> None:
        self._canvas.trigger_flash()
        self._ctrl.trigger_shutter(self._hdr_mode, self._mirror_front)

    def _open_last_photo(self) -> None:
        if self._last_photo_path:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self._last_photo_path))

    @QtCore.Slot(QtGui.QImage, dict)
    def _on_frame(self, img: QtGui.QImage, hud: dict) -> None:
        self._canvas.set_frame(img)
        prof = SENSOR_PROFILES[self._current_model]
        exp_ms = hud.get("exp_us", 0) / 1000.0
        iso = int(round(100.0 * hud.get("again", 1.0)))
        af_str = ""
        if hud.get("has_af"):
            state_map = {0: "Idle", 1: "Scan", 2: "Lock", 3: "Fail"}
            st = state_map.get(hud.get("af_state"), "Auto")
            lp = hud.get("lens_pos")
            lp_str = f" {float(lp):.1f}D" if lp is not None else ""
            af_str = f" | AF: {st}{lp_str}"
        self._hud_label.setText(
            f"{prof.display_name} ({prof.raw_size[0]}x{prof.raw_size[1]}) | "
            f"{hud.get('fps', 0):.1f} fps | {exp_ms:.1f}ms ISO {iso} | {hud.get('ct', 0)}K{af_str}"
        )

    @QtCore.Slot(str, int, int)
    def _on_started(self, model: str, vw: int, vh: int) -> None:
        self._status_label.setText(f"Live ZSL ({vw}x{vh})")

    @QtCore.Slot(str)
    def _on_error(self, msg: str) -> None:
        self._status_label.setText(msg)

    @QtCore.Slot(bool, str)
    def _on_busy(self, busy: bool, msg: str) -> None:
        self._status_label.setText(msg)
        self._btn_shutter.setEnabled(not busy)

    @QtCore.Slot(str, QtGui.QImage, str)
    def _on_saved(self, path: str, thumb: QtGui.QImage, msg: str) -> None:
        self._last_photo_path = path
        self._btn_thumb.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(thumb)))
        self._status_label.setText(msg)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._ctrl.stop_camera()
        super().closeEvent(event)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("opd-camera")
    app.setDesktopFileName("opd-camera")
    app.setWindowIcon(QtGui.QIcon.fromTheme("camera-photo"))
    win = CameraMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
