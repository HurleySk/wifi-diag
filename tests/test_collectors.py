from wifi_diag.collectors import (
    create_wifi_collector,
    create_latency_collector,
    create_speed_collector,
)


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
