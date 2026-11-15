#!/bin/bash
# Build customized Fedora 45 libcamera aarch64 RPMs for OPD2413 in a container.
#
#   tools/build-libcamera-rpm.sh [OPDREL]
#
# Outputs: out/rpmbuild/RPMS/aarch64/{libcamera,libcamera-ipa,libcamera-tools,
#          libcamera-devel,libcamera-gstreamer,libcamera-qcam,libcamera-v4l2,
#          python3-libcamera}-0.7.2-5.*.opd2413.*.aarch64.rpm
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
opdrel=${1:-1}
S=$repo/packaging/opd2413-libcamera
src=$repo/out/libcamera/src
work=$repo/out/libcamera/work
rpms=$repo/out/rpmbuild/RPMS/aarch64
srpms=$repo/out/rpmbuild/SRPMS
image=${FEDORA_IMAGE:-registry.fedoraproject.org/fedora:45}
cache=$repo/out/m3k/dnf-cache
jobs=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))

mkdir -p "$src" "$work" "$rpms" "$srpms" "$cache"

python3 - "$S" "$src" <<'EOF'
import hashlib, json, os, sys, urllib.request
S, src = sys.argv[1:3]
cfg = json.load(open(os.path.join(S, "sources.json")))["tarball"]
dst = os.path.join(src, cfg["filename"])
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
if not os.path.exists(dst):
    print(f"Downloading {cfg['url']}...")
    urllib.request.urlretrieve(cfg["url"], dst)
if h(dst) != cfg["sha256"]:
    sys.exit(f"{dst}: SHA-256 mismatch (expected {cfg['sha256']}, got {h(dst)})")
print(f"Verified source tarball: {cfg['filename']}")
EOF

rm_flag=${REUSE_BUILD:-0}
if [[ "$rm_flag" != "1" || ! -d "$work/rpm/BUILD" ]]; then
    rm -rf "$work/rpm" && mkdir -p "$work/rpm"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
    noprep_flag=""
else
    mkdir -p "$work/rpm"/{RPMS,SOURCES,SPECS,SRPMS}
    noprep_flag="--noprep"
fi
cp "$src"/libcamera-v0.7.2.tar.bz2 "$work/rpm/SOURCES/"
cp "$S"/files/* "$S"/patches/*.patch "$work/rpm/SOURCES/"
cp "$S/libcamera.spec" "$work/rpm/SPECS/"

podman run --rm --arch arm64 --network host \
    -v "$work:/work:Z" -v "$cache:/var/cache/libdnf5:Z" \
    -e OPDREL="$opdrel" -e JOBS="$jobs" -e NOPREP="$noprep_flag" \
    "$image" bash -euxc '
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True install \
    rpm-build dnf5-plugins patch tar bzip2 >/dev/null
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True builddep \
    /work/rpm/SPECS/libcamera.spec >/dev/null
rpmbuild -ba ${NOPREP} \
    --with container_check \
    --define "_topdir /work/rpm" \
    --define "opdrel ${OPDREL}" \
    --define "_smp_mflags -j${JOBS}" \
    /work/rpm/SPECS/libcamera.spec
' > "$work/build-${opdrel}.log" 2>&1 || { tail -60 "$work/build-${opdrel}.log"; exit 1; }

cp -f "$work/rpm/RPMS/aarch64/"*.rpm "$rpms/"
cp -f "$work/rpm/SRPMS/"*.src.rpm "$srpms/"
ls -la "$work/rpm/RPMS/aarch64/"
