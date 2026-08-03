import subprocess

from .base import BaseCollector
from .. import config
from ..parsers.scan_parser import parse_iw_scan, parse_nmcli_scan


class ScanLinuxCollector(BaseCollector):
    def __init__(self, interface=None):
        self.interface = interface or config.WIFI_INTERFACE

    def collect(self) -> list:
        rows = self._try_nmcli()
        if rows:
            return rows
        return self._try_iw()

    def _try_nmcli(self):
        # A forced rescan matters: NetworkManager's cached list can contain
        # only the currently associated BSSID, which would leave the other
        # radio permanently unmapped and every device on it band-unknown.
        # Requesting a scan needs authorization, so fall back to the cache
        # when it is refused.
        rows = self._nmcli(rescan=True)
        if rows:
            return rows
        return self._nmcli(rescan=False)

    def _nmcli(self, rescan):
        cmd = ["nmcli", "-t", "-f", "BSSID,SSID,FREQ,CHAN", "dev", "wifi", "list"]
        if rescan:
            cmd += ["--rescan", "yes"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0:
            return []
        return parse_nmcli_scan(result.stdout)

    def _try_iw(self):
        try:
            result = subprocess.run(
                ["iw", "dev", self.interface, "scan"],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0:
            return []
        return parse_iw_scan(result.stdout)
