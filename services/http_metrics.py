import re
import threading
import time
from collections import defaultdict


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
INT_RE = re.compile(r"/\d+")


class HTTPMetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._request_count = defaultdict(int)
        self._duration_sum = defaultdict(float)
        self._duration_count = defaultdict(int)
        self._duration_buckets = defaultdict(int)
        self._in_flight = 0
        self._buckets = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10]

    def _normalize_path(self, path: str) -> str:
        path = UUID_RE.sub(":id", path)
        path = INT_RE.sub("/:id", path)
        return path

    def begin_request(self) -> None:
        with self._lock:
            self._in_flight += 1

    def end_request(self, method: str, path: str, status_code: int, duration_sec: float) -> None:
        normalized_path = self._normalize_path(path)
        key = (method, normalized_path, str(status_code))

        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._request_count[key] += 1
            self._duration_sum[(method, normalized_path)] += duration_sec
            self._duration_count[(method, normalized_path)] += 1

            for le in self._buckets:
                if duration_sec <= le:
                    self._duration_buckets[(method, normalized_path, str(le))] += 1
            self._duration_buckets[(method, normalized_path, "+Inf")] += 1

    def render_prometheus(self) -> str:
        lines = []
        now = time.time()

        lines.append("# HELP app_uptime_seconds Seconds since API process start")
        lines.append("# TYPE app_uptime_seconds gauge")
        lines.append(f"app_uptime_seconds {now - self._started_at:.3f}")

        lines.append("# HELP http_requests_in_flight Currently processing HTTP requests")
        lines.append("# TYPE http_requests_in_flight gauge")
        lines.append(f"http_requests_in_flight {self._in_flight}")

        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        for (method, path, status), count in sorted(self._request_count.items()):
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )

        lines.append("# HELP http_request_duration_seconds HTTP request duration")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for (method, path, le), count in sorted(self._duration_buckets.items()):
            lines.append(
                f'http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{le}"}} {count}'
            )
        for (method, path), total in sorted(self._duration_sum.items()):
            lines.append(f'http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {total:.6f}')
        for (method, path), count in sorted(self._duration_count.items()):
            lines.append(f'http_request_duration_seconds_count{{method="{method}",path="{path}"}} {count}')

        return "\n".join(lines) + "\n"


http_metrics = HTTPMetricsCollector()
