from .json_output import load_json_object


def parse_speedtest(output: str) -> dict:
    """Parse `speedtest-cli --json` from the pip client.

    Speeds are bits per second here, unlike Ookla's CLI, which reports bytes
    per second. `--json` rather than `--simple` because only the former
    reports bytes_received, which is what lets the collector tell a reading
    carried by the named interface from one that straddled two.
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

    for key, field in (("download", "download_mbps"), ("upload", "upload_mbps")):
        value = data.get(key)
        if isinstance(value, (int, float)):
            result[field] = round(float(value) / 1_000_000, 2)

    if isinstance(data.get("ping"), (int, float)):
        result["ping_ms"] = round(float(data["ping"]), 3)

    if isinstance(data.get("bytes_received"), (int, float)):
        result["download_bytes"] = int(data["bytes_received"])

    return result
