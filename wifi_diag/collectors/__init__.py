import sys


def create_wifi_collector(dry_run=False):
    if dry_run:
        from .wifi_mock import WifiMockCollector
        return WifiMockCollector()
    if sys.platform == "win32":
        from .wifi_windows import WifiWindowsCollector
        return WifiWindowsCollector()
    from .wifi_linux import WifiLinuxCollector
    return WifiLinuxCollector()


def create_latency_collector(target, count=5, dry_run=False):
    if dry_run:
        from .latency_mock import LatencyMockCollector
        return LatencyMockCollector(target)
    from .latency import LatencyCollector
    return LatencyCollector(target, count)


def create_speed_collector(dry_run=False):
    if dry_run:
        from .speed_mock import SpeedMockCollector
        return SpeedMockCollector()
    from .speed import SpeedCollector
    return SpeedCollector()
