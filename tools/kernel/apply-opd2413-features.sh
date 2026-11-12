#!/bin/bash
# Apply the M3 feature patches (kernel/opd2413-7.2/patches/series) to a tree prepared by
# tools/kernel/apply-armada-series.sh, every patch strictly (patch -F0, all hunks must apply).
# Usage: apply-opd2413-features.sh TREE [LAST]   (LAST: stop after this patch number, e.g. 2001)
# Config fragments for the same features are in kernel/opd2413-7.2/config/ (see README there).
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
tree=$(realpath -e "${1:?tree with the 7.2.15 base applied}"); last=${2:-9999}
P=$repo/kernel/opd2413-7.2/patches
cd "$tree"
grep -q '^SUBLEVEL = 15$' Makefile || { echo 'not Linux 7.2.15' >&2; exit 1; }
n=0
while IFS= read -r line; do
    line="${line%%#*}"; line="${line## }"; line="${line%% *}"; [ -z "$line" ] && continue
    [ "${line%%-*}" -gt "$last" ] && break
    log=$(mktemp); expected=$(grep -c '^@@ ' "$P/$line" || true)
    if ! patch -p1 --batch --forward -F0 --dry-run --verbose < "$P/$line" > "$log" 2>&1 ||
       [ "$(grep -c '^Hunk #[0-9].*succeeded' "$log")" -ne "$expected" ]; then
        cat "$log"; rm -f "$log"; echo "FAILED: $line" >&2; exit 1
    fi
    rm -f "$log"
    patch -p1 --batch --forward -F0 --no-backup-if-mismatch --quiet < "$P/$line"
    n=$((n + 1))
done < "$P/series"
if [ -n "$(find . -path ./.git -prune -o \( -name '*.rej' -o -name '*.orig' \) -print -quit)" ]; then
    echo 'stray .rej/.orig files' >&2; exit 1
fi
echo "OK: $n feature patches applied"
