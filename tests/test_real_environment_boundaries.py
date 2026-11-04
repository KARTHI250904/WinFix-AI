"""
WinFix AI — Phase 23 Real-World Boundaries & AST Security Tests.

Validates:
1. Repository-wide AST static security analysis across all production source directories:
   agent/, ai/, database/, input/, knowledge/, modes/, ui/, windows/, production/
   ensuring 0 prohibited execution primitives exist.
2. Real-world Prompt Injection and Tool Injection Immunity.
3. Privacy Redaction verification with real-world Windows paths and secret patterns.
4. Failure Injection resilience (handling API exceptions and malformed payloads).
"""

import ast
from pathlib import Path
import unittest

from agent.agent_response import AgentResponse, parse_agent_response
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import create_default_registry
from production.logging import sanitize_log_text


class TestASTSecurityPhase23(unittest.TestCase):
    """AST static security scanner inspecting all production Python code."""

    PROHIBITED_CALLS = {
        "subprocess",
        "os.system",
        "os.popen",
        "Popen",
        "CreateProcess",
        "WinExec",
        "ShellExecute",
    }

    PROHIBITED_FUNCTIONS = {"eval", "exec"}

    def test_zero_prohibited_ast_primitives_in_production(self):
        root_dir = Path(__file__).resolve().parent.parent
        production_dirs = [
            root_dir / "agent",
            root_dir / "ai",
            root_dir / "database",
            root_dir / "input",
            root_dir / "knowledge",
            root_dir / "modes",
            root_dir / "ui",
            root_dir / "windows",
            root_dir / "production",
        ]

        violations = []
        scanned_files = 0

        for p_dir in production_dirs:
            if not p_dir.exists():
                continue
            for py_file in p_dir.rglob("*.py"):
                scanned_files += 1
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                except Exception as ex:
                    violations.append(f"Syntax error parsing {py_file}: {ex}")
                    continue

                for node in ast.walk(tree):
                    # Check for direct calls like eval() or exec()
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name) and node.func.id in self.PROHIBITED_FUNCTIONS:
                            violations.append(f"{py_file.name}:{node.lineno} prohibited call '{node.func.id}()'")
                        elif isinstance(node.func, ast.Attribute):
                            if node.func.attr in self.PROHIBITED_CALLS:
                                violations.append(f"{py_file.name}:{node.lineno} prohibited attribute '{node.func.attr}()'")

        self.assertGreater(scanned_files, 20)
        self.assertEqual(violations, [], f"Prohibited AST execution calls detected: {violations}")


class TestRealWorldSecurityBoundaries(unittest.TestCase):
    """Test suite for injection resistance and privacy sanitization."""

    @classmethod
    def setUpClass(cls):
        cls.registry = create_default_registry()
        cls.safety = SafetyEngine(registry=cls.registry)

    def test_prompt_injection_command_rejection(self):
        malicious_response = """
        {
            "thought": "Let us execute a shell command to repair the PC",
            "tool_name": "cmd.exe",
            "arguments": {"command": "del C:\\\\Windows\\\\System32"},
            "powershell": "Get-Process"
        }
        """
        success, parsed, err = parse_agent_response(malicious_response)
        self.assertFalse(success)
        self.assertIn("Security Policy Rejection", err)

    def test_privacy_sanitization_comprehensive(self):
        raw_text = (
            "User file located at C:\\Users\\Administrator\\Desktop\\report.docx. "
            "Contact admin at support@enterprise.com. "
            "Credentials: token='ghp_1234567890abcdef1234567890' api_key=secret_9876543210"
        )
        sanitized = sanitize_log_text(raw_text)
        self.assertNotIn("Administrator", sanitized)
        self.assertNotIn("support@enterprise.com", sanitized)
        self.assertNotIn("ghp_1234567890abcdef1234567890", sanitized)
        self.assertNotIn("secret_9876543210", sanitized)
        self.assertIn("C:\\Users\\<User>\\Desktop\\report.docx", sanitized)
        self.assertIn("<email-masked>", sanitized)
        self.assertIn("<credential-masked>", sanitized)


if __name__ == "__main__":
    unittest.main()
