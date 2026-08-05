# wifi-diag

A lightweight WiFi diagnostic agent that runs on Raspberry Pi and Windows. Collects signal strength, band usage (2.4GHz vs 5GHz), latency, and speed metrics over time to help diagnose WiFi degradation.

It also monitors **Google Home / Nest / Cast devices** on the same network - which band each one is associated with, whether it is reachable, and when it restarts - so you can tell whether a misbehaving speaker is a network problem or a device problem.

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
- The `zeroconf` package (installed automatically) for discovering Cast devices
- The monitoring host must be on the same network segment as the Cast devices

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
   - Install Ookla's speedtest CLI, falling back to `speedtest-cli`
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
wifi-diag devices              # Google Cast device status
wifi-diag device "Kitchen Pod" # one device's history and events
wifi-diag events --hours 24    # recent drops, band switches, reboots
```

### Example: Diagnosis Output

```
DIAGNOSIS SUMMARY (last 7 days)
────────────────────────────────────────
Signal: raspberrypi avg -52dBm (good)
Band:   raspberrypi 100% on 5GHz

Cast devices (4):
  Basement speaker: 100% reachable, 5GHz, 0 band switches, 0 reboots
  Kitchen Pod: 94% reachable, 5GHz, 7 band switches, 0 reboots
  Living Room speaker: 99% reachable, 2.4GHz, 1 band switches, 0 reboots
  Master Pod Display: 100% reachable, band unknown, 0 band switches, 0 reboots

⚠ Kitchen Pod was unreachable in 6% of polls - it is dropping off the network, not just responding slowly.
⚠ Kitchen Pod had 7 band switches - band steering is moving it between radios repeatedly.
ℹ Master Pod Display does not report a BSSID, so its band cannot be determined. Reachability data is still valid.
```

## Monitoring Google Home devices

Cast devices are discovered automatically over mDNS and polled on their local
`http://<ip>:8008/setup/eureka_info` endpoint. No account, token, or cloud
access is involved - everything is read from the local network.

```bash
wifi-diag devices                 # all Cast devices: band, uptime %, switches, drops
wifi-diag device "Kitchen Pod"    # history and event timeline for one device
wifi-diag events --hours 24       # drops, band switches, and reboots across all devices
```

Example:

```
DEVICE                   IP               BAND       UP%  SWITCHES  DROPS
──────────────────────────────────────────────────────────────────────────
Basement speaker         192.168.1.156    5GHz      100%         0      0
Kitchen Pod              192.168.1.161    5GHz       94%         7      4
Living Room speaker      192.168.1.160    2.4GHz     99%         1      0
Master Pod Display       192.168.1.152    ?         100%         0      0
```

### How band detection works

Cast devices report the BSSID they are associated with, but not which band it
is. The agent periodically scans for nearby access points, builds a
BSSID-to-frequency map, and joins the two. A device whose BSSID has not yet
been seen in a scan shows a band of `?` rather than a guess.

### Limitations

- **No per-device signal strength.** Current Cast firmware does not expose
  RSSI. This tool answers *which band, and is it reachable* - not *how strong
  is the signal*.
- **Some devices report no BSSID at all.** Older firmware returns an empty
  value, so band is shown as `?` for those. Reachability, latency, and reboot
  detection still work.
- **A device can stop reporting its MAC.** Cast firmware in the 1.68 series
  intermittently returns `00:00:00:00:00:00` - seen around a reboot - and every
  device doing so at once reports the same value. Identity therefore comes from
  the `ssdp_udn`, which is unique and stable, and a device whose UDN is already
  tied to an identity keeps it when its MAC blanks out. Devices are keyed on a
  real MAC where one has been reported, so existing history is unaffected.
- **Re-associations are not directly visible.** A device that drops and
  instantly rejoins without rebooting is only detected if it misses a poll or
  lands on a different BSSID.
- **The agent must be on the same network segment** as the devices, since
  mDNS discovery does not cross subnets. If discovery fails, set
  `CAST_STATIC_IPS` in `wifi_diag/config.py`.

