"""Comprehensive unit, safety, and verification tests for WinFix AI Phase 7 (Network Repairs + Verification).

Tests repair tool registration, user confirmation boundaries, cryptographic confirmation tokens,
before/after state captures, deterministic verification, and static security guarantees.
"""

import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.network_repairs_orchestrator import (
    NetworkRepairsOrchestrator,
    RepairExecutionResult,
    RepairProposal,
)
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from database.db import DatabaseManager
from database.repositories import SessionRepository, SolutionRepository, ToolExecutionRepository
import windows


class TestNetworkRepairRegistrationAndMetadata(unittest.TestCase):
    """Test suite verifying ToolRegistry metadata and constraints for Phase 7 repair tools."""

    def setUp(self) -> None:
        self.registry = create_default_registry()

    def test_flush_dns_cache_metadata(self) -> None:
        """Verify flush_dns_cache is registered with MEDIUM risk, not read-only, and has verification tool."""
        tool = self.registry.get("flush_dns_cache")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "flush_dns_cache")
        self.assertEqual(tool.domain, "network")
        self.assertEqual(tool.risk, RiskLevel.MEDIUM)
        self.assertFalse(tool.read_only)
        self.assertFalse(tool.automatic_allowed)
        self.assertEqual(tool.verification_tool, "check_dns_resolution")
        self.assertIsNotNone(tool.handler)
        self.assertTrue(callable(tool.handler))

    def test_renew_dhcp_lease_metadata(self) -> None:
        """Verify renew_dhcp_lease is registered with MEDIUM risk, admin requirement, and verification tool."""
        tool = self.registry.get("renew_dhcp_lease")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "renew_dhcp_lease")
        self.assertEqual(tool.domain, "network")
        self.assertEqual(tool.risk, RiskLevel.MEDIUM)
        self.assertFalse(tool.read_only)
        self.assertFalse(tool.automatic_allowed)
        self.assertTrue(tool.requires_admin)
        self.assertEqual(tool.verification_tool, "get_network_adapters_diagnostics")
        self.assertIsNotNone(tool.handler)
        self.assertTrue(callable(tool.handler))


class TestRepairConfirmationAndSafetyBoundaries(unittest.TestCase):
    """Test suite ensuring MEDIUM risk repairs fail closed without explicit user confirmation."""

    def setUp(self) -> None:
        self.registry = create_default_registry()
        self.safety_engine = SafetyEngine(registry=self.registry)
        self.orchestrator = NetworkRepairsOrchestrator(
            safety_engine=self.safety_engine,
            registry=self.registry,
        )

    def test_unconfirmed_repair_blocked_by_safety_engine(self) -> None:
        """Verify calling execute on flush_dns_cache without confirmation fails closed."""
        res = self.safety_engine.execute("flush_dns_cache", user_confirmed=False)
        self.assertFalse(res["success"])
        self.assertFalse(res["safety"]["allowed"])
        self.assertTrue(res["safety"]["requires_confirmation"])
        self.assertEqual(res["error"]["code"], "CONFIRMATION_REQUIRED")

    def test_confirmed_repair_allowed_by_safety_engine(self) -> None:
        """Verify calling execute with explicit user_confirmed=True allows handler invocation."""
        self.registry.get("flush_dns_cache").handler = lambda: {"success": True, "flushed": True}
        res = self.safety_engine.execute("flush_dns_cache", user_confirmed=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["safety"]["allowed"])
        self.assertEqual(res["risk"], "MEDIUM")

    def test_confirmation_token_binding_and_invalidation(self) -> None:
        """Verify confirmation tokens are cryptographically bound to tool, arguments, and session."""
        proposal = RepairProposal(
            tool_name="renew_dhcp_lease",
            arguments={"adapter_index": 1},
        )
        token = proposal.generate_confirmation_token("session_abc")
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

        # Same parameters -> matching token
        self.assertEqual(token, proposal.generate_confirmation_token("session_abc"))

        # Modified arguments -> mismatched token
        proposal_tampered = RepairProposal(
            tool_name="renew_dhcp_lease",
            arguments={"adapter_index": 2},
        )
        self.assertNotEqual(token, proposal_tampered.generate_confirmation_token("session_abc"))

        # Tampered token execution must be rejected
        res = self.orchestrator.execute_repair_with_verification(
            proposal=proposal_tampered,
            session_id="session_abc",
            user_confirmed=True,
            confirmation_token=token,
        )
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")
        self.assertIn("Security validation failed", res.explanation)


