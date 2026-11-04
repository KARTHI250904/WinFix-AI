"""Comprehensive test suite for WinFix AI Phase 35 — UX, Accessibility & Human Usability Finalization.

Verifies:
- Standardized user-facing terminology and calm presentation mapping
- Deterministic confidence mapping without false precision
- Standardized diagnosis, repair proposal, verification, recovery, and tutor cards
- Non-color-only accessibility indicators, high-contrast badges, and diff tables
- Welcome guide, recovery flows, and state invalidation
- UI security boundary and AST static security scans (0 prohibited execution calls)
Strictly adheres to: LLM != Windows Shell and UI != Execution Layer.
"""

import ast
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from agent.tool_metadata import RiskLevel, ToolDefinition
from database.knowledge_models import KnowledgeArticle, KnowledgeCategory, KnowledgeSeverity
from ui.accessibility import (
    accessible_button_label,
    accessible_status_indicator,
    format_accessible_bullet_list,
    format_accessible_diff,
    format_accessible_table,
)
from ui.formatting import (
    ConfidenceLevel,
    format_bytes,
    format_human_verification_status,
    format_progress_step,
    format_risk_badge,
    format_severity_badge,
    format_status_badge,
    format_timestamp,
    format_tool_name,
    format_user_friendly_terminology,
    map_confidence,
    truncate_text_safely,
)
from ui.state import AppMode, MODE_DESCRIPTIONS, UIStateManager, UIStatusState


class TestPhase35ConfidenceMapping(unittest.TestCase):
    """Test suite for deterministic, evidence-grounded confidence presentation (Phase 35)."""

    def test_high_confidence_with_sufficient_evidence(self) -> None:
        """High confidence requires >= 3 verified evidence items and confirmed status."""
        conf = map_confidence(evidence_count=3, contradictions_found=False, is_uncertain=False, hypothesis_status="CONFIRMED")
        self.assertEqual(conf, ConfidenceLevel.HIGH.value)

    def test_moderate_confidence_with_partial_evidence(self) -> None:
        """Moderate confidence when 1 or 2 evidence items are verified."""
        conf1 = map_confidence(evidence_count=1, contradictions_found=False, is_uncertain=False, hypothesis_status="SUPPORTED")
        conf2 = map_confidence(evidence_count=2, contradictions_found=False, is_uncertain=False, hypothesis_status="SUPPORTED")
        self.assertEqual(conf1, ConfidenceLevel.MODERATE.value)
        self.assertEqual(conf2, ConfidenceLevel.MODERATE.value)

    def test_unknown_confidence_when_no_evidence(self) -> None:
        """Zero evidence yields 'Not enough information'."""
        conf = map_confidence(evidence_count=0, contradictions_found=False, is_uncertain=False)
        self.assertEqual(conf, ConfidenceLevel.UNKNOWN.value)

    def test_low_confidence_on_contradiction(self) -> None:
        """Contradiction forces low confidence regardless of evidence count."""
        conf = map_confidence(evidence_count=5, contradictions_found=True, is_uncertain=False)
        self.assertEqual(conf, ConfidenceLevel.LOW.value)

    def test_unknown_confidence_on_contradiction_with_zero_evidence(self) -> None:
        """Contradiction with zero evidence returns 'Not enough information'."""
        conf = map_confidence(evidence_count=0, contradictions_found=True, is_uncertain=False)
        self.assertEqual(conf, ConfidenceLevel.UNKNOWN.value)

    def test_low_confidence_when_uncertain(self) -> None:
        """Explicit uncertainty notes reduce confidence to low."""
        conf = map_confidence(evidence_count=4, contradictions_found=False, is_uncertain=True)
        self.assertEqual(conf, ConfidenceLevel.LOW.value)


