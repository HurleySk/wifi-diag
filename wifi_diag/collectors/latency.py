import subprocess
import sys
from .base import BaseCollector
from ..parsers.ping_parser import parse_ping


class LatencyCollector(BaseCollector):
    def __init__(self, target, count=5, interface=None):
        self.target = target
        self.count = count
        self.interface = interface

    def _command(self):
        if sys.platform == "win32":
            # Windows ping has no device-binding flag, only -S <source address>,
            # which does not force egress. Left unbound rather than bound in a
            # way that would look correct without being correct.
            return ["ping", "-n", str(self.count), "-w", "1000", self.target]

        cmd = ["ping", "-c", str(self.count), "-W", "1"]
        if self.interface:
            # -I with a device name sets SO_BINDTODEVICE, which forces the probe
            # out that interface. Passing an address here instead would set only
            # the source address and still route by metric, so on a dual-homed
            # host the probe would silently time the other link.
            cmd += ["-I", self.interface]
        cmd.append(self.target)
        return cmd

    def collect(self) -> dict:
        # Per-probe deadlines matter now that this runs against Cast devices,
        # which are often offline. Without them a dead host costs ~10s per
        # probe, and enough of those overrun the collection interval and
        # starve the other collectors in the same single-threaded loop.
        try:
            result = subprocess.run(
                self._command(),
                capture_output=True,
                text=True,
                timeout=self.count * 2 + 5,
            )
            output = result.stdout
        except subprocess.TimeoutExpired:
            output = ""
        parsed = parse_ping(output)
        parsed["target"] = self.target
        return parsed
