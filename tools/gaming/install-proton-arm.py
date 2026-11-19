#!/usr/bin/env python3
"""Download and install ARM64EC Proton builds (Proton-CachyOS arm64 or GE-Proton aarch64)
into ~/.local/share/Steam/compatibilitytools.d/ and apply mandatory ARM64 fixes:
  1. Strip "require_tool_appid" from toolmanifest.vdf
  2. Create files/bin -> bin-arm64 symlink if missing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
import urllib.request
from pathlib import Path

SOURCES = {
    "proton-cachyos": {
        "api": "https://api.github.com/repos/CachyOS/proton-cachyos/releases?per_page=15",
        "patterns": ("arm64", "aarch64"),
    },
    "proton-ge": {
        "api": "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases?per_page=15",
        "patterns": ("aarch64", "arm64"),
    },
}

REQUIRE_TOOL_APPID_RE = re.compile(
    r'^[ \t]*"require_tool_appid"[ \t]+"[^"]*"[ \t]*\r?\n?',
    re.MULTILINE | re.IGNORECASE,
)


def fetch_json(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "opd2413-proton-arm/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def find_arm_release(source: str, tag_filter: str | None) -> tuple[str, dict, dict | None]:
    cfg = SOURCES[source]
    releases = fetch_json(cfg["api"])
    for rel in releases:
        tag = rel.get("tag_name", "")
        if tag_filter and tag_filter.lower() not in tag.lower():
            continue
        assets = rel.get("assets", [])
        chosen = None
        for a in assets:
            name = a["name"].lower()
            if not any(p in name for p in cfg["patterns"]):
                continue
            if name.endswith((".tar.xz", ".tar.gz", ".tar.zst")):
                chosen = a
                break
        if chosen:
            # Look for matching checksum asset
            csum = None
            base = chosen["name"]
            for a in assets:
                if a["name"] in (f"{base}.sha512sum", f"{base}.sha256sum", f"{tag}.sha512sum", f"{tag}.sha256sum"):
                    csum = a
                    break
            return tag, chosen, csum
    raise RuntimeError(f"No ARM64 release found for {source} (tag={tag_filter})")


def hash_file(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(archive: Path, csum_asset: dict | None) -> None:
    if not csum_asset:
        print("  (no published checksum asset for this release)")
        return
    req = urllib.request.Request(csum_asset["browser_download_url"],
                                 headers={"User-Agent": "opd2413-proton-arm/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", errors="replace")
    algo = "sha512" if "512" in csum_asset["name"] else "sha256"
    expected = None
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and Path(parts[1].lstrip("*")).name == archive.name:
            expected = parts[0].lower()
            break
    if not expected:
        print(f"  (checksum file {csum_asset['name']} had no entry for {archive.name})")
        return
    got = hash_file(archive, algo)
    if got != expected:
        raise RuntimeError(f"{algo} mismatch for {archive.name}: got {got}, expected {expected}")
    print(f"  verified {algo}: {got[:16]}...")


def apply_arm_fixes(proton_dir: Path) -> None:
    tm = proton_dir / "toolmanifest.vdf"
    if tm.is_file():
        orig = tm.read_text(encoding="utf-8", errors="replace")
        patched = REQUIRE_TOOL_APPID_RE.sub("", orig)
        if patched != orig:
            bak = tm.with_suffix(".vdf.bak")
            if not bak.exists():
                bak.write_text(orig, encoding="utf-8")
            tm.write_text(patched, encoding="utf-8")
            print(f"  patched {tm.name}: removed require_tool_appid")

    files_dir = proton_dir / "files"
    arm_bin = files_dir / "bin-arm64"
    bin_link = files_dir / "bin"
    if arm_bin.is_dir() and not bin_link.exists() and not bin_link.is_symlink():
        bin_link.symlink_to("bin-arm64")
        print("  created symlink: files/bin -> bin-arm64")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install ARM64EC Proton for Steam on OPD2413")
    ap.add_argument("--source", choices=tuple(SOURCES.keys()), default="proton-cachyos")
    ap.add_argument("--tag", default=None, help="Optional release tag substring")
    ap.add_argument("--dest", default=str(Path.home() / ".local/share/Steam/compatibilitytools.d"))
    ap.add_argument("--cache", default=str(Path.home() / ".cache/opd2413-proton-arm"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tag, asset, csum = find_arm_release(args.source, args.tag)
    size_mb = asset["size"] / (1024 * 1024)
    print(f"==> Selected {args.source} {tag}: {asset['name']} ({size_mb:.1f} MiB)")
    if args.dry_run:
        print(f"    URL: {asset['browser_download_url']}")
        return 0

    cache_dir = Path(args.cache)
    dest_dir = Path(args.dest)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    archive = cache_dir / asset["name"]
    if not archive.is_file() or archive.stat().st_size != asset["size"]:
        print(f"==> Downloading {asset['name']} ...")
        part = cache_dir / f"{asset['name']}.part"
        req = urllib.request.Request(asset["browser_download_url"],
                                     headers={"User-Agent": "opd2413-proton-arm/1.0"})
        with urllib.request.urlopen(req, timeout=600) as resp, part.open("wb") as out:
            shutil.copyfileobj(resp, out, length=1024 * 1024)
        part.replace(archive)

    verify_checksum(archive, csum)

    before = {p.name for p in dest_dir.iterdir()}
    print(f"==> Extracting into {dest_dir} ...")
    with tarfile.open(archive, "r:*") as tf:
        try:
            tf.extractall(dest_dir, filter="tar")
        except TypeError:
            tf.extractall(dest_dir)

    after = [p for p in dest_dir.iterdir() if p.name not in before and p.is_dir()]
    if not after:
        # Already existed: find matching directory
        for p in dest_dir.iterdir():
            if p.is_dir() and tag.lower() in p.name.lower():
                after.append(p)
    for d in after:
        apply_arm_fixes(d)
        print(f"==> Installed ARM64EC Proton at: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
