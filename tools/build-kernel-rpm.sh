#!/bin/bash
# Package a built kernel tree as kernel-opd2413.
# Usage: build-kernel-rpm.sh KERNEL_TARBALL KVER PKGREL
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
find "${top}/RPMS" -name "kernel-opd2413-${kver}-${pkgrel}.*.rpm" -exec sha256sum {} +
