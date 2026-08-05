import json

import pytest

from wifi_diag.parsers.eureka_parser import parse_eureka_info
from wifi_diag.scheduler import DiagScheduler
from wifi_diag.store import DiagStore


def eureka(mac=None, udn=None, ip=None, name=None, uptime=100.0,
           bssid="78:67:0e:6f:a7:fd"):
    return parse_eureka_info(json.dumps({
        "mac_address": mac, "ssdp_udn": udn, "name": name, "ip_address": ip,
        "ssid": "BisNet", "bssid": bssid, "ethernet_connected": False,
        "uptime": uptime, "cast_build_revision": "1.68.cast",
    }))


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
        assert len(readings) == 4
        by_id = {r["device_id"]: r for r in readings}
        assert by_id["cc:f4:11:a2:d3:af"]["band"] == "5GHz"
        assert by_id["cc:f4:11:a2:d3:af"]["channel"] == 104
        assert by_id["d8:8c:79:21:66:8a"]["band"] == "2.4GHz"

    def test_unknown_bssid_yields_null_band(self, sched, store):
        # No scan run, so the band map is empty and band must stay NULL.
        sched._collect_cast()
        readings = store.get_cast_readings()
        assert all(r["band"] is None for r in readings)

    def test_empty_bssid_device_has_null_band(self, sched, store):
        sched._collect_scan()
        sched._collect_cast()
        r = [x for x in store.get_cast_readings() if x["device_id"] == "ac:67:84:89:93:63"][0]
        assert r["bssid"] is None
        assert r["band"] is None

    def test_devices_registered(self, sched, store):
        sched._collect_cast()
        devices = store.get_cast_devices()
        assert len(devices) == 4
        assert {d["device_id"] for d in devices} == {
            "cc:f4:11:a2:d3:af", "d8:8c:79:21:66:8a", "ac:67:84:89:93:63",
            "udn:5f00bcbf-c61c-1622-325d-d3b1fa3c4e37",
        }

    def test_first_cycle_emits_no_events(self, sched, store):
        sched._collect_cast()
        assert store.get_cast_events() == []

    def test_device_that_changed_ip_keeps_one_identity(self, sched, store):
        """A DHCP lease change must not create a second device record."""
        # Seed a stale IP for the device the mock reports at 192.168.1.157.
        store.upsert_cast_device({
            "device_id": "cc:f4:11:a2:d3:af", "name": "Sam's Pod", "model": None,
            "firmware": None, "last_ip": "192.168.1.99",
            "timestamp": "2026-08-01T10:00:00+00:00",
        })
        sched._collect_cast()
        ids = [d["device_id"] for d in store.get_cast_devices()]
        assert ids.count("cc:f4:11:a2:d3:af") == 1
        assert len(set(ids)) == len(ids)

    def test_unreachable_device_recorded_as_not_reachable(self, sched, store, monkeypatch):
        def boom(ip=None):
            raise OSError("refused")

        monkeypatch.setattr(sched.cast_collector, "collect", boom)
        sched._targets = {"cc:f4:11:a2:d3:af": {"ip": "192.168.1.157", "name": "Sam's Pod"}}
        sched._collect_cast()
        readings = store.get_cast_readings()
        assert len(readings) == 1
        assert readings[0]["reachable"] == 0
        assert readings[0]["device_id"] == "cc:f4:11:a2:d3:af"


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
    return eureka(mac=mac, udn=f"udn-{mac}", ip=ip, name=mac.upper(),
                  uptime=uptime, bssid=bssid)


