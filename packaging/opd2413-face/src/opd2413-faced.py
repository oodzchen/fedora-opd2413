#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""OPD2413 native face authentication system D-Bus daemon (org.opd2413.Face1)."""

import configparser
import fcntl
import gc
import json
import math
import mmap
import os
import pwd
import re
import selectors
import signal
import struct
import threading
import time
from pathlib import Path

import cv2
import libcamera as libcam
import numpy as np
from gi.repository import Gio, GLib

BUS_NAME = "org.opd2413.Face1"
BUS_PATH = "/org/opd2413/Face1"
BUS_IFACE = "org.opd2413.Face1"

CONFIG_PATH = Path("/etc/opd2413-face.conf")
DATA_DIR = Path("/var/lib/opd2413-face")
MODEL_DIR = Path("/usr/share/opd2413-face/models")
YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
LOCKSCREEN_SERVICES = frozenset({"kde-face", "kde-fingerprint"})
POLKIT_SERVICES = frozenset({"polkit-1"})
# Must exceed kscreenlocker_greet's 2000ms fast-failure breaker while leaving headroom
# under pam_opd2413_face's D-Bus call timeout (+6000ms slack).
LOCKSCREEN_IDLE_WAIT_S = 2.3
# Polkit arm token is single-use and short-lived so a clicked button cannot linger.
POLKIT_ARM_TTL_S = 8.0

# Linux <linux/dma-buf.h>: _IOW('b', 0, __u64) = 0x40086200
DMA_BUF_IOCTL_SYNC = 0x40086200
DMA_BUF_SYNC_READ = 1
DMA_BUF_SYNC_START = 0
DMA_BUF_SYNC_END = 4

INTROSPECTION_XML = """
<node>
  <interface name='org.opd2413.Face1'>
    <method name='HasEnrolled'>
      <arg type='s' name='username' direction='in'/>
      <arg type='b' name='enrolled' direction='out'/>
    </method>
    <method name='Verify'>
      <arg type='s' name='username' direction='in'/>
      <arg type='s' name='service' direction='in'/>
      <arg type='u' name='timeout_ms' direction='in'/>
      <arg type='b' name='matched' direction='out'/>
      <arg type='s' name='reason' direction='out'/>
      <arg type='d' name='score' direction='out'/>
    </method>
    <method name='EnrollSample'>
      <arg type='s' name='username' direction='in'/>
      <arg type='b' name='replace' direction='in'/>
      <arg type='u' name='timeout_ms' direction='in'/>
      <arg type='b' name='ok' direction='out'/>
      <arg type='u' name='count' direction='out'/>
      <arg type='s' name='message' direction='out'/>
    </method>
    <method name='ClearUser'>
      <arg type='s' name='username' direction='in'/>
      <arg type='b' name='removed' direction='out'/>
    </method>
    <method name='ListUsers'>
      <arg type='a(su)' name='users' direction='out'/>
    </method>
    <method name='GetStatus'>
      <arg type='b' name='busy' direction='out'/>
      <arg type='s' name='state' direction='out'/>
      <arg type='s' name='last_reason' direction='out'/>
    </method>
    <method name='SetLockscreenMode'>
      <arg type='s' name='username' direction='in'/>
      <arg type='b' name='controlled' direction='in'/>
      <arg type='b' name='armed' direction='in'/>
      <arg type='b' name='ok' direction='out'/>
    </method>
    <method name='SetPolkitArmed'>
      <arg type='s' name='username' direction='in'/>
      <arg type='b' name='armed' direction='in'/>
      <arg type='b' name='ok' direction='out'/>
    </method>
    <method name='IsPolkitArmed'>
      <arg type='s' name='username' direction='in'/>
      <arg type='b' name='armed' direction='out'/>
    </method>
    <signal name='StatusChanged'>
      <arg type='s' name='state'/>
      <arg type='s' name='detail'/>
    </signal>
  </interface>
</node>
"""


