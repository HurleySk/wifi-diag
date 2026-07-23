import subprocess
from .base import BaseCollector
from ..parsers.speedtest_parser import parse_speedtest


class SpeedCollector(BaseCollector):
    def collect(self) -> dict:
        result = subprocess.run(
            ["speedtest-cli", "--simple"],
            capture_output=True,
            text=True,
        )
        return parse_speedtest(result.stdout)
