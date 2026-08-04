import subprocess
import sys
from .base import BaseCollector
from ..parsers.ping_parser import parse_ping


class PingError(RuntimeError):
    """A ping run produced no usable measurement of any kind."""


def _has_measurement(parsed):
    """100% loss is a measurement; neither loss nor RTT means none was taken."""
    return parsed["packet_loss_pct"] is not None or parsed["rtt_avg_ms"] is not None


class LatencyCollector(BaseCollector):
    def __init__(self, target, count=5, interface=None):
        self.target = target
        self.count = count
        self.interface = interface

    def _bound_interface(self):
        """The interface ping will actually bind, or None when it cannot."""
        if not self.interface or sys.platform == "win32":
            return None
        return self.interface

    def _command(self):
        if sys.platform == "win32":
            # Windows ping has no device-binding flag, so leave it honestly unbound.
            return ["ping", "-n", str(self.count), "-w", "1000", self.target]

        cmd = ["ping", "-c", str(self.count), "-W", "1"]
        if self._bound_interface():
            # A device name sets SO_BINDTODEVICE; an address still routes by metric.
            cmd += ["-I", self.interface]
        cmd.append(self.target)
        return cmd

    def _stamp(self, parsed):
        parsed["target"] = self.target
        # The interface ping bound, not the one asked for: NULL means unknown.
        parsed["interface"] = self._bound_interface()
        return parsed

    def collect(self) -> dict:
        # Cast devices are often offline; without a deadline each costs ~10s.
        deadline = self.count * 2 + 5
        try:
            result = subprocess.run(
                self._command(),
                capture_output=True,
                text=True,
                timeout=deadline,
            )
        except subprocess.TimeoutExpired as e:
            # A run that printed its statistics and then hung still measured something.
            parsed = parse_ping(e.output or "")
            if not _has_measurement(parsed):
                raise PingError(
                    f"ping to {self.target} did not finish within {deadline}s"
                ) from e
            return self._stamp(parsed)
        except OSError as e:
            raise PingError(f"could not run ping for {self.target}: {e}") from e

        parsed = parse_ping(result.stdout)
        if not _has_measurement(parsed):
            raise PingError(
                f"ping to {self.target} produced no parseable result; "
                f"its output was {result.stdout.strip()!r}"
            )
        return self._stamp(parsed)
