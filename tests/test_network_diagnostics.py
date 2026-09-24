"""Comprehensive unit and security tests for WinFix AI Phase 6 (Network Diagnostics).

Tests scenario orchestration, evidence-based reasoning, hostname sanitization,
SafetyEngine integration, and static code security guarantees.
"""

import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.network_diagnostics import (
    NETWORK_CATEGORIES,
    NetworkDiagnosis,
    NetworkDiagnosticsOrchestrator,
    sanitize_hostname_target,
)
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, create_default_registry
from ai.ollama_client import OllamaClient
from database.db import DatabaseManager
from database.repositories import DiagnosticRepository, SessionRepository


class TestHostnameSanitizer(unittest.TestCase):
    """Test suite for validating and sanitizing network target hostnames."""

    def test_valid_hostnames_and_ips(self) -> None:
        """Verify standard domain names, IP addresses, and intranet hostnames pass."""
        valid_targets = [
            "dns.google",
            "1.1.1.1",
            "8.8.8.8",
            "cloudflare.com",
            "router",
            "gateway",
            "localhost",
            "subdomain.example.co.uk",
        ]
        for tgt in valid_targets:
            ok, cleaned, err = sanitize_hostname_target(tgt)
            self.assertTrue(ok, f"Target '{tgt}' unexpectedly failed: {err}")
            self.assertEqual(cleaned, tgt)
            self.assertIsNone(err)

    def test_default_fallback_for_empty_target(self) -> None:
        """Verify empty or None targets default to dns.google."""
        ok1, cleaned1, _ = sanitize_hostname_target("")
        self.assertTrue(ok1)
        self.assertEqual(cleaned1, "dns.google")

        ok2, cleaned2, _ = sanitize_hostname_target(None)
        self.assertTrue(ok2)
        self.assertEqual(cleaned2, "dns.google")

    def test_reject_shell_metacharacters_and_injection(self) -> None:
        """Verify shell command tokens, pipes, and injection payloads are blocked."""
        malicious_targets = [
            "google.com; whoami",
            "1.1.1.1 && dir",
            "dns.google | powershell Get-Process",
            "`calc.exe`",
            "$(whoami).example.com",
            "google.com\nformat C:",
            "example.com > output.txt",
            "example.com < input.txt",
            "http://example.com/path",
            "1.1.1.1/24",
            "domain with spaces.com",
            "' OR '1'='1",
            '"-c whoami"',
        ]
        for mal in malicious_targets:
            ok, _, err = sanitize_hostname_target(mal)
            self.assertFalse(ok, f"Malicious target '{mal}' was not rejected!")
            self.assertIsNotNone(err)

    def test_reject_excessive_length(self) -> None:
        """Verify hostnames exceeding DNS standard (253 characters) are rejected."""
        long_host = "a" * 250 + ".example.com"
        ok, _, err = sanitize_hostname_target(long_host)
        self.assertFalse(ok)
        self.assertIn("exceeds maximum length", str(err))


