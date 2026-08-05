from pathlib import Path

from .base import BaseCollector
from ..parsers.eureka_parser import parse_eureka_info

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

_FIXTURES = [
    "eureka_pod.json",
    "eureka_speaker.json",
    "eureka_empty_bssid.json",
    "eureka_no_mac.json",
]


class CastMockCollector(BaseCollector):
    def __init__(self):
        self._index = 0

    def ips(self):
        """IPs the mock pretends to have discovered."""
        return ["192.168.1.157", "192.168.1.160", "192.168.1.152", "192.168.1.161"]

    def collect(self, ip=None) -> dict:
        name = _FIXTURES[self._index % len(_FIXTURES)]
        self._index += 1
        return parse_eureka_info((FIXTURES_DIR / name).read_text(encoding="utf-8"))
