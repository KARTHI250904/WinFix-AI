"""WinFix AI — Startup & Initialization Benchmarks (Phase 24)."""

import tempfile
import unittest
from pathlib import Path

from agent.tool_registry import create_default_registry
from database.db import DatabaseManager
from database.knowledge_repository import KnowledgeRepository
from knowledge.seed_data import seed_default_knowledge
from production.config import ProductionConfig, prod_config
from production.health_check import HealthCheckEngine
from production.performance import PerformanceProfiler, PerformanceTimer
from tests.performance.benchmark_config import benchmark_config


class BenchmarkStartup(unittest.TestCase):
    """Benchmarks for cold & warm startup, registry initialization, database init, and health checks."""

    def setUp(self):
        self.profiler = PerformanceProfiler()

    def test_benchmark_tool_registry_initialization(self):
        """Benchmark tool registry instantiation duration."""
        with self.profiler.measure("tool_registry_initialization_time") as timer:
            registry = create_default_registry()
            tools = registry.list_tools()

        self.assertEqual(len(tools), 59)
        self.assertLess(timer.duration_ms, benchmark_config.MAX_TOOL_REGISTRY_INIT_TIME_MS)

    def test_benchmark_database_initialization(self):
        """Benchmark clean SQLite schema creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "bench_init.db"
            mgr = DatabaseManager(db_path=db_path)

            with self.profiler.measure("database_initialization_time") as timer:
                res = mgr.init_db()

            self.assertTrue(res["success"])
            self.assertGreater(len(res["tables"]), 0)
            self.assertLess(timer.duration_ms, benchmark_config.MAX_DB_INIT_TIME_MS)

    def test_benchmark_knowledge_initialization(self):
        """Benchmark initial seeding of troubleshooting knowledge base."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "bench_seed.db"
            mgr = DatabaseManager(db_path=db_path)
            mgr.init_db()
            repo = KnowledgeRepository(mgr)

            with self.profiler.measure("knowledge_initialization_time") as timer:
                seed_res = seed_default_knowledge(repo)

            self.assertTrue(seed_res["success"])
            self.assertGreater(seed_res["article_count"], 0)
            self.assertLess(timer.duration_ms, benchmark_config.MAX_KNOWLEDGE_INIT_TIME_MS)

    def test_benchmark_health_check_execution(self):
        """Benchmark health check engine verification cycle."""
        engine = HealthCheckEngine()
        with self.profiler.measure("health_check_time") as timer:
            report = engine.run_health_check()

        self.assertTrue(report.is_operational())
        self.assertLess(timer.duration_ms, benchmark_config.MAX_HEALTH_CHECK_TIME_MS)


if __name__ == "__main__":
    unittest.main()
