import json


# Cast firmware from the 1.68 series reports this in place of a real address.
PLACEHOLDER_MACS = {"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}


def _real_mac(value):
    """The reported MAC, or None where the firmware declines to give one."""
    if not value:
        return None
    mac = str(value).strip().lower()
    return None if mac in PLACEHOLDER_MACS else mac


def parse_eureka_info(text: str) -> dict:
    """Normalize a Cast device's /setup/eureka_info payload.

    Raises ValueError if the payload is not a Cast device response, which
    is how a non-Cast service listening on port 8008 gets rejected.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("eureka_info response is not valid JSON")

    if not isinstance(data, dict):
        raise ValueError("eureka_info response is not a JSON object")

    mac = _real_mac(data.get("mac_address"))
    udn = (data.get("ssdp_udn") or "").strip() or None

    # Newer firmware reports an all-zero MAC, which every such device shares;
    # keying on it collapses them into one. The UDN is unique and stable.
    device_id = mac or (f"udn:{udn}" if udn else None)
    if not device_id:
        raise ValueError("eureka_info response has no mac_address or ssdp_udn")

    # An empty BSSID means the firmware declines to report it, so unknown.
    bssid = data.get("bssid") or None

    ethernet = data.get("ethernet_connected")

    uptime = data.get("uptime")

    return {
        "device_id": device_id,
        "udn": udn,
        "mac": mac,
        "name": data.get("name"),
        "ip": data.get("ip_address"),
        "ssid": data.get("ssid"),
        "bssid": bssid.lower() if bssid else None,
        "ethernet": bool(ethernet) if ethernet is not None else None,
        "uptime_secs": float(uptime) if uptime is not None else None,
        "firmware": data.get("cast_build_revision"),
    }
