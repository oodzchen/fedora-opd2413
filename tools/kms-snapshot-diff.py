#!/usr/bin/env python3
"""Compare two msm display register snapshots (/sys/kernel/debug/dri/0/kms).

The snapshot lists blocks as "=====name=====" followed by lines
"0xOFFSET : word word word word". Prints, per block, the registers whose
values differ, and the blocks present in only one snapshot.

Usage: kms-snapshot-diff.py A B [--block REGEX] [--max N]
"""
import argparse
import re
import sys

HEADER = re.compile(r'^=+([^=]+?)=+$')
ROW = re.compile(r'^0x([0-9a-f]+)\s*:\s*((?:[0-9a-f]{8}\s*)+)$')


def parse(path):
    blocks, name = {}, None
    with open(path, encoding='ascii', errors='replace') as f:
        for line in f:
            line = line.strip()
            m = HEADER.match(line)
            if m:
                name = m.group(1).strip()
                blocks.setdefault(name, {})
                continue
            m = ROW.match(line)
            if m and name:
                base = int(m.group(1), 16)
                for i, word in enumerate(m.group(2).split()):
                    blocks[name][base + 4 * i] = int(word, 16)
    return blocks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--block', default='.', help='only blocks matching this regex')
    ap.add_argument('--max', type=int, default=40, help='registers shown per block')
    args = ap.parse_args()
    a, b = parse(args.a), parse(args.b)
    pick = re.compile(args.block)
    for name in sorted(set(a) | set(b)):
        if not pick.search(name):
            continue
        if name not in a or name not in b:
            print(f'{name}: only in {"A" if name in a else "B"}')
            continue
        diff = [(off, a[name].get(off), b[name].get(off))
                for off in sorted(set(a[name]) | set(b[name]))
                if a[name].get(off) != b[name].get(off)]
        if not diff:
            continue
        print(f'{name}: {len(diff)} registers differ')
        for off, va, vb in diff[:args.max]:
            fa = '--------' if va is None else f'{va:08x}'
            fb = '--------' if vb is None else f'{vb:08x}'
            print(f'  0x{off:04x}  {fa} -> {fb}')
        if len(diff) > args.max:
            print(f'  ... {len(diff) - args.max} more')
    return 0


if __name__ == '__main__':
    sys.exit(main())
