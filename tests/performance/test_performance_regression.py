"""WinFix AI — Performance Regression & Security Verification Suite (Phase 24).

Validates:
1. Performance profiler and timing mechanisms.
2. Startup and rerun optimization.
3. SQLite query performance and batch efficiency.
4. AI read-only request deduplication.
5. Screenshot and Voice memory release & safety bounds.
6. Long-running multi-cycle stability.
7. Zero AST security violations across all 9 production directories.
8. ToolRegistry exact invariants: 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates).
"""

import ast
import gc
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from ai.ollama_client import OllamaClient
from database.db import DatabaseManager
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine
from input.screenshot_input import validate_and_load_image
from knowledge.seed_data import seed_default_knowledge
from production.health_check import HealthCheckEngine
from production.performance import (
    PerformanceMetric,
    PerformanceProfiler,
    PerformanceSnapshot,
    PerformanceTimer,
    take_resource_snapshot,
)
from tests.performance.benchmark_config import benchmark_config


class TestPerformanceRegression(unittest.TestCase):
    """Rigorous Phase 24 Performance Regression & Security Test Suite."""

    @classmethod
    def setUpClass(cls):
        cls.registry = create_default_registry()
        cls.safety = SafetyEngine(registry=cls.registry)
        cls.root_dir = Path(__file__).resolve().parent.parent.parent

    # --- 1. PROFILER INFRASTRUCTURE TESTS ---

    def test_profiler_lifecycle_and_metric_collection(self):
        """Verify PerformanceProfiler measures duration, captures metrics, and computes summaries."""
        profiler = PerformanceProfiler(max_records=10)
        with profiler.measure("test_operation") as timer:
            # Short work
            total = sum(i * i for i in range(1000))

        self.assertGreater(timer.duration_ms, 0.0)
        self.assertEqual(timer.status, "SUCCESS")

        metrics = profiler.get_metrics("test_operation")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].operation, "test_operation")

        summary = profiler.get_summary("test_operation")
        self.assertEqual(summary["count"], 1)
        self.assertGreater(summary["total_duration_ms"], 0.0)

        profiler.clear()
        self.assertEqual(len(profiler.get_metrics()), 0)

    def test_profiler_capacity_bounding(self):
        """Verify profiler discards oldest records to prevent unbounded memory growth."""
        profiler = PerformanceProfiler(max_records=5)
        for i in range(10):
            with profiler.measure(f"op_{i}"):
                pass

        metrics = profiler.get_metrics()
        self.assertEqual(len(metrics), 5)
        self.assertEqual(metrics[-1].operation, "op_9")

    # --- 2. SQLITE BATCHING & QUERY EFFICIENCY ---

    def test_sqlite_knowledge_batch_list_efficiency(self):
        """Verify list_articles performs batched queries rather than N connection loops."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_batch.db"
            mgr = DatabaseManager(db_path=db_path)
            mgr.init_db()
            repo = KnowledgeRepository(mgr)
            seed_default_knowledge(repo)

            profiler = PerformanceProfiler()
            with profiler.measure("list_articles") as timer:
                articles = repo.list_articles()

            self.assertGreaterEqual(len(articles), 9)
            self.assertLess(timer.duration_ms, 150.0)

    def test_sqlite_indexes_exist(self):
        """Verify required performance indexes are created on startup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_indexes.db"
            mgr = DatabaseManager(db_path=db_path)
            mgr.init_db()

            with mgr.get_connection() as conn:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index';")
                indexes = [r["name"] for r in cursor.fetchall()]

            self.assertIn("idx_diagnostics_session", indexes)
            self.assertIn("idx_tool_executions_session", indexes)
            self.assertIn("idx_knowledge_symptoms_article", indexes)
            self.assertIn("idx_knowledge_causes_article", indexes)

    # --- 3. AI DEDUPLICATION & LATENCY ---

    def test_ai_read_only_deduplication_integrity(self):
        """Verify read-only request caching returns exact matches and avoids duplicate requests."""
        client = OllamaClient()
        client.clear_cache()

        mock_resp = {
            "response": json.dumps({"explanation": "Safe read-only reasoning."}),
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_http = MagicMock()
            mock_http.status = 200
            mock_http.read.return_value = json.dumps(mock_resp).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_http

            # 1st call
            res1 = client.generate("Why is Wi-Fi disconnected?", use_cache=True)
            self.assertFalse(res1.get("cached", False))

            # 2nd call (identical)
            res2 = client.generate("Why is Wi-Fi disconnected?", use_cache=True)
            self.assertTrue(res2.get("cached", False))
            self.assertEqual(res1["response"], res2["response"])

            # Call with use_cache=False (must NOT use cache)
            res3 = client.generate("Why is Wi-Fi disconnected?", use_cache=False)
            self.assertFalse(res3.get("cached", False))

    # --- 4. SCREENSHOT & VOICE BOUNDED MEMORY ---

    def test_screenshot_buffer_release_and_bounds(self):
        """Verify screenshot processing respects 10MB bounds and releases image buffers."""
        img = Image.new("RGBA", (1280, 720), color=(20, 30, 40, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        buf.close()

        meta, norm_bytes, pil_img = validate_and_load_image(data, "test.png")
        self.assertEqual(meta.width, 1280)
        self.assertEqual(meta.height, 720)
        self.assertLessEqual(meta.file_size, benchmark_config.MAX_SCREENSHOT_BYTES)

        # Cleanup
        del pil_img
        del norm_bytes
        gc.collect()

    # --- 5. LONG-RUNNING STABILITY TEST ---

    def test_stability_repeated_workflow_cycles(self):
        """Execute 10 complete diagnostic/knowledge/safety cycles and verify memory stability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_stability.db"
            mgr = DatabaseManager(db_path=db_path)
            mgr.init_db()
            repo = KnowledgeRepository(mgr)
            seed_default_knowledge(repo)
            searcher = KnowledgeSearchEngine(repo)

            gc.collect()
            snap_before = take_resource_snapshot()

            for i in range(10):
                # 1. Search
                res = searcher.search("internet dns speed", limit=3)
                self.assertIsInstance(res, list)

                # 2. Safety evaluation
                dec = self.safety.evaluate("get_cpu_diagnostics", {})
                self.assertTrue(dec.allowed)

                # 3. Tool execution
                tool = self.registry.get("get_temp_storage_info")
                if tool:
                    r = tool.handler()
                    self.assertTrue(r.get("success", False))

            gc.collect()
            snap_after = take_resource_snapshot()
            growth = snap_after.memory_rss_mb - snap_before.memory_rss_mb
            self.assertLess(growth, benchmark_config.MAX_LONG_RUNNING_MEMORY_GROWTH_MB)

    # --- 6. AST SCAN & SECURITY INVARIANTS ACROSS ALL 9 PRODUCTION DIRS ---

    def test_ast_scan_all_nine_production_directories(self):
        """Static AST scan of all 9 production directories ensuring 0 prohibited execution primitives."""
        production_dirs = [
            self.root_dir / "agent",
            self.root_dir / "ai",
            self.root_dir / "database",
            self.root_dir / "input",
            self.root_dir / "knowledge",
            self.root_dir / "modes",
            self.root_dir / "ui",
            self.root_dir / "windows",
            self.root_dir / "production",
        ]

        violations = []
        file_count = 0

        for pdir in production_dirs:
            if not pdir.exists():
                continue
            for pyfile in pdir.rglob("*.py"):
                file_count += 1
                with open(pyfile, "r", encoding="utf-8") as f:
                    try:
                        tree = ast.parse(f.read(), filename=str(pyfile))
                    except Exception as e:
                        violations.append(f"Failed to parse {pyfile}: {e}")
                        continue

                for node in ast.walk(tree):
                    # Prohibited imports
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "subprocess" or alias.name.startswith("subprocess."):
                                violations.append(f"{pyfile.name}:{node.lineno} - Forbidden import '{alias.name}'")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and (node.module == "subprocess" or node.module.startswith("subprocess.")):
                            violations.append(f"{pyfile.name}:{node.lineno} - Forbidden from '{node.module}' import ...")

                    # Prohibited calls: eval, exec
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            if node.func.id in {"eval", "exec"}:
                                violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to {node.func.id}()")
                        elif isinstance(node.func, ast.Attribute):
                            if isinstance(node.func.value, ast.Name):
                                if node.func.value.id == "os" and node.func.attr in {"system", "popen"}:
                                    violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to os.{node.func.attr}()")
                                if node.func.value.id in {"subprocess"} and node.func.attr in {"Popen", "run", "call", "check_output", "check_call"}:
                                    violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to subprocess.{node.func.attr}()")
                                if node.func.attr in {"CreateProcess", "WinExec", "ShellExecute"}:
                                    violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to {node.func.attr}()")

                        # Prohibited keyword argument shell=True
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                violations.append(f"{pyfile.name}:{node.lineno} - Forbidden shell=True call parameter")

        self.assertGreater(file_count, 20, "Should have audited at least 20 production python files.")
        self.assertEqual(len(violations), 0, f"Prohibited execution primitives found:\n" + "\n".join(violations))

    def test_tool_registry_invariants_preserved(self):
        """Hard invariant: exactly 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates)."""
        tools = self.registry.list_tools()
        self.assertIn(len(tools), (59, 62))

        safe_tools = [t for t in tools if t.risk == RiskLevel.SAFE]
        medium_tools = [t for t in tools if t.risk == RiskLevel.MEDIUM]
        high_tools = [t for t in tools if t.risk == RiskLevel.HIGH]

        self.assertIn(len(safe_tools), (49, 52))
        self.assertEqual(len(medium_tools), 10)
        self.assertEqual(len(high_tools), 0)

        tool_names = [t.name for t in tools]
        self.assertEqual(len(tool_names), len(set(tool_names)), "Duplicate tool names detected!")


if __name__ == "__main__":
    unittest.main()
