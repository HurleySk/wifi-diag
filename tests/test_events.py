import json

from wifi_diag.events import detect_cast_events


def _reading(bssid="78:67:0e:6f:a7:fd", band="5GHz", reachable=1, uptime=1000.0):
    return {
        "bssid": bssid,
        "band": band,
        "reachable": reachable,
        "uptime_secs": uptime,
    }


def _types(events):
    return [e["event_type"] for e in events]


class TestFirstObservation:
    def test_no_previous_reading_emits_nothing(self):
        assert detect_cast_events(None, _reading()) == []


class TestBssidAndBand:
    def test_bssid_change_across_bands_emits_both(self):
        events = detect_cast_events(
            _reading(bssid="78:67:0e:6f:a7:fd", band="5GHz"),
            _reading(bssid="78:67:0e:6f:a7:fc", band="2.4GHz"),
        )
        assert set(_types(events)) == {"bssid_switch", "band_switch"}
        band = [e for e in events if e["event_type"] == "band_switch"][0]
        assert json.loads(band["detail"]) == {"from": "5GHz", "to": "2.4GHz"}

    def test_bssid_change_within_same_band_emits_only_bssid_switch(self):
        events = detect_cast_events(
            _reading(bssid="aa:bb:cc:dd:ee:01", band="5GHz"),
            _reading(bssid="aa:bb:cc:dd:ee:02", band="5GHz"),
        )
        assert _types(events) == ["bssid_switch"]

    def test_unchanged_bssid_emits_nothing(self):
        assert detect_cast_events(_reading(), _reading()) == []

    def test_transition_from_empty_bssid_emits_nothing(self):
        events = detect_cast_events(
            _reading(bssid=None, band=None),
            _reading(bssid="78:67:0e:6f:a7:fd", band="5GHz"),
        )
        assert events == []

    def test_transition_to_empty_bssid_emits_nothing(self):
        events = detect_cast_events(
            _reading(bssid="78:67:0e:6f:a7:fd", band="5GHz"),
            _reading(bssid=None, band=None),
        )
        assert events == []

    def test_band_switch_suppressed_when_a_band_is_unknown(self):
        events = detect_cast_events(
            _reading(bssid="aa:bb:cc:dd:ee:01", band="5GHz"),
            _reading(bssid="aa:bb:cc:dd:ee:02", band=None),
        )
        assert _types(events) == ["bssid_switch"]


class TestReachability:
    def test_going_offline(self):
        events = detect_cast_events(_reading(reachable=1), _reading(reachable=0))
        assert _types(events) == ["offline"]

    def test_coming_online(self):
        events = detect_cast_events(_reading(reachable=0), _reading(reachable=1))
        assert _types(events) == ["online"]

    def test_staying_offline_emits_nothing(self):
        assert detect_cast_events(_reading(reachable=0), _reading(reachable=0)) == []

    def test_offline_suppresses_bssid_comparison(self):
        # An unreachable device reports no BSSID; that must not read as a switch.
        events = detect_cast_events(
            _reading(bssid="78:67:0e:6f:a7:fd", band="5GHz", reachable=1),
            _reading(bssid=None, band=None, reachable=0),
        )
        assert _types(events) == ["offline"]


class TestReboot:
    def test_uptime_decrease_is_a_reboot(self):
        events = detect_cast_events(_reading(uptime=31568.0), _reading(uptime=42.1))
        assert _types(events) == ["reboot"]
        assert json.loads(events[0]["detail"]) == {"from_uptime": 31568.0, "to_uptime": 42.1}

    def test_uptime_increase_is_not_a_reboot(self):
        assert detect_cast_events(_reading(uptime=100.0), _reading(uptime=200.0)) == []

    def test_missing_uptime_emits_nothing(self):
        assert detect_cast_events(_reading(uptime=None), _reading(uptime=50.0)) == []
        assert detect_cast_events(_reading(uptime=50.0), _reading(uptime=None)) == []


class TestCombined:
    def test_reboot_onto_a_different_band(self):
        events = detect_cast_events(
            _reading(bssid="aa:bb:cc:dd:ee:01", band="5GHz", uptime=5000.0),
            _reading(bssid="aa:bb:cc:dd:ee:02", band="2.4GHz", uptime=10.0),
        )
        assert set(_types(events)) == {"bssid_switch", "band_switch", "reboot"}
