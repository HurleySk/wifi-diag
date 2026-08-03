import signal
import sys
import time
from datetime import datetime, timezone

from . import config
from .collectors import (
    create_cast_collector,
    create_latency_collector,
    create_scan_collector,
    create_speed_collector,
    create_wifi_collector,
)
from .discovery import discover_cast_devices
from .events import detect_cast_events


class DiagScheduler:
    def __init__(self, store, dry_run=False):
        self.store = store
        self.dry_run = dry_run
        self.running = False
        self._last_band = {}
        self._last_freq = {}

        self.wifi_collector = create_wifi_collector(dry_run)
        self.gateway_collector = create_latency_collector(
            config.GATEWAY_TARGET, config.PING_COUNT, dry_run
        )
        self.external_collector = create_latency_collector(
            config.EXTERNAL_TARGET, config.PING_COUNT, dry_run
        )
        self.speed_collector = create_speed_collector(dry_run)
        self.cast_collector = create_cast_collector(dry_run)
        self.scan_collector = create_scan_collector(dry_run)
        self._band_map = {}
        # mac -> {"ip": str, "name": str, "model": str}
        self._targets = {}
        # mac -> last reading dict, for event detection
        self._last_cast = {}

    def run(self):
        self.running = True
        signal.signal(signal.SIGINT, self._handle_stop)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._handle_stop)

        last_wifi = 0.0
        last_latency = 0.0
        last_speed = 0.0
        last_cast = 0.0
        last_scan = 0.0

        print(f"wifi-diag collecting on {config.HOSTNAME} (dry_run={self.dry_run})")
        print("Press Ctrl+C to stop")

        while self.running:
            now = time.time()
            if now - last_scan >= config.SCAN_INTERVAL_SECS:
                self._collect_scan()
                last_scan = now
            if now - last_wifi >= config.WIFI_INTERVAL_SECS:
                self._collect_wifi()
                last_wifi = now
            if now - last_latency >= config.LATENCY_INTERVAL_SECS:
                self._collect_latency()
                last_latency = now
            if now - last_cast >= config.CAST_INTERVAL_SECS:
                self._collect_cast()
                last_cast = now
            if now - last_speed >= config.SPEED_INTERVAL_SECS:
                self._collect_speed()
                last_speed = now
            time.sleep(1)

        print("Stopped.")

    def stop(self):
        self.running = False

    def collect_once(self):
        self._collect_scan()
        self._collect_wifi()
        self._collect_latency()
        self._collect_cast()
        self._collect_speed()

    def _now_iso(self):
        return datetime.now(timezone.utc).isoformat()

    def _collect_wifi(self):
        try:
            reading = self.wifi_collector.collect()
            ts = self._now_iso()
            reading["timestamp"] = ts
            reading["host"] = config.HOSTNAME
            self.store.insert_wifi_reading(reading)

            current_band = reading.get("band")
            current_freq = reading.get("frequency_mhz", 0)
            prev_band = self._last_band.get(config.HOSTNAME)

            if prev_band and current_band and prev_band != current_band:
                self.store.insert_band_switch({
                    "timestamp": ts,
                    "host": config.HOSTNAME,
                    "from_band": prev_band,
                    "to_band": current_band,
                    "from_freq": self._last_freq.get(config.HOSTNAME, 0),
                    "to_freq": current_freq,
                })

            self._last_band[config.HOSTNAME] = current_band
            self._last_freq[config.HOSTNAME] = current_freq
        except Exception as e:
            print(f"  WiFi collection error: {e}")

    def _collect_latency(self):
        for collector in [self.gateway_collector, self.external_collector]:
            try:
                reading = collector.collect()
                reading["timestamp"] = self._now_iso()
                reading["host"] = config.HOSTNAME
                self.store.insert_latency_reading(reading)
            except Exception as e:
                print(f"  Latency collection error: {e}")

    def _collect_speed(self):
        try:
            reading = self.speed_collector.collect()
            reading["timestamp"] = self._now_iso()
            reading["host"] = config.HOSTNAME
            self.store.insert_speed_reading(reading)
        except Exception as e:
            print(f"  Speed collection error: {e}")

    def _collect_scan(self):
        try:
            rows = self.scan_collector.collect()
        except Exception as e:
            print(f"  Scan error: {e}")
            return
        if not rows:
            return
        ts = self._now_iso()
        for r in rows:
            r["timestamp"] = ts
            r["host"] = config.HOSTNAME
        try:
            self.store.insert_ap_scans(rows)
        except Exception as e:
            print(f"  Scan store error: {e}")
            return
        self._band_map = self.store.get_bssid_band_map()

    def _refresh_targets(self):
        """Merge the persisted registry, mDNS results, and static IPs."""
        for d in self.store.get_cast_devices():
            if d["last_ip"]:
                entry = self._targets.setdefault(d["mac"], {})
                entry.setdefault("ip", d["last_ip"])
                entry.setdefault("name", d["name"])
                entry.setdefault("model", d["model"])

        discovered = []
        if not self.dry_run:
            try:
                discovered = discover_cast_devices()
            except Exception as e:
                print(f"  Discovery error: {e}")
        else:
            discovered = [{"ip": ip, "name": None, "model": None}
                          for ip in self.cast_collector.ips()]

        # Discovery and static entries have no MAC yet; they are probed by IP
        # and identified from the eureka_info response.
        extra_ips = [d["ip"] for d in discovered] + list(config.CAST_STATIC_IPS)
        known_ips = {t.get("ip") for t in self._targets.values()}
        models = {d["ip"]: d.get("model") for d in discovered}
        return [ip for ip in dict.fromkeys(extra_ips) if ip not in known_ips], models

    def _collect_cast(self):
        unidentified_ips, models = self._refresh_targets()
        ts = self._now_iso()

        probes = [(mac, t.get("ip"), t.get("name"), t.get("model"))
                  for mac, t in self._targets.items()]
        probes += [(None, ip, None, models.get(ip)) for ip in unidentified_ips]

        for known_mac, ip, known_name, model in probes:
            if not ip:
                continue
            self._probe_cast_device(known_mac, ip, known_name, model, ts)

    def _probe_cast_device(self, known_mac, ip, known_name, model, ts):
        info = None
        try:
            info = self.cast_collector.collect(ip)
        except Exception:
            info = None

        if info is not None:
            mac = info["mac"]
            name = info.get("name") or known_name
        elif known_mac:
            mac = known_mac
            name = known_name
        else:
            # Never seen this device successfully; nothing to attribute the
            # reading to, so drop it rather than inventing an identity.
            return

        latency = {}
        try:
            collector = create_latency_collector(ip, config.CAST_PING_COUNT, self.dry_run)
            latency = collector.collect()
        except Exception:
            latency = {}

        bssid = info.get("bssid") if info else None
        mapped = self._band_map.get(bssid) if bssid else None

        reading = {
            "timestamp": ts,
            "host": config.HOSTNAME,
            "mac": mac,
            "ip": ip,
            "name": name,
            "ssid": info.get("ssid") if info else None,
            "bssid": bssid,
            "band": mapped["band"] if mapped else None,
            "channel": mapped["channel"] if mapped else None,
            "frequency_mhz": mapped["frequency_mhz"] if mapped else None,
            "reachable": 1 if info else 0,
            "ethernet": int(info["ethernet"]) if info and info.get("ethernet") is not None else None,
            "uptime_secs": info.get("uptime_secs") if info else None,
            "rtt_avg_ms": latency.get("rtt_avg_ms"),
            "packet_loss_pct": latency.get("packet_loss_pct"),
        }

        try:
            self.store.insert_cast_reading(reading)
            self.store.upsert_cast_device({
                "mac": mac,
                "name": name,
                "model": model,
                "firmware": info.get("firmware") if info else None,
                "last_ip": ip,
                "timestamp": ts,
            })
        except Exception as e:
            print(f"  Cast store error for {name or mac}: {e}")
            return

        self._targets[mac] = {"ip": ip, "name": name, "model": model}

        for event in detect_cast_events(self._last_cast.get(mac), reading):
            try:
                self.store.insert_cast_event({
                    "timestamp": ts,
                    "host": config.HOSTNAME,
                    "mac": mac,
                    "name": name,
                    "event_type": event["event_type"],
                    "detail": event["detail"],
                })
            except Exception as e:
                print(f"  Cast event store error: {e}")
        self._last_cast[mac] = reading

    def _handle_stop(self, signum, frame):
        self.stop()
