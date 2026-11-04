"""WinFix AI — UI Formatting, State Management & Caching Benchmarks (Phase 24)."""

import unittest

from production.performance import PerformanceProfiler
from ui.formatting import (
    format_bytes,
    format_risk_badge,
    format_severity_badge,
    format_status_badge,
    format_timestamp,
    format_tool_name,
)
from ui.state import UIStateManager


class BenchmarkUI(unittest.TestCase):
    """Benchmarks for UI formatting functions and state transition cycles."""

    @classmethod
    def setUpClass(cls):
        cls.profiler = PerformanceProfiler()

    def test_benchmark_formatting_functions(self):
        """Benchmark rendering speed of UI badge and string formatters."""
        with self.profiler.measure("ui_formatting_time") as timer:
            for _ in range(200):
                format_bytes(1073741824)
                format_risk_badge("SAFE")
                format_severity_badge("HIGH")
                format_status_badge("SUCCESS")
                format_timestamp("2026-09-25T12:00:00")
                format_tool_name("get_network_adapters_diagnostics")

        avg_batch = timer.duration_ms / 200.0
        self.assertLess(avg_batch, 2.0)

    def test_benchmark_state_manager_transitions(self):
        """Benchmark state manager update and retrieval performance."""
        state = UIStateManager()
        with self.profiler.measure("ui_state_transitions_time") as timer:
            for i in range(100):
                state.set_active_session(f"session_{i}")
                state.record_diagnostic_result(f"diag_{i}", {"status": "ok"})
                state.clear_session()

        self.assertLess(timer.duration_ms, 50.0)


if __name__ == "__main__":
    unittest.main()
