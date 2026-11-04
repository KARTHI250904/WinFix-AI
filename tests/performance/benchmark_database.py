"""WinFix AI — SQLite Operations & Knowledge Search Benchmarks (Phase 24)."""

import tempfile
import unittest
from pathlib import Path

from database.db import DatabaseManager
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine
from database.repositories import SessionRepository, ToolExecutionRepository
from knowledge.seed_data import seed_default_knowledge
from production.performance import PerformanceProfiler
from tests.performance.benchmark_config import benchmark_config


class BenchmarkDatabase(unittest.TestCase):
    """Benchmarks for SQLite queries, transactions, batch knowledge lookups, and searches."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmpdir.name) / "bench_db.db"
        cls.mgr = DatabaseManager(db_path=cls.db_path)
        cls.mgr.init_db()
        cls.repo = KnowledgeRepository(cls.mgr)
        seed_default_knowledge(cls.repo)
        cls.search_engine = KnowledgeSearchEngine(cls.repo)
        cls.session_repo = SessionRepository(cls.mgr)
        cls.tool_exec_repo = ToolExecutionRepository(cls.mgr)
        cls.profiler = PerformanceProfiler()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_benchmark_sqlite_insert_and_query(self):
        """Benchmark session insertion and retrieval latency."""
        with self.profiler.measure("sqlite_query_time") as timer:
            sess_id = f"bench_sess_{timer.start_snapshot.timestamp}"
            self.session_repo.create_session(session_id=sess_id, mode="diagnose")
            sess = self.session_repo.get_session(session_id=sess_id)

        self.assertIsNotNone(sess)
        self.assertLess(timer.duration_ms, benchmark_config.MAX_SQLITE_QUERY_TIME_MS)

    def test_benchmark_knowledge_search_latency(self):
        """Benchmark multi-keyword knowledge search latency with ranking."""
        queries = [
            "slow internet connection dns resolving",
            "high cpu usage system process overheating",
            "disk full temp files cleanup storage",
            "bluetooth audio device disconnect pairing",
            "windows defender threat real time protection",
        ]

        for q in queries:
            with self.subTest(query=q):
                with self.profiler.measure("knowledge_search_time") as timer:
                    results = self.search_engine.search(query=q, limit=5)

                self.assertIsInstance(results, list)
                self.assertLess(timer.duration_ms, benchmark_config.MAX_KNOWLEDGE_SEARCH_TIME_MS)

    def test_benchmark_batch_list_articles(self):
        """Benchmark batch retrieval of all knowledge articles."""
        with self.profiler.measure("knowledge_list_articles_time") as timer:
            articles = self.repo.list_articles()

        self.assertGreater(len(articles), 0)
        self.assertLess(timer.duration_ms, benchmark_config.MAX_KNOWLEDGE_SEARCH_TIME_MS)


if __name__ == "__main__":
    unittest.main()
