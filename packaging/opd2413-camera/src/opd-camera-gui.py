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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec/opd2413")
from hdrplus_isp import (  # noqa: E402
    SENSOR_PROFILES,
    process_raw10_burst,
    save_jpeg_with_exif,
)
from video_recorder import (  # noqa: E402
    VideoRecorder,
    should_mirror_front,
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
    video_saved = QtCore.Signal(str, QtGui.QImage, str)
    capture_busy = QtCore.Signal(bool, str)
    recording_state_changed = QtCore.Signal(bool, str)

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
        self._vf_info: Optional[Tuple[int, int, str]] = None
        self._recorder: Optional[VideoRecorder] = None
        self._rec_thumb_rgb: Optional[np.ndarray] = None
        self._rec_mirror_active = False
        self._stopping_recording = False

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
        self._stop_recording_sync()
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=4.0)
        self._thread = None
        with self._lock:
            self._vf_info = None

    def is_recording(self) -> bool:
        with self._lock:
            return self._recorder is not None and self._recorder.is_active

    def recording_elapsed_s(self) -> float:
        with self._lock:
            return self._recorder.elapsed_s if self._recorder is not None else 0.0

    def start_recording(self, mirror_front: bool, enable_audio: bool = True) -> bool:
        with self._lock:
            if self._recorder is not None or self._stopping_recording or self._vf_info is None:
                return False
            vw, vh, pix_fmt = self._vf_info
            model = self._active_model
            mirror_video = should_mirror_front(model, mirror_front)
            vid_dir = Path.home() / "Videos" / "OPD_Camera"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            side = "FRONT" if model == "sc820cs" else "REAR"
            out_path = vid_dir / f"VID_{ts}_{side}.mp4"
            rec = VideoRecorder()
            try:
                rec.start(
                    output_path=out_path,
                    width=vw,
                    height=vh,
                    pix_fmt=pix_fmt,
                    mirror_horizontal=mirror_video,
                    enable_audio=enable_audio,
                    bitrate="8M",
                )
            except Exception as exc:
                self.camera_error.emit(f"Video start error: {exc}")
                return False
            self._recorder = rec
            self._rec_thumb_rgb = None
            self._rec_mirror_active = mirror_video
        self.recording_state_changed.emit(True, "Recording...")
        return True

    def stop_recording(self) -> None:
        with self._lock:
            if self._recorder is None or self._stopping_recording:
                return
            self._stopping_recording = True
            rec = self._recorder
            self._recorder = None
            thumb_rgb = self._rec_thumb_rgb
            self._rec_thumb_rgb = None
        self.recording_state_changed.emit(False, "Saving video...")
        threading.Thread(
            target=self._finalize_recording,
            args=(rec, thumb_rgb),
            name="rec-finalize",
            daemon=True,
        ).start()

    def _stop_recording_sync(self) -> None:
        with self._lock:
            rec = self._recorder
            self._recorder = None
            self._rec_thumb_rgb = None
            self._stopping_recording = False
        if rec is not None:
            try:
                rec.stop()
            except Exception:
                pass

    def _finalize_recording(
        self,
        rec: VideoRecorder,
        thumb_rgb: Optional[np.ndarray],
    ) -> None:
        try:
            res = rec.stop()
            if res.ok:
                if thumb_rgb is not None:
                    thumb_np = cv2.resize(thumb_rgb, (160, 120), interpolation=cv2.INTER_AREA)
                    thumb_np = np.ascontiguousarray(thumb_np)
                    thumb_q = QtGui.QImage(thumb_np.data, 160, 120, 160 * 3, QtGui.QImage.Format_RGB888).copy()
                else:
                    thumb_q = QtGui.QImage()
                audio_tag = "" if res.has_audio else " [no audio]"
                msg = f"Saved {res.path.name} ({res.duration_s:.1f}s){audio_tag}"
                self.video_saved.emit(str(res.path), thumb_q, msg)
            else:
                self.camera_error.emit(f"Video error: {res.error}")
        except Exception as exc:
            self.camera_error.emit(f"Video error: {exc}")
        finally:
            with self._lock:
                self._stopping_recording = False
            self.recording_state_changed.emit(False, "Ready")

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
            if self._pending_post is not None or self._recorder is not None:
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
            vf_pix_fmt = "bgr0" if ("XRGB8888" in vfmt or "ARGB8888" in vfmt) else "rgb0"
            with self._lock:
                self._vf_info = (vw, vh, vf_pix_fmt)
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

                    with self._lock:
                        active_rec = self._recorder
                        rec_need_thumb = active_rec is not None and self._rec_thumb_rgb is None
                        rec_mirror = self._rec_mirror_active

                    # Skip heavy RAW10 memcpy while actively recording video
                    raw_bytes: Optional[bytes] = None
                    if active_rec is None:
                        fb_raw = req.buffers[s_raw]
                        p_raw = fb_raw.planes[0]
                        with mmap.mmap(p_raw.fd, rsize, mmap.MAP_SHARED, mmap.PROT_READ) as mm:
                            raw_bytes = bytes(mm[:rsize])

                    dispatch_job = None
                    do_refocus = False
                    with self._lock:
                        if raw_bytes is not None:
                            self._ring.append((raw_bytes, meta))
                        if self._refocus_pending:
                            self._refocus_pending = False
                            do_refocus = True
                        if self._pending_post is not None and raw_bytes is not None:
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

                    # Push every viewfinder frame to recorder, and throttle UI QImage dispatch
                    emit_ui = (now - last_vf_emit) >= 0.020
                    if active_rec is not None or emit_ui:
                        fb_vf = req.buffers[s_vf]
                        p_vf = fb_vf.planes[0]
                        with mmap.mmap(p_vf.fd, vsize, mmap.MAP_SHARED, mmap.PROT_READ) as mm:
                            if active_rec is not None:
                                if vstride == vw * 4:
                                    active_rec.push_frame(bytes(mm[:vsize]))
                                else:
                                    row_rec = np.frombuffer(mm[:vsize], dtype=np.uint8).reshape(vh, vstride)
                                    active_rec.push_frame(np.ascontiguousarray(row_rec[:, : vw * 4]).tobytes())

                            if emit_ui or rec_need_thumb:
                                row = np.frombuffer(mm[:vsize], dtype=np.uint8).reshape(vh, vstride)
                                if vf_pix_fmt == "bgr0":
                                    bgra = row[:, : vw * 4].reshape(vh, vw, 4)
                                    rgb = bgra[:, :, 2::-1]
                                else:
                                    rgba = row[:, : vw * 4].reshape(vh, vw, 4)
                                    rgb = rgba[:, :, :3]
                                if rec_need_thumb:
                                    thumb_src = rgb[:, ::-1] if rec_mirror else rgb
                                    with self._lock:
                                        if self._rec_thumb_rgb is None:
                                            self._rec_thumb_rgb = np.ascontiguousarray(thumb_src)
                                if emit_ui:
                                    last_vf_emit = now
                                    if should_mirror_front(self._active_model, self._mirror_preview):
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
                    mirror_selfie=should_mirror_front(model, mirror_front),
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
        self._video_mode = False
        self._is_recording = False
        self._mirror_front = True
        self._last_media_path: Optional[str] = None
        self._rec_timer = QtCore.QTimer(self)
        self._rec_timer.setInterval(250)
        self._rec_timer.timeout.connect(self._update_rec_timer)

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
        self._btn_thumb.setToolTip("Open last photo or video")
        self._btn_thumb.clicked.connect(self._open_last_media)
        dock.addWidget(self._btn_thumb)

        self._status_label = QtWidgets.QLabel("Ready")
        self._status_label.setMinimumWidth(180)
        dock.addWidget(self._status_label)

        dock.addStretch(1)

        self._btn_photo_mode = QtWidgets.QPushButton("Photo")
        self._btn_photo_mode.setCheckable(True)
        self._btn_photo_mode.setChecked(True)
        self._btn_photo_mode.clicked.connect(lambda: self._set_capture_mode(False))
        dock.addWidget(self._btn_photo_mode)

        self._btn_shutter = QtWidgets.QPushButton("")
        self._btn_shutter.setFixedSize(78, 78)
        self._btn_shutter.clicked.connect(self._on_shutter)
        dock.addWidget(self._btn_shutter)

        self._btn_video_mode = QtWidgets.QPushButton("Video")
        self._btn_video_mode.setCheckable(True)
        self._btn_video_mode.setChecked(False)
        self._btn_video_mode.clicked.connect(lambda: self._set_capture_mode(True))
        dock.addWidget(self._btn_video_mode)

        dock.addStretch(1)

        self._btn_switch = QtWidgets.QPushButton("Switch Cam")
        self._btn_switch.setEnabled(len(self._available) > 1)
        self._btn_switch.clicked.connect(self._switch_camera)
        dock.addWidget(self._btn_switch)

        root.addLayout(dock)

        self._update_shutter_style()
        self._btn_mirror.setVisible(self._current_model == "sc820cs")

        self._ctrl.frame_ready.connect(self._on_frame)
        self._ctrl.camera_started.connect(self._on_started)
        self._ctrl.camera_error.connect(self._on_error)
        self._ctrl.photo_saved.connect(self._on_saved)
        self._ctrl.video_saved.connect(self._on_saved)
        self._ctrl.capture_busy.connect(self._on_busy)
        self._ctrl.recording_state_changed.connect(self._on_recording_state)

        QtCore.QTimer.singleShot(80, lambda: self._ctrl.start_camera(self._current_model, self._mirror_front))

    def _update_shutter_style(self) -> None:
        if not self._video_mode:
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
        elif self._is_recording:
            self._btn_shutter.setStyleSheet(
                """
                QPushButton {
                    background-color: #e53935;
                    border: 6px solid #f4f6f8;
                    border-radius: 18px;
                }
                QPushButton:pressed {
                    background-color: #b71c1c;
                }
                """
            )
        else:
            self._btn_shutter.setStyleSheet(
                """
                QPushButton {
                    background-color: #e53935;
                    border: 5px solid #f4f6f8;
                    border-radius: 39px;
                }
                QPushButton:pressed {
                    background-color: #b71c1c;
                }
                """
            )

    def _set_capture_mode(self, video_mode: bool) -> None:
        if self._is_recording:
            self._btn_photo_mode.setChecked(not self._video_mode)
            self._btn_video_mode.setChecked(self._video_mode)
            return
        self._video_mode = video_mode
        self._btn_photo_mode.setChecked(not video_mode)
        self._btn_video_mode.setChecked(video_mode)
        self._btn_mode.setVisible(not video_mode)
        self._combo_ev.setVisible(not video_mode)
        self._update_shutter_style()

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
        if len(self._available) < 2 or self._is_recording:
            return
        idx = self._available.index(self._current_model)
        self._current_model = self._available[(idx + 1) % len(self._available)]
        self._btn_mirror.setVisible(self._current_model == "sc820cs")
        self._btn_refocus.setVisible(self._current_model == "sc1300cs")
        self._hud_label.setText(f"Switching to {SENSOR_PROFILES[self._current_model].display_name}...")
        self._ctrl.start_camera(self._current_model, self._mirror_front)

    def _on_shutter(self) -> None:
        if self._video_mode:
            if self._is_recording:
                self._ctrl.stop_recording()
            else:
                self._ctrl.start_recording(self._mirror_front, enable_audio=True)
        else:
            self._canvas.trigger_flash()
            self._ctrl.trigger_shutter(self._hdr_mode, self._mirror_front)

    def _open_last_media(self) -> None:
        if self._last_media_path:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self._last_media_path))

    def _update_rec_timer(self) -> None:
        if not self._is_recording:
            self._rec_timer.stop()
            return
        secs = int(self._ctrl.recording_elapsed_s())
        self._status_label.setText(f"● REC {secs // 60:02d}:{secs % 60:02d}")
        self._status_label.setStyleSheet("color: #ff5252; font-weight: 600;")

    @QtCore.Slot(bool, str)
    def _on_recording_state(self, recording: bool, msg: str) -> None:
        self._is_recording = recording
        saving = (not recording) and (msg == "Saving video...")
        self._btn_shutter.setEnabled(not saving)
        self._btn_photo_mode.setEnabled(not recording and not saving)
        self._btn_video_mode.setEnabled(not recording and not saving)
        self._btn_switch.setEnabled(len(self._available) > 1 and not recording and not saving)
        self._btn_mirror.setEnabled(not recording and not saving)
        self._update_shutter_style()
        if recording:
            self._rec_timer.start()
            self._update_rec_timer()
        else:
            self._rec_timer.stop()
            self._status_label.setStyleSheet("color: #d8dee6;")
            if msg != "Ready":
                self._status_label.setText(msg)

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
        self._last_media_path = path
        if not thumb.isNull():
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
