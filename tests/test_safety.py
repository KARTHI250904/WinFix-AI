"""Comprehensive unit and security tests for WinFix AI Phase 4 Tool Registry and Safety Engine."""

import inspect
from pathlib import Path
import tempfile
import unittest

from agent.safety import SafetyEngine
from agent.tool_metadata import ParameterSpec, RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, create_default_registry
from database.db import DatabaseManager
from database.repositories import SessionRepository, ToolExecutionRepository


class TestToolRegistry(unittest.TestCase):
    """Test suite for ToolRegistry registration and query operations."""

    def setUp(self) -> None:
        self.registry = ToolRegistry()

    def test_register_and_get_tool(self) -> None:
        """Verify successful registration and retrieval of a valid tool."""
        tool = ToolDefinition(
            name="test_tool",
            domain="test",
            description="A test tool",
            risk=RiskLevel.SAFE,
            handler=lambda: {"success": True},
        )
        self.registry.register(tool)
        self.assertEqual(self.registry.count(), 1)
        fetched = self.registry.get("test_tool")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "test_tool")

    def test_reject_duplicate_tool(self) -> None:
        """Verify duplicate tool registration raises ValueError."""
        tool = ToolDefinition(
            name="dup_tool",
            domain="test",
            description="Duplicate tool",
            risk=RiskLevel.SAFE,
            handler=lambda: {"success": True},
        )
        self.registry.register(tool)
        with self.assertRaises(ValueError):
            self.registry.register(tool)

    def test_reject_invalid_metadata(self) -> None:
        """Verify registration rejects invalid metadata, missing handlers, or invalid risks."""
        # Missing name
        with self.assertRaises(ValueError):
            self.registry.register(
                ToolDefinition(
                    name="",
                    domain="test",
                    description="",
                    risk=RiskLevel.SAFE,
                    handler=lambda: {},
                )
            )

        # Non-callable handler
        with self.assertRaises(ValueError):
            self.registry.register(
                ToolDefinition(
                    name="bad_handler",
                    domain="test",
                    description="",
                    risk=RiskLevel.SAFE,
                    handler=None,
                )
            )

    def test_default_registry_contains_all_phase3_tools(self) -> None:
        """Verify the default registry pre-loads standard tools with correct risk classifications."""
        reg = create_default_registry()
        self.assertEqual(reg.count(), 37)

        # 29 Read-only diagnostic tools must be SAFE
        diagnostic_tools = [t for t in reg.list_tools() if t.read_only]
        self.assertEqual(len(diagnostic_tools), 29)
        for tool in diagnostic_tools:
            self.assertEqual(
                tool.risk,
                RiskLevel.SAFE,
                f"Diagnostic tool '{tool.name}' must have SAFE risk level",
            )
            self.assertTrue(
                tool.automatic_allowed,
                f"Diagnostic tool '{tool.name}' must have automatic_allowed=True",
            )
            self.assertIsNotNone(tool.handler)
            self.assertTrue(callable(tool.handler))

        # 8 Repair tools must be MEDIUM, not read-only, not auto-allowed, with verification tools
        repair_tools = [t for t in reg.list_tools() if not t.read_only]
        self.assertEqual(len(repair_tools), 8)
        for tool in repair_tools:
            self.assertEqual(tool.risk, RiskLevel.MEDIUM)
            self.assertFalse(tool.automatic_allowed)
            self.assertIsNotNone(tool.verification_tool)
            self.assertIsNotNone(tool.handler)
            self.assertTrue(callable(tool.handler))




