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
