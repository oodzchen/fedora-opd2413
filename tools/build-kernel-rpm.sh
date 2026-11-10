#!/bin/bash
# Package a built kernel tree as kernel-opd2413.
# Usage: build-kernel-rpm.sh KERNEL_TARBALL KVER PKGREL
# KVER is uname -r, e.g. 7.2.6-2.opd2413; PKGREL is used only when KVER has no
# "-" suffix (the original 7.2.6 build).
# The tarball holds lib/modules/<kver>/{vmlinuz,dtb/,kernel/,modules.*}.
set -euo pipefail

tarball=$(realpath -e "${1:?kernel tarball}")
kver=${2:?kernel version (uname -r)}
pkgrel=${3:?package release}
repo=$(cd "$(dirname "$0")/.." && pwd)
top=${repo}/out/rpmbuild

mkdir -p "${top}"
rpmbuild -bb --target aarch64 \
    --define "_topdir ${top}" \
    --define "kver ${kver}" \
    --define "pkgrel ${pkgrel}" \
    --define "kernel_tarball ${tarball}" \
    "${repo}/packaging/kernel-opd2413/kernel-opd2413.spec"
find "${top}/RPMS" -name "kernel-opd2413-${kver%%-*}-*.rpm" -newer "${tarball}" -exec sha256sum {} +
