#!/bin/bash
# Build opd2413-sensors (aarch64) RPM natively on the tablet (default) or in a
# local QEMU aarch64 podman container (--local).
#
#   tools/build-sensors-rpm.sh [--local|--tablet] [--rebuild-image] VERSION RELEASE ERHAI_REPO
#
# Inputs, all verified before anything is built:
#   out/sensors/src/          the three source archives of packaging/opd2413-sensors/sources.json
#                             (fetched by this script when missing; SHA-256 pinned there)
#   packaging/opd2413-sensors/patches/   the patches listed in sources.json (SHA-256 pinned)
#   ERHAI_REPO/packaging/sensors/rom/    stock sensor configuration, checked against
#                             packaging/opd2413-sensors/rom-config.json (vendor files: read from
#                             the erhai checkout, never copied into this repository)
# Output: out/rpmbuild/RPMS/aarch64/opd2413-sensors-VERSION-RELEASE.aarch64.rpm and a build log.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=tools/tablet-build-common.sh
source "$repo/tools/tablet-build-common.sh"

opd_parse_build_target "$@"
set -- "${OPD_ARGS[@]+"${OPD_ARGS[@]}"}"

ver=${1:?version}; rel=${2:?release}; erhai=$(realpath -e "${3:?erhai repo (onepluspad-2pro-mainline)}")
S=$repo/packaging/opd2413-sensors
src=$repo/out/sensors/src; work=$repo/out/sensors/work; rpms=$repo/out/rpmbuild/RPMS/aarch64
image=${FEDORA_IMAGE:-registry.fedoraproject.org/fedora:45}
cache=$repo/out/m3k/dnf-cache
jobs=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))
mkdir -p "$src" "$work" "$rpms" "$cache"

python3 - "$S" "$src" "$erhai/packaging/sensors" <<'EOF'
import hashlib, json, os, sys, urllib.request
S, src, rom = sys.argv[1:4]
h = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
lock = json.load(open(os.path.join(S, 'sources.json')))
for s in lock['sources']:
    a = os.path.join(src, s['archive'])
    if not os.path.exists(a):
        urllib.request.urlretrieve(s['url'], a)
    if h(a) != s['sha256']:
        sys.exit(f'{a}: SHA-256 mismatch')
    for p in s['patches']:
        f = os.path.join(S, 'patches', os.path.relpath(p['file'], 'patches'))
        if h(f) != p['sha256']:
            sys.exit(f'{f}: SHA-256 mismatch')
romcfg = json.load(open(os.path.join(S, 'rom-config.json')))
for e in romcfg['files']:
    f = os.path.join(rom, e['file'])
    if os.path.getsize(f) != e['size'] or h(f) != e['sha256']:
        sys.exit(f'{f}: does not match rom-config.json')
print(f"inputs verified: {len(lock['sources'])} sources, {len(romcfg['files'])} ROM files")
EOF

builder="localhost/opd2413-builder-sensors:fc45"
setup_cmd='dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True install \
    gcc meson ninja-build pkgconf-pkg-config patch tar bzip2 gzip python3 python3-devel rpm-build \
    glib2-devel libgudev-devel polkit-devel protobuf-c-devel protobuf-c-compiler libqmi-devel systemd-devel >/dev/null'

