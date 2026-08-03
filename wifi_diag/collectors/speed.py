import subprocess

from .base import BaseCollector
from ..netiface import busiest_interface, interface_ip, rx_byte_counters
from ..parsers.speedtest_parser import parse_speedtest


class WrongInterfaceError(RuntimeError):
    """A speed test completed, but its traffic left over the wrong interface."""


class SpeedCollector(BaseCollector):
    def __init__(self, interface=None):
        self.interface = interface

    def collect(self) -> dict:
        cmd = ["speedtest-cli", "--simple"]
        source = interface_ip(self.interface) if self.interface else None
        if source:
            cmd += ["--source", source]

        # --source only binds the source address; the kernel still picks the
        # route. Bracket the run with byte counters so a test that escaped
        # over another interface is discarded rather than stored as though it
        # measured this one. A wrong number here is worse than no number: it
        # reads as a healthy WiFi link that was never tested.
        before = rx_byte_counters() if self.interface else {}
        result = subprocess.run(cmd, capture_output=True, text=True)
        after = rx_byte_counters() if self.interface else {}

        reading = parse_speedtest(result.stdout)

        if self.interface and before and after:
            carried = busiest_interface(before, after)
            if carried is not None and carried != self.interface:
                raise WrongInterfaceError(
                    f"speed test traffic left via {carried}, not {self.interface}. "
                    "Discarding the reading; see 'Dual-homed hosts' in the README."
                )
        return reading
