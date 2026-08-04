import pytest
from wifi_diag.collectors import (
    create_wifi_collector,
    create_latency_collector,
    create_speed_collector,
)
from wifi_diag.store import DiagStore
from wifi_diag.scheduler import DiagScheduler


class TestWifiMockCollector:
    def test_collect_returns_valid_reading(self):
        collector = create_wifi_collector(dry_run=True)
        result = collector.collect()
        assert result["bssid"] is not None
        assert result["frequency_mhz"] is not None
        assert result["band"] in ("2.4GHz", "5GHz")
        assert result["rssi_dbm"] is not None

    def test_collect_alternates_bands(self):
        collector = create_wifi_collector(dry_run=True)
        r1 = collector.collect()
        r2 = collector.collect()
        assert r1["band"] != r2["band"]


class TestLatencyMockCollector:
    def test_collect_gateway(self):
        collector = create_latency_collector("192.168.1.1", dry_run=True)
        result = collector.collect()
        assert result["target"] == "192.168.1.1"
        assert result["rtt_avg_ms"] is not None
        assert result["packet_loss_pct"] is not None

    def test_collect_external(self):
        collector = create_latency_collector("8.8.8.8", dry_run=True)
        result = collector.collect()
        assert result["target"] == "8.8.8.8"
        assert result["rtt_avg_ms"] > 0


class TestSpeedMockCollector:
    def test_collect(self):
        collector = create_speed_collector(dry_run=True)
        result = collector.collect()
        assert result["download_mbps"] is not None
        assert result["upload_mbps"] is not None
        assert result["ping_ms"] is not None


