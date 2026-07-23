import re
from . import channel_to_freq


def parse_netsh_interfaces(output: str) -> dict:
    result = {
        "rssi_dbm": None,
        "noise_dbm": None,
        "frequency_mhz": None,
        "band": None,
        "channel": None,
        "link_speed_mbps": None,
        "bssid": None,
    }

    def extract(pattern):
        m = re.search(pattern, output, re.IGNORECASE)
        return m.group(1).strip() if m else None

    bssid = extract(r"BSSID\s*:\s*([0-9a-f:]+)")
    if bssid:
        result["bssid"] = bssid

    band_str = extract(r"Band\s*:\s*(.+)")
    if band_str:
        result["band"] = band_str.replace(" ", "")

    channel_str = extract(r"Channel\s*:\s*(\d+)")
    if channel_str:
        result["channel"] = int(channel_str)

    if result["channel"] and result["band"]:
        result["frequency_mhz"] = channel_to_freq(result["channel"], result["band"])

    rssi_str = extract(r"Rssi\s*:\s*(-?\d+)")
    if rssi_str:
        result["rssi_dbm"] = int(rssi_str)
    else:
        signal_str = extract(r"Signal\s*:\s*(\d+)%")
        if signal_str:
            result["rssi_dbm"] = int(signal_str) / 2 - 100

    rx_rate = extract(r"Receive rate \(Mbps\)\s*:\s*([\d.]+)")
    tx_rate = extract(r"Transmit rate \(Mbps\)\s*:\s*([\d.]+)")
    rates = [float(r) for r in [rx_rate, tx_rate] if r]
    if rates:
        result["link_speed_mbps"] = max(rates)

    return result
