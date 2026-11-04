"""Tests for UI formatting and Personal Tutor presentation layer (Phases 20 & 35).

Verifies string, single list, multiple list, empty list, None, dictionary formatting,
clean tool descriptions, diagnostic cards, and strict avoidance of raw JSON/Python structures in UI.
"""

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from agent.tool_metadata import RiskLevel
from agent.tool_registry import default_tool_registry
from ui.formatting import (
    ConfidenceLevel,
    format_bytes,
    format_diagnostic_status,
    format_diagnostic_value,
    format_human_verification_status,
    format_key_label,
    format_progress_step,
    format_risk_badge,
    format_severity_badge,
    format_status_badge,
    format_timestamp,
    format_tool_name,
    format_tutor_prose,
    format_tutor_text_list,
    format_tutor_tool_description,
    extract_diagnostic_summary_text,
    format_user_friendly_terminology,
    map_confidence,
    render_diagnostic_results_table,
    render_runtime_health_tables,
    render_structured_diagnostic_card,
    render_system_info_table,
    truncate_text_safely,
)


class TestPersonalTutorFormattingRegression(unittest.TestCase):
    """Regression tests for Personal Tutor text formatters (Part 5)."""

    def test_string_formatting(self):
        """String returns readable sentence."""
        raw = "Windows Update service is running."
        formatted = format_tutor_prose(raw)
        self.assertEqual(formatted, "Windows Update service is running.")

        items = format_tutor_text_list(raw)
        self.assertEqual(items, ["Windows Update service is running."])

    def test_single_list_formatting(self):
        """Single list returns one readable sentence."""
        raw = ["Windows Update service is running."]
        formatted = format_tutor_prose(raw)
        self.assertEqual(formatted, "Windows Update service is running.")

        items = format_tutor_text_list(raw)
        self.assertEqual(items, ["Windows Update service is running."])

    def test_multiple_list_formatting(self):
        """Multiple list returns distinct bullet items."""
        raw = [
            "Check Windows Update.",
            "Check pending updates.",
        ]
        items = format_tutor_text_list(raw)
        self.assertEqual(items, ["Check Windows Update.", "Check pending updates."])

    def test_empty_list_handling(self):
        """Empty list returns empty list or fallback."""
        self.assertEqual(format_tutor_text_list([]), [])
        self.assertEqual(format_tutor_text_list([], fallback="Default note"), ["Default note"])
        self.assertIsNone(format_tutor_prose([]))
        self.assertEqual(format_tutor_prose([], fallback="Fallback"), "Fallback")

    def test_none_handling(self):
        """None returns empty list or fallback."""
        self.assertEqual(format_tutor_text_list(None), [])
        self.assertEqual(format_tutor_text_list(None, fallback="No issues found."), ["No issues found."])
        self.assertIsNone(format_tutor_prose(None))
        self.assertEqual(format_tutor_prose(None, fallback="No issues found."), "No issues found.")

    def test_indexed_list_string_cleaning(self):
        """Indexed list strings like '0: \"text\"' are cleaned of internal index prefixes."""
        raw = '[0: "Personal Tutor Mode provides structured, factual explanations so you understand your system."]'
        items = format_tutor_text_list(raw)
        self.assertEqual(
            items,
            ["Personal Tutor Mode provides structured, factual explanations so you understand your system."],
        )

    def test_dictionary_formatting(self):
        """Dictionary returns human-friendly message instead of raw JSON syntax."""
        dict_payload = {
            "summary": "Network connectivity is degraded due to DNS resolution timeout.",
            "details": "DNS resolver failed to respond within 5 seconds.",
        }
        items = format_tutor_text_list(dict_payload)
        self.assertIn("Network connectivity is degraded due to DNS resolution timeout.", items)
        self.assertIn("DNS resolver failed to respond within 5 seconds.", items)

        # Ensure no raw braces or quotes remain in items
        for item in items:
            self.assertFalse(item.startswith("{"))
            self.assertFalse(item.endswith("}"))

    def test_tool_metadata_description_formatting(self):
        """Tool descriptions format cleanly into title and human explanation."""
        tool_item = {
            "name": "get_network_adapters_diagnostics",
            "domain": "network",
            "description": "Collects network adapter state, IP configurations, and gateway reachability.",
        }
        desc = format_tutor_tool_description(tool_item)
        self.assertIn("Get Network Adapters Diagnostics", desc)
        self.assertIn("Collects network adapter state", desc)
        self.assertFalse(desc.startswith("{"))

    def test_no_raw_json_in_tool_name_or_badges(self):
        """Risk and status badges render human-readable symbols and text."""
        self.assertIn("SAFE", format_risk_badge("SAFE"))
        self.assertIn("MEDIUM", format_risk_badge("MEDIUM"))
        self.assertIn("VERIFIED", format_status_badge("VERIFIED"))
        self.assertIn("NORMAL", format_severity_badge("NORMAL"))
        self.assertEqual(format_tool_name("check_internet_connectivity"), "Check Internet Connectivity")
        self.assertEqual(format_bytes(1048576), "1.0 MB")


