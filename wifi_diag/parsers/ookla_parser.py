from .json_output import load_json_object


def parse_ookla(output: str) -> dict:
    """Parse `speedtest --format=json` from Ookla's official CLI.

    Bandwidth is reported in bytes per second, not bits, so a naive reading of
    the field understates the link by a factor of eight. The byte totals are
    what the collector checks the interface counters against.
    """
    result = {
        "download_mbps": None,
        "upload_mbps": None,
        "ping_ms": None,
        "download_bytes": None,
    }

    data = load_json_object(output)
    if data is None:
        return result

    ping = data.get("ping")
    if isinstance(ping, dict) and isinstance(ping.get("latency"), (int, float)):
        result["ping_ms"] = round(float(ping["latency"]), 2)

    for key, field in (("download", "download_mbps"), ("upload", "upload_mbps")):
        section = data.get(key)
        if not isinstance(section, dict):
            continue
        bandwidth = section.get("bandwidth")
        if isinstance(bandwidth, (int, float)):
            result[field] = round(float(bandwidth) * 8 / 1_000_000, 2)

    download = data.get("download")
    if isinstance(download, dict) and isinstance(download.get("bytes"), (int, float)):
        result["download_bytes"] = int(download["bytes"])

    return result
