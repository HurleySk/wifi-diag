import json


def parse_ookla(output: str) -> dict:
    """Parse `speedtest --format=json` from Ookla's official CLI.

    Bandwidth is reported in bytes per second, not bits, so a naive reading of
    the field understates the link by a factor of eight.
    """
    result = {
        "download_mbps": None,
        "upload_mbps": None,
        "ping_ms": None,
    }

    data = _load(output)
    if not isinstance(data, dict):
        return result

    ping = data.get("ping")
    if isinstance(ping, dict) and isinstance(ping.get("latency"), (int, float)):
        result["ping_ms"] = round(float(ping["latency"]), 2)

    for key, field in (("download", "download_mbps"), ("upload", "upload_mbps")):
        section = data.get(key)
        if isinstance(section, dict):
            bandwidth = section.get("bandwidth")
            if isinstance(bandwidth, (int, float)):
                result[field] = round(float(bandwidth) * 8 / 1_000_000, 2)

    return result


def _load(output):
    if not output:
        return None
    try:
        return json.loads(output)
    except (ValueError, TypeError):
        pass
    # A stray progress or banner line leaves the result object on its own line.
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None
