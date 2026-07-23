import re


def parse_ping(output: str) -> dict:
    result = {
        "rtt_min_ms": None,
        "rtt_avg_ms": None,
        "rtt_max_ms": None,
        "packet_loss_pct": None,
    }

    m = re.search(r"(\d+(?:\.\d+)?)%\s*(?:packet\s+)?loss", output)
    if m:
        result["packet_loss_pct"] = float(m.group(1))

    m = re.search(
        r"rtt min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)", output
    )
    if m:
        result["rtt_min_ms"] = float(m.group(1))
        result["rtt_avg_ms"] = float(m.group(2))
        result["rtt_max_ms"] = float(m.group(3))
        return result

    m = re.search(
        r"Minimum\s*=\s*(\d+)ms.*Maximum\s*=\s*(\d+)ms.*Average\s*=\s*(\d+)ms",
        output,
        re.DOTALL,
    )
    if m:
        result["rtt_min_ms"] = float(m.group(1))
        result["rtt_max_ms"] = float(m.group(2))
        result["rtt_avg_ms"] = float(m.group(3))

    return result
