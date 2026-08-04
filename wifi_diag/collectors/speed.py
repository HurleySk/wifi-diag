import subprocess
import sys

from .base import BaseCollector
from ..netiface import (
    busiest_interface,
    interface_delta,
    interface_ip,
    rx_byte_counters,
)
from ..parsers.ookla_parser import parse_ookla
from ..parsers.speedtest_parser import parse_speedtest

# A run takes 30-60s; the ceiling stops a wedged one stalling the whole loop.
SPEEDTEST_TIMEOUT_SECS = 180

# Counters include framing the test does not count, so a clean run exceeds 1.
MIN_MEASURED_BYTE_RATIO = 0.7

# install.sh puts Ookla here; the pip client answers to "speedtest" as well.
OOKLA_CANDIDATES = ("/usr/local/bin/speedtest", "speedtest")
LEGACY_BINARY = "speedtest-cli"

_UNPROBED = object()


class SpeedTestError(RuntimeError):
    """The speed test did not produce a usable measurement."""


class WrongInterfaceError(RuntimeError):
    """A speed test completed, but its traffic did not stay on one interface."""


def ookla_binary():
    """Path to Ookla's official CLI, or None when only the pip client is here.

    Both install a command called `speedtest`, and which one PATH resolves
    differs between the systemd unit and an interactive shell, so the absolute
    path install.sh writes is tried first and the version banner decides.
    """
    for candidate in OOKLA_CANDIDATES:
        try:
            result = subprocess.run(
                [candidate, "--version"], capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if "Ookla" in (result.stdout or "") + (result.stderr or ""):
            return candidate
    return None


class SpeedCollector(BaseCollector):
    def __init__(self, interface=None):
        self.interface = interface
        self._ookla = _UNPROBED

    def _pinnable(self):
        """True where the platform offers a device-binding flag at all.

        Verification is not gated on this: off Linux there are no byte
        counters either, so an unpinned run simply records no provenance.
        """
        return bool(self.interface) and sys.platform != "win32"

    def _plan(self):
        """The command to run and the parser for its output.

        Ookla's CLI binds with SO_BINDTODEVICE, which forces egress the way
        `ping -I` does. speedtest-cli can only bind a source address, and it
        binds only some of its parallel connections, so runs there straddle
        both links on a dual-homed host and measure neither.
        """
        if self._ookla is _UNPROBED:
            self._ookla = ookla_binary()

        if self._ookla:
            cmd = [self._ookla, "--format=json", "--accept-license", "--accept-gdpr"]
            # wlan0 is not a Windows device name, so sending it fails every run.
            if self._pinnable():
                cmd += [f"--interface={self.interface}"]
            return cmd, parse_ookla

        cmd = [LEGACY_BINARY, "--json"]
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
        downloaded = reading.pop("download_bytes", None)
        if reading["download_mbps"] is None and reading["upload_mbps"] is None:
            raise SpeedTestError(
                f"{cmd[0]} exited cleanly but reported neither download nor "
                f"upload speed; its output was {result.stdout.strip()[:200]!r}"
            )

        # NULL rather than the interface we asked for: unverified is not proof.
        reading["interface"] = None
        if self.interface and before and after:
            self._verify_interface(before, after, downloaded)
            reading["interface"] = self.interface
        return reading

    def _verify_interface(self, before, after, downloaded):
        """Raise unless the named interface carried what the test measured.

        Comparing against the test's own byte total rather than against the
        other interfaces keeps the check independent of background traffic,
        which is a fixed quantity while a speed test's is not. Sharing the
        denominator with the noise made the gate tighten as the link slowed,
        so a degrading link went unrecorded at exactly the wrong moment.
        """
        iface = self.interface
        carried = interface_delta(before, after, iface)
        if carried is None:
            raise WrongInterfaceError(
                f"{iface} is missing from the byte counters or its counter "
                "reset mid-run, so this reading cannot be attributed to any "
                "interface. Discarding it; see 'Dual-homed hosts' in the README."
            )

        if downloaded:
            ratio = carried / downloaded
            if ratio < MIN_MEASURED_BYTE_RATIO:
                raise WrongInterfaceError(
                    f"{iface} carried {carried:,} of the {downloaded:,} bytes "
                    f"the test downloaded ({ratio:.0%}); the rest went via "
                    f"{busiest_interface(before, after)}. Discarding the "
                    "reading; see 'Dual-homed hosts' in the README."
                )
            return

        # No byte total to compare against; the weaker check beats none at all.
        busiest = busiest_interface(before, after)
        if busiest is not None and busiest != iface:
            raise WrongInterfaceError(
                f"the test reported no byte total and most traffic moved over "
                f"{busiest}, not {iface}. Discarding the reading; see "
                "'Dual-homed hosts' in the README."
            )
