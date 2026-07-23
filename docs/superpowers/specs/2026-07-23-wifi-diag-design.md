# wifi-diag: WiFi Diagnostic Agent

**Date:** 2026-07-23
**Status:** Approved

## Problem

Home WiFi (T-Mobile CR1000A 5G Home Internet gateway) has been gradually degrading over weeks/months — slow speeds and intermittent dropouts. The CR1000A uses a single combined SSID with auto band-steering across 2.4GHz and 5GHz bands. Suspected causes include poor band-steering decisions, 5G backhaul degradation, or increasing interference, but there's no data to confirm.

## Goal

Build a lightweight diagnostic tool that runs on Raspberry Pis (and Windows) to collect WiFi and network metrics over time, identify the root cause of degradation, and determine whether a fix (e.g., separating SSIDs, mesh network, router replacement) is warranted.

Primary goal is **diagnosis**, not ongoing monitoring infrastructure. Keep it simple.

## Network Context

- **Router:** T-Mobile CR1000A at 192.168.1.1 (5G cellular backhaul → local WiFi)
- **Band config:** Single combined SSID, auto band-steering (2.4GHz + 5GHz)
- **Pi #1 (near):** 192.168.1.195, hostname `RASPBERRYPI`, same room/floor as router
- **Pi #2 (far):** 192.168.1.196, hostname `raspberrypi`, different room/floor
- **Windows PC:** 192.168.1.169, different floor from router (development machine, also a data point)
- **Other devices:** Google Home/Nest speakers, Samsung smart fridge, Mac, ~12+ clients total

## Architecture

Two identical Python agents on each Pi + optional agent on Windows PC. Each collects independently, stores locally in SQLite. No central server, no inter-device communication.

```
Pi-near-router (195)                Pi-far (196)                  Windows PC (169)
┌────────────────────┐              ┌────────────────────┐        ┌────────────────────┐
│  wifi-diag agent   │              │  wifi-diag agent   │        │  wifi-diag agent   │
│  ├─ collectors/    │              │  ├─ collectors/    │        │  ├─ collectors/    │
│  ├─ store (SQLite) │              │  ├─ store (SQLite) │        │  ├─ store (SQLite) │
│  └─ cli            │              │  └─ cli            │        │  └─ cli            │
└────────────────────┘              └────────────────────┘        └────────────────────┘
```

Each device is a self-contained diagnostic station. To compare data across devices, SSH in and run `wifi-diag` commands on each, or copy the SQLite DBs to one machine.

## Data Collection

### Collectors

| Collector | Metrics | Tool (Linux) | Tool (Windows) | Interval |
|-----------|---------|--------------|-----------------|----------|
| wifi_signal | RSSI (dBm), noise floor, frequency, band (2.4/5GHz), channel, link speed, BSSID | `iw dev wlan0 link` | `netsh wlan show interfaces` | 30 seconds |
| band_tracker | Band-switch events (2.4↔5GHz transitions) | Derived from wifi_signal (frequency delta) | Same | Piggybacks on wifi_signal |
| latency | RTT (min/avg/max), packet loss to gateway + external | `ping -c 5` | `ping -n 5` | 60 seconds |
| speed_test | Download/upload Mbps, ping | `speedtest-cli --simple` | `speedtest-cli --simple` | 30 minutes |

### Interval Rationale

- **WiFi signal (30s):** Band switches and signal fluctuations happen rapidly; need tight resolution.
- **Latency (60s):** Stable enough that 60s catches spikes without flooding.
- **Speed test (30min):** Saturates the connection during test; too frequent would cause the degradation we're measuring. 48 data points/day is sufficient for trend analysis.

### Band Detection

2.4GHz: channels 1-11, frequencies 2412-2462 MHz. 5GHz: channels 36-165, frequencies 5180-5825 MHz. Determined by checking which range the reported frequency falls in.

### Mock/Fixture Support

For development and testing on Windows (or any machine without WiFi CLI tools):

- Recorded real outputs from Pi `iw` commands shipped as fixtures in `wifi_diag/fixtures/`
- Mock collectors load from fixtures instead of shelling out
- `--dry-run` flag runs the full agent loop with mock data
- All unit tests use fixtures, passing on all platforms

## Storage

### SQLite Schema

```sql
wifi_readings (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,             -- ISO 8601
    host TEXT,                  -- hostname
    rssi_dbm REAL,             -- signal strength
    noise_dbm REAL,            -- noise floor (NULL if unavailable)
    frequency_mhz INTEGER,    -- e.g. 2437, 5180
    band TEXT,                 -- '2.4GHz' or '5GHz'
    channel INTEGER,
    link_speed_mbps REAL,
    bssid TEXT
)

band_switches (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    host TEXT,
    from_band TEXT,
    to_band TEXT,
    from_freq INTEGER,
    to_freq INTEGER
)

latency_readings (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    host TEXT,
    target TEXT,               -- '192.168.1.1' or '8.8.8.8'
    rtt_min_ms REAL,
    rtt_avg_ms REAL,
    rtt_max_ms REAL,
    packet_loss_pct REAL
)

speed_readings (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    host TEXT,
    download_mbps REAL,
    upload_mbps REAL,
    ping_ms REAL
)
```

Indexes on `(host, timestamp)` for each table.

**Retention:** Keep all data. At these intervals, a month is ~15MB per device.

