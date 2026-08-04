import os
import socket
from pathlib import Path

WIFI_INTERVAL_SECS = 30
LATENCY_INTERVAL_SECS = 60
SPEED_INTERVAL_SECS = 1800

GATEWAY_TARGET = "192.168.1.1"
EXTERNAL_TARGET = "8.8.8.8"
PING_COUNT = 5

DB_DIR = Path.home() / ".wifi-diag"
DB_PATH = DB_DIR / "data.db"

HOSTNAME = socket.gethostname()

# Google Cast device monitoring
CAST_INTERVAL_SECS = 60
SCAN_INTERVAL_SECS = 900
CAST_HTTP_PORT = 8008
CAST_HTTP_TIMEOUT_SECS = 3
CAST_PING_COUNT = 3
CAST_STATIC_IPS = []
DISCOVERY_TIMEOUT_SECS = 5
# Overridable so a host naming its WiFi device otherwise needs no code edit.
WIFI_INTERFACE = os.environ.get("WIFI_DIAG_INTERFACE", "wlan0")
