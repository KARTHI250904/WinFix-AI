"""WinFix AI — AI Prompt Construction & Deduplication Benchmarks (Phase 24)."""

import json
import unittest
from unittest.mock import MagicMock, patch

from agent.planner import AgentPlanner
from ai.ollama_client import OllamaClient
from ai.planner_prompt import build_diagnostic_planner_prompt
from modes.personal_tutor import PersonalTutor
from modes.tutor_prompt import build_tutor_system_prompt
from production.performance import PerformanceProfiler


class BenchmarkAI(unittest.TestCase):
    """Benchmarks for prompt assembly, parsing, mock generation, and deduplication."""

    @classmethod
    def setUpClass(cls):
        cls.profiler = PerformanceProfiler()
        cls.mock_client = OllamaClient()

    def test_benchmark_prompt_construction(self):
        """Benchmark dynamic prompt formatting and token assembly."""
        sys_info = {
            "os": {"edition": "Windows 11 Pro", "build_number": "22631"},
            "cpu": {"model": "Intel Core i7", "physical_cores": 8},
        }

        with self.profiler.measure("prompt_construction_time") as timer:
            for _ in range(50):
                p = build_diagnostic_planner_prompt(
                    problem_description="My PC is freezing when opening browser.",
                    system_info=sys_info,
                )
                self.assertIn("freezing", p)

        avg_time = timer.duration_ms / 50.0
        self.assertLess(avg_time, 5.0)

    def test_benchmark_read_only_deduplication(self):
        """Benchmark response latency reduction via safe read-only deduplication."""
        client = OllamaClient()
        client.clear_cache()

        mock_resp = {
            "response": json.dumps({
                "explanation": "High CPU utilization caused by background indexer.",
                "severity": "MEDIUM",
            })
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_http = MagicMock()
            mock_http.status = 200
            mock_http.read.return_value = json.dumps(mock_resp).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_http

            # First call (cold)
            res1 = client.generate(
                prompt="Explain high CPU load.",
                model="gemma4:12b",
                use_cache=True,
            )
            self.assertTrue(res1["success"])
            self.assertFalse(res1.get("cached", False))

            # Second call (warm, cached)
            res2 = client.generate(
                prompt="Explain high CPU load.",
                model="gemma4:12b",
                use_cache=True,
            )
            self.assertTrue(res2["success"])
            self.assertTrue(res2.get("cached", False))
            self.assertEqual(res1["response"], res2["response"])


if __name__ == "__main__":
    unittest.main()
