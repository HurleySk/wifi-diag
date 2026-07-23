from datetime import datetime, timedelta, timezone
from .trends import weekly_comparison
from .bands import band_analysis


def diagnose(store, days=7):
    hosts = store.get_hosts()
    if not hosts:
        return "No data collected yet. Run 'wifi-diag collect' first."

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()
    lines = []
    lines.append(f"DIAGNOSIS SUMMARY (last {days} days)")
    lines.append("─" * 40)

    signal_parts = []
    for h in hosts:
        readings = store.get_wifi_readings(host=h, start=start)
        if not readings:
            continue
        rssis = [r["rssi_dbm"] for r in readings if r["rssi_dbm"] is not None]
        if rssis:
            avg = sum(rssis) / len(rssis)
            quality = _signal_quality(avg)
            signal_parts.append(f"{h} avg {avg:.0f}dBm ({quality})")
    if signal_parts:
        lines.append(f"Signal: {', '.join(signal_parts)}")

    ba = band_analysis(store, days=days)
    band_parts = []
    for h, d in ba["hosts"].items():
        band_parts.append(f"{h} {d['5ghz_pct']:.0f}% on 5GHz")
    if band_parts:
        lines.append(f"Band:   {', '.join(band_parts)}")

    lines.append("")

    findings = []

    for h, d in ba["hosts"].items():
        if d["5ghz_pct"] < 50:
            findings.append(
                f"⚠ {h} is spending only {d['5ghz_pct']:.0f}% of time on 5GHz — "
                f"band steering may be pushing it to 2.4GHz."
            )
        if d["switch_count"] > 10:
            findings.append(
                f"⚠ {h} had {d['switch_count']} band switches — "
                f"frequent switching suggests signal instability."
            )

    wc = weekly_comparison(store, weeks=min(4, max(1, days // 7)))
    weeks_with_data = [w for w in wc["weeks"] if w["reading_count"] > 0]
    if len(weeks_with_data) >= 2:
        first = weeks_with_data[-1]
        last = weeks_with_data[0]
        if first["band_5ghz_pct"] is not None and last["band_5ghz_pct"] is not None:
            delta = last["band_5ghz_pct"] - first["band_5ghz_pct"]
            if delta < -10:
                findings.append(
                    f"⚠ 5GHz usage declining: "
                    f"{first['band_5ghz_pct']:.0f}% → {last['band_5ghz_pct']:.0f}% "
                    f"over {len(weeks_with_data)} weeks."
                )
        if first["avg_download"] is not None and last["avg_download"] is not None:
            if last["avg_download"] < first["avg_download"] * 0.8:
                findings.append(
                    f"⚠ Download speed declining: "
                    f"{first['avg_download']:.0f} → {last['avg_download']:.0f} Mbps."
                )

    for h in hosts:
        gw = store.get_latency_readings(host=h, target="192.168.1.1", start=start)
        ext = store.get_latency_readings(host=h, target="8.8.8.8", start=start)
        if gw and ext:
            gw_avg = sum(r["rtt_avg_ms"] for r in gw if r["rtt_avg_ms"]) / len(gw)
            ext_avg = sum(r["rtt_avg_ms"] for r in ext if r["rtt_avg_ms"]) / len(ext)
            if ext_avg > gw_avg * 5:
                findings.append(
                    f"⚠ {h}: gateway latency {gw_avg:.0f}ms vs external {ext_avg:.0f}ms — "
                    f"bottleneck is likely upstream (5G backhaul), not local WiFi."
                )
            elif gw_avg > 20:
                findings.append(
                    f"⚠ {h}: gateway latency {gw_avg:.0f}ms is high — "
                    f"local WiFi congestion or interference likely."
                )

        gw_loss = [r for r in gw if r["packet_loss_pct"] and r["packet_loss_pct"] > 0]
        if gw_loss:
            pct = len(gw_loss) / len(gw) * 100
            findings.append(
                f"⚠ {h}: packet loss to gateway in {pct:.0f}% of probes — "
                f"indicates WiFi instability."
            )

    if findings:
        for f in findings:
            lines.append(f)
    else:
        lines.append("✓ No significant issues detected in the collected data.")

    lines.append("")
    return "\n".join(lines)


def _signal_quality(rssi):
    if rssi >= -50:
        return "excellent"
    if rssi >= -60:
        return "good"
    if rssi >= -70:
        return "fair"
    return "weak"
