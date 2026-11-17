#!/bin/bash
# Build customized Fedora 45 libinput aarch64 RPMs natively on the tablet
# (--local when already running on the tablet or in a local aarch64 container,
# or --tablet over private/ssh.sh from a host workstation).
#
#   tools/build-libinput-rpm.sh [--local|--tablet] [--rebuild-image] [OPDREL]
#
# Outputs: out/rpmbuild/RPMS/aarch64/libinput*-1.32.0-1.fc45.opd2413.*.aarch64.rpm
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=tools/tablet-build-common.sh
source "$repo/tools/tablet-build-common.sh"

opd_parse_build_target "$@"
set -- "${OPD_ARGS[@]+"${OPD_ARGS[@]}"}"

# Default to --local when invoked directly on the aarch64 tablet without private/ssh.sh.
if [ "$OPD_BUILD_TARGET" = "tablet" ] && [ "$(uname -m)" = "aarch64" ] && [ ! -e "$repo/private/ssh.sh" ]; then
    OPD_BUILD_TARGET=local
fi

opdrel=${1:-1}
S=$repo/packaging/opd2413-libinput
src=$repo/out/libinput/src
work=$repo/out/libinput/work
rpms=$repo/out/rpmbuild/RPMS/aarch64
srpms=$repo/out/rpmbuild/SRPMS
image=${FEDORA_IMAGE:-registry.fedoraproject.org/fedora:45}
cache=$repo/out/libinput/dnf-cache
jobs=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))

mkdir -p "$src" "$work" "$rpms" "$srpms" "$cache"

