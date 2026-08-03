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


class TestDeviceSummary:
    def _store_with_data(self):
        from wifi_diag.store import DiagStore

        s = DiagStore(":memory:")
        for i, (band, reachable) in enumerate([
            ("5GHz", 1), ("5GHz", 1), ("2.4GHz", 1), (None, 0),
        ]):
            s.insert_cast_reading({
                "timestamp": f"2026-08-0{i + 1}T10:00:00+00:00",
                "host": "testpi", "mac": "cc:f4:11:a2:d3:af", "ip": "192.168.1.157",
                "name": "Sam's Pod", "ssid": "BisNet", "bssid": "78:67:0e:6f:a7:fd",
                "band": band, "channel": 104, "frequency_mhz": 5520,
                "reachable": reachable, "ethernet": 0, "uptime_secs": 100.0,
                "rtt_avg_ms": 4.0, "packet_loss_pct": 0.0,
            })
        for etype in ["band_switch", "offline", "reboot", "bssid_switch"]:
            s.insert_cast_event({
                "timestamp": "2026-08-02T10:00:00+00:00", "host": "testpi",
                "mac": "cc:f4:11:a2:d3:af", "name": "Sam's Pod",
                "event_type": etype, "detail": "{}",
            })
        return s

    def test_summary_counts(self):
        from wifi_diag.analysis.devices import device_summary

        s = self._store_with_data()
        result = device_summary(s, days=3650)
        d = result["devices"]["cc:f4:11:a2:d3:af"]
        assert d["name"] == "Sam's Pod"
        assert d["total"] == 4
        assert d["reachable_pct"] == 75.0
        assert d["band_counts"]["5GHz"] == 2
        assert d["band_counts"]["2.4GHz"] == 1
        assert d["dominant_band"] == "5GHz"
        assert d["band_switches"] == 1
        assert d["bssid_switches"] == 1
        assert d["dropouts"] == 1
        assert d["reboots"] == 1
        assert d["avg_rtt_ms"] == 4.0
        s.close()

    def test_empty_store_returns_no_devices(self):
        from wifi_diag.analysis.devices import device_summary
        from wifi_diag.store import DiagStore

        s = DiagStore(":memory:")
        assert device_summary(s, days=7)["devices"] == {}
        s.close()

    def test_device_with_no_known_band_has_none_dominant(self):
        from wifi_diag.analysis.devices import device_summary
        from wifi_diag.store import DiagStore

        s = DiagStore(":memory:")
        s.insert_cast_reading({
            "timestamp": "2026-08-01T10:00:00+00:00", "host": "testpi",
            "mac": "ac:67:84:89:93:63", "ip": "192.168.1.152", "name": "Display",
            "ssid": "BisNet", "bssid": None, "band": None, "channel": None,
            "frequency_mhz": None, "reachable": 1, "ethernet": 0,
            "uptime_secs": 10.0, "rtt_avg_ms": None, "packet_loss_pct": None,
        })
        d = device_summary(s, days=3650)["devices"]["ac:67:84:89:93:63"]
        assert d["dominant_band"] is None
        assert d["avg_rtt_ms"] is None
        s.close()


class TestDiagnoseCastSection:
    def _store_with_flapping_device(self):
        from wifi_diag.store import DiagStore

        s = DiagStore(":memory:")
        s.insert_wifi_reading({
            "timestamp": "2026-08-01T10:00:00+00:00", "host": "testpi",
            "rssi_dbm": -50, "noise_dbm": None, "frequency_mhz": 5520,
            "band": "5GHz", "channel": 104, "link_speed_mbps": 800.0,
            "bssid": "78:67:0e:6f:a7:fd",
        })
        for i in range(10):
            s.insert_cast_reading({
                "timestamp": f"2026-08-01T10:{i:02d}:00+00:00", "host": "testpi",
                "mac": "cc:f4:11:a2:d3:af", "ip": "192.168.1.157",
                "name": "Kitchen Pod", "ssid": "BisNet",
                "bssid": "78:67:0e:6f:a7:fd", "band": "5GHz", "channel": 104,
                "frequency_mhz": 5520, "reachable": 0 if i < 4 else 1,
                "ethernet": 0, "uptime_secs": 100.0, "rtt_avg_ms": 4.0,
                "packet_loss_pct": 0.0,
            })
        for i in range(6):
            s.insert_cast_event({
                "timestamp": f"2026-08-01T10:{i:02d}:00+00:00", "host": "testpi",
                "mac": "cc:f4:11:a2:d3:af", "name": "Kitchen Pod",
                "event_type": "band_switch", "detail": "{}",
            })
        return s

    def test_diagnose_reports_unreachable_device(self):
        from wifi_diag.analysis.diagnose import diagnose

        s = self._store_with_flapping_device()
        out = diagnose(s, days=3650)
        assert "Kitchen Pod" in out
        assert "60%" in out
        s.close()

    def test_diagnose_flags_frequent_band_switching(self):
        from wifi_diag.analysis.diagnose import diagnose

        s = self._store_with_flapping_device()
        out = diagnose(s, days=3650)
        assert "band switches" in out
        s.close()

    def test_diagnose_without_cast_data_is_unchanged(self):
        from wifi_diag.analysis.diagnose import diagnose
        from wifi_diag.store import DiagStore

        s = DiagStore(":memory:")
        s.insert_wifi_reading({
            "timestamp": "2026-08-01T10:00:00+00:00", "host": "testpi",
            "rssi_dbm": -50, "noise_dbm": None, "frequency_mhz": 5520,
            "band": "5GHz", "channel": 104, "link_speed_mbps": 800.0,
            "bssid": "78:67:0e:6f:a7:fd",
        })
        out = diagnose(s, days=3650)
        assert "Cast devices" not in out
        s.close()
