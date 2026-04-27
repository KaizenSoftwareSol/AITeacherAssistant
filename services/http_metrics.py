import re
import time

from prometheus_client import Counter, Gauge, Histogram, generate_latest


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
INT_RE = re.compile(r"/\d+")


class HTTPMetricsCollector:
    def __init__(self):
        self._started_at = time.time()
        self._request_count = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
        )
        self._duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration",
            ["method", "path"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
        )
        self._in_flight = Gauge(
            "http_requests_in_flight",
            "Currently processing HTTP requests",
        )
        self._uptime = Gauge(
            "app_uptime_seconds",
            "Seconds since API process start",
        )

    def _normalize_path(self, path: str) -> str:
        path = UUID_RE.sub(":id", path)
        path = INT_RE.sub("/:id", path)
        return path

    def begin_request(self) -> None:
        self._in_flight.inc()

    def end_request(self, method: str, path: str, status_code: int, duration_sec: float) -> None:
        normalized_path = self._normalize_path(path)
        self._in_flight.dec()
        self._request_count.labels(method=method, path=normalized_path, status=str(status_code)).inc()
        self._duration.labels(method=method, path=normalized_path).observe(duration_sec)

    def render_prometheus(self) -> str:
        self._uptime.set(time.time() - self._started_at)
        return generate_latest().decode("utf-8")


http_metrics = HTTPMetricsCollector()