python3 - "$S" "$src" <<'EOF'
import hashlib, json, os, subprocess, sys
S, src = sys.argv[1:3]
cfg = json.load(open(os.path.join(S, "sources.json")))["tarball"]
dst = os.path.join(src, cfg["filename"])
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
if not os.path.exists(dst):
    print(f"Downloading {cfg['url']}...")
    subprocess.run(["curl", "-fL", "--retry", "3", "-o", dst, cfg["url"]], check=True)
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
cp "$src"/libinput-1.32.0.tar.bz2 "$work/rpm/SOURCES/"
cp "$S"/patches/*.patch "$work/rpm/SOURCES/"
cp "$S/libinput.spec" "$work/rpm/SPECS/"

spec_hash=$(grep -E '^Build(Requires|Conflicts):' "$S/libinput.spec" | sha256sum | awk '{print $1}')
builder="localhost/opd2413-builder-libinput:fc45"
setup_cmd="dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True install \
    rpm-build dnf5-plugins patch tar xz bzip2 git-core >/dev/null && \
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True builddep \
    /tmp/spec/libinput.spec >/dev/null && \
printf '%s\n' '${spec_hash}' > /etc/opd-builddep.sha256"

if [ "$OPD_BUILD_TARGET" = "tablet" ]; then
    opd_check_tablet_ssh "$repo"
    if [ "$rm_flag" = "1" ]; then
        rwork="/var/tmp/opd-build-libinput"
    else
        rwork="/tmp/opd-build-libinput-$$"
        cleanup_remote() {
            opd_tablet_ssh "$repo" "rm -rf '$rwork'" >/dev/null 2>&1 || true
        }
        trap cleanup_remote EXIT
    fi

    opd_tablet_ssh "$repo" "REUSE='$rm_flag' RWORK='$rwork' bash -euc '
if [ \"\$REUSE\" != \"1\" ]; then
    rm -rf \"\$RWORK\"
fi
mkdir -p \"\$RWORK/rpm\"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
rm -rf \"\$RWORK/rpm/RPMS/aarch64/\"* \"\$RWORK/rpm/SRPMS/\"*
'"
    tar -cf - -C "$work/rpm" SOURCES SPECS | opd_tablet_ssh "$repo" "tar -xf - -C '$rwork/rpm'"

    if ! {
        declare -f opd_ensure_cached_image
        cat <<'REMOTE'
rpm -q podman >/dev/null 2>&1 || dnf -y --setopt=install_weak_deps=False install podman >/dev/null
if [ "$OPD_REBUILD_IMAGE" != "1" ] && podman image exists "$BUILDER" >/dev/null 2>&1; then
    img_hash=$(podman run --rm "$BUILDER" cat /etc/opd-builddep.sha256 2>/dev/null || true)
    [ "$img_hash" = "$SPEC_HASH" ] || OPD_REBUILD_IMAGE=1
fi
opd_ensure_cached_image "" "$BUILDER" "$IMAGE" "/var/tmp/opd2413-dnf-cache" "$SETUP_CMD" "-v $RWORK/rpm/SPECS:/tmp/spec:ro,Z"
NOPREP=""
if [ "$REUSE" = "1" ] && [ -n "$(ls -A "$RWORK/rpm/BUILD" 2>/dev/null || true)" ]; then
    NOPREP="--noprep"
fi
JOBS=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))
systemd-inhibit --what=idle:sleep --who=opd2413-build --why="Build opd2413-libinput RPM" \
    podman run --rm --network host \
        -v "$RWORK:/work:Z" \
        -e OPDREL="$OPDREL" -e JOBS="$JOBS" -e NOPREP="$NOPREP" \
        "$BUILDER" bash -euxc '
rpmbuild -ba ${NOPREP} \
    --define "_topdir /work/rpm" \
    --define "opdrel ${OPDREL}" \
    --define "_smp_mflags -j${JOBS}" \
    /work/rpm/SPECS/libinput.spec
'
REMOTE
    } | opd_tablet_ssh "$repo" "env OPDREL=$(printf '%q' "$opdrel") REUSE=$(printf '%q' "$rm_flag") RWORK=$(printf '%q' "$rwork") BUILDER=$(printf '%q' "$builder") IMAGE=$(printf '%q' "$image") SPEC_HASH=$(printf '%q' "$spec_hash") SETUP_CMD=$(printf '%q' "$setup_cmd") OPD_REBUILD_IMAGE=$(printf '%q' "$OPD_REBUILD_IMAGE") bash -euxs" > "$work/build-${opdrel}.log" 2>&1; then
        tail -60 "$work/build-${opdrel}.log"
        exit 1
    fi

    opd_tablet_ssh "$repo" "tar -cf - -C '$rwork/rpm/RPMS/aarch64' ." | tar -xf - -C "$rpms"
    opd_tablet_ssh "$repo" "tar -cf - -C '$rwork/rpm/SRPMS' ." | tar -xf - -C "$srpms"
    ls -la "$rpms"/libinput*-1.32.0-1.*.opd2413."${opdrel}".*.rpm
else
    if [ "$OPD_REBUILD_IMAGE" != "1" ] && podman image exists "$builder" >/dev/null 2>&1; then
        img_hash=$(podman run --rm --arch arm64 "$builder" cat /etc/opd-builddep.sha256 2>/dev/null || true)
        [ "$img_hash" = "$spec_hash" ] || OPD_REBUILD_IMAGE=1
    fi
    opd_ensure_cached_image "--arch arm64" "$builder" "$image" "$cache" "$setup_cmd" "-v $work/rpm/SPECS:/tmp/spec:ro,Z"

    systemd-inhibit --what=idle:sleep --who=opd2413-build --why="Build opd2413-libinput RPM" \
        podman run --rm --arch arm64 --network host \
            -v "$work:/work:Z" \
            -e OPDREL="$opdrel" -e JOBS="$jobs" -e NOPREP="$noprep_flag" \
            "$builder" bash -euxc '
    rpmbuild -ba ${NOPREP} \
        --define "_topdir /work/rpm" \
        --define "opdrel ${OPDREL}" \
        --define "_smp_mflags -j${JOBS}" \
        /work/rpm/SPECS/libinput.spec
    ' > "$work/build-${opdrel}.log" 2>&1 || { tail -60 "$work/build-${opdrel}.log"; exit 1; }

    cp -f "$work/rpm/RPMS/aarch64/"*.rpm "$rpms/"
    cp -f "$work/rpm/SRPMS/"*.src.rpm "$srpms/"
    ls -la "$rpms"/libinput*-1.32.0-1.*.opd2413."${opdrel}".*.rpm
fi
