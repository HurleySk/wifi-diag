import subprocess
import sys
from .base import BaseCollector
from ..parsers.ping_parser import parse_ping


class PingError(RuntimeError):
    """A ping run produced no usable measurement of any kind."""


class LatencyCollector(BaseCollector):
    def __init__(self, target, count=5, interface=None):
        self.target = target
        self.count = count
        self.interface = interface

    def _command(self):
        if sys.platform == "win32":
            # Windows ping has no device-binding flag, so leave it honestly unbound.
            return ["ping", "-n", str(self.count), "-w", "1000", self.target]

        cmd = ["ping", "-c", str(self.count), "-W", "1"]
        if self.interface:
            # A device name sets SO_BINDTODEVICE; an address still routes by metric.
            cmd += ["-I", self.interface]
        cmd.append(self.target)
        return cmd

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
            output = result.stdout
        except subprocess.TimeoutExpired as e:
            raise PingError(
                f"ping to {self.target} did not finish within {deadline}s"
            ) from e
        except OSError as e:
            raise PingError(f"could not run ping for {self.target}: {e}") from e

        parsed = parse_ping(output)
        # 100% loss is a measurement; neither loss nor RTT means none was taken.
        if parsed["packet_loss_pct"] is None and parsed["rtt_avg_ms"] is None:
            raise PingError(
                f"ping to {self.target} produced no parseable result; "
                f"its output was {output.strip()!r}"
            )
        parsed["target"] = self.target
        return parsed
