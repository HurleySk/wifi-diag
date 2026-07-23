import sqlite3
from pathlib import Path
from . import config


class DiagStore:
    def __init__(self, db_path=None):
        self.db_path = str(db_path) if db_path else str(config.DB_PATH)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS wifi_readings (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                rssi_dbm REAL,
                noise_dbm REAL,
                frequency_mhz INTEGER,
                band TEXT,
                channel INTEGER,
                link_speed_mbps REAL,
                bssid TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_wifi_host_ts
                ON wifi_readings(host, timestamp);

            CREATE TABLE IF NOT EXISTS band_switches (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                from_band TEXT,
                to_band TEXT,
                from_freq INTEGER,
                to_freq INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_band_host_ts
                ON band_switches(host, timestamp);

            CREATE TABLE IF NOT EXISTS latency_readings (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                target TEXT NOT NULL,
                rtt_min_ms REAL,
                rtt_avg_ms REAL,
                rtt_max_ms REAL,
                packet_loss_pct REAL
            );
            CREATE INDEX IF NOT EXISTS idx_latency_host_ts
                ON latency_readings(host, timestamp);

            CREATE TABLE IF NOT EXISTS speed_readings (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                download_mbps REAL,
                upload_mbps REAL,
                ping_ms REAL
            );
            CREATE INDEX IF NOT EXISTS idx_speed_host_ts
                ON speed_readings(host, timestamp);
        """)

    def _query(self, table, host=None, target=None, start=None, end=None):
        query = f"SELECT * FROM {table} WHERE 1=1"
        params = []
        if host:
            query += " AND host = ?"
            params.append(host)
        if target:
            query += " AND target = ?"
            params.append(target)
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " ORDER BY timestamp"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def insert_wifi_reading(self, reading):
        self.conn.execute(
            """INSERT INTO wifi_readings
               (timestamp, host, rssi_dbm, noise_dbm, frequency_mhz,
                band, channel, link_speed_mbps, bssid)
               VALUES (:timestamp, :host, :rssi_dbm, :noise_dbm,
                :frequency_mhz, :band, :channel, :link_speed_mbps, :bssid)""",
            reading,
        )
        self.conn.commit()

    def insert_band_switch(self, switch):
        self.conn.execute(
            """INSERT INTO band_switches
               (timestamp, host, from_band, to_band, from_freq, to_freq)
               VALUES (:timestamp, :host, :from_band, :to_band,
                :from_freq, :to_freq)""",
            switch,
        )
        self.conn.commit()

    def insert_latency_reading(self, reading):
        self.conn.execute(
            """INSERT INTO latency_readings
               (timestamp, host, target, rtt_min_ms, rtt_avg_ms,
                rtt_max_ms, packet_loss_pct)
               VALUES (:timestamp, :host, :target, :rtt_min_ms,
                :rtt_avg_ms, :rtt_max_ms, :packet_loss_pct)""",
            reading,
        )
        self.conn.commit()

    def insert_speed_reading(self, reading):
        self.conn.execute(
            """INSERT INTO speed_readings
               (timestamp, host, download_mbps, upload_mbps, ping_ms)
               VALUES (:timestamp, :host, :download_mbps, :upload_mbps,
                :ping_ms)""",
            reading,
        )
        self.conn.commit()

    def get_wifi_readings(self, host=None, start=None, end=None):
        return self._query("wifi_readings", host=host, start=start, end=end)

    def get_band_switches(self, host=None, start=None, end=None):
        return self._query("band_switches", host=host, start=start, end=end)

    def get_latency_readings(self, host=None, target=None, start=None, end=None):
        return self._query("latency_readings", host=host, target=target, start=start, end=end)

    def get_speed_readings(self, host=None, start=None, end=None):
        return self._query("speed_readings", host=host, start=start, end=end)

    def get_latest_wifi(self, host):
        row = self.conn.execute(
            "SELECT * FROM wifi_readings WHERE host = ? ORDER BY timestamp DESC LIMIT 1",
            (host,),
        ).fetchone()
        return dict(row) if row else None

    def get_latest_latency(self, host, target):
        row = self.conn.execute(
            "SELECT * FROM latency_readings WHERE host = ? AND target = ? ORDER BY timestamp DESC LIMIT 1",
            (host, target),
        ).fetchone()
        return dict(row) if row else None

    def get_latest_speed(self, host):
        row = self.conn.execute(
            "SELECT * FROM speed_readings WHERE host = ? ORDER BY timestamp DESC LIMIT 1",
            (host,),
        ).fetchone()
        return dict(row) if row else None

    def get_hosts(self):
        rows = self.conn.execute(
            "SELECT DISTINCT host FROM wifi_readings ORDER BY host"
        ).fetchall()
        return [r[0] for r in rows]

    def close(self):
        self.conn.close()
