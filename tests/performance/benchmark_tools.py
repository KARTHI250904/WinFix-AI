"""WinFix AI — Diagnostic Tools & Registry Lookup Benchmarks (Phase 24)."""

import unittest

from agent.safety import SafetyEngine
from agent.tool_registry import create_default_registry
from production.performance import PerformanceProfiler
from tests.performance.benchmark_config import benchmark_config


class BenchmarkTools(unittest.TestCase):
    """Benchmarks for ToolRegistry lookup, SafetyEngine policy evaluations, and safe tool executions."""

    @classmethod
    def setUpClass(cls):
        cls.registry = create_default_registry()
        cls.safety = SafetyEngine(registry=cls.registry)
        cls.profiler = PerformanceProfiler()

    def test_benchmark_registry_lookup_speed(self):
        """Benchmark tool lookup and permission metadata retrieval."""
        tool_names = self.registry.list_tool_names()
        self.assertEqual(len(tool_names), 59)

        with self.profiler.measure("registry_lookup_time") as timer:
            for name in tool_names:
                tool = self.registry.get(name)
                self.assertIsNotNone(tool)

        avg_lookup = timer.duration_ms / len(tool_names)
        self.assertLess(avg_lookup, benchmark_config.MAX_DIAGNOSTIC_LOOKUP_TIME_MS)

    def test_benchmark_safety_engine_evaluation_speed(self):
        """Benchmark safety engine fail-closed policy gate evaluations."""
        with self.profiler.measure("safety_evaluation_time") as timer:
            d1 = self.safety.evaluate("get_cpu_diagnostics", {})
            d2 = self.safety.evaluate("unregistered_malicious_tool", {})
            d3 = self.safety.evaluate("flush_dns_cache", {})

        self.assertTrue(d1.allowed)
        self.assertTrue(d2.blocked)
        self.assertTrue(d3.requires_confirmation)
        self.assertLess(timer.duration_ms, 50.0)

    def test_benchmark_safe_diagnostic_tools(self):
        """Benchmark native execution speed of core safe diagnostic tools."""
        safe_tools_to_test = [
            "get_cpu_diagnostics",
            "get_temp_storage_info",
            "get_service_status",
            "get_network_adapters_diagnostics",
        ]

        for name in safe_tools_to_test:
            tool = self.registry.get(name)
            self.assertIsNotNone(tool)
            with self.subTest(tool=name):
                with self.profiler.measure(f"tool_exec_{name}") as timer:
                    if name == "get_service_status":
                        res = tool.handler(service_name="Spooler")
                    else:
                        res = tool.handler()

                self.assertTrue(res.get("success", False))
                self.assertLess(timer.duration_ms, benchmark_config.MAX_SAFE_TOOL_EXEC_TIME_MS)


if __name__ == "__main__":
    unittest.main()
