"""WinFix AI — Security Regression & AST Prohibited Call Scan (Phase 33)."""

import ast
from pathlib import Path
import pytest
from tests.reliability.assertions import assert_security_invariants


def test_hard_security_invariants():
    """Assert all 59 tools, zero aliases, and risk gates are preserved."""
    assert_security_invariants()


def test_repository_wide_ast_prohibited_calls():
    """Scan all python files in the entire project for prohibited execution calls."""
    scanned_dirs = [
        Path("agent"),
        Path("ai"),
        Path("database"),
        Path("input"),
        Path("knowledge"),
        Path("modes"),
        Path("production"),
        Path("ui"),
        Path("windows"),
    ]

    violations = []

    for d in scanned_dirs:
        if not d.exists():
            continue
        for py_file in d.glob("**/*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            for node in ast.walk(tree):
                # 1. Prohibited imports: subprocess
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "subprocess" or alias.name.startswith("subprocess."):
                            violations.append(f"{py_file}:{node.lineno} -> import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and (node.module == "subprocess" or node.module.startswith("subprocess.")):
                        violations.append(f"{py_file}:{node.lineno} -> from {node.module} import")

                # 2. Direct calls: eval, exec
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in {"eval", "exec"}:
                            violations.append(f"{py_file}:{node.lineno} -> {node.func.id}()")
                    elif isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            if node.func.value.id == "os" and node.func.attr in {"system", "popen"}:
                                violations.append(f"{py_file}:{node.lineno} -> os.{node.func.attr}()")
                            if node.func.value.id == "subprocess" and node.func.attr in {"Popen", "run", "call", "check_output", "check_call"}:
                                violations.append(f"{py_file}:{node.lineno} -> subprocess.{node.func.attr}()")
                        if node.func.attr in {"CreateProcess", "WinExec", "ShellExecute"}:
                            violations.append(f"{py_file}:{node.lineno} -> {node.func.attr}()")

                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            violations.append(f"{py_file}:{node.lineno} -> shell=True")

    assert len(violations) == 0, f"Prohibited AST calls detected: {violations}"
