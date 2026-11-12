#!/bin/bash
# Apply kernel/armada-7.2.6 (series, board DTS) and kernel/opd2413 (1411, 1412) to a
# Linux 7.2.15 source tree, every patch strictly (patch -F0, all hunks must apply).
# Usage: apply-armada-series.sh TREE        (TREE: clean Linux 7.2.15, e.g. a git work tree)
# Differences from the 7.2.6 series are listed in kernel/opd2413-7.2/README.md:
# refreshed copies replace three patches; 0048a is already upstream in 7.2.15.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
tree=$(realpath -e "${1:?Linux 7.2.15 tree}")
A=$repo/kernel/armada-7.2.6; F=$repo/kernel/opd2413-7.2/refreshed
cd "$tree"
grep -q '^SUBLEVEL = 15$' Makefile || { echo 'not Linux 7.2.15' >&2; exit 1; }
strict() {  # PATCH
    local log expected
    log=$(mktemp); expected=$(grep -c '^@@ ' "$1" || true)
    patch -p1 --batch --forward -F0 --dry-run --verbose < "$1" > "$log" 2>&1 &&
        [ "$(grep -c '^Hunk #[0-9].*succeeded' "$log")" -eq "$expected" ] || { cat "$log"; rm -f "$log"; return 1; }
    rm -f "$log"
    patch -p1 --batch --forward -F0 --no-backup-if-mismatch --quiet < "$1"
}
while IFS= read -r line; do
    line="${line%%#*}"; line="${line## }"; line="${line%% *}"; [ -z "$line" ] && continue
    case $line in
    0048a-*) patch -p1 --batch -R -F0 --dry-run < "$A/patches/$line" > /dev/null; continue ;;
    esac
    p=$A/patches/$line; [ -f "$F/$line" ] && p=$F/$line
    strict "$p" || { echo "FAILED: $line" >&2; exit 1; }
done < "$A/patches/series"
T=arch/arm64/boot/dts/qcom
cp "$A"/dts/*.dts "$A"/dts/*.dtsi "$T/"
for p in "$A"/dts/*.patch; do patch -p1 -F0 --no-backup-if-mismatch -s < "$p"; done
grep -q '# armada-kernel DTBs' "$T/Makefile" || printf '\n# armada-kernel DTBs\n' >> "$T/Makefile"
for d in "$A"/dts/*.dts; do
    b=$(basename "$d" .dts)
    grep -qE "(^|[[:space:]])$b\.dtb([[:space:]]|$)" "$T/Makefile" || echo "dtb-\$(CONFIG_ARCH_QCOM) += $b.dtb" >> "$T/Makefile"
done
for p in "$repo"/kernel/opd2413/1411-*.patch "$repo"/kernel/opd2413/1412-*.patch; do strict "$p"; done
if [ -n "$(find . -path ./.git -prune -o \( -name '*.rej' -o -name '*.orig' \) -print -quit)" ]; then
    echo 'stray .rej/.orig files' >&2; exit 1
fi
echo "OK: Armada series (301 patches), board DTS, 1411, 1412 applied to $(make -s kernelversion)"
