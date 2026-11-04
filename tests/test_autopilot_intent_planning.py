"""Tests for Autopilot Intent Understanding and Plan Selection.

Verifies the separation of DOMAIN and USER INTENT, ensuring that read-only
intents (VIEW_HISTORY, CHECK_STATUS, DIAGNOSE, EXPLAIN) NEVER escalate
to MEDIUM repair operations or service restarts.
"""

import pytest
from agent.intent_classifier import UserIntent, default_intent_classifier
from agent.tool_metadata import RiskLevel
from agent.tool_registry import default_tool_registry
from modes.autopilot import AutopilotEngine
from modes.personal_tutor import _detect_domain_from_text


@pytest.fixture
def autopilot_engine():
    """Create fresh AutopilotEngine instance with default registry."""
    return AutopilotEngine(registry=default_tool_registry)


class TestIntentClassifier:
    """Test UserIntentClassifier on domain-independent intent detection."""

    def test_view_history_intent_windows_update(self):
        text = "How to view the previous failure Windows Update?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent == UserIntent.VIEW_HISTORY

    def test_diagnose_intent_windows_update(self):
        text = "Why did my Windows Update fail?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent == UserIntent.DIAGNOSE

    def test_repair_intent_windows_update(self):
        text = "Fix my Windows Update"
        intent = default_intent_classifier.classify_intent(text)
        assert intent == UserIntent.REPAIR

    def test_check_status_intent_windows_update(self):
        text = "Is Windows Update running?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent == UserIntent.CHECK_STATUS

    def test_view_history_intent_wifi(self):
        text = "Show me my previous Wi-Fi problems"
        intent = default_intent_classifier.classify_intent(text)
        assert intent in (UserIntent.VIEW_HISTORY, UserIntent.CHECK_STATUS)

    def test_diagnose_intent_wifi(self):
        text = "My Wi-Fi keeps disconnecting"
        intent = default_intent_classifier.classify_intent(text)
        assert intent == UserIntent.DIAGNOSE

    def test_view_wifi_adapter_info(self):
        text = "How do I see my Wi-Fi adapter information?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent in (UserIntent.VIEW_HISTORY, UserIntent.CHECK_STATUS)

    def test_diagnose_computer_slow(self):
        text = "Why is my computer slow?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent == UserIntent.DIAGNOSE

    def test_check_cpu_usage(self):
        text = "How do I see what is using my CPU?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent in (UserIntent.VIEW_HISTORY, UserIntent.CHECK_STATUS)

    def test_check_c_drive_space(self):
        text = "How can I see what's taking space on C drive?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent in (UserIntent.VIEW_HISTORY, UserIntent.CHECK_STATUS)

    def test_windows_update_failed_yesterday_why(self):
        text = "Windows Update failed yesterday. Why?"
        intent = default_intent_classifier.classify_intent(text)
        assert intent == UserIntent.DIAGNOSE


