"""Regression tests for the failure paths that quietly corrupted the data.

A failed speed test prints nothing on stdout. The collector did not check the
exit status, so the empty output became an all-None reading, and the byte
counters - seeing only background traffic on the other interfaces - concluded
the test had escaped over one of them. Which of the two wrong stories you got
depended on a byte race: sometimes a row of NULLs that reads as a successful
collection, sometimes no row at all. Neither was visible in the journal,
because the unit did not set PYTHONUNBUFFERED and the explanatory print never
reached it.

The numbers in these tests are the ones measured on the affected Pi.
"""

import subprocess
from datetime import datetime, timedelta, timezone

import pytest


class FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


GOOD_SPEED_OUTPUT = "Ping: 29.4 ms\nDownload: 84.9 Mbit/s\nUpload: 108.7 Mbit/s\n"


def _patch_run(monkeypatch, result):
    if isinstance(result, Exception):
        def run(*args, **kwargs):
            raise result
    else:
        def run(*args, **kwargs):
            return result
    monkeypatch.setattr(subprocess, "run", run)


class TestSpeedCollectorFailures:
    def _collector(self, monkeypatch, result, before=None, after=None):
        from wifi_diag.collectors import speed

        monkeypatch.setattr(speed, "interface_ip", lambda iface: "192.168.1.196")
        snapshots = iter([before or {}, after or {}])
        monkeypatch.setattr(speed, "rx_byte_counters", lambda: next(snapshots))
        _patch_run(monkeypatch, result)
        return speed.SpeedCollector("wlan0")

    def test_nonzero_exit_raises_instead_of_storing_nulls(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedTestError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(
                stdout="", stderr="ERROR: No matched servers: 999999\n", returncode=1
            ),
        )
        with pytest.raises(SpeedTestError, match="No matched servers"):
            collector.collect()

    def test_failed_run_is_not_blamed_on_the_wrong_interface(self, monkeypatch):
        """The production failure, reproduced.

        speedtest-cli fails and moves almost nothing over wlan0 while eth0
        keeps accruing ordinary background traffic. The old code compared the
        two, concluded the test had escaped over eth0, and dropped the reading
        with a message nobody could see. The exit status has to be checked
        before the counters are consulted at all.
        """
        from wifi_diag.collectors.speed import SpeedTestError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout="", stderr="ERROR: unable to connect\n", returncode=1),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 12_638, "eth0": 696_207},
        )
        with pytest.raises(SpeedTestError):
            collector.collect()

    def test_clean_exit_with_unparseable_output_raises(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedTestError

        collector = self._collector(
            monkeypatch, FakeCompleted(stdout="Retrieving speedtest.net config...\n")
        )
        with pytest.raises(SpeedTestError):
            collector.collect()

    def test_timeout_raises_rather_than_stalling_the_loop(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedTestError

        collector = self._collector(
            monkeypatch,
            subprocess.TimeoutExpired(cmd="speedtest-cli", timeout=180),
        )
        with pytest.raises(SpeedTestError):
            collector.collect()

    def test_missing_binary_raises(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedTestError

        collector = self._collector(
            monkeypatch, FileNotFoundError(2, "No such file or directory")
        )
        with pytest.raises(SpeedTestError):
            collector.collect()

    def test_subprocess_gets_a_deadline(self, monkeypatch):
        from wifi_diag.collectors import speed

        seen = {}
        monkeypatch.setattr(speed, "interface_ip", lambda iface: None)
        monkeypatch.setattr(speed, "rx_byte_counters", lambda: {})
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda cmd, **kwargs: (
                seen.update(kwargs),
                FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            )[1],
        )
        speed.SpeedCollector("wlan0").collect()
        assert seen["timeout"] == speed.SPEEDTEST_TIMEOUT_SECS

    def test_good_run_over_the_named_interface_is_returned(self, monkeypatch):
        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 112_333_395, "eth0": 1_783_393},
        )
        assert collector.collect()["download_mbps"] == 84.9

    def test_good_run_over_the_wrong_interface_still_raises(self, monkeypatch):
        from wifi_diag.collectors.speed import WrongInterfaceError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 5_000, "eth0": 112_333_395},
        )
        with pytest.raises(WrongInterfaceError):
            collector.collect()

    def test_a_run_split_across_both_links_is_rejected(self, monkeypatch):
        """Measured on the Pi: 102 MB over eth0 and 85 MB over wlan0 at once.

        speedtest-cli opens parallel connections and binds only some to the
        source address. It reported 140 Mbit/s, which is neither the WiFi link
        nor the wire. Naming the busiest interface alone would have caught this
        one, but not a split that happens to favour wlan0.
        """
        from wifi_diag.collectors.speed import WrongInterfaceError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 85_105_778, "eth0": 102_237_035},
        )
        with pytest.raises(WrongInterfaceError, match="45%"):
            collector.collect()

    def test_a_split_favouring_the_right_interface_is_still_rejected(self, monkeypatch):
        from wifi_diag.collectors.speed import WrongInterfaceError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 60_000_000, "eth0": 40_000_000},
        )
        with pytest.raises(WrongInterfaceError):
            collector.collect()

    def test_ordinary_background_noise_does_not_reject_a_clean_run(self, monkeypatch):
        """run2 on the Pi: 111 MB over wlan0 against 1.6 MB of eth0 chatter."""
        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 111_026_024, "eth0": 1_600_067},
        )
        assert collector.collect()["download_mbps"] == 84.9


