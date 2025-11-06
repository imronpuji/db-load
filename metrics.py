from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from prometheus_client import Counter, Gauge, Histogram


# Histograms are configured with sensible default buckets for latency in seconds
REQUEST_LATENCY = Histogram(
    "db_request_latency_seconds",
    "Latency for DB requests",
    buckets=(
        0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1,
        0.2, 0.5, 1.0, 2.0, 5.0
    ),
)
CONNECT_LATENCY = Histogram(
    "db_connect_latency_seconds",
    "Latency for establishing DB connections",
    buckets=(0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5),
)
REQUESTS_TOTAL = Counter(
    "db_requests_total",
    "Total DB requests",
    labelnames=("type", "status"),
)
CONNECTIONS_OPEN = Gauge("db_connections_open", "Open DB connections")
QPS = Gauge("db_qps", "Queries per second (rolling)")


@dataclass
class TimeWindow:
    window_seconds: int
    timestamps: List[float] = field(default_factory=list)

    def add(self, ts: float) -> None:
        self.timestamps.append(ts)
        self._trim()

    def rate(self) -> float:
        self._trim()
        if not self.timestamps:
            return 0.0
        now = time.time()
        cutoff = now - self.window_seconds
        count = len([t for t in self.timestamps if t >= cutoff])
        return count / self.window_seconds

    def _trim(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.pop(0)


class MetricsCollector:
    def __init__(self, qps_window_seconds: int = 10) -> None:
        self._lock = threading.Lock()
        self.success_count = 0
        self.error_count = 0
        self.qps_window = TimeWindow(qps_window_seconds)
        self.last_update_ts = time.time()

    def record_connect(self, seconds: float, ok: bool) -> None:
        with self._lock:
            CONNECT_LATENCY.observe(seconds)
            if ok:
                REQUESTS_TOTAL.labels(type="connect", status="success").inc()
            else:
                REQUESTS_TOTAL.labels(type="connect", status="error").inc()

    def record_query(self, seconds: float, ok: bool, kind: str) -> None:
        with self._lock:
            REQUEST_LATENCY.observe(seconds)
            self.qps_window.add(time.time())
            if ok:
                self.success_count += 1
                REQUESTS_TOTAL.labels(type=kind, status="success").inc()
            else:
                self.error_count += 1
                REQUESTS_TOTAL.labels(type=kind, status="error").inc()
            QPS.set(self.qps_window.rate())

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {
                "success": float(self.success_count),
                "error": float(self.error_count),
                "qps": float(self.qps_window.rate()),
            }


__all__ = ["MetricsCollector"]


