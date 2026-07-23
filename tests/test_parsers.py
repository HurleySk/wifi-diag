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
