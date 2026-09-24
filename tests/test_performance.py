"""Comprehensive unit, safety, and verification tests for WinFix AI Phase 8 (Performance Diagnostics & Optimization).

Tests read-only performance diagnostics, process details, disk metrics, resource snapshots,
process blocklist enforcement, user temporary cache cleanup safety, cryptographic confirmation tokens,
deterministic before/after verification lifecycles, and static security AST guarantees.
"""

import inspect
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from agent.performance_diagnostics import (
    PerformanceDiagnosis,
    PerformanceDiagnosticsOrchestrator,
)
from agent.performance_repairs_orchestrator import (
    PerformanceRepairExecutionResult,
    PerformanceRepairProposal,
    PerformanceRepairsOrchestrator,
)
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from database.db import DatabaseManager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository
import windows
from windows.performance_repairs import (
    PROTECTED_PROCESS_NAMES,
    clean_user_temp_cache,
    is_process_termination_blocked,
    terminate_user_process,
)
from windows.performance_tools import (
    get_cpu_diagnostics,
    get_disk_performance_diagnostics,
    get_memory_diagnostics,
    get_process_details,
    get_resource_snapshot,
    get_top_cpu_processes,
    get_top_memory_processes,
)


class TestPerformanceDiagnosticsTools(unittest.TestCase):
    """Test suite verifying read-only performance diagnostic collectors."""

    def test_cpu_diagnostics_structure(self) -> None:
        """Verify CPU diagnostics return valid percentages and core counts."""
        res = get_cpu_diagnostics(interval=0.01)
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "get_cpu_diagnostics")
        self.assertEqual(res["domain"], "performance")
        data = res["data"]
        self.assertIn("overall_percent", data)
        self.assertIn("physical_cores", data)
        self.assertIn("logical_threads", data)
        self.assertIsInstance(data["overall_percent"], (int, float))

    def test_memory_diagnostics_structure(self) -> None:
        """Verify memory diagnostics return RAM and pagefile metrics."""
        res = get_memory_diagnostics()
        self.assertTrue(res["success"])
        self.assertEqual(res["domain"], "performance")
        data = res["data"]
        self.assertIn("virtual_memory", data)
        self.assertIn("swap_memory", data)
        self.assertIn("percent_used", data["virtual_memory"])
        self.assertIn("available_formatted", data["virtual_memory"])

    def test_top_cpu_and_memory_processes_bounded(self) -> None:
        """Verify top process collectors respect result bounds."""
        cpu_res = get_top_cpu_processes(limit=3)
        self.assertTrue(cpu_res["success"])
        self.assertLessEqual(len(cpu_res["data"]["processes"]), 3)

        mem_res = get_top_memory_processes(limit=4)
        self.assertTrue(mem_res["success"])
        self.assertLessEqual(len(mem_res["data"]["processes"]), 4)

    def test_process_details_for_current_process(self) -> None:
        """Verify get_process_details returns structured data for current process."""
        my_pid = os.getpid()
        res = get_process_details(my_pid)
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["pid"], my_pid)
        self.assertIn("name", data)
        self.assertIn("status", data)
        self.assertIn("memory_rss_bytes", data)
        self.assertIn("cpu_percent", data)
        self.assertIn("children", data)

    def test_process_details_invalid_pid_rejected(self) -> None:
        """Verify get_process_details rejects invalid or negative PIDs."""
        res = get_process_details(-1)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_PID")

    def test_disk_performance_diagnostics(self) -> None:
        """Verify disk performance tool returns partition occupancy and I/O metrics."""
        res = get_disk_performance_diagnostics()
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertIn("partitions", data)
        self.assertIn("disk_io", data)

    def test_resource_snapshot(self) -> None:
        """Verify resource snapshot provides unified point-in-time metrics."""
        res = get_resource_snapshot()
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertIn("cpu_percent", data)
        self.assertIn("memory_percent", data)
        self.assertIn("uptime_seconds", data)
        self.assertIn("top_cpu_consumers", data)
        self.assertIn("top_memory_consumers", data)


class TestProcessTerminationSafetyAndBlocklist(unittest.TestCase):
    """Test suite ensuring critical system and OS processes are blocked from termination."""

    def test_pid_0_and_pid_4_strictly_blocked(self) -> None:
        """Verify PID 0 (System Idle) and PID 4 (System) are blocked."""
        blocked_0, reason_0 = is_process_termination_blocked(0)
        self.assertTrue(blocked_0)
        self.assertIn("Kernel", reason_0)

        blocked_4, reason_4 = is_process_termination_blocked(4)
        self.assertTrue(blocked_4)
        self.assertIn("Kernel", reason_4)

    def test_protected_process_names_blocked(self) -> None:
        """Verify all standard Windows system process names are blocked by name."""
        for proc_name in ["svchost.exe", "csrss.exe", "lsass.exe", "explorer.exe", "wininit.exe", "services.exe", "dwm.exe", "smss.exe", "msmpeng.exe"]:
            blocked, reason = is_process_termination_blocked(99999, process_name=proc_name)
            self.assertTrue(blocked, f"Process {proc_name} was not blocked!")
            self.assertIn("blocklist", reason.lower())

    def test_process_name_mismatch_blocked(self) -> None:
        """Verify mismatched process name vs PID fails closed to prevent PID reuse race."""
        my_pid = os.getpid()
        blocked, reason = is_process_termination_blocked(my_pid, process_name="nonexistent_fake_app.exe")
        self.assertTrue(blocked)
        self.assertIn("mismatch", reason.lower())

    def test_terminate_user_process_fails_closed_on_blocked_target(self) -> None:
        """Verify terminate_user_process returns failure when called on blocked PID 4."""
        res = terminate_user_process(4)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "BLOCKED_PROCESS_TARGET")


