import json


def parse_eureka_info(text: str) -> dict:
    """Normalize a Cast device's /setup/eureka_info payload.

    Raises ValueError if the payload is not a Cast device response, which
    is how a non-Cast service listening on port 8008 gets rejected.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("eureka_info response is not valid JSON")

    if not isinstance(data, dict) or not data.get("mac_address"):
        raise ValueError("eureka_info response has no mac_address")

    # An empty BSSID means the firmware declines to report it, so unknown.
    bssid = data.get("bssid") or None

    ethernet = data.get("ethernet_connected")

    uptime = data.get("uptime")

    return {
        "mac": data["mac_address"].lower(),
        "name": data.get("name"),
        "ip": data.get("ip_address"),
        "ssid": data.get("ssid"),
        "bssid": bssid.lower() if bssid else None,
        "ethernet": bool(ethernet) if ethernet is not None else None,
        "uptime_secs": float(uptime) if uptime is not None else None,
        "firmware": data.get("cast_build_revision"),
    }
