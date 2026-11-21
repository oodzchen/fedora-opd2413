#!/usr/bin/env python3
"""Async FFmpeg video recorder for opd-camera with preview-consistent orientation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
from typing import Deque, List, Optional


def should_mirror_front(model: str, mirror_front: bool) -> bool:
    """Return True when front camera output (preview, photo, or video) should be mirrored."""
    return bool(mirror_front and model == "sc820cs")


def build_ffmpeg_command(
    width: int,
    height: int,
    pix_fmt: str,
    output_path: Path,
    mirror_horizontal: bool = False,
    enable_audio: bool = True,
    bitrate: str = "8M",
) -> List[str]:
    """Build an FFmpeg command for low-latency rawvideo + PulseAudio MP4 recording."""
    cmd: List[str] = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-use_wallclock_as_timestamps",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        pix_fmt,
        "-s",
        f"{width}x{height}",
        "-i",
        "pipe:0",
    ]
    if enable_audio:
        cmd.extend(
            [
                "-use_wallclock_as_timestamps",
                "1",
                "-thread_queue_size",
                "64",
                "-f",
                "pulse",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-i",
                "default",
            ]
        )
    if mirror_horizontal:
        cmd.extend(["-vf", "hflip"])

    cmd.extend(
        [
            "-c:v",
            "libopenh264",
            "-b:v",
            bitrate,
            "-pix_fmt",
            "yuv420p",
            "-fps_mode",
            "vfr",
        ]
    )
    if enable_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "128k", "-shortest"])

    cmd.extend(["-movflags", "+faststart", str(output_path)])
    return cmd


@dataclass
class VideoRecordingResult:
    path: Path
    duration_s: float
    frames_written: int
    frames_dropped: int
    has_audio: bool
    ok: bool
    error: str = ""


class VideoRecorder:
    """Non-blocking FFmpeg pipe recorder for live libcamera viewfinder frames."""

    def __init__(self, max_queue: int = 10) -> None:
        self._max_queue = max_queue
        self._queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=max_queue)
        self._proc: Optional[subprocess.Popen[bytes]] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stderr_lines: Deque[str] = deque(maxlen=25)
        self._output_path: Optional[Path] = None
        self._has_audio = False
        self._start_ts = 0.0
        self._frames_written = 0
        self._frames_dropped = 0
        self._active = False
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def elapsed_s(self) -> float:
        if not self._active or self._start_ts <= 0.0:
            return 0.0
        return max(0.0, time.monotonic() - self._start_ts)

    def _spawn(
        self,
        output_path: Path,
        width: int,
        height: int,
        pix_fmt: str,
        mirror_horizontal: bool,
        enable_audio: bool,
        bitrate: str,
    ) -> subprocess.Popen[bytes]:
        cmd = build_ffmpeg_command(
            width=width,
            height=height,
            pix_fmt=pix_fmt,
            output_path=output_path,
            mirror_horizontal=mirror_horizontal,
            enable_audio=enable_audio,
            bitrate=bitrate,
        )
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def start(
        self,
        output_path: Path,
        width: int,
        height: int,
        pix_fmt: str = "bgr0",
        mirror_horizontal: bool = False,
        enable_audio: bool = True,
        bitrate: str = "8M",
    ) -> None:
        with self._lock:
            if self._active:
                raise RuntimeError("Recorder is already running")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._queue = queue.Queue(maxsize=self._max_queue)
            self._stderr_lines.clear()
            self._frames_written = 0
            self._frames_dropped = 0
            self._output_path = output_path

            proc = self._spawn(
                output_path=output_path,
                width=width,
                height=height,
                pix_fmt=pix_fmt,
                mirror_horizontal=mirror_horizontal,
                enable_audio=enable_audio,
                bitrate=bitrate,
            )
            has_audio = enable_audio

            # Brief startup probe: if audio input fails immediately, fall back to video-only
            if enable_audio:
                time.sleep(0.12)
                if proc.poll() is not None:
                    try:
                        if proc.stderr:
                            proc.stderr.close()
                        if proc.stdin:
                            proc.stdin.close()
                    except Exception:
                        pass
                    proc = self._spawn(
                        output_path=output_path,
                        width=width,
                        height=height,
                        pix_fmt=pix_fmt,
                        mirror_horizontal=mirror_horizontal,
                        enable_audio=False,
                        bitrate=bitrate,
                    )
                    has_audio = False

            self._proc = proc
            self._has_audio = has_audio
            self._start_ts = time.monotonic()
            self._active = True

            self._stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(proc,),
                name="rec-stderr",
                daemon=True,
            )
            self._stderr_thread.start()

            self._writer_thread = threading.Thread(
                target=self._writer_loop,
                args=(proc,),
                name="rec-writer",
                daemon=True,
            )
            self._writer_thread.start()

    def _drain_stderr(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.stderr is None:
            return
        try:
            for raw in proc.stderr:
                line = raw.decode(errors="replace").strip()
                if line:
                    self._stderr_lines.append(line)
        except Exception:
            pass

    def _writer_loop(self, proc: subprocess.Popen[bytes]) -> None:
        stdin = proc.stdin
        if stdin is None:
            return
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                try:
                    stdin.write(item)
                    self._frames_written += 1
                except (BrokenPipeError, OSError):
                    break
        finally:
            try:
                stdin.flush()
            except Exception:
                pass
            try:
                stdin.close()
            except Exception:
                pass

    def push_frame(self, frame_bytes: bytes) -> bool:
        if not self._active:
            return False
        try:
            self._queue.put_nowait(frame_bytes)
            return True
        except queue.Full:
            self._frames_dropped += 1
            return False

    def stop(self) -> VideoRecordingResult:
        with self._lock:
            if not self._active or self._proc is None or self._output_path is None:
                return VideoRecordingResult(
                    path=self._output_path or Path(""),
                    duration_s=0.0,
                    frames_written=0,
                    frames_dropped=0,
                    has_audio=False,
                    ok=False,
                    error="Recorder is not running",
                )
            self._active = False
            proc = self._proc
            writer = self._writer_thread
            stderr_t = self._stderr_thread
            out_path = self._output_path
            has_audio = self._has_audio
            duration_s = max(0.0, time.monotonic() - self._start_ts)
            self._proc = None
            self._writer_thread = None
            self._stderr_thread = None

        # Signal writer thread to drain remaining frames and close stdin
        while True:
            try:
                self._queue.put(None, timeout=0.2)
                break
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._frames_dropped += 1
                except queue.Empty:
                    pass

        if writer is not None and writer.is_alive():
            writer.join(timeout=4.0)

        # Wait for graceful EOF exit (-shortest), then fall back to SIGINT/terminate
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=4.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2.0)

        if stderr_t is not None and stderr_t.is_alive():
            stderr_t.join(timeout=1.0)

        rc = proc.returncode
        exists = out_path.is_file() and out_path.stat().st_size > 0
        ok = exists and self._frames_written > 0 and rc in (0, 255, -signal.SIGINT)
        err = "" if ok else ("; ".join(self._stderr_lines) or f"ffmpeg exited with code {rc}")
        return VideoRecordingResult(
            path=out_path,
            duration_s=duration_s,
            frames_written=self._frames_written,
            frames_dropped=self._frames_dropped,
            has_audio=has_audio,
            ok=ok,
            error=err,
        )
