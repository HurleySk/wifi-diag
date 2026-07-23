from datetime import datetime, timedelta, timezone


def band_analysis(store, host=None, days=7):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()

    readings = store.get_wifi_readings(host=host, start=start)
    switches = store.get_band_switches(host=host, start=start)

    hosts_data = {}
    for r in readings:
        h = r["host"]
        if h not in hosts_data:
            hosts_data[h] = {"total": 0, "5ghz_count": 0, "2.4ghz_count": 0, "switch_count": 0}
        hosts_data[h]["total"] += 1
        if r["band"] == "5GHz":
            hosts_data[h]["5ghz_count"] += 1
        elif r["band"] == "2.4GHz":
            hosts_data[h]["2.4ghz_count"] += 1

    for s in switches:
        h = s["host"]
        if h in hosts_data:
            hosts_data[h]["switch_count"] += 1

    for h, d in hosts_data.items():
        d["5ghz_pct"] = round(d["5ghz_count"] / d["total"] * 100, 1) if d["total"] else 0.0

    return {"hosts": hosts_data}
