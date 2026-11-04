"""Comprehensive test suite for WinFix AI UI/UX Layer (Phase 20).

Verifies presentation components, formatting helpers, accessibility features,
centralized session state management, stale result invalidation, replay protection,
and AST static security compliance.
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
    format_accessible_table,
)
from ui.formatting import (
    format_bytes,
    format_risk_badge,
    format_severity_badge,
    format_status_badge,
    format_timestamp,
    format_tool_name,
    format_tutor_prose,
    format_tutor_text_list,
    format_tutor_tool_description,
    truncate_text_safely,
)
from ui.state import AppMode, MODE_DESCRIPTIONS, UIStateManager


class TestUIFormatting(unittest.TestCase):
    """Test suite for string, badge, size, and timestamp formatting utilities."""

    def test_format_bytes(self) -> None:
        """Verify human-readable byte conversions."""
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1024 * 1024 * 5), "5.0 MB")
        self.assertEqual(format_bytes(1024 * 1024 * 1024 * 2.5), "2.5 GB")
        self.assertEqual(format_bytes(-100), "0 B")

    def test_format_timestamp(self) -> None:
        """Verify ISO timestamp formatting."""
        iso_str = "2026-09-25T12:30:00"
        formatted = format_timestamp(iso_str)
        self.assertIn("2026", formatted)
        self.assertIn("Sep 25", formatted)
        self.assertEqual(format_timestamp(None), "Unknown time")
        self.assertEqual(format_timestamp("invalid_ts"), "invalid_ts")

    def test_format_risk_badge(self) -> None:
        """Verify risk badge formatting."""
        self.assertIn("SAFE", format_risk_badge(RiskLevel.SAFE))
        self.assertIn("MEDIUM", format_risk_badge(RiskLevel.MEDIUM))
        self.assertIn("HIGH", format_risk_badge(RiskLevel.HIGH))
        self.assertIn("SAFE", format_risk_badge("SAFE"))

    def test_format_status_badge(self) -> None:
        """Verify execution and verification status badges."""
        self.assertIn("✓", format_status_badge("VERIFIED"))
        self.assertIn("✓", format_status_badge("SUCCESS"))
        self.assertIn("⚠", format_status_badge("NOT_VERIFIED"))
        self.assertIn("⚠", format_status_badge("TIMEOUT"))
        self.assertIn("✕", format_status_badge("FAILED"))
        self.assertIn("✕", format_status_badge("BLOCKED"))

    def test_format_severity_badge(self) -> None:
        """Verify severity classification badges."""
        self.assertIn("🟢", format_severity_badge("LOW"))
        self.assertIn("🟢", format_severity_badge("NORMAL"))
        self.assertIn("🟡", format_severity_badge("MEDIUM"))
        self.assertIn("🔴", format_severity_badge("HIGH"))
        self.assertIn("🔴", format_severity_badge("CRITICAL"))

    def test_format_tool_name(self) -> None:
        """Verify snake_case to Title Case conversion."""
        self.assertEqual(
            format_tool_name("get_network_adapters_diagnostics"),
            "Get Network Adapters Diagnostics",
        )
        self.assertEqual(format_tool_name("clean_user_temp_cache"), "Clean User Temp Cache")
        self.assertEqual(format_tool_name(""), "Unknown Tool")

    def test_truncate_text_safely(self) -> None:
        """Verify string truncation bounds."""
        short_text = "Hello World"
        self.assertEqual(truncate_text_safely(short_text, 20), "Hello World")
        long_text = "This is a very long descriptive error string for testing."
        truncated = truncate_text_safely(long_text, 20)
        self.assertEqual(len(truncated), 20)
        self.assertTrue(truncated.endswith("..."))


class TestPersonalTutorUIFormatting(unittest.TestCase):
    """Test suite ensuring Personal Tutor outputs are formatted as clean human-readable text."""

    def test_format_tutor_string(self) -> None:
        """Verify single plain string formatting."""
        inp = "Windows Update service is running."
        prose = format_tutor_prose(inp)
        items = format_tutor_text_list(inp)
        self.assertEqual(prose, "Windows Update service is running.")
        self.assertEqual(items, ["Windows Update service is running."])

    def test_format_tutor_single_item_list(self) -> None:
        """Verify single item list converts to natural text without brackets or indexes."""
        inp = ["Windows Update service is running."]
        prose = format_tutor_prose(inp)
        items = format_tutor_text_list(inp)
        self.assertEqual(prose, "Windows Update service is running.")
        self.assertEqual(items, ["Windows Update service is running."])

    def test_format_tutor_multiple_item_list(self) -> None:
        """Verify multiple item list formats as distinct readable items without list indexes."""
        inp = [
            "Check whether Windows Update is enabled.",
            "Check Windows Settings for pending updates.",
            "Restart the Windows Update service if authorized.",
        ]
        items = format_tutor_text_list(inp)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0], "Check whether Windows Update is enabled.")
        self.assertEqual(items[1], "Check Windows Settings for pending updates.")
        self.assertEqual(items[2], "Restart the Windows Update service if authorized.")

    def test_format_tutor_empty_list_and_none(self) -> None:
        """Verify empty lists and None values return empty or approved fallback without raw representation."""
        self.assertEqual(format_tutor_text_list([]), [])
        self.assertEqual(format_tutor_text_list(None), [])
        self.assertIsNone(format_tutor_prose([]))
        self.assertIsNone(format_tutor_prose(None))
        
        fallback_items = format_tutor_text_list([], fallback="No specific root cause has been identified.")
        self.assertEqual(fallback_items, ["No specific root cause has been identified."])
        fallback_prose = format_tutor_prose(None, fallback="No specific incident reported.")
        self.assertEqual(fallback_prose, "No specific incident reported.")

    def test_format_tutor_dictionary(self) -> None:
        """Verify dictionaries are never exposed as raw Python dicts or JSON."""
        # Diagnostic message dictionary
        dict_inp = {"message": "Windows Update service is active and running normally."}
        items = format_tutor_text_list(dict_inp)
        self.assertEqual(items, ["Windows Update service is active and running normally."])

        # Tool dictionary
        tool_dict = {"tool_name": "check_windows_update_status", "risk": "SAFE"}
        tool_items = format_tutor_text_list(tool_dict)
        self.assertEqual(len(tool_items), 1)
        self.assertIn("Check Windows Update Status", tool_items[0])
        self.assertNotIn("risk", tool_items[0])
        self.assertNotIn("{", tool_items[0])

    def test_format_tutor_indexed_string_and_json_cleanup(self) -> None:
        """Verify indexed string representations like [ 0: '...' ] are cleaned of implementation artifacts."""
        raw_indexed = '[\n    0: "Personal Tutor Mode provides structured, factual explanations so you understand your system."\n]'
        items = format_tutor_text_list(raw_indexed)
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0],
            "Personal Tutor Mode provides structured, factual explanations so you understand your system.",
        )
        self.assertNotIn("0:", items[0])
        self.assertNotIn("[", items[0])

    def test_format_tutor_tool_description(self) -> None:
        """Verify tool descriptions format into readable sentences with tool names and purposes."""
        desc = format_tutor_tool_description("check_windows_update_status")
        self.assertTrue(desc.startswith("Check Windows Update Status —"))
        self.assertFalse(desc.startswith("{"))
        self.assertTrue(desc.endswith("."))

    def test_no_raw_structures_in_empty_representations(self) -> None:
        """Verify None, [], {}, '', 'None', '[]', '{}' never produce raw implementation leaks."""
        for empty_val in (None, [], {}, "", "None", "[]", "{}", "null"):
            items = format_tutor_text_list(empty_val)
            self.assertEqual(items, [], f"Failed on empty input {empty_val}")



class TestUIAccessibility(unittest.TestCase):
    """Test suite for accessibility utilities and non-color-only state indicators."""

    def test_accessible_button_label(self) -> None:
        """Verify accessible button labeling."""
        self.assertEqual(accessible_button_label("🔍", "Diagnose"), "🔍 Diagnose")
        self.assertEqual(accessible_button_label("✓", "Confirm Repair"), "✓ Confirm Repair")
        self.assertEqual(accessible_button_label("", "Cancel"), "Cancel")

    def test_accessible_status_indicator(self) -> None:
        """Verify textual status prefixes for screen readers and high contrast."""
        self.assertTrue(accessible_status_indicator("SUCCESS", "Done").startswith("[SUCCESS] ✓"))
        self.assertTrue(accessible_status_indicator("VERIFIED", "Ready").startswith("[VERIFIED] ✓"))
        self.assertTrue(accessible_status_indicator("WARNING", "Check").startswith("[WARNING] ⚠️"))
        self.assertTrue(accessible_status_indicator("ERROR", "Failed").startswith("[ERROR] ✕"))
        self.assertTrue(accessible_status_indicator("BLOCKED", "Forbidden").startswith("[BLOCKED] 🚫"))

    def test_format_accessible_table(self) -> None:
        """Verify markdown table construction with headers and rows."""
        headers = ["Tool Name", "Domain", "Risk"]
        rows = [
            ["check_dns_resolution", "network", "SAFE"],
            ["flush_dns_cache", "network", "MEDIUM"],
        ]
        table = format_accessible_table(headers, rows)
        self.assertIn("| Tool Name | Domain | Risk |", table)
        self.assertIn("| check_dns_resolution | network | SAFE |", table)
        self.assertIn("| flush_dns_cache | network | MEDIUM |", table)


class TestUIStateManager(unittest.TestCase):
    """Test suite for UI session state management, transition guards, and replay protection."""

    def setUp(self) -> None:
        self.state_dict: dict = {}
        self.ui_state = UIStateManager(self.state_dict)

    def test_initial_state_defaults(self) -> None:
        """Verify default session state keys."""
        self.assertTrue(self.ui_state.session_id.startswith("sess_"))
        self.assertEqual(self.ui_state.current_mode, AppMode.DIAGNOSTIC.value)
        self.assertIsNone(self.state_dict["last_diag_result"])
        self.assertIsNone(self.state_dict["pending_confirmation_token"])
        self.assertEqual(len(self.state_dict["executed_repair_tokens"]), 0)

    def test_mode_switching_resets_transient_state(self) -> None:
        """Switching modes should clear transient proposals and errors."""
        self.state_dict["pending_confirmation_token"] = "token_123"
        self.state_dict["ui_error_state"] = {"title": "Error"}
        self.ui_state.set_mode(AppMode.TUTOR.value)

        self.assertEqual(self.ui_state.current_mode, AppMode.TUTOR.value)
        self.assertIsNone(self.state_dict["pending_confirmation_token"])
        self.assertIsNone(self.state_dict["ui_error_state"])

    def test_active_problem_change_invalidates_stale_results(self) -> None:
        """Changing problem text must invalidate previous diagnostic results."""
        self.ui_state.set_active_problem("Internet is not working")
        self.ui_state.set_diagnostic_result({"synthesis": "DNS Issue", "tool_results": []})
        self.assertIsNotNone(self.state_dict["last_diag_result"])

        # Edit problem text
        changed = self.ui_state.set_active_problem("Computer is running slow")
        self.assertTrue(changed)
        self.assertIsNone(self.state_dict["last_diag_result"])
        self.assertIsNone(self.state_dict["last_diag_hash"])

    def test_active_problem_same_text_preserves_results(self) -> None:
        """Setting identical problem text must NOT invalidate existing diagnostic results."""
        self.ui_state.set_active_problem("Internet issue")
        self.ui_state.set_diagnostic_result({"synthesis": "DNS Issue", "tool_results": []})

        changed = self.ui_state.set_active_problem("Internet issue")
        self.assertFalse(changed)
        self.assertIsNotNone(self.state_dict["last_diag_result"])

    def test_voice_transcript_change_invalidates_stale_state(self) -> None:
        """Editing voice transcript must clear stale voice diagnostics."""
        self.ui_state.set_voice_transcript("My bluetooth is disconnected")
        self.state_dict["last_diag_result"] = {"synthesis": "Bluetooth"}

        changed = self.ui_state.set_voice_transcript("My wifi is disconnected")
        self.assertTrue(changed)
        self.assertIsNone(self.state_dict["last_diag_result"])

    def test_screenshot_change_invalidates_stale_state(self) -> None:
        """Uploading a new screenshot must clear previous screenshot analysis."""
        self.ui_state.set_screenshot_analysis({"evidence": "Error 0x8007"}, "hash_aaa")
        self.assertEqual(self.state_dict["current_screenshot_hash"], "hash_aaa")

        changed = self.ui_state.set_screenshot_analysis({"evidence": "Error 0xC000"}, "hash_bbb")
        self.assertTrue(changed)
        self.assertEqual(self.state_dict["current_screenshot_hash"], "hash_bbb")
        self.assertIsNone(self.state_dict["last_diag_result"])

    def test_confirmation_replay_protection(self) -> None:
        """A confirmed repair token cannot be executed more than once."""
        token = "conf_token_abc_123"
        self.assertTrue(self.ui_state.can_execute_repair(token))

        # Mark executed
        self.ui_state.mark_repair_executed(token, {"success": True, "verification_status": "verified"})
        self.assertFalse(self.ui_state.can_execute_repair(token))
        self.assertIn(token, self.state_dict["executed_repair_tokens"])

    def test_error_state_handling(self) -> None:
        """Verify setting and clearing UI error states."""
        self.ui_state.set_error("Test Error", "Something broke", ["Try restarting"])
        err = self.state_dict["ui_error_state"]
        self.assertEqual(err["title"], "Test Error")
        self.assertEqual(len(err["recovery_steps"]), 1)

        self.ui_state.clear_error()
        self.assertIsNone(self.state_dict["ui_error_state"])


class TestModeDescriptions(unittest.TestCase):
    """Test suite ensuring all 5 modes have distinct, user-friendly descriptions."""

    def test_all_five_modes_have_descriptions(self) -> None:
        """Ensure all 5 modes exist in MODE_DESCRIPTIONS with non-empty content."""
        expected_modes = [
            AppMode.DIAGNOSTIC.value,
            AppMode.TUTOR.value,
            AppMode.AUTOPILOT.value,
            AppMode.SCREENSHOT.value,
            AppMode.VOICE.value,
        ]
        self.assertEqual(len(expected_modes), 5)
        for mode in expected_modes:
            self.assertIn(mode, MODE_DESCRIPTIONS)
            self.assertGreater(len(MODE_DESCRIPTIONS[mode]), 10)


class TestUIComponentsRendering(unittest.TestCase):
    """Test suite ensuring UI components render safely without runtime exceptions."""

    @patch("streamlit.columns")
    @patch("streamlit.title")
    @patch("streamlit.markdown")
    @patch("streamlit.success")
    def test_render_app_header(self, mock_succ: MagicMock, mock_md: MagicMock, mock_title: MagicMock, mock_cols: MagicMock) -> None:
        """Ensure render_app_header renders title and offline badge."""
        from ui.components import render_app_header
        mock_cols.return_value = [MagicMock(), MagicMock()]
        render_app_header(is_offline=True)
        mock_title.assert_called_once()

    @patch("streamlit.radio")
    @patch("streamlit.info")
    @patch("streamlit.markdown")
    def test_render_mode_selector(self, mock_md: MagicMock, mock_info: MagicMock, mock_radio: MagicMock) -> None:
        """Ensure render_mode_selector displays radio selector and mode description."""
        from ui.components import render_mode_selector
        mock_radio.return_value = AppMode.DIAGNOSTIC.value
        selected = render_mode_selector(AppMode.DIAGNOSTIC.value)
        self.assertEqual(selected, AppMode.DIAGNOSTIC.value)
        mock_info.assert_called_once()

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    def test_render_system_status_panel(self, mock_md: MagicMock, mock_cols: MagicMock) -> None:
        """Ensure system status panel renders local AI, SQLite, and Tool Registry cards."""
        from ui.components import render_system_status_panel
        mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        render_system_status_panel(
            ollama_status={"connected": True, "model_available": True, "model": "gemma4:12b"},
            db_health={"connected": True, "tables_count": 10},
            session_count=5,
            tool_count=59,
            kb_stats={"status": "HEALTHY", "total_articles": 9, "version": 1},
        )
        mock_md.assert_called()

    @patch("streamlit.expander")
    @patch("streamlit.markdown")
    def test_render_privacy_notice(self, mock_md: MagicMock, mock_exp: MagicMock) -> None:
        """Ensure privacy notice renders local-only policy."""
        from ui.components import render_privacy_notice
        render_privacy_notice(AppMode.DIAGNOSTIC.value)
        mock_exp.assert_called_once()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    @patch("streamlit.write")
    def test_render_evidence_card(self, mock_write: MagicMock, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure evidence card renders observed and inferred facts."""
        from ui.components import render_evidence_card
        render_evidence_card(
            evidence_list=["DNS working"],
            observed=["Link state UP"],
            inferred=["Adapter connected"],
            unverified=["Upstream gateway latency"],
        )
        mock_cont.assert_called_once()

    @patch("streamlit.expander")
    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    def test_render_knowledge_card(self, mock_md: MagicMock, mock_cols: MagicMock, mock_exp: MagicMock) -> None:
        """Ensure local knowledge card renders symptoms, causes, and verification steps."""
        from ui.components import render_knowledge_card
        mock_cols.return_value = [MagicMock(), MagicMock()]
        article = KnowledgeArticle(
            id="kb_test_ui",
            title="Test Knowledge Article",
            category=KnowledgeCategory.NETWORK,
            summary="Troubleshooting summary",
            symptoms=["Symptom 1"],
            possible_causes=["Cause 1"],
            diagnostic_steps=["Step 1"],
            related_tools=["check_dns_resolution"],
            verification_steps=["Verification 1"],
        )
        render_knowledge_card(article)
        mock_exp.assert_called_once()

    @patch("streamlit.container")
    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    def test_render_tool_card(self, mock_md: MagicMock, mock_cols: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure tool card renders metadata."""
        from ui.components import render_tool_card
        mock_cols.return_value = [MagicMock(), MagicMock()]
        tool = ToolDefinition(
            name="check_dns_resolution",
            domain="network",
            description="Inspect DNS resolution",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            read_only=True,
            handler=lambda: None,
        )
        render_tool_card(tool)
        mock_cont.assert_called_once()

    @patch("streamlit.container")
    @patch("streamlit.columns")
    @patch("streamlit.warning")
    def test_render_confirmation_card(self, mock_warn: MagicMock, mock_cols: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure confirmation card displays explicit action and risk."""
        from ui.components import render_confirmation_card
        mock_cols.return_value = [MagicMock(), MagicMock()]
        render_confirmation_card(
            proposal_title="Restart DNS Cache",
            proposal_description="Flushes DNS resolver entries.",
            tool_name="flush_dns_cache",
            risk="MEDIUM",
            requires_admin=False,
        )
        mock_warn.assert_called_once()

    @patch("streamlit.container")
    @patch("streamlit.success")
    def test_render_verification_result(self, mock_succ: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure verification result card renders outcome."""
        from ui.components import render_verification_result
        render_verification_result("verified", before_state={"status": "STOPPED"}, after_state={"status": "RUNNING"})
        mock_succ.assert_called_once()

    @patch("streamlit.container")
    @patch("streamlit.error")
    def test_render_error_state(self, mock_err: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure error state card displays structured error and recovery steps."""
        from ui.components import render_error_state
        render_error_state("Speech Unavailable", "STT model offline", ["Use Text Diagnostics"])
        mock_err.assert_called_once()

    @patch("streamlit.container")
    @patch("streamlit.markdown")
    def test_render_empty_state(self, mock_md: MagicMock, mock_cont: MagicMock) -> None:
        """Ensure empty state renders mode guidance."""
        from ui.components import render_empty_state
        render_empty_state("Personal Tutor Mode", "Ready to teach", ["Ask any Windows question"])
        mock_cont.assert_called_once()


class TestASTSecurityUI(unittest.TestCase):
    """Security AST scan ensuring Phase 20 UI modules contain zero forbidden execution calls."""

    FORBIDDEN_CALLS = {
        "subprocess",
        "os.system",
        "os.popen",
        "Popen",
        "CreateProcess",
        "WinExec",
        "ShellExecute",
    }

    def test_ast_scan_phase_20_ui_modules(self) -> None:
        """Scan all Phase 20 UI files for prohibited execution patterns."""
        project_root = Path(__file__).resolve().parent.parent
        files_to_scan = [
            project_root / "ui" / "components.py",
            project_root / "ui" / "state.py",
            project_root / "ui" / "formatting.py",
            project_root / "ui" / "accessibility.py",
            project_root / "ui" / "__init__.py",
        ]

        for file_path in files_to_scan:
            self.assertTrue(file_path.exists(), f"File {file_path} does not exist.")
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))

            for node in ast.walk(tree):
                # Check for call to eval() or exec()
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            {"eval", "exec"},
                            f"Forbidden built-in call '{node.func.id}' found in {file_path.name}:L{node.lineno}",
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
                                f"Forbidden call '{full_call}' found in {file_path.name}:L{node.lineno}",
                            )
                            self.assertNotEqual(
                                forbidden,
                                full_call,
                                f"Forbidden call '{full_call}' found in {file_path.name}:L{node.lineno}",
                            )


if __name__ == "__main__":
    unittest.main()
