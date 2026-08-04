import subprocess

from .base import BaseCollector
from ..netiface import busiest_interface, interface_ip, rx_byte_counters
from ..parsers.speedtest_parser import parse_speedtest


# A run takes 30-60s; the ceiling stops a wedged one stalling the whole loop.
SPEEDTEST_TIMEOUT_SECS = 180


class SpeedTestError(RuntimeError):
    """speedtest-cli did not produce a usable measurement."""


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

        # --source binds an address but does not pick a route, so verify after.
        before = rx_byte_counters() if self.interface else {}
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=SPEEDTEST_TIMEOUT_SECS
            )
        except subprocess.TimeoutExpired as e:
            raise SpeedTestError(
                f"speedtest-cli did not finish within {SPEEDTEST_TIMEOUT_SECS}s"
            ) from e
        except OSError as e:
            raise SpeedTestError(f"could not run speedtest-cli: {e}") from e
        after = rx_byte_counters() if self.interface else {}

        # First: a failure prints nothing, and everything below misreads that.
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()
            raise SpeedTestError(
                f"speedtest-cli exited {result.returncode}: "
                f"{detail[-1] if detail else 'no error output'}"
            )

        reading = parse_speedtest(result.stdout)
        if reading["download_mbps"] is None and reading["upload_mbps"] is None:
            raise SpeedTestError(
                "speedtest-cli exited cleanly but reported neither download "
                f"nor upload speed; its output was {result.stdout.strip()!r}"
            )

        if self.interface and before and after:
            carried = busiest_interface(before, after)
            if carried is not None and carried != self.interface:
                raise WrongInterfaceError(
                    f"speed test traffic left via {carried}, not {self.interface}. "
                    "Discarding the reading; see 'Dual-homed hosts' in the README."
                )
        return reading
