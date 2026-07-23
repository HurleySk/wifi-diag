import argparse
import sys

from . import config
from .store import DiagStore
from .scheduler import DiagScheduler
from .analysis.trends import weekly_comparison
from .analysis.bands import band_analysis
from .analysis.diagnose import diagnose


def main(argv=None):
    # On Windows the console default encoding is often cp1252, which cannot
    # encode the Unicode warning/box-drawing characters produced by the
    # analysis modules. Force UTF-8 so print() never raises UnicodeEncodeError.
    if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Shared so --db can appear either before or after the subcommand, e.g.
    # both `wifi-diag --db X status` and `wifi-diag status --db X` work.
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
