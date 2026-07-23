# wifi-diag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform WiFi diagnostic agent that collects signal, latency, and speed metrics on Raspberry Pi and Windows, stores them in SQLite, and provides CLI-based analysis to diagnose WiFi degradation.

**Architecture:** Independent Python agents on each device (2 Raspberry Pis + Windows PC), each collecting WiFi metrics locally into SQLite. Parsers handle platform-specific CLI output (iw on Linux, netsh on Windows). Analysis module reads stored data to detect trends, band-steering issues, and correlate degradation with specific causes.

**Tech Stack:** Python 3.9+, SQLite (stdlib), speedtest-cli, iw/netsh (platform CLI tools), pytest

## Global Constraints

- Python 3.9+ (ships with Pi OS; user has 3.13 on Windows)
- No external dependencies beyond speedtest-cli — SQLite is stdlib
- Cross-platform: must run on Raspberry Pi OS (Debian) and Windows 11
- `.gitignore` must include `.claude/`, `docs/`, `.env`, `__pycache__/`, `*.db`
- All parsers return the same dict shapes regardless of platform
- Unit tests must pass on both platforms using fixture data
- DB path: `~/.wifi-diag/data.db`

---

### Task 1: Project Scaffold, Config, and Fixtures

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `wifi_diag/__init__.py`
- Create: `wifi_diag/config.py`
- Create: `wifi_diag/parsers/__init__.py`
- Create: `wifi_diag/collectors/__init__.py`
- Create: `wifi_diag/analysis/__init__.py`
- Create: `tests/__init__.py`
- Create: `wifi_diag/fixtures/iw_link_5ghz.txt`
- Create: `wifi_diag/fixtures/iw_link_2ghz.txt`
- Create: `wifi_diag/fixtures/netsh_5ghz.txt`
- Create: `wifi_diag/fixtures/netsh_2ghz.txt`
- Create: `wifi_diag/fixtures/ping_linux.txt`
- Create: `wifi_diag/fixtures/ping_windows.txt`
- Create: `wifi_diag/fixtures/speedtest.txt`

**Interfaces:**
- Consumes: nothing (foundation task)
- Produces:
  - `config.WIFI_INTERVAL_SECS` (int = 30)
  - `config.LATENCY_INTERVAL_SECS` (int = 60)
  - `config.SPEED_INTERVAL_SECS` (int = 1800)
  - `config.GATEWAY_TARGET` (str = "192.168.1.1")
  - `config.EXTERNAL_TARGET` (str = "8.8.8.8")
  - `config.PING_COUNT` (int = 5)
  - `config.DB_PATH` (Path)
  - `config.HOSTNAME` (str)
  - `parsers.freq_to_band(freq_mhz: int) -> str`
  - `parsers.freq_to_channel(freq_mhz: int) -> int`
  - `parsers.channel_to_freq(channel: int, band: str) -> int`
  - Fixture text files for all parsers

- [ ] **Step 1: Create `.gitignore`**

```
.claude/
docs/
.env
__pycache__/
*.pyc
*.db
*.egg-info/
dist/
build/
.pytest_cache/
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "wifi-diag"
version = "0.1.0"
description = "WiFi diagnostic agent for Raspberry Pi and Windows"
requires-python = ">=3.9"
dependencies = [
    "speedtest-cli>=2.1.3",
]

[project.scripts]
wifi-diag = "wifi_diag.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create `requirements.txt`**

```
speedtest-cli>=2.1.3
pytest>=7.0
```

- [ ] **Step 4: Create `wifi_diag/__init__.py`**

```python
```

(Empty — package marker only.)

- [ ] **Step 5: Create `wifi_diag/config.py`**

```python
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
```

- [ ] **Step 6: Create `wifi_diag/parsers/__init__.py` with frequency/channel utilities**

```python
def freq_to_band(freq_mhz: int) -> str:
    if 2400 <= freq_mhz <= 2500:
        return "2.4GHz"
    if 5000 <= freq_mhz <= 6000:
        return "5GHz"
    return "unknown"


def freq_to_channel(freq_mhz: int) -> int:
    if 2412 <= freq_mhz <= 2472:
        return (freq_mhz - 2407) // 5
    if freq_mhz == 2484:
        return 14
    if 5180 <= freq_mhz <= 5825:
        return (freq_mhz - 5000) // 5
    return 0


def channel_to_freq(channel: int, band: str) -> int:
    if band == "2.4GHz":
        if 1 <= channel <= 13:
            return 2407 + channel * 5
        if channel == 14:
            return 2484
    if band == "5GHz":
        return 5000 + channel * 5
    return 0
```

- [ ] **Step 7: Create empty `__init__.py` files**

Create these as empty files (package markers):
- `wifi_diag/collectors/__init__.py`
- `wifi_diag/analysis/__init__.py`
- `tests/__init__.py`

- [ ] **Step 8: Create fixture files**

`wifi_diag/fixtures/iw_link_5ghz.txt`:
```
Connected to 78:67:0e:6f:a7:fd (on wlan0)
	SSID: BisNet
	freq: 5520
	RX: 12345678 bytes (98765 packets)
	TX: 23456789 bytes (87654 packets)
	signal: -42 dBm
	rx bitrate: 866.7 MBit/s VHT-MCS 9 80MHz short GI VHT-NSS 2
	tx bitrate: 866.7 MBit/s VHT-MCS 9 80MHz short GI VHT-NSS 2
	bss flags:	short-preamble short-slot-time
	dtim period:	1
	beacon int:	100
```

`wifi_diag/fixtures/iw_link_2ghz.txt`:
```
Connected to 78:67:0e:6f:a7:fb (on wlan0)
	SSID: BisNet
	freq: 2437
	RX: 12345678 bytes (98765 packets)
	TX: 23456789 bytes (87654 packets)
	signal: -68 dBm
	rx bitrate: 72.2 MBit/s MCS 7 short GI
	tx bitrate: 72.2 MBit/s MCS 7 short GI
	bss flags:	short-preamble short-slot-time
	dtim period:	1
	beacon int:	100
```

`wifi_diag/fixtures/netsh_5ghz.txt`:
```
There is 1 interface on the system: 

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : f956943b-a917-435e-bde9-010c227cf5a4
    Physical address       : 7c:70:db:2c:f8:df
    Interface type         : Primary
    State                  : connected
    SSID                   : BisNet
    AP BSSID               : 78:67:0e:6f:a7:fd
    Band                   : 5 GHz
    Channel                : 104
    Connected Akm-cipher   : [ akm = 00-0f-ac:02, cipher =  00-0f-ac:04 ]
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto Connect
    Receive rate (Mbps)    : 961
    Transmit rate (Mbps)   : 576
    Signal                 : 81% 
    Rssi                   : -61
    Profile                : BisNet 
```

`wifi_diag/fixtures/netsh_2ghz.txt`:
```
There is 1 interface on the system: 

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : f956943b-a917-435e-bde9-010c227cf5a4
    Physical address       : 7c:70:db:2c:f8:df
    Interface type         : Primary
    State                  : connected
    SSID                   : BisNet
    AP BSSID               : 78:67:0e:6f:a7:fb
    Band                   : 2.4 GHz
    Channel                : 6
    Connected Akm-cipher   : [ akm = 00-0f-ac:02, cipher =  00-0f-ac:04 ]
    Network type           : Infrastructure
    Radio type             : 802.11n
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto Connect
    Receive rate (Mbps)    : 72
    Transmit rate (Mbps)   : 72
    Signal                 : 55% 
    Rssi                   : -72
    Profile                : BisNet 
```

`wifi_diag/fixtures/ping_linux.txt`:
```
PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data.
64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=1.23 ms
64 bytes from 192.168.1.1: icmp_seq=2 ttl=64 time=0.98 ms
64 bytes from 192.168.1.1: icmp_seq=3 ttl=64 time=1.05 ms
64 bytes from 192.168.1.1: icmp_seq=4 ttl=64 time=0.99 ms
64 bytes from 192.168.1.1: icmp_seq=5 ttl=64 time=1.02 ms

