#!/usr/bin/env python3
"""Download, SHA-256 verify, and install Valve's native ARM64 Steam Client
directly from Valve's official CDN into ~/.local/share/Steam.

Also installs:
  - ~/.local/share/Steam/steam.cfg (blocks x86 CDN self-update clobbering)
  - ~/.local/bin/steam-arm64 (desktop/Big Picture launcher)
  - ~/.local/share/applications/steam-arm64.desktop
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

CDN_BASE = "https://client-update.akamai.steamstatic.com"
DEFAULT_CHANNEL = "steam_client_linuxarm64"


def parse_vdf_manifest(text: str) -> tuple[str, list[dict[str, str]]]:
    """Parse Valve's simple 2-level VDF manifest for version and zip entries."""
    ver_m = re.search(r'"version"\s+"([^"]+)"', text)
    version = ver_m.group(1) if ver_m else "0"

    entries: list[dict[str, str]] = []
    cur_name: str | None = None
    cur_map: dict[str, str] = {}
    depth = 0

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line == "{":
            depth += 1
            continue
        if line == "}":
            if depth == 2 and cur_name and "file" in cur_map:
                cur_map["name"] = cur_name
                entries.append(cur_map)
                cur_name = None
                cur_map = {}
            depth -= 1
            continue
        m_pair = re.match(r'^"([^"]+)"\s+"([^"]+)"$', line)
        if m_pair:
            k, v = m_pair.group(1), m_pair.group(2)
            if depth == 2:
                cur_map[k] = v
            continue
        m_key = re.match(r'^"([^"]+)"$', line)
        if m_key and depth == 1:
            cur_name = m_key.group(1)
            cur_map = {}

    return version, entries


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_zip(entry: dict[str, str], cache_dir: Path) -> Path:
    fname = entry["file"]
    expected = entry.get("sha2", "").lower()
    dest = cache_dir / fname
    if dest.is_file() and expected and sha256_file(dest) == expected:
        return dest

    url = f"{CDN_BASE}/{fname}"
    part = cache_dir / f"{fname}.part"
    cmd = [
        "curl", "-fsSL",
        "--retry", "4", "--retry-delay", "2",
        "--connect-timeout", "15",
        "--speed-time", "25", "--speed-limit", "10240",
        "-C", "-",
        "-A", "opd2413-steam-arm64/1.0",
        "-o", str(part),
        url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # Retry cleanly from 0 if server rejected range resume
        part.unlink(missing_ok=True)
        cmd_clean = [c for c in cmd if c not in ("-C", "-")]
        subprocess.run(cmd_clean, check=True)
    got = sha256_file(part)
    if expected and got != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch for {fname}: got {got}, expected {expected}")
    part.replace(dest)
    return dest


def extract_zip_preserving_perms(zpath: Path, steam_root: Path) -> int:
    count = 0
    with zipfile.ZipFile(zpath, "r") as zf:
        for info in zf.infolist():
            rel = info.filename.replace("\\", "/")
            if not rel or rel.startswith("/") or ".." in rel.split("/"):
                continue
            target = steam_root / rel
            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                link_target = zf.read(info).decode("utf-8", errors="replace")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or target.exists():
                    if target.is_dir() and not target.is_symlink():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                os.symlink(link_target, target)
                count += 1
                continue
            if info.is_dir() or rel.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            perm = unix_mode & 0o777
            if perm:
                target.chmod(perm)
            else:
                # Fallback executable heuristic for ELF binaries / shell scripts
                with target.open("rb") as fh:
                    magic = fh.read(4)
                if magic == b"\x7fELF" or magic.startswith(b"#!") or rel.endswith(".sh"):
                    target.chmod(0o755)
                else:
                    target.chmod(0o644)
            count += 1
    return count


def setup_symlinks_and_config(steam_root: Path, version: str, channel: str, allow_updates: bool) -> None:
    home = Path.home()
    dot_steam = home / ".steam"
    dot_steam.mkdir(parents=True, exist_ok=True)

    # Ensure runtime/SDK helper libraries exist in both steamrtarm64 and linuxarm64
    rt_dir = steam_root / "steamrtarm64"
    sdk_dir = steam_root / "linuxarm64"
    sdk_dir.mkdir(parents=True, exist_ok=True)
    if rt_dir.is_dir():
        for lib in ("steamclient.so", "crashhandler.so", "steam-launch-wrapper"):
            src = rt_dir / lib
            dst = sdk_dir / lib
            if src.is_file() and src.stat().st_size > 0 and (not dst.exists() or dst.stat().st_size == 0):
                shutil.copy2(src, dst)

    # Mark executable bits on all ELF executables and scripts in runtime/bin trees.
    # Valve's zip entries often carry 0644 permissions, which breaks steam-launch-wrapper,
    # reaper, fossilize_replay, gameoverlayui, steamerrorreporter, etc.
    for sub in ("steamrtarm64", "linuxarm64", "linux32", "linux64", "ubuntu12_32", "ubuntu12_64"):
        d = steam_root / sub
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if not p.is_file() or p.is_symlink():
                continue
            if p.name.endswith(".so") or ".so." in p.name:
                continue
            try:
                head = p.read_bytes()[:4]
            except OSError:
                continue
            if head == b"\x7fELF" or head.startswith(b"#!") or p.name.endswith(".sh"):
                p.chmod(0o755)

    for sub in ("steamrtarm64", "linuxarm64"):
        d = steam_root / sub
        if not d.is_dir():
            continue
        # Replace steamerrorreporter with a fast non-blocking stub (keeping .orig)
        # so non-fatal CEF assertions never hang steamwebhelper startup trying to
        # synchronously upload minidumps to crash.steampowered.com.
        reporter = d / "steamerrorreporter"
        reporter_orig = d / "steamerrorreporter.orig"
        if reporter.is_file():
            head = reporter.read_bytes()[:4]
            if head == b"\x7fELF" and not reporter_orig.exists():
                shutil.move(str(reporter), str(reporter_orig))
            reporter.write_text("#!/bin/sh\n# Non-blocking stub installed by opd2413 install-steam-arm64.py\nexit 0\n", encoding="utf-8")
            reporter.chmod(0o755)

    def force_link(src: Path, dst: Path) -> None:
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        elif dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src)

    force_link(steam_root, dot_steam / "steam")
    force_link(steam_root, dot_steam / "root")
    force_link(sdk_dir, dot_steam / "sdkarm64")
    force_link(rt_dir if rt_dir.is_dir() else sdk_dir, dot_steam / "binarm64")
    if (steam_root / "linux32").is_dir():
        force_link(steam_root / "linux32", dot_steam / "sdk32")
    if (steam_root / "linux64").is_dir():
        force_link(steam_root / "linux64", dot_steam / "sdk64")
    if (steam_root / "ubuntu12_32").is_dir():
        force_link(steam_root / "ubuntu12_32", dot_steam / "bin32")
    if (steam_root / "ubuntu12_64").is_dir():
        force_link(steam_root / "ubuntu12_64", dot_steam / "bin64")

    # Write steam.inf so client doesn't think version is 0
    steam_inf = f"ClientVersion={version}\n"
    (steam_root / "steam.inf").write_text(steam_inf, encoding="utf-8")
    if rt_dir.is_dir():
        (rt_dir / "steam.inf").write_text(steam_inf, encoding="utf-8")

    # Block automatic x86 CDN bootstrapper replacement by default
    cfg_text = (
        "BootStrapperInhibitAll=enable\n"
        "BootStrapperForceSelfUpdate=disable\n"
        "BootStrapperInhibitClientChecksum=enable\n"
        "BootStrapperInhibitBootstrapperChecksum=enable\n"
        "BootStrapperInhibitUpdateOnLaunch=enable\n"
    )
    if not allow_updates:
        (steam_root / "steam.cfg").write_text(cfg_text, encoding="utf-8")
        if rt_dir.is_dir():
            (rt_dir / "steam.cfg").write_text(cfg_text, encoding="utf-8")

    pkg_dir = steam_root / "package"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / f"{channel}.installed").write_text(f"{version}\n", encoding="utf-8")
    (steam_root / "compatibilitytools.d").mkdir(parents=True, exist_ok=True)
    (steam_root / "logs").mkdir(parents=True, exist_ok=True)

    # Valve's ARM64 client writes steamoverlay_{i386,x86_64}.json but omits
    # steamoverlay_arm64.json even though steamrtarm64/steamoverlayvulkanlayer.so
    # is shipped. Register it so ARM64EC Proton DXVK/VKD3D games get Steam Overlay
    # and the built-in In-Game Performance Monitor / FPS counter.
    overlay_so = rt_dir / "steamoverlayvulkanlayer.so"
    if overlay_so.is_file():
        vk_layers = home / ".local/share/vulkan/implicit_layer.d"
        vk_layers.mkdir(parents=True, exist_ok=True)
        overlay_json = vk_layers / "steamoverlay_arm64.json"
        overlay_json.write_text(
            "{\n"
            "\t\"file_format_version\" : \"1.0.0\",\n"
            "\t\"layer\" : {\n"
            "\t\t\"name\": \"VK_LAYER_VALVE_steam_overlay_arm64\",\n"
            "\t\t\"type\": \"GLOBAL\",\n"
            f"\t\t\"library_path\": \"{overlay_so}\",\n"
            "\t\t\"api_version\": \"1.3.207\",\n"
            "\t\t\"implementation_version\": \"1\",\n"
            "\t\t\"description\": \"Steam Overlay Layer (ARM64)\",\n"
            "\t\t\"disable_environment\": { \"DISABLE_VK_LAYER_VALVE_steam_overlay_1\": \"1\" },\n"
            "\t\t\"enable_environment\": { \"ENABLE_VK_LAYER_VALVE_steam_overlay_1\": \"1\" }\n"
            "\t}\n"
            "}\n",
            encoding="utf-8",
        )
        overlay_json.chmod(0o644)


