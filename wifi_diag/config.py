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
