#!/usr/bin/env python3
"""Offline tests for device/libexec/boot-select (no device, no real ESP).

With the private copies of boot_b and KSHIM.CHO (private/bootflow-*/), also checks
that the codec reproduces the tablet's existing record and that Armada's C decoder
accepts a record written for another manifest. Those cases are skipped without them.
"""
from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import json, os, shutil, struct, subprocess, sys, tempfile, unittest

REPO = Path(__file__).resolve().parent.parent
_loader = SourceFileLoader('boot_select', str(REPO / 'device/libexec/boot-select'))
bs = importlib.util.module_from_spec(importlib.util.spec_from_loader('boot_select', _loader))
_loader.exec_module(bs)
PRIVATE = sorted(REPO.glob('private/bootflow-*/'))
OLD = PRIVATE[-1] / 'boot_b-readonly.img' if PRIVATE else None
CHO = PRIVATE[-1] / 'KSHIM.CHO.before' if PRIVATE else None
NEW = REPO / 'out/bootb-fedora1/read-boot-flash.img'
ARMADA_KSHIM = Path.home() / 'github/armada/porting/oneplus-pad-2-pro/kshim'


def manifest_image(names, timeout=10000):
    """A minimal boot image whose payload declares a manifest like kShimC's packer."""
    m = bytearray(struct.pack('<IHHIII', bs.MAGIC, 0, 1, len(names) + 1, 0, timeout) + bytes(40))
    for name in names + ['Attached Shim']:
        raw = name.encode()
        flags = bs.EXECUTABLE if name != 'Attached Shim' else 0
        entry = struct.pack('<QQIIQIIIQI', 0, 0, 2, flags, 0, 0, 0, 12, 0, len(raw)) + raw
        m += entry + bytes(-len(entry) % 4)
    payload = bytearray(0x100) + m
    struct.pack_into('<QQ', payload, 0x20, 0x100, len(m))
    return b'ANDROID!' + bytes(bs.PAGE - 8) + bytes(payload)


def journal_file(base=0):
    data = bytearray(bs.FILE_SIZE)
    prov = bytearray(bs.PAGE)
    prov[:8] = b'KSHPROV1'
    struct.pack_into('<II', prov, 8, 1, bs.FILE_SIZE)
    prov[16:32] = bytes(range(16))
    struct.pack_into('<QII', prov, 32, 0x1000, bs.PAGE, 2)
    prov[48:64] = b'n' * 16
    struct.pack_into('<I', prov, bs.PAGE - 4, bs.crc(bytes(prov[:bs.PAGE - 4])))
    data[base + 2 * bs.PAGE:base + 3 * bs.PAGE] = prov
    return data


def apply(data, journal, plan):
    slot, page = plan
    data = bytearray(data)
    data[journal.base + slot * bs.PAGE:journal.base + (slot + 1) * bs.PAGE] = page
    return data


class Codec(unittest.TestCase):
    def setUp(self):
        self.a = bs.Manifest(manifest_image(['ColorOS', 'Armada', 'Armada boot menu'], 30000))
        self.b = bs.Manifest(manifest_image(['ColorOS', 'Fedora', 'Fedora boot menu']))

    def test_manifest_parse(self):
        self.assertEqual(self.b.names(), ['ColorOS', 'Fedora', 'Fedora boot menu'])
        self.assertEqual((self.b.timeout_ms, self.b.selectable), (10000, 3))
        with self.assertRaises(ValueError):
            self.b.index('Attached Shim')
        with self.assertRaises(ValueError):
            self.b.index('Armada')

    def test_select_and_alternate_slots(self):
        data = journal_file()
        j = bs.Journal(data)
        self.assertIsNone(j.selected(self.a))
        data = apply(data, j, j.plan(self.a, 'Armada'))
        j = bs.Journal(data)
        self.assertEqual(j.selected(self.a)['name'], 'Armada')
        self.assertIsNone(j.plan(self.a, 'Armada'))           # unchanged choice writes nothing
        slot = j.selected(self.a)['slot']
        data = apply(data, j, j.plan(self.a, 'ColorOS'))
        r = bs.Journal(data).selected(self.a)
        self.assertEqual((r['name'], r['slot'], r['sequence']), ('ColorOS', 1 - slot, 2))

    def test_record_is_bound_to_its_manifest(self):
        data = journal_file()
        j = bs.Journal(data)
        data = apply(data, j, j.plan(self.a, 'Armada'))
        self.assertIsNone(bs.Journal(data).selected(self.b))  # a menu change invalidates the record

    def test_keep_record_of_installed_manifest(self):
        data = journal_file()
        j = bs.Journal(data)
        data = apply(data, j, j.plan(self.a, 'ColorOS'))      # installed boot_b -> ColorOS
        j = bs.Journal(data)
        kept = j.selected(self.a)['slot']
        plan = j.plan(self.b, 'Fedora', keep=self.a)          # new boot_b -> Fedora
        self.assertNotEqual(plan[0], kept)
        j = bs.Journal(apply(data, j, plan))
        self.assertEqual((j.selected(self.a)['name'], j.selected(self.b)['name']), ('ColorOS', 'Fedora'))

    def test_unaligned_base_and_corruption(self):
        data = journal_file(base=512)
        j = bs.Journal(data)
        self.assertEqual(j.base, 512)
        data = apply(data, j, j.plan(self.b, 'Fedora'))
        self.assertEqual(bs.Journal(data).selected(self.b)['name'], 'Fedora')
        broken = bytearray(data)
        broken[512 + 40] ^= 1
        self.assertIsNone(bs.Journal(broken).selected(self.b))
        with self.assertRaises(ValueError):
            bs.Journal(bytes(bs.FILE_SIZE))


