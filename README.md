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
