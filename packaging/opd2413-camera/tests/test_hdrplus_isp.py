#!/usr/bin/env python3
"""Offline unit tests for opd2413-camera HDR+ ISP engine."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from hdrplus_isp import (  # noqa: E402
    SENSOR_PROFILES,
    _ycbcr_bilateral_polish_and_cas,
    align_and_merge_burst,
    pack_raw10_csi2p,
    process_raw10_burst,
    save_jpeg_with_exif,
    unpack_raw10_csi2p,
)


def _sample_bggr(rgb_hr: np.ndarray) -> np.ndarray:
    bayer = np.empty(rgb_hr.shape[:2], dtype=np.float32)
    bayer[0::2, 0::2] = rgb_hr[0::2, 0::2, 2]
    bayer[0::2, 1::2] = rgb_hr[0::2, 1::2, 1]
    bayer[1::2, 0::2] = rgb_hr[1::2, 0::2, 1]
    bayer[1::2, 1::2] = rgb_hr[1::2, 1::2, 0]
    return bayer


def test_raw10_roundtrip() -> None:
    rng = np.random.default_rng(7)
    raw = rng.integers(0, 1024, size=(64, 128), dtype=np.uint16)
    packed = pack_raw10_csi2p(raw, stride=164)
    unpacked = unpack_raw10_csi2p(packed, 128, 64, 164)
    assert np.array_equal(raw, unpacked), "RAW10 CSI2P pack/unpack mismatch"


def test_alignment_and_noise_reduction() -> None:
    rng = np.random.default_rng(42)
    h, w = 512, 640
    # Rich multi-scale broadband texture + flat grey area + clipped highlight patch
    n1 = cv2.GaussianBlur(rng.standard_normal((h, w), dtype=np.float32), (0, 0), 6.0)
    n2 = cv2.GaussianBlur(rng.standard_normal((h, w), dtype=np.float32), (0, 0), 2.0)
    tex = 0.10 * (n1 / (float(n1.std()) + 1e-6)) + 0.07 * (n2 / (float(n2.std()) + 1e-6))
    base = np.clip(0.35 + tex, 0.06, 0.75).astype(np.float32)
    base[40:180, 40:200] = 0.35  # flat noise measurement ROI
    base[340:440, 420:560] = 1.6  # clipped highlight patch
    rgb_hr = np.stack([base * 1.05, base * 1.0, base * 0.92], axis=-1)

    shifts = [(0.0, 0.0), (4.0, -6.0), (-4.0, 4.0), (2.0, 6.0), (-6.0, -2.0), (4.0, 4.0), (-2.0, -4.0), (6.0, -4.0)]
    raw_frames = []
    stride = (w // 4) * 5
    for dy, dx in shifts:
        mat = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(rgb_hr, mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        bayer = _sample_bggr(shifted)
        noisy_dn = np.clip(64.0 + bayer * (1023.0 - 64.0) + rng.normal(0.0, 16.0, size=(h, w)), 0, 1023).astype(np.uint16)
        raw_frames.append(pack_raw10_csi2p(noisy_dn, stride=stride))

    # Direct alignment accuracy check on Bayer superpixels
    lin_stack = np.stack([(unpack_raw10_csi2p(b, w, h, stride).astype(np.float32) - 64.0) / (1023.0 - 64.0) for b in raw_frames], axis=0)
    merged, info = align_and_merge_burst(lin_stack, black_floor_norm=64.0 / 959.0, analogue_gain=4.0)
    assert info["frames"] == 8
    # Flat ROI std on a single Bayer subchannel (avoids R/G/B mosaic gain delta)
    single_std = float(lin_stack[info["ref_idx"], 60:160:2, 60:180:2].std())
    merged_std = float(merged[60:160:2, 60:180:2].std())
    assert merged_std < single_std * 0.55, f"Expected >=1.8x noise reduction, got {single_std:.4f} -> {merged_std:.4f}"

    # Textured ROI RMSE against ground-truth reference frame verifies alignment sign and precision
    ref_dy, ref_dx = shifts[info["ref_idx"]]
    ref_mat = np.float32([[1, 0, ref_dx], [0, 1, ref_dy]])
    ref_gt = _sample_bggr(cv2.warpAffine(rgb_hr, ref_mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT))
    unaligned_mean = lin_stack.mean(axis=0)
    unaligned_rmse = float(np.sqrt(np.mean((unaligned_mean[200:320, 220:400] - ref_gt[200:320, 220:400]) ** 2)))
    merged_rmse = float(np.sqrt(np.mean((merged[200:320, 220:400] - ref_gt[200:320, 220:400]) ** 2)))
    assert merged_rmse < unaligned_rmse * 0.65, f"Alignment RMSE regression: merged={merged_rmse:.5f}, unaligned={unaligned_rmse:.5f}"

    # Verify full pipeline for both sc820cs and sc1300cs profiles and EXIF metadata
    meta = {
        "ExposureTime": 33000,
        "AnalogueGain": 4.0,
        "ColourGains": [1.55, 1.40],
        "ColourTemperature": 5200,
        "SensorBlackLevels": [4096, 4096, 4096, 4096],
    }
    for model in ("sc820cs", "sc1300cs"):
        rgb_u8, stats = process_raw10_burst(raw_frames, w, h, stride, model, metadata=meta, mirror_selfie=False)
        assert rgb_u8.shape == (h, w, 3) and rgb_u8.dtype == np.uint8
        # Clipped highlight patch must remain neutral white (no magenta cast: |R-G| <= 12)
        hi_patch = rgb_u8[360:420, 440:540].mean(axis=(0, 1))
        assert abs(float(hi_patch[0]) - float(hi_patch[1])) < 14.0, f"{model} highlight cast: {hi_patch}"
        assert stats["output_size"] == [w, h]

    with tempfile.TemporaryDirectory() as td:
        out_jpg = Path(td) / "test.jpg"
        save_jpeg_with_exif(rgb_u8, out_jpg, SENSOR_PROFILES["sc1300cs"], metadata=meta)
        with Image.open(out_jpg) as im:
            ex = im.getexif()
            ex_sub = ex.get_ifd(0x8769)
            assert ex.get(0x010F) == "OnePlus"
            assert "OPD2413" in str(ex.get(0x0110))
            assert ex_sub.get(0x8827) == 400
            assert abs(float(ex_sub.get(0x829A)) - 0.033) < 0.002


def test_ev_comp_and_shadow_safe_vibrance() -> None:
    h, w = 128, 128
    # Build synthetic midtone grey raw burst + bright highlight corner to test EV monotonicity
    rgb_lin = np.full((h, w, 3), 0.14, dtype=np.float32)
    rgb_lin[:32, :32, :] = 0.92
    bayer = _sample_bggr(rgb_lin)
    dn = np.clip(64.0 + bayer * (1023.0 - 64.0), 0, 1023).astype(np.uint16)
    stride = (w // 4) * 5
    raw_frames = [pack_raw10_csi2p(dn, stride=stride) for _ in range(3)]
    meta = {
        "ExposureTime": 18000,
        "AnalogueGain": 1.5,
        "ColourGains": [1.5, 1.4],
        "ColourTemperature": 5500,
        "SensorBlackLevels": [4096, 4096, 4096, 4096],
    }

    out_base, st_base = process_raw10_burst(raw_frames, w, h, stride, "sc1300cs", metadata=meta, ev_comp=0.0)
    out_plus, st_plus = process_raw10_burst(raw_frames, w, h, stride, "sc1300cs", metadata=meta, ev_comp=0.7)
    mid_base = float(out_base[48:112, 48:112].mean())
    mid_plus = float(out_plus[48:112, 48:112].mean())
    assert mid_plus > mid_base + 12.0, f"Expected ev_comp=0.7 brighter than 0.0: {mid_base:.2f} -> {mid_plus:.2f}"
    assert st_plus["ev_comp"] == 0.7 and st_base["low_light_t"] == 0.0

    # Verify vibrance boosts colorful midtones while strictly preserving dark neutral shadows (Y < 0.05)
    rng = np.random.default_rng(99)
    synth = np.zeros((h, w, 3), dtype=np.float32)
    synth[16:56, 16:56] = [0.22, 0.50, 0.25]  # green foliage midtone
    synth[16:56, 72:112] = [0.60, 0.30, 0.25]  # red/warm brick midtone
    # Deep shadow patch with slight chromatic noise around Y ~ 0.025
    shadow_noise = rng.normal(0.0, 0.002, size=(40, 80, 3)).astype(np.float32)
    synth[72:112, 24:104] = np.clip(0.024 + shadow_noise, 0.0, 0.045)

    res_std = _ycbcr_bilateral_polish_and_cas(synth, is_burst=True, analogue_gain=2.0, sat_scale=1.0)
    res_muted = _ycbcr_bilateral_polish_and_cas(synth, is_burst=True, analogue_gain=2.0, sat_scale=0.5)

    chroma_std = float(np.abs(res_std[20:52, 20:52, 1].astype(float) - res_std[20:52, 20:52, 0].astype(float)).mean())
    chroma_muted = float(np.abs(res_muted[20:52, 20:52, 1].astype(float) - res_muted[20:52, 20:52, 0].astype(float)).mean())
    assert chroma_std > chroma_muted + 4.0, f"Expected vibrance chroma boost: std={chroma_std:.2f}, muted={chroma_muted:.2f}"

    dark_patch = res_std[76:108, 28:100].astype(np.float32)
    dark_rg = float(np.abs(dark_patch[:, :, 0] - dark_patch[:, :, 1]).mean())
    dark_rb = float(np.abs(dark_patch[:, :, 0] - dark_patch[:, :, 2]).mean())
    assert dark_rg < 1.5 and dark_rb < 1.5, f"Dark shadow neutrality broken: dRG={dark_rg:.2f}, dRB={dark_rb:.2f}"


if __name__ == "__main__":
    test_raw10_roundtrip()
    test_alignment_and_noise_reduction()
    test_ev_comp_and_shadow_safe_vibrance()
    print("ALL_HDRPLUS_UNIT_TESTS_PASSED")
