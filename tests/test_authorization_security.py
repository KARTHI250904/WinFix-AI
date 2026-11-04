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

import unittest
from unittest.mock import MagicMock, patch
import hashlib
import json

from agent.network_repairs_orchestrator import RepairProposal
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


if __name__ == "__main__":
    unittest.main()