@unittest.skipUnless(OLD and OLD.exists() and CHO.exists() and NEW.exists(), 'private images not present')
class RealImages(unittest.TestCase):
    def test_reproduces_tablet_record_and_c_accepts_new_one(self):
        cho = CHO.read_bytes()
        old, new = bs.Manifest(OLD.read_bytes()), bs.Manifest(NEW.read_bytes())
        j = bs.Journal(cho)
        self.assertIsNotNone(j.selected(old))                 # existing record decodes
        self.assertEqual(new.names(), ['ColorOS', 'Fedora', 'Fedora boot menu'])
        self.assertEqual(new.timeout_ms, 10000)
        data = apply(cho, j, j.plan(old, 'ColorOS'))
        j2 = bs.Journal(data)
        data = apply(data, j2, j2.plan(new, 'Fedora', keep=old))
        j3 = bs.Journal(data)
        self.assertEqual((j3.selected(old)['name'], j3.selected(new)['name']), ('ColorOS', 'Fedora'))
        if not (ARMADA_KSHIM / 'choice_journal.h').exists() or not shutil.which('cc'):
            self.skipTest('Armada C decoder not available')
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / 't.c'
            src.write_text('#include <stdio.h>\n#include <stdlib.h>\n#include "choice_journal.h"\n'
                           'int main(int c,char**v){static uint8_t p[CHOICE_BYTES];FILE*f=fopen(v[1],"rb");'
                           'if(fread(p,1,sizeof p,f)!=sizeof p)return 2;uint32_t h[50]={0},n=atoi(v[3]);'
                           'for(unsigned i=0;i<n;i++)h[i]=strtoul(v[4+i],0,10);struct choice_record r={0};'
                           'int ok=choice_latest(p,strtoul(v[2],0,10),h,n,&r);printf("%d %u\\n",ok,r.entry);return 0;}\n')
            subprocess.run(['cc', '-O2', '-I', str(ARMADA_KSHIM), '-o', f'{t}/t', str(src)], check=True)
            pages = Path(t) / 'pages'
            pages.write_bytes(bytes(data[j3.base:j3.base + 2 * bs.PAGE]))
            for m, expect in ((old, 'ColorOS'), (new, 'Fedora')):
                hashes = [str(e[1]) for e in m.entries[:m.selectable]]
                out = subprocess.run([f'{t}/t', str(pages), str(j3.context(m)), str(m.selectable), *hashes],
                                     capture_output=True, text=True, check=True).stdout.split()
                self.assertEqual(out[0], '1')
                self.assertEqual(m.entries[int(out[1])][0], expect)


