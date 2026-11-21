#!/usr/bin/env python3
"""Offline unit tests for opd2413-camera video recording and mirror orientation."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time

import cv2
import numpy as np

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from video_recorder import (  # noqa: E402
    VideoRecorder,
    build_ffmpeg_command,
    should_mirror_front,
)


def test_should_mirror_front() -> None:
    assert should_mirror_front("sc820cs", True) is True
    assert should_mirror_front("sc820cs", False) is False
    assert should_mirror_front("sc1300cs", True) is False
    assert should_mirror_front("sc1300cs", False) is False


def test_build_ffmpeg_command() -> None:
    out = Path("/tmp/test.mp4")
    cmd_mirrored = build_ffmpeg_command(640, 480, "bgr0", out, mirror_horizontal=True, enable_audio=True)
    assert "-vf" in cmd_mirrored and "hflip" in cmd_mirrored
    assert "pulse" in cmd_mirrored and "-shortest" in cmd_mirrored

    cmd_plain = build_ffmpeg_command(640, 480, "rgb0", out, mirror_horizontal=False, enable_audio=False)
    assert "-vf" not in cmd_plain and "hflip" not in cmd_plain
    assert "pulse" not in cmd_plain


def _record_and_decode_first_frame(mirror_horizontal: bool) -> np.ndarray:
    w, h = 320, 240
    # Synthetic BGR0 frame: bright red on left half, bright blue on right half
    frame = np.zeros((h, w, 4), dtype=np.uint8)
    frame[:, : w // 2, 2] = 220  # R channel (BGR0 index 2) on left
    frame[:, w // 2 :, 0] = 220  # B channel (BGR0 index 0) on right
    frame_bytes = frame.tobytes()

    with tempfile.TemporaryDirectory() as td:
        out_mp4 = Path(td) / "clip.mp4"
        rec = VideoRecorder()
        rec.start(
            output_path=out_mp4,
            width=w,
            height=h,
            pix_fmt="bgr0",
            mirror_horizontal=mirror_horizontal,
            enable_audio=False,
            bitrate="2M",
        )
        for _ in range(12):
            rec.push_frame(frame_bytes)
            time.sleep(0.02)
        res = rec.stop()
        assert res.ok, f"Recording failed: {res.error}"
        assert res.frames_written >= 10
        assert out_mp4.is_file() and out_mp4.stat().st_size > 1000

        cap = cv2.VideoCapture(str(out_mp4))
        ok, bgr = cap.read()
        cap.release()
        assert ok and bgr is not None and bgr.shape == (h, w, 3)
        return bgr


def test_recorded_orientation_matches_preview() -> None:
    # Unmirrored: left half is red (R > B), right half is blue (B > R)
    bgr_normal = _record_and_decode_first_frame(mirror_horizontal=False)
    left_n = bgr_normal[40:200, 30:130].mean(axis=(0, 1))   # BGR
    right_n = bgr_normal[40:200, 190:290].mean(axis=(0, 1))
    assert left_n[2] > left_n[0] + 100, f"Expected red on left when unmirrored, got BGR={left_n}"
    assert right_n[0] > right_n[2] + 100, f"Expected blue on right when unmirrored, got BGR={right_n}"

    # Mirrored (front camera with Selfie Mirror enabled): left half becomes blue, right half becomes red
    bgr_mirrored = _record_and_decode_first_frame(mirror_horizontal=True)
    left_m = bgr_mirrored[40:200, 30:130].mean(axis=(0, 1))
    right_m = bgr_mirrored[40:200, 190:290].mean(axis=(0, 1))
    assert left_m[0] > left_m[2] + 100, f"Expected blue on left when mirrored, got BGR={left_m}"
    assert right_m[2] > right_m[0] + 100, f"Expected red on right when mirrored, got BGR={right_m}"


if __name__ == "__main__":
    test_should_mirror_front()
    test_build_ffmpeg_command()
    test_recorded_orientation_matches_preview()
    print("ALL_VIDEO_RECORDER_UNIT_TESTS_PASSED")
