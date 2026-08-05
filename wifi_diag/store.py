import sqlite3
from pathlib import Path
from . import config
from .parsers.eureka_parser import PLACEHOLDER_MACS

# Rendered into migration SQL, so the order must not vary between runs.
_PLACEHOLDER_MACS = tuple(sorted(PLACEHOLDER_MACS))


class DiagStore:
    def __init__(self, db_path=None):
        self.db_path = str(db_path) if db_path else str(config.DB_PATH)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._migrate()

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
                packet_loss_pct REAL,
                interface TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_latency_host_ts
                ON latency_readings(host, timestamp);

            CREATE TABLE IF NOT EXISTS speed_readings (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                download_mbps REAL,
                upload_mbps REAL,
                ping_ms REAL,
                interface TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_speed_host_ts
                ON speed_readings(host, timestamp);

            CREATE TABLE IF NOT EXISTS cast_devices (
                device_id TEXT PRIMARY KEY,
                mac TEXT,
                name TEXT,
                model TEXT,
                firmware TEXT,
                first_seen TEXT,
                last_seen TEXT,
                last_ip TEXT
            );

            CREATE TABLE IF NOT EXISTS cast_readings (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                device_id TEXT NOT NULL,
                mac TEXT,
                ip TEXT,
                name TEXT,
                ssid TEXT,
                bssid TEXT,
                band TEXT,
                channel INTEGER,
                frequency_mhz INTEGER,
                reachable INTEGER NOT NULL,
                ethernet INTEGER,
                uptime_secs REAL,
                rtt_avg_ms REAL,
                packet_loss_pct REAL
            );
            CREATE TABLE IF NOT EXISTS cast_events (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                device_id TEXT NOT NULL,
                name TEXT,
                event_type TEXT NOT NULL,
                detail TEXT
            );

            CREATE TABLE IF NOT EXISTS ap_scans (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                bssid TEXT NOT NULL,
                ssid TEXT,
                frequency_mhz INTEGER,
                channel INTEGER,
                band TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ap_scan_bssid_ts
                ON ap_scans(bssid, timestamp);
        """)

    def _columns(self, table):
        return {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self):
        """Add columns introduced after a database may already exist."""
        # NULL interface means unknown provenance, not WiFi.
        for table in ("latency_readings", "speed_readings"):
            if "interface" not in self._columns(table):
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN interface TEXT")
        self._migrate_cast_identity()
        self.conn.commit()

    def _migrate_cast_identity(self):
        """Re-key Cast tables from MAC onto device_id.

        Rows whose MAC is the all-zero placeholder cannot be told apart by it -
        several devices reported it at once - so they are split by name. That
        recovers separate histories rather than leaving them merged, but it
        cannot rejoin them to the UDN identity the same devices now report.
        """
        legacy = "'unidentified:' || COALESCE(LOWER(NULLIF(name, '')), mac)"
        derived = (
            f"CASE WHEN mac IS NULL OR mac IN {_PLACEHOLDER_MACS} "
            f"THEN {legacy} ELSE mac END"
        )
        # The old column was NOT NULL, so a placeholder cannot be nulled in
        # place; each table is rebuilt rather than altered.
        real_mac = f"CASE WHEN mac IN {_PLACEHOLDER_MACS} THEN NULL ELSE mac END"

        if "device_id" not in self._columns("cast_readings"):
            self.conn.executescript(f"""
                CREATE TABLE cast_readings_new (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    host TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    mac TEXT,
                    ip TEXT,
                    name TEXT,
                    ssid TEXT,
                    bssid TEXT,
                    band TEXT,
                    channel INTEGER,
                    frequency_mhz INTEGER,
                    reachable INTEGER NOT NULL,
                    ethernet INTEGER,
                    uptime_secs REAL,
                    rtt_avg_ms REAL,
                    packet_loss_pct REAL
                );
                INSERT INTO cast_readings_new
                    SELECT id, timestamp, host, {derived}, {real_mac}, ip, name,
                           ssid, bssid, band, channel, frequency_mhz, reachable,
                           ethernet, uptime_secs, rtt_avg_ms, packet_loss_pct
                    FROM cast_readings;
                DROP TABLE cast_readings;
                ALTER TABLE cast_readings_new RENAME TO cast_readings;
            """)

        if "device_id" not in self._columns("cast_events"):
            self.conn.executescript(f"""
                CREATE TABLE cast_events_new (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    host TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    name TEXT,
                    event_type TEXT NOT NULL,
                    detail TEXT
                );
                INSERT INTO cast_events_new
                    SELECT id, timestamp, host, {derived}, name, event_type, detail
                    FROM cast_events;
                DROP TABLE cast_events;
                ALTER TABLE cast_events_new RENAME TO cast_events;
            """)

        if "device_id" not in self._columns("cast_devices"):
            self.conn.executescript(f"""
                CREATE TABLE cast_devices_new (
                    device_id TEXT PRIMARY KEY,
                    mac TEXT,
                    name TEXT,
                    model TEXT,
                    firmware TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    last_ip TEXT
                );
                INSERT OR REPLACE INTO cast_devices_new
                    SELECT {derived}, {real_mac}, name, model, firmware,
                           first_seen, last_seen, last_ip
                    FROM cast_devices;
                DROP TABLE cast_devices;
                ALTER TABLE cast_devices_new RENAME TO cast_devices;
            """)

        # Indexed here rather than in _create_tables: on a pre-existing database
        # the column does not exist until the rebuilds above have run.
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cast_device_ts"
            " ON cast_readings(device_id, timestamp)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cast_event_device_ts"
            " ON cast_events(device_id, timestamp)"
        )

    def _query(self, table, host=None, target=None, device_id=None, start=None, end=None):
        query = f"SELECT * FROM {table} WHERE 1=1"
        params = []
        if host:
            query += " AND host = ?"
            params.append(host)
        if target:
            query += " AND target = ?"
            params.append(target)
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
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
        params = dict(reading)
        params.setdefault("interface", None)
        self.conn.execute(
            """INSERT INTO latency_readings
               (timestamp, host, target, rtt_min_ms, rtt_avg_ms,
                rtt_max_ms, packet_loss_pct, interface)
               VALUES (:timestamp, :host, :target, :rtt_min_ms,
                :rtt_avg_ms, :rtt_max_ms, :packet_loss_pct, :interface)""",
            params,
        )
        self.conn.commit()

    def insert_speed_reading(self, reading):
        params = dict(reading)
        params.setdefault("interface", None)
        self.conn.execute(
            """INSERT INTO speed_readings
               (timestamp, host, download_mbps, upload_mbps, ping_ms, interface)
               VALUES (:timestamp, :host, :download_mbps, :upload_mbps,
                :ping_ms, :interface)""",
            params,
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

    def upsert_cast_device(self, device):
        params = dict(device)
        params.setdefault("mac", None)
        self.conn.execute(
            """INSERT INTO cast_devices
               (device_id, mac, name, model, firmware, first_seen, last_seen, last_ip)
               VALUES (:device_id, :mac, :name, :model, :firmware, :timestamp,
                :timestamp, :last_ip)
               ON CONFLICT(device_id) DO UPDATE SET
                 mac = COALESCE(excluded.mac, cast_devices.mac),
                 name = COALESCE(excluded.name, cast_devices.name),
                 model = COALESCE(excluded.model, cast_devices.model),
                 firmware = COALESCE(excluded.firmware, cast_devices.firmware),
                 last_seen = excluded.last_seen,
                 last_ip = COALESCE(excluded.last_ip, cast_devices.last_ip)""",
            params,
        )
        self.conn.commit()

    def insert_cast_reading(self, reading):
        params = dict(reading)
        params.setdefault("mac", None)
        self.conn.execute(
            """INSERT INTO cast_readings
               (timestamp, host, device_id, mac, ip, name, ssid, bssid, band,
                channel, frequency_mhz, reachable, ethernet, uptime_secs,
                rtt_avg_ms, packet_loss_pct)
               VALUES (:timestamp, :host, :device_id, :mac, :ip, :name, :ssid,
                :bssid, :band, :channel, :frequency_mhz, :reachable, :ethernet,
                :uptime_secs, :rtt_avg_ms, :packet_loss_pct)""",
            params,
        )
        self.conn.commit()

    def insert_cast_event(self, event):
        self.conn.execute(
            """INSERT INTO cast_events
               (timestamp, host, device_id, name, event_type, detail)
               VALUES (:timestamp, :host, :device_id, :name, :event_type, :detail)""",
            event,
        )
        self.conn.commit()

    def insert_ap_scans(self, rows):
        self.conn.executemany(
            """INSERT INTO ap_scans
               (timestamp, host, bssid, ssid, frequency_mhz, channel, band)
               VALUES (:timestamp, :host, :bssid, :ssid, :frequency_mhz,
                :channel, :band)""",
            rows,
        )
        self.conn.commit()

    def get_cast_devices(self):
        rows = self.conn.execute(
            "SELECT * FROM cast_devices ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cast_readings(self, device_id=None, host=None, start=None, end=None):
        return self._query(
            "cast_readings", host=host, device_id=device_id, start=start, end=end
        )

    def get_cast_events(self, device_id=None, host=None, start=None, end=None):
        return self._query(
            "cast_events", host=host, device_id=device_id, start=start, end=end
        )

    def get_ap_scans(self, bssid=None, start=None, end=None):
        query = "SELECT * FROM ap_scans WHERE 1=1"
        params = []
        if bssid:
            query += " AND bssid = ?"
            params.append(bssid)
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " ORDER BY timestamp"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_latest_cast_reading(self, device_id):
        row = self.conn.execute(
            "SELECT * FROM cast_readings WHERE device_id = ?"
            " ORDER BY timestamp DESC LIMIT 1",
            (device_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_bssid_band_map(self):
        """Latest observed frequency/channel/band per BSSID."""
        rows = self.conn.execute(
            """SELECT s.bssid, s.frequency_mhz, s.channel, s.band
               FROM ap_scans s
               JOIN (SELECT bssid, MAX(timestamp) AS ts
                     FROM ap_scans GROUP BY bssid) latest
                 ON s.bssid = latest.bssid AND s.timestamp = latest.ts
               GROUP BY s.bssid"""
        ).fetchall()
        return {
            r["bssid"]: {
                "frequency_mhz": r["frequency_mhz"],
                "channel": r["channel"],
                "band": r["band"],
            }
            for r in rows
        }

    def close(self):
        self.conn.close()