class LoaderDefault(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        root = Path(self.t.name)
        (root / 'loader/entries').mkdir(parents=True)
        for e in ('fedora-7.2.6-3.opd2413', 'test'):
            (root / 'loader/entries' / f'{e}.conf').write_text('title x\n')
        (root / 'loader/loader.conf').write_text('timeout 3\neditor no\ndefault fedora-*\n')
        self.patch = {'LOADER_CONF': root / 'loader/loader.conf', 'ENTRIES': root / 'loader/entries',
                      'STATE': root / 'state/next.json'}
        self.saved = {k: getattr(bs, k) for k in self.patch}
        for k, v in self.patch.items():
            setattr(bs, k, v)
        self.saved_entry = bs.selected_entry
        bs.selected_entry = lambda: 'test.conf'

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(bs, k, v)
        bs.selected_entry = self.saved_entry
        self.t.cleanup()

    def run_cmd(self, func, **kw):
        func(type('A', (), kw)())

    def test_next_then_restore(self):
        self.run_cmd(bs.cmd_next, entry='test.conf')
        self.assertEqual(bs.loader_default(bs.loader_lines()), 'test.conf')
        self.assertIn('editor no', bs.loader_lines())
        self.run_cmd(bs.cmd_next, entry='test')               # a second next keeps the original default
        self.assertEqual(json.loads(bs.STATE.read_text())['previous_default'], 'fedora-*')
        self.run_cmd(bs.cmd_restore)
        self.assertEqual(bs.loader_default(bs.loader_lines()), 'fedora-*')
        self.assertFalse(bs.STATE.exists())
        self.run_cmd(bs.cmd_restore)                          # nothing pending: no change

    def test_restore_leaves_manual_change(self):
        self.run_cmd(bs.cmd_next, entry='test')
        bs.write_loader_default('other')
        self.run_cmd(bs.cmd_restore)
        self.assertEqual(bs.loader_default(bs.loader_lines()), 'other')

    def test_default_and_pending_next(self):
        self.run_cmd(bs.cmd_default, value='fedora-7.2.6-3.opd2413')
        self.assertEqual(bs.loader_default(bs.loader_lines()), 'fedora-7.2.6-3.opd2413.conf')
        self.run_cmd(bs.cmd_next, entry='test')
        self.run_cmd(bs.cmd_default, value='fedora-*')       # changes what restore puts back
        self.assertEqual(bs.loader_default(bs.loader_lines()), 'test.conf')
        self.run_cmd(bs.cmd_restore)
        self.assertEqual(bs.loader_default(bs.loader_lines()), 'fedora-*')
        with self.assertRaises(SystemExit):
            self.run_cmd(bs.cmd_default, value='missing')
        with self.assertRaises(SystemExit):
            self.run_cmd(bs.cmd_default, value='a b')

    @unittest.skipUnless(shutil.which('bootctl'), 'needs bootctl')
    def test_systemd_boot_picks_it(self):
        # bootctl applies systemd-boot's own default matching. An exact entry
        # name without ".conf" matches nothing and falls back to the newest
        # entry, which is how the first M3.3b one-shot booted the wrong entry.
        root = Path(self.t.name)
        for e, version in (('fedora-7.2.15-3.opd2413', '7.2.15-3.opd2413'),
                           ('fedora-7.2.15-2.opd2413', '7.2.15-2.opd2413'),
                           ('opd2413-m33b', '7.2.15-3.opd2413')):
            (root / 'loader/entries' / f'{e}.conf').write_text(
                f'title {e}\nversion {version}\nsort-key fedora\nlinux /x\n')
        (root / 'loader/entries/test.conf').unlink()
        (root / 'loader/entries/fedora-7.2.6-3.opd2413.conf').unlink()

        def picked():
            out = subprocess.run(['bootctl', f'--esp-path={root}', '--no-variables', '--no-pager', 'list'],
                                 env=os.environ | {'SYSTEMD_RELAX_ESP_CHECKS': '1'},
                                 capture_output=True, text=True).stdout
            block = next(b for b in out.split('\n\n') if '(default)' in b)
            return next(line.split(':', 1)[1].strip() for line in block.splitlines() if line.strip().startswith('id:'))

        self.assertEqual(picked(), 'fedora-7.2.15-3.opd2413.conf')
        self.run_cmd(bs.cmd_default, value='fedora-7.2.15-2.opd2413')
        self.assertEqual(picked(), 'fedora-7.2.15-2.opd2413.conf')
        self.run_cmd(bs.cmd_next, entry='opd2413-m33b')
        self.assertEqual(picked(), 'opd2413-m33b.conf')
        self.run_cmd(bs.cmd_restore)
        self.assertEqual(picked(), 'fedora-7.2.15-2.opd2413.conf')

    def test_unknown_entry(self):
        with self.assertRaises(SystemExit):
            self.run_cmd(bs.cmd_next, entry='missing')
        self.assertEqual(bs.loader_default(bs.loader_lines()), 'fedora-*')


if __name__ == '__main__':
    unittest.main()
