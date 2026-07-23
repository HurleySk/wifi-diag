import signal
import sys
import time
from datetime import datetime, timezone

from . import config
from .collectors import (
    create_latency_collector,
    create_speed_collector,
    create_wifi_collector,
)


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

    def run(self):
        self.running = True
        signal.signal(signal.SIGINT, self._handle_stop)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._handle_stop)

        last_wifi = 0.0
        last_latency = 0.0
        last_speed = 0.0

        print(f"wifi-diag collecting on {config.HOSTNAME} (dry_run={self.dry_run})")
        print("Press Ctrl+C to stop")

        while self.running:
            now = time.time()
            if now - last_wifi >= config.WIFI_INTERVAL_SECS:
                self._collect_wifi()
                last_wifi = now
            if now - last_latency >= config.LATENCY_INTERVAL_SECS:
                self._collect_latency()
                last_latency = now
            if now - last_speed >= config.SPEED_INTERVAL_SECS:
                self._collect_speed()
                last_speed = now
            time.sleep(1)

        print("Stopped.")

    def stop(self):
        self.running = False

    def collect_once(self):
        self._collect_wifi()
        self._collect_latency()
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

    def _handle_stop(self, signum, frame):
        self.stop()
