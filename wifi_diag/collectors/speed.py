import subprocess

from .base import BaseCollector
from ..netiface import (
    busiest_interface,
    interface_ip,
    interface_share,
    rx_byte_counters,
)
from ..parsers.ookla_parser import parse_ookla
from ..parsers.speedtest_parser import parse_speedtest

# A run takes 30-60s; the ceiling stops a wedged one stalling the whole loop.
SPEEDTEST_TIMEOUT_SECS = 180

# A clean run measures 98%+ on the named interface; a split is worth nothing.
MIN_INTERFACE_SHARE = 0.9

OOKLA_BINARY = "speedtest"
LEGACY_BINARY = "speedtest-cli"


class SpeedTestError(RuntimeError):
    """The speed test did not produce a usable measurement."""


class WrongInterfaceError(RuntimeError):
    """A speed test completed, but its traffic did not stay on one interface."""


def ookla_available():
    """True when Ookla's official CLI is on PATH, as opposed to the pip one."""
    try:
        result = subprocess.run(
            [OOKLA_BINARY, "--version"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "Ookla" in (result.stdout or "") + (result.stderr or "")


class SpeedCollector(BaseCollector):
    def __init__(self, interface=None):
        self.interface = interface
        self._ookla = None

    def _plan(self):
        """The command to run and the parser for its output.

        Ookla's CLI binds with SO_BINDTODEVICE, which forces egress the way
        `ping -I` does. speedtest-cli can only bind a source address, and it
        binds only some of its parallel connections, so runs there straddle
        both links on a dual-homed host and measure neither.
        """
        if self._ookla is None:
            self._ookla = ookla_available()
        if self._ookla:
            cmd = [OOKLA_BINARY, "--format=json", "--accept-license", "--accept-gdpr"]
            if self.interface:
                cmd += [f"--interface={self.interface}"]
            return cmd, parse_ookla

        cmd = [LEGACY_BINARY, "--simple"]
        source = interface_ip(self.interface) if self.interface else None
        if source:
            cmd += ["--source", source]
        return cmd, parse_speedtest

    def collect(self) -> dict:
        cmd, parse = self._plan()

        # Verify after the fact regardless: binding is a request, not a proof.
        before = rx_byte_counters() if self.interface else {}
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=SPEEDTEST_TIMEOUT_SECS
            )
        except subprocess.TimeoutExpired as e:
            raise SpeedTestError(
                f"{cmd[0]} did not finish within {SPEEDTEST_TIMEOUT_SECS}s"
            ) from e
        except OSError as e:
            raise SpeedTestError(f"could not run {cmd[0]}: {e}") from e
        after = rx_byte_counters() if self.interface else {}

        # First: a failure prints nothing, and everything below misreads that.
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()
            raise SpeedTestError(
                f"{cmd[0]} exited {result.returncode}: "
                f"{detail[-1] if detail else 'no error output'}"
            )

        reading = parse(result.stdout)
        if reading["download_mbps"] is None and reading["upload_mbps"] is None:
            raise SpeedTestError(
                f"{cmd[0]} exited cleanly but reported neither download nor "
                f"upload speed; its output was {result.stdout.strip()[:200]!r}"
            )

        if self.interface and before and after:
            share = interface_share(before, after, self.interface)
            if share is not None and share < MIN_INTERFACE_SHARE:
                busiest = busiest_interface(before, after)
                raise WrongInterfaceError(
                    f"only {share:.0%} of the traffic left via {self.interface} "
                    f"(most went via {busiest}). Discarding the reading; "
                    "see 'Dual-homed hosts' in the README."
                )
        return reading
