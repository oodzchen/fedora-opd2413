#!/usr/bin/env python3
"""Offline unit tests for opd-netshare-daemon IPv6 and fast-discovery helpers."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_PATH = REPO_ROOT / "netshare" / "linux" / "opd-netshare-daemon"

loader = importlib.machinery.SourceFileLoader("opd_netshare_daemon", str(DAEMON_PATH))
spec = importlib.util.spec_from_loader("opd_netshare_daemon", loader)
assert spec is not None
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)


class NetShareDaemonTests(unittest.TestCase):
    def test_pick_ap_candidates_peer_sta_freq(self) -> None:
        allowed = {5180, 5240, 5745}
        self.assertEqual(
            mod.pick_ap_candidates(None, allowed, preferred_5g=5745, peer_sta_freq=5240),
            [5240, 2462],
        )
        self.assertEqual(
            mod.pick_ap_candidates(None, allowed, preferred_5g=5240, failed_freqs={5240: 9999999999.0}, now=100.0, peer_sta_freq=5240),
            [2462, 5240],
        )
        self.assertEqual(
            mod.pick_ap_candidates(5180, allowed, peer_sta_freq=5240),
            [2462],
        )

    def test_normalize_v6_addr(self) -> None:
        self.assertEqual(
            mod.normalize_v6_addr("fe80::1234:56ff:fe78:9abc%p2p0", require_link_local=True),
            "fe80::1234:56ff:fe78:9abc",
        )
        self.assertEqual(mod.normalize_v6_addr("240e:3b3:1234:5678::1", require_link_local=True), "")
        self.assertEqual(
            mod.normalize_v6_addr("240e:3b3:1234:5678:0:2413:49:1"),
            "240e:3b3:1234:5678:0:2413:49:1",
        )
        self.assertEqual(mod.normalize_v6_addr("fe80::1"), "")
        self.assertEqual(mod.normalize_v6_addr("not-an-ip"), "")

    def test_wait_for_peer_hello(self) -> None:
        d = object.__new__(mod.NetShareDaemon)
        d.lock = threading.RLock()
        d.shutting_down = False
        d.state = "advertising"

        s_srv, s_cli = socket.socketpair()
        try:
            d.rfcomm_sock = s_srv
            s_cli.sendall(b'{"event":"hello","sta_freq":5240}\n{"ip":"192.168.49.113"}\n')
            sta, rest = d._wait_for_peer_hello(s_srv)
            self.assertEqual(sta, 5240)
            self.assertEqual(rest, b'{"ip":"192.168.49.113"}\n')
        finally:
            s_srv.close()
            s_cli.close()

        s_srv2, s_cli2 = socket.socketpair()
        try:
            d.rfcomm_sock = s_srv2
            s_cli2.sendall(b'{"ip":"192.168.49.113"}\n')
            sta, rest = d._wait_for_peer_hello(s_srv2)
            self.assertIsNone(sta)
            self.assertEqual(rest, b'{"ip":"192.168.49.113"}\n')
        finally:
            s_srv2.close()
            s_cli2.close()

    def test_apply_peer_route_ipv6_lifecycle(self) -> None:
        d = object.__new__(mod.NetShareDaemon)
        d.lock = threading.RLock()
        d.ap_lock = threading.RLock()
        d.wpas_proc = object()
        d.mode = "auto"
        d.state = "advertising"
        d.freq = 5240
        d.wlp_has_def = False
        d.wlp_net_ok = False
        d.failed_freqs = {5240: 123.0}
        d.p2p_v6_ip = ""
        d.p2p_v6_ll = ""
        d._unregister_adv = lambda: None
        d._emit_status = lambda: None

        cmds: list[list[str]] = []

        def fake_run(cmd, check=False, timeout=10.0):
            cmds.append(list(cmd))
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(mod, "run_cmd", side_effect=fake_run):
            d._apply_peer_route(
                "192.168.49.113",
                v6_ll="fe80::1234:56ff:fe78:9abc",
                v6_ip="240e:3b3:1111:2222:0:2413:49:1",
                v6_out="rmnet_data3",
            )
            self.assertEqual(d.p2p_v6_ip, "240e:3b3:1111:2222:0:2413:49:1")
            self.assertIn(
                ["ip", "-6", "addr", "replace", "240e:3b3:1111:2222:0:2413:49:1/128", "dev", "p2p0", "nodad"],
                cmds,
            )
            self.assertIn(
                [
                    "ip",
                    "-6",
                    "route",
                    "replace",
                    "default",
                    "via",
                    "fe80::1234:56ff:fe78:9abc",
                    "dev",
                    "p2p0",
                    "proto",
                    "static",
                    "src",
                    "240e:3b3:1111:2222:0:2413:49:1",
                    "metric",
                    "700",
                ],
                cmds,
            )

            # DHCPACK without v6 fields must preserve existing v6 config
            cmds.clear()
            d._apply_peer_route("192.168.49.113")
            self.assertEqual(d.p2p_v6_ip, "240e:3b3:1111:2222:0:2413:49:1")
            self.assertTrue(any("2400:3200::1" in c for c in cmds))

            # Prefix change deletes old /128 and replaces with new /128
            cmds.clear()
            d._apply_peer_route(
                "192.168.49.113",
                v6_ll="fe80::1234:56ff:fe78:9abc",
                v6_ip="2409:8900:aaaa:bbbb:0:2413:49:1",
                v6_out="wlan0",
            )
            self.assertIn(["ip", "-6", "addr", "del", "240e:3b3:1111:2222:0:2413:49:1/128", "dev", "p2p0"], cmds)
            self.assertEqual(d.p2p_v6_ip, "2409:8900:aaaa:bbbb:0:2413:49:1")

            # Upstream switches to IPv4-only -> clears IPv6 cleanly
            cmds.clear()
            d._apply_peer_route("192.168.49.113", v6_ll="", v6_ip="", v6_out="none")
            self.assertEqual(d.p2p_v6_ip, "")
            self.assertIn(["ip", "-6", "route", "del", "default", "dev", "p2p0"], cmds)
            self.assertIn(["ip", "-6", "addr", "del", "2409:8900:aaaa:bbbb:0:2413:49:1/128", "dev", "p2p0"], cmds)

    def test_drain_proc_log_signals_ap_enabled(self) -> None:
        import io

        d = object.__new__(mod.NetShareDaemon)
        ev = threading.Event()
        proc = mock.Mock()
        proc.stdout = io.StringIO("p2p0: interface state UNINITIALIZED->HT_SCAN\np2p0: AP-ENABLED\n")
        d._drain_proc_log("wpa_supplicant", proc, ev)
        self.assertTrue(ev.is_set())
        self.assertIn("--no-ping", DAEMON_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