class TestCacheCleanupSafety(unittest.TestCase):
    """Test suite verifying user temporary cache cleanup boundaries and sandbox protection."""

    def test_temp_cache_cleanup_dry_run(self) -> None:
        """Verify clean_user_temp_cache dry run scans without errors."""
        res = clean_user_temp_cache(dry_run=True)
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertTrue(data["dry_run"])
        self.assertIn("scanned_files_count", data)
        self.assertIn("freed_bytes", data)

    def test_temp_cache_cleanup_in_custom_temp_dir(self) -> None:
        """Verify cache cleanup safely purges obsolete files within temp directory."""
        with tempfile.TemporaryDirectory() as custom_temp:
            # Create test files
            f1 = Path(custom_temp) / "test_old_1.tmp"
            f1.write_text("temporary data 1", encoding="utf-8")
            f2 = Path(custom_temp) / "test_old_2.tmp"
            f2.write_text("temporary data 2", encoding="utf-8")

            with patch.dict(os.environ, {"TEMP": custom_temp, "TMP": custom_temp}):
                res = clean_user_temp_cache(dry_run=False)
                self.assertTrue(res["success"])
                self.assertFalse(f1.exists())
                self.assertFalse(f2.exists())


class TestPerformanceToolRegistration(unittest.TestCase):
    """Test suite verifying ToolRegistry registration and metadata for Phase 8 tools."""

    def setUp(self) -> None:
        self.registry = create_default_registry()

    def test_registered_performance_tools_metadata(self) -> None:
        """Verify Phase 8 diagnostic and repair tools are correctly registered."""
        # 1. Process details (SAFE)
        tool_p = self.registry.get("get_process_details")
        self.assertIsNotNone(tool_p)
        self.assertEqual(tool_p.risk, RiskLevel.SAFE)
        self.assertTrue(tool_p.read_only)
        self.assertTrue(tool_p.automatic_allowed)

        # 2. Disk performance (SAFE)
        tool_d = self.registry.get("get_disk_performance_diagnostics")
        self.assertIsNotNone(tool_d)
        self.assertEqual(tool_d.risk, RiskLevel.SAFE)
        self.assertTrue(tool_d.read_only)

        # 3. Resource snapshot (SAFE)
        tool_s = self.registry.get("get_resource_snapshot")
        self.assertIsNotNone(tool_s)
        self.assertEqual(tool_s.risk, RiskLevel.SAFE)
        self.assertTrue(tool_s.read_only)

        # 4. Terminate user process (MEDIUM repair)
        tool_t = self.registry.get("terminate_user_process")
        self.assertIsNotNone(tool_t)
        self.assertEqual(tool_t.risk, RiskLevel.MEDIUM)
        self.assertFalse(tool_t.read_only)
        self.assertFalse(tool_t.automatic_allowed)
        self.assertEqual(tool_t.verification_tool, "get_process_details")

        # 5. Clean user temp cache (MEDIUM repair)
        tool_c = self.registry.get("clean_user_temp_cache")
        self.assertIsNotNone(tool_c)
        self.assertEqual(tool_c.risk, RiskLevel.MEDIUM)
        self.assertFalse(tool_c.read_only)
        self.assertFalse(tool_c.automatic_allowed)
        self.assertEqual(tool_c.verification_tool, "get_temp_storage_info")


