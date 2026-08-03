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

echo "Creating systemd service for user=$CURRENT_USER, dir=$INSTALL_DIR..."
sudo tee /etc/systemd/system/wifi-diag.service > /dev/null << UNIT
[Unit]
Description=WiFi Diagnostic Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
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
sudo systemctl start wifi-diag

echo ""
echo "=== Done! ==="
echo "Check status:  sudo systemctl status wifi-diag"
echo "View logs:     journalctl -u wifi-diag -f"
echo "View data:     wifi-diag status"
