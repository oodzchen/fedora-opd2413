#!/usr/bin/env python3
"""fixdeps.py SRC BUILD FRAGMENT K3CONFIG: print the parent symbols to add as =y.
For every symbol the fragment wants =y but the build config has =m, collect the
identifiers in its 'depends on' lines and in the 'if'/'menuconfig' blocks around
it, and keep those that are =y in kernel 3 and =m in the build config."""
import sys, re, os, glob
src, build, frag, k3 = sys.argv[1:5]
def load(p):
    d = {}
    for l in open(p):
        m = re.match(r'^(CONFIG_\w+)=(.*)$', l)
        if m: d[m.group(1)[7:]] = m.group(2)
    return d
want = {}
for l in open(frag):
    m = re.match(r'^CONFIG_(\w+)=y', l)
    if m: want[m.group(1)] = 'y'
got, k = load(os.path.join(build, '.config')), load(k3)
# index Kconfig: symbol -> list of dependency identifiers (depends + enclosing if/menu deps)
deps = {}
for f in glob.glob(os.path.join(src, '**', 'Kconfig*'), recursive=True):
    try: lines = open(f, errors='replace').read().split('\n')
    except Exception: continue
    ifstack, cur, menudeps = [], None, []
    for l in lines:
        s = l.strip()
        m = re.match(r'^(menu)?config\s+(\w+)', s)
        if m:
            cur = m.group(2); deps.setdefault(cur, set()).update(*ifstack) if ifstack else deps.setdefault(cur, set())
            if m.group(1): menudeps.append(cur)
            continue
        m = re.match(r'^if\s+(.*)', s)
        if m: ifstack.append(set(re.findall(r'[A-Z][A-Z0-9_]+', m.group(1)))); cur = None; continue
        if s == 'endif' and ifstack: ifstack.pop(); cur = None; continue
        m = re.match(r'^depends on\s+(.*)', s)
        if m and cur: deps[cur].update(re.findall(r'[A-Z][A-Z0-9_]+', m.group(1)))
add = set()
for s in want:
    if got.get(s) == 'm':
        for d in deps.get(s, ()):
            if k.get(d) == 'y' and got.get(d) == 'm': add.add(d)
for a in sorted(add): print(f'CONFIG_{a}=y')
