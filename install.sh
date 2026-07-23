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
