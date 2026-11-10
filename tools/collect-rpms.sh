#!/bin/bash
# Collect the one current build of each package into out/rpms, the set that
# gets copied to the tablet and installed with `dnf install ./*.rpm`.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
dest=${repo}/out/rpms
rm -rf "${dest}"
mkdir -p "${dest}"
for name in kernel-opd2413 opd2413-firmware opd2413-device opd2413-audio; do
    mapfile -t found < <(find "${repo}/out/rpmbuild/RPMS" -name "${name}-[0-9]*.rpm")
    [ "${#found[@]}" -eq 1 ] || { echo "expected one ${name} rpm, found ${#found[@]}" >&2; exit 1; }
    cp "${found[0]}" "${dest}/"
done
(cd "${dest}" && sha256sum ./*.rpm | tee SHA256SUMS)
