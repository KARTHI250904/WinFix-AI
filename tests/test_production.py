"""
WinFix AI — Phase 22 Production Readiness & Release Test Suite.

Validates:
1. Production Configuration & Version Consistency (1.0.0).
2. Windows Application Data Paths & Traversal Protection.
3. First-Run Setup Idempotency & Repeatability.
4. Production Logging & Privacy Sanitization.
5. Crash Handling & Safe Exception Boundary.
6. Startup Health Evaluation & Subsystem Degradation.
7. Application Lifecycle: Restart, Migration, and Uninstall Policies.
8. Five-Mode Production Smoke Tests.
"""

from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.agent_response import AgentResponse, ToolRequest
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from config import config as app_config
from database.db import DatabaseManager
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine
from modes.autopilot import AutopilotEngine
from modes.personal_tutor import PersonalTutor
from production import (
    __app_name__,
    __version__,
    AppPaths,
    ComponentStatus,
    HealthCheckEngine,
    MigrationResult,
    ProductionConfig,
    RestartCheckResult,
    SafeCrashSummary,
    UninstallPolicy,
    execute_safe_uninstall,
    get_category_logger,
    prod_config,
    resolve_app_paths,
    run_database_migration,
    run_first_time_setup,
    safe_exception_boundary,
    setup_production_logging,
    verify_restart_state,
)
from production.logging import LogCategory, SanitizingFormatter, sanitize_log_text
from production.paths import initialize_app_directories, is_safe_app_path
from production.setup import is_first_run


class TestProductionConfigAndVersion(unittest.TestCase):
    """Test production configuration and authoritative version management."""

    def test_single_authoritative_version(self):
        self.assertEqual(__version__, "1.0.0")
        self.assertEqual(prod_config.app_version, "1.0.0")
        self.assertEqual(app_config.app_version, "1.0.0")
        self.assertEqual(__app_name__, "WinFix AI")

    def test_production_config_defaults(self):
        cfg = ProductionConfig()
        self.assertFalse(cfg.debug_mode)
        self.assertEqual(cfg.ollama_model, "gemma4:12b")
        self.assertIn(cfg.vision_model, ["minicpm-v:latest", "moondream:latest"])
        self.assertEqual(cfg.stt_provider, "whisper_cpp")
        self.assertEqual(cfg.sqlite_busy_timeout_ms, 5000)
        self.assertTrue(cfg.sqlite_wal_mode)
        self.assertGreaterEqual(cfg.max_autopilot_steps, 5)


class TestAppPathsAndDirectories(unittest.TestCase):
    """Test Windows application data paths and directory creation."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="winfix_test_paths_"))
        self.paths = resolve_app_paths(base_data_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_path_structure(self):
        self.assertEqual(self.paths.root_dir, self.test_dir)
        self.assertEqual(self.paths.data_dir, self.test_dir / "Data")
        self.assertEqual(self.paths.logs_dir, self.test_dir / "Logs")
        self.assertEqual(self.paths.config_dir, self.test_dir / "Config")
        self.assertEqual(self.paths.temp_dir, self.test_dir / "Temp")
        self.assertEqual(self.paths.database_path, self.test_dir / "Data" / "winfix.db")

    def test_initialize_directories_and_write_permission(self):
        results = initialize_app_directories(self.paths)
        self.assertTrue(all(results.values()))
        self.assertTrue(self.paths.data_dir.exists())
        self.assertTrue(self.paths.logs_dir.exists())
        self.assertTrue(self.paths.config_dir.exists())
        self.assertTrue(self.paths.temp_dir.exists())

    def test_path_traversal_prevention(self):
        safe_child = self.paths.data_dir / "reports" / "summary.json"
        unsafe_traversal = self.paths.root_dir / ".." / ".." / "Windows" / "System32"
        self.assertTrue(is_safe_app_path(safe_child, self.paths.root_dir))
        self.assertFalse(is_safe_app_path(unsafe_traversal, self.paths.root_dir))


class TestFirstRunAndSetup(unittest.TestCase):
    """Test deterministic and idempotent first-run setup."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="winfix_test_setup_"))
        self.paths = resolve_app_paths(base_data_dir=self.test_dir)
        self.config = ProductionConfig(paths=self.paths)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_first_run_detection(self):
        self.assertTrue(is_first_run(self.config))

    def test_first_run_execution_idempotency(self):
        # 1. First execution
        res1 = run_first_time_setup(self.config)
        self.assertTrue(res1.success)
        self.assertTrue(res1.directories_created)
        self.assertTrue(res1.database_initialized)
        self.assertTrue(res1.knowledge_seeded)
        self.assertEqual(res1.seed_count, 9)
        self.assertFalse(is_first_run(self.config))

        # 2. Second execution (must not duplicate articles or fail)
        res2 = run_first_time_setup(self.config)
        self.assertTrue(res2.success)
        self.assertEqual(res2.seed_count, 9)

        # 3. Verify Database state
        db_mgr = DatabaseManager(db_path=self.paths.database_path)
        repo = KnowledgeRepository(db_mgr)
        self.assertEqual(repo.count_articles(), 9)


