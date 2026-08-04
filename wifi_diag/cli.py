import argparse
import sys

from . import config
from .store import DiagStore
from .scheduler import DiagScheduler
from .analysis.trends import weekly_comparison
from .analysis.bands import band_analysis
from .analysis.diagnose import diagnose
from .analysis.devices import device_summary


def main(argv=None):
    # Windows consoles default to cp1252 and raise on the box-drawing output.
    if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Shared so --db works either before or after the subcommand.
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument(
        "--db", default=None,
        help="Path to SQLite database (default: ~/.wifi-diag/data.db)",
    )

    parser = argparse.ArgumentParser(
        prog="wifi-diag",
        description="WiFi diagnostic agent",
        parents=[db_parent],
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    collect_p = sub.add_parser("collect", help="Start collecting metrics", parents=[db_parent])
    collect_p.add_argument("--dry-run", action="store_true", help="Use mock collectors")

    sub.add_parser("status", help="Current readings snapshot", parents=[db_parent])
    sub.add_parser("history", help="Last 24h summary", parents=[db_parent])

    trends_p = sub.add_parser("trends", help="Week-over-week comparison", parents=[db_parent])
    trends_p.add_argument("--weeks", type=int, default=4)

    bands_p = sub.add_parser("bands", help="Band usage analysis", parents=[db_parent])
    bands_p.add_argument("--days", type=int, default=7)

    diag_p = sub.add_parser("diagnose", help="Automated root cause analysis", parents=[db_parent])
    diag_p.add_argument("--days", type=int, default=7)

    sub.add_parser("devices", help="Google Cast device status", parents=[db_parent])

    device_p = sub.add_parser("device", help="History for one Cast device", parents=[db_parent])
    device_p.add_argument("name", help="Device name (case-insensitive) or MAC")
    device_p.add_argument("--days", type=int, default=7)

    events_p = sub.add_parser("events", help="Recent Cast device events", parents=[db_parent])
    events_p.add_argument("--hours", type=int, default=24)

    args = parser.parse_args(argv)
    db_path = args.db or config.DB_PATH
    store = DiagStore(db_path)

    try:
        if args.command == "collect":
            _cmd_collect(store, args)
        elif args.command == "status":
            _cmd_status(store)
        elif args.command == "history":
            _cmd_history(store)
        elif args.command == "trends":
            _cmd_trends(store, args.weeks)
        elif args.command == "bands":
            _cmd_bands(store, args.days)
        elif args.command == "diagnose":
            _cmd_diagnose(store, args.days)
        elif args.command == "devices":
            _cmd_devices(store)
        elif args.command == "device":
            _cmd_device(store, args.name, args.days)
        elif args.command == "events":
            _cmd_events(store, args.hours)
    finally:
        store.close()


def _cmd_collect(store, args):
    sched = DiagScheduler(store, dry_run=args.dry_run)
    sched.run()


def _cmd_status(store):
    hosts = store.get_hosts()
    if not hosts:
        print("No data collected yet. Run 'wifi-diag collect' first.")
        return

    for h in hosts:
        print(f"\n── {h} ──")
        wifi = store.get_latest_wifi(h)
        if wifi:
            print(f"  WiFi:    {wifi['rssi_dbm']}dBm | {wifi['band']} ch{wifi['channel']} | {wifi['link_speed_mbps']}Mbps")

        gw = store.get_latest_latency(h, config.GATEWAY_TARGET)
        if gw:
            print(f"  Gateway: {gw['rtt_avg_ms']}ms avg | {gw['packet_loss_pct']}% loss")

        ext = store.get_latest_latency(h, config.EXTERNAL_TARGET)
        if ext:
            print(f"  External: {ext['rtt_avg_ms']}ms avg | {ext['packet_loss_pct']}% loss")

        speed = store.get_latest_speed(h)
        if speed:
            print(f"  Speed:   ↓{speed['download_mbps']}Mbps ↑{speed['upload_mbps']}Mbps | {speed['ping_ms']}ms")


def _cmd_history(store):
    from datetime import datetime, timedelta, timezone

    hosts = store.get_hosts()
    if not hosts:
        print("No data collected yet.")
        return

    start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    for h in hosts:
        readings = store.get_wifi_readings(host=h, start=start)
        switches = store.get_band_switches(host=h, start=start)
        latency = store.get_latency_readings(host=h, target=config.GATEWAY_TARGET, start=start)

        print(f"\n── {h} (last 24h) ──")
        if readings:
            rssis = [r["rssi_dbm"] for r in readings if r["rssi_dbm"] is not None]
            fives = sum(1 for r in readings if r["band"] == "5GHz")
            print(f"  Readings: {len(readings)}")
            if rssis:
                print(f"  Signal:   avg {sum(rssis)/len(rssis):.0f}dBm, min {min(rssis)}dBm, max {max(rssis)}dBm")
            print(f"  Band:     {fives}/{len(readings)} on 5GHz ({fives/len(readings)*100:.0f}%)")
            print(f"  Switches: {len(switches)}")

        if latency:
            losses = [r for r in latency if r["packet_loss_pct"] and r["packet_loss_pct"] > 0]
            print(f"  Dropouts: {len(losses)} probes with packet loss")


def _cmd_trends(store, weeks):
    hosts = store.get_hosts()
    if not hosts:
        print("No data collected yet.")
        return

    for h in hosts:
        wc = weekly_comparison(store, host=h, weeks=weeks)
        print(f"\n── {h} ──")
        for i, w in enumerate(wc["weeks"]):
            label = "this week" if i == 0 else f"{i} week(s) ago"
            if w["reading_count"] == 0:
                print(f"  {label}: no data")
                continue
            rssi = f"{w['avg_rssi']:.0f}dBm" if w["avg_rssi"] is not None else "n/a"
            band = f"{w['band_5ghz_pct']:.0f}% 5GHz" if w["band_5ghz_pct"] is not None else "n/a"
            dl = f"{w['avg_download']:.0f}Mbps" if w["avg_download"] is not None else "n/a"
            print(f"  {label}: {rssi} | {band} | ↓{dl} ({w['reading_count']} readings)")


def _cmd_bands(store, days):
    ba = band_analysis(store, days=days)
    if not ba["hosts"]:
        print("No data collected yet.")
        return

    for h, d in ba["hosts"].items():
        print(f"\n── {h} (last {days} days) ──")
        print(f"  Total readings: {d['total']}")
        print(f"  5GHz:   {d['5ghz_count']} ({d['5ghz_pct']:.1f}%)")
        print(f"  2.4GHz: {d['2.4ghz_count']} ({100 - d['5ghz_pct']:.1f}%)")
        print(f"  Band switches: {d['switch_count']}")


def _cmd_diagnose(store, days):
    print(diagnose(store, days=days))


def _cmd_devices(store):
    summary = device_summary(store, days=7)["devices"]
    if not summary:
        print("No Cast devices seen yet. Run 'wifi-diag collect' first.")
        return

    print(f"{'DEVICE':<24} {'IP':<16} {'BAND':<8} {'UP%':>6} {'SWITCHES':>9} {'DROPS':>6}")
    print("─" * 74)
    for mac, d in sorted(summary.items(), key=lambda kv: (kv[1]["name"] or kv[0])):
        print(
            f"{(d['name'] or mac):<24} {(d['last_ip'] or '?'):<16} "
            f"{(d['dominant_band'] or '?'):<8} {d['reachable_pct']:>5.0f}% "
            f"{d['band_switches']:>9} {d['dropouts']:>6}"
        )


def _resolve_device(store, needle):
    needle = needle.strip().lower()
    devices = store.get_cast_devices()
    exact = [d for d in devices if d["mac"] == needle]
    if exact:
        return exact[0]
    matches = [d for d in devices if (d["name"] or "").lower() == needle]
    if not matches:
        matches = [d for d in devices if needle in (d["name"] or "").lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"'{needle}' matches multiple devices:")
        for d in matches:
            print(f"  {d['name']} ({d['mac']})")
        return None
    print(f"No device matching '{needle}'.")
    return None


def _cmd_device(store, name, days):
    from datetime import datetime, timedelta, timezone

    device = _resolve_device(store, name)
    if not device:
        return

    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    readings = store.get_cast_readings(mac=device["mac"], start=start)
    events = store.get_cast_events(mac=device["mac"], start=start)

    print(f"\n── {device['name'] or device['mac']} ({device['mac']}) ──")
    print(f"  Model:    {device['model'] or 'unknown'}")
    print(f"  Firmware: {device['firmware'] or 'unknown'}")
    print(f"  Last IP:  {device['last_ip'] or 'unknown'}")

    if not readings:
        print(f"  No readings in the last {days} days.")
        return

    reachable = sum(1 for r in readings if r["reachable"])
    print(f"  Readings: {len(readings)} over {days} days")
    print(f"  Reachable: {reachable / len(readings) * 100:.0f}%")

    bands = {}
    for r in readings:
        if r["band"]:
            bands[r["band"]] = bands.get(r["band"], 0) + 1
    if bands:
        parts = [f"{b} {c / len(readings) * 100:.0f}%" for b, c in sorted(bands.items())]
        print(f"  Band:     {', '.join(parts)}")
    else:
        print("  Band:     unknown (device does not report a BSSID)")

    if events:
        print(f"\n  Events ({len(events)}):")
        for e in events[-20:]:
            print(f"    {e['timestamp']}  {e['event_type']:<14} {e['detail']}")
    else:
        print("\n  No events recorded.")


def _cmd_events(store, hours):
    from datetime import datetime, timedelta, timezone

    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    events = store.get_cast_events(start=start)
    if not events:
        print(f"No device events in the last {hours} hours.")
        return

    print(f"{'TIME':<28} {'DEVICE':<22} {'EVENT':<14} DETAIL")
    print("─" * 90)
    for e in events:
        print(
            f"{e['timestamp']:<28} {(e['name'] or e['mac']):<22} "
            f"{e['event_type']:<14} {e['detail']}"
        )
