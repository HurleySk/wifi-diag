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


def _cast_reading(mac="cc:f4:11:a2:d3:af", band="5GHz", reachable=1,
                  ts="2026-08-01T10:00:00+00:00", uptime=1000.0):
    return {
        "timestamp": ts,
        "host": "testpi",
        "mac": mac,
        "ip": "192.168.1.157",
        "name": "Sam's Pod",
        "ssid": "BisNet",
        "bssid": "78:67:0e:6f:a7:fd",
        "band": band,
        "channel": 104,
        "frequency_mhz": 5520,
        "reachable": reachable,
        "ethernet": 0,
        "uptime_secs": uptime,
        "rtt_avg_ms": 3.2,
        "packet_loss_pct": 0.0,
    }


class TestCastStore:
    def test_upsert_cast_device_inserts_then_updates(self, store):
        store.upsert_cast_device({
            "mac": "cc:f4:11:a2:d3:af", "name": "Sam's Pod", "model": "Nest Hub",
            "firmware": "1.68", "last_ip": "192.168.1.157",
            "timestamp": "2026-08-01T10:00:00+00:00",
        })
        store.upsert_cast_device({
            "mac": "cc:f4:11:a2:d3:af", "name": "Sam's Pod", "model": "Nest Hub",
            "firmware": "1.69", "last_ip": "192.168.1.199",
            "timestamp": "2026-08-02T10:00:00+00:00",
        })
        devices = store.get_cast_devices()
        assert len(devices) == 1
        assert devices[0]["first_seen"] == "2026-08-01T10:00:00+00:00"
        assert devices[0]["last_seen"] == "2026-08-02T10:00:00+00:00"
        assert devices[0]["last_ip"] == "192.168.1.199"
        assert devices[0]["firmware"] == "1.69"

    def test_insert_and_query_cast_readings(self, store):
        store.insert_cast_reading(_cast_reading())
        store.insert_cast_reading(_cast_reading(mac="d8:8c:79:21:66:8a", band="2.4GHz"))
        assert len(store.get_cast_readings()) == 2
        assert len(store.get_cast_readings(mac="cc:f4:11:a2:d3:af")) == 1

    def test_get_cast_readings_filters_by_time(self, store):
        store.insert_cast_reading(_cast_reading(ts="2026-08-01T10:00:00+00:00"))
        store.insert_cast_reading(_cast_reading(ts="2026-08-05T10:00:00+00:00"))
        assert len(store.get_cast_readings(start="2026-08-03T00:00:00+00:00")) == 1

    def test_get_latest_cast_reading(self, store):
        store.insert_cast_reading(_cast_reading(ts="2026-08-01T10:00:00+00:00", uptime=100.0))
        store.insert_cast_reading(_cast_reading(ts="2026-08-02T10:00:00+00:00", uptime=200.0))
        latest = store.get_latest_cast_reading("cc:f4:11:a2:d3:af")
        assert latest["uptime_secs"] == 200.0

    def test_get_latest_cast_reading_missing_returns_none(self, store):
        assert store.get_latest_cast_reading("00:00:00:00:00:00") is None

    def test_insert_and_query_cast_events(self, store):
        store.insert_cast_event({
            "timestamp": "2026-08-01T10:00:00+00:00", "host": "testpi",
            "mac": "cc:f4:11:a2:d3:af", "name": "Sam's Pod",
            "event_type": "band_switch", "detail": '{"from": "5GHz", "to": "2.4GHz"}',
        })
        events = store.get_cast_events(mac="cc:f4:11:a2:d3:af")
        assert len(events) == 1
        assert events[0]["event_type"] == "band_switch"

    def test_bssid_band_map_uses_latest_scan_per_bssid(self, store):
        store.insert_ap_scans([
            {"timestamp": "2026-08-01T10:00:00+00:00", "host": "testpi",
             "bssid": "78:67:0e:6f:a7:fd", "ssid": "BisNet",
             "frequency_mhz": 5520, "channel": 104, "band": "5GHz"},
        ])
        store.insert_ap_scans([
            {"timestamp": "2026-08-02T10:00:00+00:00", "host": "testpi",
             "bssid": "78:67:0e:6f:a7:fd", "ssid": "BisNet",
             "frequency_mhz": 5180, "channel": 36, "band": "5GHz"},
            {"timestamp": "2026-08-02T10:00:00+00:00", "host": "testpi",
             "bssid": "78:67:0e:6f:a7:fc", "ssid": "BisNet",
             "frequency_mhz": 2437, "channel": 6, "band": "2.4GHz"},
        ])
        mapping = store.get_bssid_band_map()
        assert mapping["78:67:0e:6f:a7:fd"]["channel"] == 36
        assert mapping["78:67:0e:6f:a7:fc"]["band"] == "2.4GHz"
        assert len(store.get_ap_scans()) == 3

    def test_new_tables_added_to_preexisting_db(self, tmp_path):
        """A database created before this feature must gain the new tables."""
        import sqlite3
        db = tmp_path / "old.db"
        conn = sqlite3.connect(str(db))
        # The pre-feature wifi_readings schema, verbatim. It must be the real
        # column list: _create_tables() also creates an index on
        # (host, timestamp), which errors against a stub table.
        conn.execute(
            """CREATE TABLE wifi_readings (
                   id INTEGER PRIMARY KEY,
                   timestamp TEXT NOT NULL,
                   host TEXT NOT NULL,
                   rssi_dbm REAL,
                   noise_dbm REAL,
                   frequency_mhz INTEGER,
                   band TEXT,
                   channel INTEGER,
                   link_speed_mbps REAL,
                   bssid TEXT
               )"""
        )
        conn.execute(
            "INSERT INTO wifi_readings (timestamp, host) VALUES ('2026-07-01T00:00:00', 'oldpi')"
        )
        conn.commit()
        conn.close()

        s = DiagStore(str(db))
        s.insert_cast_reading(_cast_reading())
        assert len(s.get_cast_readings()) == 1
        # Pre-existing data must survive the upgrade.
        assert len(s.get_wifi_readings()) == 1
        s.close()