class TestPhase35TerminologyAndFormatting(unittest.TestCase):
    """Test suite for user-friendly terminology and workflow progress formatting."""

    def test_user_friendly_terminology_mapping(self) -> None:
        """Verify internal engineering concepts map to calm, clear terms."""
        self.assertEqual(format_user_friendly_terminology("diagnosis"), "What we found")
        self.assertEqual(format_user_friendly_terminology("evidence"), "Why we think this")
        self.assertEqual(format_user_friendly_terminology("hypothesis"), "Possible cause")
        self.assertEqual(format_user_friendly_terminology("tool"), "Windows check / action")
        self.assertEqual(format_user_friendly_terminology("medium_risk"), "Requires your approval")
        self.assertEqual(format_user_friendly_terminology("verification"), "Check whether the fix worked")
        self.assertEqual(format_user_friendly_terminology("recovery"), "Safely continue")
        self.assertEqual(format_user_friendly_terminology("telemetry"), "Technical diagnostics")

    def test_format_progress_step_descriptions(self) -> None:
        """Verify each workflow step has an understandable user-facing explanation."""
        self.assertEqual(format_progress_step("INPUT"), "Understanding your problem")
        self.assertEqual(format_progress_step("ANALYSIS"), "Checking system information")
        self.assertEqual(format_progress_step("EVIDENCE"), "Collecting diagnostic clues")
        self.assertEqual(format_progress_step("KNOWLEDGE"), "Checking known Windows patterns")
        self.assertEqual(format_progress_step("DIAGNOSTIC"), "Looking for the likely cause")
        self.assertEqual(format_progress_step("ACTION"), "Applying approved fix")
        self.assertEqual(format_progress_step("VERIFICATION"), "Checking whether the fix worked")
        self.assertEqual(format_progress_step("UNKNOWN_STEP"), "Step: UNKNOWN_STEP")

    def test_format_human_verification_status(self) -> None:
        """Verify human-facing explanation of verification outcomes."""
        self.assertIn("Windows is now in the expected", format_human_verification_status("verified"))
        self.assertIn("Windows is now in the expected", format_human_verification_status("success"))
        self.assertIn("not fully resolved", format_human_verification_status("partial_success"))
        self.assertIn("timed out", format_human_verification_status("timeout"))
        self.assertIn("did not resolve", format_human_verification_status("failed"))
        self.assertIn("did not resolve", format_human_verification_status("not_verified"))


class TestPhase35Accessibility(unittest.TestCase):
    """Test suite for non-color-only cues, high contrast, and accessible diff formatting."""

    def test_accessible_status_indicator_covers_all_ui_states(self) -> None:
        """Ensure all UI status states produce explicit text tags and symbols."""
        states = [
            ("SUCCESS", "[SUCCESS] ✓"),
            ("VERIFIED", "[VERIFIED] ✓"),
            ("PARTIAL_SUCCESS", "[PARTIALLY RESOLVED] ⚠️"),
            ("WARNING", "[WARNING] ⚠️"),
            ("ERROR", "[ERROR] ✕"),
            ("FAILED", "[FAILED] ✕"),
            ("UNRESOLVED", "[UNRESOLVED] ⚠️"),
            ("NOT_VERIFIED", "[NOT VERIFIED] ⚠️"),
            ("TIMEOUT", "[TIMEOUT] ⚠️"),
            ("BLOCKED", "[BLOCKED] 🚫"),
            ("INFO", "[INFO] ℹ️"),
            ("RUNNING", "[RUNNING] ⏳"),
            ("RECOVERING", "[RECOVERING] 🔄"),
            ("OFFLINE", "[OFFLINE] 🔌"),
            ("IDLE", "[READY] ●"),
            ("WAITING_FOR_CONFIRMATION", "[CONFIRMATION REQUIRED] ⚠️"),
        ]
        for st_key, expected_prefix in states:
            res = accessible_status_indicator(st_key, "Status Message")
            self.assertTrue(res.startswith(expected_prefix), f"Failed for {st_key}: {res}")

    def test_accessible_button_label_with_context(self) -> None:
        """Button label with action and accessible context hint."""
        lbl = accessible_button_label("🛡", "Approve Repair", "Requires Administrator Privileges")
        self.assertEqual(lbl, "🛡 Approve Repair (Requires Administrator Privileges)")

    def test_format_accessible_diff(self) -> None:
        """Verify before/after comparison table generation."""
        before = {"service_status": "STOPPED", "dns_check": "FAIL"}
        after = {"service_status": "RUNNING", "dns_check": "FAIL"}
        diff_table = format_accessible_diff(before, after)
        self.assertIn("| Component / Property | Before Repair | After Repair | Status Change |", diff_table)
        self.assertIn("| service_status | STOPPED | RUNNING | Changed |", diff_table)
        self.assertIn("| dns_check | FAIL | FAIL | Unchanged |", diff_table)

    def test_format_accessible_diff_empty(self) -> None:
        """Empty diff comparison returns descriptive text."""
        self.assertEqual(format_accessible_diff({}, {}), "No measurable state properties to compare.")

    def test_format_accessible_bullet_list(self) -> None:
        """List formatting with bullet prefix."""
        items = ["Network adapter active", "DNS query failed"]
        formatted = format_accessible_bullet_list(items)
        self.assertEqual(formatted, "• Network adapter active\n• DNS query failed")
        self.assertEqual(format_accessible_bullet_list([]), "None recorded.")