class TestLatencyCollectorFailures:
    def _collector(self, monkeypatch, result):
        from wifi_diag.collectors.latency import LatencyCollector

        _patch_run(monkeypatch, result)
        return LatencyCollector("8.8.8.8", 3, "wlan0")

    def test_unparseable_output_raises_instead_of_storing_nulls(self, monkeypatch):
        from wifi_diag.collectors.latency import PingError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout="", stderr="ping: SO_BINDTODEVICE: Operation not permitted\n", returncode=2),
        )
        with pytest.raises(PingError):
            collector.collect()

    def test_timeout_raises(self, monkeypatch):
        from wifi_diag.collectors.latency import PingError

        collector = self._collector(
            monkeypatch, subprocess.TimeoutExpired(cmd="ping", timeout=11)
        )
        with pytest.raises(PingError):
            collector.collect()

    def test_total_packet_loss_is_a_measurement_and_is_kept(self, monkeypatch):
        """100% loss is the signal, not the absence of one.

        The link was up enough to try and every packet died. Discarding that
        would throw away the clearest evidence of a WiFi problem this tool can
        gather.
        """
        output = (
            "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n\n"
            "--- 8.8.8.8 ping statistics ---\n"
            "3 packets transmitted, 0 received, 100% packet loss, time 2043ms\n"
        )
        collector = self._collector(
            monkeypatch, FakeCompleted(stdout=output, returncode=1)
        )
        reading = collector.collect()
        assert reading["packet_loss_pct"] == 100.0
        assert reading["rtt_avg_ms"] is None


class TestPhysicalInterfaceFiltering:
    """wg0 moved 611 KB in 15 idle seconds on the affected host.

    A WireGuard interface counts the same payload bytes that wlan0 already
    counted as ciphertext, so it can win a comparison it has no business
    entering.
    """

    def _fake_sysfs(self, tmp_path, spec):
        for name, (rx_bytes, physical) in spec.items():
            stats = tmp_path / name / "statistics"
            stats.mkdir(parents=True)
            (stats / "rx_bytes").write_text(str(rx_bytes))
            if physical:
                backing = tmp_path / ("%s.backing" % name)
                backing.mkdir()
                try:
                    (tmp_path / name / "device").symlink_to(
                        backing, target_is_directory=True
                    )
                except (OSError, NotImplementedError):
                    pytest.skip("symlink creation not permitted on this host")
        return tmp_path

    def test_virtual_interfaces_are_excluded(self, tmp_path, monkeypatch):
        from wifi_diag import netiface

        root = self._fake_sysfs(
            tmp_path,
            {
                "wlan0": (112_333_395, True),
                "eth0": (1_783_393, True),
                "wg0": (611_056, False),
                "lo": (709, False),
            },
        )
        monkeypatch.setattr(netiface, "_SYS_NET", root)
        assert set(netiface.rx_byte_counters()) == {"wlan0", "eth0"}

    def test_missing_sysfs_yields_no_counters(self, tmp_path, monkeypatch):
        from wifi_diag import netiface

        monkeypatch.setattr(netiface, "_SYS_NET", tmp_path / "absent")
        assert netiface.rx_byte_counters() == {}