class TestNetworkRepairWorkflowAndVerification(unittest.TestCase):
    """Test suite for Before-State -> Repair -> After-State -> Verification state lifecycle."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_repairs.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db_manager = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db_manager.init_db()

        self.registry = create_default_registry()
        self.exec_repo = ToolExecutionRepository(self.db_manager)
        self.safety_engine = SafetyEngine(registry=self.registry, execution_repo=self.exec_repo)
        self.orchestrator = NetworkRepairsOrchestrator(
            safety_engine=self.safety_engine,
            registry=self.registry,
            db_mgr=self.db_manager,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_propose_repair_from_dns_symptoms(self) -> None:
        """Verify diagnostic DNS failure proposes flush_dns_cache."""
        proposal = self.orchestrator.propose_repair_from_diagnosis(
            problem_category="dns",
            observed_evidence=["DNS lookup for 'google.com' failed to resolve any IP addresses."],
        )
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.tool_name, "flush_dns_cache")
        self.assertEqual(proposal.verification_tool, "check_dns_resolution")

    def test_propose_repair_from_adapter_symptoms(self) -> None:
        """Verify missing IPv4 address proposes renew_dhcp_lease."""
        proposal = self.orchestrator.propose_repair_from_diagnosis(
            problem_category="ip_configuration",
            observed_evidence=["No active network adapters currently have an assigned IPv4 address."],
        )
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.tool_name, "renew_dhcp_lease")
        self.assertEqual(proposal.verification_tool, "get_network_adapters_diagnostics")

    def test_no_repair_proposed_when_diagnostics_normal(self) -> None:
        """Verify normal network diagnostics do not propose unwarranted repairs."""
        proposal = self.orchestrator.propose_repair_from_diagnosis(
            problem_category="connectivity",
            observed_evidence=["All network adapters and DNS working normally."],
        )
        self.assertIsNone(proposal)

    def test_flush_dns_successful_verification_lifecycle(self) -> None:
        """Verify Before-State -> flush_dns_cache -> After-State -> 'verified' status."""
        session_repo = SessionRepository(self.db_manager)
        session_repo.create(session_id="sess_dns_01")

        proposal = RepairProposal(
            tool_name="flush_dns_cache",
            arguments={},
            verification_tool="check_dns_resolution",
        )

        flush_tool = self.registry.get("flush_dns_cache")
        check_dns_tool = self.registry.get("check_dns_resolution")
        self.assertIsNotNone(flush_tool)
        self.assertIsNotNone(check_dns_tool)

        flush_tool.handler = lambda: {"success": True, "flushed": True}
        check_dns_tool.handler = lambda hostname="dns.google", timeout=3.0: {
            "success": True,
            "data": {"resolved": True, "resolved_ips": ["8.8.8.8"]},
        }

        result = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="sess_dns_01",
            user_confirmed=True,
        )

        self.assertTrue(result.repair_success)
        self.assertEqual(result.verification_status, "verified")
        self.assertIsNotNone(result.before_state)
        self.assertIsNotNone(result.after_state)

        # Verify solution record was saved in SQLite
        solution_repo = SolutionRepository(self.db_manager)
        records = solution_repo.list_for_session("sess_dns_01")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["proposed_repair"], "flush_dns_cache")
        self.assertEqual(records[0]["verified_status"], "verified")
        self.assertTrue(records[0]["repair_executed"])

    def test_failed_repair_does_not_loop_and_reports_failure(self) -> None:
        """Verify a failing repair operation stops safely and does not enter recursive repair loops."""
        proposal = RepairProposal(
            tool_name="flush_dns_cache",
            arguments={},
        )

        flush_tool = self.registry.get("flush_dns_cache")
        self.assertIsNotNone(flush_tool)
        flush_tool.handler = lambda: {
            "success": False,
            "error": {"code": "DLL_ERROR", "message": "Access Denied"},
        }

        result = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="sess_fail_01",
            user_confirmed=True,
        )

        self.assertFalse(result.repair_success)
        self.assertEqual(result.verification_status, "failed")
        self.assertIn("Repair action failed", result.explanation)


class TestPhase7SecurityAndStaticScan(unittest.TestCase):
    """Security scan verifying no command/shell execution exists in Phase 7 repair code."""

    def test_no_forbidden_execution_imports_in_network_repairs(self) -> None:
        """Verify windows/network_repairs.py and agent/network_repairs_orchestrator.py have no shell patterns."""
        forbidden_patterns = [
            "subprocess",
            "os.system",
            "os.popen",
            "shell=True",
            "eval(",
            "exec(",
        ]

        modules_to_scan = [
            "windows.network_repairs",
            "agent.network_repairs_orchestrator",
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
