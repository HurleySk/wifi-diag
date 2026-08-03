import time

from . import config

CAST_SERVICE = "_googlecast._tcp.local."


def _import_zeroconf():
    """Isolated so tests can simulate zeroconf being unavailable."""
    try:
        import zeroconf
        return zeroconf
    except ImportError:
        return None


def _txt(properties, key):
    value = (properties or {}).get(key)
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return str(value)


def service_info_to_device(info):
    """Convert a zeroconf ServiceInfo into a device dict, or None.

    Returns no MAC: the Cast mDNS TXT record has no reliable MAC field.
    Identity is established from eureka_info instead.
    """
    if info is None:
        return None
    try:
        addresses = info.parsed_addresses()
    except Exception:
        return None

    ipv4 = next((a for a in addresses if ":" not in a), None)
    if not ipv4:
        return None

    return {
        "ip": ipv4,
        "name": _txt(info.properties, b"fn"),
        "model": _txt(info.properties, b"md"),
    }


class _CastListener:
    def __init__(self, zc):
        self._zc = zc
        self.devices = {}

    def add_service(self, zc, type_, name):
        try:
            info = zc.get_service_info(type_, name, timeout=2000)
        except Exception:
            return
        device = service_info_to_device(info)
        if device:
            self.devices[device["ip"]] = device

    def update_service(self, zc, type_, name):
        self.add_service(zc, type_, name)

    def remove_service(self, zc, type_, name):
        pass


def discover_cast_devices(timeout=None):
    """Browse mDNS for Cast devices. Returns [] rather than raising."""
    timeout = timeout if timeout is not None else config.DISCOVERY_TIMEOUT_SECS
    zeroconf = _import_zeroconf()
    if zeroconf is None:
        return []

    zc = None
    try:
        zc = zeroconf.Zeroconf()
        listener = _CastListener(zc)
        browser = zeroconf.ServiceBrowser(zc, CAST_SERVICE, listener)
        time.sleep(timeout)
        browser.cancel()
        return list(listener.devices.values())
    except Exception:
        return []
    finally:
        if zc is not None:
            try:
                zc.close()
            except Exception:
                pass