class TestBusiestInterfaceContract:
    """The docstring promised these; the code did not deliver them."""

    def test_returns_none_when_a_counter_went_backwards(self):
        from wifi_diag.netiface import busiest_interface

        assert busiest_interface(
            {"wlan0": 10_000, "eth0": 0}, {"wlan0": 5, "eth0": 900}
        ) is None

    def test_returns_none_when_an_interface_vanished(self):
        from wifi_diag.netiface import busiest_interface

        assert busiest_interface({"wlan0": 0, "usb0": 0}, {"wlan0": 500}) is None

    def test_returns_none_when_an_interface_appeared(self):
        from wifi_diag.netiface import busiest_interface

        assert busiest_interface({"wlan0": 0}, {"wlan0": 500, "usb0": 900}) is None


class _StubLatency:
    def __init__(self, *args, **kwargs):
        pass

    def collect(self):
        return {"rtt_avg_ms": 1.0, "packet_loss_pct": 0.0}


class _StubCast:
    def collect(self, ip):
        return {
            "mac": "aa:bb:cc:dd:ee:ff",
            "name": "Stub Speaker",
            "ssid": "net",
            "bssid": None,
            "ethernet": False,
            "uptime_secs": 100.0,
            "firmware": "1.0",
        }


class TestSchedulerWiring:
    """The previous version of this test called the factories directly.

    Reverting every interface argument in scheduler.py left it green, which
    means it protected nothing. These construct the scheduler.
    """

    def _scheduler(self, monkeypatch):
        from wifi_diag import config
        from wifi_diag.scheduler import DiagScheduler
        from wifi_diag.store import DiagStore

        monkeypatch.setattr(config, "WIFI_INTERFACE", "wlan9")
        store = DiagStore(":memory:")
        return DiagScheduler(store), store

    def test_every_probe_is_pinned_to_the_configured_interface(self, monkeypatch):
        scheduler, store = self._scheduler(monkeypatch)
        try:
            assert scheduler.gateway_collector.interface == "wlan9"
            assert scheduler.external_collector.interface == "wlan9"
            assert scheduler.speed_collector.interface == "wlan9"
        finally:
            store.close()

    def test_cast_probes_are_pinned_to_the_same_interface(self, monkeypatch):
        from wifi_diag import scheduler as scheduler_mod

        scheduler, store = self._scheduler(monkeypatch)
        try:
            seen = []
            monkeypatch.setattr(
                scheduler_mod,
                "create_latency_collector",
                lambda target, count, dry_run, interface: (
                    seen.append(interface),
                    _StubLatency(),
                )[1],
            )
            scheduler.cast_collector = _StubCast()
            scheduler._probe_cast_device(
                None, "192.168.1.50", None, None, "2026-08-04T12:00:00+00:00", set()
            )
            assert seen == ["wlan9"]
        finally:
            store.close()


class TestSchedulerFailureHandling:
    def _scheduler(self, monkeypatch):
        from wifi_diag.scheduler import DiagScheduler
        from wifi_diag.store import DiagStore

        store = DiagStore(":memory:")
        return DiagScheduler(store), store

    def test_a_failed_speed_test_stores_nothing(self, monkeypatch, capsys):
        from wifi_diag.collectors.speed import SpeedTestError

        scheduler, store = self._scheduler(monkeypatch)
        try:
            class Failing:
                interface = "wlan0"

                def collect(self):
                    raise SpeedTestError("speedtest-cli exited 1: ERROR: unable to connect")

            scheduler.speed_collector = Failing()
            scheduler._collect_speed()
            assert store.get_speed_readings() == []
            assert "unable to connect" in capsys.readouterr().out
        finally:
            store.close()

    def test_a_discarded_speed_test_says_so_distinctly(self, monkeypatch, capsys):
        from wifi_diag.collectors.speed import WrongInterfaceError

        scheduler, store = self._scheduler(monkeypatch)
        try:
            class Escaped:
                interface = "wlan0"

                def collect(self):
                    raise WrongInterfaceError("speed test traffic left via eth0")

            scheduler.speed_collector = Escaped()
            scheduler._collect_speed()
            assert store.get_speed_readings() == []
            out = capsys.readouterr().out
            assert "discarded" in out.lower()
            assert "eth0" in out
        finally:
            store.close()

    def test_a_good_speed_reading_records_its_interface(self, monkeypatch):
        scheduler, store = self._scheduler(monkeypatch)
        try:
            class Good:
                def collect(self):
                    return {
                        "download_mbps": 84.9,
                        "upload_mbps": 108.7,
                        "ping_ms": 29.4,
                    }

            scheduler.speed_collector = Good()
            scheduler._collect_speed()
            rows = store.get_speed_readings()
            assert len(rows) == 1
            assert rows[0]["interface"] == scheduler._interface
        finally:
            store.close()


