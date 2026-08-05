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

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest


class FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def legacy_json(download_mbps=84.9, bytes_received=112_000_000):
    """One `speedtest-cli --json` result, whose speeds are bits per second."""
    return json.dumps({
        "download": download_mbps * 1_000_000,
        "upload": 108.7 * 1_000_000,
        "ping": 29.4,
        "bytes_sent": 90_000_000,
        "bytes_received": bytes_received,
    })


GOOD_SPEED_OUTPUT = legacy_json()


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

        monkeypatch.setattr(speed, "ookla_binary", lambda: None)
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
        monkeypatch.setattr(speed, "ookla_binary", lambda: None)
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
            FakeCompleted(stdout=legacy_json(bytes_received=187_342_813)),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 85_105_778, "eth0": 102_237_035},
        )
        with pytest.raises(WrongInterfaceError, match="45%"):
            collector.collect()

    def test_a_split_favouring_the_right_interface_is_still_rejected(self, monkeypatch):
        from wifi_diag.collectors.speed import WrongInterfaceError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=legacy_json(bytes_received=100_000_000)),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 60_000_000, "eth0": 40_000_000},
        )
        with pytest.raises(WrongInterfaceError):
            collector.collect()

    def test_ordinary_background_noise_does_not_reject_a_clean_run(self, monkeypatch):
        """run2 on the Pi: 111 MB over wlan0 against 1.6 MB of eth0 chatter."""
        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=legacy_json(bytes_received=111_000_000)),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 111_026_024, "eth0": 1_600_067},
        )
        assert collector.collect()["download_mbps"] == 84.9

    @pytest.mark.parametrize(
        "mbps,downloaded,carried",
        [
            # Shares of 76% and 55% against the 3.0 MB of eth0 chatter below.
            (5.0, 9_400_000, 9_412_336),
            (2.0, 3_750_000, 3_770_112),
        ],
    )
    def test_a_degraded_link_is_recorded_rather_than_discarded(
        self, monkeypatch, mbps, downloaded, carried
    ):
        """The regression that made this tool blind exactly when it mattered.

        Background chatter on the other NIC is a fixed number of bytes, so
        sharing a denominator with it made the gate tighten as the link slowed:
        the numerator falls with the link while the noise stays put. Every
        reading below roughly 15 Mbit/s was thrown away, and the history read
        as healthy right up to the moment the data stopped. Checking against
        the byte total the test itself reports is independent of the noise.
        """
        collector = self._collector(
            monkeypatch,
            FakeCompleted(
                stdout=legacy_json(download_mbps=mbps, bytes_received=downloaded)
            ),
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": carried, "eth0": 3_045_407},
        )
        reading = collector.collect()
        assert reading["download_mbps"] == mbps
        assert reading["interface"] == "wlan0"

    def test_a_reading_is_discarded_when_the_interface_cannot_be_compared(self, monkeypatch):
        """Counters that cannot be compared mean unattributable, not verified."""
        from wifi_diag.collectors.speed import WrongInterfaceError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            before={"eth0": 0},
            after={"eth0": 500},
        )
        with pytest.raises(WrongInterfaceError, match="cannot be attributed"):
            collector.collect()

    def test_a_counter_reset_mid_run_discards_rather_than_stores(self, monkeypatch):
        from wifi_diag.collectors.speed import WrongInterfaceError

        collector = self._collector(
            monkeypatch,
            FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
            before={"wlan0": 900_000_000, "eth0": 0},
            after={"wlan0": 12_000, "eth0": 500},
        )
        with pytest.raises(WrongInterfaceError):
            collector.collect()


OOKLA_JSON = (
    '{"type":"result","timestamp":"2026-08-04T14:12:50Z",'
    '"ping":{"jitter":1.903,"latency":5.855},'
    '"download":{"bandwidth":13261655,"bytes":192730004,"elapsed":15010},'
    '"upload":{"bandwidth":12256386,"bytes":80546340,"elapsed":6607}}'
)


