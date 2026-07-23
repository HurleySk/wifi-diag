from datetime import datetime, timedelta, timezone


def weekly_comparison(store, host=None, weeks=4):
    now = datetime.now(timezone.utc)
    result = {"weeks": []}

    for w in range(weeks):
        end = now - timedelta(weeks=w)
        start = end - timedelta(weeks=1)
        start_s = start.isoformat()
        end_s = end.isoformat()

        readings = store.get_wifi_readings(host=host, start=start_s, end=end_s)
        speeds = store.get_speed_readings(host=host, start=start_s, end=end_s)

        week_data = {
            "start": start_s,
            "end": end_s,
            "reading_count": len(readings),
            "avg_rssi": None,
            "avg_download": None,
            "band_5ghz_pct": None,
        }

        if readings:
            rssis = [r["rssi_dbm"] for r in readings if r["rssi_dbm"] is not None]
            if rssis:
                week_data["avg_rssi"] = sum(rssis) / len(rssis)

            fives = sum(1 for r in readings if r["band"] == "5GHz")
            week_data["band_5ghz_pct"] = round(fives / len(readings) * 100, 1)

        if speeds:
            dls = [s["download_mbps"] for s in speeds if s["download_mbps"] is not None]
            if dls:
                week_data["avg_download"] = round(sum(dls) / len(dls), 1)

        result["weeks"].append(week_data)

    return result
