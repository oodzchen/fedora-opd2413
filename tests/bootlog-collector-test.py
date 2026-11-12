#!/usr/bin/env python3
"""Offline collector tests: ordinary files/FIFOs only; never opens /dev/kmsg or a disk."""
from pathlib import Path
import os
import select
import shlex
import signal
import socket
import stat
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent


class CollectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='opd2413-bootlog-build-')
        if os.environ.get('BOOTLOG_BINARY'):
            cls.binary = Path(os.environ['BOOTLOG_BINARY']).resolve(strict=True)
        else:
            cls.binary = Path(cls.build.name) / 'kmsg-to-file'
            command = shlex.split(os.environ.get('CC', 'cc'))
            subprocess.run(command + ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                      str(REPO / 'tools/bootlog/kmsg-to-file.c'),
                                      '-o', str(cls.binary)], check=True)
        cls.command = shlex.split(os.environ.get('BOOTLOG_RUNNER', '')) + [str(cls.binary)]

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='opd2413-bootlog-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'fake-kmsg'
        self.output = self.root / 'boot.log'
        self.payload = b'6,1,100,-;first initcall\n7,2,200,-;second initcall\n'
        self.source.write_bytes(self.payload)

    def run_collector(self, *extra, source=None, output=None):
        return subprocess.run(self.command + ['--source', str(source or self.source),
                               '--output', str(output or self.output), *extra],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)

    def test_replay_includes_metadata_and_raw_records(self):
        result = self.run_collector()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.output.read_bytes()
        self.assertTrue(data.startswith(b'# opd2413-bootlog format=1 kernel='))
        self.assertIn(b'# boot_id=', data)
        self.assertIn(b'# cmdline=', data)
        self.assertIn(self.payload, data)
        self.assertTrue(data.endswith(b'# END signal=0 overruns=0\n'))
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    def test_existing_log_is_not_truncated(self):
        self.output.write_bytes(b'previous evidence')
        self.assertNotEqual(self.run_collector().returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'previous evidence')

    def test_output_symlink_cannot_overwrite_another_file(self):
        victim = self.root / 'keep'
        victim.write_bytes(b'do not overwrite')
        self.output.symlink_to(victim)
        self.assertNotEqual(self.run_collector().returncode, 0)
        self.assertEqual(victim.read_bytes(), b'do not overwrite')

    def test_symlinked_output_directory_is_rejected(self):
        directory = self.root / 'real-directory'
        directory.mkdir()
        link = self.root / 'symlink-directory'
        link.symlink_to(directory, target_is_directory=True)
        self.assertNotEqual(self.run_collector(output=link / 'boot.log').returncode, 0)
        self.assertFalse((directory / 'boot.log').exists())

    def test_missing_source_creates_no_log(self):
        result = self.run_collector(source=self.root / 'absent')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_invalid_readiness_fd_creates_no_log(self):
        for fd in ['-1', '2', '65536', 'bad', '']:
            with self.subTest(fd=fd):
                self.assertNotEqual(self.run_collector('--ready-fd', fd).returncode, 0)
                self.assertFalse(self.output.exists())

    def test_source_symlink_is_rejected(self):
        link = self.root / 'source-symlink'
        link.symlink_to(self.source)
        self.assertNotEqual(self.run_collector(source=link).returncode, 0)
        self.assertFalse(self.output.exists())

    def test_permissive_mode_exposes_initial_loss_and_sequence_gaps(self):
        payload = b'6,279,100,-;oldest\n6,281,200,-;gap\n'
        self.source.write_bytes(payload)
        self.assertEqual(self.run_collector().returncode, 0)
        data = self.output.read_bytes()
        self.assertIn(payload, data)
        self.assertIn(b'initial_missing=279 gaps=1', data)
        self.assertIn(b'gap_previous=279 gap_current=281', data)

    def test_strict_accepts_zero_dictionary_lines_and_future_header_fields(self):
        self.source.write_bytes(b'6,0,100,-,extension;first\n SUBSYSTEM=test\n6,1,200,c;next\n')
        result = self.run_collector('--require-start-zero')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'initial_missing=0 gaps=0 malformed=0 partial=0', self.output.read_bytes())

    def test_strict_rejects_incomplete_history_without_readiness(self):
        cases = {
            'initial': b'6,279,100,-;lost beginning\n',
            'gap': b'6,0,100,-;first\n6,2,200,-;missing one\n',
            'duplicate': b'6,0,100,-;first\n6,0,200,-;duplicate\n',
            'malformed': b'bad header\n',
            'unfinished': b'6,0,100,-;no newline',
            'overflow': b'6,18446744073709551616,100,-;too large\n',
            'empty': b'',
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                self.source.write_bytes(payload)
                read_fd, ready_fd = os.pipe()
                try:
                    result = subprocess.run(self.command + [
                        '--source', str(self.source), '--output', str(self.root / (name+'.log')),
                        '--require-start-zero', '--ready-fd', str(ready_fd)],
                        pass_fds=(ready_fd,), capture_output=True, timeout=5)
                    os.close(ready_fd)
                    ready_fd = -1
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(os.read(read_fd, 1024), b'')
                    self.assertIn(b'# INCOMPLETE:', (self.root / (name+'.log')).read_bytes())
                finally:
                    os.close(read_fd)
                    if ready_fd >= 0:
                        os.close(ready_fd)

    def test_systemd_notification_follows_synced_strict_history(self):
        self.source.write_bytes(b'6,0,100,-;complete beginning\n')
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify:
            path = str(self.root / 'notify.sock')
            notify.bind(path)
            result = subprocess.run(self.command + ['--source', str(self.source),
                '--output', str(self.output), '--require-start-zero', '--notify'],
                env=os.environ | {'NOTIFY_SOCKET': path}, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(select.select([notify], [], [], 1)[0])
            self.assertIn(b'READY=1\n', notify.recv(1024))
            self.assertIn(b'initial_missing=0 gaps=0', self.output.read_bytes())

    def test_notification_is_not_sent_for_initial_loss(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify:
            path = str(self.root / 'notify.sock')
            notify.bind(path)
            result = subprocess.run(self.command + ['--source', str(self.source),
                '--output', str(self.output), '--require-start-zero', '--notify'],
                env=os.environ | {'NOTIFY_SOCKET': path}, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)  # fixture begins at sequence 1
            self.assertFalse(select.select([notify], [], [], 0)[0])

    def test_notification_failure_is_an_error(self):
        self.source.write_bytes(b'6,0,100,-;first\n')
        result = subprocess.run(self.command + ['--source', str(self.source),
            '--output', str(self.output), '--notify'],
            env=os.environ | {'NOTIFY_SOCKET': str(self.root / 'missing.sock')},
            capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)

    def test_strict_stream_fragments_and_post_readiness_gap(self):
        self.source.unlink()
        os.mkfifo(self.source, 0o600)
        writer = os.open(self.source, os.O_RDWR | os.O_NONBLOCK)
        read_fd, ready_fd = os.pipe()
        process = None
        try:
            os.write(writer, b'6,0,100,')
            process = subprocess.Popen(self.command + ['--source', str(self.source),
                '--output', str(self.output), '--require-start-zero', '--ready-fd', str(ready_fd)],
                pass_fds=(ready_fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.close(ready_fd)
            ready_fd = -1
            self.assertFalse(select.select([read_fd], [], [], 0.1)[0])
            os.write(writer, b'-;first complete record\n')
            self.assertTrue(select.select([read_fd], [], [], 5)[0])
            self.assertEqual(os.read(read_fd, 1024), b'READY\n')
            self.assertIn(b'6,0,100,-;first complete record\n', self.output.read_bytes())
            os.write(writer, b'6,2,200,-;missing record one\n')
            process.communicate(timeout=5)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn(b'initial_missing=0 gaps=1', self.output.read_bytes())
            self.assertIn(b'# INCOMPLETE:', self.output.read_bytes())
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            os.close(writer)
            os.close(read_fd)
            if ready_fd >= 0:
                os.close(ready_fd)

    def test_file_limit_fails_without_exceeding_bound(self):
        import resource
        self.source.write_bytes(b'6,0,100,-;' + b'x'*16384 + b'\n')
        def limits():
            resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 4096))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        result = subprocess.run(self.command + ['--source', str(self.source),
            '--output', str(self.output)], preexec_fn=limits, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertLessEqual(self.output.stat().st_size, 4096)

    def test_signal_immediately_after_ready_has_no_lost_wakeup(self):
        self.source.unlink()
        os.mkfifo(self.source, 0o600)
        writer = os.open(self.source, os.O_RDWR | os.O_NONBLOCK)
        try:
            for index in range(20):
                read_fd, ready_fd = os.pipe()
                process = None
                try:
                    output = self.root / f'immediate-stop-{index}.log'
                    process = subprocess.Popen(
                        self.command + ['--source', str(self.source),
                         '--output', str(output), '--ready-fd', str(ready_fd)],
                        pass_fds=(ready_fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    os.close(ready_fd)
                    ready_fd = -1
                    self.assertTrue(select.select([read_fd], [], [], 5)[0])
                    self.assertEqual(os.read(read_fd, 1024), b'READY\n')
                    process.send_signal(signal.SIGTERM)
                    _, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertIn(b'# END signal=15', output.read_bytes())
                finally:
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
                    os.close(read_fd)
                    if ready_fd >= 0:
                        os.close(ready_fd)
        finally:
            os.close(writer)

    def test_stream_sync_flag_readiness_after_backlog_and_signal_stop(self):
        self.source.unlink()
        os.mkfifo(self.source, 0o600)
        writer = os.open(self.source, os.O_RDWR | os.O_NONBLOCK)
        read_fd, ready_fd = os.pipe()
        process = None
        try:
            # Seed the FIFO before launch. READY must not precede this backlog.
            os.write(writer, self.payload)
            process = subprocess.Popen(self.command + ['--source', str(self.source),
                                        '--output', str(self.output), '--ready-fd', str(ready_fd)],
                                       pass_fds=(ready_fd,), stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            os.close(ready_fd)
            ready_fd = -1
            self.assertTrue(select.select([read_fd], [], [], 5)[0], 'readiness timed out')
            self.assertEqual(os.read(read_fd, 1024), b'READY\n')
            self.assertIn(self.payload, self.output.read_bytes())
            # Check the live descriptor, not just the source spelling of O_DSYNC.
            descriptors = Path(f'/proc/{process.pid}/fd')
            output_fd = next(p.name for p in descriptors.iterdir()
                             if p.resolve() == self.output)
            info = Path(f'/proc/{process.pid}/fdinfo/{output_fd}').read_text()
            flags = int(next(line.split()[1] for line in info.splitlines()
                             if line.startswith('flags:')), 8)
            self.assertEqual(flags & os.O_DSYNC, os.O_DSYNC)
            os.write(writer, b'6,3,300,-;late driver probe\n')
            # Use a test-side deadline; the collector itself follows events.
            import time
            deadline = time.monotonic() + 5
            while b'late driver probe' not in self.output.read_bytes():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            process.send_signal(signal.SIGTERM)
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn(b'# END signal=15 overruns=0\n', self.output.read_bytes())
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            os.close(writer)
            os.close(read_fd)
            if ready_fd >= 0:
                os.close(ready_fd)


if __name__ == '__main__':
    unittest.main(verbosity=2)