class TestOoklaPath:
    """Ookla's CLI binds with SO_BINDTODEVICE, so egress is forced not requested.

    Captured from the affected Pi, where --interface=wlan0 put 206.9 MB on
    wlan0 against 3.0 MB of eth0 background chatter.
    """

    def _collector(self, monkeypatch, available=True, result=None, before=None, after=None):
        import sys as _sys
        from wifi_diag.collectors import speed

        # These describe the Pi, and only Linux has a device-binding flag.
        monkeypatch.setattr(_sys, "platform", "linux")
        path = "/usr/local/bin/speedtest" if available else None
        monkeypatch.setattr(speed, "ookla_binary", lambda: path)
        snapshots = iter([before or {}, after or {}])
        monkeypatch.setattr(speed, "rx_byte_counters", lambda: next(snapshots))
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return result if result is not None else FakeCompleted(stdout=OOKLA_JSON)

        monkeypatch.setattr(subprocess, "run", run)
        return speed.SpeedCollector("wlan0"), calls

    def test_binds_to_the_interface_by_name(self, monkeypatch):
        collector, calls = self._collector(
            monkeypatch,
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 206_946_617, "eth0": 3_045_407},
        )
        collector.collect()
        assert "--interface=wlan0" in calls[0]
        assert "--source" not in calls[0]

    def test_bandwidth_is_bytes_per_second_not_bits(self, monkeypatch):
        collector, _ = self._collector(
            monkeypatch,
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 206_946_617, "eth0": 3_045_407},
        )
        reading = collector.collect()
        # 13,261,655 B/s * 8 / 1e6. Reading the field as bits understates by 8x.
        assert reading["download_mbps"] == 106.09
        assert reading["upload_mbps"] == 98.05
        assert reading["ping_ms"] == 5.86

    def test_falls_back_to_speedtest_cli_when_absent(self, monkeypatch):
        from wifi_diag.collectors import speed

        monkeypatch.setattr(speed, "interface_ip", lambda iface: "192.168.1.196")
        collector, calls = self._collector(
            monkeypatch,
            available=False,
            result=FakeCompleted(stdout=GOOD_SPEED_OUTPUT),
        )
        collector.collect()
        assert calls[0][0] == "speedtest-cli"
        assert "--source" in calls[0]

    def test_a_failed_run_still_raises(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedTestError

        collector, _ = self._collector(
            monkeypatch,
            result=FakeCompleted(stdout="", stderr="[error] no servers\n", returncode=1),
        )
        with pytest.raises(SpeedTestError, match="no servers"):
            collector.collect()

    def test_unparseable_json_raises(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedTestError

        collector, _ = self._collector(monkeypatch, result=FakeCompleted(stdout="not json"))
        with pytest.raises(SpeedTestError):
            collector.collect()

    def test_reported_bytes_are_checked_against_the_counters(self, monkeypatch):
        """The JSON says 192.7 MB; wlan0 carrying 40 MB of it means a split."""
        from wifi_diag.collectors.speed import WrongInterfaceError

        collector, _ = self._collector(
            monkeypatch,
            before={"wlan0": 0, "eth0": 0},
            after={"wlan0": 40_000_000, "eth0": 155_000_000},
        )
        with pytest.raises(WrongInterfaceError, match="21%"):
            collector.collect()

    def test_windows_gets_no_interface_flag_and_claims_no_provenance(self, monkeypatch):
        """wlan0 is not a Windows device name, so passing it fails every run."""
        import sys as _sys
        from wifi_diag.collectors import speed

        monkeypatch.setattr(_sys, "platform", "win32")
        monkeypatch.setattr(speed, "ookla_binary", lambda: "speedtest")
        # What the real thing returns off Linux, so nothing can be verified.
        monkeypatch.setattr(speed, "rx_byte_counters", lambda: {})
        calls = []
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda cmd, **k: (calls.append(cmd), FakeCompleted(stdout=OOKLA_JSON))[1],
        )
        reading = speed.SpeedCollector("wlan0").collect()
        assert not any(c.startswith("--interface") for c in calls[0])
        assert reading["interface"] is None


class TestOoklaDetection:
    """Both clients install a command called `speedtest`; only one can bind."""

    def _probe(self, monkeypatch, versions):
        from wifi_diag.collectors import speed

        seen = []

        def run(cmd, **kwargs):
            seen.append(cmd[0])
            if cmd[0] not in versions:
                raise FileNotFoundError(2, "No such file or directory")
            return FakeCompleted(stdout=versions[cmd[0]])

        monkeypatch.setattr(subprocess, "run", run)
        return speed.ookla_binary(), seen

    def test_the_pip_client_is_not_mistaken_for_ookla(self, monkeypatch):
        # Real `speedtest-cli 2.1.3 --version` output; no Ookla anywhere in it.
        found, _ = self._probe(
            monkeypatch,
            {"speedtest": "speedtest-cli 2.1.3\nPython 3.11.2\n"},
        )
        assert found is None

    def test_the_absolute_path_wins_over_a_shim_earlier_on_path(self, monkeypatch):
        found, seen = self._probe(
            monkeypatch,
            {
                "/usr/local/bin/speedtest": "Speedtest by Ookla 1.2.0\n",
                "speedtest": "speedtest-cli 2.1.3\n",
            },
        )
        assert found == "/usr/local/bin/speedtest"
        assert seen == ["/usr/local/bin/speedtest"]

    def test_ookla_on_path_alone_is_accepted(self, monkeypatch):
        found, _ = self._probe(
            monkeypatch, {"speedtest": "Speedtest by Ookla 1.2.0\n"}
        )
        assert found == "speedtest"

    def test_no_speedtest_at_all_is_not_an_error(self, monkeypatch):
        assert self._probe(monkeypatch, {})[0] is None


class TestOoklaParser:
    def test_result_object_on_its_own_line_is_found(self):
        from wifi_diag.parsers.ookla_parser import parse_ookla

        noisy = "Speedtest by Ookla\n" + OOKLA_JSON + "\n"
        assert parse_ookla(noisy)["download_mbps"] == 106.09

    def test_missing_sections_yield_none_rather_than_zero(self):
        from wifi_diag.parsers.ookla_parser import parse_ookla

        reading = parse_ookla('{"type":"result"}')
        assert reading == {
            "download_mbps": None,
            "upload_mbps": None,
            "ping_ms": None,
            "download_bytes": None,
        }

    def test_garbage_yields_none(self):
        from wifi_diag.parsers.ookla_parser import parse_ookla

        assert parse_ookla("")["download_mbps"] is None
        assert parse_ookla("[]")["download_mbps"] is None


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
            "device_id": "aa:bb:cc:dd:ee:ff",
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
            # Omitted once, and reverting the Cast wiring left the suite green.
            assert scheduler.cast_collector.interface == "wlan9"
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

    def _stored_speed_reading(self, monkeypatch, reading):
        scheduler, store = self._scheduler(monkeypatch)
        try:
            class Collector:
                def collect(self):
                    return dict(reading)

            scheduler.speed_collector = Collector()
            scheduler._collect_speed()
            rows = store.get_speed_readings()
            assert len(rows) == 1
            return rows[0]
        finally:
            store.close()

    def test_a_verified_reading_keeps_the_interface_the_collector_confirmed(self, monkeypatch):
        row = self._stored_speed_reading(
            monkeypatch,
            {"download_mbps": 84.9, "upload_mbps": 108.7, "ping_ms": 29.4,
             "interface": "wlan0"},
        )
        assert row["interface"] == "wlan0"

    def test_an_unverified_reading_is_stored_without_claiming_an_interface(self, monkeypatch):
        """The scheduler used to stamp its configured interface on every row.

        That made provenance a statement of intent, so a Windows ping or a
        speed test on a host with no byte counters was filed as WiFi, and
        trends compared it against genuinely verified rows.
        """
        row = self._stored_speed_reading(
            monkeypatch,
            {"download_mbps": 84.9, "upload_mbps": 108.7, "ping_ms": 29.4,
             "interface": None},
        )
        assert row["interface"] is None


class TestCastProbeIsPinned:
    """Reachability was measured over whichever link the kernel preferred.

    Its ping was pinned to WiFi while the HTTP probe that decides reachable
    yes/no was not, so a device unreachable over WiFi could still be recorded
    as up because the wire answered for it.
    """

    def _opener_handlers(self, monkeypatch, interface, resolved):
        from wifi_diag.collectors import cast

        monkeypatch.setattr(cast, "interface_ip", lambda iface: resolved)
        monkeypatch.setattr(cast, "parse_eureka_info", lambda text: {"device_id": "aa", "mac": "aa"})
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