class TestSafetyEngine(unittest.TestCase):
    """Test suite for SafetyEngine policy evaluation, argument validation, and execution."""

    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.safety_engine = SafetyEngine(registry=self.registry)

        # Register sample SAFE tool
        self.registry.register(
            ToolDefinition(
                name="safe_sample",
                domain="system",
                description="Safe sample diagnostic tool",
                risk=RiskLevel.SAFE,
                parameters={
                    "count": ParameterSpec(
                        name="count",
                        param_type=int,
                        required=False,
                        default=5,
                        min_value=1,
                        max_value=20,
                    ),
                    "target": ParameterSpec(
                        name="target",
                        param_type=str,
                        required=True,
                        max_value=100,
                    ),
                },
                handler=lambda count=5, target="": {"success": True, "count": count, "target": target},
            )
        )

        # Register sample MEDIUM tool (representing future repair capability)
        self.registry.register(
            ToolDefinition(
                name="medium_sample",
                domain="network",
                description="Medium sample repair tool",
                risk=RiskLevel.MEDIUM,
                requires_admin=True,
                read_only=False,
                handler=lambda: {"success": True, "repaired": True},
            )
        )

        # Register sample HIGH tool (representing blocked dangerous operation)
        self.registry.register(
            ToolDefinition(
                name="high_sample",
                domain="security",
                description="High sample destructive tool",
                risk=RiskLevel.HIGH,
                read_only=False,
                handler=lambda: {"success": False},
            )
        )

    # --- POLICY EVALUATION TESTS ---
    def test_safe_tool_evaluation(self) -> None:
        """Verify SAFE tools are permitted automatically without confirmation."""
        decision = self.safety_engine.evaluate("safe_sample", {"target": "example.com"})
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_confirmation)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.risk, "SAFE")
        self.assertEqual(decision.validated_arguments["count"], 5)
        self.assertEqual(decision.validated_arguments["target"], "example.com")

    def test_medium_tool_evaluation(self) -> None:
        """Verify MEDIUM tools require explicit confirmation before being allowed."""
        # Without confirmation
        unconfirmed = self.safety_engine.evaluate("medium_sample", user_confirmed=False)
        self.assertFalse(unconfirmed.allowed)
        self.assertTrue(unconfirmed.requires_confirmation)
        self.assertFalse(unconfirmed.blocked)
        self.assertEqual(unconfirmed.risk, "MEDIUM")

        # With confirmation
        confirmed = self.safety_engine.evaluate("medium_sample", user_confirmed=True)
        self.assertTrue(confirmed.allowed)
        self.assertFalse(confirmed.requires_confirmation)
        self.assertFalse(confirmed.blocked)

    def test_high_tool_evaluation(self) -> None:
        """Verify HIGH-risk tools are strictly blocked regardless of user confirmation."""
        blocked_unconfirmed = self.safety_engine.evaluate("high_sample", user_confirmed=False)
        self.assertFalse(blocked_unconfirmed.allowed)
        self.assertTrue(blocked_unconfirmed.blocked)
        self.assertEqual(blocked_unconfirmed.risk, "HIGH")

        blocked_confirmed = self.safety_engine.evaluate("high_sample", user_confirmed=True)
        self.assertFalse(blocked_confirmed.allowed)
        self.assertTrue(blocked_confirmed.blocked)

    def test_unknown_tool_evaluation(self) -> None:
        """Verify unknown or unregistered tools are rejected and fail closed."""
        decision = self.safety_engine.evaluate("unregistered_arbitrary_cmd")
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.blocked)
        self.assertIn("not registered", decision.reason)

    # --- STRICT ARGUMENT VALIDATION TESTS ---
    def test_missing_required_argument(self) -> None:
        """Verify missing required arguments fail closed."""
        decision = self.safety_engine.evaluate("safe_sample", {})
        self.assertFalse(decision.allowed)
        self.assertIn("is required", decision.reason)

    def test_unexpected_argument_rejected(self) -> None:
        """Verify unexpected arguments not in schema are rejected."""
        decision = self.safety_engine.evaluate(
            "safe_sample", {"target": "example.com", "malicious_extra": "payload"}
        )
        self.assertFalse(decision.allowed)
        self.assertIn("Unexpected argument", decision.reason)

    def test_argument_type_mismatch_rejected(self) -> None:
        """Verify invalid parameter types are rejected."""
        decision = self.safety_engine.evaluate(
            "safe_sample", {"target": "example.com", "count": "not_an_int"}
        )
        self.assertFalse(decision.allowed)
        self.assertIn("expected type", decision.reason)

    def test_numerical_bounds_validation(self) -> None:
        """Verify numbers outside min/max bounds are rejected."""
        # Below min
        below_min = self.safety_engine.evaluate("safe_sample", {"target": "ok", "count": 0})
        self.assertFalse(below_min.allowed)
        self.assertIn("below minimum", below_min.reason)

        # Above max
        above_max = self.safety_engine.evaluate("safe_sample", {"target": "ok", "count": 50})
        self.assertFalse(above_max.allowed)
        self.assertIn("exceeds maximum", above_max.reason)

    def test_command_injection_tokens_in_arguments_rejected(self) -> None:
        """Verify dangerous characters and command separators are blocked."""
        forbidden_payloads = [
            "google.com; rm -rf",
            "test.com && whoami",
            "server.net | powershell",
            "host.com `calc.exe`",
            "host.com\nmalicious",
        ]
        for payload in forbidden_payloads:
            decision = self.safety_engine.evaluate("safe_sample", {"target": payload})
            self.assertFalse(
                decision.allowed,
                f"Payload '{payload}' was not blocked by argument sanitizer",
            )
            self.assertIn("forbidden character", decision.reason)

    # --- EXECUTION BOUNDARY TESTS ---
    def test_safe_execution(self) -> None:
        """Verify valid SAFE tool executes and returns structured output."""
        res = self.safety_engine.execute("safe_sample", {"target": "test.local", "count": 10})
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "safe_sample")
        self.assertEqual(res["risk"], "SAFE")
        self.assertEqual(res["data"]["count"], 10)
        self.assertEqual(res["data"]["target"], "test.local")
        self.assertTrue(res["safety"]["allowed"])

    def test_blocked_execution_fails_closed(self) -> None:
        """Verify blocked tools do not invoke handlers."""
        res = self.safety_engine.execute("high_sample")
        self.assertFalse(res["success"])
        self.assertFalse(res["safety"]["allowed"])
        self.assertTrue(res["safety"]["blocked"])
        self.assertEqual(res["error"]["code"], "SAFETY_BLOCKED")

    def test_unconfirmed_medium_execution_fails_closed(self) -> None:
        """Verify unconfirmed MEDIUM tools do not execute."""
        res = self.safety_engine.execute("medium_sample", user_confirmed=False)
        self.assertFalse(res["success"])
        self.assertFalse(res["safety"]["allowed"])
        self.assertTrue(res["safety"]["requires_confirmation"])
        self.assertEqual(res["error"]["code"], "CONFIRMATION_REQUIRED")

    def test_confirmed_medium_execution_allowed(self) -> None:
        """Verify confirmed MEDIUM tools execute properly."""
        res = self.safety_engine.execute("medium_sample", user_confirmed=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["safety"]["allowed"])
        self.assertEqual(res["risk"], "MEDIUM")
        self.assertTrue(res["data"]["repaired"])