class TestProductionLoggingAndSanitization(unittest.TestCase):
    """Test production logging sanitization."""

    def test_sanitize_windows_user_path(self):
        raw = "Error accessing C:\\Users\\Administrator\\AppData\\Local\\secret.json"
        sanitized = sanitize_log_text(raw)
        self.assertNotIn("Administrator", sanitized)
        self.assertIn("C:\\Users\\<User>\\AppData\\Local\\secret.json", sanitized)

    def test_sanitize_credentials_and_emails(self):
        raw = "Failed auth: api_key='sk-1234567890abcdef' email=test.user@company.com"
        sanitized = sanitize_log_text(raw)
        self.assertNotIn("sk-1234567890abcdef", sanitized)
        self.assertNotIn("test.user@company.com", sanitized)
        self.assertIn("<credential-masked>", sanitized)
        self.assertIn("<email-masked>", sanitized)

    def test_category_logger_creation(self):
        log = get_category_logger(LogCategory.SECURITY)
        self.assertEqual(log.name, "winfix.SECURITY")


class TestCrashHandlerBoundary(unittest.TestCase):
    """Test production crash handling and exception boundaries."""

    def test_safe_exception_boundary_catches_error(self):
        @safe_exception_boundary(context="diagnostic_worker")
        def faulty_operation():
            raise RuntimeError("Underlying driver failure 0x80004005")

        success, result, crash = faulty_operation()
        self.assertFalse(success)
        self.assertIsNone(result)
        self.assertIsNotNone(crash)
        self.assertTrue(crash.is_crashed)
        self.assertIn("diagnostic_worker", crash.context)
        self.assertNotIn("Traceback", crash.user_message)
        self.assertIn("unexpected error", crash.user_message.lower())

    def test_safe_exception_boundary_passes_success(self):
        @safe_exception_boundary(context="healthy_worker")
        def normal_operation():
            return {"status": "ok", "value": 42}

        success, result, crash = normal_operation()
        self.assertTrue(success)
        self.assertEqual(result["value"], 42)
        self.assertIsNone(crash)