class TestDiagnosticUIFormatting(unittest.TestCase):
    """Tests covering all 20 diagnostic UI formatting requirements."""

    def test_1_boolean_formatting(self):
        """Contextual boolean values are converted to human readable terms."""
        self.assertEqual(format_diagnostic_value("resolved", True), "Successful")
        self.assertEqual(format_diagnostic_value("resolved", False), "Failed")
        self.assertEqual(format_diagnostic_value("reachable", True), "Target is reachable")
        self.assertEqual(format_diagnostic_value("reachable", False), "Target is unreachable")
        self.assertEqual(format_diagnostic_value("requires_admin", False), "No")
        self.assertEqual(format_diagnostic_value("requires_admin", True), "Yes")
        self.assertEqual(format_diagnostic_value("read_only", True), "Yes")
        self.assertEqual(format_diagnostic_value("is_running", True), "Running")
        self.assertEqual(format_diagnostic_value("is_running", False), "Stopped")

    def test_2_none_null_formatting(self):
        """None/null values are converted to informative sentences."""
        self.assertEqual(format_diagnostic_value("error", None), "No error reported")
        self.assertEqual(format_diagnostic_value("dns_server", None), "Not available")

    def test_3_snake_case_label_conversion(self):
        """Snake_case keys are translated into capitalized human-readable labels."""
        self.assertEqual(format_key_label("target_host"), "Target Host")
        self.assertEqual(format_key_label("resolved_ips"), "Resolved IP Addresses")
        self.assertEqual(format_key_label("latency_ms"), "Latency")
        self.assertEqual(format_key_label("requires_admin"), "Requires Admin")
        self.assertEqual(format_key_label("read_only"), "Read Only")
        self.assertEqual(format_key_label("automatic_allowed"), "Automatic Execution Allowed")
        self.assertEqual(format_key_label("verification_tool"), "Verification Tool")

    def test_4_nested_dictionary_formatting(self):
        """Nested dictionaries are flattened into readable structured properties."""
        mock_st = MagicMock()
        payload = {
            "tool": "check_dns_resolution",
            "domain": "network",
            "success": True,
            "data": {
                "target_host": "dns.google",
                "resolved": True,
                "latency_ms": 1147.5,
            },
            "error": None,
        }
        render_structured_diagnostic_card("check_dns_resolution", payload, st_module=mock_st)
        mock_st.markdown.assert_any_call("#### 🔍 Check Dns Resolution")
        # Check that table markdown was sent to st.markdown
        calls = [str(c) for c in mock_st.markdown.call_args_list]
        table_rendered = any("Target Host" in c and "dns.google" in c for c in calls)
        self.assertTrue(table_rendered)

    def test_5_list_formatting(self):
        """Lists are rendered as bulleted items or comma-separated lists."""
        val = format_diagnostic_value("resolved_ips", ["8.8.8.8", "8.8.4.4"])
        self.assertEqual(val, "8.8.8.8, 8.8.4.4")

    def test_6_empty_lists(self):
        """Empty lists render as None reported."""
        val = format_diagnostic_value("resolved_ips", [])
        self.assertEqual(val, "None reported")

    def test_7_multiple_diagnostic_results(self):
        """Multiple diagnostic results can be rendered cleanly."""
        dns_payload = {
            "tool": "check_dns_resolution",
            "success": True,
            "domain": "network",
            "data": {"target_host": "dns.google", "resolved": True},
        }
        internet_payload = {
            "tool": "check_internet_connectivity",
            "success": True,
            "domain": "network",
            "data": {"target": "1.1.1.1:53", "reachable": True},
        }
        mock_st = MagicMock()
        render_structured_diagnostic_card("check_dns_resolution", dns_payload, st_module=mock_st)
        render_structured_diagnostic_card("check_internet_connectivity", internet_payload, st_module=mock_st)
        self.assertEqual(mock_st.markdown.call_count >= 2, True)

    def test_8_successful_diagnostics(self):
        """Successful diagnostics show PASS badge."""
        self.assertEqual(format_diagnostic_status(True), "✓ PASS")
        self.assertEqual(format_diagnostic_status("PASS"), "✓ PASS")

    def test_9_failed_diagnostics(self):
        """Failed diagnostics show FAILED badge."""
        self.assertEqual(format_diagnostic_status(False), "✕ FAILED")
        self.assertEqual(format_diagnostic_status("FAILED"), "✕ FAILED")

    def test_10_diagnostic_errors(self):
        """Diagnostic errors render error details clearly without raw dump."""
        mock_st = MagicMock()
        payload = {
            "tool": "check_dns_resolution",
            "success": False,
            "domain": "network",
            "data": {},
            "error": "Connection timed out after 5000ms",
        }
        render_structured_diagnostic_card("check_dns_resolution", payload, st_module=mock_st)
        mock_st.error.assert_called_with("**Error Details:** Connection timed out after 5000ms")

    def test_11_dns_result_formatting(self):
        """DNS resolution result renders Target Host, Resolution Status, and IP list."""
        dns_payload = {
            "tool": "check_dns_resolution",
            "domain": "network",
            "success": True,
            "data": {
                "target_host": "dns.google",
                "resolved": True,
                "resolved_ips": ["8.8.8.8", "8.8.4.4"],
                "latency_ms": 42.5,
            },
            "error": None,
        }
        mock_st = MagicMock()
        render_structured_diagnostic_card("check_dns_resolution", dns_payload, st_module=mock_st)
        calls = [str(c) for c in mock_st.markdown.call_args_list]
        self.assertTrue(any("dns.google" in c for c in calls))

    def test_12_internet_connectivity_result_formatting(self):
        """Internet connectivity result renders Reachability and Latency."""
        internet_payload = {
            "tool": "check_internet_connectivity",
            "domain": "network",
            "success": True,
            "data": {
                "target": "1.1.1.1:53",
                "reachable": True,
                "latency_ms": 116.69,
            },
            "error": None,
        }
        mock_st = MagicMock()
        render_structured_diagnostic_card("check_internet_connectivity", internet_payload, st_module=mock_st)
        calls = [str(c) for c in mock_st.markdown.call_args_list]
        self.assertTrue(any("1.1.1.1:53" in c for c in calls))

    def test_13_network_adapter_result_formatting(self):
        """Network adapter diagnostics render structured adapter details."""
        adapter_payload = {
            "tool": "get_network_adapters_diagnostics",
            "domain": "network",
            "success": True,
            "data": {
                "adapter_name": "Wi-Fi",
                "is_up": True,
                "speed_mbps": 866,
                "ipv4": ["192.168.1.100"],
            },
            "error": None,
        }
        mock_st = MagicMock()
        render_structured_diagnostic_card("get_network_adapters_diagnostics", adapter_payload, st_module=mock_st)
        calls = [str(c) for c in mock_st.markdown.call_args_list]
        self.assertTrue(any("Wi-Fi" in c for c in calls))

    def test_14_personal_tutor_evidence_formatting(self):
        """Personal Tutor evidence is converted to natural sentences."""
        evidence_list = [
            "DNS resolution working for dns.google.",
            "Internet gateway reachable with 116 ms latency.",
        ]
        prose = format_tutor_prose(evidence_list)
        self.assertIn("DNS resolution working for dns.google.", prose)
        self.assertIn("Internet gateway reachable with 116 ms latency.", prose)
        self.assertFalse(prose.startswith("["))

    def test_15_screenshot_failure_formatting(self):
        """Screenshot analysis failures format cleanly without raw exception dumps."""
        fail_msg = "The local vision model did not complete the analysis within the configured timeout."
        formatted = format_tutor_prose(fail_msg)
        self.assertEqual(formatted, fail_msg)
        self.assertFalse(formatted.startswith("{"))

    def test_16_voice_stt_unavailable_formatting(self):
        """Voice STT unavailable message formats cleanly."""
        stt_msg = "The audio file was received successfully, but WinFix AI cannot transcribe it because local speech model is unavailable."
        formatted = format_tutor_prose(stt_msg)
        self.assertEqual(formatted, stt_msg)

    def test_17_raw_json_not_used_in_normal_ui(self):
        """Primary UI elements receive structured markdown rather than raw st.json."""
        mock_st = MagicMock()
        payload = {
            "tool": "check_dns_resolution",
            "domain": "network",
            "success": True,
            "data": {"target_host": "dns.google", "resolved": True},
            "error": None,
        }
        render_structured_diagnostic_card("check_dns_resolution", payload, st_module=mock_st)
        # Verify expander was created for developer view
        mock_st.expander.assert_called_once()
        expander_title = mock_st.expander.call_args[0][0]
        self.assertIn("Developer View", expander_title)

    def test_18_developer_raw_payload_remains_available(self):
        """Developer view expander preserves the exact raw payload inside json view."""
        mock_st = MagicMock()
        payload = {
            "tool": "check_dns_resolution",
            "domain": "network",
            "success": True,
            "data": {"target_host": "dns.google"},
            "error": None,
        }
        render_structured_diagnostic_card("check_dns_resolution", payload, st_module=mock_st)
        mock_st.json.assert_called_with(payload)

    def test_19_no_unsupported_conclusions_generated(self):
        """Confidence and formatting do not generate unsupported causal conclusions."""
        conf = map_confidence(evidence_count=0, is_uncertain=True)
        self.assertEqual(conf, ConfidenceLevel.UNKNOWN.value)

    def test_20_existing_tool_registry_formatting_remains_unchanged(self):
        """ToolRegistry structure and tool listing table remain intact."""
        tools = default_tool_registry.list_tools()
        self.assertIn(len(tools), (59, 62))
        safe_count = sum(1 for t in tools if t.risk == RiskLevel.SAFE)
        med_count = sum(1 for t in tools if t.risk == RiskLevel.MEDIUM)
        high_count = sum(1 for t in tools if t.risk == RiskLevel.HIGH)
        self.assertIn(safe_count, (49, 52))
        self.assertEqual(med_count, 10)
        self.assertEqual(high_count, 0)

    def test_21_diagnostic_summary_extractor(self):
        """extract_diagnostic_summary_text returns clean, human-readable summaries."""
        dns_payload = {
            "tool": "check_dns_resolution",
            "domain": "network",
            "success": True,
            "data": {
                "target_host": "dns.google",
                "resolved": True,
                "resolved_ips": ["8.8.8.8", "8.8.4.4"],
                "latency_ms": 1426.8,
            },
            "error": None,
        }
        summary = extract_diagnostic_summary_text("check_dns_resolution", dns_payload)
        self.assertIn("dns.google", summary)
        self.assertIn("resolved", summary)
        self.assertIn("1426.8 ms", summary)
        self.assertFalse(summary.startswith("{"))

    def test_22_render_diagnostic_results_table(self):
        """render_diagnostic_results_table renders a clean Markdown table with headers."""
        diag_data = {
            "dns": {
                "tool": "check_dns_resolution",
                "domain": "network",
                "success": True,
                "data": {
                    "target_host": "dns.google",
                    "resolved": True,
                    "latency_ms": 1426.8,
                },
                "error": None,
            },
            "internet": {
                "tool": "check_internet_connectivity",
                "domain": "network",
                "success": True,
                "data": {
                    "target": "1.1.1.1:53",
                    "reachable": True,
                    "latency_ms": 138.29,
                },
                "error": None,
            },
        }
        mock_st = MagicMock()
        render_diagnostic_results_table(diag_data, st_module=mock_st)
        mock_st.markdown.assert_called_once()
        table_output = mock_st.markdown.call_args[0][0]
        self.assertIn("| Tool | Domain | Status | Key Findings |", table_output)
        self.assertIn("`check_dns_resolution`", table_output)
        self.assertIn("Network", table_output)
        self.assertIn("`✓ PASS`", table_output)
        self.assertIn("dns.google", table_output)
        self.assertIn("`check_internet_connectivity`", table_output)
        self.assertIn("1.1.1.1:53", table_output)

    def test_23_render_system_info_table(self):
        """render_system_info_table renders system information as a structured table."""
        sys_info = {
            "os": {"os_name": "Windows 11 Pro", "os_version": "10.0.26100", "build_number": "26100"},
            "computer": {"hostname": "WIN-FIX-PC"},
            "cpu": {"model": "Intel Core i7-12700H", "physical_cores": 14, "logical_cores": 20},
            "memory": {"total_formatted": "32.0 GB", "percent_used": 45.0},
            "disk": {"drives": ["C:", "D:"]},
            "network": {"adapters": ["Wi-Fi", "Ethernet"]},
            "uptime": {"uptime_formatted": "2 days, 3 hours"},
        }
        mock_st = MagicMock()
        render_system_info_table(sys_info, st_module=mock_st)
        mock_st.markdown.assert_called_once()
        table_output = mock_st.markdown.call_args[0][0]
        self.assertIn("| Component | Specification | Domain | Status |", table_output)
        self.assertIn("Windows 11 Pro", table_output)
        self.assertIn("WIN-FIX-PC", table_output)
        self.assertIn("Intel Core i7", table_output)
        self.assertIn("32.0 GB Total", table_output)

    def test_24_render_runtime_health_tables(self):
        """render_runtime_health_tables renders local AI and DB health in a structured table."""
        ollama_status = {"available": True, "model": "llama3"}
        db_health = {"connected": True, "tables_count": 8}
        mock_st = MagicMock()
        render_runtime_health_tables(ollama_status, db_health, st_module=mock_st)
        mock_st.markdown.assert_called_once()
        table_output = mock_st.markdown.call_args[0][0]
        self.assertIn("| Subsystem | Details | Status |", table_output)
        self.assertIn("Local AI (Ollama)", table_output)
        self.assertIn("SQLite Database", table_output)


if __name__ == "__main__":
    unittest.main()
