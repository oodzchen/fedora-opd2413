#!/bin/bash
# Build opd2413-face (aarch64) RPM in a Fedora 45 aarch64 container.
#
#   tools/build-face-rpm.sh [VERSION] [RELEASE]
#
# Outputs: out/rpmbuild/RPMS/aarch64/opd2413-face-VERSION-RELEASE.fc45.aarch64.rpm
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
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

rm -rf "$work/rpm" && mkdir -p "$work/rpm"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

podman run --rm --arch arm64 --network host \
    -v "$repo:/repo:ro,Z" -v "$work:/work:Z" -v "$models:/models:ro,Z" -v "$cache:/var/cache/libdnf5:Z" \
    -e VER="$ver" -e REL="$rel" -e JOBS="$jobs" \
    "$image" bash -euxc '
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True install \
    rpm-build gcc make cmake ninja-build pkgconf-pkg-config pam-devel systemd-devel \
    qt6-qtbase-devel qt6-qtdeclarative-devel selinux-policy-devel checkpolicy \
    policycoreutils python3 authselect >/dev/null
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
sha256sum "$rpms/opd2413-face-${ver}-${rel}."*.rpm
