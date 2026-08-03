import pytest

from wifi_diag.scheduler import DiagScheduler
from wifi_diag.store import DiagStore


@pytest.fixture
def store():
    s = DiagStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def sched(store, monkeypatch):
    monkeypatch.setattr("wifi_diag.scheduler.discover_cast_devices", lambda timeout=None: [])
    return DiagScheduler(store, dry_run=True)


class TestScanCollection:
    def test_scan_populates_band_map(self, sched, store):
        sched._collect_scan()
        rows = store.get_ap_scans()
        assert len(rows) == 3
        assert sched._band_map["78:67:0e:6f:a7:fd"]["band"] == "5GHz"


class TestCastCollection:
    def test_cast_readings_stored_with_band_from_scan(self, sched, store):
        sched._collect_scan()
        sched._collect_cast()
        readings = store.get_cast_readings()
        assert len(readings) == 3
        by_mac = {r["mac"]: r for r in readings}
        assert by_mac["cc:f4:11:a2:d3:af"]["band"] == "5GHz"
        assert by_mac["cc:f4:11:a2:d3:af"]["channel"] == 104
        assert by_mac["d8:8c:79:21:66:8a"]["band"] == "2.4GHz"

    def test_unknown_bssid_yields_null_band(self, sched, store):
        # No scan run, so the band map is empty and band must stay NULL.
        sched._collect_cast()
        readings = store.get_cast_readings()
        assert all(r["band"] is None for r in readings)

    def test_empty_bssid_device_has_null_band(self, sched, store):
        sched._collect_scan()
        sched._collect_cast()
        r = [x for x in store.get_cast_readings() if x["mac"] == "ac:67:84:89:93:63"][0]
        assert r["bssid"] is None
        assert r["band"] is None

    def test_devices_registered(self, sched, store):
        sched._collect_cast()
        devices = store.get_cast_devices()
        assert len(devices) == 3
        assert {d["mac"] for d in devices} == {
            "cc:f4:11:a2:d3:af", "d8:8c:79:21:66:8a", "ac:67:84:89:93:63",
        }

    def test_first_cycle_emits_no_events(self, sched, store):
        sched._collect_cast()
        assert store.get_cast_events() == []

    def test_device_that_changed_ip_keeps_one_identity(self, sched, store):
        """A DHCP lease change must not create a second device record."""
        # Seed the registry with a stale IP for the device the mock will
        # report at 192.168.1.157.
        store.upsert_cast_device({
            "mac": "cc:f4:11:a2:d3:af", "name": "Sam's Pod", "model": None,
            "firmware": None, "last_ip": "192.168.1.99",
            "timestamp": "2026-08-01T10:00:00+00:00",
        })
        sched._collect_cast()
        macs = [d["mac"] for d in store.get_cast_devices()]
        assert macs.count("cc:f4:11:a2:d3:af") == 1
        assert len(set(macs)) == len(macs)

    def test_unreachable_device_recorded_as_not_reachable(self, sched, store, monkeypatch):
        def boom(ip=None):
            raise OSError("refused")

        monkeypatch.setattr(sched.cast_collector, "collect", boom)
        sched._targets = {"cc:f4:11:a2:d3:af": {"ip": "192.168.1.157", "name": "Sam's Pod"}}
        sched._collect_cast()
        readings = store.get_cast_readings()
        assert len(readings) == 1
        assert readings[0]["reachable"] == 0
        assert readings[0]["mac"] == "cc:f4:11:a2:d3:af"


class FakeCastCollector:
    """Unlike CastMockCollector, this respects the IP it is given.

    The mock returns a fixture regardless of address, which is why the
    single-cycle tests above could not catch stale-address bugs.
    """

    def __init__(self, mapping):
        self.mapping = mapping

    def ips(self):
        return list(self.mapping)

    def collect(self, ip=None):
        if ip not in self.mapping:
            raise OSError("connection refused")
        return dict(self.mapping[ip])


