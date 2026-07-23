from pathlib import Path
from .base import BaseCollector
from ..parsers.iw_parser import parse_iw_link

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class WifiMockCollector(BaseCollector):
    def __init__(self):
        self._index = 0
        self._fixtures = [
            FIXTURES_DIR / "iw_link_5ghz.txt",
            FIXTURES_DIR / "iw_link_2ghz.txt",
        ]

    def collect(self) -> dict:
        fixture = self._fixtures[self._index % len(self._fixtures)]
        self._index += 1
        return parse_iw_link(fixture.read_text())
