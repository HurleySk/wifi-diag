import pytest
from unittest.mock import patch
from io import StringIO
from wifi_diag.store import DiagStore
from wifi_diag.cli import main
from datetime import datetime, timedelta, timezone


def _seed_store(store):
    now = datetime.now(timezone.utc)
    for i in range(5):
        ts = (now - timedelta(hours=i)).isoformat()
        store.insert_wifi_reading({
            "timestamp": ts, "host": "testhost", "rssi_dbm": -42 - i,
            "noise_dbm": None, "frequency_mhz": 5520, "band": "5GHz",
            "channel": 104, "link_speed_mbps": 866.7, "bssid": "aa:bb:cc:dd:ee:ff",
        })
        store.insert_latency_reading({
            "timestamp": ts, "host": "testhost", "target": "192.168.1.1",
            "rtt_min_ms": 1.0, "rtt_avg_ms": 2.0, "rtt_max_ms": 3.0, "packet_loss_pct": 0.0,
        })
        store.insert_latency_reading({
            "timestamp": ts, "host": "testhost", "target": "8.8.8.8",
            "rtt_min_ms": 10.0, "rtt_avg_ms": 15.0, "rtt_max_ms": 20.0, "packet_loss_pct": 0.0,
        })
    store.insert_speed_reading({
        "timestamp": now.isoformat(), "host": "testhost",
        "download_mbps": 95.5, "upload_mbps": 45.2, "ping_ms": 12.0,
    })


class TestCli:
    @pytest.fixture
    def seeded_db(self, tmp_path):
        db = tmp_path / "test.db"
        store = DiagStore(str(db))
        _seed_store(store)
        store.close()
        return str(db)

    def test_status_command(self, seeded_db, capsys):
        main(["status", "--db", seeded_db])
        out = capsys.readouterr().out
        assert "testhost" in out

    def test_bands_command(self, seeded_db, capsys):
        main(["bands", "--db", seeded_db])
        out = capsys.readouterr().out
        assert "5GHz" in out

    def test_diagnose_command(self, seeded_db, capsys):
        main(["diagnose", "--db", seeded_db])
        out = capsys.readouterr().out
        assert "DIAGNOSIS" in out

    def test_no_args_shows_help(self, capsys):
        with pytest.raises(SystemExit):
            main([])

    def test_collect_dry_run_collects_and_stops(self, seeded_db, monkeypatch):
        import threading
        import time

        from wifi_diag.scheduler import DiagScheduler

        # This asserted nothing before, and passed while its thread died.
        created = {}
        real_init = DiagScheduler.__init__

        def capture(self, store, dry_run=False):
            real_init(self, store, dry_run)
            created["scheduler"] = self

        monkeypatch.setattr(DiagScheduler, "__init__", capture)

        error = {}

        def run_collect():
            try:
                main(["collect", "--dry-run", "--db", seeded_db])
            except SystemExit:
                pass
            except BaseException as e:
                error["raised"] = e

        def wifi_count():
            # Unfiltered: collect writes under this machine's hostname.
            store = DiagStore(seeded_db)
            try:
                return len(store.get_wifi_readings())
            finally:
                store.close()

        before = wifi_count()
        thread = threading.Thread(target=run_collect, daemon=True)
        thread.start()

        deadline = time.time() + 10
        while time.time() < deadline and wifi_count() == before:
            assert "raised" not in error, f"collect raised {error.get('raised')!r}"
            time.sleep(0.05)

        assert wifi_count() > before, "collect wrote no readings"
        created["scheduler"].stop()
        thread.join(timeout=10)
        assert not thread.is_alive(), "collect did not stop when asked"
        assert "raised" not in error, f"collect raised {error.get('raised')!r}"


class TestDeviceCommands:
    def _seed(self, db_path):
        from wifi_diag.store import DiagStore

        s = DiagStore(str(db_path))
        s.insert_cast_reading({
            "timestamp": "2026-08-01T10:00:00+00:00", "host": "testpi",
            "mac": "cc:f4:11:a2:d3:af", "ip": "192.168.1.157", "name": "Kitchen Pod",
            "ssid": "BisNet", "bssid": "78:67:0e:6f:a7:fd", "band": "5GHz",
            "channel": 104, "frequency_mhz": 5520, "reachable": 1, "ethernet": 0,
            "uptime_secs": 100.0, "rtt_avg_ms": 4.0, "packet_loss_pct": 0.0,
        })
        s.upsert_cast_device({
            "mac": "cc:f4:11:a2:d3:af", "name": "Kitchen Pod", "model": "Nest Hub",
            "firmware": "1.68", "last_ip": "192.168.1.157",
            "timestamp": "2026-08-01T10:00:00+00:00",
        })
        s.insert_cast_event({
            "timestamp": "2026-08-01T11:00:00+00:00", "host": "testpi",
            "mac": "cc:f4:11:a2:d3:af", "name": "Kitchen Pod",
            "event_type": "band_switch", "detail": '{"from": "5GHz", "to": "2.4GHz"}',
        })
        s.close()

    def test_devices_lists_device(self, tmp_path, capsys):
        from wifi_diag.cli import main

        db = tmp_path / "t.db"
        self._seed(db)
        main(["devices", "--db", str(db)])
        assert "Kitchen Pod" in capsys.readouterr().out

    def test_devices_empty_message(self, tmp_path, capsys):
        from wifi_diag.cli import main

        main(["devices", "--db", str(tmp_path / "empty.db")])
        assert "No Cast devices" in capsys.readouterr().out

    def test_device_by_name_case_insensitive(self, tmp_path, capsys):
        from wifi_diag.cli import main

        db = tmp_path / "t.db"
        self._seed(db)
        main(["device", "kitchen pod", "--db", str(db)])
        out = capsys.readouterr().out
        assert "Kitchen Pod" in out
        assert "band_switch" in out

    def test_device_by_mac(self, tmp_path, capsys):
        from wifi_diag.cli import main

        db = tmp_path / "t.db"
        self._seed(db)
        main(["device", "cc:f4:11:a2:d3:af", "--db", str(db)])
        assert "Kitchen Pod" in capsys.readouterr().out

    def test_device_not_found(self, tmp_path, capsys):
        from wifi_diag.cli import main

        db = tmp_path / "t.db"
        self._seed(db)
        main(["device", "Nonexistent", "--db", str(db)])
        assert "No device matching" in capsys.readouterr().out

    def test_events_lists_events(self, tmp_path, capsys):
        from wifi_diag.cli import main

        db = tmp_path / "t.db"
        self._seed(db)
        main(["events", "--hours", "999999", "--db", str(db)])
        assert "band_switch" in capsys.readouterr().out

    def test_events_empty_message(self, tmp_path, capsys):
        from wifi_diag.cli import main

        main(["events", "--db", str(tmp_path / "empty.db")])
        assert "No device events" in capsys.readouterr().out
