import errno
import http.client
import urllib.request

from .base import BaseCollector
from .. import config
from ..netiface import interface_ip
from ..parsers.eureka_parser import parse_eureka_info


_UNRESOLVED = object()


def _is_unbindable(err):
    """True when the local bind failed rather than the device being unreachable.

    urllib wraps the socket error in a URLError, which subclasses OSError but
    assigns args directly and so carries no errno of its own; the code stays
    on the wrapped reason.
    """
    reason = getattr(err, "reason", err)
    return getattr(reason, "errno", None) == errno.EADDRNOTAVAIL


class _SourceBoundHTTPHandler(urllib.request.HTTPHandler):
    """Opens connections from a fixed local address."""

    def __init__(self, source):
        super().__init__()
        self._source = source

    def http_open(self, req):
        return self.do_open(
            http.client.HTTPConnection, req, source_address=(self._source, 0)
        )


class CastCollector(BaseCollector):
    """Fetches one Cast device's eureka_info. One device per call."""

    def __init__(self, port=None, timeout=None, interface=None):
        self.port = port or config.CAST_HTTP_PORT
        self.timeout = timeout or config.CAST_HTTP_TIMEOUT_SECS
        self.interface = interface
        self._source = _UNRESOLVED

    # Payloads are under 2 KB; the socket timeout is per read, not per transfer.
    MAX_RESPONSE_BYTES = 65536

    def _source_address(self):
        # Sentinel, not None: an interface with no address must stay resolved.
        if self._source is _UNRESOLVED:
            self._source = interface_ip(self.interface) if self.interface else None
        return self._source

    def _fetch(self, ip):
        url = f"http://{ip}:{self.port}/setup/eureka_info?options=detail"
        # LAN addresses: the default opener would honour any http_proxy.
        handlers = [urllib.request.ProxyHandler({})]
        source = self._source_address()
        if source:
            handlers.append(_SourceBoundHTTPHandler(source))
        opener = urllib.request.build_opener(*handlers)
        with opener.open(url, timeout=self.timeout) as resp:
            return resp.read(self.MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")

    def collect(self, ip=None) -> dict:
        if ip is None:
            raise ValueError("CastCollector.collect requires an ip")
        try:
            return parse_eureka_info(self._fetch(ip))
        except OSError as e:
            if not _is_unbindable(e):
                raise
        # A new lease made the cached source unbindable; this device is not down.
        self._source = _UNRESOLVED
        return parse_eureka_info(self._fetch(ip))
