"""WinFix AI — Performance Profiling and Telemetry-Free Metrics (Phase 24).

Provides lightweight, non-intrusive, monotonic performance measurement tools
for memory, CPU, and duration without external telemetry or cloud reporting.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import logging
import os
import time
from typing import Any, Dict, Generator, List, Optional

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

logger = logging.getLogger("winfix.PERFORMANCE")


@dataclass(frozen=True)
class PerformanceSnapshot:
    """System resource snapshot at a specific point in time."""

    timestamp: float
    memory_rss_mb: float
    cpu_percent: float


def take_resource_snapshot() -> PerformanceSnapshot:
    """Capture current process memory (RSS) and CPU usage safely."""
    ts = time.monotonic()
    rss_mb = 0.0
    cpu_pct = 0.0

    if _PSUTIL_AVAILABLE:
        try:
            proc = psutil.Process(os.getpid())
            mem_info = proc.memory_info()
            rss_mb = round(mem_info.rss / (1024 * 1024), 2)
            # Process-specific CPU utilization
            cpu_pct = round(proc.cpu_percent(interval=None), 2)
        except Exception:
            rss_mb = 0.0
            cpu_pct = 0.0

    return PerformanceSnapshot(
        timestamp=ts,
        memory_rss_mb=rss_mb,
        cpu_percent=cpu_pct,
    )


@dataclass
class PerformanceMetric:
    """Structured performance measurement for an operation."""

    operation: str
    duration_ms: float
    memory_before_mb: float
    memory_after_mb: float
    memory_delta_mb: float
    cpu_before: float
    cpu_after: float
    status: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metric to structured dictionary."""
        return {
            "operation": self.operation,
            "duration_ms": self.duration_ms,
            "memory_before_mb": self.memory_before_mb,
            "memory_after_mb": self.memory_after_mb,
            "memory_delta_mb": self.memory_delta_mb,
            "cpu_before": self.cpu_before,
            "cpu_after": self.cpu_after,
            "status": self.status,
            "timestamp": self.timestamp,
            "details": self.details or {},
        }


class PerformanceTimer:
    """Context manager measuring monotonic duration, memory, and CPU."""

    def __init__(self, operation: str, profiler: Optional["PerformanceProfiler"] = None) -> None:
        self.operation = operation
        self.profiler = profiler
        self.start_snapshot: Optional[PerformanceSnapshot] = None
        self.end_snapshot: Optional[PerformanceSnapshot] = None
        self.duration_ms: float = 0.0
        self.status: str = "PENDING"
        self.metric: Optional[PerformanceMetric] = None

    def __enter__(self) -> "PerformanceTimer":
        self.start_snapshot = take_resource_snapshot()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.end_snapshot = take_resource_snapshot()
        self.duration_ms = round((self.end_snapshot.timestamp - self.start_snapshot.timestamp) * 1000.0, 3)
        self.status = "SUCCESS" if exc_type is None else "ERROR"

        mem_before = self.start_snapshot.memory_rss_mb
        mem_after = self.end_snapshot.memory_rss_mb
        mem_delta = round(mem_after - mem_before, 2)

        self.metric = PerformanceMetric(
            operation=self.operation,
            duration_ms=self.duration_ms,
            memory_before_mb=mem_before,
            memory_after_mb=mem_after,
            memory_delta_mb=mem_delta,
            cpu_before=self.start_snapshot.cpu_percent,
            cpu_after=self.end_snapshot.cpu_percent,
            status=self.status,
            details={"exception": str(exc_val)} if exc_val else None,
        )

        if self.profiler is not None:
            self.profiler.record_metric(self.metric)

        return False  # Do not suppress exceptions


class PerformanceProfiler:
    """In-memory, zero-telemetry performance profiler."""

    def __init__(self, max_records: int = 500) -> None:
        self.max_records = max_records
        self._metrics: List[PerformanceMetric] = []

    @contextmanager
    def measure(self, operation: str) -> Generator[PerformanceTimer, None, None]:
        """Context manager for profiling an operation."""
        timer = PerformanceTimer(operation=operation, profiler=self)
        with timer:
            yield timer

    def record_metric(self, metric: PerformanceMetric) -> None:
        """Store a recorded metric with bounded capacity."""
        self._metrics.append(metric)
        if len(self._metrics) > self.max_records:
            # Keep recent records to prevent unbounded memory growth
            self._metrics = self._metrics[-self.max_records:]

    def get_metrics(self, operation: Optional[str] = None) -> List[PerformanceMetric]:
        """Retrieve recorded metrics, optionally filtered by operation name."""
        if operation:
            return [m for m in self._metrics if m.operation == operation]
        return list(self._metrics)

    def get_summary(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """Compute aggregate performance statistics."""
        metrics = self.get_metrics(operation)
        if not metrics:
            return {
                "count": 0,
                "avg_duration_ms": 0.0,
                "min_duration_ms": 0.0,
                "max_duration_ms": 0.0,
                "total_duration_ms": 0.0,
                "avg_memory_delta_mb": 0.0,
            }

        durations = [m.duration_ms for m in metrics]
        mem_deltas = [m.memory_delta_mb for m in metrics]

        return {
            "count": len(metrics),
            "avg_duration_ms": round(sum(durations) / len(durations), 3),
            "min_duration_ms": round(min(durations), 3),
            "max_duration_ms": round(max(durations), 3),
            "total_duration_ms": round(sum(durations), 3),
            "avg_memory_delta_mb": round(sum(mem_deltas) / len(mem_deltas), 3),
        }

    def clear(self) -> None:
        """Clear all stored metrics."""
        self._metrics.clear()


# Default process-level profiler
default_profiler = PerformanceProfiler()