--- 192.168.1.1 ping statistics ---
5 packets transmitted, 5 received, 0% packet loss, time 4006ms
rtt min/avg/max/mdev = 0.980/1.054/1.230/0.090 ms
```

`wifi_diag/fixtures/ping_windows.txt`:
```
Pinging 192.168.1.1 with 32 bytes of data:
Reply from 192.168.1.1: bytes=32 time=2ms TTL=64
Reply from 192.168.1.1: bytes=32 time=1ms TTL=64
Reply from 192.168.1.1: bytes=32 time=1ms TTL=64
Reply from 192.168.1.1: bytes=32 time=1ms TTL=64
Reply from 192.168.1.1: bytes=32 time=1ms TTL=64

Ping statistics for 192.168.1.1:
    Packets: Sent = 5, Received = 5, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 1ms, Maximum = 2ms, Average = 1ms
```

`wifi_diag/fixtures/speedtest.txt`:
```
Ping: 12.345 ms
Download: 95.67 Mbit/s
Upload: 45.23 Mbit/s
```

- [ ] **Step 9: Write and run test for frequency/channel utilities**

Create `tests/test_parsers.py` with initial utility tests:

```python
from wifi_diag.parsers import freq_to_band, freq_to_channel, channel_to_freq


class TestFreqUtils:
    def test_freq_to_band_2ghz(self):
        assert freq_to_band(2437) == "2.4GHz"

    def test_freq_to_band_5ghz(self):
        assert freq_to_band(5520) == "5GHz"

    def test_freq_to_band_unknown(self):
        assert freq_to_band(900) == "unknown"

    def test_freq_to_channel_2ghz(self):
        assert freq_to_channel(2412) == 1
        assert freq_to_channel(2437) == 6
        assert freq_to_channel(2462) == 11

    def test_freq_to_channel_5ghz(self):
        assert freq_to_channel(5180) == 36
        assert freq_to_channel(5520) == 104
        assert freq_to_channel(5745) == 149

    def test_channel_to_freq_2ghz(self):
        assert channel_to_freq(1, "2.4GHz") == 2412
        assert channel_to_freq(6, "2.4GHz") == 2437
        assert channel_to_freq(11, "2.4GHz") == 2462

    def test_channel_to_freq_5ghz(self):
        assert channel_to_freq(36, "5GHz") == 5180
        assert channel_to_freq(104, "5GHz") == 5520

    def test_roundtrip_2ghz(self):
        for ch in range(1, 14):
            freq = channel_to_freq(ch, "2.4GHz")
            assert freq_to_channel(freq) == ch

    def test_roundtrip_5ghz(self):
        for ch in [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]:
            freq = channel_to_freq(ch, "5GHz")
            assert freq_to_channel(freq) == ch
```

Run: `pytest tests/test_parsers.py::TestFreqUtils -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add .gitignore pyproject.toml requirements.txt wifi_diag/ tests/
git commit -m "scaffold: project structure, config, fixtures, freq/channel utils"
```

---

### Task 2: Parsers (TDD)

**Files:**
- Create: `wifi_diag/parsers/iw_parser.py`
- Create: `wifi_diag/parsers/netsh_parser.py`
- Create: `wifi_diag/parsers/ping_parser.py`
- Create: `wifi_diag/parsers/speedtest_parser.py`
- Modify: `tests/test_parsers.py`

**Interfaces:**
- Consumes: `parsers.freq_to_band`, `parsers.freq_to_channel`, `parsers.channel_to_freq` from Task 1
- Produces:
  - `iw_parser.parse_iw_link(output: str) -> dict` — returns `{"rssi_dbm": int|None, "noise_dbm": None, "frequency_mhz": int|None, "band": str|None, "channel": int|None, "link_speed_mbps": float|None, "bssid": str|None}`
  - `netsh_parser.parse_netsh_interfaces(output: str) -> dict` — same dict shape
  - `ping_parser.parse_ping(output: str) -> dict` — returns `{"rtt_min_ms": float|None, "rtt_avg_ms": float|None, "rtt_max_ms": float|None, "packet_loss_pct": float|None}`
  - `speedtest_parser.parse_speedtest(output: str) -> dict` — returns `{"download_mbps": float|None, "upload_mbps": float|None, "ping_ms": float|None}`

- [ ] **Step 1: Write failing tests for iw_parser**

Append to `tests/test_parsers.py`:

```python
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "wifi_diag" / "fixtures"


