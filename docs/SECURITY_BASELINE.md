# WinFix AI — Security Baseline Report
**Audit Version:** 1.0.0 (Pre-Pilot Distribution)
**Date:** 2026-11-26
**Auditor:** Antigravity AI Security Systems Agent
**Active Git Branch:** `security-remediation`
**Active Commit SHA:** `9fa4f73285e34dafed3923ee44896a5fc4310ff9`
**Baseline Commit SHA:** `9d5fa4bc889b83048d8c7bd402ef2a438128c7cf`
**Presence of 9fa4f73:** VERIFIED (Current HEAD)

---

## 1. Executive Security Baseline

WinFix AI is an offline-first Windows troubleshooting assistant designed to assist nontechnical users in diagnosing and repairing common operating system problems without internet connectivity.

This document establishes the verified, evidence-based security baseline of the actual repository state on branch `security-remediation` prior to real-user pilot deployment.

### System Verification State
- **Operating System:** Windows 11 Home Single Language (Build 10.0.26300, 64-bit AMD64).
- **Python Runtime:** Python 3.14.2 (AMD64) in isolated `.venv`.
- **Local AI Engines:** Ollama runtime over IPv4 loopback (`http://127.0.0.1:11434`), Gemma 4 12B (`gemma4:12b`), Moondream (`moondream:latest`), and Faster-Whisper (`base.en`).
- **Database Engine:** SQLite 3 with Write-Ahead Logging (WAL), foreign key enforcement (`PRAGMA foreign_keys = ON`), and 100% parameterized SQL.

---

## 2. Core Security Invariants

WinFix AI enforces strict architectural separation between untrusted inputs, local AI models, and the host operating system:

```text
+------------------------------------------------------------------------+
| UNTRUSTED INPUTS                                                       |
| Written text, UI controls, Screenshots (Moondream), Audio (Whisper)   |
+------------------------------------------------------------------------+
                                   |
                                   v
+------------------------------------------------------------------------+
| LOCAL AI REASONING (Ollama / Gemma 4 / Local Heuristics)              |
| LLM != Windows Shell                                                   |
| LLM != Arbitrary Python                                                |
| Model outputs are parsed strictly as structured JSON candidate intents |
+------------------------------------------------------------------------+
                                   |
                                   v
+------------------------------------------------------------------------+
| SAFETY ENGINE & ALLOWLIST GATING                                      |
| 1. ToolRegistry lookup: Unregistered tools FAIL CLOSED immediately     |
| 2. Parameter schema validation: Bounds, types, forbidden characters   |
| 3. Risk Policy:                                                        |
|    - HIGH: Strictly prohibited (0 registered)                         |
|    - MEDIUM: Requires explicit confirmation token & anti-replay lock  |
|    - SAFE: Read-only diagnostic tools allowed automatically            |
+------------------------------------------------------------------------+
                                   |
                                   v
+------------------------------------------------------------------------+
| HARDCODED WINDOWS EXECUTION LAYER                                      |
| Native Win32 C-APIs (ctypes), psutil, win32service, win32evtlog       |
| ZERO subprocess shell calls, ZERO arbitrary PowerShell scripts         |
+------------------------------------------------------------------------+
```

---

## 3. Tool Registry Baseline Inventory

Dynamic introspection of `default_tool_registry` confirms exact tool counts:

* **Total Registered Tools:** 62
* **SAFE (Read-Only Diagnostics):** 52 tools
* **MEDIUM (Controlled Reversible Repairs):** 10 tools
* **HIGH (Destructive / Security Lowering):** 0 tools
* **Duplicate Tool Names:** 0
* **Aliases / Bypasses:** 0

