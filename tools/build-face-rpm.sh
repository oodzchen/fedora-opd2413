#!/bin/bash
# Build opd2413-face (aarch64) RPM natively on the tablet (default) or in a
# local QEMU aarch64 podman container (--local / OPD_BUILD_TARGET=local).
#
#   tools/build-face-rpm.sh [--local|--tablet] [--rebuild-image] [VERSION] [RELEASE]
#
# Outputs: out/rpmbuild/RPMS/aarch64/opd2413-face-VERSION-RELEASE.fc45.aarch64.rpm
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=tools/tablet-build-common.sh
source "$repo/tools/tablet-build-common.sh"

opd_parse_build_target "$@"
set -- "${OPD_ARGS[@]+"${OPD_ARGS[@]}"}"

ver=${1:-0.1}
rel=${2:-1}
S=$repo/packaging/opd2413-face
models=$repo/out/face/models
work=$repo/out/face/work
rpms=$repo/out/rpmbuild/RPMS/aarch64
image=${FEDORA_IMAGE:-registry.fedoraproject.org/fedora:45}
cache=$repo/out/m3k/dnf-cache
jobs=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))

mkdir -p "$models" "$work" "$rpms" "$cache"

python3 - "$S" "$models" <<'EOF'
import hashlib, json, os, sys, urllib.request
S, models = sys.argv[1:3]
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
lock = json.load(open(os.path.join(S, "sources.json")))
for m in lock["models"]:
    dst = os.path.join(models, m["filename"])
    if not os.path.exists(dst):
        print(f"Downloading {m['url']}...")
        urllib.request.urlretrieve(m["url"], dst)
    if h(dst) != m["sha256"]:
        sys.exit(f"{dst}: SHA-256 mismatch")
print(f"Verified {len(lock['models'])} ONNX models")
EOF

builder="localhost/opd2413-builder-face:fc45"
setup_cmd='dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True install \
    rpm-build gcc make cmake ninja-build pkgconf-pkg-config pam-devel systemd-devel \
    qt6-qtbase-devel qt6-qtdeclarative-devel selinux-policy-devel checkpolicy \
    policycoreutils python3 authselect >/dev/null'

if [ "$OPD_BUILD_TARGET" = "tablet" ]; then
    opd_check_tablet_ssh "$repo"
    rwork="/tmp/opd-build-face-$$"
    cleanup_remote() {
        opd_tablet_ssh "$repo" "rm -rf '$rwork'" >/dev/null 2>&1 || true
    }
    trap cleanup_remote EXIT

    opd_tablet_ssh "$repo" "rm -rf '$rwork' && mkdir -p '$rwork/src' '$rwork/models' '$rwork/work/rpm'/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}"
    tar -cf - -C "$S" . | opd_tablet_ssh "$repo" "tar -xf - -C '$rwork/src'"
    tar -cf - -C "$models" . | opd_tablet_ssh "$repo" "tar -xf - -C '$rwork/models'"

    if ! {
        declare -f opd_ensure_cached_image
        cat <<'REMOTE'
rpm -q podman >/dev/null 2>&1 || dnf -y --setopt=install_weak_deps=False install podman >/dev/null
opd_ensure_cached_image "" "$BUILDER" "$IMAGE" "/var/tmp/opd2413-dnf-cache" "$SETUP_CMD"
JOBS=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))
systemd-inhibit --what=idle:sleep --who=opd2413-build --why="Build opd2413-face RPM" \
    podman run --rm --network host \
        -v "$RWORK/src:/src:ro,Z" -v "$RWORK/models:/models:ro,Z" -v "$RWORK/work:/work:Z" \
        -e VER="$VER" -e REL="$REL" -e JOBS="$JOBS" \
        "$BUILDER" bash -euxc '
rpmbuild -bb \
    --define "_topdir /work/rpm" \
    --define "_smp_mflags -j${JOBS}" \
    --define "pkgver ${VER}" \
    --define "pkgrel ${REL}" \
    --define "srcdir /src" \
    --define "modeldir /models" \
    /src/opd2413-face.spec
'
REMOTE
    } | opd_tablet_ssh "$repo" "env VER=$(printf '%q' "$ver") REL=$(printf '%q' "$rel") RWORK=$(printf '%q' "$rwork") BUILDER=$(printf '%q' "$builder") IMAGE=$(printf '%q' "$image") SETUP_CMD=$(printf '%q' "$setup_cmd") OPD_REBUILD_IMAGE=$(printf '%q' "$OPD_REBUILD_IMAGE") bash -euxs" > "$work/build-$ver-$rel.log" 2>&1; then
        tail -60 "$work/build-$ver-$rel.log"
        exit 1
    fi

    opd_tablet_ssh "$repo" "tar -cf - -C '$rwork/work/rpm/RPMS/aarch64' ." | tar -xf - -C "$rpms"
else
    rm -rf "$work/rpm" && mkdir -p "$work/rpm"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
    opd_ensure_cached_image "--arch arm64" "$builder" "$image" "$cache" "$setup_cmd"

    podman run --rm --arch arm64 --network host \
        -v "$repo:/repo:ro,Z" -v "$work:/work:Z" -v "$models:/models:ro,Z" \
        -e VER="$ver" -e REL="$rel" -e JOBS="$jobs" \
        "$builder" bash -euxc '
    rpmbuild -bb \
        --define "_topdir /work/rpm" \
        --define "_smp_mflags -j${JOBS}" \
        --define "pkgver ${VER}" \
        --define "pkgrel ${REL}" \
        --define "srcdir /repo/packaging/opd2413-face" \
        --define "modeldir /models" \
        /repo/packaging/opd2413-face/opd2413-face.spec
    ' > "$work/build-$ver-$rel.log" 2>&1 || { tail -60 "$work/build-$ver-$rel.log"; exit 1; }

    cp -f "$work/rpm/RPMS/aarch64/"*.rpm "$rpms/"
fi

sha256sum "$rpms/opd2413-face-${ver}-${rel}."*.rpm
