#!/usr/bin/env python3
"""pick.py FILE CHOICES  -- resolve conflict hunks in order.
CHOICES: string of o (ours/fedora), t (theirs/erhai), b (ours then theirs), B (theirs then ours);
a single letter applies to every hunk."""
import sys, re
path, choices = sys.argv[1], sys.argv[2]
lines = open(path, encoding='utf-8', errors='surrogateescape').read().split('\n')
out, i, n = [], 0, 0
while i < len(lines):
    if lines[i].startswith('<<<<<<< '):
        o, t, j = [], [], i + 1
        while not lines[j].startswith('======='): o.append(lines[j]); j += 1
        j += 1
        while not lines[j].startswith('>>>>>>> '): t.append(lines[j]); j += 1
        c = choices[n] if len(choices) > 1 else choices
        out += {'o': o, 't': t, 'b': o + t, 'B': t + o}[c]
        n += 1; i = j + 1
    else:
        out.append(lines[i]); i += 1
if len(choices) > 1 and len(choices) != n:
    sys.exit(f'{path}: {n} hunks, {len(choices)} choices; file unchanged')
open(path, 'w', encoding='utf-8', errors='surrogateescape').write('\n'.join(out))
print(f'{path}: resolved {n} hunks')
