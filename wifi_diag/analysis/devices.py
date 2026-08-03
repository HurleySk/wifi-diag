from collections import Counter
from datetime import datetime, timedelta, timezone

_EVENT_KEYS = {
    "band_switch": "band_switches",
    "bssid_switch": "bssid_switches",
    "offline": "dropouts",
    "reboot": "reboots",
}


def device_summary(store, days=7):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    readings = store.get_cast_readings(start=start)
    events = store.get_cast_events(start=start)

    by_mac = {}
    for r in readings:
        by_mac.setdefault(r["mac"], []).append(r)

    events_by_mac = {}
    for e in events:
        events_by_mac.setdefault(e["mac"], []).append(e)

    devices = {}
    for mac, rows in by_mac.items():
        total = len(rows)
        reachable = sum(1 for r in rows if r["reachable"])
        bands = Counter(r["band"] for r in rows if r["band"])
        rtts = [r["rtt_avg_ms"] for r in rows if r["rtt_avg_ms"] is not None]
        counts = Counter(e["event_type"] for e in events_by_mac.get(mac, []))

        summary = {
            "name": next((r["name"] for r in reversed(rows) if r["name"]), None),
            "total": total,
            "reachable_pct": reachable / total * 100 if total else 0.0,
            "band_counts": dict(bands),
            "dominant_band": bands.most_common(1)[0][0] if bands else None,
            "avg_rtt_ms": sum(rtts) / len(rtts) if rtts else None,
            "last_seen": rows[-1]["timestamp"],
            "last_ip": rows[-1]["ip"],
        }
        for event_type, key in _EVENT_KEYS.items():
            summary[key] = counts.get(event_type, 0)
        devices[mac] = summary

    return {"days": days, "devices": devices}
