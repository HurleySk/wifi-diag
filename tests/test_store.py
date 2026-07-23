import pytest
from wifi_diag.store import DiagStore


@pytest.fixture
def store():
    s = DiagStore(":memory:")
    yield s
    s.close()


def _wifi_reading(host="testpi", band="5GHz", rssi=-42, ts="2026-07-20T10:00:00"):
    return {
        "timestamp": ts,
        "host": host,
        "rssi_dbm": rssi,
        "noise_dbm": None,
        "frequency_mhz": 5520,
        "band": band,
        "channel": 104,
        "link_speed_mbps": 866.7,
        "bssid": "aa:bb:cc:dd:ee:ff",
    }


def _latency_reading(host="testpi", target="192.168.1.1", ts="2026-07-20T10:00:00"):
    return {
        "timestamp": ts,
        "host": host,
        "target": target,
        "rtt_min_ms": 1.0,
        "rtt_avg_ms": 2.5,
        "rtt_max_ms": 5.0,
        "packet_loss_pct": 0.0,
    }


def _speed_reading(host="testpi", ts="2026-07-20T10:00:00"):
    return {
        "timestamp": ts,
        "host": host,
        "download_mbps": 95.5,
        "upload_mbps": 45.2,
        "ping_ms": 12.0,
    }


class TestWifiReadings:
    def test_insert_and_get(self, store):
        store.insert_wifi_reading(_wifi_reading())
        rows = store.get_wifi_readings()
        assert len(rows) == 1
        assert rows[0]["rssi_dbm"] == -42
        assert rows[0]["band"] == "5GHz"

    def test_filter_by_host(self, store):
        store.insert_wifi_reading(_wifi_reading(host="pi1"))
        store.insert_wifi_reading(_wifi_reading(host="pi2"))
        rows = store.get_wifi_readings(host="pi1")
        assert len(rows) == 1
        assert rows[0]["host"] == "pi1"

    def test_filter_by_time_range(self, store):
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T08:00:00"))
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T10:00:00"))
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T12:00:00"))
        rows = store.get_wifi_readings(start="2026-07-20T09:00:00", end="2026-07-20T11:00:00")
        assert len(rows) == 1

    def test_get_latest(self, store):
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T08:00:00", rssi=-50))
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T10:00:00", rssi=-42))
        latest = store.get_latest_wifi("testpi")
        assert latest["rssi_dbm"] == -42

    def test_get_latest_none(self, store):
        assert store.get_latest_wifi("nonexistent") is None


class TestBandSwitches:
    def test_insert_and_get(self, store):
        store.insert_band_switch({
            "timestamp": "2026-07-20T10:00:00",
            "host": "testpi",
            "from_band": "5GHz",
            "to_band": "2.4GHz",
            "from_freq": 5520,
            "to_freq": 2437,
        })
        rows = store.get_band_switches()
        assert len(rows) == 1
        assert rows[0]["from_band"] == "5GHz"
        assert rows[0]["to_band"] == "2.4GHz"


class TestLatencyReadings:
    def test_insert_and_get(self, store):
        store.insert_latency_reading(_latency_reading())
        rows = store.get_latency_readings()
        assert len(rows) == 1
        assert rows[0]["rtt_avg_ms"] == 2.5

    def test_filter_by_target(self, store):
        store.insert_latency_reading(_latency_reading(target="192.168.1.1"))
        store.insert_latency_reading(_latency_reading(target="8.8.8.8"))
        rows = store.get_latency_readings(target="8.8.8.8")
        assert len(rows) == 1

    def test_get_latest(self, store):
        store.insert_latency_reading(_latency_reading(ts="2026-07-20T08:00:00"))
        store.insert_latency_reading(_latency_reading(ts="2026-07-20T10:00:00"))
        latest = store.get_latest_latency("testpi", "192.168.1.1")
        assert latest["timestamp"] == "2026-07-20T10:00:00"


class TestSpeedReadings:
    def test_insert_and_get(self, store):
        store.insert_speed_reading(_speed_reading())
        rows = store.get_speed_readings()
        assert len(rows) == 1
        assert rows[0]["download_mbps"] == 95.5

    def test_get_latest(self, store):
        store.insert_speed_reading(_speed_reading(ts="2026-07-20T08:00:00"))
        store.insert_speed_reading(_speed_reading(ts="2026-07-20T10:00:00"))
        latest = store.get_latest_speed("testpi")
        assert latest["timestamp"] == "2026-07-20T10:00:00"


class TestHosts:
    def test_get_hosts(self, store):
        store.insert_wifi_reading(_wifi_reading(host="pi1"))
        store.insert_wifi_reading(_wifi_reading(host="pi2"))
        store.insert_wifi_reading(_wifi_reading(host="pi1"))
        hosts = store.get_hosts()
        assert hosts == ["pi1", "pi2"]