class TestPhase35UIStateManager(unittest.TestCase):
    """Test suite for Phase 35 session state lifecycle, recovery tracking, and invalidation."""

    def setUp(self) -> None:
        self.state_dict: dict = {}
        self.mgr = UIStateManager(self.state_dict)

    def test_welcome_guide_default_and_dismissal(self) -> None:
        """Welcome guide is shown by default and can be dismissed."""
        self.assertTrue(self.mgr.show_welcome_guide)
        self.mgr.dismiss_welcome_guide()
        self.assertFalse(self.mgr.show_welcome_guide)

    def test_ui_status_transitions(self) -> None:
        """UI status transitions correctly update session state."""
        self.assertEqual(self.mgr.ui_status, UIStatusState.IDLE.value)
        self.mgr.set_ui_status(UIStatusState.ANALYZING)
        self.assertEqual(self.mgr.ui_status, UIStatusState.ANALYZING.value)
        self.mgr.set_ui_status(UIStatusState.EXECUTING)
        self.assertEqual(self.mgr.ui_status, UIStatusState.EXECUTING.value)

    def test_interrupted_session_recovery_tracking(self) -> None:
        """Interrupted session sets RECOVERING status and tracks recovery state."""
        self.mgr.set_interrupted_session("sess_old_123", {"interrupted_step": "ACTION"})
        self.assertEqual(self.mgr.ui_status, UIStatusState.RECOVERING.value)
        self.assertEqual(self.state_dict["interrupted_session_id"], "sess_old_123")

        self.mgr.clear_interrupted_session()
        self.assertIsNone(self.state_dict["interrupted_session_id"])
        self.assertEqual(self.mgr.ui_status, UIStatusState.IDLE.value)

    def test_verification_result_sets_appropriate_status(self) -> None:
        """Verification results map to SUCCESS, PARTIAL_SUCCESS, or FAILED."""
        self.mgr.set_verification_result({"status": "verified"})
        self.assertEqual(self.mgr.ui_status, UIStatusState.SUCCESS.value)

        self.mgr.set_verification_result({"status": "partial_success"})
        self.assertEqual(self.mgr.ui_status, UIStatusState.PARTIAL_SUCCESS.value)

        self.mgr.set_verification_result({"status": "failed"})
        self.assertEqual(self.mgr.ui_status, UIStatusState.FAILED.value)

    def test_error_and_clear_error_lifecycle(self) -> None:
        """Setting error marks FAILED; clearing error restores IDLE."""
        self.mgr.set_error("Storage Error", "Disk full", ["Clean temp files"])
        self.assertEqual(self.mgr.ui_status, UIStatusState.FAILED.value)
        self.mgr.clear_error()
        self.assertEqual(self.mgr.ui_status, UIStatusState.IDLE.value)


