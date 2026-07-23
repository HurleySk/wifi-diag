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
