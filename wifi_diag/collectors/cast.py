import urllib.request

from .base import BaseCollector
from .. import config
from ..parsers.eureka_parser import parse_eureka_info


class CastCollector(BaseCollector):
    """Fetches one Cast device's eureka_info. One device per call."""

    def __init__(self, port=None, timeout=None):
        self.port = port or config.CAST_HTTP_PORT
        self.timeout = timeout or config.CAST_HTTP_TIMEOUT_SECS

    def _fetch(self, ip):
        url = f"http://{ip}:{self.port}/setup/eureka_info?options=detail"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def collect(self, ip=None) -> dict:
        if ip is None:
            raise ValueError("CastCollector.collect requires an ip")
        return parse_eureka_info(self._fetch(ip))
