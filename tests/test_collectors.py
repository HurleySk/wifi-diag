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