class TestCastProbeIsPinned:
    """Reachability was measured over whichever link the kernel preferred.

    Its ping was pinned to WiFi while the HTTP probe that decides reachable
    yes/no was not, so a device unreachable over WiFi could still be recorded
    as up because the wire answered for it.
    """

    def _opener_handlers(self, monkeypatch, interface, resolved):
        from wifi_diag.collectors import cast

        monkeypatch.setattr(cast, "interface_ip", lambda iface: resolved)
        monkeypatch.setattr(cast, "parse_eureka_info", lambda text: {"mac": "aa"})
        captured = {}

        class Response:
            def read(self, size):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Opener:
            def open(self, url, timeout=None):
                return Response()

        def build_opener(*handlers):
            captured["handlers"] = handlers
            return Opener()

        monkeypatch.setattr(cast.urllib.request, "build_opener", build_opener)
        cast.CastCollector(interface=interface).collect("192.168.1.50")
        return cast, captured["handlers"]

    def test_probe_is_bound_to_the_wifi_address(self, monkeypatch):
        cast, handlers = self._opener_handlers(monkeypatch, "wlan0", "192.168.1.196")
        bound = [h for h in handlers if isinstance(h, cast._SourceBoundHTTPHandler)]
        assert len(bound) == 1
        assert bound[0]._source == "192.168.1.196"

    def test_probe_is_unbound_when_the_address_cannot_be_resolved(self, monkeypatch):
        cast, handlers = self._opener_handlers(monkeypatch, "wlan0", None)
        assert not any(isinstance(h, cast._SourceBoundHTTPHandler) for h in handlers)

    def test_probe_is_unbound_when_no_interface_is_configured(self, monkeypatch):
        cast, handlers = self._opener_handlers(monkeypatch, None, "192.168.1.196")
        assert not any(isinstance(h, cast._SourceBoundHTTPHandler) for h in handlers)


class TestCrossInterfaceComparison:
    """The tool reported its own bug fix as a network regression.

    Before the interface pinning landed, speed tests ran over ethernet and
    recorded around 400 Mbps. Afterwards they measured the WiFi link at around
    53. Comparing the two windows produced "Download speed declining", which is
    the opposite of what happened.
    """

    def _seed(self, store, entries):
        for days_ago, download, interface in entries:
            ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
            store.insert_wifi_reading({
                "timestamp": ts,
                "host": "pi",
                "rssi_dbm": -52.0,
                "noise_dbm": None,
                "frequency_mhz": 5180,
                "band": "5GHz",
                "channel": 36,
                "link_speed_mbps": 400.0,
                "bssid": "aa:bb:cc:dd:ee:ff",
            })
            store.insert_speed_reading({
                "timestamp": ts,
                "host": "pi",
                "download_mbps": download,
                "upload_mbps": 100.0,
                "ping_ms": 10.0,
                "interface": interface,
            })

    def test_windows_measured_over_different_interfaces_are_not_compared(self):
        from wifi_diag.analysis.diagnose import diagnose
        from wifi_diag.store import DiagStore

        store = DiagStore(":memory:")
        try:
            self._seed(store, [(10, 400.0, "eth0"), (1, 53.0, "wlan0")])
            report = diagnose(store, days=21)
            assert "Download speed declining" not in report
            assert "not comparable" in report
        finally:
            store.close()

    def test_a_real_decline_on_one_interface_is_still_reported(self):
        from wifi_diag.analysis.diagnose import diagnose
        from wifi_diag.store import DiagStore

        store = DiagStore(":memory:")
        try:
            self._seed(store, [(10, 400.0, "wlan0"), (1, 53.0, "wlan0")])
            report = diagnose(store, days=21)
            assert "Download speed declining" in report
        finally:
            store.close()


class TestStoreMigration:
    def test_an_existing_database_without_the_column_gains_it(self, tmp_path):
        import sqlite3

        from wifi_diag.store import DiagStore

        db = tmp_path / "old.db"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE speed_readings (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                download_mbps REAL,
                upload_mbps REAL,
                ping_ms REAL
            );
            INSERT INTO speed_readings (timestamp, host, download_mbps)
            VALUES ('2026-08-01T00:00:00+00:00', 'pi', 400.0);
        """)
        conn.commit()
        conn.close()

        store = DiagStore(db)
        try:
            rows = store.get_speed_readings()
            assert len(rows) == 1
            # NULL means unknown provenance, not WiFi.
            assert rows[0]["interface"] is None
        finally:
            store.close()