def install_icons(steam_root: Path) -> None:
    """Install official Steam PNG icons into user hicolor icon theme."""
    import struct

    hicolor = Path.home() / ".local/share/icons/hicolor"
    ico_path = steam_root / "public/steam_tray.ico"
    png128_src = steam_root / "public/steam_tray_posix.png"

    # Extract embedded 256x256 PNG from steam_tray.ico if present
    png256_bytes: bytes | None = None
    if ico_path.is_file():
        data = ico_path.read_bytes()
        if len(data) >= 6:
            _, _, count = struct.unpack_from("<HHH", data, 0)
            for i in range(count):
                off_hdr = 6 + i * 16
                if off_hdr + 16 > len(data):
                    break
                w, h, _, _, _, _, sz, off = struct.unpack_from("<BBBBHHII", data, off_hdr)
                blob = data[off : off + sz]
                if (w == 0 and h == 0) and blob.startswith(b"\x89PNG\r\n\x1a\n"):
                    png256_bytes = blob
                    break

    if png256_bytes is not None:
        dst256 = hicolor / "256x256/apps/steam.png"
        dst256.parent.mkdir(parents=True, exist_ok=True)
        dst256.write_bytes(png256_bytes)

    # Generate all standard sizes from the crisp 256x256 logo via Pillow if available
    generated_128 = False
    try:
        from PIL import Image
        import io

        base_img = None
        if png256_bytes is not None:
            base_img = Image.open(io.BytesIO(png256_bytes)).convert("RGBA")
        elif png128_src.is_file():
            base_img = Image.open(png128_src).convert("RGBA")
        if base_img is not None:
            for sz in (16, 24, 32, 48, 64, 128):
                out = hicolor / f"{sz}x{sz}/apps/steam.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                base_img.resize((sz, sz), Image.Resampling.LANCZOS).save(out, format="PNG")
            generated_128 = True
    except Exception:
        pass

    if not generated_128 and png128_src.is_file():
        dst128 = hicolor / "128x128/apps/steam.png"
        dst128.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(png128_src, dst128)

    # Also ensure hicolor index.theme exists locally if icon lookup checks user hicolor
    sys_index = Path("/usr/share/icons/hicolor/index.theme")
    usr_index = hicolor / "index.theme"
    if sys_index.is_file() and not usr_index.exists():
        shutil.copy2(sys_index, usr_index)


