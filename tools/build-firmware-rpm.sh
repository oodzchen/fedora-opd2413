#!/bin/bash
# Build opd2413-firmware from local firmware trees.
# Usage: build-firmware-rpm.sh FWVER PKGREL FIRMWARE_ROOT...
# Each FIRMWARE_ROOT is laid out like /usr/lib/firmware. Every manifest entry is
# taken from the first root that has it and must match its SHA-256; files not in
# the manifest are never packaged.
set -euo pipefail

fwver=${1:?firmware version, e.g. the OTA date}
pkgrel=${2:?package release}
shift 2
[ "$#" -gt 0 ] || { echo "need at least one firmware root" >&2; exit 2; }
repo=$(cd "$(dirname "$0")/.." && pwd)
manifest=${repo}/packaging/opd2413-firmware/manifest.sha256
top=${repo}/out/rpmbuild
stage=${repo}/out/firmware-stage

rm -rf "${stage}"
mkdir -p "${stage}" "${top}/SOURCES"
while read -r digest path; do
    case "${digest}" in ''|'#'*) continue ;; esac
    found=
    for root in "$@"; do
        if [ -f "${root}/${path}" ]; then found=${root}/${path}; break; fi
    done
    [ -n "${found}" ] || { echo "missing firmware: ${path}" >&2; exit 1; }
    install -D -m 0644 "${found}" "${stage}/${path}"
done < "${manifest}"
(cd "${stage}" && grep -v '^#' "${manifest}" | sha256sum --quiet --check -)

cp "${manifest}" "${top}/SOURCES/"
rpmbuild -bb \
    --define "_topdir ${top}" \
    --define "fwver ${fwver}" \
    --define "pkgrel ${pkgrel}" \
    --define "fw_tree ${stage}" \
    "${repo}/packaging/opd2413-firmware/opd2413-firmware.spec" >"${top}/firmware-build.log" 2>&1 \
    || { tail -20 "${top}/firmware-build.log" >&2; exit 1; }
find "${top}/RPMS" -name "opd2413-firmware-${fwver}-${pkgrel}.*.rpm" -exec sha256sum {} +