class TestScheduler:
    @pytest.fixture
    def store(self):
        s = DiagStore(":memory:")
        yield s
        s.close()

    def test_collect_once_inserts_wifi(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        readings = store.get_wifi_readings()
        assert len(readings) == 1
        assert readings[0]["band"] in ("2.4GHz", "5GHz")

    def test_collect_once_inserts_latency(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        gateway = store.get_latency_readings(target="192.168.1.1")
        external = store.get_latency_readings(target="8.8.8.8")
        assert len(gateway) == 1
        assert len(external) == 1

    def test_collect_once_inserts_speed(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        readings = store.get_speed_readings()
        assert len(readings) == 1
        assert readings[0]["download_mbps"] == 95.5

    def test_band_switch_detection(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        sched.collect_once()
        switches = store.get_band_switches()
        assert len(switches) == 1
        bands = {switches[0]["from_band"], switches[0]["to_band"]}
        assert bands == {"2.4GHz", "5GHz"}

    def test_no_band_switch_on_same_band(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        sched.collect_once()
        sched.collect_once()
        switches = store.get_band_switches()
        assert len(switches) == 2


class TestCastCollector:
    def test_collect_parses_response(self, monkeypatch):
        from wifi_diag.collectors.cast import CastCollector

        payload = '{"mac_address":"CC:F4:11:A2:D3:AF","bssid":"78:67:0E:6F:A7:FD","name":"Sam Pod","uptime":10.0}'
        c = CastCollector()
        monkeypatch.setattr(c, "_fetch", lambda ip: payload)
        result = c.collect("192.168.1.157")
        assert result["mac"] == "cc:f4:11:a2:d3:af"
        assert result["bssid"] == "78:67:0e:6f:a7:fd"

    def test_collect_propagates_fetch_failure(self, monkeypatch):
        import pytest
        from wifi_diag.collectors.cast import CastCollector

        c = CastCollector()

        def boom(ip):
            raise OSError("connection refused")

        monkeypatch.setattr(c, "_fetch", boom)
        with pytest.raises(OSError):
            c.collect("192.168.1.157")


class TestScanMockCollector:
    def test_returns_rows(self):
        from wifi_diag.collectors.scan_mock import ScanMockCollector

        rows = ScanMockCollector().collect()
        assert len(rows) >= 2
        assert rows[0]["bssid"] == "78:67:0e:6f:a7:fd"
        assert rows[0]["band"] == "5GHz"


class TestCastMockCollector:
    def test_cycles_through_fixtures(self):
        from wifi_diag.collectors.cast_mock import CastMockCollector

        c = CastMockCollector()
        macs = {c.collect("1.2.3.4")["mac"] for _ in range(3)}
        assert len(macs) == 3

    def test_ips_lists_mock_devices(self):
        from wifi_diag.collectors.cast_mock import CastMockCollector

        assert len(CastMockCollector().ips()) == 3


class TestLatencyInterfaceBinding:
    """A dual-homed host routes probes out the preferred interface unless the
    probe is explicitly bound, which silently measures the wrong link."""

    def test_binds_by_device_name_not_address(self, monkeypatch):
        import sys as _sys
        from wifi_diag.collectors.latency import LatencyCollector

        monkeypatch.setattr(_sys, "platform", "linux")
        cmd = LatencyCollector("8.8.8.8", 3, "wlan0")._command()
        assert "-I" in cmd
        # Device name, not address: only SO_BINDTODEVICE forces egress.
        assert cmd[cmd.index("-I") + 1] == "wlan0"

    def test_unbound_when_no_interface_given(self, monkeypatch):
        import sys as _sys
        from wifi_diag.collectors.latency import LatencyCollector

        monkeypatch.setattr(_sys, "platform", "linux")
        assert "-I" not in LatencyCollector("8.8.8.8", 3)._command()

    def test_windows_is_left_unbound(self, monkeypatch):
        import sys as _sys
        from wifi_diag.collectors.latency import LatencyCollector

        monkeypatch.setattr(_sys, "platform", "win32")
        cmd = LatencyCollector("8.8.8.8", 3, "wlan0")._command()
        assert "-I" not in cmd
        assert cmd[0] == "ping"


class TestSpeedInterfaceVerification:
    def _patch(self, monkeypatch, before, after, ip="192.168.1.196"):
        import subprocess
        from wifi_diag.collectors import speed

        class Result:
            stdout = "Ping: 20.0 ms\nDownload: 53.5 Mbit/s\nUpload: 55.6 Mbit/s\n"
            stderr = ""
            returncode = 0

        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return Result()

        snapshots = iter([before, after])
        monkeypatch.setattr(subprocess, "run", run)
        monkeypatch.setattr(speed, "ookla_available", lambda: False)
        monkeypatch.setattr(speed, "interface_ip", lambda i: ip)
        monkeypatch.setattr(speed, "rx_byte_counters", lambda: next(snapshots))
        return calls

    def test_passes_source_address_when_resolvable(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedCollector

        calls = self._patch(
            monkeypatch, {"wlan0": 0, "eth0": 0}, {"wlan0": 90_000_000, "eth0": 100}
        )
        SpeedCollector("wlan0").collect()
        assert "--source" in calls[0]
        assert calls[0][calls[0].index("--source") + 1] == "192.168.1.196"

    def test_accepts_reading_carried_by_the_named_interface(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedCollector

        self._patch(
            monkeypatch, {"wlan0": 0, "eth0": 0}, {"wlan0": 90_000_000, "eth0": 100}
        )
        assert SpeedCollector("wlan0").collect()["download_mbps"] == 53.5

    def test_rejects_reading_that_escaped_over_another_interface(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedCollector, WrongInterfaceError

        # The real failure: eth0 had the lower metric, so the test ran on wire.
        self._patch(
            monkeypatch, {"wlan0": 0, "eth0": 0}, {"wlan0": 4_000, "eth0": 500_000_000}
        )
        with pytest.raises(WrongInterfaceError):
            SpeedCollector("wlan0").collect()

    def test_keeps_reading_when_counters_are_unavailable(self, monkeypatch):
        from wifi_diag.collectors.speed import SpeedCollector

        # No /sys/class/net: unverifiable is not wrong, so the reading stands.
        self._patch(monkeypatch, {}, {})
        assert SpeedCollector("wlan0").collect()["upload_mbps"] == 55.6

    def test_unbound_collector_skips_verification(self, monkeypatch):
        import subprocess
        from wifi_diag.collectors import speed
        from wifi_diag.collectors.speed import SpeedCollector

        class Result:
            stdout = "Download: 400.0 Mbit/s\n"
            stderr = ""
            returncode = 0

        calls = []
        monkeypatch.setattr(subprocess, "run", lambda cmd, **k: (calls.append(cmd), Result())[1])
        monkeypatch.setattr(speed, "ookla_available", lambda: False)
        monkeypatch.setattr(speed, "rx_byte_counters", lambda: pytest.fail("should not snapshot"))
        assert SpeedCollector().collect()["download_mbps"] == 400.0
        assert "--source" not in calls[0]


class TestBusiestInterface:
    def test_names_the_interface_that_moved_the_most(self):
        from wifi_diag.netiface import busiest_interface

        assert busiest_interface(
            {"wlan0": 0, "eth0": 0}, {"wlan0": 10, "eth0": 900}
        ) == "eth0"

    def test_returns_none_when_nothing_moved(self):
        from wifi_diag.netiface import busiest_interface

        assert busiest_interface({"wlan0": 7}, {"wlan0": 7}) is None

    # Loopback and vanished-interface cases moved to test_failure_paths.py.


class TestScanFactory:
    def test_dry_run_returns_mock(self):
        from wifi_diag.collectors import create_scan_collector
        from wifi_diag.collectors.scan_mock import ScanMockCollector

        assert isinstance(create_scan_collector(dry_run=True), ScanMockCollector)

    def test_dry_run_cast_returns_mock(self):
        from wifi_diag.collectors import create_cast_collector
        from wifi_diag.collectors.cast_mock import CastMockCollector

        assert isinstance(create_cast_collector(dry_run=True), CastMockCollector)


class TestScanLinuxCollector:
    def _fake_run(self, calls, results):
        import subprocess

        class Result:
            def __init__(self, rc, out):
                self.returncode = rc
                self.stdout = out

        def run(cmd, **kwargs):
            calls.append(cmd)
            return Result(*results[len(calls) - 1])

        return run

    def test_forces_a_rescan_first(self, monkeypatch):
        import subprocess
        from wifi_diag.collectors.scan_linux import ScanLinuxCollector

        calls = []
        out = "78\\:67\\:0E\\:6F\\:A7\\:FC:BisNet:2462 MHz:11\n"
        monkeypatch.setattr(subprocess, "run", self._fake_run(calls, [(0, out)]))
        rows = ScanLinuxCollector().collect()
        assert calls[0][-2:] == ["--rescan", "yes"]
        assert rows[0]["band"] == "2.4GHz"

    def test_falls_back_to_cache_when_rescan_refused(self, monkeypatch):
        import subprocess
        from wifi_diag.collectors.scan_linux import ScanLinuxCollector

        calls = []
        out = "78\\:67\\:0E\\:6F\\:A7\\:FD:BisNet:5240 MHz:48\n"
        # First call (rescan) is refused, second (cached) succeeds.
        monkeypatch.setattr(subprocess, "run", self._fake_run(calls, [(4, ""), (0, out)]))
        rows = ScanLinuxCollector().collect()
        assert len(calls) == 2
        assert "--rescan" not in calls[1]
        assert rows[0]["channel"] == 48

    def test_falls_back_to_iw_when_nmcli_unavailable(self, monkeypatch):
        import subprocess
        from wifi_diag.collectors.scan_linux import ScanLinuxCollector

        calls = []
        iw_out = "BSS 78:67:0e:6f:a7:fd(on wlan0)\n\tfreq: 5240\n\tSSID: BisNet\n"
        monkeypatch.setattr(
            subprocess, "run", self._fake_run(calls, [(4, ""), (4, ""), (0, iw_out)])
        )
        rows = ScanLinuxCollector().collect()
        assert calls[2][0] == "iw"
        assert rows[0]["bssid"] == "78:67:0e:6f:a7:fd"
