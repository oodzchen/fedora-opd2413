#!/bin/bash
# Shared helpers for OPD2413 ARM64 userspace RPM builds (tablet-native by default,
# with optional --local host-container fallback).
#
# Never store device IPs, MACs, serials, or host user paths here; all tablet SSH
# calls go through "$repo/private/ssh.sh" with OPD_OS=fedora.

opd_parse_build_target() {
    OPD_BUILD_TARGET=${OPD_BUILD_TARGET:-tablet}
    OPD_REBUILD_IMAGE=${OPD_REBUILD_IMAGE:-0}
    OPD_ARGS=()
    for arg in "$@"; do
        case "$arg" in
            --local)
                OPD_BUILD_TARGET=local
                ;;
            --tablet)
                OPD_BUILD_TARGET=tablet
                ;;
            --rebuild-image)
                OPD_REBUILD_IMAGE=1
                ;;
            *)
                OPD_ARGS+=("$arg")
                ;;
        esac
    done
    export OPD_BUILD_TARGET OPD_REBUILD_IMAGE
}

opd_tablet_ssh() {
    local repo=$1
    shift
    OPD_OS="${OPD_OS:-fedora}" bash "$repo/private/ssh.sh" "$@"
}

opd_check_tablet_ssh() {
    local repo=$1
    local probe_out=""
    if ! probe_out=$(opd_tablet_ssh "$repo" '
        set -e
        arch=$(uname -m)
        if [ "$arch" != "aarch64" ]; then
            echo "BAD_ARCH:$arch"
            exit 2
        fi
        low_batt=""
        batt_info=""
        for d in /sys/class/power_supply/*; do
            [ -r "$d/capacity" ] || continue
            cap=$(cat "$d/capacity" 2>/dev/null || true)
            st=$(cat "$d/status" 2>/dev/null || echo Unknown)
            batt_info="${batt_info}${batt_info:+ }${cap}%(${st})"
            if [ -n "$cap" ] && [ "$cap" -lt 15 ] && [ "$st" = "Discharging" ]; then
                low_batt="${cap}% ${st}"
            fi
        done
        if [ -n "$low_batt" ]; then
            echo "LOW_BATT:$low_batt"
            exit 3
        fi
        jobs=$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))
        echo "OK arch=$arch jobs=$jobs batt=${batt_info:-unknown}"
    ' 2>&1); then
        echo "ERROR: Tablet unreachable or not ready via private/ssh.sh (OPD_OS=${OPD_OS:-fedora})." >&2
        echo "Detail: $probe_out" >&2
        echo "Hint: Wake the tablet Fedora screen/Wi-Fi, ensure >=15% battery (or charging), or pass --local for host-container fallback." >&2
        return 1
    fi
    echo "Tablet build target ready: $probe_out"
}

opd_ensure_cached_image() {
    local arch_flag=$1
    local image_tag=$2
    local base_image=$3
    local cache_dir=$4
    local setup_cmd=$5
    local extra_mount=${6:-}

    if [ "${OPD_REBUILD_IMAGE:-0}" != "1" ] && podman image exists "$image_tag" >/dev/null 2>&1; then
        return 0
    fi
    mkdir -p "$cache_dir"
    local cname="opd-init-$$-$(date +%s)"
    local -a run_args=()
    if [ -n "$arch_flag" ]; then
        # shellcheck disable=SC2206
        run_args+=($arch_flag)
    fi
    if [ -n "$extra_mount" ]; then
        # shellcheck disable=SC2206
        run_args+=($extra_mount)
    fi
    podman rm -f "$cname" >/dev/null 2>&1 || true
    if ! podman run --name "$cname" "${run_args[@]}" --network host \
        -v "$cache_dir:/var/cache/libdnf5:Z" \
        "$base_image" bash -euxc "$setup_cmd"; then
        podman rm -f "$cname" >/dev/null 2>&1 || true
        return 1
    fi
    podman commit "$cname" "$image_tag" >/dev/null
    podman rm -f "$cname" >/dev/null 2>&1 || true
}
