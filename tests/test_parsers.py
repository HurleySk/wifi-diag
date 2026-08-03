from wifi_diag.parsers import freq_to_band, freq_to_channel, channel_to_freq


class TestFreqUtils:
    def test_freq_to_band_2ghz(self):
        assert freq_to_band(2437) == "2.4GHz"

    def test_freq_to_band_5ghz(self):
        assert freq_to_band(5520) == "5GHz"

    def test_freq_to_band_unknown(self):
        assert freq_to_band(900) == "unknown"

    def test_freq_to_channel_2ghz(self):
        assert freq_to_channel(2412) == 1
        assert freq_to_channel(2437) == 6
        assert freq_to_channel(2462) == 11

    def test_freq_to_channel_5ghz(self):
        assert freq_to_channel(5180) == 36
        assert freq_to_channel(5520) == 104
        assert freq_to_channel(5745) == 149

    def test_channel_to_freq_2ghz(self):
        assert channel_to_freq(1, "2.4GHz") == 2412
        assert channel_to_freq(6, "2.4GHz") == 2437
        assert channel_to_freq(11, "2.4GHz") == 2462

    def test_channel_to_freq_5ghz(self):
        assert channel_to_freq(36, "5GHz") == 5180
        assert channel_to_freq(104, "5GHz") == 5520

    def test_roundtrip_2ghz(self):
        for ch in range(1, 14):
            freq = channel_to_freq(ch, "2.4GHz")
            assert freq_to_channel(freq) == ch

    def test_roundtrip_5ghz(self):
        for ch in [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]:
            freq = channel_to_freq(ch, "5GHz")
            assert freq_to_channel(freq) == ch

    def test_freq_to_band_6ghz(self):
        assert freq_to_band(5955) == "6GHz"
        assert freq_to_band(6175) == "6GHz"
        assert freq_to_band(7115) == "6GHz"

    def test_freq_to_band_5ghz_upper_edge(self):
        assert freq_to_band(5825) == "5GHz"
        assert freq_to_band(5895) == "5GHz"

    def test_freq_to_band_above_6ghz_is_unknown(self):
        assert freq_to_band(7300) == "unknown"

    def test_freq_to_channel_6ghz(self):
        assert freq_to_channel(5955) == 1
        assert freq_to_channel(6175) == 45


from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "wifi_diag" / "fixtures"


