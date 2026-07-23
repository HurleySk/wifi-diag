import pytest
from datetime import datetime, timedelta, timezone
from wifi_diag.store import DiagStore
from wifi_diag.analysis.trends import weekly_comparison
from wifi_diag.analysis.bands import band_analysis
from wifi_diag.analysis.diagnose import diagnose


@pytest.fixture
def store():
    s = DiagStore(":memory:")
    yield s
    s.close()


def _seed_wifi(store, host, band, rssi, days_ago):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    freq = 5520 if band == "5GHz" else 2437
    ch = 104 if band == "5GHz" else 6
    store.insert_wifi_reading({
        "timestamp": ts, "host": host, "rssi_dbm": rssi,
        "noise_dbm": None, "frequency_mhz": freq, "band": band,
        "channel": ch, "link_speed_mbps": 100.0, "bssid": "aa:bb:cc:dd:ee:ff",
    })


def _seed_latency(store, host, target, avg_ms, days_ago):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    store.insert_latency_reading({
        "timestamp": ts, "host": host, "target": target,
        "rtt_min_ms": avg_ms * 0.8, "rtt_avg_ms": avg_ms,
        "rtt_max_ms": avg_ms * 1.5, "packet_loss_pct": 0.0,
    })


def _seed_speed(store, host, download, days_ago):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    store.insert_speed_reading({
        "timestamp": ts, "host": host,
        "download_mbps": download, "upload_mbps": download * 0.5,
        "ping_ms": 12.0,
    })


class TestWeeklyComparison:
    def test_returns_weekly_buckets(self, store):
        for d in range(28):
            _seed_wifi(store, "pi1", "5GHz", -45, d)
        result = weekly_comparison(store, "pi1", weeks=4)
        assert len(result["weeks"]) == 4

    def test_calculates_avg_rssi(self, store):
        _seed_wifi(store, "pi1", "5GHz", -40, 1)
        _seed_wifi(store, "pi1", "5GHz", -50, 2)
        result = weekly_comparison(store, "pi1", weeks=1)
        assert result["weeks"][0]["avg_rssi"] == -45.0

    def test_empty_store(self, store):
        result = weekly_comparison(store, "pi1", weeks=4)
        assert all(w["reading_count"] == 0 for w in result["weeks"])


class TestBandAnalysis:
    def test_calculates_band_split(self, store):
        for _ in range(7):
            _seed_wifi(store, "pi1", "5GHz", -42, 1)
        for _ in range(3):
            _seed_wifi(store, "pi1", "2.4GHz", -68, 1)
        result = band_analysis(store, "pi1", days=7)
        assert result["hosts"]["pi1"]["5ghz_pct"] == 70.0

    def test_includes_switch_count(self, store):
        _seed_wifi(store, "pi1", "5GHz", -42, 1)
        _seed_wifi(store, "pi1", "2.4GHz", -68, 1)
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        store.insert_band_switch({
            "timestamp": ts, "host": "pi1",
            "from_band": "5GHz", "to_band": "2.4GHz",
            "from_freq": 5520, "to_freq": 2437,
        })
        result = band_analysis(store, "pi1", days=7)
        assert result["hosts"]["pi1"]["switch_count"] == 1

    def test_multiple_hosts(self, store):
        _seed_wifi(store, "pi1", "5GHz", -42, 1)
        _seed_wifi(store, "pi2", "2.4GHz", -68, 1)
        result = band_analysis(store, days=7)
        assert "pi1" in result["hosts"]
        assert "pi2" in result["hosts"]


class TestDiagnose:
    def test_returns_string(self, store):
        _seed_wifi(store, "pi1", "5GHz", -42, 1)
        _seed_latency(store, "pi1", "192.168.1.1", 2.0, 1)
        _seed_latency(store, "pi1", "8.8.8.8", 15.0, 1)
        _seed_speed(store, "pi1", 95.0, 1)
        result = diagnose(store, days=7)
        assert isinstance(result, str)
        assert "pi1" in result

    def test_empty_store(self, store):
        result = diagnose(store, days=7)
        assert "No data" in result or "no data" in result.lower()
