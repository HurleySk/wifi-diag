def freq_to_band(freq_mhz: int) -> str:
    if 2400 <= freq_mhz <= 2500:
        return "2.4GHz"
    if 5000 <= freq_mhz <= 6000:
        return "5GHz"
    return "unknown"


def freq_to_channel(freq_mhz: int) -> int:
    if 2412 <= freq_mhz <= 2472:
        return (freq_mhz - 2407) // 5
    if freq_mhz == 2484:
        return 14
    if 5180 <= freq_mhz <= 5825:
        return (freq_mhz - 5000) // 5
    return 0


def channel_to_freq(channel: int, band: str) -> int:
    if band == "2.4GHz":
        if 1 <= channel <= 13:
            return 2407 + channel * 5
        if channel == 14:
            return 2484
    if band == "5GHz":
        return 5000 + channel * 5
    return 0
