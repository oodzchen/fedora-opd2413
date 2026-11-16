#!/usr/bin/env python3
"""Command-line burst RAW10 HDR+ camera capture utility for OPD2413."""

from __future__ import annotations

import argparse
from datetime import datetime
import gc
import json
import mmap
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

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


def find_camera(cm: Any, which: str) -> Tuple[Any, str]:
    target = {"front": "sc820cs", "rear": "sc1300cs", "sc820cs": "sc820cs", "sc1300cs": "sc1300cs"}.get(which, "")
    by_model = {}
    for cam in cm.cameras:
        import libcamera as lc
        model = str(cam.properties.get(lc.properties.Model) or "")
        by_model[model] = cam
    if target:
        if target not in by_model:
            raise RuntimeError(f"Requested camera '{which}' ({target}) not found; available: {list(by_model)}")
        return by_model[target], target
    for cand in ("sc1300cs", "sc820cs"):
        if cand in by_model:
            return by_model[cand], cand
    raise RuntimeError(f"No supported OPD2413 cameras found; available: {list(by_model)}")


def capture_raw_burst(
    camera_choice: str,
    num_frames: int,
    warmup_frames: int,
    lens_position: Optional[float] = None,
) -> Tuple[str, List[bytes], int, int, int, Dict[str, Any], float]:
    import libcamera as lc

    cm = lc.CameraManager.singleton()
    cam, model = find_camera(cm, camera_choice)
    profile = SENSOR_PROFILES[model]
    ctrl_names = {c.name if hasattr(c, "name") else str(c) for c in cam.controls}
    has_af = "AfMode" in ctrl_names and "LensPosition" in ctrl_names

    cam.acquire()
    reqs = []
    alloc = None
    captured_raw: List[bytes] = []
    last_meta: Dict[str, Any] = {}
    t_capture_start = 0.0
    t_capture_end = 0.0

    try:
        cfg = cam.generate_configuration([lc.StreamRole.Viewfinder, lc.StreamRole.Raw])
        cfg.at(0).pixel_format = lc.formats.XRGB8888
        cfg.at(0).size = lc.Size(*profile.preview_size)
        cfg.at(1).size = lc.Size(*profile.raw_size)
        cfg.validate()
        cam.configure(cfg)

        raw_sc = cfg.at(1)
        rw, rh, rstride, rsize = raw_sc.size.width, raw_sc.size.height, raw_sc.stride, raw_sc.frame_size

        alloc = lc.FrameBufferAllocator(cam)
        s_vf = cfg.at(0).stream
        s_raw = cfg.at(1).stream
        if alloc.allocate(s_vf) <= 0 or alloc.allocate(s_raw) <= 0:
            raise RuntimeError("Failed to allocate libcamera streams")

        buf_vf = alloc.buffers(s_vf)
        buf_raw = alloc.buffers(s_raw)
        n_req = min(len(buf_vf), len(buf_raw))
        for idx in range(n_req):
            req = cam.create_request(idx)
            req.add_buffer(s_vf, buf_vf[idx])
            req.add_buffer(s_raw, buf_raw[idx])
            reqs.append(req)

        cam.start()
        for idx, req in enumerate(reqs):
            if has_af and idx == 0:
                if lens_position is not None:
                    req.set_control(lc.controls.AfMode, lc.controls.AfModeEnum.Manual)
                    req.set_control(lc.controls.LensPosition, float(lens_position))
                else:
                    req.set_control(lc.controls.AfMode, lc.controls.AfModeEnum.Continuous)
                    req.set_control(lc.controls.AfTrigger, lc.controls.AfTriggerEnum.Start)
            cam.queue_request(req)

        min_warmup = max(8, warmup_frames) if (has_af and lens_position is not None) else max(1, warmup_frames)
        max_warmup = max(min_warmup, 75) if (has_af and lens_position is None) else min_warmup
        warmup_done = 0
        focused_settle = 0
        capturing = False
        target_burst = max(1, num_frames)

        while len(captured_raw) < target_burst:
            ready = cm.get_ready_requests()
            if not ready:
                time.sleep(0.002)
                continue
            for req in ready:
                if req.status != lc.Request.Status.Complete:
                    if not capturing or len(captured_raw) < target_burst:
                        req.reuse()
                        cam.queue_request(req)
                    continue

                if not capturing:
                    warmup_done += 1
                    meta = _extract_meta(req.metadata)
                    af_state = meta.get("AfState")
                    if has_af and lens_position is None:
                        if af_state == 2:
                            focused_settle += 1
                        else:
                            focused_settle = 0
                        af_done = (af_state == 2 and focused_settle >= 2) or (
                            af_state == 3 and warmup_done >= max(min_warmup, 45)
                        )
                        if (warmup_done >= min_warmup and af_done) or warmup_done >= max_warmup:
                            capturing = True
                    elif warmup_done >= min_warmup:
                        capturing = True
                else:
                    if not captured_raw:
                        t_capture_start = time.monotonic()
                    fb = req.buffers[s_raw]
                    plane = fb.planes[0]
                    with mmap.mmap(plane.fd, rsize, mmap.MAP_SHARED, mmap.PROT_READ) as mm:
                        captured_raw.append(bytes(mm[:rsize]))
                    last_meta = _extract_meta(req.metadata)
                    t_capture_end = time.monotonic()

                if len(captured_raw) < target_burst:
                    req.reuse()
                    cam.queue_request(req)
                else:
                    break
    finally:
        try:
            cam.stop()
        except Exception:
            pass
        _ = cm.get_ready_requests()
        reqs.clear()
        del alloc
        gc.collect()
        cam.release()

    burst_ms = (t_capture_end - t_capture_start) * 1000.0 if len(captured_raw) > 1 else 0.0
    return model, captured_raw, rw, rh, rstride, last_meta, burst_ms