### Approved Repair Operations (10 MEDIUM Tools)
| Tool Name | Native Handler | Requires Admin | Verification Tool |
|---|---|:---:|---|
| `flush_dns_cache` | `windows.network_repairs.flush_dns_cache` (`dnsapi.dll!DnsFlushResolverCache`) | No | `check_dns_resolution` |
| `renew_dhcp_lease` | `windows.network_repairs.renew_dhcp_lease` (`iphlpapi.dll!IpRenewAddress`) | Yes | `check_internet_connectivity` |
| `terminate_user_process` | `windows.performance_repairs.terminate_user_process` (`psutil.Process.terminate`) | No | `get_process_details` |
| `clean_user_temp_cache` | `windows.performance_repairs.clean_user_temp_cache` (`os.scandir` + `unlink`) | No | `get_temp_storage_info` |
| `start_service` | `windows.service_repairs.start_service` (`win32serviceutil.StartService`) | Yes | `get_service_status` |
| `stop_service` | `windows.service_repairs.stop_service` (`win32serviceutil.StopService`) | Yes | `get_service_status` |
| `restart_service` | `windows.service_repairs.restart_service` (`win32serviceutil.RestartService`) | Yes | `get_service_status` |
| `restart_bluetooth_service` | `windows.bluetooth_repairs.restart_bluetooth_service` (`win32serviceutil.RestartService`) | Yes | `get_service_status` |
| `restart_windows_update_service` | `windows.windows_update_repairs.restart_windows_update_service` (`win32serviceutil.RestartService`) | Yes | `get_service_status` |
| `restart_defender_service` | `windows.windows_defender_repairs.restart_defender_service` (`win32serviceutil.RestartService`) | Yes | `get_service_status` |

---

## 4. Test Suite Baseline Evidence

Execution of the core security, authorization, and repair regression suite against the active commit (`9fa4f73`) yielded:

* **Command:** `pytest tests/test_authorization_security.py ... (13 test files) -q`
* **Result:** **81 passed, 132 subtests passed (239 test assertions) in 33.72s** (Exit code `0`).
* **Test Coverage:**
  - Mandatory confirmation token validation.
  - Parameter tampering rejection.
  - Atomic one-time token consumption (anti-replay).
  - Missing and empty token failure closed.
  - Fail-closed behavior on unregistered tool names (`cmd.exe`, `powershell`, etc.).
  - Privacy sanitization across forward and backslash path formats.

---

## 5. Cloudflare Audit Remediation Status

| Audit Observation | Target Control | Remediation State | Empirical Finding |
|---|---|:---:|---|
| `winfix-lan-unauth-access-001` | Default to `127.0.0.1` loopback binding | **REMEDIATED (Source) / DRIFT (Build Dist)** | `.streamlit/config.toml` and root `winfix_launcher.py` enforce `127.0.0.1`. However, pre-existing build distribution directory `build/dist/WinFixAI/winfix_launcher.py` retains stale `0.0.0.0` default. |
| `winfix-token-design-gap-002` | Parameter-bound single-use confirmation tokens | **REMEDIATED (Source) / ARCHITECTURAL GAPS** | Tokens in repair orchestrators bind `tool_name`, `arguments`, and `session_id`. `SafetyEngine` enforces atomic single-use anti-replay. Tokens remain unkeyed SHA-256 digests. Autopilot bypasses domain orchestrators for certain tools by synthesizing ad-hoc tokens. |
| `winfix-log-separator-leak-004` | Sanitize Windows paths with forward & backward slashes | **REMEDIATED (Logging) / DRIFT (Tutor Context)** | `production/logging.py` was updated with dual-separator regex `r"([a-zA-Z]:[/\\\\]Users[/\\\\])[^/\\\\]+([/\\\\].*)?"`. However, `modes/tutor_context.py` still contains single-separator regex. |

---

## 6. Static Code Execution Primitive Scan

An exhaustive regex search across all application packages (`agent/`, `ai/`, `windows/`, `database/`, `production/`, `input/`, `modes/`, `ui/`, `app.py`, `winfix_launcher.py`) for dangerous execution sinks yielded:

- `os.system`: **0 occurrences**
- `os.popen`: **0 occurrences**
- `shell=True`: **0 occurrences**
- `eval()`: **0 occurrences**
- `exec()`: **0 occurrences**
- `CreateProcess`: **0 occurrences**
- `WinExec`: **0 occurrences**
- `ShellExecute`: **0 occurrences**
- `subprocess`: **1 occurrence strictly bounded in `winfix_launcher.py`**:
  ```python
  cmd = [sys.executable, "-m", "streamlit", "run", str(app_py), "--server.port", str(port), "--server.address", str(host), "--browser.gatherUsageStats", "false"]
  proc = subprocess.run(cmd)
  ```
All other matches of strings like `powershell`, `cmd.exe`, `subprocess`, etc., are in explicit input rejection blocklists and defense-in-depth prompt filters.
