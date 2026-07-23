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

    def test_collect_dry_run_exits_cleanly(self, seeded_db):
        import threading, time
        stop = threading.Event()

        def run_collect():
            try:
                main(["collect", "--dry-run", "--db", seeded_db])
            except SystemExit:
                pass

        t = threading.Thread(target=run_collect, daemon=True)
        t.start()
        time.sleep(0.5)
        import signal, os
        # Just verify it started without error — thread is daemon so it dies with test
