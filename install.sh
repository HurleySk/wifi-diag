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

CURRENT_USER="$(whoami)"
INSTALL_DIR="$(pwd)"

# pip user-installs the console script to ~/.local/bin, which is NOT on PATH
# for non-interactive shells. That breaks remote invocation over SSH
# (`ssh pi@host wifi-diag devices`), since such shells source neither
# .profile nor the interactive part of .bashrc. Symlink into /usr/local/bin
# so the command resolves regardless of how the shell was started.
WIFI_DIAG_BIN="$(command -v wifi-diag || true)"
if [ -z "$WIFI_DIAG_BIN" ]; then
    for candidate in "$HOME/.local/bin/wifi-diag" /usr/local/bin/wifi-diag /usr/bin/wifi-diag; do
        if [ -x "$candidate" ]; then
            WIFI_DIAG_BIN="$candidate"
            break
        fi
    done
fi

if [ -n "$WIFI_DIAG_BIN" ] && [ "$WIFI_DIAG_BIN" != "/usr/local/bin/wifi-diag" ]; then
    echo "Linking $WIFI_DIAG_BIN -> /usr/local/bin/wifi-diag..."
    sudo ln -sf "$WIFI_DIAG_BIN" /usr/local/bin/wifi-diag
elif [ -z "$WIFI_DIAG_BIN" ]; then
    echo "Warning: wifi-diag console script not found; use 'python3 -m wifi_diag' instead."
fi

# A host with a second route to the internet sends every probe out whichever
# interface has the lower route metric, normally the wired one. Latency probes
# are pinned with `ping -I <device>`, which forces egress on its own, but the
# speed test can only bind a source address, and that does not choose a route.
# Without the policy rule below, the speed collector detects the mismatch and
# discards the reading rather than storing a number that describes the wire.
WIFI_IF="${WIFI_DIAG_INTERFACE:-wlan0}"
DISPATCH_DIR=/etc/NetworkManager/dispatcher.d

if [ -d "$DISPATCH_DIR" ] && [ -f "$INSTALL_DIR/dispatcher/90-wifi-diag-srcroute" ]; then
    echo "Installing source-routing dispatcher for $WIFI_IF..."
    sed "s/__WIFI_IF__/$WIFI_IF/" "$INSTALL_DIR/dispatcher/90-wifi-diag-srcroute" \
        | sudo tee "$DISPATCH_DIR/90-wifi-diag-srcroute" > /dev/null
    sudo chmod 755 "$DISPATCH_DIR/90-wifi-diag-srcroute"
    sudo chown root:root "$DISPATCH_DIR/90-wifi-diag-srcroute"
    # Apply now; the dispatcher itself only fires on the next interface event.
    sudo "$DISPATCH_DIR/90-wifi-diag-srcroute" "$WIFI_IF" up || true
else
    echo "NetworkManager dispatcher not found; skipping source-routing setup."
    echo "  If this host has both wired and WiFi routes, speed readings will be"
    echo "  discarded rather than attributed to the wrong interface."
fi

echo "Creating systemd service for user=$CURRENT_USER, dir=$INSTALL_DIR..."
sudo tee /etc/systemd/system/wifi-diag.service > /dev/null << UNIT
[Unit]
Description=WiFi Diagnostic Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
# systemd gives units a minimal PATH that excludes ~/.local/bin, where pip
# user-installs console scripts. Without this, speedtest-cli is not found and
# speed collection silently fails for the life of the service.
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin"
ExecStart=/usr/bin/python3 -m wifi_diag collect
WorkingDirectory=$INSTALL_DIR
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

echo "Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable wifi-diag
# restart, not start: on a re-install the service is usually already running,
# and 'start' is a no-op that would leave the old process alive with the old
# unit's environment and the old code.
sudo systemctl restart wifi-diag

echo ""
echo "=== Done! ==="
echo "Check status:  sudo systemctl status wifi-diag"
echo "View logs:     journalctl -u wifi-diag -f"
echo "View data:     wifi-diag status"
