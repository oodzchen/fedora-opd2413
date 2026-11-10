#!/bin/bash
# Build opd2413-device and opd2413-audio from this repository.
# Usage: build-device-rpms.sh PKGVER PKGREL
set -euo pipefail

pkgver=${1:?package version}
pkgrel=${2:?package release}
repo=$(cd "$(dirname "$0")/.." && pwd)
top=${repo}/out/rpmbuild
mkdir -p "${top}"

build() {
    local name=$1 srcdir=$2
    rpmbuild -bb \
        --define "_topdir ${top}" \
        --define "pkgver ${pkgver}" \
        --define "pkgrel ${pkgrel}" \
        --define "srcdir ${srcdir}" \
        "${repo}/packaging/${name}/${name}.spec" >"${top}/${name}-build.log" 2>&1 \
        || { tail -20 "${top}/${name}-build.log" >&2; exit 1; }
    find "${top}/RPMS" -name "${name}-${pkgver}-${pkgrel}.*.rpm" -exec sha256sum {} +
}
build opd2413-device "${repo}/device"
build opd2413-audio "${repo}/device/audio"
