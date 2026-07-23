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
