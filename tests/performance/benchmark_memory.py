"""WinFix AI — Memory Consumption & Stability Benchmarks (Phase 24)."""

import gc
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from agent.tool_registry import create_default_registry
from database.db import DatabaseManager
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine
from input.screenshot_input import validate_and_load_image
from knowledge.seed_data import seed_default_knowledge
from production.performance import PerformanceProfiler, take_resource_snapshot
from tests.performance.benchmark_config import benchmark_config


class BenchmarkMemory(unittest.TestCase):
    """Benchmarks for memory consumption during diagnostics, image processing, and long-running cycles."""

    @classmethod
    def setUpClass(cls):
        cls.profiler = PerformanceProfiler()

    def test_benchmark_screenshot_memory_release(self):
        """Benchmark image memory allocation and immediate buffer release."""
        # Create a test PNG image buffer
        img = Image.new("RGB", (1920, 1080), color=(73, 109, 137))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()
        buf.close()

        snap_before = take_resource_snapshot()

        for _ in range(5):
            meta, norm_bytes, pil_img = validate_and_load_image(raw_bytes, "test.png")
            self.assertEqual(meta.width, 1920)
            self.assertEqual(meta.height, 1080)
            # Ensure PIL image and bytes are freed
            del pil_img
            del norm_bytes

        gc.collect()
        snap_after = take_resource_snapshot()
        growth_mb = snap_after.memory_rss_mb - snap_before.memory_rss_mb

        self.assertLess(growth_mb, benchmark_config.MAX_LONG_RUNNING_MEMORY_GROWTH_MB)

    def test_benchmark_long_running_diagnostic_cycles_stability(self):
        """Benchmark repeated safe workflow cycles to detect memory leaks and growth."""
        registry = create_default_registry()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "bench_stability.db"
            mgr = DatabaseManager(db_path=db_path)
            mgr.init_db()
            repo = KnowledgeRepository(mgr)
            seed_default_knowledge(repo)
            searcher = KnowledgeSearchEngine(repo)

            gc.collect()
            snap_start = take_resource_snapshot()

            # Execute 15 repeated safe diagnostic and knowledge cycles
            for cycle in range(15):
                searcher.search("network dns adapter disconnect", limit=5)
                # Safe CPU tool
                t_cpu = registry.get("get_cpu_diagnostics")
                if t_cpu:
                    t_cpu.handler()
                # Safe temp storage tool
                t_stor = registry.get("get_temp_storage_info")
                if t_stor:
                    t_stor.handler()

            gc.collect()
            snap_end = take_resource_snapshot()
            growth_mb = snap_end.memory_rss_mb - snap_start.memory_rss_mb

            self.assertLess(growth_mb, benchmark_config.MAX_LONG_RUNNING_MEMORY_GROWTH_MB)


if __name__ == "__main__":
    unittest.main()