class TestNetworkDiagnosticsOrchestrator(unittest.TestCase):
    """Test suite for network diagnostic scenario orchestration and evidence synthesis."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_net_diag.db"
        self.schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        self.db_manager = DatabaseManager(db_path=self.db_path, schema_path=self.schema_path)
        self.db_manager.init_db()

        self.registry = create_default_registry()
        self.safety_engine = SafetyEngine(registry=self.registry)
        self.mock_client = MagicMock(spec=OllamaClient)
        self.mock_client.is_available.return_value = False  # Test deterministic reasoning

        self.orchestrator = NetworkDiagnosticsOrchestrator(
            safety_engine=self.safety_engine,
            registry=self.registry,
            client=self.mock_client,
            db_mgr=self.db_manager,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_problem_classification(self) -> None:
        """Verify problem descriptions are mapped to standard network categories."""
        self.assertEqual(
            self.orchestrator.classify_network_problem("My Wi-Fi adapter is disconnected"),
            "adapter",
        )
        self.assertEqual(
            self.orchestrator.classify_network_problem("Cannot resolve domain names or DNS failure"),
            "dns",
        )
        self.assertEqual(
            self.orchestrator.classify_network_problem("DHCP is not giving me a valid IP address"),
            "ip_configuration",
        )
        self.assertEqual(
            self.orchestrator.classify_network_problem("Cannot reach server 192.168.1.1 on port 80"),
            "host_reachability",
        )
        self.assertEqual(
            self.orchestrator.classify_network_problem("Internet is offline and disconnected"),
            "connectivity",
        )
        self.assertEqual(
            self.orchestrator.classify_network_problem("Something is wrong with my computer"),
            "unknown",
        )

    def test_tool_selection_reuses_phase3_tools(self) -> None:
        """Verify tool selection produces valid requests matching registered Phase 3 tools."""
        for cat in NETWORK_CATEGORIES:
            tool_requests = self.orchestrator.select_diagnostic_tools(cat)
            self.assertTrue(len(tool_requests) >= 1)
            for req in tool_requests:
                registered = self.registry.get(req.tool_name)
                self.assertIsNotNone(
                    registered,
                    f"Selected tool '{req.tool_name}' is not in ToolRegistry",
                )
                self.assertEqual(registered.risk, RiskLevel.SAFE)
                self.assertTrue(registered.read_only)

    def test_scenario_no_internet_diagnosis(self) -> None:
        """Verify Scenario A: No Internet executes tools and returns evidence-based diagnosis."""
        diagnosis = self.orchestrator.run_network_diagnostics(
            problem_description="I have no internet connection on my PC."
        )
        self.assertIsInstance(diagnosis, NetworkDiagnosis)
        self.assertEqual(diagnosis.problem_category, "connectivity")
        self.assertTrue(len(diagnosis.observed_evidence) > 0)
        self.assertTrue(len(diagnosis.interpretation) > 0)
        self.assertTrue(len(diagnosis.recommended_next_steps) > 0)
        self.assertTrue(len(diagnosis.tool_results) >= 3)

        # Confirm all executed tools returned through SafetyEngine
        for tr in diagnosis.tool_results:
            self.assertIn("result", tr)
            self.assertIn("safety", tr["result"])
            self.assertTrue(tr["result"]["safety"]["allowed"])

    def test_scenario_dns_problem_diagnosis(self) -> None:
        """Verify Scenario B: DNS issue isolates DNS checks."""
        diagnosis = self.orchestrator.run_network_diagnostics(
            problem_description="Web browser says DNS_PROBE_FINISHED_NXDOMAIN"
        )
        self.assertEqual(diagnosis.problem_category, "dns")
        tool_names = [tr["tool_name"] for tr in diagnosis.tool_results]
        self.assertIn("get_dns_client_config", tool_names)
        self.assertIn("check_dns_resolution", tool_names)

    def test_scenario_adapter_issue_diagnosis(self) -> None:
        """Verify Scenario C: Wi-Fi / Adapter issue inspects adapter status."""
        diagnosis = self.orchestrator.run_network_diagnostics(
            problem_description="My Wi-Fi adapter is missing or disabled"
        )
        self.assertEqual(diagnosis.problem_category, "adapter")
        tool_names = [tr["tool_name"] for tr in diagnosis.tool_results]
        self.assertIn("get_network_adapters_diagnostics", tool_names)

    def test_scenario_host_reachability_with_custom_target(self) -> None:
        """Verify Scenario D: Custom host target is validated and checked."""
        diagnosis = self.orchestrator.run_network_diagnostics(
            problem_description="Cannot connect to internal server",
            custom_target="dns.google",
        )
        self.assertEqual(diagnosis.problem_category, "host_reachability")
        dns_reqs = [
            tr for tr in diagnosis.tool_results if tr["tool_name"] == "check_dns_resolution"
        ]
        self.assertEqual(len(dns_reqs), 1)
        self.assertEqual(dns_reqs[0]["arguments"]["hostname"], "dns.google")

    def test_sqlite_persistence_of_network_diagnosis(self) -> None:
        """Verify network diagnostic results are recorded into SQLite diagnostics table."""
        session_repo = SessionRepository(self.db_manager)
        session_repo.create(session_id="sess_net_001")

        diagnosis = self.orchestrator.run_network_diagnostics(
            problem_description="Network connectivity test",
            session_id="sess_net_001",
        )
        self.assertIsNotNone(diagnosis)

        diag_repo = DiagnosticRepository(self.db_manager)
        records = diag_repo.list_for_session("sess_net_001")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tool_name"], "network_diagnostics")
        self.assertEqual(records[0]["status"], "completed")


class TestPhase6SecurityAndStaticScan(unittest.TestCase):
    """Security verification ensuring no repair or command execution exists in Phase 6."""

    def test_no_forbidden_execution_imports_in_network_diagnostics(self) -> None:
        """Verify agent/network_diagnostics.py contains no subprocess, os.system, eval, or exec."""
        forbidden_patterns = [
            "subprocess",
            "os.system",
            "os.popen",
            "shell=True",
            "eval(",
            "exec(",
        ]

        mod = __import__("agent.network_diagnostics", fromlist=["*"])
        src = inspect.getsource(mod)
        for forbidden in forbidden_patterns:
            self.assertNotIn(
                forbidden,
                src,
                f"Forbidden execution pattern '{forbidden}' found in agent.network_diagnostics",
            )

    def test_no_network_repair_functions_implemented(self) -> None:
        """Verify Phase 6 does not implement or expose repair operations."""
        forbidden_repair_names = [
            "flush_dns",
            "reset_adapter",
            "reset_winsock",
            "release_dhcp",
            "renew_dhcp",
            "set_ip_address",
            "set_dns_server",
            "disable_adapter",
            "enable_adapter",
        ]

        mod = __import__("agent.network_diagnostics", fromlist=["*"])
        dir_members = dir(mod)
        for repair_fn in forbidden_repair_names:
            self.assertNotIn(
                repair_fn,
                dir_members,
                f"Repair function '{repair_fn}' must NOT be implemented in Phase 6!",
            )


if __name__ == "__main__":
    unittest.main()
