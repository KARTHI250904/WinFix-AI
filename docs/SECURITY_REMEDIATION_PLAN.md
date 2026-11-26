# WinFix AI — Security Remediation Plan
**Plan Version:** 1.0.0 (Pre-Pilot Distribution)
**Date:** 2026-11-26
**Auditor:** Antigravity AI Security Systems Agent
**Status:** PROPOSED — PENDING EXPLICIT USER APPROVAL

> [!IMPORTANT]
> This plan is proposed for review. Per security instructions, no source code, configuration, or packaging modifications have been made during this assessment. Fixes will only be executed after explicit user approval.

---

## 1. Prioritized Remediation Roadmap

| Priority | Finding ID | Severity | Remediation Target | Estimated Effort | Release Blocker |
|---|---|:---:|---|:---:|:---:|
| **P1** | **WF-SEC-01** | **HIGH** | Rebuild `build/dist/WinFixAI` & sync launcher | 10 mins | **YES** |
| **P2** | **WF-SEC-02** | **MEDIUM** | Dual-separator regex in `modes/tutor_context.py` | 5 mins | **NO** |
| **P3** | **WF-SEC-04** | **LOW** | Path confinement via `is_relative_to` in `production/paths.py` | 5 mins | **NO** |
| **P4** | **WF-SEC-03** | **MEDIUM** | Route Autopilot repair steps via domain orchestrators | 20 mins | **NO** |
| **P5** | **WF-SEC-05** | **LOW** | Pin production dependencies in `requirements.txt` | 10 mins | **NO** |
| **P6** | **WF-SEC-06** | **NEEDS_VAL**| Perform sandboxed runtime listener validation | 15 mins | **NO** |

---

## 2. Detailed Technical Fix Specifications

### Fix P1: Rebuild Distribution Directory to Synchronize Commit 9fa4f73 (WF-SEC-01)

* **Objective:** Eliminate the stale `0.0.0.0` default in `build/dist/WinFixAI/winfix_launcher.py`.
* **Action:**
  1. Execute `python build/build_windows.py` using the current `security-remediation` branch.
  2. Verify that `build/dist/WinFixAI/winfix_launcher.py` contains:
     ```python
     parser.add_argument("--host", default="127.0.0.1", help="Host address to bind the UI server to (default: 127.0.0.1 for Localhost)")
     ```
  3. Recompute SHA-256 sums in `build/artifacts/SHA256SUMS.txt`.
* **Verification Command:**
  ```powershell
  git diff --no-index winfix_launcher.py build/dist/WinFixAI/winfix_launcher.py
  ```
  Expected output: No diff on line 109 (`--host` default).

---

### Fix P2: Update Path Separator Regex in `modes/tutor_context.py` (WF-SEC-02)

* **Objective:** Mask Windows usernames in paths formatted with forward slashes (`/`) within Personal Tutor and Voice prompts.
* **Target File:** `modes/tutor_context.py` (Line 15)
* **Code Modification:**
  ```python
  # Replace line 15:
  USER_PATH_PATTERN = re.compile(r"([a-zA-Z]:\\Users\\)[^\\]+(\\.*)?", re.IGNORECASE)

  # With dual-separator regex matching production/logging.py:
  USER_PATH_PATTERN = re.compile(r"([a-zA-Z]:[/\\\\]Users[/\\\\])[^/\\\\]+([/\\\\].*)?", re.IGNORECASE)
  ```
* **Verification Command:**
  ```powershell
  .\.venv\Scripts\python.exe -c "from modes.tutor_context import sanitize_tutor_text; assert sanitize_tutor_text('C:/Users/SecretUser/data') == 'C:/Users/<User>/data'; print('P2 Verified!')"
  ```

---

### Fix P3: Strengthen Path Confinement in `production/paths.py` (WF-SEC-04)

* **Objective:** Prevent directory prefix collisions (`WinFixAI-malicious`) in `is_safe_app_path`.
* **Target File:** `production/paths.py` (Line 105)
* **Code Modification:**
  ```python
  # Replace line 105:
  return str(resolved_target).startswith(str(resolved_root))

  # With native Python 3.9+ path confinement:
  return resolved_target.is_relative_to(resolved_root)
  ```
* **Verification Command:**
  ```powershell
  .\.venv\Scripts\python.exe -c "from pathlib import Path; from production.paths import is_safe_app_path; assert not is_safe_app_path(Path('C:/App-evil'), Path('C:/App')); print('P3 Verified!')"
  ```

---

### Fix P4: Route Autopilot Repair Steps via Domain Orchestrators (WF-SEC-03)

* **Objective:** Ensure all MEDIUM-risk tools executed by Autopilot obtain parameter-bound tokens and validate argument schemas via domain orchestrators rather than synthesizing ad-hoc tokens.
* **Target File:** `modes/autopilot.py` (Lines 1283-1345)
* **Code Modification:**
  - Route `clean_user_temp_cache` through `default_storage_repairs_orchestrator.execute_confirmed_repair()`.
  - Route service restart actions through `default_service_repairs_orchestrator.execute_confirmed_repair()`.
  - In `agent/safety.py:execute()`, require `confirmation_token is not None` whenever `tool.risk == RiskLevel.MEDIUM`.
* **Verification Command:**
  Run `pytest tests/test_autopilot.py tests/test_authorization_security.py -v`.

---

### Fix P5: Pin Production Dependencies in `requirements.txt` (WF-SEC-05)

* **Objective:** Guarantee deterministic, reproducible dependency resolution for pilot distribution.
* **Target File:** `requirements.txt`
* **Code Modification:**
  Pin all top-level direct packages to their verified versions:
  ```text
  streamlit==1.39.0
  ollama==0.3.3
  psutil==6.0.0
  pywin32==308
  faster-whisper==1.0.3
  av==13.0.0
  pyyaml==6.0.2
  pillow==10.4.0
  ```

---

### Validation Step P6: OS-Enforced Runtime Listener Isolation (WF-SEC-06)

* **Objective:** Empirically prove that Streamlit and Ollama bind exclusively to `127.0.0.1` and dual-stack `::` LAN exposure is absent.
* **Procedure:**
  1. Launch WinFix AI in an isolated test harness:
     ```powershell
     .\.venv\Scripts\python.exe winfix_launcher.py --headless
     ```
  2. Inspect listening TCP ports:
     ```powershell
     Get-NetTCPConnection -LocalPort 8501, 11434 | Select-Object LocalAddress, LocalPort, State
     ```
  3. Confirm `LocalAddress` is strictly `127.0.0.1`.
  4. Attempt connection from another host on LAN -> Verify connection refused.
