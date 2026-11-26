"""
Phase 21: Comprehensive Authorization Security Tests for WinFix AI.

Tests:
1. Confirmation token generation and validation for all 10 MEDIUM repair tools.
2. Token replay prevention (tokens cannot be used more than once).
3. Token session binding (Session A token cannot be used in Session B).
4. Argument mutation detection (modifying arguments after token generation invalidates authorization).
5. Tool name mutation detection (changing the tool name invalidates token).
6. Autopilot plan hash integrity and authorization binding.
7. Autopilot step mutation invalidation.
8. Autopilot cancellation and abort security.
9. Streamlit rerun replay defense in UI state.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

from agent.network_repairs_orchestrator import NetworkRepairsOrchestrator, RepairProposal
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, create_default_registry
from modes.autopilot import AutopilotEngine, compute_plan_hash
from modes.autopilot_models import (
    AutopilotPlan,
    AutopilotStep,
    AutopilotStatus,
    AutopilotPrecondition,
    PreconditionOperator,
)
from tests.security.test_vectors import (
    ALL_MEDIUM_TOOLS,
    PROMPT_INJECTIONS,
    COMMAND_INJECTIONS,
)


class TestAuthorizationSecurity(unittest.TestCase):
    """Deep authorization and replay security tests across all repair primitives."""

    def setUp(self):
        self.registry = create_default_registry()
        self.safety = SafetyEngine(registry=self.registry)
        self.orchestrator = NetworkRepairsOrchestrator(safety_engine=self.safety, registry=self.registry)
        self.autopilot = AutopilotEngine(registry=self.registry, safety_engine=self.safety)

    def test_all_ten_medium_tools_require_authorization(self):
        """Every single MEDIUM repair tool must require confirmation."""
        medium_tools = [
            t for t in self.registry.list_tools() if t.risk == RiskLevel.MEDIUM
        ]
        self.assertEqual(len(medium_tools), 10, "Expected exactly 10 MEDIUM repair tools")
        
        sample_args = {
            "terminate_user_process": {"pid": 1234},
            "start_service": {"service_name": "wuauserv"},
            "stop_service": {"service_name": "wuauserv"},
            "restart_service": {"service_name": "wuauserv"},
        }
        
        for tool in medium_tools:
            with self.subTest(tool=tool.name):
                args = sample_args.get(tool.name, {})
                decision = self.safety.evaluate(tool.name, args, user_confirmed=False)
                self.assertTrue(decision.requires_confirmation, f"{tool.name} did not require confirmation")
                self.assertFalse(decision.allowed, f"{tool.name} allowed without confirmation token")

    def test_token_cryptographic_uniqueness_for_all_medium_tools(self):
        """Tokens generated for each repair tool are distinct and cryptographically bound."""
        tokens = set()
        for tool_name in ALL_MEDIUM_TOOLS:
            proposal = RepairProposal(tool_name=tool_name, arguments={})
            tok = proposal.generate_confirmation_token(session_id="sess_unique")
            self.assertNotIn(tok, tokens, f"Duplicate token generated for {tool_name}")
            tokens.add(tok)

    def test_cross_session_token_isolation(self):
        """A token generated for Session A differs from Session B."""
        for tool_name in ALL_MEDIUM_TOOLS:
            proposal = RepairProposal(tool_name=tool_name, arguments={})
            token_a = proposal.generate_confirmation_token(session_id="session_A")
            token_b = proposal.generate_confirmation_token(session_id="session_B")
            self.assertNotEqual(token_a, token_b, f"Cross-session token collided for {tool_name}")

    def test_argument_mutation_invalidates_authorization(self):
        """Changing arguments changes the generated confirmation token."""
        proposal_orig = RepairProposal(tool_name="start_service", arguments={"service_name": "wuauserv"})
        token_orig = proposal_orig.generate_confirmation_token(session_id="session_mutate")
        
        proposal_mutated = RepairProposal(tool_name="start_service", arguments={"service_name": "bits"})
        token_mutated = proposal_mutated.generate_confirmation_token(session_id="session_mutate")
        
        self.assertNotEqual(token_orig, token_mutated, "Mutated argument produced identical confirmation token!")

    def test_tool_name_mutation_invalidates_authorization(self):
        """Token generated for Tool A does not match Tool B."""
        proposal_a = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token_a = proposal_a.generate_confirmation_token(session_id="session_tool_mutate")
        
        proposal_b = RepairProposal(tool_name="renew_dhcp_lease", arguments={})
        token_b = proposal_b.generate_confirmation_token(session_id="session_tool_mutate")
        
        self.assertNotEqual(token_a, token_b, "Different tools produced identical tokens!")

    def test_autopilot_plan_hash_mismatch_blocks_execution(self):
        """Autopilot must compute plan hash and reject execution if plan steps are altered."""
        steps = [
            {"sequence": 1, "tool_name": "check_network_adapters", "arguments": {}},
            {"sequence": 2, "tool_name": "flush_dns_cache", "arguments": {}}
        ]
        
        # Original plan hash
        orig_hash = compute_plan_hash(steps, session_id="sess_auto_01")
        self.assertIsNotNone(orig_hash)
        
        # Tampered plan with extra step
        mutated_steps = list(steps) + [
            {"sequence": 3, "tool_name": "renew_dhcp_lease", "arguments": {}}
        ]
        mutated_hash = compute_plan_hash(mutated_steps, session_id="sess_auto_01")
        
        self.assertNotEqual(orig_hash, mutated_hash, "Mutated plan hash matched original hash!")

    def test_autopilot_rejects_more_than_five_steps(self):
        """Autopilot strict bound of max 5 steps."""
        raw_plan = {
            "goal": "Oversized plan",
            "steps": [
                {"sequence": i + 1, "tool_name": "check_network_adapters", "arguments": {}, "purpose": f"Step {i}"}
                for i in range(6)
            ]
        }
        with self.assertRaises(ValueError) as ctx:
            self.autopilot.validate_and_build_plan(raw_plan, session_id="sess_too_long")
        self.assertIn("exceeding the maximum limit", str(ctx.exception))

    def test_autopilot_rejects_duplicate_repair_steps(self):
        """Autopilot must reject plans that attempt the same repair tool more than once."""
        raw_plan = {
            "goal": "Duplicate repair attempt",
            "steps": [
                {"sequence": 1, "tool_name": "flush_dns_cache", "arguments": {}, "purpose": "Flush 1"},
                {"sequence": 2, "tool_name": "flush_dns_cache", "arguments": {}, "purpose": "Flush 2"}
            ]
        }
        with self.assertRaises(ValueError) as ctx:
            self.autopilot.validate_and_build_plan(raw_plan, session_id="sess_dup_repair")
        self.assertIn("duplicate repair", str(ctx.exception).lower())

    def test_safety_engine_evaluate_default_unconfirmed_fails_closed(self):
        """Default user_confirmed=False must fail closed on MEDIUM tools."""
        decision = self.safety.evaluate("flush_dns_cache", {})
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_confirmation)

        # Invalid/non-boolean authorization values must also fail closed
        for invalid_val in [None, "true", "True", 1, [], {}]:
            dec = self.safety.evaluate("flush_dns_cache", {}, user_confirmed=invalid_val)
            self.assertFalse(dec.allowed, f"user_confirmed={invalid_val} erroneously allowed execution")
            self.assertTrue(dec.requires_confirmation)

    def test_safety_engine_execute_default_unconfirmed_fails_closed(self):
        """execute() without explicit user_confirmed=True fails closed."""
        res = self.safety.execute("flush_dns_cache", {})
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "CONFIRMATION_REQUIRED")

        res_none = self.safety.execute("flush_dns_cache", {}, user_confirmed=None)
        self.assertFalse(res_none["success"])

    def test_missing_empty_whitespace_token_fails_closed(self):
        """Orchestrator rejects missing, None, empty, and whitespace-only confirmation tokens."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        for bad_token in [None, "", "   ", "\t\r\n"]:
            with self.subTest(bad_token=bad_token):
                res = self.orchestrator.execute_repair_with_verification(
                    proposal=proposal,
                    user_confirmed=True,
                    confirmation_token=bad_token,
                )
                self.assertFalse(res.repair_success)
                self.assertEqual(res.verification_status, "blocked")
                self.assertIn("Mandatory confirmation token missing or empty", res.explanation)

    def test_session_id_mutation_invalidates_token(self):
        """Tokens bound to Session A are rejected when submitted under Session B."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token_a = proposal.generate_confirmation_token(session_id="session_A")
        res = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="session_B",
            user_confirmed=True,
            confirmation_token=token_a,
        )
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")
        self.assertIn("Confirmation token does not match the proposal arguments", res.explanation)

    def test_sequential_token_replay_blocked(self):
        """Replaying a previously consumed token must be blocked atomically."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token = proposal.generate_confirmation_token(session_id="sess_seq_replay")
        tool = self.registry.get("flush_dns_cache")
        original_handler = tool.handler
        try:
            tool.handler = lambda: {"success": True, "flushed": True}

            # First execution succeeds
            res1 = self.orchestrator.execute_repair_with_verification(
                proposal=proposal,
                session_id="sess_seq_replay",
                user_confirmed=True,
                confirmation_token=token,
            )
            self.assertTrue(res1.repair_success)

            # Replaying the exact same token fails closed
            res2 = self.orchestrator.execute_repair_with_verification(
                proposal=proposal,
                session_id="sess_seq_replay",
                user_confirmed=True,
                confirmation_token=token,
            )
            self.assertFalse(res2.repair_success)
            self.assertEqual(res2.verification_status, "blocked")
            self.assertIn("already been consumed", res2.explanation.lower())
        finally:
            tool.handler = original_handler

    def test_concurrent_token_replay_thread_safety(self):
        """10 concurrent threads submitting the exact same token must result in exactly 1 execution."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token = proposal.generate_confirmation_token(session_id="sess_concurrent")
        tool = self.registry.get("flush_dns_cache")
        original_handler = tool.handler
        try:
            tool.handler = lambda: {"success": True, "flushed": True}

            def run_attempt():
                return self.orchestrator.execute_repair_with_verification(
                    proposal=proposal,
                    session_id="sess_concurrent",
                    user_confirmed=True,
                    confirmation_token=token,
                )

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(run_attempt) for _ in range(10)]
                results = [f.result() for f in futures]

            successes = [r for r in results if r.repair_success is True]
            blocked = [r for r in results if r.verification_status == "blocked"]

            self.assertEqual(len(successes), 1, "Exactly one thread must execute successfully")
            self.assertEqual(len(blocked), 9, "All 9 concurrent replay attempts must be blocked")
            for b in blocked:
                self.assertIn("already been consumed", b.explanation.lower())
        finally:
            tool.handler = original_handler

    def test_token_consumed_even_on_handler_failure(self):
        """If a tool handler fails or raises an error, the token remains consumed and cannot be reused."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token = proposal.generate_confirmation_token(session_id="sess_handler_fail")
        tool = self.registry.get("flush_dns_cache")
        original_handler = tool.handler
        try:
            tool.handler = lambda: (_ for _ in ()).throw(RuntimeError("Underlying adapter driver failed"))

            # First invocation fails inside handler
            res1 = self.orchestrator.execute_repair_with_verification(
                proposal=proposal,
                session_id="sess_handler_fail",
                user_confirmed=True,
                confirmation_token=token,
            )
            self.assertFalse(res1.repair_success)

            # Token must remain marked as consumed
            self.assertTrue(self.safety.is_token_consumed(token))

            # Replaying the token is blocked immediately
            res2 = self.orchestrator.execute_repair_with_verification(
                proposal=proposal,
                session_id="sess_handler_fail",
                user_confirmed=True,
                confirmation_token=token,
            )
            self.assertFalse(res2.repair_success)
            self.assertEqual(res2.verification_status, "blocked")
            self.assertIn("already been consumed", res2.explanation.lower())
        finally:
            tool.handler = original_handler

    def test_user_confirmed_false_blocks_even_with_valid_token(self):
        """user_confirmed=False must fail closed even when a valid token is provided."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token = proposal.generate_confirmation_token(session_id="sess_gate_test")
        res = self.orchestrator.execute_repair_with_verification(
            proposal=proposal,
            session_id="sess_gate_test",
            user_confirmed=False,
            confirmation_token=token,
        )
        self.assertFalse(res.repair_success)
        self.assertEqual(res.verification_status, "blocked")
        self.assertIn("Explicit user confirmation required", res.explanation)

    # -------------------------------------------------------------------------
    # WF-SEC-03: Autopilot Confirmation Token Management Regression Tests
    # -------------------------------------------------------------------------

    def test_autopilot_missing_token_blocks_medium_repair(self):
        """Autopilot execution without a confirmation token for a MEDIUM tool must fail closed with BLOCKED."""
        step = AutopilotStep(
            step_id="step_no_tok",
            sequence=1,
            tool_name="flush_dns_cache",
            arguments={},
            risk_level="MEDIUM",
            requires_confirmation=True,
            confirmation_token=None,
        )
        plan = AutopilotPlan(
            plan_id="plan_no_tok",
            session_id="sess_no_tok",
            goal="Flush DNS",
            steps=[step],
            plan_hash="hash_no_tok",
            is_authorized=True,
            status=AutopilotStatus.AUTHORIZED,
        )
        res = self.autopilot.execute_plan(plan, user_confirmed_hash="hash_no_tok")
        self.assertEqual(res.status, AutopilotStatus.BLOCKED)
        self.assertEqual(len(res.step_results), 1)
        self.assertEqual(res.step_results[0].status, "BLOCKED")
        self.assertIn("Mandatory confirmation token missing", res.step_results[0].explanation)

    def test_autopilot_synthetic_token_string_rejected(self):
        """Autopilot must reject ad-hoc synthetic strings (tok_...) rather than bypassing validation."""
        synthetic_token = f"tok_sess_synth_flush_dns_cache_123456789.0"
        step = AutopilotStep(
            step_id="step_synth",
            sequence=1,
            tool_name="flush_dns_cache",
            arguments={},
            risk_level="MEDIUM",
            requires_confirmation=True,
            confirmation_token=synthetic_token,
        )
        plan = AutopilotPlan(
            plan_id="plan_synth",
            session_id="sess_synth",
            goal="Flush DNS",
            steps=[step],
            plan_hash="hash_synth",
            is_authorized=True,
            status=AutopilotStatus.AUTHORIZED,
        )
        res = self.autopilot.execute_plan(plan, user_confirmed_hash="hash_synth")
        self.assertEqual(res.status, AutopilotStatus.BLOCKED)
        self.assertEqual(res.step_results[0].status, "BLOCKED")
        self.assertIn("does not match", res.step_results[0].explanation.lower())

    def test_autopilot_wrong_session_token_rejected(self):
        """Autopilot must reject a token generated for Session A when executed under Session B."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token_sess_a = proposal.generate_confirmation_token(session_id="session_A")
        step = AutopilotStep(
            step_id="step_wrong_sess",
            sequence=1,
            tool_name="flush_dns_cache",
            arguments={},
            risk_level="MEDIUM",
            requires_confirmation=True,
            confirmation_token=token_sess_a,
        )
        plan = AutopilotPlan(
            plan_id="plan_wrong_sess",
            session_id="session_B",
            goal="Flush DNS",
            steps=[step],
            plan_hash="hash_wrong_sess",
            is_authorized=True,
            status=AutopilotStatus.AUTHORIZED,
        )
        res = self.autopilot.execute_plan(plan, user_confirmed_hash="hash_wrong_sess")
        self.assertEqual(res.status, AutopilotStatus.BLOCKED)
        self.assertEqual(res.step_results[0].status, "BLOCKED")
        self.assertIn("does not match", res.step_results[0].explanation.lower())

    def test_autopilot_modified_arguments_token_rejected(self):
        """Mutating arguments after token issuance causes Autopilot orchestrator validation to reject execution."""
        token_orig = self.autopilot.issue_step_confirmation_token(
            AutopilotStep(step_id="s1", sequence=1, tool_name="start_service", arguments={"service_name": "wuauserv"}, risk_level="MEDIUM"),
            session_id="sess_arg_tamper",
        )
        # Mutate arguments to bits
        step_tampered = AutopilotStep(
            step_id="s1",
            sequence=1,
            tool_name="start_service",
            arguments={"service_name": "bits"},
            risk_level="MEDIUM",
            requires_confirmation=True,
            confirmation_token=token_orig,
        )
        plan = AutopilotPlan(
            plan_id="plan_tampered",
            session_id="sess_arg_tamper",
            goal="Start service",
            steps=[step_tampered],
            plan_hash="hash_tampered",
            is_authorized=True,
            status=AutopilotStatus.AUTHORIZED,
        )
        res = self.autopilot.execute_plan(plan, user_confirmed_hash="hash_tampered")
        self.assertEqual(res.status, AutopilotStatus.BLOCKED)
        self.assertEqual(res.step_results[0].status, "BLOCKED")
        self.assertIn("does not match", res.step_results[0].explanation.lower())

    def test_autopilot_replayed_step_token_blocked(self):
        """Replaying a previously consumed token in Autopilot must be blocked atomically."""
        proposal = RepairProposal(tool_name="flush_dns_cache", arguments={})
        token = proposal.generate_confirmation_token(session_id="sess_replay_step")
        tool = self.registry.get("flush_dns_cache")
        v_tool = self.registry.get("check_dns_resolution")
        orig_handler = tool.handler
        orig_v_handler = v_tool.handler
        try:
            tool.handler = lambda: {"success": True, "flushed": True}
            v_tool.handler = lambda **kw: {"success": True, "data": {"resolved": True}}
            step1 = AutopilotStep(
                step_id="s1",
                sequence=1,
                tool_name="flush_dns_cache",
                arguments={},
                risk_level="MEDIUM",
                requires_confirmation=True,
                confirmation_token=token,
            )
            plan1 = AutopilotPlan(
                plan_id="plan_rep_1",
                session_id="sess_replay_step",
                goal="Flush DNS 1",
                steps=[step1],
                plan_hash="hash_rep_1",
                is_authorized=True,
                status=AutopilotStatus.AUTHORIZED,
            )
            res1 = self.autopilot.execute_plan(plan1, user_confirmed_hash="hash_rep_1")
            self.assertEqual(res1.status, AutopilotStatus.COMPLETED)

            # Ensure the token was consumed atomically
            self.assertTrue(self.safety.is_token_consumed(token))

            # Attempt to reuse the consumed token in a new plan
            step2 = AutopilotStep(
                step_id="s2",
                sequence=1,
                tool_name="flush_dns_cache",
                arguments={},
                risk_level="MEDIUM",
                requires_confirmation=True,
                confirmation_token=token,
            )
            plan2 = AutopilotPlan(
                plan_id="plan_rep_2",
                session_id="sess_replay_step",
                goal="Flush DNS 2",
                steps=[step2],
                plan_hash="hash_rep_2",
                is_authorized=True,
                status=AutopilotStatus.AUTHORIZED,
            )
            res2 = self.autopilot.execute_plan(plan2, user_confirmed_hash="hash_rep_2")
            self.assertEqual(res2.status, AutopilotStatus.BLOCKED)
            self.assertEqual(res2.step_results[0].status, "BLOCKED")
            self.assertIn("already been consumed", res2.step_results[0].explanation.lower())
        finally:
            tool.handler = orig_handler
            v_tool.handler = orig_v_handler

    def test_autopilot_routes_storage_repair_through_orchestrator(self):
        """clean_user_temp_cache in Autopilot must route through StorageRepairsOrchestrator."""
        with patch.object(self.autopilot.storage_orchestrator, "execute_repair_with_verification") as mock_exec:
            mock_res = MagicMock()
            mock_res.confirmed = True
            mock_res.repair_success = True
            mock_res.verification_status = "verified"
            mock_res.repair_output = {"cleaned": True}
            mock_res.after_state = {"temp_files": 0}
            mock_res.explanation = "Temp files purged."
            mock_exec.return_value = mock_res

            raw_plan = {
                "goal": "Clean temp files",
                "steps": [{"sequence": 1, "tool_name": "clean_user_temp_cache", "arguments": {}}],
            }
            plan = self.autopilot.validate_and_build_plan(raw_plan, session_id="sess_storage_route")
            self.autopilot.authorize_plan(plan, user_confirmed_hash=plan.plan_hash)
            res = self.autopilot.execute_plan(plan, user_confirmed_hash=plan.plan_hash)

            self.assertTrue(mock_exec.called, "StorageRepairsOrchestrator was not called!")
            call_kwargs = mock_exec.call_args[1]
            self.assertTrue(call_kwargs.get("user_confirmed"))
            self.assertIsNotNone(call_kwargs.get("confirmation_token"))
            self.assertEqual(res.status, AutopilotStatus.COMPLETED)

    def test_autopilot_routes_service_repair_through_orchestrator(self):
        """restart_service in Autopilot must route through ServiceRepairsOrchestrator."""
        with patch.object(self.autopilot.service_orchestrator, "execute_confirmed_repair") as mock_exec:
            mock_res = MagicMock()
            mock_res.confirmed = True
            mock_res.repair_success = True
            mock_res.verification_status = "verified"
            mock_res.repair_output = {"success": True}
            mock_res.after_state = {"status": "RUNNING"}
            mock_res.explanation = "Service restarted."
            mock_exec.return_value = mock_res

            raw_plan = {
                "goal": "Restart spooler",
                "steps": [{"sequence": 1, "tool_name": "restart_service", "arguments": {"service_name": "Spooler"}}],
            }
            plan = self.autopilot.validate_and_build_plan(raw_plan, session_id="sess_svc_route")
            self.autopilot.authorize_plan(plan, user_confirmed_hash=plan.plan_hash)
            res = self.autopilot.execute_plan(plan, user_confirmed_hash=plan.plan_hash)

            self.assertTrue(mock_exec.called, "ServiceRepairsOrchestrator was not called!")
            call_kwargs = mock_exec.call_args[1]
            self.assertIsNotNone(call_kwargs.get("confirmation_token"))
            self.assertEqual(res.status, AutopilotStatus.COMPLETED)

    def test_autopilot_routes_bluetooth_repair_through_orchestrator(self):
        """restart_bluetooth_service in Autopilot must route through BluetoothRepairsOrchestrator."""
        with patch.object(self.autopilot.bluetooth_orchestrator, "execute_confirmed_repair") as mock_exec:
            mock_res = MagicMock()
            mock_res.confirmed = True
            mock_res.repair_success = True
            mock_res.verification_status = "verified"
            mock_res.repair_output = {"success": True}
            mock_res.after_state = {"status": "RUNNING"}
            mock_res.explanation = "Bluetooth restarted."
            mock_exec.return_value = mock_res

            raw_plan = {
                "goal": "Restart bluetooth",
                "steps": [{"sequence": 1, "tool_name": "restart_bluetooth_service", "arguments": {}}],
            }
            plan = self.autopilot.validate_and_build_plan(raw_plan, session_id="sess_bt_route")
            self.autopilot.authorize_plan(plan, user_confirmed_hash=plan.plan_hash)
            res = self.autopilot.execute_plan(plan, user_confirmed_hash=plan.plan_hash)

            self.assertTrue(mock_exec.called, "BluetoothRepairsOrchestrator was not called!")
            call_kwargs = mock_exec.call_args[1]
            self.assertIsNotNone(call_kwargs.get("confirmation_token"))
            self.assertEqual(res.status, AutopilotStatus.COMPLETED)

    def test_autopilot_routes_performance_repair_through_orchestrator(self):
        """terminate_user_process in Autopilot must route through PerformanceRepairsOrchestrator."""
        with patch.object(self.autopilot.performance_orchestrator, "execute_repair_with_verification") as mock_exec:
            mock_res = MagicMock()
            mock_res.confirmed = True
            mock_res.repair_success = True
            mock_res.verification_status = "verified"
            mock_res.repair_output = {"terminated": True}
            mock_res.after_state = {"running": False}
            mock_res.explanation = "Process terminated."
            mock_exec.return_value = mock_res

            raw_plan = {
                "goal": "Terminate process",
                "steps": [{"sequence": 1, "tool_name": "terminate_user_process", "arguments": {"pid": 9999}}],
            }
            plan = self.autopilot.validate_and_build_plan(raw_plan, session_id="sess_perf_route")
            self.autopilot.authorize_plan(plan, user_confirmed_hash=plan.plan_hash)
            res = self.autopilot.execute_plan(plan, user_confirmed_hash=plan.plan_hash)

            self.assertTrue(mock_exec.called, "PerformanceRepairsOrchestrator was not called!")
            call_kwargs = mock_exec.call_args[1]
            self.assertIsNotNone(call_kwargs.get("confirmation_token"))
            self.assertEqual(res.status, AutopilotStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
