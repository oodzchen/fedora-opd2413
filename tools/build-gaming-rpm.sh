#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PKGVER="${1:-0.1}"
PKGREL="${2:-1}"
TOP="${ROOT}/out/rpmbuild"
SPEC="${ROOT}/packaging/opd2413-gaming/opd2413-gaming.spec"
SRCDIR="${ROOT}/packaging/opd2413-gaming/src"

mkdir -p "${TOP}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

rpmbuild -bb \
    --define "_topdir ${TOP}" \
    --define "pkgver ${PKGVER}" \
    --define "pkgrel ${PKGREL}" \
    --define "srcdir ${SRCDIR}" \
    "${SPEC}"

echo "Built RPM under ${TOP}/RPMS/noarch/"