build_cmd=$(cat <<'BUILD'
P=/usr/libexec/opd2413-sensors
lock=/repo/packaging/opd2413-sensors/sources.json
rm -rf /build; mkdir -p /build/tree /build/stage
field() { python3 -c "import json,sys;s=[x for x in json.load(open(\"$lock\"))[\"sources\"] if x[\"name\"]==sys.argv[1]][0];print(s[sys.argv[2]])" "$1" "$2"; }
patches() { python3 -c "import json,sys;s=[x for x in json.load(open(\"$lock\"))[\"sources\"] if x[\"name\"]==sys.argv[1]][0];print(\" \".join(p[\"file\"] for p in s[\"patches\"]))" "$1"; }
prep() { tar -xf /repo/out/sensors/src/$(field $1 archive) -C /build/tree
         for p in $(patches $1); do patch -d /build/tree/$(field $1 directory) -p1 --batch --fuzz=0 -i /repo/packaging/opd2413-sensors/$p; done; }
setup() { meson setup "$1" "$2" --prefix=$P --libdir=lib --bindir=bin --libexecdir=libexec \
          --buildtype=release --wrap-mode=nofallback -Dc_link_args=-Wl,-rpath,$P/lib "${@:3}"; }
export CFLAGS="-O2 -g0 -ffile-prefix-map=/build/tree=."
prep hexagonrpc; setup /build/hex /build/tree/$(field hexagonrpc directory)
meson compile -C /build/hex -j $JOBS; meson test -C /build/hex --print-errorlogs
meson install -C /build/hex --no-rebuild --destdir /build/stage
prep libssc; setup /build/ssc /build/tree/$(field libssc directory)
meson compile -C /build/ssc -j $JOBS; /build/ssc/tests/tests-delivery
meson install -C /build/ssc --no-rebuild; meson install -C /build/ssc --no-rebuild --destdir /build/stage
prep iio-sensor-proxy
PKG_CONFIG_PATH=$P/lib/pkgconfig setup /build/isp /build/tree/$(field iio-sensor-proxy directory) \
    -Dssc-support=enabled -Dudevrulesdir=$P/unused/udev -Dsystemdsystemunitdir=$P/unused/systemd
meson compile -C /build/isp -j $JOBS
meson install -C /build/isp --no-rebuild --destdir /build/stage
rpmbuild -bb --define "_topdir /build/rpm" --define "pkgver $VER" --define "pkgrel $REL" \
    --define "stagedir /build/stage" --define "srcdir /repo/packaging/opd2413-sensors" \
    --define "romdir /erhai/packaging/sensors" /repo/packaging/opd2413-sensors/opd2413-sensors.spec
cp /build/rpm/RPMS/aarch64/*.rpm /work/
BUILD
)

if [ "$OPD_BUILD_TARGET" = "tablet" ]; then
    opd_check_tablet_ssh "$repo"
    rwork="/tmp/opd-build-sensors-$$"
    cleanup_remote() {
        opd_tablet_ssh "$repo" "rm -rf '$rwork'" >/dev/null 2>&1 || true
    }
    trap cleanup_remote EXIT

    opd_tablet_ssh "$repo" "rm -rf '$rwork' && mkdir -p '$rwork/pkg' '$rwork/src_tar' '$rwork/erhai_sensors' '$rwork/work'"
    tar -cf - -C "$S" . | opd_tablet_ssh "$repo" "tar -xf - -C '$rwork/pkg'"
    tar -cf - -C "$src" . | opd_tablet_ssh "$repo" "tar -xf - -C '$rwork/src_tar'"
    tar -cf - -C "$erhai/packaging/sensors" . | opd_tablet_ssh "$repo" "tar -xf - -C '$rwork/erhai_sensors'"

    if ! {
        declare -f opd_ensure_cached_image
        cat <<'REMOTE'
rpm -q podman >/dev/null 2>&1 || dnf -y --setopt=install_weak_deps=False install podman >/dev/null
opd_ensure_cached_image "" "$BUILDER" "$IMAGE" "/var/tmp/opd2413-dnf-cache" "$SETUP_CMD"
JOBS=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))
systemd-inhibit --what=idle:sleep --who=opd2413-build --why="Build opd2413-sensors RPM" \
    podman run --rm --network host \
        -v "$RWORK/pkg:/repo/packaging/opd2413-sensors:ro,Z" \
        -v "$RWORK/src_tar:/repo/out/sensors/src:ro,Z" \
        -v "$RWORK/erhai_sensors:/erhai/packaging/sensors:ro,Z" \
        -v "$RWORK/work:/work:Z" \
        -e VER="$VER" -e REL="$REL" -e JOBS="$JOBS" \
        "$BUILDER" bash -euxc "$BUILD_CMD"
REMOTE
    } | opd_tablet_ssh "$repo" "env VER=$(printf '%q' "$ver") REL=$(printf '%q' "$rel") RWORK=$(printf '%q' "$rwork") BUILDER=$(printf '%q' "$builder") IMAGE=$(printf '%q' "$image") SETUP_CMD=$(printf '%q' "$setup_cmd") BUILD_CMD=$(printf '%q' "$build_cmd") OPD_REBUILD_IMAGE=$(printf '%q' "$OPD_REBUILD_IMAGE") bash -euxs" > "$work/build-$ver-$rel.log" 2>&1; then
        tail -40 "$work/build-$ver-$rel.log"
        exit 1
    fi

    opd_tablet_ssh "$repo" "tar -cf - -C '$rwork/work' ." | tar -xf - -C "$work"
else
    opd_ensure_cached_image "--arch arm64" "$builder" "$image" "$cache" "$setup_cmd"

    podman run --rm --arch arm64 --network host \
        -v "$repo:/repo:ro,Z" -v "$erhai:/erhai:ro,Z" -v "$work:/work:Z" \
        -e VER="$ver" -e REL="$rel" -e JOBS="$jobs" \
        "$builder" bash -euxc "$build_cmd" > "$work/build-$ver-$rel.log" 2>&1 || { tail -40 "$work/build-$ver-$rel.log"; exit 1; }
fi

cp "$work/opd2413-sensors-$ver-$rel.aarch64.rpm" "$rpms/"
sha256sum "$rpms/opd2413-sensors-$ver-$rel.aarch64.rpm"
