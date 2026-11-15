#!/usr/bin/env python3
"""Offline calibration & tuning fitter for opd2413 Simple Software ISP.

Fits:
1. BlackLevel (`blackLevel` in 16-bit scale 0..65535; Simple IPA shifts >> 8)
2. Radial per-channel LSC (`cx`, `cy`, `k0`, `k1`) matching `lsc_eval()` in
   libcamera's `bayer_unpacked.frag` / `bayer_1x_packed.frag`:
     centerPx = (cx * W, cy * H)
     maxDist  = max(centerPx, (W, H) - centerPx)
     m2       = max(dot(maxDist, maxDist), 1.0)
     r2       = dot(px - centerPx, px - centerPx) / m2
     gain     = max(1.0, 1.0 + k0 * r2 + k1 * r2 * r2)
3. Row-sum-normalized 3x3 Color Correction Matrices (`ccm`) per CT in linear sRGB.

Supports `.npz` bundles captured on device (width, height, stride, format, raw),
unpacked uint16/uint8 `.npy`, or linear/sRGB patch RGB JSON/CSV files.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

# Standard ColorChecker Classic 24-patch sRGB (D65, 0..255), ordered top-left -> bottom-right.
COLORCHECKER_24_SRGB = np.array(
    [
        [115, 82, 68],    # 01 dark skin
        [194, 150, 130],  # 02 light skin
        [98, 122, 157],   # 03 blue sky
        [87, 108, 67],    # 04 foliage
        [133, 128, 177],  # 05 blue flower
        [103, 189, 170],  # 06 bluish green
        [214, 126, 44],   # 07 orange
        [80, 91, 166],    # 08 purplish blue
        [193, 90, 99],    # 09 moderate red
        [94, 60, 108],    # 10 purple
        [157, 188, 64],   # 11 yellow green
        [224, 163, 46],   # 12 orange yellow
        [56, 61, 150],    # 13 blue
        [70, 148, 73],    # 14 green
        [175, 54, 60],    # 15 red
        [231, 199, 31],   # 16 yellow
        [187, 86, 149],   # 17 magenta
        [8, 133, 161],    # 18 cyan
        [243, 243, 242],  # 19 white
        [200, 200, 200],  # 20 neutral 8
        [160, 160, 160],  # 21 neutral 6.5
        [122, 122, 121],  # 22 neutral 5
        [85, 85, 85],     # 23 neutral 3.5
        [52, 52, 52],     # 24 black
    ],
    dtype=np.float64,
)

BAYER_LAYOUTS = {
    "RGGB": ((0, 0), (0, 1), (1, 0), (1, 1)),
    "GRBG": ((0, 1), (0, 0), (1, 1), (1, 0)),
    "GBRG": ((1, 0), (0, 0), (1, 1), (0, 1)),
    "BGGR": ((1, 1), (0, 1), (1, 0), (0, 0)),
}


def srgb_to_linear(val: np.ndarray) -> np.ndarray:
    """Convert normalized sRGB [0..1] to linear sRGB [0..1]."""
    x = np.clip(val, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(val: np.ndarray) -> np.ndarray:
    """Convert linear sRGB [0..1] to normalized sRGB [0..1]."""
    x = np.clip(val, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * (x ** (1.0 / 2.4)) - 0.055)


def unpack_raw10_csi2p(buf: bytes, width: int, height: int, stride: int) -> np.ndarray:
    """Unpack MIPI CSI-2 10-bit packed Bayer image to float64 normalized [0..1]."""
    expected_row_bytes = (width * 10 + 7) // 8
    arr = np.frombuffer(buf, dtype=np.uint8)
    if stride <= 0:
        stride = expected_row_bytes
    rows = arr[: height * stride].reshape((height, stride))[:, :expected_row_bytes]
    groups = rows.reshape((height, width // 4, 5)).astype(np.uint16)
    lsbs = groups[:, :, 4]
    out = np.empty((height, width), dtype=np.uint16)
    out[:, 0::4] = (groups[:, :, 0] << 2) | ((lsbs >> 0) & 0x03)
    out[:, 1::4] = (groups[:, :, 1] << 2) | ((lsbs >> 2) & 0x03)
    out[:, 2::4] = (groups[:, :, 2] << 2) | ((lsbs >> 4) & 0x03)
    out[:, 3::4] = (groups[:, :, 3] << 2) | ((lsbs >> 6) & 0x03)
    return out.astype(np.float64) / 1023.0


def parse_bayer_order(fmt: str) -> str:
    """Extract 4-char Bayer pattern (RGGB/GRBG/GBRG/BGGR) from libcamera format name."""
    upper = fmt.upper()
    for pat in BAYER_LAYOUTS:
        if pat in upper:
            return pat
    raise ValueError(f"Unsupported Bayer format string: {fmt!r}")


def load_raw_frame(path: Path) -> tuple[np.ndarray, str]:
    """Load a captured frame (.npz or .npy) as normalized [0..1] 2D float64 Bayer array."""
    if path.suffix == ".npz":
        data = np.load(path, allow_pickle=False)
        fmt = str(data["format"])
        width = int(data["width"])
        height = int(data["height"])
        stride = int(data["stride"]) if "stride" in data else 0
        raw = data["raw"]
        bayer = parse_bayer_order(fmt)
        if "CSI2P" in fmt.upper() or (raw.dtype == np.uint8 and "10" in fmt):
            img = unpack_raw10_csi2p(raw.tobytes(), width, height, stride)
        elif raw.dtype == np.uint16:
            bit_depth = int(data["bit_depth"]) if "bit_depth" in data else (10 if raw.max() < 1024 else 16)
            img = raw.astype(np.float64) / float((1 << bit_depth) - 1)
        elif raw.dtype == np.uint8:
            img = raw.astype(np.float64) / 255.0
        else:
            img = np.clip(raw.astype(np.float64), 0.0, 1.0)
        return img, bayer

    arr = np.load(path, allow_pickle=False)
    if arr.dtype == np.uint16:
        scale = 1023.0 if arr.max() < 1024 else 65535.0
        return arr.astype(np.float64) / scale, "RGGB"
    return np.clip(arr.astype(np.float64), 0.0, 1.0), "RGGB"


def split_bayer_planes(img: np.ndarray, layout: str) -> dict[str, np.ndarray]:
    """Split a 2D Bayer frame into half-res R, Gr, Gb, B planes."""
    r_yx, gr_yx, gb_yx, b_yx = BAYER_LAYOUTS[layout]
    return {
        "R": img[r_yx[0] :: 2, r_yx[1] :: 2],
        "Gr": img[gr_yx[0] :: 2, gr_yx[1] :: 2],
        "Gb": img[gb_yx[0] :: 2, gb_yx[1] :: 2],
        "B": img[b_yx[0] :: 2, b_yx[1] :: 2],
    }


def fit_dark(args: argparse.Namespace) -> dict[str, Any]:
    """Estimate 16-bit BlackLevel from one or more dark captures."""
    medians = []
    per_ch_accum: dict[str, list[float]] = {"R": [], "Gr": [], "Gb": [], "B": []}
    for p in args.inputs:
        img, layout = load_raw_frame(Path(p))
        planes = split_bayer_planes(img, layout)
        for ch, plane in planes.items():
            per_ch_accum[ch].append(float(np.median(plane)))
        medians.append(float(np.median(img)))

    overall_norm = float(np.median(medians))
    black_16bit = int(round(overall_norm * 65535.0))
    # int16_t max is 32767 in libcamera BlackLevel::init tuningData["blackLevel"].get<int16_t>().
    black_16bit = max(0, min(32767, black_16bit))
    summary = {
        "blackLevel": black_16bit,
        "normalizedMedian": round(overall_norm, 6),
        "raw10Equivalent": round(overall_norm * 1023.0, 2),
        "softIsp8Bit": black_16bit >> 8,
        "channelMedians16Bit": {
            ch: int(round(float(np.median(vals)) * 65535.0))
            for ch, vals in per_ch_accum.items()
        },
    }
    return summary


def lsc_eval_r2(ys: np.ndarray, xs: np.ndarray, height: int, width: int, cx: float, cy: float) -> np.ndarray:
    """Exact shader equivalent of normalized r^2 in full-frame pixel units."""
    cx_px = cx * width
    cy_px = cy * height
    max_dx = max(cx_px, width - cx_px)
    max_dy = max(cy_px, height - cy_px)
    m2 = max(max_dx * max_dx + max_dy * max_dy, 1.0)
    dx = xs - cx_px
    dy = ys - cy_px
    return (dx * dx + dy * dy) / m2


def fit_lsc_channel(
    plane: np.ndarray,
    full_h: int,
    full_w: int,
    yx_offset: tuple[int, int],
    grid_x: int,
    grid_y: int,
) -> dict[str, Any]:
    """Fit radial polynomial `1 + k0*r2 + k1*r2^2` for one Bayer channel."""
    ph, pw = plane.shape
    bx = np.array_split(np.arange(pw), grid_x)
    by = np.array_split(np.arange(ph), grid_y)

    sample_x: list[float] = []
    sample_y: list[float] = []
    sample_val: list[float] = []

    for ys_idx in by:
        y_center = float(np.mean(ys_idx) * 2.0 + yx_offset[0] + 0.5)
        row_slice = plane[ys_idx[0] : ys_idx[-1] + 1, :]
        for xs_idx in bx:
            block = row_slice[:, xs_idx[0] : xs_idx[-1] + 1]
            val = float(np.median(block))
            if val <= 1e-4:
                continue
            x_center = float(np.mean(xs_idx) * 2.0 + yx_offset[1] + 0.5)
            sample_x.append(x_center)
            sample_y.append(y_center)
            sample_val.append(val)

    xs = np.asarray(sample_x, dtype=np.float64)
    ys = np.asarray(sample_y, dtype=np.float64)
    vals = np.asarray(sample_val, dtype=np.float64)
    if vals.size < 16:
        raise ValueError("Too few valid flat-field grid blocks for LSC fit")

    # Normalize against high percentile in the central 35% to resist hot pixels.
    in_center = (
        (xs > full_w * 0.325)
        & (xs < full_w * 0.675)
        & (ys > full_h * 0.325)
        & (ys < full_h * 0.675)
    )
    center_vals = vals[in_center] if np.any(in_center) else vals
    peak = float(np.percentile(center_vals, 95))
    target_gain = np.clip(peak / vals, 1.0, 6.0)
    delta_gain = target_gain - 1.0

    best_err = math.inf
    best = (0.5, 0.5, 0.0, 0.0, 0.0)

    # Coarse-to-fine grid search over optical center (cx, cy); linear least squares for (k0, k1).
    for step, span in ((0.02, 0.12), (0.005, 0.025)):
        c0_x = 0.5 if step == 0.02 else best[0]
        c0_y = 0.5 if step == 0.02 else best[1]
        cxs = np.arange(c0_x - span, c0_x + span + 1e-9, step)
        cys = np.arange(c0_y - span, c0_y + span + 1e-9, step)
        for cy in cys:
            for cx in cxs:
                r2 = lsc_eval_r2(ys, xs, full_h, full_w, float(cx), float(cy))
                design = np.column_stack((r2, r2 * r2))
                coeffs, _, _, _ = np.linalg.lstsq(design, delta_gain, rcond=None)
                k0, k1 = float(coeffs[0]), float(coeffs[1])
                pred_gain = np.maximum(1.0, 1.0 + k0 * r2 + k1 * (r2 * r2))
                corrected = vals * pred_gain
                rel_flat = corrected / peak - 1.0
                err = float(np.sqrt(np.mean(rel_flat * rel_flat)))
                if err < best_err:
                    best_err = err
                    best = (float(cx), float(cy), k0, k1, err)

    cx, cy, k0, k1, rms = best
    # Compute flatness before/after correction.
    raw_cv = float(np.std(vals) / np.mean(vals))
    r2_best = lsc_eval_r2(ys, xs, full_h, full_w, cx, cy)
    corr_vals = vals * np.maximum(1.0, 1.0 + k0 * r2_best + k1 * (r2_best * r2_best))
    corr_cv = float(np.std(corr_vals) / np.mean(corr_vals))
    return {
        "cx": round(cx, 4),
        "cy": round(cy, 4),
        "k0": round(k0, 4),
        "k1": round(k1, 4),
        "rmsFlatnessBefore": round(raw_cv, 4),
        "rmsFlatnessAfter": round(corr_cv, 4),
        "cornerGain": round(max(1.0, 1.0 + k0 + k1), 3),
    }


def fit_lsc(args: argparse.Namespace) -> dict[str, Any]:
    """Fit per-channel radial LSC from averaged flat-field raw frames."""
    black_norm = float(args.black_level) / 65535.0
    accum: np.ndarray | None = None
    layout = "RGGB"
    for p in args.inputs:
        img, layout = load_raw_frame(Path(p))
        accum = img if accum is None else (accum + img)
    assert accum is not None
    mean_img = accum / float(len(args.inputs))
    lin_img = np.clip((mean_img - black_norm) / max(1.0 - black_norm, 1e-6), 0.0, 1.0)
    full_h, full_w = lin_img.shape

    max_val = float(np.percentile(lin_img, 99.5))
    if max_val > 0.92:
        print(f"WARNING: flat-field near saturation (p99.5={max_val:.3f})", file=sys.stderr)
    elif max_val < 0.15:
        print(f"WARNING: flat-field very dim (p99.5={max_val:.3f})", file=sys.stderr)

    planes = split_bayer_planes(lin_img, layout)
    offsets = BAYER_LAYOUTS[layout]
    r_fit = fit_lsc_channel(planes["R"], full_h, full_w, offsets[0], args.grid_x, args.grid_y)
    gr_fit = fit_lsc_channel(planes["Gr"], full_h, full_w, offsets[1], args.grid_x, args.grid_y)
    gb_fit = fit_lsc_channel(planes["Gb"], full_h, full_w, offsets[2], args.grid_x, args.grid_y)
    b_fit = fit_lsc_channel(planes["B"], full_h, full_w, offsets[3], args.grid_x, args.grid_y)

    g_fit = {
        "cx": round(0.5 * (gr_fit["cx"] + gb_fit["cx"]), 4),
        "cy": round(0.5 * (gr_fit["cy"] + gb_fit["cy"]), 4),
        "k0": round(0.5 * (gr_fit["k0"] + gb_fit["k0"]), 4),
        "k1": round(0.5 * (gr_fit["k1"] + gb_fit["k1"]), 4),
        "rmsFlatnessBefore": round(0.5 * (gr_fit["rmsFlatnessBefore"] + gb_fit["rmsFlatnessBefore"]), 4),
        "rmsFlatnessAfter": round(0.5 * (gr_fit["rmsFlatnessAfter"] + gb_fit["rmsFlatnessAfter"]), 4),
        "cornerGain": round(0.5 * (gr_fit["cornerGain"] + gb_fit["cornerGain"]), 3),
    }

    return {"r": r_fit, "g": g_fit, "b": b_fit}


def solve_row_normalized_ccm(
    src_rgb: np.ndarray,
    dst_rgb: np.ndarray,
    reg: float = 1e-3,
    scale_exposure: bool = True,
) -> tuple[np.ndarray, float]:
    """Solve row-sum=1 3x3 CCM minimizing ||src @ M.T - dst||^2 + reg*||M - I||^2.

    Each row i satisfies m_i0 + m_i1 + m_i2 = 1 -> m_i2 = 1 - m_i0 - m_i1:
      d_c - b = [r - b, g - b] @ [m_i0, m_i1]^T
    """
    src = np.asarray(src_rgb, dtype=np.float64)
    dst = np.asarray(dst_rgb, dtype=np.float64)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 3:
        raise ValueError(f"Expected Nx3 matching RGB arrays, got {src.shape} vs {dst.shape}")

    ident = np.eye(3, dtype=np.float64)
    mat = ident.copy()
    gain = float(np.sum(dst) / max(np.sum(src), 1e-12)) if scale_exposure else 1.0
    n_iter = 10 if scale_exposure else 1

    for _ in range(n_iter):
        src_scaled = src * gain
        r, g, b = src_scaled[:, 0], src_scaled[:, 1], src_scaled[:, 2]
        A = np.column_stack((r - b, g - b))  # N x 2
        for ch in range(3):
            y = dst[:, ch] - b
            # Ridge toward identity row: ||A @ w - y||^2 + reg * ||w - I_ch[:2]||^2
            w_prior = ident[ch, :2]
            lhs = A.T @ A + reg * len(r) * np.eye(2)
            rhs = A.T @ y + reg * len(r) * w_prior
            w = np.linalg.solve(lhs, rhs)
            mat[ch, 0] = w[0]
            mat[ch, 1] = w[1]
            mat[ch, 2] = 1.0 - w[0] - w[1]
        if scale_exposure:
            mapped = src @ mat.T
            gain = float(np.sum(dst * mapped) / max(np.sum(mapped * mapped), 1e-12))

    pred = np.clip((src * gain) @ mat.T, 0.0, 1.0)
    # Report sRGB-space RMSE (approximate perceptual visual error across patches).
    srgb_pred = linear_to_srgb(pred) * 255.0
    srgb_dst = linear_to_srgb(dst) * 255.0
    rmse = float(np.sqrt(np.mean((srgb_pred - srgb_dst) ** 2)))
    return mat, rmse


def fit_ccm(args: argparse.Namespace) -> dict[str, Any]:
    """Fit CCM for a single CT entry from JSON measured patches.

    Expected JSON schema:
      {
        "ct": 5500,
        "input_is_srgb": false,
        "measured": [[r, g, b], ...],  # 24 rows (0..1 linear or 0..255 sRGB) or Nx3
        "target_srgb": [[r, g, b], ...] # optional; defaults to COLORCHECKER_24_SRGB
      }
    """
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    ct = int(args.ct if args.ct is not None else payload.get("ct", 6500))
    measured = np.asarray(payload["measured"], dtype=np.float64)
    is_srgb = bool(payload.get("input_is_srgb", False))
    if is_srgb:
        if measured.max() > 1.5:
            measured = measured / 255.0
        measured = srgb_to_linear(measured)

    if "target_srgb" in payload:
        tgt = np.asarray(payload["target_srgb"], dtype=np.float64)
        if tgt.max() > 1.5:
            tgt = tgt / 255.0
        target_lin = srgb_to_linear(tgt)
    else:
        if len(measured) != len(COLORCHECKER_24_SRGB):
            raise ValueError("Provide 24 patches matching ColorChecker Classic or supply target_srgb")
        target_lin = srgb_to_linear(COLORCHECKER_24_SRGB / 255.0)

    # White-balance normalize measured patches on the neutral gray ramp (patches 19..23 if 24-patch)
    if args.awb_from_grays and len(measured) == 24:
        grays = measured[19:23]  # neutral 8, 6.5, 5, 3.5 (avoid clipped white / noisy black)
        g_mean = grays.mean(axis=0)
        awb_gains = g_mean[1] / np.maximum(g_mean, 1e-6)
        measured = measured * awb_gains

    mat, rmse = solve_row_normalized_ccm(measured, target_lin, reg=args.reg)
    cond = float(np.linalg.cond(mat))
    return {
        "ct": ct,
        "ccm": [round(float(x), 4) for x in mat.reshape(-1)],
        "srgbRmse255": round(rmse, 2),
        "conditionNumber": round(cond, 3),
    }


def merge_tuning_yaml(
    yaml_path: Path,
    black_level: int | None,
    lsc: dict[str, Any] | None,
    ccms: list[dict[str, Any]],
) -> None:
    """Update an existing libcamera Simple IPA tuning YAML in place cleanly."""
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    algos: list[dict[str, Any]] = doc["algorithms"]

    def upsert(name: str, body: dict[str, Any]) -> None:
        for entry in algos:
            if name in entry:
                entry[name] = body
                return
        algos.append({name: body})

    if black_level is not None:
        upsert("BlackLevel", {"blackLevel": int(black_level)})
    if lsc is not None:
        clean_lsc = {
            ch: {k: float(lsc[ch][k]) for k in ("cx", "cy", "k0", "k1")}
            for ch in ("r", "g", "b")
        }
        upsert("Lsc", clean_lsc)
    if ccms:
        ordered = sorted(ccms, key=lambda c: int(c["ct"]))
        upsert(
            "Ccm",
            {"ccms": [{"ct": int(c["ct"]), "ccm": [float(v) for v in c["ccm"]]} for c in ordered]},
        )

    out_text = "%YAML 1.1\n---\n" + yaml.safe_dump(doc, sort_keys=False) + "...\n"
    yaml_path.write_text(out_text, encoding="utf-8")


def cmd_self_test(_: argparse.Namespace) -> int:
    """Verify dark, LSC, and CCM solvers on synthetic ground-truth data."""
    # 1. Synthetic LSC: exact shader parameters
    w, h = 640, 480
    true_p = {"r": (0.48, 0.52, 0.65, 0.35), "g": (0.50, 0.50, 0.55, 0.25), "b": (0.52, 0.49, 0.72, 0.40)}
    ys, xs = np.mgrid[0:h, 0:w]
    raw = np.zeros((h, w), dtype=np.float64)
    offsets = BAYER_LAYOUTS["RGGB"]
    black = 4096.0 / 65535.0
    for (name, (oy, ox)) in zip(("r", "g", "g", "b"), offsets):
        cx, cy, k0, k1 = true_p[name]
        py = ys[oy::2, ox::2] + 0.5
        px = xs[oy::2, ox::2] + 0.5
        r2 = lsc_eval_r2(py, px, h, w, cx, cy)
        gain = 1.0 + k0 * r2 + k1 * (r2 * r2)
        signal = 0.65 / gain
        raw[oy::2, ox::2] = black + (1.0 - black) * signal

    lin = np.clip((raw - black) / (1.0 - black), 0.0, 1.0)
    planes = split_bayer_planes(lin, "RGGB")
    r_fit = fit_lsc_channel(planes["R"], h, w, offsets[0], 24, 18)
    assert abs(r_fit["cx"] - 0.48) < 0.02 and abs(r_fit["k0"] - 0.65) < 0.03, f"LSC R mismatch: {r_fit}"
    assert abs(r_fit["k1"] - 0.35) < 0.05 and r_fit["rmsFlatnessAfter"] < 0.002, f"LSC R residual: {r_fit}"

    # 2. Synthetic CCM: recover known matrix with row sum 1
    m_true = np.array([[1.42, -0.31, -0.11], [-0.22, 1.38, -0.16], [0.04, -0.44, 1.40]])
    tgt_lin = srgb_to_linear(COLORCHECKER_24_SRGB / 255.0)
    src_lin = tgt_lin @ np.linalg.inv(m_true).T * 0.85
    m_fit, rmse = solve_row_normalized_ccm(src_lin, tgt_lin, reg=1e-6)
    assert np.max(np.abs(m_fit - m_true)) < 0.01 and rmse < 0.5, f"CCM mismatch: {m_fit} rmse={rmse}"
    assert np.allclose(m_fit.sum(axis=1), 1.0, atol=1e-6)

    print("Self-test PASSED:", json.dumps({"r_fit": r_fit, "ccm_rmse": round(rmse, 4)}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fit OPD2413 Simple ISP tuning parameters")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dark = sub.add_parser("dark", help="Estimate 16-bit BlackLevel from dark frames (.npz/.npy)")
    p_dark.add_argument("inputs", nargs="+", help="Dark frame .npz/.npy paths")

    p_lsc = sub.add_parser("lsc", help="Fit per-channel radial LSC from flat-field frames")
    p_lsc.add_argument("--black-level", type=int, default=4096, help="16-bit blackLevel (default 4096)")
    p_lsc.add_argument("--grid-x", type=int, default=32)
    p_lsc.add_argument("--grid-y", type=int, default=24)
    p_lsc.add_argument("inputs", nargs="+", help="Flat-field frame .npz/.npy paths")

    p_ccm = sub.add_parser("ccm", help="Fit row-normalized 3x3 CCM from ColorChecker patch JSON")
    p_ccm.add_argument("--ct", type=int, default=None, help="Color temperature K (overrides JSON ct)")
    p_ccm.add_argument("--reg", type=float, default=1e-3, help="Identity ridge regularization")
    p_ccm.add_argument("--no-awb-grays", dest="awb_from_grays", action="store_false")
    p_ccm.add_argument("input", help="JSON with measured patch RGB values")

    p_apply = sub.add_parser("apply", help="Merge calibration JSON outputs into IPA tuning YAML")
    p_apply.add_argument("--yaml", required=True, help="Target tuning YAML path")
    p_apply.add_argument("--dark-json", default=None)
    p_apply.add_argument("--lsc-json", default=None)
    p_apply.add_argument("--ccm-json", action="append", default=[])

    sub.add_parser("self-test", help="Run synthetic solver verification")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "self-test":
        return cmd_self_test(args)
    if args.cmd == "dark":
        print(json.dumps(fit_dark(args), indent=2))
        return 0
    if args.cmd == "lsc":
        print(json.dumps(fit_lsc(args), indent=2))
        return 0
    if args.cmd == "ccm":
        print(json.dumps(fit_ccm(args), indent=2))
        return 0
    if args.cmd == "apply":
        bl = json.loads(Path(args.dark_json).read_text())["blackLevel"] if args.dark_json else None
        lsc = json.loads(Path(args.lsc_json).read_text()) if args.lsc_json else None
        ccms = [json.loads(Path(p).read_text()) for p in args.ccm_json]
        merge_tuning_yaml(Path(args.yaml), bl, lsc, ccms)
        print(f"Updated {args.yaml}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
