import subprocess
import sys
from .base import BaseCollector
from ..parsers.ping_parser import parse_ping


class LatencyCollector(BaseCollector):
    def __init__(self, target, count=5):
        self.target = target
        self.count = count

    def collect(self) -> dict:
        # Per-probe deadlines matter now that this runs against Cast devices,
        # which are often offline. Without them a dead host costs ~10s per
        # probe, and enough of those overrun the collection interval and
        # starve the other collectors in the same single-threaded loop.
        if sys.platform == "win32":
            cmd = ["ping", "-n", str(self.count), "-w", "1000", self.target]
        else:
            cmd = ["ping", "-c", str(self.count), "-W", "1", self.target]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.count * 2 + 5,
            )
            output = result.stdout
        except subprocess.TimeoutExpired:
            output = ""
        parsed = parse_ping(output)
        parsed["target"] = self.target
        return parsed
