import subprocess
import sys
from .base import BaseCollector
from ..parsers.ping_parser import parse_ping


class LatencyCollector(BaseCollector):
    def __init__(self, target, count=5):
        self.target = target
        self.count = count

    def collect(self) -> dict:
        if sys.platform == "win32":
            cmd = ["ping", "-n", str(self.count), self.target]
        else:
            cmd = ["ping", "-c", str(self.count), self.target]
        result = subprocess.run(cmd, capture_output=True, text=True)
        parsed = parse_ping(result.stdout)
        parsed["target"] = self.target
        return parsed
