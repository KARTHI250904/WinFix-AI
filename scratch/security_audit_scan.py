"""Comprehensive Source-Level Security Audit Script for WinFix AI (Phase 14)."""

import ast
import os

FORBIDDEN_CALLS = {
    "os.system",
    "os.popen",
    "eval",
    "exec",
    "ClearEventLog",
    "TerminateProcess",
    "taskkill",
}

FORBIDDEN_ATTRIBUTES = {
    "SetValue",
    "SetValueEx",
    "DeleteValue",
    "DeleteKey",
    "CreateKey",
    "CreateKeyEx",
}

FORBIDDEN_IMPORTS = {
    "subprocess",
    "shutil",
}

app_dirs = ["windows", "agent", "ai", "database", "modes", "input", "knowledge"]
app_files = ["app.py", "config.py"]

for d in app_dirs:
    if os.path.exists(d):
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".py"):
                    app_files.append(os.path.join(root, f))

violations = []

for file_path in app_files:
    if not os.path.exists(file_path):
        continue
    with open(file_path, "r", encoding="utf-8") as fh:
        try:
            tree = ast.parse(fh.read(), filename=file_path)
        except Exception as e:
            violations.append((file_path, 0, f"Parse error: {e}"))
            continue

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTS:
                    violations.append((file_path, getattr(node, "lineno", 0), f"Forbidden import: {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module in FORBIDDEN_IMPORTS:
                violations.append((file_path, getattr(node, "lineno", 0), f"Forbidden import-from: {node.module}"))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                violations.append((file_path, getattr(node, "lineno", 0), f"Forbidden function call: {node.func.id}()"))
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in FORBIDDEN_ATTRIBUTES:
                    violations.append((file_path, getattr(node, "lineno", 0), f"Forbidden attribute call: .{node.func.attr}()"))
                if isinstance(node.func.value, ast.Name) and node.func.value.id in ("os", "sys", "subprocess"):
                    full_call = f"{node.func.value.id}.{node.func.attr}"
                    if full_call in FORBIDDEN_CALLS:
                        violations.append((file_path, getattr(node, "lineno", 0), f"Forbidden call: {full_call}()"))

print(f"Scanned {len(app_files)} application source files.")
print(f"Total Application Code Security Violations Found: {len(violations)}")
for v in violations:
    print(f"  [VIOLATION] {v[0]}:{v[1]} - {v[2]}")
