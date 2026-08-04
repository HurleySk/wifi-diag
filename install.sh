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

# Ookla's CLI forces egress with SO_BINDTODEVICE; speedtest-cli cannot.
OOKLA_VERSION=1.2.0
# By path, not by name: pip's `speedtest` shim precedes this on interactive PATH.
OOKLA_BIN=/usr/local/bin/speedtest
if [ -x "$OOKLA_BIN" ] && "$OOKLA_BIN" --version 2>&1 | grep -q Ookla; then
    echo "Ookla speedtest CLI already installed."
else
    case "$(uname -m)" in
        x86_64)  OOKLA_ARCH=x86_64 ;;
        aarch64) OOKLA_ARCH=aarch64 ;;
        armv7l)  OOKLA_ARCH=armhf ;;
        armv6l)  OOKLA_ARCH=armel ;;
        *)       OOKLA_ARCH="" ;;
    esac
    if [ -z "$OOKLA_ARCH" ]; then
        echo "No Ookla build for $(uname -m); speed tests will use speedtest-cli."
    else
        echo "Installing Ookla speedtest CLI ($OOKLA_ARCH)..."
        OOKLA_TMP="$(mktemp -d)"
        OOKLA_URL="https://install.speedtest.net/app/cli/ookla-speedtest-${OOKLA_VERSION}-linux-${OOKLA_ARCH}.tgz"
        if curl -sSfL -o "$OOKLA_TMP/ookla.tgz" "$OOKLA_URL" \
           && tar xzf "$OOKLA_TMP/ookla.tgz" -C "$OOKLA_TMP" speedtest; then
            sudo install -m 755 "$OOKLA_TMP/speedtest" "$OOKLA_BIN"
            echo "Installed $OOKLA_BIN"
        else
            echo "Could not install the Ookla CLI; speed tests will use speedtest-cli."
            echo "  On a dual-homed host expect some readings to be discarded."
        fi
        rm -rf "$OOKLA_TMP"
    fi
fi

CURRENT_USER="$(whoami)"
INSTALL_DIR="$(pwd)"

# ~/.local/bin is off PATH for non-interactive shells, breaking ssh invocation.
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

# Speed tests can only bind a source address, which does not choose a route.
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
# systemd's minimal PATH omits ~/.local/bin, where pip puts speedtest-cli.
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin"
# Without this stdout is block-buffered off a tty and the journal stays empty.
Environment="PYTHONUNBUFFERED=1"
Environment="WIFI_DIAG_INTERFACE=$WIFI_IF"
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
# restart, not start: 'start' is a no-op on an already-running old process.
sudo systemctl restart wifi-diag

echo ""
echo "=== Done! ==="
echo "Check status:  sudo systemctl status wifi-diag"
echo "View logs:     journalctl -u wifi-diag -f"
echo "View data:     wifi-diag status"