## Dual-homed hosts

If the monitoring host has more than one route to the internet - a Pi plugged
into ethernet while also associated on WiFi is the common case - the kernel
sends every probe out whichever interface has the lower route metric. That is
almost always the wire. Left alone, latency and speed readings describe the
cable, not the WiFi link, and nothing in the numbers reveals it.

The agent pins its probes to the interface named by `WIFI_INTERFACE` in
`wifi_diag/config.py`, which defaults to `wlan0` and can be overridden with the
`WIFI_DIAG_INTERFACE` environment variable. `install.sh` reads the same
variable and writes it into the systemd unit.

- **Latency** uses `ping -I <device>`, which sets `SO_BINDTODEVICE` and forces
  egress. This works with no additional setup.
- **Speed** prefers [Ookla's official CLI](https://www.speedtest.net/apps/cli),
  whose `--interface` binds with `SO_BINDTODEVICE` and forces egress the same
  way `ping -I` does. `install.sh` fetches it automatically.

  Where it is unavailable the collector falls back to `speedtest-cli`, which
  can only bind a source address. That is weaker than it looks: `speedtest-cli`
  opens parallel connections and binds only some of them, so one run measured
  here put 102MB over eth0 and 85MB over wlan0 and reported 140 Mbit/s, a
  figure describing neither link.

  Either way the collector brackets each run with per-interface byte counters
  and **discards the reading** unless the named interface carried at least 70%
  of the bytes the speed test itself reports downloading. A missing reading is
  recoverable; a wrong one that reads as a healthy WiFi link is not. Discards
  are logged with the fraction that did go the right way.

  The comparison is deliberately against the test's own byte total rather than
  against traffic on the other interfaces. Background chatter is roughly a
  fixed number of bytes per run, so sharing a denominator with it made the
  check tighten as the link slowed and threw away every reading below about
  15 Mbit/s: the tool went blind during exactly the degradation it exists to
  record. This is also why the fallback runs `speedtest-cli --json` rather
  than `--simple`, which reports no byte total at all.
- **Cast reachability** binds its HTTP probe to the WiFi address, so a device
  that is unreachable over WiFi is not recorded as up because the wire
  answered for it.

Latency and speed rows record the interface they were **verified** to have been
measured on, which is not the same as the one the agent asked for. A Windows
ping has no device-binding flag, and a host with no `/sys/class/net` has no
byte counters to check against; both store `interface` NULL, as do rows written
before the column existed. NULL means unknown provenance, and `diagnose`
refuses to compare a window of one interface against another rather than
reporting the difference as a change in the network.

To make speed readings work on such a host, `install.sh` adds a NetworkManager
dispatcher script that keeps a policy rule routing traffic sourced from the
WiFi address out the WiFi interface. Nothing else sources traffic from that
address, so nothing else on the system is affected.

One caveat if you use policy routing yourself: on every WiFi event the script
rebuilds table 200 from scratch, which means flushing its routes and deleting
every rule that points at it, whoever added them. Move your own rules to a
different table before installing.

To verify, compare the two paths by hand:

```bash
ping -I wlan0 -c 5 8.8.8.8      # over WiFi
ping -c 5 8.8.8.8               # over whatever the routing table prefers
```

Different round-trip times mean the host is dual-homed and the pinning matters.
To remove the dispatcher later:

```bash
sudo rm /etc/NetworkManager/dispatcher.d/90-wifi-diag-srcroute
while sudo ip rule del pref 20200 table 200 2>/dev/null; do :; done
sudo ip route flush table 200
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

Data is stored in SQLite at `~/.wifi-diag/data.db`, across eight tables: WiFi
readings, band switches, latency, speed, plus `cast_devices`, `cast_readings`,
`cast_events`, and `ap_scans` for Google device monitoring. At default
collection intervals, expect roughly 15MB per month for the host's own metrics
plus about 5MB per month per monitored Cast device.

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