def load_config():
    cfg = {
        "camera_match": "sc820cs",
        "width": 1280,
        "height": 960,
        "warmup_frames": 8,
        "default_timeout_ms": 3500,
        "cosine_threshold": 0.42,
        "liveness": "standard",
        "required_matches": 2,
        "min_face_px": 96,
        "min_sharpness": 22.0,
        "min_frame_delta": 0.45,
        "reject_when_lid_closed": True,
    }
    if not CONFIG_PATH.exists():
        return cfg

    cp = configparser.ConfigParser()
    cp.read(CONFIG_PATH, encoding="utf-8")
    if "face" not in cp:
        return cfg

    sec = cp["face"]
    cfg["camera_match"] = sec.get("camera_match", cfg["camera_match"]).strip()
    cfg["width"] = sec.getint("width", cfg["width"])
    cfg["height"] = sec.getint("height", cfg["height"])
    cfg["warmup_frames"] = max(0, sec.getint("warmup_frames", cfg["warmup_frames"]))
    cfg["default_timeout_ms"] = max(500, sec.getint("default_timeout_ms", cfg["default_timeout_ms"]))
    cfg["cosine_threshold"] = sec.getfloat("cosine_threshold", cfg["cosine_threshold"])
    cfg["liveness"] = sec.get("liveness", cfg["liveness"]).strip().lower()
    cfg["required_matches"] = max(1, sec.getint("required_matches", cfg["required_matches"]))
    cfg["min_face_px"] = max(32, sec.getint("min_face_px", cfg["min_face_px"]))
    cfg["min_sharpness"] = sec.getfloat("min_sharpness", cfg["min_sharpness"])
    cfg["min_frame_delta"] = sec.getfloat("min_frame_delta", cfg["min_frame_delta"])
    cfg["reject_when_lid_closed"] = sec.getboolean("reject_when_lid_closed", cfg["reject_when_lid_closed"])
    return cfg


def validate_username(username: str):
    if not username or not USERNAME_RE.match(username):
        return None
    try:
        return pwd.getpwnam(username)
    except KeyError:
        return None


def dma_buf_sync(fd: int, start: bool):
    flags = DMA_BUF_SYNC_READ | (DMA_BUF_SYNC_START if start else DMA_BUF_SYNC_END)
    try:
        fcntl.ioctl(fd, DMA_BUF_IOCTL_SYNC, struct.pack("Q", flags))
    except OSError:
        pass


def copy_xrgb8888_bgr(plane, width: int, height: int, stride: int) -> np.ndarray:
    """Map one DMA-BUF XRGB8888 plane via stdlib mmap and copy tightly packed BGR."""
    required = height * stride
    if plane.length < required:
        raise ValueError(f"plane length {plane.length} < required {required}")
    page_off = plane.offset % mmap.PAGESIZE
    map_off = plane.offset - page_off
    map_len = plane.length + page_off
    mm = mmap.mmap(plane.fd, map_len, mmap.PROT_READ, mmap.MAP_SHARED, offset=map_off)
    raw = None
    rows = None
    try:
        raw = np.frombuffer(mm, dtype=np.uint8, count=required, offset=page_off)
        rows = raw.reshape((height, stride))
        return rows[:, : width * 4].reshape((height, width, 4))[:, :, :3].copy()
    finally:
        # Release NumPy views before closing mmap so BufferError cannot mask or fail cleanup.
        rows = None
        raw = None
        mm.close()


def rotate_image(img: np.ndarray, angle: int) -> np.ndarray:
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def check_pose_sanity(face_row: np.ndarray) -> bool:
    # YuNet row: [x, y, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score]
    re_x, re_y = float(face_row[4]), float(face_row[5])
    le_x, le_y = float(face_row[6]), float(face_row[7])
    nt_x, nt_y = float(face_row[8]), float(face_row[9])
    eye_dx = abs(le_x - re_x)
    eye_dy = abs(le_y - re_y)
    if eye_dx < 20.0 or eye_dy > eye_dx * 0.45:
        return False
    min_ex = min(re_x, le_x) - eye_dx * 0.25
    max_ex = max(re_x, le_x) + eye_dx * 0.25
    if not (min_ex <= nt_x <= max_ex):
        return False
    if nt_y <= min(re_y, le_y) - 4.0:
        return False
    return True


