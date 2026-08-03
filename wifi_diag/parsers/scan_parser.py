import re
from . import channel_to_freq, freq_to_band, freq_to_channel

# nmcli terse output escapes field-internal colons as "\:". Split only on
# colons that are not preceded by a backslash.
_NMCLI_SPLIT = re.compile(r"(?<!\\):")


def _row(bssid, ssid, frequency_mhz, channel, band):
    return {
        "bssid": bssid.lower(),
        "ssid": ssid,
        "frequency_mhz": frequency_mhz,
        "channel": channel,
        # An unclassifiable frequency is stored as NULL, not as the string
        # "unknown": a non-null band is treated as known everywhere downstream
        # and would otherwise produce band_switch events against "unknown".
        "band": None if band == "unknown" else band,
    }


def parse_nmcli_scan(output: str) -> list:
    rows = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = [f.replace("\\:", ":") for f in _NMCLI_SPLIT.split(line)]
        if len(fields) < 4:
            continue
        bssid, ssid, freq_field, chan_field = fields[0], fields[1], fields[2], fields[3]
        if bssid.count(":") != 5:
            continue
        m = re.search(r"(\d+)", freq_field)
        if not m:
            continue
        freq = int(m.group(1))
        try:
            channel = int(chan_field)
        except ValueError:
            channel = freq_to_channel(freq)
        rows.append(_row(bssid, ssid, freq, channel, freq_to_band(freq)))
    return rows


def parse_iw_scan(output: str) -> list:
    rows = []
    current = None
    for line in output.splitlines():
        m = re.match(r"BSS ([0-9a-fA-F:]{17})", line.strip())
        if m:
            if current:
                rows.append(current)
            current = {"bssid": m.group(1), "ssid": None, "freq": None}
            continue
        if current is None:
            continue
        m = re.search(r"^\s*freq:\s*(\d+)", line)
        if m:
            current["freq"] = int(m.group(1))
            continue
        m = re.search(r"^\s*SSID:\s*(.*)$", line)
        if m:
            current["ssid"] = m.group(1).strip()
    if current:
        rows.append(current)

    result = []
    for c in rows:
        if c["freq"] is None:
            continue
        result.append(
            _row(c["bssid"], c["ssid"], c["freq"], freq_to_channel(c["freq"]),
                 freq_to_band(c["freq"]))
        )
    return result


def parse_netsh_scan(output: str) -> list:
    """Parse `netsh wlan show networks mode=bssid`.

    netsh reports a channel but not a frequency, and some Windows builds omit
    the Band line entirely, so band is inferred from the channel number and the
    frequency is derived from that.
    """
    rows = []
    ssid = None
    pending = None

    for line in output.splitlines():
        m = re.match(r"\s*SSID\s+\d+\s*:\s*(.*)$", line)
        if m:
            ssid = m.group(1).strip()
            continue
        m = re.match(r"\s*BSSID\s+\d+\s*:\s*([0-9a-fA-F:]{17})", line)
        if m:
            if pending:
                rows.append(pending)
            pending = {"bssid": m.group(1), "ssid": ssid, "channel": None, "band": None}
            continue
        if pending is None:
            continue
        m = re.match(r"\s*Band\s*:\s*([\d.]+)\s*GHz", line)
        if m:
            pending["band"] = "2.4GHz" if m.group(1).startswith("2") else (
                "6GHz" if m.group(1).startswith("6") else "5GHz"
            )
            continue
        m = re.match(r"\s*Channel\s*:\s*(\d+)", line)
        if m:
            pending["channel"] = int(m.group(1))
    if pending:
        rows.append(pending)

    result = []
    for c in rows:
        if c["channel"] is None:
            continue
        band = c["band"] or ("2.4GHz" if c["channel"] <= 14 else "5GHz")
        result.append(
            _row(c["bssid"], c["ssid"], channel_to_freq(c["channel"], band),
                 c["channel"], band)
        )
    return result
