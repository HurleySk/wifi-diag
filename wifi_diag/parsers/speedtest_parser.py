import re


def parse_speedtest(output: str) -> dict:
    result = {
        "download_mbps": None,
        "upload_mbps": None,
        "ping_ms": None,
    }

    m = re.search(r"Ping:\s*([\d.]+)\s*ms", output)
    if m:
        result["ping_ms"] = float(m.group(1))

    m = re.search(r"Download:\s*([\d.]+)\s*Mbit/s", output)
    if m:
        result["download_mbps"] = float(m.group(1))

    m = re.search(r"Upload:\s*([\d.]+)\s*Mbit/s", output)
    if m:
        result["upload_mbps"] = float(m.group(1))

    return result