def _info(mac, ip, uptime=100.0, bssid="78:67:0e:6f:a7:fd"):
    return {
        "mac": mac, "name": mac.upper(), "ip": ip, "ssid": "BisNet",
        "bssid": bssid, "ethernet": False, "uptime_secs": uptime,
        "firmware": "1.0",
    }


class TestMultiCycle:
    def test_dhcp_move_yields_one_reading_and_no_false_dropout(self, sched, store):
        """A device that changed lease must not also be probed at its old IP."""
        store.upsert_cast_device({
            "mac": "aa", "name": "AA", "model": None, "firmware": None,
            "last_ip": "192.168.1.99", "timestamp": "2026-08-01T00:00:00+00:00",
        })
        sched.cast_collector = FakeCastCollector({"192.168.1.157": _info("aa", "192.168.1.157")})
        sched._collect_cast()

        readings = store.get_cast_readings()
        assert len(readings) == 1
        assert readings[0]["ip"] == "192.168.1.157"
        assert readings[0]["reachable"] == 1
        assert store.get_cast_events() == []

    def test_ip_reuse_evicts_the_stale_device(self, sched, store):
        """When another device takes over an IP, the old MAC must be dropped."""
        sched.cast_collector = FakeCastCollector({"192.168.1.10": _info("aa", "192.168.1.10")})
        sched._collect_cast()

        # bb now owns .10; aa has left the network entirely.
        sched.cast_collector = FakeCastCollector({
            "192.168.1.10": _info("bb", "192.168.1.10"),
            "192.168.1.11": _info("bb", "192.168.1.11"),
        })
        sched._collect_cast()
        sched._collect_cast()

        macs = [r["mac"] for r in store.get_cast_readings()]
        # bb must never get two readings in one cycle, and aa must not linger.
        assert macs.count("aa") == 1
        assert "aa" not in sched._targets
        assert macs.count("bb") <= 3
        assert all(e["mac"] != "aa" for e in store.get_cast_events())

    def test_reboot_is_detected_across_a_missed_poll(self, sched, store):
        """A reboot usually costs a poll; the dropout must not hide it."""
        up = FakeCastCollector({"192.168.1.20": _info("cc", "192.168.1.20", uptime=31568.0)})
        sched.cast_collector = up
        sched._collect_cast()

        sched.cast_collector = FakeCastCollector({})          # device rebooting
        sched._collect_cast()

        sched.cast_collector = FakeCastCollector(
            {"192.168.1.20": _info("cc", "192.168.1.20", uptime=42.0)}
        )
        sched._collect_cast()

        types = [e["event_type"] for e in store.get_cast_events()]
        assert "reboot" in types
        assert types.count("offline") == 1
        assert types.count("online") == 1

    def test_steady_state_emits_no_events(self, sched, store):
        sched.cast_collector = FakeCastCollector({"192.168.1.30": _info("dd", "192.168.1.30")})
        for _ in range(3):
            sched._collect_cast()
        assert store.get_cast_events() == []
        assert len(store.get_cast_readings()) == 3


class TestBandMapSeeding:
    def test_band_map_seeded_from_stored_scans(self, store, monkeypatch):
        monkeypatch.setattr(
            "wifi_diag.scheduler.discover_cast_devices", lambda timeout=None: []
        )
        store.insert_ap_scans([{
            "timestamp": "2026-08-01T00:00:00+00:00", "host": "h",
            "bssid": "78:67:0e:6f:a7:fd", "ssid": "BisNet",
            "frequency_mhz": 5240, "channel": 48, "band": "5GHz",
        }])
        fresh = DiagScheduler(store, dry_run=True)
        assert fresh._band_map["78:67:0e:6f:a7:fd"]["band"] == "5GHz"

    def test_band_survives_a_failed_scan(self, sched, store):
        sched._collect_scan()
        before = dict(sched._band_map)
        sched.scan_collector = type("Empty", (), {"collect": lambda self: []})()
        sched._collect_scan()
        assert sched._band_map == before
