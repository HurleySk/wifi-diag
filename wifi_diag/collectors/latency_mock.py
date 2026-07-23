from .base import BaseCollector


class LatencyMockCollector(BaseCollector):
    def __init__(self, target):
        self.target = target

    def collect(self) -> dict:
        if "192.168" in self.target:
            return {
                "target": self.target,
                "rtt_min_ms": 1.0,
                "rtt_avg_ms": 2.5,
                "rtt_max_ms": 5.0,
                "packet_loss_pct": 0.0,
            }
        return {
            "target": self.target,
            "rtt_min_ms": 10.0,
            "rtt_avg_ms": 15.0,
            "rtt_max_ms": 25.0,
            "packet_loss_pct": 0.0,
        }