def check_strict_screen_spoof(bgr: np.ndarray, face_row: np.ndarray) -> bool:
    """Reject obvious close-up phone/tablet screen spoofs in strict mode."""
    h, w = bgr.shape[:2]
    x, y, bw, bh = [int(v) for v in face_row[:4]]
    x0 = max(0, x - bw // 2)
    y0 = max(0, y - bh // 2)
    x1 = min(w, x + bw + bw // 2)
    y1 = min(h, y + bh + bh // 2)
    roi = bgr[y0:y1, x0:x1]
    if roi.size == 0:
        return True

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    lines = cv2.HoughLinesP(
        edges, 1, math.pi / 180.0, threshold=max(40, bw // 2),
        minLineLength=max(48, int(bw * 0.6)), maxLineGap=10
    )
    if lines is not None and len(lines) >= 6:
        hv_long = 0
        for line in lines[:, 0, :]:
            dx = abs(int(line[2]) - int(line[0]))
            dy = abs(int(line[3]) - int(line[1]))
            if dx < 5 or dy < 5:
                hv_long += 1
        if hv_long >= 4:
            return False

    # High-frequency periodic subpixel / moire ratio on central face
    fx0, fy0 = max(0, x), max(0, y)
    fx1, fy1 = min(w, x + bw), min(h, y + bh)
    face_gray = cv2.cvtColor(bgr[fy0:fy1, fx0:fx1], cv2.COLOR_BGR2GRAY)
    if face_gray.shape[0] >= 64 and face_gray.shape[1] >= 64:
        resized = cv2.resize(face_gray, (128, 128)).astype(np.float32)
        f = np.fft.fftshift(np.fft.fft2(resized))
        mag = np.abs(f)
        yy, xx = np.ogrid[:128, :128]
        r2 = (xx - 64) ** 2 + (yy - 64) ** 2
        high = mag[(r2 > 36 ** 2) & (r2 < 60 ** 2)].mean()
        mid = mag[(r2 > 8 ** 2) & (r2 <= 36 ** 2)].mean() + 1e-6
        if (high / mid) > 0.42:
            return False

    return True


class FaceDaemon:
    def __init__(self, bus: Gio.DBusConnection, loop: GLib.MainLoop):
        self.bus = bus
        self.loop = loop
        self.cfg = load_config()
        self.op_cond = threading.Condition()
        self.op_lock = self.op_cond
        self.busy = False
        self.state = "idle"
        self.last_reason = ""
        self.preferred_angle = 0

        self.active_sender = None
        self.active_cancel = None
        self.active_user = None
        self.active_service = None
        self.active_polkit_owner = None
        self.lock_gates = {}
        self.polkit_arms = {}
        self.waiting_cancels = {}

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(DATA_DIR, 0o700)

        if not YUNET_MODEL.exists() or not SFACE_MODEL.exists():
            raise FileNotFoundError(
                f"Missing ONNX models in {MODEL_DIR}"
            )

        self.detector = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL), "", (480, 360), 0.78, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(SFACE_MODEL), "")

        node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self.reg_id = self.bus.register_object(
            BUS_PATH,
            node_info.interfaces[0],
            self._handle_method_call,
            None,
            None,
        )

        self.name_watch_sub = self.bus.signal_subscribe(
            "org.freedesktop.DBus",
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_name_owner_changed,
        )

        self.lid_watch_sub = self.bus.signal_subscribe(
            "org.freedesktop.UPower",
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            "/org/freedesktop/UPower",
            "org.freedesktop.UPower",
            Gio.DBusSignalFlags.NONE,
            self._on_upower_props_changed,
        )

    def _on_upower_props_changed(self, _conn, _sender, _path, _iface, _signal, params):
        iface_name, changed, _invalidated = params.unpack()
        if iface_name != "org.freedesktop.UPower" or "LidIsClosed" not in changed:
            return
        if bool(changed["LidIsClosed"]) and self.cfg.get("reject_when_lid_closed", True):
            with self.op_lock:
                if self.active_cancel is not None:
                    self.active_cancel.set()

    def _on_name_owner_changed(self, _conn, _sender, _path, _iface, _signal, params):
        _name, old_owner, new_owner = params.unpack()
        if old_owner and not new_owner:
            with self.op_lock:
                woke = False
                if old_owner in (self.active_sender, self.active_polkit_owner) and self.active_cancel is not None:
                    self.active_cancel.set()
                wait_evt = self.waiting_cancels.get(old_owner)
                if wait_evt is not None:
                    wait_evt.set()
                    woke = True
                stale = [u for u, g in self.lock_gates.items() if g.get("owner") == old_owner]
                for u in stale:
                    del self.lock_gates[u]
                    woke = True
                stale_polkit = [u for u, g in self.polkit_arms.items() if g.get("owner") == old_owner]
                for u in stale_polkit:
                    del self.polkit_arms[u]
                    woke = True
                if woke:
                    self.op_cond.notify_all()

    def _emit_status_idle(self, state: str, detail: str):
        try:
            self.bus.emit_signal(
                None,
                BUS_PATH,
                BUS_IFACE,
                "StatusChanged",
                GLib.Variant("(ss)", (state, detail)),
            )
        except Exception:
            pass
        return False

    def _emit_status(self, state: str, detail: str = ""):
        GLib.idle_add(self._emit_status_idle, state, detail)

    def _get_caller_uid(self, sender: str) -> int:
        res = self.bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "GetConnectionUnixUser",
            GLib.Variant("(s)", (sender,)),
            GLib.VariantType("(u)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
        return int(res.unpack()[0])

    def _is_lid_closed(self) -> bool:
        if not self.cfg["reject_when_lid_closed"]:
            return False
        try:
            res = self.bus.call_sync(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", ("org.freedesktop.login1.Manager", "LidClosed")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                500,
                None,
            )
            return bool(res.unpack()[0])
        except Exception:
            return False

    def _user_file(self, username: str) -> Path:
        return DATA_DIR / f"{username}.json"

    def _load_templates(self, username: str):
        p = self._user_file(username)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            tmpls = []
            for vec in data.get("templates", []):
                arr = np.asarray(vec, dtype=np.float32).reshape(1, -1)
                norm = np.linalg.norm(arr)
                if norm > 0:
                    tmpls.append(arr / norm)
            return tmpls
        except Exception:
            return []

    def _save_templates(self, username: str, templates):
        p = self._user_file(username)
        tmp = DATA_DIR / f".{username}.json.tmp.{os.getpid()}"
        payload = {
            "user": username,
            "model": "opencv-yunet-2023mar+sface-2021dec",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "templates": [t.reshape(-1).astype(float).tolist() for t in templates],
        }
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def _select_front_camera(self, cm):
        cams = list(cm.cameras)
        for cam in cams:
            loc = cam.properties.get(libcam.properties.Location, None)
            if loc == libcam.properties.LocationEnum.Front:
                return cam
        needle = self.cfg["camera_match"]
        for cam in cams:
            if needle in cam.id:
                return cam
        return None

    def _detect_largest_face(self, bgr: np.ndarray, angle: int):
        rotated = rotate_image(bgr, angle)
        rh, rw = rotated.shape[:2]
        det_w = 480
        scale = det_w / float(rw)
        det_h = max(64, int(round(rh * scale)))
        small = cv2.resize(rotated, (det_w, det_h), interpolation=cv2.INTER_AREA)
        self.detector.setInputSize((det_w, det_h))
        _, faces = self.detector.detect(small)
        if faces is None or len(faces) == 0:
            return None, rotated

        best = max(faces, key=lambda row: float(row[2] * row[3]))
        full_row = best.copy()
        inv = 1.0 / scale
        full_row[:14] *= inv
        if float(full_row[2]) < self.cfg["min_face_px"]:
            return None, rotated
        return full_row, rotated

    def _detect_any_orientation(self, bgr: np.ndarray):
        order = [self.preferred_angle] + [
            a for a in (0, 90, 270, 180) if a != self.preferred_angle
        ]
        for angle in order:
            face_row, rotated = self._detect_largest_face(bgr, angle)
            if face_row is not None:
                self.preferred_angle = angle
                return face_row, rotated
        return None, None

    def _extract_valid_feature(self, bgr: np.ndarray, prev_crop_gray):
        face_row, rotated = self._detect_any_orientation(bgr)
        if face_row is None:
            return None, prev_crop_gray, "no-face"

        liveness = self.cfg["liveness"]
        if liveness != "off":
            if not check_pose_sanity(face_row):
                return None, prev_crop_gray, "pose"

        aligned = self.recognizer.alignCrop(rotated, face_row)
        crop_gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)

        if liveness != "off":
            sharpness = float(cv2.Laplacian(crop_gray, cv2.CV_64F).var())
            if sharpness < self.cfg["min_sharpness"]:
                return None, prev_crop_gray, "blurry"
            if prev_crop_gray is not None and prev_crop_gray.shape == crop_gray.shape:
                delta = float(np.mean(cv2.absdiff(crop_gray, prev_crop_gray)))
                if delta < self.cfg["min_frame_delta"]:
                    return None, crop_gray, "static-frame"
            if liveness == "strict" and not check_strict_screen_spoof(rotated, face_row):
                return None, crop_gray, "spoof-screen"

        feat = self.recognizer.feature(aligned).reshape(1, -1).astype(np.float32)
        norm = float(np.linalg.norm(feat))
        if norm <= 0.0:
            return None, crop_gray, "bad-feature"
        return feat / norm, crop_gray, "ok"

    def _run_camera_loop(self, timeout_ms: int, cancel_event: threading.Event, frame_cb):
        cm = libcam.CameraManager.singleton()
        cam = None
        allocator = None
        sel = None
        reqs = []
        started = False
        acquired = False
        try:
            cam = self._select_front_camera(cm)
            if cam is None:
                return False, "camera-missing"

            try:
                cam.acquire()
                acquired = True
            except Exception:
                return False, "busy"
            cam_config = cam.generate_configuration([libcam.StreamRole.Viewfinder])
            sc = cam_config.at(0)
            sc.size = libcam.Size(self.cfg["width"], self.cfg["height"])
            sc.pixel_format = libcam.PixelFormat("XRGB8888")
            cam_config.validate()
            cam.configure(cam_config)

            stream = sc.stream
            w, h, stride = sc.size.width, sc.size.height, sc.stride

            allocator = libcam.FrameBufferAllocator(cam)
            if allocator.allocate(stream) <= 0:
                return False, "camera-error"

            for i, buf in enumerate(allocator.buffers(stream)):
                req = cam.create_request(i)
                req.add_buffer(stream, buf)
                reqs.append(req)

            cam.start()
            started = True
            for req in reqs:
                cam.queue_request(req)

            sel = selectors.DefaultSelector()
            sel.register(cm.event_fd, selectors.EVENT_READ)

            deadline = time.monotonic() + (timeout_ms / 1000.0)
            frame_idx = 0
            while not cancel_event.is_set() and time.monotonic() < deadline:
                rem = max(0.02, min(0.15, deadline - time.monotonic()))
                if not sel.select(timeout=rem):
                    continue

                ready = cm.get_ready_requests()
                for req in ready:
                    if req.status != libcam.Request.Status.Complete:
                        if not cancel_event.is_set():
                            req.reuse()
                            cam.queue_request(req)
                        continue

                    _, fb = next(iter(req.buffers.items()))
                    frame_idx += 1
                    done = False
                    if frame_idx > self.cfg["warmup_frames"]:
                        plane = fb.planes[0]
                        dma_buf_sync(plane.fd, start=True)
                        try:
                            bgr = copy_xrgb8888_bgr(plane, w, h, stride)
                        finally:
                            dma_buf_sync(plane.fd, start=False)

                        done = frame_cb(bgr)

                    if done or cancel_event.is_set():
                        return True, "done"

                    req.reuse()
                    cam.queue_request(req)

            return True, "cancelled" if cancel_event.is_set() else "timeout"
        except Exception as exc:
            return False, f"camera-error:{exc}"
        finally:
            try:
                if sel is not None:
                    sel.close()
            except Exception:
                pass
            try:
                if started:
                    cam.stop()
            except Exception:
                pass
            reqs.clear()
            del allocator
            if acquired and cam is not None:
                try:
                    cam.release()
                except Exception:
                    pass
            # Drop CameraManager references so weak_ptr singleton resets cleanly between runs.
            cam = None
            cm = None
            gc.collect()

    def _wait_for_lockscreen_arm(self, username: str, timeout_ms: int,
                                 sender: str, cancel_event: threading.Event) -> str:
        """Hold idle lockscreen Verify on op_cond so rapid-fail guards in kscreenlocker stay reset."""
        gate = self.lock_gates.get(username)
        if not gate or not gate.get("controlled"):
            return "run"

        now = time.monotonic()
        if gate.get("armed") and now <= gate.get("armed_until", 0.0):
            gate["armed"] = False
            return "run"

        idle_wait_s = min(LOCKSCREEN_IDLE_WAIT_S, max(0.0, (timeout_ms - 800) / 1000.0))
        deadline = now + idle_wait_s
        self.waiting_cancels[sender] = cancel_event
        try:
            while True:
                if cancel_event.is_set():
                    return "cancelled"
                gate = self.lock_gates.get(username)
                now = time.monotonic()
                if gate is None or not gate.get("controlled"):
                    return "cancelled"
                if gate.get("armed") and now <= gate.get("armed_until", 0.0):
                    gate["armed"] = False
                    return "run"
                rem = deadline - now
                if rem <= 0.0:
                    return "lockscreen-idle"
                self.op_cond.wait(timeout=rem)
        finally:
            if self.waiting_cancels.get(sender) is cancel_event:
                del self.waiting_cancels[sender]

    def _is_polkit_armed_locked(self, username: str) -> bool:
        arm = self.polkit_arms.get(username)
        if not arm:
            return False
        if time.monotonic() > arm.get("armed_until", 0.0):
            del self.polkit_arms[username]
            return False
        return True

    def _do_verify(self, username: str, service: str, timeout_ms: int,
                   sender: str, invocation: Gio.DBusMethodInvocation):
        cancel_event = threading.Event()
        polkit_owner = None
        with self.op_lock:
            self.cfg = load_config()
            if service in LOCKSCREEN_SERVICES:
                wait_res = self._wait_for_lockscreen_arm(username, timeout_ms, sender, cancel_event)
                if wait_res != "run":
                    GLib.idle_add(self._reply_verify, invocation, False, wait_res, 0.0)
                    return

            if service in POLKIT_SERVICES:
                if not self._is_polkit_armed_locked(username):
                    GLib.idle_add(self._reply_verify, invocation, False, "polkit-unarmed", 0.0)
                    return
                arm = self.polkit_arms.pop(username, None)
                polkit_owner = arm.get("owner") if arm else None

            if self.busy and self.active_cancel is not None and self.active_cancel.is_set():
                self.op_cond.wait_for(lambda: not self.busy, timeout=0.9)

            if self.busy:
                if service in LOCKSCREEN_SERVICES or service in POLKIT_SERVICES:
                    self._emit_status("failed", "busy")
                GLib.idle_add(self._reply_verify, invocation, False, "busy", 0.0)
                return

            tmpls = self._load_templates(username)
            if not tmpls:
                if service in LOCKSCREEN_SERVICES or service in POLKIT_SERVICES:
                    self._emit_status("failed", "not-enrolled")
                GLib.idle_add(self._reply_verify, invocation, False, "not-enrolled", 0.0)
                return

            if self._is_lid_closed():
                if service in LOCKSCREEN_SERVICES or service in POLKIT_SERVICES:
                    self._emit_status("failed", "lid-closed")
                GLib.idle_add(self._reply_verify, invocation, False, "lid-closed", 0.0)
                return

            self.busy = True
            self.state = "verifying"
            self.active_sender = sender
            self.active_cancel = cancel_event
            self.active_user = username
            self.active_service = service
            self.active_polkit_owner = polkit_owner if service in POLKIT_SERVICES else None
            self._emit_status("scanning", service)

        state = {
            "matched": False,
            "best_score": 0.0,
            "consecutive": 0,
            "prev_gray": None,
            "last_fail": "no-face",
        }
        threshold = self.cfg["cosine_threshold"]
        req_matches = self.cfg["required_matches"]

        def on_frame(bgr: np.ndarray) -> bool:
            feat, prev_gray, tag = self._extract_valid_feature(bgr, state["prev_gray"])
            state["prev_gray"] = prev_gray
            if feat is None:
                state["consecutive"] = 0
                state["last_fail"] = tag
                return False

            score = max(
                float(self.recognizer.match(t, feat, cv2.FaceRecognizerSF_FR_COSINE))
                for t in tmpls
            )
            state["best_score"] = max(state["best_score"], score)
            if score >= threshold:
                state["consecutive"] += 1
                if state["consecutive"] >= req_matches:
                    state["matched"] = True
                    return True
            else:
                state["consecutive"] = 0
                state["last_fail"] = f"mismatch:{score:.3f}"
            return False

        ok, loop_reason = self._run_camera_loop(timeout_ms, cancel_event, on_frame)
        with self.op_lock:
            self.busy = False
            self.state = "idle"
            self.active_sender = None
            self.active_cancel = None
            self.active_user = None
            self.active_service = None
            self.active_polkit_owner = None
            if state["matched"]:
                reason = f"matched:{state['best_score']:.3f}"
                self._emit_status("matched", f"{state['best_score']:.3f}")
            elif not ok:
                reason = loop_reason
                self._emit_status("failed", reason)
            else:
                reason = state["last_fail"] if loop_reason == "timeout" else loop_reason
                if reason == "cancelled":
                    if self._is_lid_closed():
                        reason = "lid-closed"
                        self._emit_status("failed", reason)
                    else:
                        self._emit_status("idle", "cancelled")
                else:
                    self._emit_status("failed", reason)
            self.last_reason = reason
            self.op_cond.notify_all()

        GLib.idle_add(
            self._reply_verify, invocation, bool(state["matched"]), reason, float(state["best_score"])
        )

    def _do_enroll(self, username: str, replace: bool, timeout_ms: int,
                   invocation: Gio.DBusMethodInvocation):
        cancel_event = threading.Event()
        with self.op_lock:
            self.cfg = load_config()
            if self.busy:
                GLib.idle_add(self._reply_enroll, invocation, False, 0, "busy")
                return
            self.busy = True
            self.state = "enrolling"
            self.active_cancel = cancel_event

        existing = [] if replace else self._load_templates(username)
        result = {"ok": False, "count": len(existing), "msg": "timeout", "prev_gray": None}

        def on_frame(bgr: np.ndarray) -> bool:
            feat, prev_gray, tag = self._extract_valid_feature(bgr, result["prev_gray"])
            result["prev_gray"] = prev_gray
            if feat is None:
                result["msg"] = tag
                return False

            existing.append(feat)
            self._save_templates(username, existing)
            result["ok"] = True
            result["count"] = len(existing)
            result["msg"] = f"enrolled template #{len(existing)}"
            return True

        ok, loop_reason = self._run_camera_loop(timeout_ms, cancel_event, on_frame)
        with self.op_lock:
            self.busy = False
            self.state = "idle"
            self.active_cancel = None
            if not ok and not result["ok"]:
                result["msg"] = loop_reason
            elif not result["ok"] and loop_reason != "timeout":
                result["msg"] = loop_reason
            self.last_reason = result["msg"]
            self.op_cond.notify_all()

        GLib.idle_add(
            self._reply_enroll, invocation, bool(result["ok"]), int(result["count"]), result["msg"]
        )

    @staticmethod
    def _reply_verify(invocation: Gio.DBusMethodInvocation, matched: bool, reason: str, score: float):
        invocation.return_value(GLib.Variant("(bsd)", (matched, reason, score)))
        return False

    @staticmethod
    def _reply_enroll(invocation: Gio.DBusMethodInvocation, ok: bool, count: int, msg: str):
        invocation.return_value(GLib.Variant("(bus)", (ok, count, msg)))
        return False

    def _handle_method_call(self, _conn, sender, _path, _iface, method, params, invocation):
        try:
            caller_uid = self._get_caller_uid(sender)
        except Exception as exc:
            invocation.return_dbus_error("org.opd2413.Face1.Error", str(exc))
            return

        if method == "HasEnrolled":
            username = params.unpack()[0]
            pw = validate_username(username)
            if pw is None or (caller_uid != 0 and caller_uid != pw.pw_uid):
                invocation.return_value(GLib.Variant("(b)", (False,)))
                return
            enrolled = len(self._load_templates(username)) > 0
            invocation.return_value(GLib.Variant("(b)", (enrolled,)))
            return

        if method == "Verify":
            username, service, timeout_ms = params.unpack()
            pw = validate_username(username)
            if pw is None:
                invocation.return_value(GLib.Variant("(bsd)", (False, "unknown-user", 0.0)))
                return
            if caller_uid != 0 and caller_uid != pw.pw_uid:
                invocation.return_dbus_error("org.opd2413.Face1.AccessDenied", "uid mismatch")
                return
            t = timeout_ms if timeout_ms > 0 else self.cfg["default_timeout_ms"]
            threading.Thread(
                target=self._do_verify,
                args=(username, service, int(t), sender, invocation),
                daemon=True,
            ).start()
            return

        if method == "EnrollSample":
            if caller_uid != 0:
                invocation.return_dbus_error("org.opd2413.Face1.AccessDenied", "root required")
                return
            username, replace, timeout_ms = params.unpack()
            if validate_username(username) is None:
                invocation.return_value(GLib.Variant("(bus)", (False, 0, "unknown-user")))
                return
            t = timeout_ms if timeout_ms > 0 else 8000
            threading.Thread(
                target=self._do_enroll,
                args=(username, bool(replace), int(t), invocation),
                daemon=True,
            ).start()
            return

        if method == "ClearUser":
            if caller_uid != 0:
                invocation.return_dbus_error("org.opd2413.Face1.AccessDenied", "root required")
                return
            username = params.unpack()[0]
            if validate_username(username) is None:
                invocation.return_value(GLib.Variant("(b)", (False,)))
                return
            p = self._user_file(username)
            removed = p.exists()
            p.unlink(missing_ok=True)
            invocation.return_value(GLib.Variant("(b)", (removed,)))
            return

        if method == "ListUsers":
            if caller_uid != 0:
                invocation.return_dbus_error("org.opd2413.Face1.AccessDenied", "root required")
                return
            users = []
            for p in sorted(DATA_DIR.glob("*.json")):
                uname = p.stem
                if USERNAME_RE.match(uname):
                    users.append((uname, len(self._load_templates(uname))))
            invocation.return_value(GLib.Variant("(a(su))", (users,)))
            return

        if method == "GetStatus":
            invocation.return_value(
                GLib.Variant("(bss)", (self.busy, self.state, self.last_reason))
            )
            return

        if method == "SetLockscreenMode":
            username, controlled, armed = params.unpack()
            pw = validate_username(username)
            if pw is None or (caller_uid != 0 and caller_uid != pw.pw_uid):
                invocation.return_value(GLib.Variant("(b)", (False,)))
                return
            now = time.monotonic()
            with self.op_lock:
                if controlled:
                    self.lock_gates[username] = {
                        "owner": sender,
                        "controlled": True,
                        "armed": bool(armed),
                        "armed_until": (now + 4.5) if armed else 0.0,
                    }
                    if not armed and self.busy and self.active_user == username and self.active_service in LOCKSCREEN_SERVICES:
                        if self.active_cancel is not None:
                            self.active_cancel.set()
                else:
                    self.lock_gates.pop(username, None)
                self.op_cond.notify_all()
            invocation.return_value(GLib.Variant("(b)", (True,)))
            return

        if method == "SetPolkitArmed":
            username, armed = params.unpack()
            pw = validate_username(username)
            if pw is None or (caller_uid != 0 and caller_uid != pw.pw_uid):
                invocation.return_value(GLib.Variant("(b)", (False,)))
                return
            with self.op_lock:
                if armed:
                    self.polkit_arms[username] = {
                        "owner": sender,
                        "armed_until": time.monotonic() + POLKIT_ARM_TTL_S,
                    }
                else:
                    self.polkit_arms.pop(username, None)
                    if self.busy and self.active_user == username and self.active_service in POLKIT_SERVICES:
                        if self.active_cancel is not None:
                            self.active_cancel.set()
                self.op_cond.notify_all()
            invocation.return_value(GLib.Variant("(b)", (True,)))
            return

        if method == "IsPolkitArmed":
            username = params.unpack()[0]
            pw = validate_username(username)
            if pw is None or (caller_uid != 0 and caller_uid != pw.pw_uid):
                invocation.return_value(GLib.Variant("(b)", (False,)))
                return
            with self.op_lock:
                armed = self._is_polkit_armed_locked(username)
            invocation.return_value(GLib.Variant("(b)", (armed,)))
            return

        invocation.return_dbus_error(
            "org.freedesktop.DBus.Error.UnknownMethod", f"Unknown method {method}"
        )


def main():
    loop = GLib.MainLoop()
    state = {"daemon": None}

    def on_bus_acquired(conn, _name):
        state["daemon"] = FaceDaemon(conn, loop)

    def on_name_lost(_conn, _name):
        loop.quit()

    Gio.bus_own_name(
        Gio.BusType.SYSTEM,
        BUS_NAME,
        Gio.BusNameOwnerFlags.NONE,
        on_bus_acquired,
        None,
        on_name_lost,
    )

    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda *_: loop.quit() or False)

    loop.run()


if __name__ == "__main__":
    main()
