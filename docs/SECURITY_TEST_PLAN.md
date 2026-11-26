# WinFix AI — Security Test Plan
**Plan Version:** 1.0.0 (Pre-Pilot Distribution)
**Date:** 2026-11-26
**Auditor:** Antigravity AI Security Systems Agent
**Target:** WinFix AI Security Boundaries & Regression Testing

---

## 1. Overview & Objectives

This security test plan defines the automated, reproducible verification procedures to validate that all identified vulnerabilities, architectural invariants, and security controls in WinFix AI function correctly and prevent regression before pilot user deployment.

---

## 2. Test Execution Environment & Prerequisites

* **Operating System:** Windows 11 (64-bit AMD64).
* **Python Environment:** `.venv` with `pytest` installed.
* **Network Mode:** Air-gapped / Local Loopback Only (`127.0.0.1`).
* **Safety Constraint:** Test harnesses must execute in sandboxed environments or use mock handlers for MEDIUM-risk repair operations.

---

## 3. Detailed Security Test Specifications

### Suite 1: Network Listener & Binding Isolation
* **Test Case ID:** `SEC-TEST-NET-01`
* **Target:** `.streamlit/config.toml` & `winfix_launcher.py`
* **Test Method:** Automated configuration and CLI flag assertion.
* **Procedure:**
  1. Read `.streamlit/config.toml` and assert `server.address == "127.0.0.1"`.
  2. Parse `winfix_launcher.py` default arguments and assert `default == "127.0.0.1"`.
  3. In an isolated environment, launch `winfix_launcher.py --check-only` and verify loopback output.
* **Expected Outcome:** Default binding is strictly `127.0.0.1`.

---

### Suite 2: Packaging & Distribution Synchronization
* **Test Case ID:** `SEC-TEST-PKG-01`
* **Target:** `build/dist/WinFixAI/winfix_launcher.py`
* **Test Method:** File diff and SHA-256 integrity verification.
* **Procedure:**
  1. Compute SHA-256 of root `winfix_launcher.py`.
  2. Compute SHA-256 of `build/dist/WinFixAI/winfix_launcher.py`.
  3. Assert hashes are identical and line 114 does not contain `0.0.0.0`.
* **Expected Outcome:** Packaged distribution matches remediated source code.

---

### Suite 3: Path Separator Privacy Sanitization
* **Test Case ID:** `SEC-TEST-PRIV-01`
* **Target:** `production/logging.py` & `modes/tutor_context.py`
* **Test Method:** Unit test asserting username masking across both path styles.
* **Procedure:**
  ```python
  test_cases = [
      (r"C:\Users\JohnDoe\AppData\Local\Temp\error.log", r"C:\Users\<User>\AppData\Local\Temp\error.log"),
      ("C:/Users/JohnDoe/AppData/Local/Temp/error.log", "C:/Users/<User>/AppData/Local/Temp/error.log"),
      ("D:\\Users\\Alice\\Documents\\trace.txt", "D:\\Users\\<User>\\Documents\\trace.txt"),
      ("D:/Users/Alice/Documents/trace.txt", "D:/Users/<User>/Documents/trace.txt"),
  ]
  for input_path, expected in test_cases:
      assert sanitize_log_text(input_path) == expected
      assert sanitize_tutor_text(input_path) == expected
  ```
* **Expected Outcome:** 100% of Windows paths mask username regardless of separator type.

---

### Suite 4: Confirmation Token Anti-Replay & Parameter Binding
* **Test Case ID:** `SEC-TEST-TOK-01`
* **Target:** `agent/safety.py` & Domain Repair Orchestrators
* **Test Method:** Unit test in `tests/test_authorization_security.py`.
* **Procedure:**
  1. Generate proposal for `restart_bluetooth_service` with session ID `sess_001`.
  2. Extract `confirmation_token`.
  3. Execute via `safety_engine.execute(..., confirmation_token=token)` -> Must succeed.
  4. Attempt second execution with the same token -> Must return `error.code == "TOKEN_ALREADY_USED"`.
  5. Attempt execution with mutated argument dictionary -> Must return `error.code == "CONFIRMATION_REQUIRED"` or `TOKEN_REQUIRED`.
* **Expected Outcome:** Replay and tampered tokens are rejected atomically.

---

### Suite 5: Path Traversal Confinement
* **Test Case ID:** `SEC-TEST-PATH-01`
* **Target:** `production/paths.py:is_safe_app_path`
* **Test Method:** Path prefix collision test.
* **Procedure:**
  ```python
  from pathlib import Path
  from production.paths import is_safe_app_path

  root = Path("C:/AppData/WinFixAI")
  safe_child = Path("C:/AppData/WinFixAI/Data/winfix.db")
  sibling_prefix_attack = Path("C:/AppData/WinFixAI-backup/stolen.db")
  traversal_attack = Path("C:/AppData/WinFixAI/../Windows/System32")

  assert is_safe_app_path(safe_child, root) is True
  assert is_safe_app_path(sibling_prefix_attack, root) is False
  assert is_safe_app_path(traversal_attack, root) is False
  ```
* **Expected Outcome:** Prefix collisions evaluate strictly to `False`.

---

### Suite 6: ToolRegistry Fail-Closed Allowlist Invariant
* **Test Case ID:** `SEC-TEST-REG-01`
* **Target:** `agent/safety.py:evaluate`
* **Test Method:** Negative testing against prohibited commands.
* **Procedure:**
  ```python
  from agent.safety import default_safety_engine

  prohibited = ["cmd", "cmd.exe", "powershell", "powershell.exe", "bash", "sh", "format c:", "rmdir"]
  for tool in prohibited:
      decision = default_safety_engine.evaluate(tool, {})
      assert decision.allowed is False
      assert decision.blocked is True
  ```
* **Expected Outcome:** Unregistered tools fail closed immediately.

---

## 4. Regression Execution Commands

To execute the verified security regression test suite locally:

```powershell
# Core security and authorization suite
.\.venv\Scripts\python.exe -m pytest tests/test_authorization_security.py tests/test_security_boundaries.py tests/test_security_regression.py tests/test_troubleshooting_workflow_security.py tests/test_adaptive_security.py tests/test_ai_model_security.py tests/test_domain_troubleshooting_security.py tests/test_evaluation_security.py tests/test_installer_security.py tests/test_phase33_security.py tests/test_recovery_security.py tests/test_telemetry_security.py tests/test_verification_stress.py -v
```
