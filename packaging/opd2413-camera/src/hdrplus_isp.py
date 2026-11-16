#!/usr/bin/env python3
"""OPD2413 Multi-Frame RAW10 HDR+ & Single-Frame Computational ISP Engine.

Supports both sc820cs (8MP front) and sc1300cs (13MP rear) sensors on
OnePlus Pad 2 Pro using OpenCV (C++/NEON) + NumPy + Pillow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class SensorProfile:
    model: str
    display_name: str
    lens_label: str
    f_number: float
    focal_length_mm: float
    bayer_order: str
    raw_rotation: int
    default_black_level_10b: float
    chroma_damping: float
    lsc: Dict[str, Tuple[float, float, float, float]]
    ccms: List[Tuple[float, np.ndarray]]
    awb_warm_bias: Tuple[float, float]
    preview_size: Tuple[int, int]
    raw_size: Tuple[int, int]


SENSOR_PROFILES: Dict[str, SensorProfile] = {
    "sc820cs": SensorProfile(
        model="sc820cs",
        display_name="Front 8MP",
        lens_label="OnePlus Pad 2 Pro Front 8MP (sc820cs)",
        f_number=2.0,
        focal_length_mm=2.4,
        # Hardware HFLIP+VFLIP keeps stream upright; actual memory order is BGGR
        bayer_order="BGGR",
        raw_rotation=0,
        default_black_level_10b=4100.0 / 64.0,
        chroma_damping=0.32,
        lsc={
            "r": (0.4800, 0.5000, 2.6230, -0.7705),
            "g": (0.4740, 0.4980, 2.4709, -0.7512),
            "b": (0.4680, 0.5000, 2.3900, -0.7081),
        },
        ccms=[
            (2300.0, np.array([[1.8673, -0.5707, -0.2966], [-0.4856, 1.7991, -0.3136], [-0.2668, -0.3527, 1.6194]], dtype=np.float32)),
            (2850.0, np.array([[1.8618, -0.5780, -0.2838], [-0.4874, 1.8171, -0.3297], [-0.2676, -0.3422, 1.6098]], dtype=np.float32)),
            (4100.0, np.array([[1.7481, -0.7035, -0.0446], [-0.4211, 1.7487, -0.3276], [-0.1840, -0.6161, 1.8001]], dtype=np.float32)),
            (5050.0, np.array([[1.7602, -0.6256, -0.1346], [-0.3731, 1.6710, -0.2979], [-0.1369, -0.4736, 1.6105]], dtype=np.float32)),
            (6500.0, np.array([[1.7502, -0.5851, -0.1650], [-0.3461, 1.7169, -0.3708], [-0.1227, -0.4827, 1.6053]], dtype=np.float32)),
        ],
        awb_warm_bias=(1.035, 0.955),
        preview_size=(1632, 1224),
        raw_size=(3264, 2448),
    ),
    "sc1300cs": SensorProfile(
        model="sc1300cs",
        display_name="Rear 13MP",
        lens_label="OnePlus Pad 2 Pro Rear 13MP (sc1300cs)",
        f_number=2.2,
        focal_length_mm=3.2,
        bayer_order="BGGR",
        raw_rotation=0,
        default_black_level_10b=4100.0 / 64.0,
        chroma_damping=0.50,
        lsc={
            "r": (0.5000, 0.5000, 0.9204, 0.5562),
            "g": (0.5000, 0.5000, 0.8974, 0.5480),
            "b": (0.5000, 0.5000, 0.9183, 0.5402),
        },
        ccms=[
            (2300.0, np.array([[1.7192, -0.3884, -0.3308], [-0.2760, 1.4796, -0.2036], [0.0384, -0.7916, 1.7532]], dtype=np.float32)),
            (2850.0, np.array([[1.6792, -0.3684, -0.3108], [-0.2160, 1.4236, -0.2076], [0.1004, -0.7956, 1.6952]], dtype=np.float32)),
            (3900.0, np.array([[1.5656, -0.4284, -0.1372], [-0.2064, 1.3516, -0.1452], [0.0708, -0.7360, 1.6652]], dtype=np.float32)),
            (5100.0, np.array([[1.5952, -0.4068, -0.1884], [-0.1780, 1.5136, -0.3356], [0.0560, -0.7796, 1.7236]], dtype=np.float32)),
            (6500.0, np.array([[1.6652, -0.4268, -0.2384], [-0.1740, 1.4596, -0.2856], [0.1480, -0.8536, 1.7056]], dtype=np.float32)),
        ],
        awb_warm_bias=(1.015, 0.980),
        preview_size=(2080, 1560),
        raw_size=(4160, 3120),
    ),
}

# Precompiled 5x5 Malvar-He-Cutler convolution kernels (scaled by 8)
_K_G_AT_RB = np.array(
    [
        [0, 0, -1, 0, 0],
        [0, 0, 2, 0, 0],
        [-1, 2, 4, 2, -1],
        [0, 0, 2, 0, 0],
        [0, 0, -1, 0, 0],
    ],
    dtype=np.float32,
) / 8.0

_K_RB_H = np.array(
    [
        [0, 0, 0.5, 0, 0],
        [0, -1, 0, -1, 0],
        [-1, 4, 5, 4, -1],
        [0, -1, 0, -1, 0],
        [0, 0, 0.5, 0, 0],
    ],
    dtype=np.float32,
) / 8.0

_K_RB_V = _K_RB_H.T.copy()

_K_RB_DIAG = np.array(
    [
        [0, 0, -1.5, 0, 0],
        [0, 2, 0, 2, 0],
        [-1.5, 0, 6, 0, -1.5],
        [0, 2, 0, 2, 0],
        [0, 0, -1.5, 0, 0],
    ],
    dtype=np.float32,
) / 8.0


def unpack_raw10_csi2p(buf: bytes | np.ndarray, width: int, height: int, stride: int) -> np.ndarray:
    """Vectorized unpack of MIPI RAW10 CSI2P (4 pixels per 5 bytes) to uint16 [0..1023]."""
    arr = np.frombuffer(buf, dtype=np.uint8)
    expected = height * stride
    if arr.size < expected:
        raise ValueError(f"RAW10 buffer too small: got {arr.size} bytes, expected >= {expected}")
    rows = arr[:expected].reshape(height, stride)
    n_groups = width // 4
    g = rows[:, : n_groups * 5].reshape(height, n_groups, 5).astype(np.uint16)
    lsb = g[:, :, 4]
    out = np.empty((height, n_groups, 4), dtype=np.uint16)
    out[:, :, 0] = (g[:, :, 0] << 2) | (lsb & 0x03)
    out[:, :, 1] = (g[:, :, 1] << 2) | ((lsb >> 2) & 0x03)
    out[:, :, 2] = (g[:, :, 2] << 2) | ((lsb >> 4) & 0x03)
    out[:, :, 3] = (g[:, :, 3] << 2) | ((lsb >> 6) & 0x03)
    return out.reshape(height, width)


def pack_raw10_csi2p(raw10: np.ndarray, stride: Optional[int] = None) -> bytes:
    """Pack uint16 [0..1023] Bayer image into MIPI RAW10 CSI2P bytes (for unit tests)."""
    h, w = raw10.shape
    if w % 4 != 0:
        raise ValueError("width must be a multiple of 4")
    n_groups = w // 4
    if stride is None:
        stride = n_groups * 5
    vals = np.clip(raw10, 0, 1023).astype(np.uint16).reshape(h, n_groups, 4)
    out = np.zeros((h, stride), dtype=np.uint8)
    packed = out[:, : n_groups * 5].reshape(h, n_groups, 5)
    packed[:, :, 0] = (vals[:, :, 0] >> 2).astype(np.uint8)
    packed[:, :, 1] = (vals[:, :, 1] >> 2).astype(np.uint8)
    packed[:, :, 2] = (vals[:, :, 2] >> 2).astype(np.uint8)
    packed[:, :, 3] = (vals[:, :, 3] >> 2).astype(np.uint8)
    packed[:, :, 4] = (
        (vals[:, :, 0] & 0x03)
        | ((vals[:, :, 1] & 0x03) << 2)
        | ((vals[:, :, 2] & 0x03) << 4)
        | ((vals[:, :, 3] & 0x03) << 6)
    ).astype(np.uint8)
    return out.tobytes()


def split_bayer_4ch(raw: np.ndarray) -> np.ndarray:
    """Split HxW Bayer mosaic into (H/2, W/2, 4) preserving (0,0),(0,1),(1,0),(1,1) phases."""
    return np.stack([raw[0::2, 0::2], raw[0::2, 1::2], raw[1::2, 0::2], raw[1::2, 1::2]], axis=-1)


def merge_bayer_4ch(ch4: np.ndarray) -> np.ndarray:
    """Reassemble (H/2, W/2, 4) Bayer superpixels into (H, W) mosaic."""
    h2, w2, _ = ch4.shape
    out = np.empty((h2 * 2, w2 * 2), dtype=ch4.dtype)
    out[0::2, 0::2] = ch4[:, :, 0]
    out[0::2, 1::2] = ch4[:, :, 1]
    out[1::2, 0::2] = ch4[:, :, 2]
    out[1::2, 1::2] = ch4[:, :, 3]
    return out


def _select_sharpest_frame(g_stack: List[np.ndarray]) -> int:
    scores = []
    for g in g_stack:
        # Downsample 2x once to suppress pure shot noise when scoring focus sharpness
        g_ds = cv2.resize(g, (g.shape[1] // 2, g.shape[0] // 2), interpolation=cv2.INTER_AREA)
        lap = cv2.Laplacian(g_ds, cv2.CV_32F, ksize=3)
        scores.append(float(np.mean(lap * lap)))
    return int(np.argmax(scores))


def _phase_corr_tile(ref_blk: np.ndarray, mov_blk: np.ndarray, win: Optional[np.ndarray] = None) -> Tuple[float, float, float]:
    """Return (dy, dx, response) so mov_blk[y + dy, x + dx] aligns onto ref_blk[y, x].

    OpenCV cv2.phaseCorrelate(src1, src2) returns shift where src2 is displaced by
    (sx, sy) relative to src1, i.e. src2(x + sx, y + sy) matches src1(x, y).
    """
    r = ref_blk - float(ref_blk.mean())
    m = mov_blk - float(mov_blk.mean())
    if float(r.std()) < 1e-5 or float(m.std()) < 1e-5:
        return 0.0, 0.0, 0.0
    shift, response = cv2.phaseCorrelate(r, m, window=win)
    return float(shift[1]), float(shift[0]), float(response)


def align_and_merge_burst(
    raw_lin_burst: np.ndarray,
    black_floor_norm: float,
    analogue_gain: float = 1.0,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Align N Bayer RAW frames at 2x2 superpixel level and merge with anti-ghost robustness."""
    n = raw_lin_burst.shape[0]
    if n == 1:
        return np.maximum(raw_lin_burst[0], 0.0), {
            "frames": 1,
            "ref_idx": 0,
            "mad_noise": 0.0,
            "mean_shift_px": 0.0,
        }

    ch_stack = [split_bayer_4ch(raw_lin_burst[i]).astype(np.float32) for i in range(n)]
    g_stack = [0.5 * (c[:, :, 1] + c[:, :, 2]) for c in ch_stack]
    h2, w2 = g_stack[0].shape

    ref_idx = _select_sharpest_frame(g_stack)
    g_ref = g_stack[ref_idx]

    # 4x downsampled luma proxy for coarse global registration
    cw, ch = max(64, w2 // 4), max(64, h2 // 4)
    g_ref_c = cv2.resize(g_ref, (cw, ch), interpolation=cv2.INTER_AREA)
    win_c = cv2.createHanningWindow((cw, ch), cv2.CV_32F)

    # Tile grid for local phase correlation on half-res green plane
    grid_y, grid_x = 4, 6
    blk_h = min(192, max(64, (h2 // grid_y) & ~1))
    blk_w = min(256, max(64, (w2 // grid_x) & ~1))
    win_t = cv2.createHanningWindow((blk_w, blk_h), cv2.CV_32F)
    ys = np.linspace(0, max(0, h2 - blk_h), grid_y, dtype=np.int32)
    xs = np.linspace(0, max(0, w2 - blk_w), grid_x, dtype=np.int32)

    base_yy, base_xx = np.meshgrid(np.arange(h2, dtype=np.float32), np.arange(w2, dtype=np.float32), indexing="ij")

    aligned_list: List[np.ndarray] = [None] * n  # type: ignore[list-item]
    aligned_list[ref_idx] = ch_stack[ref_idx]
    shift_mags: List[float] = []

    for k in range(n):
        if k == ref_idx:
            continue
        gk = g_stack[k]
        gk_c = cv2.resize(gk, (cw, ch), interpolation=cv2.INTER_AREA)
        cdy, cdx, _ = _phase_corr_tile(g_ref_c, gk_c, win_c)
        gdy = int(np.clip(round(cdy * (h2 / ch)), -(h2 // 6), h2 // 6))
        gdx = int(np.clip(round(cdx * (w2 / cw)), -(w2 // 6), w2 // 6))

        fdy = np.full((grid_y, grid_x), float(gdy), dtype=np.float32)
        fdx = np.full((grid_y, grid_x), float(gdx), dtype=np.float32)
        fconf = np.zeros((grid_y, grid_x), dtype=np.float32)

        for iy, y0 in enumerate(ys):
            for ix, x0 in enumerate(xs):
                my0 = int(np.clip(int(y0) + gdy, 0, h2 - blk_h))
                mx0 = int(np.clip(int(x0) + gdx, 0, w2 - blk_w))
                act_dy = float(my0 - int(y0))
                act_dx = float(mx0 - int(x0))
                r_blk = g_ref[y0 : y0 + blk_h, x0 : x0 + blk_w]
                m_blk = gk[my0 : my0 + blk_h, mx0 : mx0 + blk_w]
                ldy, ldx, resp = _phase_corr_tile(r_blk, m_blk, win_t)
                if abs(ldy) <= 20.0 and abs(ldx) <= 20.0 and resp > 0.08:
                    fdy[iy, ix] = act_dy + ldy
                    fdx[iy, ix] = act_dx + ldx
                    fconf[iy, ix] = resp

        good = fconf > 0.12
        med_dy = float(np.median(fdy[good])) if good.any() else float(gdy)
        med_dx = float(np.median(fdx[good])) if good.any() else float(gdx)
        fdy = np.where(good, fdy, med_dy)
        fdx = np.where(good, fdx, med_dx)
        fdy = cv2.medianBlur(fdy, 3)
        fdx = cv2.medianBlur(fdx, 3)
        shift_mags.append(float(np.hypot(med_dy * 2.0, med_dx * 2.0)))

        # Upsample coarse flow field smoothly across superpixel plane
        full_dy = cv2.resize(fdy, (w2, h2), interpolation=cv2.INTER_LINEAR)
        full_dx = cv2.resize(fdx, (w2, h2), interpolation=cv2.INTER_LINEAR)
        map_x = base_xx + full_dx
        map_y = base_yy + full_dy
        aligned_list[k] = cv2.remap(
            ch_stack[k],
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

    # Estimate temporal single-channel noise variance vs intensity:
    # g = 0.5 * (G1 + G2) has variance 0.5 * sigma^2, so (g_k - g_ref) already has std == sigma.
    diffs = [np.abs((0.5 * (aligned_list[k][:, :, 1] + aligned_list[k][:, :, 2])) - g_ref) for k in range(n) if k != ref_idx]
    mad_noise = float(np.median(diffs[0][::4, ::4])) * 1.4826 if diffs else 0.002
    base_sig = max(mad_noise, 0.0012 * np.sqrt(max(1.0, analogue_gain)))
    sigma0_sq = base_sig * base_sig
    alpha = max(sigma0_sq * 2.5, 4.0e-5 * max(1.0, analogue_gain))

    # Streaming spatial-neighborhood robust HDR+ temporal accumulation
    ref_4 = aligned_list[ref_idx]
    ref_clipped = np.clip(ref_4, 0.0, 1.0)
    # Local noise tolerance variance map per channel (difference of two noisy frames -> 2 * sigma^2)
    noise_var = 2.0 * (sigma0_sq + alpha * ref_clipped) * 1.5

    acc_num = ref_4.copy()
    acc_w = np.ones((h2, w2, 1), dtype=np.float32)

    for k in range(n):
        if k == ref_idx:
            continue
        ak = aligned_list[k]
        # 5x5 local squared discrepancy aggregated across channels catches ghosting cleanly
        sq_err = (ak - ref_4) ** 2
        local_err = cv2.boxFilter(sq_err.mean(axis=2), cv2.CV_32F, (5, 5), normalize=True)
        local_nv = noise_var.mean(axis=2)
        ratio = local_err / np.maximum(local_nv, 1e-8)
        # Keep full weight for noise-level deltas (ratio <= 1.6), decay smoothly for scene motion
        excess = np.maximum(0.0, ratio - 1.6)
        wk = np.exp(-0.75 * excess).astype(np.float32)[:, :, None]
        acc_num += wk * ak
        acc_w += wk

    merged_4ch = acc_num / np.maximum(acc_w, 1e-5)
    merged_bayer = merge_bayer_4ch(np.maximum(merged_4ch, -black_floor_norm))
    return merged_bayer, {
        "frames": n,
        "ref_idx": ref_idx,
        "mad_noise": round(mad_noise, 6),
        "mean_shift_px": round(float(np.mean(shift_mags)) if shift_mags else 0.0, 2),
    }


def compute_radial_lsc_bayer(h: int, w: int, profile: SensorProfile) -> np.ndarray:
    """Compute per-photosite radial LSC multiplier in Bayer mosaic."""
    yy = (np.arange(h, dtype=np.float32) + 0.5) / h
    xx = (np.arange(w, dtype=np.float32) + 0.5) / w

    def eval_ch(params: Tuple[float, float, float, float]) -> np.ndarray:
        cx, cy, k0, k1 = params
        max_dx = max(cx, 1.0 - cx) * w
        max_dy = max(cy, 1.0 - cy) * h
        m2 = max(max_dx * max_dx + max_dy * max_dy, 1.0)
        dy_px = (yy[:, None] - cy) * h
        dx_px = (xx[None, :] - cx) * w
        r2 = (dx_px * dx_px + dy_px * dy_px) / m2
        return np.maximum(1.0, 1.0 + k0 * r2 + k1 * r2 * r2).astype(np.float32)

    g_gain = eval_ch(profile.lsc["g"])
    r_raw = eval_ch(profile.lsc["r"])
    b_raw = eval_ch(profile.lsc["b"])

    damping = profile.chroma_damping
    r_gain = g_gain * (1.0 + damping * (r_raw / g_gain - 1.0))
    b_gain = g_gain * (1.0 + damping * (b_raw / g_gain - 1.0))

    lsc = np.empty((h, w), dtype=np.float32)
    if profile.bayer_order == "BGGR":
        lsc[0::2, 0::2] = b_gain[0::2, 0::2]
        lsc[0::2, 1::2] = g_gain[0::2, 1::2]
        lsc[1::2, 0::2] = g_gain[1::2, 0::2]
        lsc[1::2, 1::2] = r_gain[1::2, 1::2]
    elif profile.bayer_order == "RGGB":
        lsc[0::2, 0::2] = r_gain[0::2, 0::2]
        lsc[0::2, 1::2] = g_gain[0::2, 1::2]
        lsc[1::2, 0::2] = g_gain[1::2, 0::2]
        lsc[1::2, 1::2] = b_gain[1::2, 1::2]
    elif profile.bayer_order == "GRBG":
        lsc[0::2, 0::2] = g_gain[0::2, 0::2]
        lsc[0::2, 1::2] = r_gain[0::2, 1::2]
        lsc[1::2, 0::2] = b_gain[1::2, 0::2]
        lsc[1::2, 1::2] = g_gain[1::2, 1::2]
    elif profile.bayer_order == "GBRG":
        lsc[0::2, 0::2] = g_gain[0::2, 0::2]
        lsc[0::2, 1::2] = b_gain[0::2, 1::2]
        lsc[1::2, 0::2] = r_gain[1::2, 0::2]
        lsc[1::2, 1::2] = g_gain[1::2, 1::2]
    else:
        raise ValueError(f"Unsupported Bayer order: {profile.bayer_order}")
    return lsc


def demosaic_malvar_cv(bayer: np.ndarray, bayer_order: str = "BGGR") -> np.ndarray:
    """OpenCV-accelerated 5x5 Malvar-He-Cutler demosaic + chroma-diff zipper suppression."""
    b32 = np.ascontiguousarray(bayer, dtype=np.float32)
    g_rb = cv2.filter2D(b32, cv2.CV_32F, _K_G_AT_RB, borderType=cv2.BORDER_REFLECT_101)
    rb_h = cv2.filter2D(b32, cv2.CV_32F, _K_RB_H, borderType=cv2.BORDER_REFLECT_101)
    rb_v = cv2.filter2D(b32, cv2.CV_32F, _K_RB_V, borderType=cv2.BORDER_REFLECT_101)
    rb_d = cv2.filter2D(b32, cv2.CV_32F, _K_RB_DIAG, borderType=cv2.BORDER_REFLECT_101)

    if bayer_order == "BGGR":
        ry, rx = 1, 1
        by, bx = 0, 0
    elif bayer_order == "RGGB":
        ry, rx = 0, 0
        by, bx = 1, 1
    elif bayer_order == "GRBG":
        ry, rx = 0, 1
        by, bx = 1, 0
    elif bayer_order == "GBRG":
        ry, rx = 1, 0
        by, bx = 0, 1
    else:
        raise ValueError(f"Unsupported Bayer order: {bayer_order}")

    G = b32.copy()
    G[ry::2, rx::2] = g_rb[ry::2, rx::2]
    G[by::2, bx::2] = g_rb[by::2, bx::2]

    R = np.empty_like(b32)
    R[ry::2, rx::2] = b32[ry::2, rx::2]
    R[ry::2, (1 - rx)::2] = rb_h[ry::2, (1 - rx)::2]
    R[(1 - ry)::2, rx::2] = rb_v[(1 - ry)::2, rx::2]
    R[by::2, bx::2] = rb_d[by::2, bx::2]

    B = np.empty_like(b32)
    B[by::2, bx::2] = b32[by::2, bx::2]
    B[by::2, (1 - bx)::2] = rb_h[by::2, (1 - bx)::2]
    B[(1 - by)::2, bx::2] = rb_v[(1 - by)::2, bx::2]
    B[ry::2, rx::2] = rb_d[ry::2, rx::2]

    # Mild chroma-difference 3x3 median suppression removes Bayer moire
    rg = R - G
    bg = B - G
    R = G + 0.5 * rg + 0.5 * cv2.medianBlur(rg, 3)
    B = G + 0.5 * bg + 0.5 * cv2.medianBlur(bg, 3)
    return np.maximum(np.stack([R, G, B], axis=-1), 0.0).astype(np.float32)


def reconstruct_clipped_highlights(rgb_wb: np.ndarray, raw_lin: np.ndarray, sat_mask: np.ndarray) -> np.ndarray:
    """Desaturate sensor-clipped highlights to neutral white luminance after AWB."""
    k3 = np.ones((3, 3), dtype=np.uint8)
    local_max = cv2.dilate(raw_lin, k3, borderType=cv2.BORDER_REPLICATE)
    sat_dil = cv2.dilate(sat_mask.astype(np.float32), k3, borderType=cv2.BORDER_REPLICATE)
    alpha = np.clip((local_max - 0.965) / 0.032, 0.0, 1.0)
    alpha = np.maximum(alpha, sat_dil)
    if not (alpha > 0.01).any():
        return rgb_wb
    neutral = np.maximum(rgb_wb.max(axis=2, keepdims=True), rgb_wb.mean(axis=2, keepdims=True))
    a = alpha[:, :, None]
    return (rgb_wb * (1.0 - a) + neutral * a).astype(np.float32)


def _interpolate_ccm(profile: SensorProfile, ct: float) -> np.ndarray:
    cts = [c[0] for c in profile.ccms]
    mats = [c[1] for c in profile.ccms]
    if ct <= cts[0]:
        ccm = mats[0].copy()
    elif ct >= cts[-1]:
        ccm = mats[-1].copy()
    else:
        ccm = mats[-1].copy()
        for i in range(len(cts) - 1):
            if cts[i] <= ct <= cts[i + 1]:
                t = (ct - cts[i]) / (cts[i + 1] - cts[i])
                ccm = (1.0 - t) * mats[i] + t * mats[i + 1]
                break
    return (ccm / ccm.sum(axis=1, keepdims=True)).astype(np.float32)


def estimate_awb_and_ccm(
    rgb_lin: np.ndarray,
    profile: SensorProfile,
    hint_gains: Optional[Tuple[float, float]] = None,
    hint_ct: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Hybrid Shades-of-Grey + libcamera-hint AWB and temperature-interpolated CCM."""
    sub = rgb_lin[::4, ::4]
    y = 0.2126 * sub[:, :, 0] + 0.7152 * sub[:, :, 1] + 0.0722 * sub[:, :, 2]
    mx = np.maximum(sub.max(axis=2), 1e-6)
    mn = sub.min(axis=2)
    sat_ratio = (mx - mn) / mx
    mask = (y > 0.03) & (y < 0.78) & (sat_ratio < 0.48)
    if int(mask.sum()) < 400:
        mask = (y > 0.01) & (y < 0.88)
    pts = sub[mask]
    if len(pts) > 16:
        p4 = np.power(np.mean(np.power(np.maximum(pts, 1e-5), 4.0), axis=0), 0.25)
        med = np.median(pts, axis=0)
        illum = 0.65 * p4 + 0.35 * med
        est_r = float(illum[1] / max(float(illum[0]), 1e-5))
        est_b = float(illum[1] / max(float(illum[2]), 1e-5))
    else:
        est_r, est_b = 1.45, 1.45

    if hint_gains is not None and hint_gains[0] > 0.5 and hint_gains[1] > 0.5:
        r_g = 0.45 * float(hint_gains[0]) + 0.55 * est_r
        b_g = 0.45 * float(hint_gains[1]) + 0.55 * est_b
    else:
        r_g, b_g = est_r, est_b

    r_g = float(np.clip(r_g * profile.awb_warm_bias[0], 0.95, 2.55))
    b_g = float(np.clip(b_g * profile.awb_warm_bias[1], 0.95, 2.75))
    gains = np.array([r_g, 1.0, b_g], dtype=np.float32)

    rb_ratio = b_g / max(r_g, 1e-4)
    ct_est = float(np.clip(6500.0 - (rb_ratio - 0.85) * 4200.0, 2300.0, 6500.0))
    if hint_ct is not None and 2000.0 <= hint_ct <= 7500.0:
        ct = 0.45 * float(hint_ct) + 0.55 * ct_est
    else:
        ct = ct_est

    ccm = _interpolate_ccm(profile, ct)
    return gains, ccm, ct


def _linear_to_srgb(x: np.ndarray) -> np.ndarray:
    c = np.clip(x, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 1e-8), 1.0 / 2.4) - 0.055).astype(np.float32)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def _exposure_low_light_t(exp_us: float = 20000.0, ag: float = 2.0) -> float:
    exposure_index = max(1.0, (float(exp_us) / 1000.0) * max(1.0, float(ag)))
    return float(np.clip((exposure_index - 110.0) / 360.0, 0.0, 1.0))


def _auto_ev_gain(
    rgb_lin: np.ndarray,
    exp_us: float = 20000.0,
    ag: float = 2.0,
    ev_comp: float = 0.0,
) -> float:
    h, w, _ = rgb_lin.shape
    y = 0.2126 * rgb_lin[:, :, 0] + 0.7152 * rgb_lin[:, :, 1] + 0.0722 * rgb_lin[:, :, 2]
    # Center 50% area weighted ~2.6x heavier than border so background walls don't underexpose subjects
    yc = y[h // 4 : (3 * h) // 4, w // 4 : (3 * w) // 4]
    p_mid = 0.45 * float(np.percentile(yc[::2, ::2], 44)) + 0.55 * float(np.percentile(y[::4, ::4], 44))

    low_light_t = _exposure_low_light_t(exp_us, ag)
    target_mid = 0.345 - 0.060 * low_light_t
    max_ev = 3.15 - 0.70 * low_light_t

    p_hi = float(np.percentile(y[::2, ::2], 99.5))
    max_safe = 3.6 / max(p_hi, 0.06)
    base_gain = float(np.clip(min(target_mid / max(p_mid, 0.012), max_safe), 0.70, max_ev))
    if abs(ev_comp) > 1e-4:
        ev_scale = float(2.0 ** np.clip(ev_comp, -2.0, 2.0))
        return float(np.clip(base_gain * ev_scale, 0.35, max_ev * 1.8))
    return base_gain


def _mertens_exposure_fusion_cv(
    rgb_lin: np.ndarray,
    levels: int = 5,
    exp_us: float = 20000.0,
    ag: float = 2.0,
    ev_comp: float = 0.0,
) -> np.ndarray:
    """Halo-free multi-scale virtual bracket Mertens fusion accelerated with cv2.pyrDown/Up."""
    low_light_t = _exposure_low_light_t(exp_us, ag)
    base_gain = _auto_ev_gain(rgb_lin, exp_us=exp_us, ag=ag, ev_comp=ev_comp)
    ev_factors = [
        base_gain * 0.66,
        base_gain * 1.08,
        base_gain * (1.64 - 0.22 * low_light_t),
    ]
    imgs: List[np.ndarray] = []
    weights: List[np.ndarray] = []

    for g_ev in ev_factors:
        lin_e = rgb_lin * g_ev
        lum = 0.2126 * lin_e[:, :, 0] + 0.7152 * lin_e[:, :, 1] + 0.0722 * lin_e[:, :, 2]
        lum_c = (lum * (1.0 + lum / 9.0)) / (1.0 + 0.42 * lum)
        lin_c = lin_e * (lum_c / np.maximum(lum, 1e-6))[:, :, None]
        im = _linear_to_srgb(lin_c)
        imgs.append(im)

        gray = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]
        lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
        w_exp = np.exp(-0.5 * ((im - 0.56) / 0.35) ** 2).prod(axis=2)
        w_sat = np.std(im, axis=2)
        w_tot = (np.power(lap + 1e-3, 0.15)) * (np.power(w_sat + 0.10, 0.15)) * w_exp + 1e-4
        weights.append(w_tot.astype(np.float32))

    w_sum = weights[0] + weights[1] + weights[2] + 1e-8
    weights = [wt / w_sum for wt in weights]

    g_ws: List[List[np.ndarray]] = [weights]
    g_ims: List[List[np.ndarray]] = [imgs]
    for _ in range(levels - 1):
        g_ws.append([cv2.pyrDown(wt) for wt in g_ws[-1]])
        g_ims.append([cv2.pyrDown(im) for im in g_ims[-1]])

    fused_pyr: List[np.ndarray] = []
    for lv in range(levels):
        if lv == levels - 1:
            acc = g_ims[lv][0] * g_ws[lv][0][:, :, None]
            for k in range(1, 3):
                acc += g_ims[lv][k] * g_ws[lv][k][:, :, None]
            fused_pyr.append(acc)
        else:
            th, tw = g_ims[lv][0].shape[:2]
            acc = np.zeros((th, tw, 3), dtype=np.float32)
            for k in range(3):
                up = cv2.pyrUp(g_ims[lv + 1][k], dstsize=(tw, th))
                lap_k = g_ims[lv][k] - up
                acc += lap_k * g_ws[lv][k][:, :, None]
            fused_pyr.append(acc)

    out = fused_pyr[-1]
    for lv in range(levels - 2, -1, -1):
        th, tw = fused_pyr[lv].shape[:2]
        out = cv2.pyrUp(out, dstsize=(tw, th)) + fused_pyr[lv]

    out = np.clip(out, 0.0, 1.0)
    p_white = float(np.percentile(out[::2, ::2], 99.85))
    if 0.72 <= p_white < 0.995:
        out = np.clip(out / max(p_white, 0.80), 0.0, 1.0)
    lift_gamma = 0.91 + 0.06 * low_light_t
    out = np.power(np.maximum(out, 1e-6), lift_gamma)
    out = np.clip(out - 0.018 * np.sin(2.0 * np.pi * out), 0.0, 1.0)
    return out.astype(np.float32)


def _filmic_tone_map_singleframe(
    rgb_lin: np.ndarray,
    exp_us: float = 20000.0,
    ag: float = 2.0,
    ev_comp: float = 0.0,
) -> np.ndarray:
    low_light_t = _exposure_low_light_t(exp_us, ag)
    ev_scale = _auto_ev_gain(rgb_lin, exp_us=exp_us, ag=ag, ev_comp=ev_comp)
    x = rgb_lin * ev_scale
    y_scaled = 0.2126 * x[:, :, 0] + 0.7152 * x[:, :, 1] + 0.0722 * x[:, :, 2]
    p_hi = float(np.percentile(y_scaled[::2, ::2], 99.0))
    white_pt = max(2.2, p_hi * 1.05)
    y_lifted = np.power(np.maximum(y_scaled, 1e-6), 0.80 + 0.05 * low_light_t)
    y_mapped = (y_lifted * (1.0 + y_lifted / (white_pt * white_pt))) / (1.0 + 0.68 * y_lifted)
    scale = y_mapped / np.maximum(y_scaled, 1e-6)
    mapped = x * scale[:, :, None]
    hi_blend = np.clip((y_mapped - 0.86) / 0.30, 0.0, 0.75)[:, :, None]
    mapped = mapped * (1.0 - hi_blend) + y_mapped[:, :, None] * hi_blend
    srgb = _linear_to_srgb(mapped)
    return np.clip(srgb - 0.018 * np.sin(2.0 * np.pi * srgb), 0.0, 1.0).astype(np.float32)


def _ycbcr_bilateral_polish_and_cas(
    srgb: np.ndarray,
    is_burst: bool,
    analogue_gain: float,
    vibrance: float = 0.26,
    base_sat: float = 0.14,
    sat_scale: float = 1.0,
) -> np.ndarray:
    """Fast OpenCV YCrCb bilateral chroma+luma NR, skin/shadow-gated vibrance, and CAS sharpen."""
    # Convert float RGB [0..1] -> uint8/float YCrCb via OpenCV C++
    u8_rgb = np.round(np.clip(srgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    ycc = cv2.cvtColor(u8_rgb, cv2.COLOR_RGB2YCrCb)
    y_u8, cr_u8, cb_u8 = cv2.split(ycc)
    h, w = y_u8.shape

    # Scale NR mildly with ISO/AnalogueGain while keeping burst outputs super crisp
    gain_boost = float(np.clip(np.sqrt(max(1.0, analogue_gain)) * 0.45, 0.85, 1.85))
    if is_burst:
        chroma_sigma_c = 16.0 * gain_sigma(gain_boost)
        luma_weight = min(0.24, 0.14 * gain_boost)
        cas_amount = 0.34
    else:
        chroma_sigma_c = 22.0 * gain_sigma(gain_boost)
        luma_weight = min(0.45, 0.35 * gain_boost)
        cas_amount = 0.28

    # 2x downsampled wide chroma denoising + residual full-res blend eliminates color blotches rapidly
    cr2 = cv2.resize(cr_u8, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    cb2 = cv2.resize(cb_u8, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    cr2_f = cv2.bilateralFilter(cr2, d=7, sigmaColor=chroma_sigma_c, sigmaSpace=5.0)
    cb2_f = cv2.bilateralFilter(cb2, d=7, sigmaColor=chroma_sigma_c, sigmaSpace=5.0)
    cr_up = cv2.resize(cr2_f, (w, h), interpolation=cv2.INTER_LINEAR)
    cb_up = cv2.resize(cb2_f, (w, h), interpolation=cv2.INTER_LINEAR)
    cr_f = cv2.addWeighted(cr_up, 0.78, cr_u8, 0.22, 0.0)
    cb_f = cv2.addWeighted(cb_up, 0.78, cb_u8, 0.22, 0.0)

    # Light shadow-weighted edge-preserving luma NR
    y_den = cv2.bilateralFilter(y_u8, d=5, sigmaColor=11.0 * gain_boost, sigmaSpace=1.5)
    y_f = y_u8.astype(np.float32) * (1.0 / 255.0)
    yd_f = y_den.astype(np.float32) * (1.0 / 255.0)
    w_nr = luma_weight * np.clip(1.12 - y_f, 0.30, 1.0)
    y_clean = y_f * (1.0 - w_nr) + yd_f * w_nr

    # CAS edge-adaptive sharpening on luma only
    if cas_amount > 0.0:
        p = np.pad(y_clean, 1, mode="edge")
        n = p[:-2, 1:-1]
        s = p[2:, 1:-1]
        wv = p[1:-1, :-2]
        e = p[1:-1, 2:]
        mn = np.minimum(np.minimum(np.minimum(n, s), np.minimum(wv, e)), y_clean)
        mx = np.maximum(np.maximum(np.maximum(n, s), np.maximum(wv, e)), y_clean)
        amp = np.sqrt(np.clip(np.minimum(mn, 1.0 - mx) / np.maximum(mx, 1e-4), 0.0, 1.0))
        edge_gate = np.clip(((mx - mn) - 0.015) / 0.04, 0.0, 1.0)
        weight = -cas_amount * 0.2 * amp * edge_gate
        y_clean = np.clip((y_clean + weight * (n + s + wv + e)) / (1.0 + 4.0 * weight), 0.0, 1.0)

    # Shadow-zeroed, skin-protected, ISO-attenuated adaptive Vibrance + Saturation
    cb_c = (cb_f.astype(np.float32) - 128.0) / 255.0
    cr_c = (cr_f.astype(np.float32) - 128.0) / 255.0
    chroma = np.sqrt(cb_c * cb_c + cr_c * cr_c)

    # Strict 0 boost for Y <= 0.06 so dark shadows stay neutral without chroma noise
    lum_gate = _smoothstep(0.06, 0.20, y_clean) * (1.0 - 0.35 * _smoothstep(0.86, 0.98, y_clean))
    iso_atten = 1.0 - float(np.clip((max(1.0, analogue_gain) - 6.0) / 14.0, 0.0, 0.45))

    raw_boost_delta = (vibrance * np.exp(-chroma * 5.5) + base_sat) * iso_atten
    raw_boost_delta = raw_boost_delta * float(np.clip(sat_scale, 0.0, 2.0))

    # Detect warm skin-tone quadrant (Cr > 0.015, Cb < -0.005, 0.8 <= Cr/(-Cb) <= 2.6)
    neg_cb = np.maximum(-cb_c, 1e-4)
    ratio = cr_c / neg_cb
    skin_quad = _smoothstep(0.015, 0.045, cr_c) * _smoothstep(0.005, 0.025, -cb_c)
    skin_ratio_w = _smoothstep(0.65, 0.95, ratio) * (1.0 - _smoothstep(2.40, 2.90, ratio))
    skin_mask = np.clip(skin_quad * skin_ratio_w, 0.0, 1.0)

    skin_cap = max(0.0, 0.08 * float(np.clip(sat_scale, 0.0, 1.5)))
    delta = raw_boost_delta * (1.0 - skin_mask) + np.minimum(raw_boost_delta, skin_cap) * skin_mask
    boost = np.where(sat_scale < 1.0, 1.0 + (sat_scale - 1.0) * lum_gate, 1.0 + delta * lum_gate)

    mid_w = np.exp(-((y_clean - 0.50) / 0.25) ** 2) * np.clip(1.0 - chroma * 6.0, 0.0, 1.0) * lum_gate
    cr_c = cr_c * boost + 0.005 * mid_w
    cb_c = cb_c * boost - 0.002 * mid_w

    y_out = np.round(y_clean * 255.0).clip(0, 255).astype(np.uint8)
    cr_out = np.round(cr_c * 255.0 + 128.0).clip(0, 255).astype(np.uint8)
    cb_out = np.round(cb_c * 255.0 + 128.0).clip(0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge([y_out, cr_out, cb_out]), cv2.COLOR_YCrCb2RGB)


def gain_sigma(g: float) -> float:
    return float(np.clip(g, 0.85, 1.85))


def apply_display_orientation(img: np.ndarray, rotation: int = 0, mirror_selfie: bool = False) -> np.ndarray:
    out = img
    if rotation == 180:
        out = img[::-1, ::-1]
    elif rotation == 90:
        out = np.rot90(img, k=3)
    elif rotation == 270:
        out = np.rot90(img, k=1)
    if mirror_selfie:
        out = out[:, ::-1]
    return np.ascontiguousarray(out)


def save_jpeg_with_exif(
    rgb_u8: np.ndarray,
    out_path: Path,
    profile: SensorProfile,
    metadata: Optional[Dict[str, Any]] = None,
    quality: int = 95,
    mode_tag: str = "HDR+",
) -> Path:
    """Save uint8 RGB array as high-quality JPEG with standard camera EXIF tags."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(rgb_u8, mode="RGB")
    exif = im.getexif()
    now_str = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
    exif[0x010F] = "OnePlus"  # Make
    exif[0x0110] = "OnePlus Pad 2 Pro (OPD2413)"  # Model
    exif[0x0112] = 1  # Orientation
    exif[0x0131] = f"opd2413-camera ({mode_tag}; {profile.model})"  # Software
    exif[0x0132] = now_str  # DateTime
    exif_ifd = exif.get_ifd(0x8769)  # ExifIFD
    exif_ifd[0x9003] = now_str  # DateTimeOriginal
    exif_ifd[0x9004] = now_str  # DateTimeDigitized
    exif_ifd[0xA434] = profile.lens_label  # LensModel
    exif_ifd[0x829D] = float(profile.f_number)  # FNumber
    exif_ifd[0x920A] = float(profile.focal_length_mm)  # FocalLength
    if metadata:
        exp_us = float(metadata.get("ExposureTime", 0.0) or 0.0)
        if exp_us > 0:
            exif_ifd[0x829A] = exp_us / 1_000_000.0  # ExposureTime in sec
        again = float(metadata.get("AnalogueGain", 0.0) or 0.0)
        if again > 0:
            exif_ifd[0x8827] = int(round(100.0 * again))  # ISOSpeedRatings
    im.save(str(out_path), format="JPEG", quality=quality, subsampling=0, exif=exif)
    return out_path


def process_raw10_burst(
    raw_frames: Iterable[bytes | np.ndarray],
    width: int,
    height: int,
    stride: int,
    sensor_model: str,
    metadata: Optional[Dict[str, Any]] = None,
    mirror_selfie: bool = False,
    bayer_override: Optional[str] = None,
    rotation_override: Optional[int] = None,
    ev_comp: float = 0.0,
    sat_scale: float = 1.0,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Run complete single-frame or multi-frame HDR+ RAW10 pipeline returning uint8 RGB image."""
    profile = SENSOR_PROFILES.get(sensor_model)
    if profile is None:
        raise ValueError(f"Unsupported sensor model: {sensor_model}")
    bayer_order = bayer_override or profile.bayer_order
    rotation = profile.raw_rotation if rotation_override is None else rotation_override

    raw_list: List[np.ndarray] = []
    for frame in raw_frames:
        if isinstance(frame, np.ndarray) and frame.ndim == 2:
            raw_list.append(frame.astype(np.uint16, copy=False))
        else:
            raw_list.append(unpack_raw10_csi2p(frame, width, height, stride))
    if not raw_list:
        raise ValueError("No RAW frames provided")

    raw_stack = np.stack(raw_list, axis=0)
    meta = metadata or {}

    # Derive black level in 10-bit DN (libcamera encodes SensorBlackLevels on 16-bit 0..65535)
    bl = profile.default_black_level_10b
    sbl = meta.get("SensorBlackLevels")
    if isinstance(sbl, (list, tuple)) and len(sbl) >= 1 and float(sbl[0]) > 100.0:
        bl = float(np.mean(sbl)) / 64.0
    # Guard only against gross sensor black-level misconfiguration, never single-frame read noise
    p05 = float(np.percentile(raw_stack[0, ::4, ::4], 5.0))
    if p05 < bl * 0.5:
        bl = max(0.0, p05 * 0.8)
    denom = 1023.0 - bl

    raw_lin_stack = (raw_stack.astype(np.float32) - bl) / denom
    again = float(meta.get("AnalogueGain", 1.0) or 1.0)
    is_burst = raw_stack.shape[0] > 1

    if is_burst:
        merged_bayer, merge_info = align_and_merge_burst(raw_lin_stack, black_floor_norm=bl / denom, analogue_gain=again)
        ref_idx = int(merge_info["ref_idx"])
    else:
        merged_bayer = np.maximum(raw_lin_stack[0], 0.0)
        merge_info = {"frames": 1, "ref_idx": 0, "mad_noise": 0.0, "mean_shift_px": 0.0}
        ref_idx = 0

    sat_mask = raw_stack[ref_idx] >= 1018

    # Sensor-space radial LSC -> 5x5 Malvar-He-Cutler demosaic -> AWB + Highlight Rec -> CCM
    lsc_profile = profile if bayer_order == profile.bayer_order else SensorProfile(
        model=profile.model,
        display_name=profile.display_name,
        lens_label=profile.lens_label,
        f_number=profile.f_number,
        focal_length_mm=profile.focal_length_mm,
        bayer_order=bayer_order,
        raw_rotation=rotation,
        default_black_level_10b=profile.default_black_level_10b,
        chroma_damping=profile.chroma_damping,
        lsc=profile.lsc,
        ccms=profile.ccms,
        awb_warm_bias=profile.awb_warm_bias,
        preview_size=profile.preview_size,
        raw_size=profile.raw_size,
    )
    lsc_bayer = compute_radial_lsc_bayer(height, width, lsc_profile)
    bayer_lsc = merged_bayer * lsc_bayer
    rgb_dem = demosaic_malvar_cv(bayer_lsc, bayer_order=bayer_order)

    cg = meta.get("ColourGains")
    hint_gains = (float(cg[0]), float(cg[1])) if isinstance(cg, (list, tuple)) and len(cg) == 2 else None
    hint_ct = float(meta["ColourTemperature"]) if "ColourTemperature" in meta else None

    gains, ccm, est_ct = estimate_awb_and_ccm(
        np.maximum(rgb_dem, 0.0), profile, hint_gains=hint_gains, hint_ct=hint_ct
    )
    rgb_wb = rgb_dem * gains[None, None, :]
    rgb_wb = reconstruct_clipped_highlights(rgb_wb, np.maximum(raw_lin_stack[ref_idx], 0.0), sat_mask)
    rgb_ccm = np.maximum(rgb_wb @ ccm.T, 0.0).astype(np.float32)

    # Suppress residual chroma noise in very dark pixels near the black floor
    mad_n = float(merge_info.get("mad_noise", 0.0) or 0.0)
    lum_ccm = (0.2126 * rgb_ccm[:, :, 0:1] + 0.7152 * rgb_ccm[:, :, 1:2] + 0.0722 * rgb_ccm[:, :, 2:3]).astype(
        np.float32
    )
    shadow_knee = max(0.0035, (mad_n if mad_n > 0.0 else 0.002 * float(np.sqrt(again))) * 1.8)
    w_sh = np.clip((lum_ccm - 0.20 * shadow_knee) / shadow_knee, 0.15, 1.0).astype(np.float32)
    rgb_ccm = (lum_ccm + w_sh * (rgb_ccm - lum_ccm)).astype(np.float32)

    exp_us = float(meta.get("ExposureTime", 20000.0) or 20000.0)
    low_light_t = _exposure_low_light_t(exp_us, again)
    if is_burst:
        srgb = _mertens_exposure_fusion_cv(
            rgb_ccm,
            levels=5,
            exp_us=exp_us,
            ag=again,
            ev_comp=ev_comp,
        )
    else:
        srgb = _filmic_tone_map_singleframe(
            rgb_ccm,
            exp_us=exp_us,
            ag=again,
            ev_comp=ev_comp,
        )

    rgb_u8 = _ycbcr_bilateral_polish_and_cas(
        srgb,
        is_burst=is_burst,
        analogue_gain=again,
        vibrance=0.26 if is_burst else 0.20,
        base_sat=0.14 if is_burst else 0.11,
        sat_scale=sat_scale,
    )
    rgb_u8 = apply_display_orientation(rgb_u8, rotation=rotation, mirror_selfie=mirror_selfie)

    stats = {
        **merge_info,
        "sensor": sensor_model,
        "bayer_order": bayer_order,
        "black_level_10b": round(bl, 2),
        "awb_gains": [round(float(x), 3) for x in gains],
        "est_ct": round(est_ct, 0),
        "analogue_gain": round(again, 2),
        "exposure_us": int(exp_us) if meta.get("ExposureTime") else 0,
        "ev_comp": round(float(ev_comp), 2),
        "sat_scale": round(float(sat_scale), 2),
        "low_light_t": round(low_light_t, 3),
        "af_state": meta.get("AfState"),
        "lens_position": round(float(meta["LensPosition"]), 3) if "LensPosition" in meta else None,
        "output_size": [int(rgb_u8.shape[1]), int(rgb_u8.shape[0])],
    }
    return rgb_u8, stats
