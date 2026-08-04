"""Interface-scoped networking helpers.

A monitoring host with more than one route to the internet - a Pi wired to
eth0 while also associated on wlan0, say - sends every probe out whichever
interface the routing table prefers. That is normally the wired one, so
latency and speed readings end up describing the cable rather than the WiFi
link this tool exists to measure, and nothing in the numbers reveals it.

These helpers let a collector name the interface it means, and check
afterwards that the traffic actually went there.
"""

import re
import subprocess
import sys
from pathlib import Path

_SYS_NET = Path("/sys/class/net")


def interface_ip(iface):
    """Return the IPv4 address assigned to iface, or None if undeterminable."""
    if not iface or sys.platform == "win32":
        return None
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "dev", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", result.stdout)
    return m.group(1) if m else None


def _is_physical(entry):
    """True when entry is a real NIC: only a driver-backed device has this symlink."""
    # wg0 reports the plaintext bytes wlan0 already counted as ciphertext.
    return (entry / "device").exists()


def rx_byte_counters():
    """Snapshot {interface: rx_bytes} for physical interfaces, or {} off Linux."""
    counters = {}
    try:
        entries = list(_SYS_NET.iterdir())
    except OSError:
        return {}
    for entry in entries:
        try:
            if not _is_physical(entry):
                continue
            raw = (entry / "statistics" / "rx_bytes").read_text().strip()
            counters[entry.name] = int(raw)
        except (OSError, ValueError):
            continue
    return counters


def busiest_interface(before, after):
    """Name the interface that received the most bytes between two snapshots.

    Returns None when a counter went backwards, when an interface appeared or
    vanished mid-measurement, or when nothing moved. Callers read None as
    "cannot tell", which beats naming a winner from an incomplete comparison.
    """
    if before.keys() != after.keys():
        return None
    deltas = {}
    for name in before:
        delta = after[name] - before[name]
        if delta < 0:
            # A wrap or device reset makes every delta in the pair suspect.
            return None
        if delta > 0:
            deltas[name] = delta
    if not deltas:
        return None
    return max(deltas, key=deltas.get)
