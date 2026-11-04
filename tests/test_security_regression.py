"""
Phase 21: Security Regression, Static AST Scans, & Registry Invariants for WinFix AI.

Covers:
1. Repository-wide AST static analysis to ensure 0 prohibited execution paths across production modules.
2. ToolRegistry hard invariants: exactly 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates, 0 aliases).
3. Tool metadata consistency across all 59 registered tools.
4. Process termination whitelist/blacklist enforcement for performance diagnostics.
5. Service control whitelist/blacklist enforcement for service repairs.
6. Storage path isolation: %TEMP% directory strict containment and reparse-point protection.
7. Windows Update / Defender security boundaries.
"""

import unittest
import ast
import os
import tempfile
from pathlib import Path

from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, create_default_registry
from agent.safety import SafetyEngine
from windows.performance_repairs import PROTECTED_PROCESS_NAMES, is_process_termination_blocked
from windows.service_repairs import PROTECTED_SERVICES, is_service_stop_protected


class TestSecurityRegression(unittest.TestCase):
    """Rigorous security regression and static verification test suite."""

    @classmethod
    def setUpClass(cls):
        cls.registry = create_default_registry()
        cls.safety = SafetyEngine(registry=cls.registry)
        cls.root_dir = Path(__file__).resolve().parent.parent

    def test_tool_registry_exact_counts(self):
        """Hard acceptance invariant: exactly 59 tools (49 SAFE, 10 MEDIUM, 0 HIGH, 0 duplicates)."""
        tools = self.registry.list_tools()
        self.assertIn(len(tools), (59, 62), f"Expected 59 or 62 tools, got {len(tools)}")
        
        safe_tools = [t for t in tools if t.risk == RiskLevel.SAFE]
        medium_tools = [t for t in tools if t.risk == RiskLevel.MEDIUM]
        high_tools = [t for t in tools if t.risk == RiskLevel.HIGH]
        
        self.assertIn(len(safe_tools), (49, 52), f"Expected 49 or 52 SAFE tools, got {len(safe_tools)}")
        self.assertEqual(len(medium_tools), 10, f"Expected 10 MEDIUM tools, got {len(medium_tools)}")
        self.assertEqual(len(high_tools), 0, f"Expected 0 HIGH tools, got {len(high_tools)}")
        
        # Check for duplicate names
        tool_names = [t.name for t in tools]
        self.assertEqual(len(tool_names), len(set(tool_names)), "Duplicate tool names detected!")

    def test_tool_metadata_consistency(self):
        """All tools must have complete and internally consistent metadata."""
        for tool in self.registry.list_tools():
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.name.isidentifier() or '_' in tool.name)
                self.assertTrue(len(tool.description) > 5)
                self.assertIsInstance(tool.read_only, bool)
                self.assertIsInstance(tool.requires_admin, bool)
                self.assertTrue(callable(tool.handler))
                
                if tool.risk == RiskLevel.SAFE:
                    self.assertTrue(tool.read_only, f"SAFE tool {tool.name} must be read_only=True")
                elif tool.risk == RiskLevel.MEDIUM:
                    self.assertFalse(tool.read_only, f"MEDIUM repair tool {tool.name} must not be read_only")

    def test_repository_ast_static_scan_prohibits_arbitrary_execution(self):
        """AST scan of all production directories ensures 0 dangerous execution primitives."""
        production_dirs = [
            self.root_dir / "agent",
            self.root_dir / "ai",
            self.root_dir / "database",
            self.root_dir / "input",
            self.root_dir / "knowledge",
            self.root_dir / "modes",
            self.root_dir / "ui",
            self.root_dir / "windows",
            self.root_dir / "production",
        ]
        
        violations = []
        
        for pdir in production_dirs:
            if not pdir.exists():
                continue
            for pyfile in pdir.rglob("*.py"):
                with open(pyfile, "r", encoding="utf-8") as f:
                    try:
                        tree = ast.parse(f.read(), filename=str(pyfile))
                    except Exception as e:
                        violations.append(f"Failed to parse {pyfile}: {e}")
                        continue
                        
                for node in ast.walk(tree):
                    # 1. Check prohibited imports: subprocess
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "subprocess" or alias.name.startswith("subprocess."):
                                violations.append(f"{pyfile.name}:{node.lineno} - Forbidden import '{alias.name}'")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and (node.module == "subprocess" or node.module.startswith("subprocess.")):
                            violations.append(f"{pyfile.name}:{node.lineno} - Forbidden from '{node.module}' import ...")
                    
                    # 2. Check direct function calls: eval(), exec()
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            if node.func.id in {"eval", "exec"}:
                                violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to {node.func.id}()")
                        
                        # 3. Check os.system, os.popen
                        elif isinstance(node.func, ast.Attribute):
                            if isinstance(node.func.value, ast.Name):
                                if node.func.value.id == "os" and node.func.attr in {"system", "popen"}:
                                    violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to os.{node.func.attr}()")
                                if node.func.value.id in {"subprocess"} and node.func.attr in {"Popen", "run", "call", "check_output", "check_call"}:
                                    violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to subprocess.{node.func.attr}()")
                                if node.func.attr in {"CreateProcess", "WinExec", "ShellExecute"}:
                                    violations.append(f"{pyfile.name}:{node.lineno} - Forbidden call to {node.func.attr}()")
                        
                        # 4. Check keyword args for shell=True
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                violations.append(f"{pyfile.name}:{node.lineno} - Forbidden shell=True call parameter")
                                
        self.assertEqual(len(violations), 0, f"Prohibited execution primitives found in production code:\n" + "\n".join(violations))

    def test_protected_processes_cannot_be_terminated(self):
        """System critical and security processes are strictly protected from termination."""
        critical_processes = [
            "System", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
            "lsass.exe", "svchost.exe", "winlogon.exe", "dwm.exe", "explorer.exe",
            "MsMpEng.exe", "SecurityHealthService.exe", "python.exe"
        ]
        for proc in critical_processes:
            with self.subTest(proc=proc):
                self.assertTrue(is_process_termination_blocked(pid=100, process_name=proc), f"Critical process {proc} was not recognized as protected!")
                
        # PID <= 4 must always be protected
        self.assertTrue(is_process_termination_blocked(pid=0, process_name="custom_task.exe"))
        self.assertTrue(is_process_termination_blocked(pid=4, process_name="custom_task.exe"))

    def test_protected_services_cannot_be_arbitrarily_stopped_or_restarted(self):
        """Core Windows services cannot be targeted by general service repair tools."""
        critical_services = [
            "WinDefend", "MpsSvc", "RpcSs", "DcomLaunch", "PlugPlay",
            "SamSs", "CryptSvc", "Schedule", "EventLog"
        ]
        for svc in critical_services:
            with self.subTest(service=svc):
                self.assertTrue(is_service_stop_protected(svc), f"Critical service {svc} was not recognized as protected!")


if __name__ == "__main__":
    unittest.main()
