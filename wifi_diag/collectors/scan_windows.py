import subprocess

from .base import BaseCollector
from ..parsers.scan_parser import parse_netsh_scan


class ScanWindowsCollector(BaseCollector):
    def collect(self) -> list:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        return parse_netsh_scan(result.stdout)
