#!/usr/bin/env python3
"""Reboot the tablet into a chosen boot entry and wait until it is back.

Runs on the host; everything on the tablet goes through the SSH wrapper
(default private/ssh.sh, OPD_OS=fedora) and /usr/libexec/opd2413/boot-select
from the opd2413-device package.

  tools/tablet-reboot.py                         reboot into the default entry
  tools/tablet-reboot.py --entry opd2413-m3test  boot that loader entry once
  tools/tablet-reboot.py --entry X --fetch       ...then pull the boot logs
  tools/tablet-reboot.py --status                show what is selected, no reboot

The one-shot entry is consumed as soon as the test kernel mounts the root file
system. A kernel that resets earlier boots again until someone picks
"Fedora boot menu" in the kShimC menu and the normal kernel in systemd-boot;
when the tablet does not come back within --wait seconds this script says so
and does nothing else.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = '/usr/libexec/opd2413/boot-select'


def ssh(wrapper, command, timeout=60):
    env = os.environ | {'OPD_OS': os.environ.get('OPD_OS', 'fedora')}
    return subprocess.run([str(wrapper), command], env=env, capture_output=True, text=True, timeout=timeout)


def facts(wrapper):
    done = ssh(wrapper, 'cat /proc/sys/kernel/random/boot_id; uname -r; cat /proc/cmdline; '
                        'systemctl is-system-running; ' + TOOL + ' status', timeout=40)
    if done.returncode not in (0, 1) or not done.stdout:
        raise RuntimeError(done.stderr.strip() or 'no answer')
    boot, kernel, cmdline, state, *rest = done.stdout.splitlines()
    return {'boot_id': boot, 'kernel': kernel, 'cmdline': cmdline, 'system': state,
            'boot_select': json.loads('\n'.join(rest)) if rest else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ssh', type=Path, default=REPO / 'private/ssh.sh')
    parser.add_argument('--entry', help='systemd-boot loader entry to boot once')
    parser.add_argument('--wait', type=int, default=300, help='seconds to wait for SSH after the reboot')
    parser.add_argument('--fetch', action='store_true', help='run tools/bootlog/fetch-bootlogs.py afterwards')
    parser.add_argument('--status', action='store_true', help='only show the current selection')
    args = parser.parse_args()

    before = facts(args.ssh)
    if args.status:
        print(json.dumps(before, indent=2))
        return
    if args.entry:
        done = ssh(args.ssh, f'{TOOL} next {args.entry}')
        if done.returncode:
            sys.exit(done.stderr.strip())
        print('one-shot:', done.stdout.strip())
        # Ask systemd-boot's own matching (bootctl) which entry it will boot.
        want = f'{args.entry.removesuffix(".conf")}.conf'
        check = ssh(args.ssh, "bootctl list --no-pager --no-variables 2>/dev/null | "
                              "awk '/\\(default\\)/{d=1} d&&/ id:/{print $2; exit}'")
        if check.stdout.strip() != want:
            ssh(args.ssh, f'{TOOL} restore')
            sys.exit(f'systemd-boot would boot {check.stdout.strip() or "?"}, not {want}; one-shot undone')
    print(f"rebooting from {before['kernel']} (boot {before['boot_id'][:8]})", flush=True)
    ssh(args.ssh, 'systemctl reboot', timeout=20)
    start = time.monotonic()
    time.sleep(15)
    while time.monotonic() - start < args.wait:
        try:
            now = facts(args.ssh)
            if now['boot_id'] != before['boot_id']:
                break
        except (RuntimeError, subprocess.TimeoutExpired, ValueError):
            pass
        time.sleep(5)
    else:
        sys.exit(f'no new boot reachable over SSH within {args.wait} s. If a test entry resets or hangs before '
                 'mounting the root file system it keeps booting: choose "Fedora boot menu" in the kShimC menu '
                 'and the normal kernel. A short press of the power key shuts a live system down cleanly.')
    took = time.monotonic() - start
    selected = (now['boot_select'] or {}).get('booted_entry')
    print(f"back after {took:.0f} s: kernel {now['kernel']}, entry {selected}, system {now['system']}")
    if args.entry and selected != f'{args.entry.removesuffix(".conf")}.conf':
        print(f'note: asked for {args.entry}, booted {selected}')
    pending = (now['boot_select'] or {}).get('pending_next')
    if pending:
        print(f'warning: one-shot still pending: {pending}')
    if args.fetch:
        subprocess.run([sys.executable, str(REPO / 'tools/bootlog/fetch-bootlogs.py'), '--ssh', str(args.ssh)])


if __name__ == '__main__':
    main()