def default_output_path(model: str, mode: str) -> Path:
    pic_dir = Path.home() / "Pictures" / "OPD_Camera"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    side = "FRONT" if model == "sc820cs" else "REAR"
    suffix = "HDR" if mode == "hdr+" else "RAW1"
    return pic_dir / f"IMG_{ts}_{side}_{suffix}.jpg"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="OPD2413 RAW10 HDR+ still capture CLI")
    ap.add_argument("--camera", choices=["auto", "front", "rear", "sc820cs", "sc1300cs"], default="front",
                    help="Select camera sensor (default: front)")
    ap.add_argument("--mode", choices=["hdr+", "single"], default="hdr+",
                    help="Multi-frame HDR+ burst or single RAW10 frame (default: hdr+)")
    ap.add_argument("--frames", type=int, default=8, help="Burst frames in hdr+ mode (default: 8)")
    ap.add_argument("--warmup", type=int, default=24, help="AE/AWB warmup frames before capture (default: 24)")
    ap.add_argument("--lens-position", type=float, default=None,
                    help="Manual focus diopter (rear camera, e.g. 0.0=far, 10.0=near)")
    ap.add_argument("--ev", type=float, default=0.0,
                    help="Exposure compensation in EV stops (default: 0.0)")
    ap.add_argument("--saturation", type=float, default=1.0,
                    help="Vibrance/saturation multiplier (default: 1.0)")
    ap.add_argument("--mirror", action="store_true", help="Horizontally mirror front camera photo")
    ap.add_argument("--quality", type=int, default=95, help="JPEG quality (default: 95)")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Output JPEG path")
    ap.add_argument("--json-stats", action="store_true", help="Print JSON statistics to stdout")
    args = ap.parse_args(argv)

    n_frames = 1 if args.mode == "single" else max(2, min(16, args.frames))
    t0 = time.monotonic()
    model, raw_frames, rw, rh, rstride, meta, burst_ms = capture_raw_burst(
        args.camera, n_frames, args.warmup, lens_position=args.lens_position
    )
    t_proc0 = time.monotonic()
    profile = SENSOR_PROFILES[model]
    rgb_u8, stats = process_raw10_burst(
        raw_frames,
        rw,
        rh,
        rstride,
        model,
        metadata=meta,
        mirror_selfie=(args.mirror and model == "sc820cs"),
        ev_comp=args.ev,
        sat_scale=args.saturation,
    )
    proc_ms = (time.monotonic() - t_proc0) * 1000.0
    out_path = args.output or default_output_path(model, args.mode)
    save_jpeg_with_exif(
        rgb_u8,
        out_path,
        profile,
        metadata=meta,
        quality=args.quality,
        mode_tag="HDR+" if n_frames > 1 else "SingleRAW",
    )
    total_ms = (time.monotonic() - t0) * 1000.0
    stats.update({
        "output_path": str(out_path),
        "burst_capture_ms": round(burst_ms, 1),
        "isp_process_ms": round(proc_ms, 1),
        "total_ms": round(total_ms, 1),
    })
    if args.json_stats:
        print(json.dumps(stats, indent=2))
    else:
        af_info = ""
        if stats.get("lens_position") is not None:
            af_info = f", af_state={stats.get('af_state')}, lens={stats.get('lens_position')}D"
        print(f"Saved {out_path} ({stats['output_size'][0]}x{stats['output_size'][1]}, "
              f"frames={stats['frames']}{af_info}, burst={stats['burst_capture_ms']}ms, isp={stats['isp_process_ms']}ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