class TestMultiCycle:
    def test_dhcp_move_yields_one_reading_and_no_false_dropout(self, sched, store):
        """A device that changed lease must not also be probed at its old IP."""
        store.upsert_cast_device({
            "device_id": "aa", "name": "AA", "model": None, "firmware": None,
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

        macs = [r["device_id"] for r in store.get_cast_readings()]
        # bb must never get two readings in one cycle, and aa must not linger.
        assert macs.count("aa") == 1
        assert "aa" not in sched._targets
        assert macs.count("bb") <= 3
        assert all(e["device_id"] != "aa" for e in store.get_cast_events())

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


class TestSharedIdentity:
    """Firmware 1.68 reports no MAC, so several devices once looked like one."""

    def _udn_info(self, udn, ip, name):
        return eureka(udn=udn, ip=ip, name=name)

    def test_devices_without_macs_stay_separate(self, sched, store):
        sched.cast_collector = FakeCastCollector({
            "192.168.1.161": self._udn_info("aaa", "192.168.1.161", "Kitchen Pod"),
            "192.168.1.163": self._udn_info("bbb", "192.168.1.163", "BigBoiTV"),
        })
        sched._collect_cast()

        readings = store.get_cast_readings()
        assert {r["device_id"] for r in readings} == {"udn:aaa", "udn:bbb"}
        assert {r["name"] for r in readings} == {"Kitchen Pod", "BigBoiTV"}
        # No MAC was reported, so none may be invented.
        assert all(r["mac"] is None for r in readings)

    def test_clashing_identity_is_recorded_not_dropped(self, sched, store):
        """Two addresses, one identity: the loser must leave a trace."""
        sched.cast_collector = FakeCastCollector({
            "192.168.1.161": self._udn_info("same", "192.168.1.161", "Kitchen Pod"),
            "192.168.1.163": self._udn_info("same", "192.168.1.163", "BigBoiTV"),
        })
        sched._collect_cast()

        assert len(store.get_cast_readings()) == 1
        clashes = [e for e in store.get_cast_events()
                   if e["event_type"] == "identity_clash"]
        assert len(clashes) == 1
        assert "192.168.1.163" in clashes[0]["detail"]

    def test_clash_detail_names_the_entry_that_lost_its_reading(self, sched, store):
        store.upsert_cast_device({
            "device_id": "stale-entry", "name": "BigBoiTV", "model": None,
            "firmware": None, "last_ip": "192.168.1.163",
            "timestamp": "2026-08-01T00:00:00+00:00",
        })
        sched.cast_collector = FakeCastCollector({
            "192.168.1.161": self._udn_info("same", "192.168.1.161", "Kitchen Pod"),
            "192.168.1.163": self._udn_info("same", "192.168.1.163", "BigBoiTV"),
        })
        sched._collect_cast()

        clash = [e for e in store.get_cast_events()
                 if e["event_type"] == "identity_clash"][0]
        detail = json.loads(clash["detail"])
        assert detail == {"ip": "192.168.1.163", "suppressed_id": "stale-entry"}


class TestMigratedGhosts:
    """History the migration split by name is not a device that can be probed."""

    def test_a_split_out_fragment_never_clashes_with_the_real_device(
        self, legacy_cast_db, monkeypatch
    ):
        monkeypatch.setattr(
            "wifi_diag.scheduler.discover_cast_devices", lambda timeout=None: []
        )
        db = legacy_cast_db(
            [("00:00:00:00:00:00", "BigBoiTV", "192.168.1.163")],
            [("00:00:00:00:00:00", "BigBoiTV", "192.168.1.163")],
        )
        store = DiagStore(db)
        try:
            sched = DiagScheduler(store, dry_run=True)
            sched.cast_collector = FakeCastCollector({
                "192.168.1.163": eureka(
                    udn="udn-tv", ip="192.168.1.163", name="BigBoiTV"
                ),
            })
            for _ in range(3):
                sched._collect_cast()

            assert [e for e in store.get_cast_events()
                    if e["event_type"] == "identity_clash"] == []
            assert len(store.get_cast_readings(device_id="udn:udn-tv")) == 3
        finally:
            store.close()


class TestTransientMacLoss:
    """A Cast device can blank its MAC for a while and then report it again."""

    def _info(self, mac, udn, ip, name):
        return eureka(mac=mac, udn=udn, ip=ip, name=name)

    def test_identity_survives_the_mac_blanking_out(self, sched, store):
        real = self._info("cc:f4:11:cc:d2:e8", "udn-kitchen", "192.168.1.161", "Kitchen Pod")
        blank = self._info(None, "udn-kitchen", "192.168.1.161", "Kitchen Pod")

        sched.cast_collector = FakeCastCollector({"192.168.1.161": real})
        sched._collect_cast()
        sched.cast_collector = FakeCastCollector({"192.168.1.161": blank})
        sched._collect_cast()
        sched.cast_collector = FakeCastCollector({"192.168.1.161": real})
        sched._collect_cast()

        ids = {r["device_id"] for r in store.get_cast_readings()}
        assert ids == {"cc:f4:11:cc:d2:e8"}
        assert len(store.get_cast_readings()) == 3

    def test_blanked_mac_does_not_merge_two_devices(self, sched, store):
        """The UDN still separates devices that have never reported a MAC."""
        sched.cast_collector = FakeCastCollector({
            "192.168.1.161": self._info(None, "udn-kitchen", "192.168.1.161", "Kitchen Pod"),
            "192.168.1.163": self._info(None, "udn-tv", "192.168.1.163", "BigBoiTV"),
        })
        sched._collect_cast()

        ids = {r["device_id"] for r in store.get_cast_readings()}
        assert ids == {"udn:udn-kitchen", "udn:udn-tv"}

    def test_udn_mapping_is_reloaded_from_the_registry(self, sched, store):
        """A restart must not fork the identity of a device mid-blackout."""
        store.upsert_cast_device({
            "device_id": "cc:f4:11:cc:d2:e8", "mac": "cc:f4:11:cc:d2:e8",
            "udn": "udn-kitchen", "name": "Kitchen Pod", "model": None,
            "firmware": None, "last_ip": "192.168.1.161",
            "timestamp": "2026-08-01T00:00:00+00:00",
        })
        sched.cast_collector = FakeCastCollector({
            "192.168.1.161": self._info(None, "udn-kitchen", "192.168.1.161", "Kitchen Pod"),
        })
        sched._collect_cast()

        assert [r["device_id"] for r in store.get_cast_readings()] == ["cc:f4:11:cc:d2:e8"]

    def test_identity_survives_a_mac_appearing_for_the_first_time(self, sched, store):
        """The device was first seen without a MAC, so the UDN key is the one."""
        blank = self._info(None, "udn-tv", "192.168.1.163", "BigBoiTV")
        real = self._info("cc:f4:11:aa:bb:cc", "udn-tv", "192.168.1.163", "BigBoiTV")

        sched.cast_collector = FakeCastCollector({"192.168.1.163": blank})
        sched._collect_cast()
        sched.cast_collector = FakeCastCollector({"192.168.1.163": real})
        sched._collect_cast()
        sched._collect_cast()

        assert {r["device_id"] for r in store.get_cast_readings()} == {"udn:udn-tv"}
        assert [d["device_id"] for d in store.get_cast_devices()] == ["udn:udn-tv"]
        assert store.get_cast_devices()[0]["mac"] == "cc:f4:11:aa:bb:cc"

    def test_identity_is_stable_when_the_registry_already_forked(self, sched, store):
        """Two rows, one UDN: whichever is picked must not vary by name order."""
        for device_id, mac, name in [
            ("udn:udn-tv", None, "aaa-first-by-name"),
            ("cc:f4:11:aa:bb:cc", "cc:f4:11:aa:bb:cc", "zzz-later-by-name"),
        ]:
            store.upsert_cast_device({
                "device_id": device_id, "mac": mac, "udn": "udn-tv", "name": name,
                "model": None, "firmware": None, "last_ip": None,
                "timestamp": "2026-08-01T00:00:00+00:00",
            })
        sched.cast_collector = FakeCastCollector({
            "192.168.1.163": self._info(None, "udn-tv", "192.168.1.163", "BigBoiTV"),
        })
        sched._collect_cast()

        assert [r["device_id"] for r in store.get_cast_readings()] == ["cc:f4:11:aa:bb:cc"]