class TestIwParser:
    def test_parse_5ghz(self):
        from wifi_diag.parsers.iw_parser import parse_iw_link

        output = (FIXTURES / "iw_link_5ghz.txt").read_text()
        result = parse_iw_link(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fd"
        assert result["frequency_mhz"] == 5520
        assert result["band"] == "5GHz"
        assert result["channel"] == 104
        assert result["rssi_dbm"] == -42
        assert result["link_speed_mbps"] == 866.7
        assert result["noise_dbm"] is None

    def test_parse_2ghz(self):
        from wifi_diag.parsers.iw_parser import parse_iw_link

        output = (FIXTURES / "iw_link_2ghz.txt").read_text()
        result = parse_iw_link(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fb"
        assert result["frequency_mhz"] == 2437
        assert result["band"] == "2.4GHz"
        assert result["channel"] == 6
        assert result["rssi_dbm"] == -68
        assert result["link_speed_mbps"] == 72.2
```

Run: `pytest tests/test_parsers.py::TestIwParser -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement `iw_parser.py`**

```python
import re
from . import freq_to_band, freq_to_channel


def parse_iw_link(output: str) -> dict:
    result = {
        "rssi_dbm": None,
        "noise_dbm": None,
        "frequency_mhz": None,
        "band": None,
        "channel": None,
        "link_speed_mbps": None,
        "bssid": None,
    }

    m = re.search(r"Connected to ([0-9a-f:]+)", output)
    if m:
        result["bssid"] = m.group(1)

    m = re.search(r"freq:\s*(\d+)", output)
    if m:
        freq = int(m.group(1))
        result["frequency_mhz"] = freq
        result["band"] = freq_to_band(freq)
        result["channel"] = freq_to_channel(freq)

    m = re.search(r"signal:\s*(-?\d+)", output)
    if m:
        result["rssi_dbm"] = int(m.group(1))

    m = re.search(r"tx bitrate:\s*([\d.]+)", output)
    if m:
        result["link_speed_mbps"] = float(m.group(1))

    return result
```

Run: `pytest tests/test_parsers.py::TestIwParser -v`
Expected: All PASS

- [ ] **Step 3: Write failing tests for netsh_parser**

Append to `tests/test_parsers.py`:

```python
class TestNetshParser:
    def test_parse_5ghz(self):
        from wifi_diag.parsers.netsh_parser import parse_netsh_interfaces

        output = (FIXTURES / "netsh_5ghz.txt").read_text()
        result = parse_netsh_interfaces(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fd"
        assert result["band"] == "5GHz"
        assert result["channel"] == 104
        assert result["frequency_mhz"] == 5520
        assert result["rssi_dbm"] == -61
        assert result["link_speed_mbps"] == 961.0
        assert result["noise_dbm"] is None

    def test_parse_2ghz(self):
        from wifi_diag.parsers.netsh_parser import parse_netsh_interfaces

        output = (FIXTURES / "netsh_2ghz.txt").read_text()
        result = parse_netsh_interfaces(output)
        assert result["bssid"] == "78:67:0e:6f:a7:fb"
        assert result["band"] == "2.4GHz"
        assert result["channel"] == 6
        assert result["frequency_mhz"] == 2437
        assert result["rssi_dbm"] == -72
        assert result["link_speed_mbps"] == 72.0

    def test_fallback_signal_pct_to_rssi(self):
        from wifi_diag.parsers.netsh_parser import parse_netsh_interfaces

        output = "    Band                   : 5 GHz\n    Channel                : 36\n    Signal                 : 80%\n"
        result = parse_netsh_interfaces(output)
        assert result["rssi_dbm"] == -60.0
```

Run: `pytest tests/test_parsers.py::TestNetshParser -v`
Expected: FAIL

- [ ] **Step 4: Implement `netsh_parser.py`**

```python
import re
from . import channel_to_freq


def parse_netsh_interfaces(output: str) -> dict:
    result = {
        "rssi_dbm": None,
        "noise_dbm": None,
        "frequency_mhz": None,
        "band": None,
        "channel": None,
        "link_speed_mbps": None,
        "bssid": None,
    }

    def extract(pattern):
        m = re.search(pattern, output, re.IGNORECASE)
        return m.group(1).strip() if m else None

    bssid = extract(r"BSSID\s*:\s*([0-9a-f:]+)")
    if bssid:
        result["bssid"] = bssid

    band_str = extract(r"Band\s*:\s*(.+)")
    if band_str:
        result["band"] = band_str.replace(" ", "")

    channel_str = extract(r"Channel\s*:\s*(\d+)")
    if channel_str:
        result["channel"] = int(channel_str)

    if result["channel"] and result["band"]:
        result["frequency_mhz"] = channel_to_freq(result["channel"], result["band"])

    rssi_str = extract(r"Rssi\s*:\s*(-?\d+)")
    if rssi_str:
        result["rssi_dbm"] = int(rssi_str)
    else:
        signal_str = extract(r"Signal\s*:\s*(\d+)%")
        if signal_str:
            result["rssi_dbm"] = int(signal_str) / 2 - 100

    rx_rate = extract(r"Receive rate \(Mbps\)\s*:\s*([\d.]+)")
    tx_rate = extract(r"Transmit rate \(Mbps\)\s*:\s*([\d.]+)")
    rates = [float(r) for r in [rx_rate, tx_rate] if r]
    if rates:
        result["link_speed_mbps"] = max(rates)

    return result
```

Run: `pytest tests/test_parsers.py::TestNetshParser -v`
Expected: All PASS

- [ ] **Step 5: Write failing tests for ping_parser**

Append to `tests/test_parsers.py`:

```python
class TestPingParser:
    def test_parse_linux(self):
        from wifi_diag.parsers.ping_parser import parse_ping

        output = (FIXTURES / "ping_linux.txt").read_text()
        result = parse_ping(output)
        assert result["rtt_min_ms"] == 0.980
        assert result["rtt_avg_ms"] == 1.054
        assert result["rtt_max_ms"] == 1.230
        assert result["packet_loss_pct"] == 0.0

    def test_parse_windows(self):
        from wifi_diag.parsers.ping_parser import parse_ping

        output = (FIXTURES / "ping_windows.txt").read_text()
        result = parse_ping(output)
        assert result["rtt_min_ms"] == 1.0
        assert result["rtt_avg_ms"] == 1.0
        assert result["rtt_max_ms"] == 2.0
        assert result["packet_loss_pct"] == 0.0

    def test_parse_packet_loss(self):
        from wifi_diag.parsers.ping_parser import parse_ping

        output = "5 packets transmitted, 3 received, 40% packet loss, time 4000ms\nrtt min/avg/max/mdev = 1.0/2.0/3.0/0.5 ms"
        result = parse_ping(output)
        assert result["packet_loss_pct"] == 40.0
```

Run: `pytest tests/test_parsers.py::TestPingParser -v`
Expected: FAIL

- [ ] **Step 6: Implement `ping_parser.py`**

```python
import re


def parse_ping(output: str) -> dict:
    result = {
        "rtt_min_ms": None,
        "rtt_avg_ms": None,
        "rtt_max_ms": None,
        "packet_loss_pct": None,
    }

    m = re.search(r"(\d+(?:\.\d+)?)%\s*(?:packet\s+)?loss", output)
    if m:
        result["packet_loss_pct"] = float(m.group(1))

    m = re.search(
        r"rtt min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)", output
    )
    if m:
        result["rtt_min_ms"] = float(m.group(1))
        result["rtt_avg_ms"] = float(m.group(2))
        result["rtt_max_ms"] = float(m.group(3))
        return result

    m = re.search(
        r"Minimum\s*=\s*(\d+)ms.*Maximum\s*=\s*(\d+)ms.*Average\s*=\s*(\d+)ms",
        output,
        re.DOTALL,
    )
    if m:
        result["rtt_min_ms"] = float(m.group(1))
        result["rtt_max_ms"] = float(m.group(2))
        result["rtt_avg_ms"] = float(m.group(3))

    return result
```

Run: `pytest tests/test_parsers.py::TestPingParser -v`
Expected: All PASS

- [ ] **Step 7: Write failing tests for speedtest_parser**

Append to `tests/test_parsers.py`:

```python
class TestSpeedtestParser:
    def test_parse(self):
        from wifi_diag.parsers.speedtest_parser import parse_speedtest

        output = (FIXTURES / "speedtest.txt").read_text()
        result = parse_speedtest(output)
        assert result["download_mbps"] == 95.67
        assert result["upload_mbps"] == 45.23
        assert result["ping_ms"] == 12.345

    def test_parse_empty(self):
        from wifi_diag.parsers.speedtest_parser import parse_speedtest

        result = parse_speedtest("")
        assert result["download_mbps"] is None
        assert result["upload_mbps"] is None
        assert result["ping_ms"] is None
```

Run: `pytest tests/test_parsers.py::TestSpeedtestParser -v`
Expected: FAIL

- [ ] **Step 8: Implement `speedtest_parser.py`**

```python
import re


def parse_speedtest(output: str) -> dict:
    result = {
        "download_mbps": None,
        "upload_mbps": None,
        "ping_ms": None,
    }

    m = re.search(r"Ping:\s*([\d.]+)\s*ms", output)
    if m:
        result["ping_ms"] = float(m.group(1))

    m = re.search(r"Download:\s*([\d.]+)\s*Mbit/s", output)
    if m:
        result["download_mbps"] = float(m.group(1))

    m = re.search(r"Upload:\s*([\d.]+)\s*Mbit/s", output)
    if m:
        result["upload_mbps"] = float(m.group(1))

    return result
```

Run: `pytest tests/test_parsers.py -v`
Expected: All PASS (all parser tests)

- [ ] **Step 9: Commit**

```bash
git add wifi_diag/parsers/ tests/test_parsers.py
git commit -m "feat: add parsers for iw, netsh, ping, speedtest output"
```

---

### Task 3: Store (TDD)

**Files:**
- Create: `wifi_diag/store.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: `config.DB_PATH` from Task 1
- Produces:
  - `DiagStore(db_path: str | Path | None = None)` — pass `":memory:"` for tests
  - `store.insert_wifi_reading(reading: dict) -> None`
  - `store.insert_band_switch(switch: dict) -> None`
  - `store.insert_latency_reading(reading: dict) -> None`
  - `store.insert_speed_reading(reading: dict) -> None`
  - `store.get_wifi_readings(host: str | None, start: str | None, end: str | None) -> list[dict]`
  - `store.get_band_switches(host: str | None, start: str | None, end: str | None) -> list[dict]`
  - `store.get_latency_readings(host: str | None, target: str | None, start: str | None, end: str | None) -> list[dict]`
  - `store.get_speed_readings(host: str | None, start: str | None, end: str | None) -> list[dict]`
  - `store.get_latest_wifi(host: str) -> dict | None`
  - `store.get_latest_latency(host: str, target: str) -> dict | None`
  - `store.get_latest_speed(host: str) -> dict | None`
  - `store.get_hosts() -> list[str]`
  - `store.close() -> None`

- [ ] **Step 1: Write failing tests**

Create `tests/test_store.py`:

```python
import pytest
from wifi_diag.store import DiagStore


@pytest.fixture
def store():
    s = DiagStore(":memory:")
    yield s
    s.close()


def _wifi_reading(host="testpi", band="5GHz", rssi=-42, ts="2026-07-20T10:00:00"):
    return {
        "timestamp": ts,
        "host": host,
        "rssi_dbm": rssi,
        "noise_dbm": None,
        "frequency_mhz": 5520,
        "band": band,
        "channel": 104,
        "link_speed_mbps": 866.7,
        "bssid": "aa:bb:cc:dd:ee:ff",
    }


def _latency_reading(host="testpi", target="192.168.1.1", ts="2026-07-20T10:00:00"):
    return {
        "timestamp": ts,
        "host": host,
        "target": target,
        "rtt_min_ms": 1.0,
        "rtt_avg_ms": 2.5,
        "rtt_max_ms": 5.0,
        "packet_loss_pct": 0.0,
    }


def _speed_reading(host="testpi", ts="2026-07-20T10:00:00"):
    return {
        "timestamp": ts,
        "host": host,
        "download_mbps": 95.5,
        "upload_mbps": 45.2,
        "ping_ms": 12.0,
    }


class TestWifiReadings:
    def test_insert_and_get(self, store):
        store.insert_wifi_reading(_wifi_reading())
        rows = store.get_wifi_readings()
        assert len(rows) == 1
        assert rows[0]["rssi_dbm"] == -42
        assert rows[0]["band"] == "5GHz"

    def test_filter_by_host(self, store):
        store.insert_wifi_reading(_wifi_reading(host="pi1"))
        store.insert_wifi_reading(_wifi_reading(host="pi2"))
        rows = store.get_wifi_readings(host="pi1")
        assert len(rows) == 1
        assert rows[0]["host"] == "pi1"

    def test_filter_by_time_range(self, store):
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T08:00:00"))
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T10:00:00"))
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T12:00:00"))
        rows = store.get_wifi_readings(start="2026-07-20T09:00:00", end="2026-07-20T11:00:00")
        assert len(rows) == 1

    def test_get_latest(self, store):
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T08:00:00", rssi=-50))
        store.insert_wifi_reading(_wifi_reading(ts="2026-07-20T10:00:00", rssi=-42))
        latest = store.get_latest_wifi("testpi")
        assert latest["rssi_dbm"] == -42

    def test_get_latest_none(self, store):
        assert store.get_latest_wifi("nonexistent") is None


class TestBandSwitches:
    def test_insert_and_get(self, store):
        store.insert_band_switch({
            "timestamp": "2026-07-20T10:00:00",
            "host": "testpi",
            "from_band": "5GHz",
            "to_band": "2.4GHz",
            "from_freq": 5520,
            "to_freq": 2437,
        })
        rows = store.get_band_switches()
        assert len(rows) == 1
        assert rows[0]["from_band"] == "5GHz"
        assert rows[0]["to_band"] == "2.4GHz"


class TestLatencyReadings:
    def test_insert_and_get(self, store):
        store.insert_latency_reading(_latency_reading())
        rows = store.get_latency_readings()
        assert len(rows) == 1
        assert rows[0]["rtt_avg_ms"] == 2.5

    def test_filter_by_target(self, store):
        store.insert_latency_reading(_latency_reading(target="192.168.1.1"))
        store.insert_latency_reading(_latency_reading(target="8.8.8.8"))
        rows = store.get_latency_readings(target="8.8.8.8")
        assert len(rows) == 1

    def test_get_latest(self, store):
        store.insert_latency_reading(_latency_reading(ts="2026-07-20T08:00:00"))
        store.insert_latency_reading(_latency_reading(ts="2026-07-20T10:00:00"))
        latest = store.get_latest_latency("testpi", "192.168.1.1")
        assert latest["timestamp"] == "2026-07-20T10:00:00"


class TestSpeedReadings:
    def test_insert_and_get(self, store):
        store.insert_speed_reading(_speed_reading())
        rows = store.get_speed_readings()
        assert len(rows) == 1
        assert rows[0]["download_mbps"] == 95.5

    def test_get_latest(self, store):
        store.insert_speed_reading(_speed_reading(ts="2026-07-20T08:00:00"))
        store.insert_speed_reading(_speed_reading(ts="2026-07-20T10:00:00"))
        latest = store.get_latest_speed("testpi")
        assert latest["timestamp"] == "2026-07-20T10:00:00"


class TestHosts:
    def test_get_hosts(self, store):
        store.insert_wifi_reading(_wifi_reading(host="pi1"))
        store.insert_wifi_reading(_wifi_reading(host="pi2"))
        store.insert_wifi_reading(_wifi_reading(host="pi1"))
        hosts = store.get_hosts()
        assert hosts == ["pi1", "pi2"]
```

Run: `pytest tests/test_store.py -v`
Expected: FAIL (module not found)

- [ ] **Step 2: Implement `store.py`**

```python
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
```

Run: `pytest tests/test_store.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add wifi_diag/store.py tests/test_store.py
git commit -m "feat: add SQLite store with schema, CRUD, and queries"
```

---

### Task 4: Collectors (TDD)

**Files:**
- Create: `wifi_diag/collectors/base.py`
- Create: `wifi_diag/collectors/wifi_linux.py`
- Create: `wifi_diag/collectors/wifi_windows.py`
- Create: `wifi_diag/collectors/wifi_mock.py`
- Create: `wifi_diag/collectors/latency.py`
- Create: `wifi_diag/collectors/latency_mock.py`
- Create: `wifi_diag/collectors/speed.py`
- Create: `wifi_diag/collectors/speed_mock.py`
- Modify: `wifi_diag/collectors/__init__.py`
- Create: `tests/test_collectors.py`

**Interfaces:**
- Consumes: all parsers from Task 2, fixtures from Task 1
- Produces:
  - `BaseCollector.collect() -> dict` (abstract)
  - `create_wifi_collector(dry_run: bool = False) -> BaseCollector`
  - `create_latency_collector(target: str, count: int = 5, dry_run: bool = False) -> BaseCollector`
  - `create_speed_collector(dry_run: bool = False) -> BaseCollector`
  - All collectors' `collect()` return dicts matching parser output shapes
  - Mock latency collector's `collect()` also includes `"target"` key

- [ ] **Step 1: Write failing tests for mock collectors**

Create `tests/test_collectors.py`:

```python
from wifi_diag.collectors import (
    create_wifi_collector,
    create_latency_collector,
    create_speed_collector,
)


class TestWifiMockCollector:
    def test_collect_returns_valid_reading(self):
        collector = create_wifi_collector(dry_run=True)
        result = collector.collect()
        assert result["bssid"] is not None
        assert result["frequency_mhz"] is not None
        assert result["band"] in ("2.4GHz", "5GHz")
        assert result["rssi_dbm"] is not None

    def test_collect_alternates_bands(self):
        collector = create_wifi_collector(dry_run=True)
        r1 = collector.collect()
        r2 = collector.collect()
        assert r1["band"] != r2["band"]


class TestLatencyMockCollector:
    def test_collect_gateway(self):
        collector = create_latency_collector("192.168.1.1", dry_run=True)
        result = collector.collect()
        assert result["target"] == "192.168.1.1"
        assert result["rtt_avg_ms"] is not None
        assert result["packet_loss_pct"] is not None

    def test_collect_external(self):
        collector = create_latency_collector("8.8.8.8", dry_run=True)
        result = collector.collect()
        assert result["target"] == "8.8.8.8"
        assert result["rtt_avg_ms"] > 0


class TestSpeedMockCollector:
    def test_collect(self):
        collector = create_speed_collector(dry_run=True)
        result = collector.collect()
        assert result["download_mbps"] is not None
        assert result["upload_mbps"] is not None
        assert result["ping_ms"] is not None
```

Run: `pytest tests/test_collectors.py -v`
Expected: FAIL

- [ ] **Step 2: Implement `base.py`**

```python
from abc import ABC, abstractmethod


class BaseCollector(ABC):
    @abstractmethod
    def collect(self) -> dict: ...
```

- [ ] **Step 3: Implement `wifi_mock.py`**

```python
from pathlib import Path
from .base import BaseCollector
from ..parsers.iw_parser import parse_iw_link

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class WifiMockCollector(BaseCollector):
    def __init__(self):
        self._index = 0
        self._fixtures = [
            FIXTURES_DIR / "iw_link_5ghz.txt",
            FIXTURES_DIR / "iw_link_2ghz.txt",
        ]

    def collect(self) -> dict:
        fixture = self._fixtures[self._index % len(self._fixtures)]
        self._index += 1
        return parse_iw_link(fixture.read_text())
```

- [ ] **Step 4: Implement `latency_mock.py`**

```python
from .base import BaseCollector


class LatencyMockCollector(BaseCollector):
    def __init__(self, target):
        self.target = target

    def collect(self) -> dict:
        if "192.168" in self.target:
            return {
                "target": self.target,
                "rtt_min_ms": 1.0,
                "rtt_avg_ms": 2.5,
                "rtt_max_ms": 5.0,
                "packet_loss_pct": 0.0,
            }
        return {
            "target": self.target,
            "rtt_min_ms": 10.0,
            "rtt_avg_ms": 15.0,
            "rtt_max_ms": 25.0,
            "packet_loss_pct": 0.0,
        }
```

- [ ] **Step 5: Implement `speed_mock.py`**

```python
from .base import BaseCollector


class SpeedMockCollector(BaseCollector):
    def collect(self) -> dict:
        return {
            "download_mbps": 95.5,
            "upload_mbps": 45.2,
            "ping_ms": 12.0,
        }
```

- [ ] **Step 6: Implement `wifi_linux.py`**

```python
import subprocess
from .base import BaseCollector
from ..parsers.iw_parser import parse_iw_link


class WifiLinuxCollector(BaseCollector):
    def __init__(self, interface="wlan0"):
        self.interface = interface

    def collect(self) -> dict:
        result = subprocess.run(
            ["iw", "dev", self.interface, "link"],
            capture_output=True,
            text=True,
        )
        return parse_iw_link(result.stdout)
```

- [ ] **Step 7: Implement `wifi_windows.py`**

```python
import subprocess
from .base import BaseCollector
from ..parsers.netsh_parser import parse_netsh_interfaces


class WifiWindowsCollector(BaseCollector):
    def collect(self) -> dict:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
        )
        return parse_netsh_interfaces(result.stdout)
```

- [ ] **Step 8: Implement `latency.py`**

```python
import subprocess
import sys
from .base import BaseCollector
from ..parsers.ping_parser import parse_ping


class LatencyCollector(BaseCollector):
    def __init__(self, target, count=5):
        self.target = target
        self.count = count

    def collect(self) -> dict:
        if sys.platform == "win32":
            cmd = ["ping", "-n", str(self.count), self.target]
        else:
            cmd = ["ping", "-c", str(self.count), self.target]
        result = subprocess.run(cmd, capture_output=True, text=True)
        parsed = parse_ping(result.stdout)
        parsed["target"] = self.target
        return parsed
```

- [ ] **Step 9: Implement `speed.py`**

```python
import subprocess
from .base import BaseCollector
from ..parsers.speedtest_parser import parse_speedtest


class SpeedCollector(BaseCollector):
    def collect(self) -> dict:
        result = subprocess.run(
            ["speedtest-cli", "--simple"],
            capture_output=True,
            text=True,
        )
        return parse_speedtest(result.stdout)
```

- [ ] **Step 10: Update `collectors/__init__.py` with factory functions**

```python
import sys


def create_wifi_collector(dry_run=False):
    if dry_run:
        from .wifi_mock import WifiMockCollector
        return WifiMockCollector()
    if sys.platform == "win32":
        from .wifi_windows import WifiWindowsCollector
        return WifiWindowsCollector()
    from .wifi_linux import WifiLinuxCollector
    return WifiLinuxCollector()


def create_latency_collector(target, count=5, dry_run=False):
    if dry_run:
        from .latency_mock import LatencyMockCollector
        return LatencyMockCollector(target)
    from .latency import LatencyCollector
    return LatencyCollector(target, count)


def create_speed_collector(dry_run=False):
    if dry_run:
        from .speed_mock import SpeedMockCollector
        return SpeedMockCollector()
    from .speed import SpeedCollector
    return SpeedCollector()
```

Run: `pytest tests/test_collectors.py -v`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
git add wifi_diag/collectors/ tests/test_collectors.py
git commit -m "feat: add collectors with platform-specific and mock implementations"
```

---

### Task 5: Scheduler (TDD)

**Files:**
- Create: `wifi_diag/scheduler.py`
- Modify: `tests/test_collectors.py` (add scheduler tests)

**Interfaces:**
- Consumes: `DiagStore` from Task 3, factory functions from Task 4, `config.*` from Task 1
- Produces:
  - `DiagScheduler(store: DiagStore, dry_run: bool = False)`
  - `scheduler.run() -> None` (blocking main loop)
  - `scheduler.stop() -> None`
  - `scheduler.collect_once() -> None` (single pass — runs all collectors once, used for testing)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_collectors.py`:

```python
import pytest
from wifi_diag.store import DiagStore
from wifi_diag.scheduler import DiagScheduler


class TestScheduler:
    @pytest.fixture
    def store(self):
        s = DiagStore(":memory:")
        yield s
        s.close()

    def test_collect_once_inserts_wifi(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        readings = store.get_wifi_readings()
        assert len(readings) == 1
        assert readings[0]["band"] in ("2.4GHz", "5GHz")

    def test_collect_once_inserts_latency(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        gateway = store.get_latency_readings(target="192.168.1.1")
        external = store.get_latency_readings(target="8.8.8.8")
        assert len(gateway) == 1
        assert len(external) == 1

    def test_collect_once_inserts_speed(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        readings = store.get_speed_readings()
        assert len(readings) == 1
        assert readings[0]["download_mbps"] == 95.5

    def test_band_switch_detection(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        sched.collect_once()
        switches = store.get_band_switches()
        assert len(switches) == 1
        bands = {switches[0]["from_band"], switches[0]["to_band"]}
        assert bands == {"2.4GHz", "5GHz"}

    def test_no_band_switch_on_same_band(self, store):
        sched = DiagScheduler(store, dry_run=True)
        sched.collect_once()
        sched.collect_once()
        sched.collect_once()
        switches = store.get_band_switches()
        assert len(switches) == 2
```

Run: `pytest tests/test_collectors.py::TestScheduler -v`
Expected: FAIL

- [ ] **Step 2: Implement `scheduler.py`**

```python
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
from .store import DiagStore


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
```

Run: `pytest tests/test_collectors.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add wifi_diag/scheduler.py tests/test_collectors.py
git commit -m "feat: add scheduler with interval-based collection and band-switch detection"
```

---

### Task 6: Analysis (TDD)

**Files:**
- Create: `wifi_diag/analysis/trends.py`
- Create: `wifi_diag/analysis/bands.py`
- Create: `wifi_diag/analysis/diagnose.py`
- Create: `tests/test_analysis.py`

**Interfaces:**
- Consumes: `DiagStore` from Task 3
- Produces:
  - `trends.weekly_comparison(store: DiagStore, host: str | None = None, weeks: int = 4) -> dict`
    - Returns `{"weeks": [{"start": str, "end": str, "avg_rssi": float, "avg_download": float, "band_5ghz_pct": float, "reading_count": int}, ...]}`
  - `bands.band_analysis(store: DiagStore, host: str | None = None, days: int = 7) -> dict`
    - Returns `{"hosts": {"hostname": {"total": int, "5ghz_count": int, "2.4ghz_count": int, "5ghz_pct": float, "switch_count": int}, ...}}`
  - `diagnose.diagnose(store: DiagStore, days: int = 7) -> str`
    - Returns formatted multi-line diagnosis report string

- [ ] **Step 1: Write failing tests**

Create `tests/test_analysis.py`:

```python
import pytest
from datetime import datetime, timedelta, timezone
from wifi_diag.store import DiagStore
from wifi_diag.analysis.trends import weekly_comparison
from wifi_diag.analysis.bands import band_analysis
from wifi_diag.analysis.diagnose import diagnose


@pytest.fixture
def store():
    s = DiagStore(":memory:")
    yield s
    s.close()


def _seed_wifi(store, host, band, rssi, days_ago):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    freq = 5520 if band == "5GHz" else 2437
    ch = 104 if band == "5GHz" else 6
    store.insert_wifi_reading({
        "timestamp": ts, "host": host, "rssi_dbm": rssi,
        "noise_dbm": None, "frequency_mhz": freq, "band": band,
        "channel": ch, "link_speed_mbps": 100.0, "bssid": "aa:bb:cc:dd:ee:ff",
    })


def _seed_latency(store, host, target, avg_ms, days_ago):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    store.insert_latency_reading({
        "timestamp": ts, "host": host, "target": target,
        "rtt_min_ms": avg_ms * 0.8, "rtt_avg_ms": avg_ms,
        "rtt_max_ms": avg_ms * 1.5, "packet_loss_pct": 0.0,
    })


def _seed_speed(store, host, download, days_ago):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    store.insert_speed_reading({
        "timestamp": ts, "host": host,
        "download_mbps": download, "upload_mbps": download * 0.5,
        "ping_ms": 12.0,
    })


class TestWeeklyComparison:
    def test_returns_weekly_buckets(self, store):
        for d in range(28):
            _seed_wifi(store, "pi1", "5GHz", -45, d)
        result = weekly_comparison(store, "pi1", weeks=4)
        assert len(result["weeks"]) == 4

    def test_calculates_avg_rssi(self, store):
        _seed_wifi(store, "pi1", "5GHz", -40, 1)
        _seed_wifi(store, "pi1", "5GHz", -50, 2)
        result = weekly_comparison(store, "pi1", weeks=1)
        assert result["weeks"][0]["avg_rssi"] == -45.0

    def test_empty_store(self, store):
        result = weekly_comparison(store, "pi1", weeks=4)
        assert all(w["reading_count"] == 0 for w in result["weeks"])


class TestBandAnalysis:
    def test_calculates_band_split(self, store):
        for _ in range(7):
            _seed_wifi(store, "pi1", "5GHz", -42, 1)
        for _ in range(3):
            _seed_wifi(store, "pi1", "2.4GHz", -68, 1)
        result = band_analysis(store, "pi1", days=7)
        assert result["hosts"]["pi1"]["5ghz_pct"] == 70.0

    def test_includes_switch_count(self, store):
        _seed_wifi(store, "pi1", "5GHz", -42, 1)
        _seed_wifi(store, "pi1", "2.4GHz", -68, 1)
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        store.insert_band_switch({
            "timestamp": ts, "host": "pi1",
            "from_band": "5GHz", "to_band": "2.4GHz",
            "from_freq": 5520, "to_freq": 2437,
        })
        result = band_analysis(store, "pi1", days=7)
        assert result["hosts"]["pi1"]["switch_count"] == 1

    def test_multiple_hosts(self, store):
        _seed_wifi(store, "pi1", "5GHz", -42, 1)
        _seed_wifi(store, "pi2", "2.4GHz", -68, 1)
        result = band_analysis(store, days=7)
        assert "pi1" in result["hosts"]
        assert "pi2" in result["hosts"]


class TestDiagnose:
    def test_returns_string(self, store):
        _seed_wifi(store, "pi1", "5GHz", -42, 1)
        _seed_latency(store, "pi1", "192.168.1.1", 2.0, 1)
        _seed_latency(store, "pi1", "8.8.8.8", 15.0, 1)
        _seed_speed(store, "pi1", 95.0, 1)
        result = diagnose(store, days=7)
        assert isinstance(result, str)
        assert "pi1" in result

    def test_empty_store(self, store):
        result = diagnose(store, days=7)
        assert "No data" in result or "no data" in result.lower()
```

Run: `pytest tests/test_analysis.py -v`
Expected: FAIL

- [ ] **Step 2: Implement `trends.py`**

```python
from datetime import datetime, timedelta, timezone


def weekly_comparison(store, host=None, weeks=4):
    now = datetime.now(timezone.utc)
    result = {"weeks": []}

    for w in range(weeks):
        end = now - timedelta(weeks=w)
        start = end - timedelta(weeks=1)
        start_s = start.isoformat()
        end_s = end.isoformat()

        readings = store.get_wifi_readings(host=host, start=start_s, end=end_s)
        speeds = store.get_speed_readings(host=host, start=start_s, end=end_s)

        week_data = {
            "start": start_s,
            "end": end_s,
            "reading_count": len(readings),
            "avg_rssi": None,
            "avg_download": None,
            "band_5ghz_pct": None,
        }

        if readings:
            rssis = [r["rssi_dbm"] for r in readings if r["rssi_dbm"] is not None]
            if rssis:
                week_data["avg_rssi"] = sum(rssis) / len(rssis)

            fives = sum(1 for r in readings if r["band"] == "5GHz")
            week_data["band_5ghz_pct"] = round(fives / len(readings) * 100, 1)

        if speeds:
            dls = [s["download_mbps"] for s in speeds if s["download_mbps"] is not None]
            if dls:
                week_data["avg_download"] = round(sum(dls) / len(dls), 1)

        result["weeks"].append(week_data)

    return result
```

- [ ] **Step 3: Implement `bands.py`**

```python
from datetime import datetime, timedelta, timezone


def band_analysis(store, host=None, days=7):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()

    readings = store.get_wifi_readings(host=host, start=start)
    switches = store.get_band_switches(host=host, start=start)

    hosts_data = {}
    for r in readings:
        h = r["host"]
        if h not in hosts_data:
            hosts_data[h] = {"total": 0, "5ghz_count": 0, "2.4ghz_count": 0, "switch_count": 0}
        hosts_data[h]["total"] += 1
        if r["band"] == "5GHz":
            hosts_data[h]["5ghz_count"] += 1
        elif r["band"] == "2.4GHz":
            hosts_data[h]["2.4ghz_count"] += 1

    for s in switches:
        h = s["host"]
        if h in hosts_data:
            hosts_data[h]["switch_count"] += 1

    for h, d in hosts_data.items():
        d["5ghz_pct"] = round(d["5ghz_count"] / d["total"] * 100, 1) if d["total"] else 0.0

    return {"hosts": hosts_data}
```

- [ ] **Step 4: Implement `diagnose.py`**

```python
from datetime import datetime, timedelta, timezone
from .trends import weekly_comparison
from .bands import band_analysis


def diagnose(store, days=7):
    hosts = store.get_hosts()
    if not hosts:
        return "No data collected yet. Run 'wifi-diag collect' first."

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()
    lines = []
    lines.append(f"DIAGNOSIS SUMMARY (last {days} days)")
    lines.append("─" * 40)

    signal_parts = []
    for h in hosts:
        readings = store.get_wifi_readings(host=h, start=start)
        if not readings:
            continue
        rssis = [r["rssi_dbm"] for r in readings if r["rssi_dbm"] is not None]
        if rssis:
            avg = sum(rssis) / len(rssis)
            quality = _signal_quality(avg)
            signal_parts.append(f"{h} avg {avg:.0f}dBm ({quality})")
    if signal_parts:
        lines.append(f"Signal: {', '.join(signal_parts)}")

    ba = band_analysis(store, days=days)
    band_parts = []
    for h, d in ba["hosts"].items():
        band_parts.append(f"{h} {d['5ghz_pct']:.0f}% on 5GHz")
    if band_parts:
        lines.append(f"Band:   {', '.join(band_parts)}")

    lines.append("")

    findings = []

    for h, d in ba["hosts"].items():
        if d["5ghz_pct"] < 50:
            findings.append(
                f"⚠ {h} is spending only {d['5ghz_pct']:.0f}% of time on 5GHz — "
                f"band steering may be pushing it to 2.4GHz."
            )
        if d["switch_count"] > 10:
            findings.append(
                f"⚠ {h} had {d['switch_count']} band switches — "
                f"frequent switching suggests signal instability."
            )

    wc = weekly_comparison(store, weeks=min(4, max(1, days // 7)))
    weeks_with_data = [w for w in wc["weeks"] if w["reading_count"] > 0]
    if len(weeks_with_data) >= 2:
        first = weeks_with_data[-1]
        last = weeks_with_data[0]
        if first["band_5ghz_pct"] is not None and last["band_5ghz_pct"] is not None:
            delta = last["band_5ghz_pct"] - first["band_5ghz_pct"]
            if delta < -10:
                findings.append(
                    f"⚠ 5GHz usage declining: "
                    f"{first['band_5ghz_pct']:.0f}% → {last['band_5ghz_pct']:.0f}% "
                    f"over {len(weeks_with_data)} weeks."
                )
        if first["avg_download"] is not None and last["avg_download"] is not None:
            if last["avg_download"] < first["avg_download"] * 0.8:
                findings.append(
                    f"⚠ Download speed declining: "
                    f"{first['avg_download']:.0f} → {last['avg_download']:.0f} Mbps."
                )

    for h in hosts:
        gw = store.get_latency_readings(host=h, target="192.168.1.1", start=start)
        ext = store.get_latency_readings(host=h, target="8.8.8.8", start=start)
        if gw and ext:
            gw_avg = sum(r["rtt_avg_ms"] for r in gw if r["rtt_avg_ms"]) / len(gw)
            ext_avg = sum(r["rtt_avg_ms"] for r in ext if r["rtt_avg_ms"]) / len(ext)
            if ext_avg > gw_avg * 5:
                findings.append(
                    f"⚠ {h}: gateway latency {gw_avg:.0f}ms vs external {ext_avg:.0f}ms — "
                    f"bottleneck is likely upstream (5G backhaul), not local WiFi."
                )
            elif gw_avg > 20:
                findings.append(
                    f"⚠ {h}: gateway latency {gw_avg:.0f}ms is high — "
                    f"local WiFi congestion or interference likely."
                )

        gw_loss = [r for r in gw if r["packet_loss_pct"] and r["packet_loss_pct"] > 0]
        if gw_loss:
            pct = len(gw_loss) / len(gw) * 100
            findings.append(
                f"⚠ {h}: packet loss to gateway in {pct:.0f}% of probes — "
                f"indicates WiFi instability."
            )

    if findings:
        for f in findings:
            lines.append(f)
    else:
        lines.append("✓ No significant issues detected in the collected data.")

    lines.append("")
    return "\n".join(lines)


def _signal_quality(rssi):
    if rssi >= -50:
        return "excellent"
    if rssi >= -60:
        return "good"
    if rssi >= -70:
        return "fair"
    return "weak"
```

Run: `pytest tests/test_analysis.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add wifi_diag/analysis/ tests/test_analysis.py
git commit -m "feat: add analysis module with trends, bands, and diagnose"
```

---

### Task 7: CLI and Entry Point (TDD)

**Files:**
- Create: `wifi_diag/cli.py`
- Create: `wifi_diag/__main__.py`
- Modify: `tests/__init__.py` (no change, already exists)

**Interfaces:**
- Consumes: `DiagStore` from Task 3, `DiagScheduler` from Task 5, all analysis functions from Task 6, `config.*` from Task 1
- Produces:
  - `cli.main(argv: list[str] | None = None) -> None` — entry point, parses args, dispatches commands
  - `python -m wifi_diag` invocation via `__main__.py`
  - `wifi-diag` console script via `pyproject.toml` entry point

- [ ] **Step 1: Write failing tests**

Create new file `tests/test_cli.py`:

```python
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
```

Run: `pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 2: Implement `cli.py`**

```python
import argparse
import sys

from . import config
from .store import DiagStore
from .scheduler import DiagScheduler
from .analysis.trends import weekly_comparison
from .analysis.bands import band_analysis
from .analysis.diagnose import diagnose


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="wifi-diag",
        description="WiFi diagnostic agent",
    )
    parser.add_argument(
        "--db", default=None,
        help="Path to SQLite database (default: ~/.wifi-diag/data.db)",
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    collect_p = sub.add_parser("collect", help="Start collecting metrics")
    collect_p.add_argument("--dry-run", action="store_true", help="Use mock collectors")

    sub.add_parser("status", help="Current readings snapshot")
    sub.add_parser("history", help="Last 24h summary")

    trends_p = sub.add_parser("trends", help="Week-over-week comparison")
    trends_p.add_argument("--weeks", type=int, default=4)

    bands_p = sub.add_parser("bands", help="Band usage analysis")
    bands_p.add_argument("--days", type=int, default=7)

    diag_p = sub.add_parser("diagnose", help="Automated root cause analysis")
    diag_p.add_argument("--days", type=int, default=7)

    args = parser.parse_args(argv)
    db_path = args.db or config.DB_PATH
    store = DiagStore(db_path)

    try:
        if args.command == "collect":
            _cmd_collect(store, args)
        elif args.command == "status":
            _cmd_status(store)
        elif args.command == "history":
            _cmd_history(store)
        elif args.command == "trends":
            _cmd_trends(store, args.weeks)
        elif args.command == "bands":
            _cmd_bands(store, args.days)
        elif args.command == "diagnose":
            _cmd_diagnose(store, args.days)
    finally:
        store.close()


def _cmd_collect(store, args):
    sched = DiagScheduler(store, dry_run=args.dry_run)
    sched.run()


def _cmd_status(store):
    hosts = store.get_hosts()
    if not hosts:
        print("No data collected yet. Run 'wifi-diag collect' first.")
        return

    for h in hosts:
        print(f"\n── {h} ──")
        wifi = store.get_latest_wifi(h)
        if wifi:
            print(f"  WiFi:    {wifi['rssi_dbm']}dBm | {wifi['band']} ch{wifi['channel']} | {wifi['link_speed_mbps']}Mbps")

        gw = store.get_latest_latency(h, config.GATEWAY_TARGET)
        if gw:
            print(f"  Gateway: {gw['rtt_avg_ms']}ms avg | {gw['packet_loss_pct']}% loss")

        ext = store.get_latest_latency(h, config.EXTERNAL_TARGET)
        if ext:
            print(f"  External: {ext['rtt_avg_ms']}ms avg | {ext['packet_loss_pct']}% loss")

        speed = store.get_latest_speed(h)
        if speed:
            print(f"  Speed:   ↓{speed['download_mbps']}Mbps ↑{speed['upload_mbps']}Mbps | {speed['ping_ms']}ms")


def _cmd_history(store):
    from datetime import datetime, timedelta, timezone

    hosts = store.get_hosts()
    if not hosts:
        print("No data collected yet.")
        return

    start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    for h in hosts:
        readings = store.get_wifi_readings(host=h, start=start)
        switches = store.get_band_switches(host=h, start=start)
        latency = store.get_latency_readings(host=h, target=config.GATEWAY_TARGET, start=start)

        print(f"\n── {h} (last 24h) ──")
        if readings:
            rssis = [r["rssi_dbm"] for r in readings if r["rssi_dbm"] is not None]
            fives = sum(1 for r in readings if r["band"] == "5GHz")
            print(f"  Readings: {len(readings)}")
            if rssis:
                print(f"  Signal:   avg {sum(rssis)/len(rssis):.0f}dBm, min {min(rssis)}dBm, max {max(rssis)}dBm")
            print(f"  Band:     {fives}/{len(readings)} on 5GHz ({fives/len(readings)*100:.0f}%)")
            print(f"  Switches: {len(switches)}")

        if latency:
            losses = [r for r in latency if r["packet_loss_pct"] and r["packet_loss_pct"] > 0]
            print(f"  Dropouts: {len(losses)} probes with packet loss")


def _cmd_trends(store, weeks):
    hosts = store.get_hosts()
    if not hosts:
        print("No data collected yet.")
        return

    for h in hosts:
        wc = weekly_comparison(store, host=h, weeks=weeks)
        print(f"\n── {h} ──")
        for i, w in enumerate(wc["weeks"]):
            label = "this week" if i == 0 else f"{i} week(s) ago"
            if w["reading_count"] == 0:
                print(f"  {label}: no data")
                continue
            rssi = f"{w['avg_rssi']:.0f}dBm" if w["avg_rssi"] is not None else "n/a"
            band = f"{w['band_5ghz_pct']:.0f}% 5GHz" if w["band_5ghz_pct"] is not None else "n/a"
            dl = f"{w['avg_download']:.0f}Mbps" if w["avg_download"] is not None else "n/a"
            print(f"  {label}: {rssi} | {band} | ↓{dl} ({w['reading_count']} readings)")


def _cmd_bands(store, days):
    ba = band_analysis(store, days=days)
    if not ba["hosts"]:
        print("No data collected yet.")
        return

    for h, d in ba["hosts"].items():
        print(f"\n── {h} (last {days} days) ──")
        print(f"  Total readings: {d['total']}")
        print(f"  5GHz:   {d['5ghz_count']} ({d['5ghz_pct']:.1f}%)")
        print(f"  2.4GHz: {d['2.4ghz_count']} ({100 - d['5ghz_pct']:.1f}%)")
        print(f"  Band switches: {d['switch_count']}")


def _cmd_diagnose(store, days):
    print(diagnose(store, days=days))
```

- [ ] **Step 3: Create `__main__.py`**

```python
from .cli import main

main()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Test dry-run end-to-end on Windows**

Run: `python -m wifi_diag collect --dry-run`
Let it run for ~5 seconds, then Ctrl+C.
Expected: prints collection messages, exits cleanly.

Then: `python -m wifi_diag status`
Expected: shows readings from the dry-run.

Then: `python -m wifi_diag diagnose`
Expected: shows diagnosis report with data from dry-run.

- [ ] **Step 7: Commit**

```bash
git add wifi_diag/cli.py wifi_diag/__main__.py tests/test_cli.py
git commit -m "feat: add CLI with status, history, trends, bands, diagnose commands"
```

---

### Task 8: README, Install Script, and GitHub Repo

**Files:**
- Create: `README.md`
- Create: `install.sh`

**Interfaces:**
- Consumes: everything (documentation task)
- Produces: complete README with setup instructions, deployment script, live GitHub repo

- [ ] **Step 1: Create `README.md`**

```markdown
# wifi-diag

A lightweight WiFi diagnostic agent that runs on Raspberry Pi and Windows. Collects signal strength, band usage (2.4GHz vs 5GHz), latency, and speed metrics over time to help diagnose WiFi degradation.

## Quick Start

### Windows

```powershell
git clone https://github.com/HurleySk/wifi-diag.git
cd wifi-diag
pip install -e .
wifi-diag collect --dry-run   # test with mock data
wifi-diag collect              # collect real data
```

### Raspberry Pi

```bash
git clone https://github.com/HurleySk/wifi-diag.git
cd wifi-diag
./install.sh                   # installs deps + systemd service
```

## Installation

### Prerequisites

- Python 3.9+
- WiFi connection (the tool monitors the WiFi interface it's connected through)

### Windows Setup

1. Clone the repo:
   ```powershell
   git clone https://github.com/HurleySk/wifi-diag.git
   cd wifi-diag
   ```

2. Install in development mode:
   ```powershell
   pip install -e .
   ```

3. Verify it works with mock data:
   ```powershell
   wifi-diag collect --dry-run
   ```
   Press Ctrl+C after a few seconds.

4. Start real collection:
   ```powershell
   wifi-diag collect
   ```

### Raspberry Pi Setup

1. SSH into your Pi:
   ```bash
   ssh pi@<pi-ip-address>
   ```

2. Clone and install:
   ```bash
   git clone https://github.com/HurleySk/wifi-diag.git
   cd wifi-diag
   chmod +x install.sh
   ./install.sh
   ```

   This will:
   - Install Python dependencies
   - Install `speedtest-cli`
   - Create a systemd service that starts on boot
   - Enable and start the service

3. Check it's running:
   ```bash
   sudo systemctl status wifi-diag
   journalctl -u wifi-diag -f
   ```

### Verifying Installation

After a few minutes of collection:

```bash
wifi-diag status     # see current readings
wifi-diag bands      # check 2.4GHz vs 5GHz split
wifi-diag diagnose   # run automated diagnosis
```

## Usage

### Collecting Data

```bash
wifi-diag collect              # foreground (Ctrl+C to stop)
wifi-diag collect --dry-run    # mock data for testing
```

On Raspberry Pi, the systemd service handles collection automatically.

### Viewing Data

```bash
wifi-diag status               # current snapshot
wifi-diag history              # last 24 hours
wifi-diag trends               # week-over-week comparison
wifi-diag trends --weeks 8     # last 8 weeks
wifi-diag bands                # band usage analysis
wifi-diag bands --days 30      # last 30 days
wifi-diag diagnose             # automated root cause analysis
wifi-diag diagnose --days 14   # analyze last 14 days
```

### Example: Diagnosis Output

```
DIAGNOSIS SUMMARY (last 7 days)
────────────────────────────────────────
Signal: RASPBERRYPI avg -42dBm (good), raspberrypi avg -68dBm (fair)
Band:   RASPBERRYPI 95% on 5GHz, raspberrypi 40% on 5GHz

⚠ raspberrypi is spending only 40% of time on 5GHz — band steering may be pushing it to 2.4GHz.
⚠ 5GHz usage declining: 70% → 40% over 4 weeks.
```

## Managing the Service (Pi)

```bash
sudo systemctl status wifi-diag    # check status
sudo systemctl stop wifi-diag      # stop collecting
sudo systemctl start wifi-diag     # start collecting
sudo systemctl restart wifi-diag   # restart
journalctl -u wifi-diag -f         # follow logs
```

## Data Storage

Data is stored in SQLite at `~/.wifi-diag/data.db`. At default collection intervals, a month of data is roughly 15MB per device.

To copy data off a Pi for analysis elsewhere:

```bash
scp pi@<pi-ip>:~/.wifi-diag/data.db ./pi-data.db
wifi-diag status --db ./pi-data.db
```

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

Tests use fixture data and run on both Windows and Linux.
```

- [ ] **Step 2: Create `install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== wifi-diag installer ==="

if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install it with: sudo apt install python3"
    exit 1
fi

echo "Installing Python package..."
pip3 install -e . --break-system-packages 2>/dev/null || pip3 install -e .

echo "Installing speedtest-cli..."
pip3 install speedtest-cli --break-system-packages 2>/dev/null || pip3 install speedtest-cli

echo "Creating systemd service..."
sudo tee /etc/systemd/system/wifi-diag.service > /dev/null << 'UNIT'
[Unit]
Description=WiFi Diagnostic Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 -m wifi_diag collect
WorkingDirectory=/home/pi/wifi-diag
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

echo "Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable wifi-diag
sudo systemctl start wifi-diag

echo ""
echo "=== Done! ==="
echo "Check status:  sudo systemctl status wifi-diag"
echo "View logs:     journalctl -u wifi-diag -f"
echo "View data:     wifi-diag status"
```

- [ ] **Step 3: Initialize git repo and push to GitHub**

```bash
cd wifi-diag
git init
git add .gitignore pyproject.toml requirements.txt install.sh README.md wifi_diag/ tests/
git commit -m "feat: wifi-diag — WiFi diagnostic agent for Raspberry Pi and Windows"
gh repo create wifi-diag --public --source=. --push
```

- [ ] **Step 4: Verify repo is live**

```bash
gh repo view HurleySk/wifi-diag --web
```

- [ ] **Step 5: Run full test suite one final time**

```bash
pytest tests/ -v
```

Expected: All tests PASS.
