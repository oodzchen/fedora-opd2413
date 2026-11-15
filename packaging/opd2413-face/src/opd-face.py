#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""CLI for managing OPD2413 face unlock templates and testing recognition."""

import argparse
import os
import pwd
import shutil
import subprocess
import sys
import time
from pathlib import Path

from gi.repository import Gio, GLib

BUS_NAME = "org.opd2413.Face1"
BUS_PATH = "/org/opd2413/Face1"
BUS_IFACE = "org.opd2413.Face1"

LOCKSCREEN_SRC = Path("/usr/share/opd2413-face/lockscreen")
SHELL_SYS_DIR = Path("/usr/share/plasma/shells/org.kde.plasma.desktop")
SHELL_LOCAL_DIR = Path("/usr/local/share/plasma/shells/org.kde.plasma.desktop")
LEGACY_KDE_FACE_PAM = Path("/etc/pam.d/kde-face")
LEGACY_LNF_LOCAL_DIR = Path("/usr/local/share/plasma/look-and-feel")
MANAGED_MARKER = ".opd2413-face-managed"


def default_user() -> str:
    return (
        os.environ.get("SUDO_USER")
        or os.environ.get("PKEXEC_UID")
        and pwd.getpwuid(int(os.environ["PKEXEC_UID"])).pw_name
        or os.environ.get("USER")
        or pwd.getpwuid(os.getuid()).pw_name
    )


def get_bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def call_dbus(bus, method: str, sig: str, args: tuple, ret_sig: str, timeout_ms: int = 15000):
    res = bus.call_sync(
        BUS_NAME,
        BUS_PATH,
        BUS_IFACE,
        method,
        GLib.Variant(sig, args) if sig else None,
        GLib.VariantType(ret_sig),
        Gio.DBusCallFlags.NONE,
        timeout_ms,
        None,
    )
    return res.unpack()


