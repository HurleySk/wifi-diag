import re
from . import freq_to_band, freq_to_channel


def parse_iw_link(output: str) -> dict:
    result = {
        "rssi_dbm": None,
        "noise_dbm": None,
        "frequency_mhz": None,
        "band": None,
        "channel": None,
        "link_speed_mbps": None,
        "bssid": None,
    }

    m = re.search(r"Connected to ([0-9a-f:]+)", output)
    if m:
        result["bssid"] = m.group(1)

    m = re.search(r"freq:\s*(\d+)", output)
    if m:
        freq = int(m.group(1))
        result["frequency_mhz"] = freq
        result["band"] = freq_to_band(freq)
        result["channel"] = freq_to_channel(freq)

    m = re.search(r"signal:\s*(-?\d+)", output)
    if m:
        result["rssi_dbm"] = int(m.group(1))

    m = re.search(r"tx bitrate:\s*([\d.]+)", output)
    if m:
        result["link_speed_mbps"] = float(m.group(1))

    return result