def refresh_desktop_caches() -> None:
    home = Path.home()
    cmds = [
        ["gtk-update-icon-cache", "-f", "-t", str(home / ".local/share/icons/hicolor")],
        ["update-desktop-database", str(home / ".local/share/applications")],
        ["kbuildsycoca6", "--noincremental"],
        ["gdbus", "emit", "--session", "--object-path", "/KIconLoader",
         "--signal", "org.kde.KIconLoader.iconChanged", "0"],
    ]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install_drkonqi_wine_filter() -> None:
    """Install a user-level systemd drop-in for drkonqi-coredump-launcher@.service
    that silently drops harmless Wine/Proton teardown crashes while forwarding
    all native Linux/KDE crashes intact."""
    home = Path.home()
    libexec = home / ".local/libexec"
    libexec.mkdir(parents=True, exist_ok=True)
    wrapper = libexec / "opd-drkonqi-filter"
    wrapper.write_text(
        """#!/usr/bin/env python3
import os
import socket
import sys

REAL = "/usr/libexec/drkonqi-coredump-launcher"
WINE_MARKERS = (
    b"wine-preloader",
    b"wine64-preloader",
    b"/wine/aarch64-unix/wine",
    b"/wine/x86_64-unix/wine",
)

if os.environ.get("LISTEN_FDS") == "1":
    packets = []
    blob = b""
    try:
        sock = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            sock.settimeout(0.5)
            while True:
                try:
                    pkt = sock.recv(65536)
                except socket.timeout:
                    break
                if not pkt:
                    break
                packets.append(pkt)
                blob += pkt
                if any(m in blob for m in WINE_MARKERS):
                    sys.stderr.write("opd-drkonqi-filter: suppressed harmless Wine/Proton teardown crash\\n")
                    sys.exit(0)
        finally:
            sock.close()
    except SystemExit:
        raise
    except Exception:
        packets = []
        blob = b""

    if any(m in blob for m in WINE_MARKERS):
        sys.stderr.write("opd-drkonqi-filter: suppressed harmless Wine/Proton teardown crash\\n")
        sys.exit(0)

    if packets:
        # Replay exact buffered packets on fd 3 for real native Linux/KDE crashes
        s_srv, s_cli = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        for pkt in packets:
            s_srv.send(pkt)
        s_srv.close()
        os.dup2(s_cli.fileno(), 3, inheritable=True)
        if s_cli.fileno() != 3:
            s_cli.close()

os.execv(REAL, [REAL] + sys.argv[1:])
""",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    dropin_dir = home / ".config/systemd/user/drkonqi-coredump-launcher@.service.d"
    dropin_dir.mkdir(parents=True, exist_ok=True)
    dropin = dropin_dir / "10-opd2413-ignore-wine.conf"
    dropin.write_text(
        "[Service]\n"
        "ExecStart=\n"
        f"ExecStart={wrapper}\n",
        encoding="utf-8",
    )
    dropin.chmod(0o644)
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install_launcher(steam_root: Path) -> None:
    home = Path.home()
    bin_dir = home / ".local/bin"
    apps_dir = home / ".local/share/applications"
    bin_dir.mkdir(parents=True, exist_ok=True)
    apps_dir.mkdir(parents=True, exist_ok=True)

    install_icons(steam_root)
    install_drkonqi_wine_filter()

    launcher = bin_dir / "steam-arm64"
    launcher.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail

STEAMROOT="${{STEAMROOT:-{steam_root}}}"
RT_DIR="${{STEAMROOT}}/steamrtarm64"
[[ -x "${{RT_DIR}}/steam" ]] || RT_DIR="${{STEAMROOT}}/linuxarm64"

if [[ ! -x "${{RT_DIR}}/steam" ]]; then
    echo "steam-arm64: missing ${{RT_DIR}}/steam" >&2
    exit 1
fi

# Clean stale crash/lock files ONLY when no Steam instance is currently running.
# Deleting Singleton* while Steam is alive breaks the running instance on a 2nd launch.
if ! pgrep -u "$(id -u)" -f "${{RT_DIR}}/steam" >/dev/null 2>&1; then
    rm -f "${{STEAMROOT}}/.crash" "${{STEAMROOT}}/steam.pid" \\
          "${{STEAMROOT}}/config/htmlcache/SingletonLock" \\
          "${{STEAMROOT}}/config/htmlcache/SingletonCookie" \\
          "${{STEAMROOT}}/config/htmlcache/SingletonSocket" 2>/dev/null || true
fi

export LD_LIBRARY_PATH="${{RT_DIR}}${{LD_LIBRARY_PATH:+:${{LD_LIBRARY_PATH}}}}"
export STEAMLINK_V4L2_RESET_AFTER_LAST_BUF=1
export WINE_D3D_CONFIG="${{WINE_D3D_CONFIG:-renderer=vulkan}}"
export PROTON_USE_NTSYNC="${{PROTON_USE_NTSYNC:-1}}"
if [[ -d "${{HOME}}/.local/share/opd2413-steam-layer" ]]; then
    export VK_ADD_IMPLICIT_LAYER_PATH="${{HOME}}/.local/share/opd2413-steam-layer${{VK_ADD_IMPLICIT_LAYER_PATH:+:${{VK_ADD_IMPLICIT_LAYER_PATH}}}}"
fi

# Steam Desktop UI runs via XWayland on KDE Wayland; keep DISPLAY intact.
export QT_QPA_PLATFORM=xcb
unset LD_PRELOAD || true

EXTRA_ARGS=()
if [[ "${{1:-}}" == "--gamepadui" ]]; then
    shift
    EXTRA_ARGS+=(-gamepadui -steamdeck)
fi

cd "${{STEAMROOT}}"
exec "${{RT_DIR}}/steam" -noverifyfiles -inhibitbootstrap -nobootstrapperupdate "${{EXTRA_ARGS[@]}}" "$@"
""",
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    # Provide ~/.local/bin/steam symlink alongside system /usr/bin/steam
    steam_link = bin_dir / "steam"
    if steam_link.exists() or steam_link.is_symlink():
        steam_link.unlink()
    steam_link.symlink_to(launcher.name)

    # Remove legacy duplicate desktop file so KRunner/Plasma match steam.desktop cleanly
    legacy_desktop = apps_dir / "steam-arm64.desktop"
    if legacy_desktop.exists() or legacy_desktop.is_symlink():
        legacy_desktop.unlink()

    icon_png = home / ".local/share/icons/hicolor/256x256/apps/steam.png"
    icon_val = str(icon_png) if icon_png.is_file() else "steam"

    desktop = apps_dir / "steam.desktop"
    desktop.write_text(
        f"""[Desktop Entry]
Name=Steam (ARM64)
Comment=Native ARM64 Steam Client on OPD2413 Fedora
Exec={launcher} %U
Icon={icon_val}
Terminal=false
Type=Application
Categories=Network;FileTransfer;Game;
MimeType=x-scheme-handler/steam;x-scheme-handler/steamlink;
StartupWMClass=steam
""",
        encoding="utf-8",
    )
    desktop.chmod(0o644)
    refresh_desktop_caches()


def main() -> int:
    ap = argparse.ArgumentParser(description="Install Valve's official native ARM64 Steam Client")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL,
                    help=f"Valve CDN manifest name (default: {DEFAULT_CHANNEL})")
    ap.add_argument("--dest", default=str(Path.home() / ".local/share/Steam"),
                    help="Steam install directory (default: ~/.local/share/Steam)")
    ap.add_argument("--cache", default=str(Path.home() / ".cache/opd2413-steam-arm64"),
                    help="Download cache directory")
    ap.add_argument("--allow-updates", action="store_true",
                    help="Do not write steam.cfg bootstrapper inhibit flags")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch manifest and print summary without downloading zips")
    ap.add_argument("--reconfigure", action="store_true",
                    help="Re-apply symlinks, launcher, icons, and stubs on existing install without re-downloading")
    args = ap.parse_args()

    steam_root = Path(args.dest)
    if args.reconfigure:
        ver_file = steam_root / "package" / f"{args.channel}.installed"
        version = ver_file.read_text(encoding="utf-8").strip() if ver_file.is_file() else "1794536281"
        setup_symlinks_and_config(steam_root, version, args.channel, args.allow_updates)
        install_launcher(steam_root)
        print(f"==> Reconfigured Steam ARM64 in {steam_root} (version={version})")
        return 0

    manifest_url = f"{CDN_BASE}/{args.channel}"
    print(f"==> Fetching manifest: {manifest_url}")
    req = urllib.request.Request(manifest_url, headers={"User-Agent": "opd2413-steam-arm64/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        manifest_text = resp.read().decode("utf-8", errors="replace")

    version, entries = parse_vdf_manifest(manifest_text)
    total_bytes = sum(int(e.get("size", "0") or 0) for e in entries)
    print(f"==> Manifest version={version}, packages={len(entries)}, total={total_bytes / (1024*1024):.1f} MiB")

    if args.dry_run:
        for e in entries:
            sz = int(e.get("size", "0") or 0) / (1024 * 1024)
            print(f"  {e['name']:34s} {sz:6.1f} MiB  {e['file']}")
        return 0

    cache_dir = Path(args.cache)
    steam_root = Path(args.dest)
    cache_dir.mkdir(parents=True, exist_ok=True)
    steam_root.mkdir(parents=True, exist_ok=True)

    print("==> Downloading & verifying SHA-256 (6 parallel streams)...")
    zips: list[Path] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(fetch_zip, e, cache_dir): e for e in entries}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            e = futs[fut]
            zp = fut.result()
            zips.append(zp)
            done += 1
            print(f"  [{done:2d}/{len(entries)}] verified {e['name']}")

    # Extract deterministically in manifest order
    zip_by_file = {z.name: z for z in zips}
    total_files = 0
    print(f"==> Extracting into {steam_root} ...")
    for e in entries:
        zp = zip_by_file[e["file"]]
        total_files += extract_zip_preserving_perms(zp, steam_root)

    setup_symlinks_and_config(steam_root, version, args.channel, args.allow_updates)
    install_launcher(steam_root)
    print(f"==> Done: extracted {total_files} files. Launch with: steam-arm64")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
