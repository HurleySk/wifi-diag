from datetime import datetime, timedelta, timezone
from .. import config
from .trends import weekly_comparison
from .bands import band_analysis
from .devices import device_summary


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
        gw = store.get_latency_readings(host=h, target=config.GATEWAY_TARGET, start=start)
        ext = store.get_latency_readings(host=h, target=config.EXTERNAL_TARGET, start=start)
        if gw and ext:
            gw_valid = [r["rtt_avg_ms"] for r in gw if r["rtt_avg_ms"]]
            ext_valid = [r["rtt_avg_ms"] for r in ext if r["rtt_avg_ms"]]
            if not gw_valid or not ext_valid:
                continue
            gw_avg = sum(gw_valid) / len(gw_valid)
            ext_avg = sum(ext_valid) / len(ext_valid)
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

    cast = device_summary(store, days=days)["devices"]
    if cast:
        lines.append("")
        lines.append(f"Cast devices ({len(cast)}):")
        for mac, d in sorted(cast.items(), key=lambda kv: (kv[1]["name"] or kv[0])):
            band = d["dominant_band"] or "band unknown"
            lines.append(
                f"  {d['name'] or mac}: {d['reachable_pct']:.0f}% reachable, "
                f"{band}, {d['band_switches']} band switches, {d['reboots']} reboots"
            )

        for mac, d in cast.items():
            label = d["name"] or mac
            if d["reachable_pct"] < 95:
                findings.append(
                    f"⚠ {label} was unreachable in {100 - d['reachable_pct']:.0f}% of "
                    f"polls - it is dropping off the network, not just responding slowly."
                )
            if d["band_switches"] > 5:
                findings.append(
                    f"⚠ {label} had {d['band_switches']} band switches - "
                    f"band steering is moving it between radios repeatedly."
                )
            if d["reboots"] > 2:
                findings.append(
                    f"⚠ {label} restarted {d['reboots']} times - "
                    f"a device-side fault, not a network one."
                )
            if d["dominant_band"] is None and d["total"] > 0:
                findings.append(
                    f"ℹ {label} does not report a BSSID, so its band cannot be "
                    f"determined. Reachability data is still valid."
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
