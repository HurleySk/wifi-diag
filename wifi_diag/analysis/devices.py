from collections import Counter
from datetime import datetime, timedelta, timezone

_EVENT_KEYS = {
    "band_switch": "band_switches",
    "bssid_switch": "bssid_switches",
    "offline": "dropouts",
    "reboot": "reboots",
    "identity_clash": "identity_clashes",
}


def device_summary(store, days=7):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    readings = store.get_cast_readings(start=start)
    events = store.get_cast_events(start=start)

    by_device = {}
    for r in readings:
        by_device.setdefault(r["device_id"], []).append(r)

    events_by_device = {}
    for e in events:
        events_by_device.setdefault(e["device_id"], []).append(e)

    devices = {}
    seen_only_in_events = [d for d in events_by_device if d not in by_device]
    for device_id in list(by_device) + seen_only_in_events:
        rows = by_device.get(device_id, [])
        events = events_by_device.get(device_id, [])
        total = len(rows)
        reachable = sum(1 for r in rows if r["reachable"])
        bands = Counter(r["band"] for r in rows if r["band"])
        rtts = [r["rtt_avg_ms"] for r in rows if r["rtt_avg_ms"] is not None]
        counts = Counter(e["event_type"] for e in events)

        named = [r["name"] for r in reversed(rows) if r["name"]]
        named += [e["name"] for e in reversed(events) if e["name"]]
        summary = {
            "name": next(iter(named), None),
            "total": total,
            "reachable_pct": reachable / total * 100 if total else 0.0,
            "band_counts": dict(bands),
            "dominant_band": bands.most_common(1)[0][0] if bands else None,
            "avg_rtt_ms": sum(rtts) / len(rtts) if rtts else None,
            "last_seen": rows[-1]["timestamp"] if rows else events[-1]["timestamp"],
            "last_ip": rows[-1]["ip"] if rows else None,
        }
        for event_type, key in _EVENT_KEYS.items():
            summary[key] = counts.get(event_type, 0)
        devices[device_id] = summary

    return {"days": days, "devices": devices}
