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
