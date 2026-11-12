#!/usr/bin/env bash
# The initramfs log service runs with umask 077. Its mount/umount helpers must
# not leave a private /run/mount behind: /run is carried into the real root.
# Runs in an unprivileged user+mount namespace on tmpfs; touches no real disk.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
lib="$repo/tools/bootlog/dracut/91opd2413-bootlog/bootlog-lib.sh"
unshare -Urm true 2>/dev/null || { echo 'bootlog-mount: SKIP (no unprivileged user namespaces)'; exit 0; }

# Control: the plain call the helpers replace does create a 0700 /run/mount.
got=$(unshare -Urm bash -c 'mount -t tmpfs none /run && mkdir /run/t && umask 077 &&
    mount -t tmpfs none /run/t && stat -c %a /run/mount')
[ "$got" = 700 ] || { echo "FAIL: control expected 700, got '$got' (libmount behaviour changed?)"; exit 1; }

got=$(LIB="$lib" unshare -Urm bash -c 'set -euo pipefail
    mount -t tmpfs none /run && mkdir /run/t
    . "$LIB"
    umask 077
    bootlog_mount tmpfs none /run/t
    awk '\''$5=="/run/t" {print $6}'\'' /proc/self/mountinfo | tr "," "\n" | grep -cxE "rw|nosuid|nodev|noexec|noatime"
    : > /run/t/probe; stat -c %a /run/t/probe
    bootlog_umount /run/t
    awk '\''$5=="/run/t" {found=1} END {print found ? "mounted" : "unmounted"}'\'' /proc/self/mountinfo
    if [ -e /run/mount ]; then stat -c %a /run/mount; else echo absent; fi
    umask')
expected=$'5\n600\nunmounted\nabsent\n0077'
[ "$got" = "$expected" ] || { echo "FAIL: got:"; echo "$got"; exit 1; }
! grep -nE '^\s*(mount|umount) ' "$repo/tools/bootlog/dracut/91opd2413-bootlog/bootlog-control" ||
    { echo 'FAIL: bootlog-control calls mount/umount directly'; exit 1; }
echo 'bootlog-mount: helpers keep options and the caller umask, leave no /run/mount behind'