**Location:** `~/.wifi-diag/data.db`

## CLI Interface

```
wifi-diag collect                # start collecting (foreground, Ctrl+C to stop)
wifi-diag collect --dry-run      # run with mock collectors (dev/testing)

wifi-diag status                 # current readings snapshot
wifi-diag history                # last 24h summary
wifi-diag trends                 # week-over-week comparison
wifi-diag bands                  # band usage analysis (2.4 vs 5GHz time split)
wifi-diag diagnose               # automated root cause analysis
```

### `wifi-diag diagnose` Output

The payoff command. Analyzes collected data and reports:

- % time on 5GHz vs 2.4GHz per host, and whether that ratio is changing over time
- Signal strength correlation with speed drops
- Band-switch correlation with dropout events
- Gateway latency vs external latency (isolates local WiFi vs 5G backhaul)
- Cross-host comparison (near-Pi vs far-Pi vs Windows PC)
- Ranked likely causes with evidence

Example:
```
DIAGNOSIS SUMMARY (last 7 days)
───────────────────────────────
Signal: RASPBERRYPI avg -42dBm (good), raspberrypi avg -68dBm (fair), LAP avg -71dBm (weak)
Band:   RASPBERRYPI 95% on 5GHz, raspberrypi 40% on 5GHz (↓ from 70% last week), LAP 25% on 5GHz

⚠ Far devices spending less time on 5GHz over time.
  raspberrypi: 70% → 55% → 40% over 3 weeks
  Correlates with speed drops on those devices.

⚠ Gateway latency stable (2-4ms) but external latency spikes
  coincide with speed drops → likely 5G backhaul issue.

LIKELY CAUSES (ranked):
  1. Band steering degrading — far devices increasingly stuck on 2.4GHz
  2. 5G backhaul congestion during peak hours
  3. Consider separating SSIDs to force 5GHz where signal permits
```

## Project Structure

```
wifi-diag/
├── .gitignore                   # .claude/, docs/, .env, __pycache__, *.db, etc.
├── README.md                    # setup instructions (Pi + Windows), usage, examples
├── pyproject.toml               # project config, dependencies
├── requirements.txt             # pinned deps
├── install.sh                   # Pi setup: apt deps + systemd service
├── wifi_diag/
│   ├── __main__.py              # entry point (python -m wifi_diag)
│   ├── cli.py                   # argument parsing, command dispatch
│   ├── config.py                # intervals, targets, DB path
│   ├── scheduler.py             # runs collectors on their intervals
│   ├── store.py                 # SQLite wrapper, schema, queries
│   ├── collectors/
│   │   ├── base.py              # abstract collector interface
│   │   ├── wifi_linux.py        # iw-based WiFi collector
│   │   ├── wifi_windows.py      # netsh-based WiFi collector
│   │   ├── wifi_mock.py         # fixture-based mock collector
│   │   ├── latency.py           # ping collector (cross-platform)
│   │   └── speed.py             # speedtest-cli wrapper
│   ├── parsers/
│   │   ├── iw_parser.py         # parse iw output → dict
│   │   ├── netsh_parser.py      # parse netsh output → dict
│   │   ├── ping_parser.py       # parse ping output → dict
│   │   └── speedtest_parser.py  # parse speedtest output → dict
│   ├── analysis/
│   │   ├── trends.py            # week-over-week comparisons
│   │   ├── bands.py             # band usage analysis
│   │   └── diagnose.py          # automated root cause analysis
│   └── fixtures/                # recorded real outputs for mock/test
│       ├── iw_link_5ghz.txt
│       ├── iw_link_2ghz.txt
│       ├── netsh_5ghz.txt
│       ├── netsh_2ghz.txt
│       ├── ping_linux.txt
│       ├── ping_windows.txt
│       └── speedtest.txt
├── tests/
│   ├── test_parsers.py
│   ├── test_store.py
│   ├── test_analysis.py
│   └── test_collectors.py
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-07-23-wifi-diag-design.md
```

## Testing Strategy

### Platform Split

| Layer | Testable on Windows | Testable on Pi |
|-------|-------------------|----------------|
| Parsers (iw, netsh, ping, speedtest output → dict) | Yes (fixture-based) | Yes |
| Store (SQLite reads/writes/queries) | Yes | Yes |
| Analysis (trends, bands, diagnose) | Yes (seeded DB) | Yes |
| Linux collectors (iw, ping) | No (mock only) | Yes |
| Windows collectors (netsh, ping) | Yes | No |

All unit tests use fixtures and run on both platforms. Integration tests on Pi validate real collector output matches expected parser input shapes.

## Deployment (Pi)

- `install.sh`: installs apt dependencies, creates systemd service, enables on boot
- Runs as `wifi-diag.service` via systemd
- Restarts on failure, survives reboots
- Logs to journald: `journalctl -u wifi-diag`
- User clones repo, runs `./install.sh`, done

## Dependencies

- Python 3.9+ (ships with Pi OS)
- `speedtest-cli` (pip install)
- `iw` / `wireless-tools` (apt, already on Pi OS)
- No other external dependencies; SQLite is in Python stdlib

## Out of Scope

- Web dashboard / UI (can be added later; SQLite data is easy to export)
- Alerting / notifications
- Central aggregation server
- Router configuration changes (read-only monitoring)
- Historical WiFi channel scanning (would require monitor mode, adds complexity)