class TestSafetyAuditAndSecurityGuarantees(unittest.TestCase):
    """Test suite verifying SQLite audit logging and absence of arbitrary execution patterns."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_audit.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db_manager = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db_manager.init_db()

        self.session_repo = SessionRepository(self.db_manager)
        self.exec_repo = ToolExecutionRepository(self.db_manager)

        self.registry = create_default_registry()
        self.safety_engine = SafetyEngine(registry=self.registry, execution_repo=self.exec_repo)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_audit_logging_on_execution(self) -> None:
        """Verify allowed tool execution creates an audit entry in SQLite."""
        session = self.session_repo.create(session_id="sess_audit_01")
        res = self.safety_engine.execute(
            tool_name="get_memory_diagnostics",
            session_id="sess_audit_01",
        )
        self.assertTrue(res["success"])

        logs = self.exec_repo.list_for_session("sess_audit_01")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["tool_name"], "get_memory_diagnostics")
        self.assertTrue(logs[0]["success"])
        self.assertEqual(logs[0]["risk_level"], "SAFE")

    def test_audit_logging_on_blocked_tool(self) -> None:
        """Verify safety rejection creates an audit failure log in SQLite."""
        self.session_repo.create(session_id="sess_audit_02")
        res = self.safety_engine.execute(
            tool_name="unregistered_tool",
            session_id="sess_audit_02",
        )
        self.assertFalse(res["success"])

        logs = self.exec_repo.list_for_session("sess_audit_02")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["tool_name"], "unregistered_tool")
        self.assertFalse(logs[0]["success"])

    def test_no_forbidden_execution_imports_in_agent_package(self) -> None:
        """Verify no agent module imports subprocess, os.system, eval, or exec."""
        forbidden_patterns = ["subprocess", "os.system", "os.popen", "shell=True", "eval(", "exec("]

        agent_modules = [
            "agent.tool_metadata",
            "agent.tool_registry",
            "agent.safety",
            "agent",
        ]

        for mod_name in agent_modules:
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