class TestIwParser:
    def test_parse_5ghz(self):
        from wifi_diag.parsers.iw_parser import parse_iw_link

        output = (FIXTURES / "iw_link_5ghz.txt").read_text()
        result = parse_iw_link(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fd"
        assert result["frequency_mhz"] == 5520
        assert result["band"] == "5GHz"
        assert result["channel"] == 104
        assert result["rssi_dbm"] == -42
        assert result["link_speed_mbps"] == 866.7
        assert result["noise_dbm"] is None

    def test_parse_2ghz(self):
        from wifi_diag.parsers.iw_parser import parse_iw_link

        output = (FIXTURES / "iw_link_2ghz.txt").read_text()
        result = parse_iw_link(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fb"
        assert result["frequency_mhz"] == 2437
        assert result["band"] == "2.4GHz"
        assert result["channel"] == 6
        assert result["rssi_dbm"] == -68
        assert result["link_speed_mbps"] == 72.2


class TestNetshParser:
    def test_parse_5ghz(self):
        from wifi_diag.parsers.netsh_parser import parse_netsh_interfaces

        output = (FIXTURES / "netsh_5ghz.txt").read_text()
        result = parse_netsh_interfaces(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fd"
        assert result["band"] == "5GHz"
        assert result["channel"] == 104
        assert result["frequency_mhz"] == 5520
        assert result["rssi_dbm"] == -61
        assert result["link_speed_mbps"] == 961.0
        assert result["noise_dbm"] is None

    def test_parse_2ghz(self):
        from wifi_diag.parsers.netsh_parser import parse_netsh_interfaces

        output = (FIXTURES / "netsh_2ghz.txt").read_text()
        result = parse_netsh_interfaces(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fb"
        assert result["band"] == "2.4GHz"
        assert result["channel"] == 6
        assert result["frequency_mhz"] == 2437
        assert result["rssi_dbm"] == -72
        assert result["link_speed_mbps"] == 72.0

    def test_fallback_signal_pct_to_rssi(self):
        from wifi_diag.parsers.netsh_parser import parse_netsh_interfaces

        output = "    Band                   : 5 GHz\n    Channel                : 36\n    Signal                 : 80%\n"
        result = parse_netsh_interfaces(output)
        assert result["rssi_dbm"] == -60.0


class TestPingParser:
    def test_parse_linux(self):
        from wifi_diag.parsers.ping_parser import parse_ping

        output = (FIXTURES / "ping_linux.txt").read_text()
        result = parse_ping(output)
        assert result["rtt_min_ms"] == 0.980
        assert result["rtt_avg_ms"] == 1.054
        assert result["rtt_max_ms"] == 1.230
        assert result["packet_loss_pct"] == 0.0

    def test_parse_windows(self):
        from wifi_diag.parsers.ping_parser import parse_ping

        output = (FIXTURES / "ping_windows.txt").read_text()
        result = parse_ping(output)
        assert result["rtt_min_ms"] == 1.0
        assert result["rtt_avg_ms"] == 1.0
        assert result["rtt_max_ms"] == 2.0
        assert result["packet_loss_pct"] == 0.0

    def test_parse_packet_loss(self):
        from wifi_diag.parsers.ping_parser import parse_ping

        output = "5 packets transmitted, 3 received, 40% packet loss, time 4000ms\nrtt min/avg/max/mdev = 1.0/2.0/3.0/0.5 ms"
        result = parse_ping(output)
        assert result["packet_loss_pct"] == 40.0


class TestSpeedtestParser:
    def test_parse(self):
        from wifi_diag.parsers.speedtest_parser import parse_speedtest

        output = (FIXTURES / "speedtest.txt").read_text()
        result = parse_speedtest(output)
        assert result["download_mbps"] == 95.67
        assert result["upload_mbps"] == 45.23
        assert result["ping_ms"] == 12.345

    def test_parse_empty(self):
        from wifi_diag.parsers.speedtest_parser import parse_speedtest

        result = parse_speedtest("")
        assert result["download_mbps"] is None
        assert result["upload_mbps"] is None
        assert result["ping_ms"] is None


class TestEurekaParser:
    def test_parse_newer_firmware(self):
        from wifi_diag.parsers.eureka_parser import parse_eureka_info

        result = parse_eureka_info((FIXTURES / "eureka_pod.json").read_text(encoding="utf-8"))
        assert result["mac"] == "cc:f4:11:a2:d3:af"
        assert result["name"] == "Sam's Pod"
        assert result["ip"] == "192.168.1.157"
        assert result["ssid"] == "BisNet"
        assert result["bssid"] == "78:67:0e:6f:a7:fd"
        assert result["ethernet"] is False
        assert result["uptime_secs"] == 30988.337637
        assert result["firmware"] == "1.68.cast_20251119_1643_RC14.834495410"

    def test_parse_older_firmware(self):
        from wifi_diag.parsers.eureka_parser import parse_eureka_info

        result = parse_eureka_info((FIXTURES / "eureka_speaker.json").read_text(encoding="utf-8"))
        assert result["mac"] == "d8:8c:79:21:66:8a"
        assert result["bssid"] == "78:67:0e:6f:a7:fc"
        assert result["firmware"] == "3.78.540761"

    def test_empty_bssid_becomes_none(self):
        from wifi_diag.parsers.eureka_parser import parse_eureka_info

        result = parse_eureka_info((FIXTURES / "eureka_empty_bssid.json").read_text(encoding="utf-8"))
        assert result["bssid"] is None
        assert result["mac"] == "ac:67:84:89:93:63"

    def test_bssid_is_lowercased(self):
        from wifi_diag.parsers.eureka_parser import parse_eureka_info

        result = parse_eureka_info('{"mac_address":"AA:BB:CC:DD:EE:FF","bssid":"11:22:33:AA:BB:CC"}')
        assert result["bssid"] == "11:22:33:aa:bb:cc"
        assert result["mac"] == "aa:bb:cc:dd:ee:ff"

    def test_missing_optional_fields_are_none(self):
        from wifi_diag.parsers.eureka_parser import parse_eureka_info

        result = parse_eureka_info('{"mac_address":"AA:BB:CC:DD:EE:FF"}')
        assert result["name"] is None
        assert result["ssid"] is None
        assert result["bssid"] is None
        assert result["uptime_secs"] is None
        assert result["ethernet"] is None

    def test_rejects_non_cast_json(self):
        import pytest
        from wifi_diag.parsers.eureka_parser import parse_eureka_info

        with pytest.raises(ValueError):
            parse_eureka_info('{"hello":"world"}')

    def test_rejects_invalid_json(self):
        import pytest
        from wifi_diag.parsers.eureka_parser import parse_eureka_info

        with pytest.raises(ValueError):
            parse_eureka_info("<html>not json</html>")