def require_root_or_hint(cmd_args):
    if os.geteuid() != 0:
        print(
            f"Root privileges required. Run with: pkexec opd-face {' '.join(cmd_args)}",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_enroll(args):
    require_root_or_hint(sys.argv[1:])
    bus = get_bus()
    user = args.user or default_user()
    prompts = [
        "Look directly at the front camera",
        "Tilt head slightly LEFT while looking at camera",
        "Tilt head slightly RIGHT while looking at camera",
        "Tilt head slightly UP while looking at camera",
        "Hold tablet at natural reading distance",
    ]
    print(f"Enrolling {args.samples} face template(s) for user '{user}'...")
    for i in range(args.samples):
        prompt = prompts[i] if i < len(prompts) else f"Pose #{i + 1}"
        print(f"[{i + 1}/{args.samples}] {prompt}...")
        replace = args.replace and (i == 0)
        ok, count, msg = call_dbus(
            bus, "EnrollSample", "(sbu)", (user, replace, 10000), "(bus)", 12000
        )
        if not ok:
            print(f"  FAILED: {msg}", file=sys.stderr)
            return 1
        print(f"  OK: {msg} (total templates: {count})")
        if i + 1 < args.samples:
            time.sleep(0.35)
    print(f"Enrollment complete for '{user}'. Run 'opd-face test --user {user}' to verify.")
    return 0


def cmd_test(args):
    bus = get_bus()
    user = args.user or default_user()
    (enrolled,) = call_dbus(bus, "HasEnrolled", "(s)", (user,), "(b)", 2000)
    if not enrolled:
        print(f"No face enrolled for user '{user}'.", file=sys.stderr)
        return 2
    t0 = time.monotonic()
    matched, reason, score = call_dbus(
        bus, "Verify", "(ssu)", (user, "opd-face-test", args.timeout), "(bsd)", args.timeout + 3000
    )
    dt_ms = (time.monotonic() - t0) * 1000.0
    status = "MATCHED" if matched else "REJECTED"
    print(f"{status}: user={user} score={score:.4f} reason={reason} elapsed={dt_ms:.0f}ms")
    return 0 if matched else 1


def cmd_clear(args):
    require_root_or_hint(sys.argv[1:])
    bus = get_bus()
    user = args.user or default_user()
    (removed,) = call_dbus(bus, "ClearUser", "(s)", (user,), "(b)", 3000)
    print(f"Cleared face templates for '{user}': {'yes' if removed else 'none present'}")
    return 0


def cmd_list(_args):
    require_root_or_hint(sys.argv[1:])
    bus = get_bus()
    (users,) = call_dbus(bus, "ListUsers", "", (), "(a(su))", 3000)
    if not users:
        print("No users enrolled.")
        return 0
    for uname, count in users:
        print(f"{uname}\t{count} template(s)")
    return 0


def cmd_status(args):
    bus = get_bus()
    user = args.user or default_user()
    busy, state, last_reason = call_dbus(bus, "GetStatus", "", (), "(bss)", 2000)
    (enrolled,) = call_dbus(bus, "HasEnrolled", "(s)", (user,), "(b)", 2000)
    print(f"service: org.opd2413.Face1 (busy={busy}, state={state}, last={last_reason or '-'})")
    print(f"user '{user}': enrolled={'yes' if enrolled else 'no'}")
    cur = subprocess.run(["authselect", "current", "--raw"], capture_output=True, text=True)
    if cur.returncode == 0:
        print(f"authselect: {cur.stdout.strip()}")
    ui_ok = (SHELL_LOCAL_DIR / MANAGED_MARKER).exists()
    print(f"lockscreen UI shell overlay: {'enabled' if ui_ok else 'disabled'}")
    return 0


def _restorecon(path: Path):
    if shutil.which("restorecon"):
        subprocess.run(["restorecon", "-R", str(path)], check=False)


def _cleanup_legacy_kde_integration():
    LEGACY_KDE_FACE_PAM.unlink(missing_ok=True)
    if LEGACY_LNF_LOCAL_DIR.is_dir():
        for pkg_dir in list(LEGACY_LNF_LOCAL_DIR.iterdir()):
            if pkg_dir.is_dir() and not pkg_dir.is_symlink() and (pkg_dir / MANAGED_MARKER).exists():
                shutil.rmtree(pkg_dir)
        try:
            if not any(LEGACY_LNF_LOCAL_DIR.iterdir()):
                LEGACY_LNF_LOCAL_DIR.rmdir()
        except OSError:
            pass


def _enable_kde_integration():
    _cleanup_legacy_kde_integration()

    if not LOCKSCREEN_SRC.is_dir() or not SHELL_SYS_DIR.is_dir():
        return

    SHELL_LOCAL_DIR.parent.mkdir(parents=True, exist_ok=True)
    for base in (Path("/usr/local/share/plasma"), SHELL_LOCAL_DIR.parent):
        os.chmod(base, 0o755)

    if SHELL_LOCAL_DIR.is_symlink():
        SHELL_LOCAL_DIR.unlink()
    elif SHELL_LOCAL_DIR.exists():
        if not (SHELL_LOCAL_DIR / MANAGED_MARKER).exists():
            print(
                f"Warning: skipping unmanaged shell override at {SHELL_LOCAL_DIR}",
                file=sys.stderr,
            )
            return
        shutil.rmtree(SHELL_LOCAL_DIR)

    shutil.copytree(SHELL_SYS_DIR, SHELL_LOCAL_DIR, symlinks=False)
    dst_lockscreen = SHELL_LOCAL_DIR / "contents" / "lockscreen"
    if dst_lockscreen.exists():
        shutil.rmtree(dst_lockscreen)
    shutil.copytree(LOCKSCREEN_SRC, dst_lockscreen, symlinks=False)

    for root_dir, _dirs, files in os.walk(SHELL_LOCAL_DIR):
        os.chmod(root_dir, 0o755)
        for fname in files:
            os.chmod(Path(root_dir) / fname, 0o644)

    marker = SHELL_LOCAL_DIR / MANAGED_MARKER
    marker.write_text("managed by opd2413-face\n", encoding="utf-8")
    os.chmod(marker, 0o644)
    _restorecon(SHELL_LOCAL_DIR)


def _disable_kde_integration():
    _cleanup_legacy_kde_integration()
    if SHELL_LOCAL_DIR.is_dir() and not SHELL_LOCAL_DIR.is_symlink() and (SHELL_LOCAL_DIR / MANAGED_MARKER).exists():
        shutil.rmtree(SHELL_LOCAL_DIR)
        try:
            if SHELL_LOCAL_DIR.parent.is_dir() and not any(SHELL_LOCAL_DIR.parent.iterdir()):
                SHELL_LOCAL_DIR.parent.rmdir()
        except OSError:
            pass


def _current_authselect_features():
    cur = subprocess.run(["authselect", "current", "--raw"], capture_output=True, text=True)
    if cur.returncode != 0:
        return ["with-silent-lastlog", "with-mdns4"]
    tokens = cur.stdout.strip().split()
    return [t for t in tokens[1:] if t.startswith("with-") or t.startswith("without-")]


def cmd_enable(_args):
    require_root_or_hint(sys.argv[1:])
    feats = _current_authselect_features()
    cmd = ["authselect", "select", "opd2413-face", *feats, "--force"]
    subprocess.run(cmd, check=True)
    _enable_kde_integration()
    print("Enabled PAM face authentication (authselect + lockscreen UI).")
    return 0


def cmd_disable(_args):
    require_root_or_hint(sys.argv[1:])
    _disable_kde_integration()
    feats = _current_authselect_features()
    cmd = ["authselect", "select", "local", *feats, "--force"]
    subprocess.run(cmd, check=True)
    print("Disabled PAM face authentication (reverted to authselect local + stock lockscreen).")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="opd-face", description="OPD2413 native face unlock tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_enroll = sub.add_parser("enroll", help="Enroll face templates for a user")
    p_enroll.add_argument("--user", help="Target username (defaults to current user)")
    p_enroll.add_argument("--samples", type=int, default=4, help="Number of samples to capture")
    p_enroll.add_argument("--replace", action="store_true", help="Replace existing templates")
    p_enroll.set_defaults(func=cmd_enroll)

    p_test = sub.add_parser("test", help="Test live face verification")
    p_test.add_argument("--user", help="Target username")
    p_test.add_argument("--timeout", type=int, default=5000, help="Timeout in ms")
    p_test.set_defaults(func=cmd_test)

    p_clear = sub.add_parser("clear", help="Remove enrolled face templates for a user")
    p_clear.add_argument("--user", help="Target username")
    p_clear.set_defaults(func=cmd_clear)

    p_list = sub.add_parser("list", help="List all enrolled users")
    p_list.set_defaults(func=cmd_list)

    p_status = sub.add_parser("status", help="Show service and user enrollment status")
    p_status.add_argument("--user", help="Target username")
    p_status.set_defaults(func=cmd_status)

    p_enable = sub.add_parser("enable", help="Activate opd2413-face authselect PAM profile")
    p_enable.set_defaults(func=cmd_enable)

    p_disable = sub.add_parser("disable", help="Revert to stock local authselect PAM profile")
    p_disable.set_defaults(func=cmd_disable)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