class TestPerformanceOrchestratorAndVerificationLifecycle(unittest.TestCase):
    """Test suite for Performance Diagnostics -> Proposal -> Confirmation -> Verification."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_perf.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db_manager = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db_manager.init_db()

        self.registry = create_default_registry()
        self.exec_repo = ToolExecutionRepository(self.db_manager)
        self.safety_engine = SafetyEngine(registry=self.registry, execution_repo=self.exec_repo)
        self.orchestrator = PerformanceRepairsOrchestrator(
            safety_engine=self.safety_engine,
            registry=self.registry,
            db_mgr=self.db_manager,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_confirmation_token_mismatch_fails_closed(self) -> None:
        """Verify tampered confirmation token is rejected before execution."""
        proposal = PerformanceRepairProposal(
            tool_name="terminate_user_process",
            arguments={"pid": 1234, "process_name": "notepad.exe"},
        )
        token = proposal.generate_confirmation_token("session_1")

        # Tampered argument
        proposal_tampered = PerformanceRepairProposal(
            tool_name="terminate_user_process",
            arguments={"pid": 5678, "process_name": "notepad.exe"},
        )

        res = self.orchestrator.execute_repair_with_verification(
            proposal=proposal_tampered,
            session_id="session_1",
            user_confirmed=True,
            confirmation_token=token,
        )
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")
        self.assertIn("Security validation failed", res.explanation)

    def test_unconfirmed_repair_fails_closed(self) -> None:
        """Verify unconfirmed repair proposal fails closed without invoking tool."""
        proposal = PerformanceRepairProposal(
            tool_name="clean_user_temp_cache",
            arguments={"max_file_age_hours": 0.0, "dry_run": False},
        )
        res = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="session_unconf",
            user_confirmed=False,
        )
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")

    def test_successful_clean_temp_cache_verification_lifecycle(self) -> None:
        """Verify Before-State -> clean_user_temp_cache -> After-State -> 'verified' status."""
        session_repo = SessionRepository(self.db_manager)
        session_repo.create(session_id="sess_perf_01")

        proposal = PerformanceRepairProposal(
            tool_name="clean_user_temp_cache",
            arguments={"max_file_age_hours": 0.0, "dry_run": False},
            verification_tool="get_temp_storage_info",
        )

        # Mock handlers in registry
        clean_tool = self.registry.get("clean_user_temp_cache")
        temp_tool = self.registry.get("get_temp_storage_info")
        self.assertIsNotNone(clean_tool)
        self.assertIsNotNone(temp_tool)

        clean_tool.handler = lambda max_file_age_hours=0.0, dry_run=False: {
            "success": True,
            "data": {
                "deleted_files_count": 12,
                "freed_bytes": 10485760,
                "freed_formatted": "10.0 MB",
            },
        }
        temp_tool.handler = lambda: {
            "success": True,
            "data": {"total_temp_bytes": 0, "total_temp_files": 0},
        }

        result = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="sess_perf_01",
            user_confirmed=True,
        )

        self.assertTrue(result.repair_success)
        self.assertEqual(result.verification_status, "verified")
        self.assertIn("10.0 MB", result.explanation)

        # Verify solution persisted in SQLite
        solution_repo = SolutionRepository(self.db_manager)
        records = solution_repo.list_for_session("sess_perf_01")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["proposed_repair"], "clean_user_temp_cache")
        self.assertEqual(records[0]["verified_status"], "verified")

    def test_successful_process_termination_verification_lifecycle(self) -> None:
        """Verify Before-State -> terminate_user_process -> After-State -> 'verified' status."""
        session_repo = SessionRepository(self.db_manager)
        session_repo.create(session_id="sess_proc_01")

        proposal = PerformanceRepairProposal(
            tool_name="terminate_user_process",
            arguments={"pid": 9999, "process_name": "rogue_task.exe"},
            verification_tool="get_process_details",
        )

        term_tool = self.registry.get("terminate_user_process")
        proc_tool = self.registry.get("get_process_details")
        self.assertIsNotNone(term_tool)
        self.assertIsNotNone(proc_tool)

        # Mock termination success and after-state process not found
        term_tool.handler = lambda pid=9999, process_name=None: {
            "success": True,
            "data": {"pid": pid, "name": "rogue_task.exe", "terminated": True},
        }

        # Sequence: Before -> exists; After -> process not found
        call_count = {"val": 0}
        def mock_proc_details(pid: int):
            call_count["val"] += 1
            if call_count["val"] == 1:
                return {"success": True, "data": {"pid": pid, "name": "rogue_task.exe", "cpu_percent": 90.0}}
            return {"success": False, "error": {"code": "PROCESS_NOT_FOUND", "message": "Process terminated"}}

        proc_tool.handler = mock_proc_details

        result = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="sess_proc_01",
            user_confirmed=True,
        )

        self.assertTrue(result.repair_success)
        self.assertEqual(result.verification_status, "verified")
        self.assertIn("successfully terminated", result.explanation)


class TestPhase8SecurityAndStaticScan(unittest.TestCase):
    """Security scan verifying no shell or command execution exists in Phase 8 code."""

    def test_no_forbidden_execution_imports_in_performance_modules(self) -> None:
        """Verify performance modules contain no forbidden execution patterns."""
        forbidden_patterns = [
            "subprocess",
            "os.system",
            "os.popen",
            "shell=True",
            "eval(",
            "exec(",
        ]

        modules_to_scan = [
            "windows.performance_tools",
            "windows.performance_repairs",
            "agent.performance_diagnostics",
            "agent.performance_repairs_orchestrator",
        ]

        for mod_name in modules_to_scan:
            mod = __import__(mod_name, fromlist=["*"])
            src = inspect.getsource(mod)
            for forbidden in forbidden_patterns:
                self.assertNotIn(
                    forbidden,
                    src,
                    f"Forbidden execution pattern '{forbidden}' found in {mod_name}",
                )


if __name__ == "__main__":
    unittest.main()