class TestAutopilotIntentPlanSelection:
    """Test Autopilot plan generation across all domains and intent combinations."""

    def test_case_1_view_previous_windows_update_failure(self, autopilot_engine):
        """Input: 'How to view the previous failure Windows Update?'
        Expected:
        - Domain: WINDOWS_UPDATE
        - Intent: VIEW_HISTORY
        - No MEDIUM repair
        - No restart operation
        """
        problem = "How to view the previous failure Windows Update?"
        domain = _detect_domain_from_text(problem)
        intent = default_intent_classifier.classify_intent(problem)

        assert domain == "windows_update"
        assert intent == UserIntent.VIEW_HISTORY

        plan = autopilot_engine.plan(problem_description=problem)

        assert len(plan.steps) >= 1
        tool_names = [s.tool_name for s in plan.steps]

        # Verify no repair tools present
        assert "restart_windows_update_service" not in tool_names
        assert "reset_windows_update" not in tool_names

        # Verify all proposed steps are strictly SAFE and read-only
        for step in plan.steps:
            assert step.risk_level == RiskLevel.SAFE.value
            assert not step.requires_confirmation
            tool_def = default_tool_registry.get(step.tool_name)
            assert tool_def is not None
            assert tool_def.read_only is True

    def test_case_2_why_did_windows_update_fail(self, autopilot_engine):
        """Input: 'Why did my Windows Update fail?'
        Expected:
        - Domain: WINDOWS_UPDATE
        - Intent: DIAGNOSE
        - Read-only diagnostics first
        - No restart operation
        """
        problem = "Why did my Windows Update fail?"
        domain = _detect_domain_from_text(problem)
        intent = default_intent_classifier.classify_intent(problem)

        assert domain == "windows_update"
        assert intent == UserIntent.DIAGNOSE

        plan = autopilot_engine.plan(problem_description=problem)

        tool_names = [s.tool_name for s in plan.steps]
        assert "restart_windows_update_service" not in tool_names
        assert "reset_windows_update" not in tool_names

        for step in plan.steps:
            assert step.risk_level == RiskLevel.SAFE.value
            assert not step.requires_confirmation

    def test_case_3_fix_windows_update(self, autopilot_engine):
        """Input: 'Fix my Windows Update'
        Expected:
        - Domain: WINDOWS_UPDATE
        - Intent: REPAIR
        - Proposes diagnostic steps + restart_windows_update_service with confirmation
        """
        problem = "Fix my Windows Update"
        domain = _detect_domain_from_text(problem)
        intent = default_intent_classifier.classify_intent(problem)

        assert domain == "windows_update"
        assert intent == UserIntent.REPAIR

        plan = autopilot_engine.plan(problem_description=problem)

        tool_names = [s.tool_name for s in plan.steps]
        assert "restart_windows_update_service" in tool_names

        # Verify the repair step requires confirmation and verification
        repair_steps = [s for s in plan.steps if s.tool_name == "restart_windows_update_service"]
        assert len(repair_steps) == 1
        assert repair_steps[0].requires_confirmation is True
        assert repair_steps[0].verification_required is True

    def test_case_4_is_windows_update_running(self, autopilot_engine):
        """Input: 'Is Windows Update running?'
        Expected:
        - Domain: WINDOWS_UPDATE
        - Intent: CHECK_STATUS
        - Read-only service/status inspection
        - No repair
        """
        problem = "Is Windows Update running?"
        domain = _detect_domain_from_text(problem)
        intent = default_intent_classifier.classify_intent(problem)

        assert domain == "windows_update"
        assert intent == UserIntent.CHECK_STATUS

        plan = autopilot_engine.plan(problem_description=problem)

        tool_names = [s.tool_name for s in plan.steps]
        assert "restart_windows_update_service" not in tool_names
        assert "get_windows_update_service_status" in tool_names

        for step in plan.steps:
            assert step.risk_level == RiskLevel.SAFE.value
            assert not step.requires_confirmation

    def test_case_5_show_previous_wifi_problems(self, autopilot_engine):
        """Input: 'Show me my previous Wi-Fi problems'
        Expected:
        - Domain: NETWORK
        - Intent: VIEW_HISTORY
        - Read-only, no repair
        """
        problem = "Show me my previous Wi-Fi problems"
        domain = _detect_domain_from_text(problem)
        intent = default_intent_classifier.classify_intent(problem)

        assert domain == "network"
        assert intent == UserIntent.VIEW_HISTORY

        plan = autopilot_engine.plan(problem_description=problem)

        tool_names = [s.tool_name for s in plan.steps]
        assert "flush_dns_cache" not in tool_names
        assert "reset_network_stack" not in tool_names

        for step in plan.steps:
            assert step.risk_level == RiskLevel.SAFE.value
            assert not step.requires_confirmation

    def test_storage_view_vs_repair(self, autopilot_engine):
        """Verify storage intent separation."""
        view_problem = "How can I see what's taking space on C drive?"
        plan_view = autopilot_engine.plan(problem_description=view_problem)
        view_tools = [s.tool_name for s in plan_view.steps]
        assert "clean_user_temp_cache" not in view_tools

        repair_problem = "Clean up temporary files on C drive"
        plan_repair = autopilot_engine.plan(problem_description=repair_problem)
        repair_tools = [s.tool_name for s in plan_repair.steps]
        assert "clean_user_temp_cache" in repair_tools

    def test_strict_read_only_intent_validation_enforcement(self, autopilot_engine):
        """Verify that validate_and_build_plan strictly rejects mutating tools for read-only intents."""
        raw_plan_with_repair = {
            "goal": "Invalid mutating plan for view intent",
            "steps": [
                {
                    "sequence": 1,
                    "tool_name": "get_windows_update_diagnostics",
                    "arguments": {},
                },
                {
                    "sequence": 2,
                    "tool_name": "restart_windows_update_service",
                    "arguments": {},
                },
            ],
        }

        with pytest.raises(ValueError, match="Mutating/repair tool.*strictly prohibited for read-only intent"):
            autopilot_engine.validate_and_build_plan(
                raw_plan=raw_plan_with_repair,
                session_id="test_sess",
                user_intent=UserIntent.VIEW_HISTORY,
            )