class TestStartupHealthCheck(unittest.TestCase):
    """Test startup health evaluation and ToolRegistry validation."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="winfix_test_health_"))
        self.paths = resolve_app_paths(base_data_dir=self.test_dir)
        self.config = ProductionConfig(paths=self.paths)
        run_first_time_setup(self.config)
        self.health_engine = HealthCheckEngine(config=self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tool_registry_baseline_invariants(self):
        report = self.health_engine.run_health_check()
        self.assertIn("tool_registry", report.components)
        self.assertIn(report.tool_counts["total"], (59, 62))
        self.assertIn(report.tool_counts["safe"], (49, 52))
        self.assertEqual(report.tool_counts["medium"], 10)
        self.assertEqual(report.tool_counts["high"], 0)
        self.assertIn(report.tool_counts["unique"], (59, 62))
        self.assertEqual(report.components["tool_registry"].status, ComponentStatus.READY)

    def test_safety_engine_health_verification(self):
        report = self.health_engine.run_health_check()
        self.assertEqual(report.components["safety_engine"].status, ComponentStatus.READY)


class TestLifecycleManagement(unittest.TestCase):
    """Test restart validation, transactional migration, and uninstall policies."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="winfix_test_lifecycle_"))
        self.paths = resolve_app_paths(base_data_dir=self.test_dir)
        self.config = ProductionConfig(paths=self.paths)
        run_first_time_setup(self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_verify_restart_state(self):
        restart_res = verify_restart_state(self.config)
        self.assertTrue(restart_res.success)
        self.assertTrue(restart_res.database_intact)
        self.assertEqual(restart_res.knowledge_count, 9)
        self.assertTrue(restart_res.marker_valid)

    def test_transactional_schema_migration(self):
        mig_res = run_database_migration(target_version="1.0.0", config=self.config)
        self.assertTrue(mig_res.success)
        self.assertEqual(mig_res.to_version, "1.0.0")
        self.assertIn("sessions", mig_res.tables_migrated)
        self.assertIn("knowledge_articles", mig_res.tables_migrated)

    def test_uninstall_policy_keep_user_data(self):
        results = execute_safe_uninstall(UninstallPolicy.KEEP_USER_DATA, config=self.config)
        self.assertTrue(results["temp_cleaned"])
        self.assertTrue(results["config_cleaned"])
        self.assertFalse(results["data_cleaned"])
        self.assertTrue(self.paths.database_path.exists())

    def test_uninstall_policy_purge_all(self):
        results = execute_safe_uninstall(UninstallPolicy.PURGE_ALL, config=self.config)
        self.assertTrue(results["data_cleaned"])
        self.assertFalse(self.paths.database_path.exists())


class TestFiveModesProductionReadiness(unittest.TestCase):
    """Smoke test validation for all five operating modes."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="winfix_test_modes_"))
        self.paths = resolve_app_paths(base_data_dir=self.test_dir)
        self.config = ProductionConfig(paths=self.paths)
        run_first_time_setup(self.config)
        self.db_mgr = DatabaseManager(db_path=self.paths.database_path)
        self.registry = create_default_registry()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_mode1_diagnostic_and_repair_tools_ready(self):
        tool = self.registry.get("get_complete_system_info")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, RiskLevel.SAFE)
        self.assertTrue(callable(tool.handler))

    def test_mode2_personal_tutor_mode_ready(self):
        tutor = PersonalTutor(db=self.db_mgr, tool_registry=self.registry)
        mock_tutor_json = json.dumps({
            "title": "CPU Usage Diagnostic",
            "summary": "CPU utilization is currently elevated.",
            "what_happened": "High process activity observed.",
            "evidence": ["CPU at 95%"],
            "severity": "ELEVATED",
            "possible_causes": ["Background service update"],
            "what_this_means": "Computer may feel sluggish temporarily.",
            "recommended_next_steps": ["Inspect top processes"],
            "recommended_tools": ["get_top_cpu_processes"],
            "safety_notes": ["No automatic repair needed."],
        })
        with patch.object(tutor.client, "generate", return_value=mock_tutor_json):
            response = tutor.explain_diagnostic(
                diagnostic_data={"cpu_usage": 95.0, "high_proc": "system_idle"},
                user_question="How do I diagnose high CPU usage?",
            )
        self.assertIsNotNone(response)
        self.assertTrue(hasattr(response, "summary") and bool(response.summary))

    def test_mode3_autopilot_mode_ready(self):
        autopilot = AutopilotEngine(registry=self.registry, db=self.db_mgr)
        mock_plan_json = json.dumps({
            "plan_summary": "Network diagnostic workflow",
            "steps": [
                {
                    "sequence": 1,
                    "tool_name": "check_internet_connectivity",
                    "arguments": {},
                    "purpose": "Verify gateway reachability",
                    "expected_outcome": "Reachability status returned",
                    "preconditions": [],
                    "requires_confirmation": False,
                }
            ]
        })
        with patch.object(autopilot.ai_client, "generate", return_value=mock_plan_json):
            plan = autopilot.plan("Diagnose network connection issues")
        self.assertIsNotNone(plan)
        self.assertTrue(hasattr(plan, "steps") and len(plan.steps) > 0)

    def test_mode4_screenshot_analyzer_ready(self):
        from ai.screenshot_analyzer import ScreenshotAnalyzer
        analyzer = ScreenshotAnalyzer()
        self.assertIsNotNone(analyzer)

    def test_mode5_voice_diagnostics_ready(self):
        from ai.voice_transcriber import VoiceTranscriber
        voice_mgr = VoiceTranscriber()
        self.assertIsNotNone(voice_mgr)


if __name__ == "__main__":
    unittest.main()
