import sqlite3

import pytest

LEGACY_SCHEMA = [
    "CREATE TABLE cast_devices ("
    " mac TEXT PRIMARY KEY, name TEXT, model TEXT, firmware TEXT,"
    " first_seen TEXT, last_seen TEXT, last_ip TEXT)",
    "CREATE TABLE cast_readings ("
    " id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, host TEXT NOT NULL,"
    " mac TEXT NOT NULL, ip TEXT, name TEXT, ssid TEXT, bssid TEXT,"
    " band TEXT, channel INTEGER, frequency_mhz INTEGER,"
    " reachable INTEGER NOT NULL, ethernet INTEGER, uptime_secs REAL,"
    " rtt_avg_ms REAL, packet_loss_pct REAL)",
    "CREATE TABLE cast_events ("
    " id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, host TEXT NOT NULL,"
    " mac TEXT NOT NULL, name TEXT, event_type TEXT NOT NULL, detail TEXT)",
]


@pytest.fixture
def legacy_cast_db(tmp_path):
    def build(rows, devices, filename="legacy.db"):
        db = tmp_path / filename
        conn = sqlite3.connect(str(db))
        for statement in LEGACY_SCHEMA:
            conn.execute(statement)
        for mac, name, ip in rows:
            conn.execute(
                "INSERT INTO cast_readings"
                " (timestamp, host, mac, ip, name, reachable)"
                " VALUES ('2026-08-01T10:00:00+00:00', 'testpi', ?, ?, ?, 1)",
                (mac, ip, name),
            )
        for mac, name, ip in devices:
            conn.execute(
                "INSERT INTO cast_devices (mac, name, last_ip) VALUES (?, ?, ?)",
                (mac, name, ip),
            )
        conn.commit()
        conn.close()
        return db

    return build