class TestPhase35StandardizedComponentsRendering(unittest.TestCase):
    """Test suite ensuring all Phase 35 presentation cards render cleanly without exceptions."""

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.columns")
    @patch("streamlit.button")
    def test_render_welcome_guide(self, mock_btn: MagicMock, mock_cols: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure welcome guide renders friendly intro and dismiss control."""
        from ui.components import render_welcome_guide
        mock_cols.return_value = [MagicMock(), MagicMock()]
        mock_btn.return_value = False
        render_welcome_guide()
        mock_md.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.write")
    @patch("streamlit.expander")
    def test_render_standardized_diagnosis_card(self, mock_exp: MagicMock, mock_write: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure standardized diagnosis card renders findings, confidence, and evidence."""
        from ui.components import render_standardized_diagnosis_card
        render_standardized_diagnosis_card(
            summary="Windows DNS client resolution is failing.",
            likely_cause="DNS Resolver Cache Corruption",
            evidence=["DNS resolution query returned timeout", "Active WiFi adapter has IP"],
            recommendations=["Flush DNS resolver cache", "Re-test DNS resolution"],
            confidence_level="High confidence",
            observations=["IP: 192.168.1.50", "Adapter: Wi-Fi"],
            inferences=["Gateway reachable, DNS unreachable"],
            unknowns=["Upstream router DNS status"],
            contradictions=None,
            technical_details={"Domain": "network", "Tool": "check_dns_resolution"},
        )
        mock_md.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.warning")
    def test_render_standardized_diagnosis_card_with_contradictions(self, mock_warn: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure contradiction warning is prominently displayed when conflicting evidence exists."""
        from ui.components import render_standardized_diagnosis_card
        render_standardized_diagnosis_card(
            summary="Network status is ambiguous.",
            likely_cause="Intermittent Connection",
            evidence=["Ping to gateway succeeded"],
            recommendations=["Inspect adapter log"],
            contradictions=["check_dns_resolution reported FAIL but check_internet_connectivity reported SUCCESS"],
        )
        mock_warn.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.write")
    def test_render_standardized_repair_proposal_card(self, mock_write: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure repair proposal card communicates action, risk, and verification cleanly."""
        from ui.components import render_standardized_repair_proposal_card
        proposal = MagicMock()
        proposal.tool_name = "flush_dns_cache"
        proposal.risk = "MEDIUM"
        proposal.reason = "DNS cache contains stale records."
        proposal.expected_effect = "Clear resolver cache and restore web browsing."
        proposal.verification_tool = "check_dns_resolution"
        proposal.requires_admin = False

        render_standardized_repair_proposal_card(proposal, domain_label="Network & Internet")
        mock_md.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.error")
    def test_render_standardized_repair_proposal_card_stale(self, mock_err: MagicMock, mock_cont: MagicMock) -> None:
        """Stale repair proposals must render a clear invalidation message."""
        from ui.components import render_standardized_repair_proposal_card
        render_standardized_repair_proposal_card(None, domain_label="Network", is_stale=True)
        mock_err.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.success")
    @patch("streamlit.expander")
    def test_render_standardized_verification_card_verified(self, mock_exp: MagicMock, mock_succ: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Verified state renders clear success affirmation."""
        from ui.components import render_standardized_verification_card
        render_standardized_verification_card(
            verification_status="verified",
            explanation="DNS resolution now succeeds.",
            tool_name="flush_dns_cache",
            before_state={"dns_status": "FAILED"},
            after_state={"dns_status": "SUCCESS"},
            verification_tool="check_dns_resolution",
        )
        mock_succ.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.error")
    def test_render_standardized_verification_card_failed(self, mock_err: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Failed verification renders clear non-resolution notice."""
        from ui.components import render_standardized_verification_card
        render_standardized_verification_card(
            verification_status="failed",
            explanation="DNS resolution is still unresponsive.",
            tool_name="flush_dns_cache",
        )
        mock_err.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.warning")
    @patch("streamlit.columns")
    def test_render_recovery_card(self, mock_cols: MagicMock, mock_warn: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure recovery card displays interrupted session info and safe revalidation notice."""
        from ui.components import render_recovery_card
        mock_cols.return_value = [MagicMock(), MagicMock()]
        render_recovery_card("sess_rec_456", "VERIFICATION")
        mock_warn.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.error")
    @patch("streamlit.markdown")
    def test_render_user_friendly_error(self, mock_md: MagicMock, mock_err: MagicMock, mock_cont: MagicMock) -> None:
        """User friendly error displays calm message and recovery actions."""
        from ui.components import render_user_friendly_error
        render_user_friendly_error(
            title="Diagnostic Check Interrupted",
            message="Could not read Bluetooth adapter state.",
            recovery_steps=["Verify Bluetooth is enabled in Windows Settings", "Run standard Network check"],
            technical_details="System.Management.Automation.CommandNotFoundException",
        )
        mock_err.assert_called()


class TestPhase35ModeUX(unittest.TestCase):
    """Test suite for Phase 35 operating mode UX presentation and transitions."""

    def test_all_five_modes_user_facing_descriptions(self) -> None:
        """Verify all 5 modes have clear, non-technical descriptions."""
        self.assertEqual(len(MODE_DESCRIPTIONS), 5)
        for mode_val, desc in MODE_DESCRIPTIONS.items():
            self.assertTrue(len(desc) > 20, f"Description too short for {mode_val}")
            self.assertFalse("subprocess" in desc.lower())
            self.assertFalse("eval" in desc.lower())

    @patch("streamlit.radio")
    @patch("streamlit.info")
    def test_render_mode_selector_selection(self, mock_info: MagicMock, mock_radio: MagicMock) -> None:
        """Verify render_mode_selector returns selected mode and shows info banner."""
        from ui.components import render_mode_selector
        mock_radio.return_value = AppMode.TUTOR.value
        sel = render_mode_selector(AppMode.DIAGNOSTIC.value)
        self.assertEqual(sel, AppMode.TUTOR.value)
        mock_info.assert_called()

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    def test_render_system_status_panel(self, mock_md: MagicMock, mock_cols: MagicMock) -> None:
        """Verify system status cards render accurately."""
        from ui.components import render_system_status_panel
        mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        render_system_status_panel(
            ollama_status={"connected": True, "model_available": True, "model": "gemma4:12b"},
            db_health={"connected": True, "tables_count": 8},
            session_count=3,
            tool_count=59,
        )
        mock_md.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.warning")
    @patch("streamlit.markdown")
    def test_render_standardized_medium_confirmation(self, mock_md: MagicMock, mock_warn: MagicMock, mock_cont: MagicMock) -> None:
        """Verify explicit confirmation warning for MEDIUM actions."""
        from ui.components import render_standardized_medium_confirmation
        render_standardized_medium_confirmation(
            proposal_title="Restart Windows Update Service",
            action_description="Restarts the wuauserv service to recover stalled update downloads.",
            what_will_happen="Windows Update service will be stopped and restarted.",
            what_will_not_happen="No other services or registry keys will be modified.",
            risk="MEDIUM",
            is_stale=False,
        )
        mock_warn.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.error")
    def test_render_standardized_medium_confirmation_stale(self, mock_err: MagicMock, mock_cont: MagicMock) -> None:
        """Stale confirmation renders invalidation message."""
        from ui.components import render_standardized_medium_confirmation
        render_standardized_medium_confirmation(
            proposal_title="Restart Service",
            action_description="Desc",
            what_will_happen="Action",
            what_will_not_happen="None",
            is_stale=True,
        )
        mock_err.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    def test_render_diagnostic_intelligence_card(self, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Verify diagnostic intelligence card renders observations and hypotheses."""
        from ui.components import render_diagnostic_intelligence_card
        diag_data = {
            "summary": "Network check evaluation",
            "observations": ["Wi-Fi connected"],
            "interpretations": ["DNS server is unresponsive"],
            "hypotheses": [{"status": "SUPPORTED", "statement": "DNS Cache Issue", "explanation": "Cache holds invalid records"}],
            "uncertainty": ["Router upstream status unknown"],
            "recommended_tools": ["check_dns_resolution"],
        }
        render_diagnostic_intelligence_card(diag_data)
        mock_md.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.progress")
    @patch("streamlit.columns")
    def test_render_troubleshooting_workflow_card(self, mock_cols: MagicMock, mock_prog: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Verify workflow card renders current step and progress."""
        from ui.components import render_troubleshooting_workflow_card
        mock_cols.return_value = [MagicMock(), MagicMock()]
        wf_data = {
            "title": "Network Recovery Workflow",
            "status": "RUNNING",
            "current_step": 1,
            "steps": [
                {"purpose": "Check link state", "step_type": "DIAGNOSE", "tool_name": "get_network_adapters_diagnostics"},
                {"purpose": "Flush DNS cache", "step_type": "REPAIR", "tool_name": "flush_dns_cache", "authorization_required": True},
            ],
        }
        render_troubleshooting_workflow_card(wf_data)
        mock_md.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.columns")
    def test_render_domain_troubleshooting_card(self, mock_cols: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Verify domain intelligence card renders domain evidence."""
        from ui.components import render_domain_troubleshooting_card
        mock_cols.return_value = [MagicMock(), MagicMock()]
        dom_data = {
            "primary_domain": "NETWORK",
            "secondary_domains": ["DNS"],
            "status": "SUPPORTED",
            "selected_strategy": "Adapter First",
            "evidence_summary": "Ethernet disconnected, Wi-Fi connected",
            "evidence_items": [{"title": "Wi-Fi", "details": "Signal 90%", "status": "ok"}],
        }
        render_domain_troubleshooting_card(dom_data)
        mock_md.assert_called()

    @patch("streamlit.expander")
    @patch("streamlit.markdown")
    def test_render_privacy_notice(self, mock_md: MagicMock, mock_exp: MagicMock) -> None:
        """Verify privacy notice renders local-only policy."""
        from ui.components import render_privacy_notice
        render_privacy_notice("Diagnostic & Repair Assistant")
        mock_exp.assert_called()


class TestPhase35SecurityBoundary(unittest.TestCase):
    """Test suite for UI != Execution Layer and security isolation (Phase 35)."""

    def test_replay_protection_prevents_reexecution(self) -> None:
        """Executed tokens are recorded and cannot be reused."""
        mgr = UIStateManager({})
        token = "token_sec_check_999"
        self.assertTrue(mgr.can_execute_repair(token))
        mgr.mark_repair_executed(token, {"status": "verified"})
        self.assertFalse(mgr.can_execute_repair(token))

    def test_stale_results_cleared_on_problem_change(self) -> None:
        """Changing input text immediately invalidates stale proposals and tokens."""
        mgr = UIStateManager({})
        mgr.set_active_problem("Initial symptom")
        mgr.set_diagnostic_result({"synthesis": "Issue", "tool_results": []})
        self.assertIsNotNone(mgr._state.get("last_diag_result"))

        mgr.set_active_problem("New completely different symptom")
        self.assertIsNone(mgr._state.get("last_diag_result"))
        self.assertIsNone(mgr._state.get("pending_confirmation_token"))

    def test_empty_or_invalid_tokens_rejected(self) -> None:
        """None or empty tokens cannot execute repairs."""
        mgr = UIStateManager({})
        self.assertFalse(mgr.can_execute_repair(""))
        self.assertFalse(mgr.can_execute_repair(None))  # type: ignore


class TestPhase35StaticSecurityAST(unittest.TestCase):
    """AST static security scan verifying UI layer contains ZERO prohibited execution calls."""

    FORBIDDEN_CALLS = {
        "subprocess",
        "os.system",
        "os.popen",
        "Popen",
        "CreateProcess",
        "WinExec",
        "ShellExecute",
    }

    def test_ast_scan_ui_modules(self) -> None:
        """Verify UI modules contain 0 forbidden execution calls."""
        project_root = Path(__file__).resolve().parent.parent
        ui_files = [
            project_root / "ui" / "components.py",
            project_root / "ui" / "state.py",
            project_root / "ui" / "formatting.py",
            project_root / "ui" / "accessibility.py",
            project_root / "ui" / "__init__.py",
        ]

        for file_path in ui_files:
            self.assertTrue(file_path.exists(), f"Missing file: {file_path}")
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            {"eval", "exec"},
                            f"Prohibited built-in {node.func.id} in {file_path.name}:L{node.lineno}",
                        )
                    elif isinstance(node.func, ast.Attribute):
                        attr_chain = []
                        curr = node.func
                        while isinstance(curr, ast.Attribute):
                            attr_chain.append(curr.attr)
                            curr = curr.value
                        if isinstance(curr, ast.Name):
                            attr_chain.append(curr.id)
                        full_call = ".".join(reversed(attr_chain))
                        call_parts = full_call.split(".")
                        for forbidden in self.FORBIDDEN_CALLS:
                            self.assertNotIn(
                                forbidden,
                                call_parts,
                                f"Prohibited execution call '{full_call}' in {file_path.name}:L{node.lineno}",
                            )


if __name__ == "__main__":
    unittest.main()
