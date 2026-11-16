#!/bin/bash
# Build opd2413-camera (aarch64) RPM natively on the tablet (default) or in a
# local QEMU aarch64 podman container (--local / OPD_BUILD_TARGET=local).
#
#   tools/build-camera-rpm.sh [--local|--tablet] [--rebuild-image] [VERSION] [RELEASE]
#
# Outputs: out/rpmbuild/RPMS/aarch64/opd2413-camera-VERSION-RELEASE.fc45.aarch64.rpm
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=tools/tablet-build-common.sh
source "$repo/tools/tablet-build-common.sh"

opd_parse_build_target "$@"
set -- "${OPD_ARGS[@]+"${OPD_ARGS[@]}"}"

ver=${1:-0.1}
rel=${2:-1}
S=$repo/packaging/opd2413-camera
work=$repo/out/camera/work
rpms=$repo/out/rpmbuild/RPMS/aarch64
image=${FEDORA_IMAGE:-registry.fedoraproject.org/fedora:45}
cache=$repo/out/m3k/dnf-cache
jobs=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))

mkdir -p "$work" "$rpms" "$cache"

if [ "$OPD_BUILD_TARGET" = "tablet" ]; then
    opd_check_tablet_ssh "$repo"
    rwork="/tmp/opd-build-camera-$$"
    cleanup_remote() {
        opd_tablet_ssh "$repo" "rm -rf '$rwork'" >/dev/null 2>&1 || true
    }
    trap cleanup_remote EXIT

    opd_tablet_ssh "$repo" "rm -rf '$rwork' && mkdir -p '$rwork/src' '$rwork/rpm'/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}"
    tar -cf - -C "$S" . | opd_tablet_ssh "$repo" "tar -xf - -C '$rwork/src'"

    if ! opd_tablet_ssh "$repo" "env VER=$(printf '%q' "$ver") REL=$(printf '%q' "$rel") RWORK=$(printf '%q' "$rwork") bash -euxs" <<'REMOTE' > "$work/build-$ver-$rel.log" 2>&1
missing=()
for pkg in rpm-build python3-devel python3-numpy python3-opencv python3-pillow desktop-file-utils; do
    rpm -q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
    dnf -y --setopt=install_weak_deps=False install "${missing[@]}" >/dev/null
fi
JOBS=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))
systemd-inhibit --what=idle:sleep --who=opd2413-build --why="Build opd2413-camera RPM" \
    rpmbuild -bb \
        --define "_topdir $RWORK/rpm" \
        --define "_smp_mflags -j${JOBS}" \
        --define "pkgver ${VER}" \
        --define "pkgrel ${REL}" \
        --define "srcdir $RWORK/src" \
        "$RWORK/src/opd2413-camera.spec"
REMOTE
    then
        tail -60 "$work/build-$ver-$rel.log"
        exit 1
    fi

    opd_tablet_ssh "$repo" "tar -cf - -C '$rwork/rpm/RPMS/aarch64' ." | tar -xf - -C "$rpms"
else
    rm -rf "$work/rpm" && mkdir -p "$work/rpm"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
    builder="localhost/opd2413-builder-camera:fc45"
    setup_cmd='dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True install \
        rpm-build python3-devel python3-numpy python3-opencv python3-pillow \
        desktop-file-utils >/dev/null'
    opd_ensure_cached_image "--arch arm64" "$builder" "$image" "$cache" "$setup_cmd"

    podman run --rm --arch arm64 --network host \
        -v "$repo:/repo:ro,Z" -v "$work:/work:Z" \
        -e VER="$ver" -e REL="$rel" -e JOBS="$jobs" \
        "$builder" bash -euxc '
    rpmbuild -bb \
        --define "_topdir /work/rpm" \
        --define "_smp_mflags -j${JOBS}" \
        --define "pkgver ${VER}" \
        --define "pkgrel ${REL}" \
        --define "srcdir /repo/packaging/opd2413-camera" \
        /repo/packaging/opd2413-camera/opd2413-camera.spec
    ' > "$work/build-$ver-$rel.log" 2>&1 || { tail -60 "$work/build-$ver-$rel.log"; exit 1; }

    cp -f "$work/rpm/RPMS/aarch64/"*.rpm "$rpms/"
fi

sha256sum "$rpms/opd2413-camera-${ver}-${rel}."*.rpm
