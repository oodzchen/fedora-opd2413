#!/usr/bin/env python3
"""mod2config.py KTREE MODNAMES... -> 'modname path CONFIG_SYMBOL builtin|module'"""
import sys, os, re
tree = sys.argv[1]
names = set(n.replace('-', '_') for n in sys.argv[2:])
paths = {}
for f, kind in (('modules.builtin', 'builtin'), ('modules.order', 'module')):
    for l in open(os.path.join(tree, f)):
        p = l.strip()
        p = re.sub(r'^kernel/', '', p).replace('.ko', '.o')
        paths[os.path.basename(p)[:-2].replace('-', '_')] = (p, kind)
def config_for(objpath):
    d, o = os.path.split(objpath)
    mk = os.path.join(tree, d, 'Makefile')
    if not os.path.exists(mk): mk = os.path.join(tree, d, 'Kbuild')
    if not os.path.exists(mk): return '?'
    text = open(mk).read().replace('\\\n', ' ')
    for m in re.finditer(r'obj-\$\((CONFIG_\w+)\)\s*[+:]?=\s*([^\n]*)', text):
        if re.search(r'(^|\s)' + re.escape(o) + r'(\s|$)', m.group(2)):
            return m.group(1)
    return '?'
for n in sorted(names):
    if n not in paths: print(n, '-', '?', 'unknown'); continue
    p, kind = paths[n]
    print(n, p, config_for(p), kind)
