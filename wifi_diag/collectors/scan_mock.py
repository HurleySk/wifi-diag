from pathlib import Path

from .base import BaseCollector
from ..parsers.scan_parser import parse_nmcli_scan

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class ScanMockCollector(BaseCollector):
    def collect(self) -> list:
        return parse_nmcli_scan((FIXTURES_DIR / "nmcli_scan.txt").read_text())
