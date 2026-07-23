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
