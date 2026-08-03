import urllib.request

from .base import BaseCollector
from .. import config
from ..parsers.eureka_parser import parse_eureka_info


class CastCollector(BaseCollector):
    """Fetches one Cast device's eureka_info. One device per call."""

    def __init__(self, port=None, timeout=None):
        self.port = port or config.CAST_HTTP_PORT
        self.timeout = timeout or config.CAST_HTTP_TIMEOUT_SECS

    # An eureka_info payload is well under 2 KB. Cap the read so a hostile or
    # malfunctioning responder on port 8008 cannot stream indefinitely: the
    # socket timeout applies per read, not to the total transfer.
    MAX_RESPONSE_BYTES = 65536

    def _fetch(self, ip):
        url = f"http://{ip}:{self.port}/setup/eureka_info?options=detail"
        # These are LAN addresses; the default opener would route them through
        # any http_proxy set in the environment.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=self.timeout) as resp:
            return resp.read(self.MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")

    def collect(self, ip=None) -> dict:
        if ip is None:
            raise ValueError("CastCollector.collect requires an ip")
        return parse_eureka_info(self._fetch(ip))
