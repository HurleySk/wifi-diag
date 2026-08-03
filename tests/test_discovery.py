from wifi_diag.discovery import service_info_to_device


class FakeInfo:
    def __init__(self, addresses, properties):
        self._addresses = addresses
        self.properties = properties

    def parsed_addresses(self):
        return self._addresses


class TestServiceInfoToDevice:
    def test_extracts_ip_name_and_model(self):
        info = FakeInfo(["192.168.1.157"], {b"fn": b"Sam's Pod", b"md": b"Nest Hub"})
        device = service_info_to_device(info)
        assert device == {"ip": "192.168.1.157", "name": "Sam's Pod", "model": "Nest Hub"}

    def test_prefers_ipv4_address(self):
        info = FakeInfo(["fe80::1", "192.168.1.160"], {b"fn": b"Speaker"})
        assert service_info_to_device(info)["ip"] == "192.168.1.160"

    def test_missing_txt_fields_become_none(self):
        info = FakeInfo(["192.168.1.152"], {})
        device = service_info_to_device(info)
        assert device["name"] is None
        assert device["model"] is None

    def test_no_address_returns_none(self):
        assert service_info_to_device(FakeInfo([], {b"fn": b"X"})) is None

    def test_no_ipv4_address_returns_none(self):
        assert service_info_to_device(FakeInfo(["fe80::1"], {b"fn": b"X"})) is None

    def test_none_info_returns_none(self):
        assert service_info_to_device(None) is None

    def test_handles_undecodable_txt_bytes(self):
        info = FakeInfo(["192.168.1.157"], {b"fn": b"\xff\xfe bad"})
        assert service_info_to_device(info)["ip"] == "192.168.1.157"


class TestDiscoverFallback:
    def test_returns_empty_when_zeroconf_missing(self, monkeypatch):
        import wifi_diag.discovery as d

        monkeypatch.setattr(d, "_import_zeroconf", lambda: None)
        assert d.discover_cast_devices(timeout=0.01) == []
