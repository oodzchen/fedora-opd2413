#!/usr/bin/env python3
"""Pull every boot log the tablet kept, without touching it (read-only).

Run from the stable system after a test boot. Sources, earliest stage first:

  pstore-keep/     ramoops console of earlier boots, one directory per boot
                   that found records (opd2413-pstore-keep.service)
  pstore-archive/  what systemd-pstore moved to /var/lib/systemd/pstore
                   (fixed names: only the most recent record of each kind)
  pstore-live/     records still in /sys/fs/pstore
  bootlog/         files written by the initramfs collector on ARMADA_BOOT,
                   read with debugfs while the partition is not mounted
  journal/         kernel log of the last boots that reached journald

ramoops survives a warm reset (reboot, panic reboot, firmware reset) and is
lost by a long press of the power key; see docs/BOOT-LOGGING.md.

Usage:
  tools/bootlog/fetch-bootlogs.py                 # pull now
  tools/bootlog/fetch-bootlogs.py --wait 900 --after BOOT_ID
                                                  # wait for a boot other than BOOT_ID

The SSH wrapper (default private/ssh.sh with OPD_OS=fedora) and the output
directory (default private/bootlogs/) are outside Git.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

# Runs on the tablet. Only reads; writes a tar archive to stdout.
REMOTE = r'''
import io, json, os, re, subprocess, sys, tarfile, time
boots, skip = int(sys.argv[1]), set(sys.argv[2:])
out = tarfile.open(fileobj=sys.stdout.buffer, mode='w|')

def add(name, data):
    if isinstance(data, str):
        data = data.encode()
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), int(time.time()), 0o600
    out.addfile(info, io.BytesIO(data))

def run(*command):
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return done.returncode, done.stdout, done.stderr.decode(errors='replace')

def text(*command):
    return run(*command)[1].decode(errors='replace').strip()

def tree(root, prefix):
    for base, _, files in os.walk(root):
        for name in sorted(files):
            path = os.path.join(base, name)
            try:
                with open(path, 'rb') as handle:
                    add(prefix + os.path.relpath(path, root), handle.read())
            except OSError as error:
                add(prefix + os.path.relpath(path, root) + '.error', str(error))

state = {
    'kernel': os.uname().release,
    'cmdline': open('/proc/cmdline').read().strip(),
    'boot_id': open('/proc/sys/kernel/random/boot_id').read().strip(),
    'uptime_seconds': float(open('/proc/uptime').read().split()[0]),
    'system': text('systemctl', 'is-system-running'),
    'failed_units': text('systemctl', '--failed', '--no-legend', '--plain'),
    'pstore_keep_wanted_by': text('systemctl', 'show', '-P', 'WantedBy', 'opd2413-pstore-keep.service'),
}
tree('/var/lib/opd2413-pstore', 'pstore-keep/')
tree('/var/lib/systemd/pstore', 'pstore-archive/')
tree('/sys/fs/pstore', 'pstore-live/')

code, listing, _ = run('journalctl', '--list-boots', '--no-pager', '-o', 'json')
try:
    known = json.loads(listing) if code == 0 else []
except ValueError:
    known = []
add('boots.json', json.dumps(known, indent=1))
for boot in known[-boots:]:
    ident = boot.get('boot_id', '')
    if re.fullmatch('[0-9a-f]{32}', ident):
        add('journal/%s.kernel.txt' % ident,
            run('journalctl', '-b', ident, '-k', '--no-pager', '-o', 'short-monotonic')[1])

# The collector's partition: by label, never mounted here, debugfs opens read-only.
device = os.path.realpath('/dev/disk/by-partlabel/ARMADA_BOOT')
mounted = any(line.split()[0] == device for line in open('/proc/mounts'))
state['bootlog_partition'] = 'missing'
if os.path.exists(device) and not mounted:
    state['bootlog_partition'] = 'read'
    _, listing, _ = run('debugfs', '-R', 'ls -p /opd2413-bootlog', device)
    for line in listing.decode(errors='replace').splitlines():
        fields = line.split('/')
        if len(fields) < 7 or not re.fullmatch(r'[A-Za-z0-9._-]+', fields[5]) or fields[5] in ('.', '..'):
            continue
        name = fields[5]
        if not fields[2].startswith('04') or name in skip:
            continue
        for item in ('kernel.raw', 'service.result'):
            code, data, _ = run('debugfs', '-R', 'cat /opd2413-bootlog/%s/%s' % (name, item), device)
            if code == 0 and data:
                add('bootlog/%s/%s' % (name, item), data)
elif mounted:
    state['bootlog_partition'] = 'mounted, not read'
add('state.json', json.dumps(state, indent=1))
out.close()
'''


def ssh(wrapper, arguments, script=None, timeout=120):
    environment = os.environ | {'OPD_OS': os.environ.get('OPD_OS', 'fedora')}
    return subprocess.run([str(wrapper), *arguments], input=script, env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def wait_for_boot(wrapper, seconds, after):
    deadline = time.monotonic() + seconds
    while True:
        try:
            done = ssh(wrapper, ['cat', '/proc/sys/kernel/random/boot_id'], timeout=15)
            boot = done.stdout.decode().strip()
            if done.returncode == 0 and boot and boot != after:
                return boot
        except subprocess.TimeoutExpired:
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(5)


def printable(data):
    return data.decode('utf-8', errors='replace').replace('\x00', '')


def describe(path, seen):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    lines = [line for line in printable(data).splitlines() if line.strip()]
    version = next((line for line in lines if 'Linux version' in line), None)
    note = ' (same content as %s)' % seen[digest] if digest in seen else ''
    print('\n== %s: %d bytes, %d lines%s' % (os.path.relpath(path), len(data), len(lines), note))
    if version:
        print('   ' + version.strip()[:160])
    if not note:
        for line in lines[-12:]:
            print('   | ' + line[:200])
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ssh', default=REPO / 'private/ssh.sh', type=Path, help='SSH wrapper script')
    parser.add_argument('--out', default=REPO / 'private/bootlogs', type=Path, help='local output directory')
    parser.add_argument('--boots', default=4, type=int, help='kernel journals of this many last boots')
    parser.add_argument('--wait', default=0, type=int, metavar='SECONDS', help='wait for SSH first')
    parser.add_argument('--after', default='', metavar='BOOT_ID', help='with --wait: ignore this boot ID')
    options = parser.parse_args()
    if not options.ssh.is_file():
        sys.exit('SSH wrapper not found: %s' % options.ssh)

    if options.wait:
        boot = wait_for_boot(options.ssh, options.wait, options.after)
        if boot is None:
            sys.exit('no new boot reachable over SSH within %d s; nothing fetched' % options.wait)
        print('tablet reachable, boot ID %s' % boot)

    options.out.mkdir(parents=True, exist_ok=True)
    # Collector directories are immutable once written: fetch each only once.
    have = sorted({path.name for path in options.out.glob('*/bootlog/*') if path.is_dir()})
    seen = {}
    for path in sorted(options.out.glob('*/pstore-*/**/*')):
        if path.is_file():
            seen.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), str(path.relative_to(options.out)))

    done = ssh(options.ssh, ['python3', '-I', '-', str(options.boots), *have], script=REMOTE.encode())
    if done.returncode != 0 or not done.stdout:
        sys.exit('fetch failed (exit %d): %s' % (done.returncode, done.stderr.decode(errors='replace').strip()))
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as archive:
        state = json.load(archive.extractfile('state.json'))
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        target = options.out / ('%s-%s' % (stamp, state['boot_id'][:8]))
        target.mkdir()
        archive.extractall(target, filter='data')

    print('saved to %s' % os.path.relpath(target))
    print('running: kernel %s, system %s, boot %s, up %.0f s' % (
        state['kernel'], state['system'], state['boot_id'], state['uptime_seconds']))
    if state['failed_units']:
        print('failed units:\n' + state['failed_units'])
    if 'sysinit.target' not in state['pstore_keep_wanted_by'].split():
        print('note: opd2413-pstore-keep.service is not installed; only the newest pstore record is kept')
    print('collector partition: %s' % state['bootlog_partition'])

    records = [path for kind in ('pstore-keep', 'pstore-archive', 'pstore-live')
               for path in sorted((target / kind).glob('**/*')) if path.is_file()]
    if not records:
        print('\nno pstore records: the previous boot ended in a cold start or logged nothing to its console')
    for path in records:
        digest = describe(path, seen)
        seen.setdefault(digest, str(path.relative_to(options.out)))
    for path in sorted((target / 'bootlog').glob('*/kernel.raw')):
        describe(path, {})
    foreign = []
    for path in sorted((target / 'journal').glob('*.kernel.txt')):
        head = printable(path.read_bytes()[:4000])
        version = next((line for line in head.splitlines() if 'Linux version' in line), '')
        if version and state['kernel'] not in version:
            foreign.append((path, version))
    for path, version in foreign:
        print('\n== journal of a boot with another kernel: %s\n   %s' % (path, version.strip()[:160]))


if __name__ == '__main__':
    main()
