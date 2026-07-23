from .base import BaseCollector


class SpeedMockCollector(BaseCollector):
    def collect(self) -> dict:
        return {
            "download_mbps": 95.5,
            "upload_mbps": 45.2,
            "ping_ms": 12.0,
        }
