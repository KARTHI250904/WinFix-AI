# WinFix AI — Security Findings & Vulnerability Register
**Register Version:** 1.0.0 (Pre-Pilot Distribution)
**Date:** 2026-11-26
**Auditor:** Antigravity AI Security Systems Agent
**Active Git Branch:** `security-remediation` (`9fa4f73285e34dafed3923ee44896a5fc4310ff9`)

---

## 1. Executive Findings Summary

| Finding ID | Title | Severity | Affected Area | Release Blocker |
|---|---|:---:|---|:---:|
| **WF-SEC-01** | Stale Pre-Remediation Build/Dist Artifacts in Inno Setup Packaging | **HIGH** | `build/dist/WinFixAI/winfix_launcher.py:114` | **YES** |
| **WF-SEC-02** | Forward-Slash Path Separator Privacy Leak in Tutor Context | **MEDIUM** | `modes/tutor_context.py:15` | **NO** |
| **WF-SEC-03** | Confirmation Token Architecture Bypass via Autopilot Synthesis | **MEDIUM** | `modes/autopilot.py:1284,1308,1337` | **NO** |
| **WF-SEC-04** | Path Traversal Prefix Collision Weakness in Path Validator | **LOW** | `production/paths.py:105` | **NO** |
| **WF-SEC-05** | Unpinned Dependencies in Production Manifest | **LOW** | `requirements.txt:1-8` | **NO** |
| **WF-SEC-06** | OS-Enforced Runtime Listener Isolation Remains Pending | **NEEDS_VALIDATION** | Runtime Streamlit Listener | **NO** |

---

## 2. Detailed Vulnerability Reports

### Finding WF-SEC-01: Stale Pre-Remediation Build/Dist Artifacts in Inno Setup Packaging

* **Severity:** **HIGH**
* **Release-Blocking Status:** **YES**
* **Affected File & Line:**
  - `build/dist/WinFixAI/winfix_launcher.py` (Line 114)
  - `build/artifacts/winfix_setup.iss` (Line 22)
* **Entry Point:** Inno Setup installer compilation and execution of distributed launcher.
* **Attacker Prerequisites:** Network adjacency (LAN) to victim machine running an installed distribution of WinFix AI.
* **Attack Scenario:**
  1. A project administrator compiles `build/artifacts/winfix_setup.iss` using Inno Setup.
  2. Line 22 copies all files from `build/dist/WinFixAI\*` into the installation bundle.
  3. `build/dist/WinFixAI` was generated prior to Phase 11 security remediations. Line 114 of `build/dist/WinFixAI/winfix_launcher.py` still contains:
     ```python
     parser.add_argument("--host", default="0.0.0.0", help="Host address to bind the UI server to (default: 0.0.0.0 for Local & LAN)")
     ```
  4. When an end-user installs and launches WinFix AI from this installer, the Streamlit server binds to `0.0.0.0:8501`.
  5. Any unauthenticated device on the local network connects to `http://<victim-ip>:8501`, gaining full access to the diagnostic UI and repair actions.
* **Potential Impact:** Complete regression of Cloudflare finding `winfix-lan-unauth-access-001`, exposing the user's desktop troubleshooting interface to LAN adversaries.
* **Existing Protections:** The root source version of `winfix_launcher.py` and `.streamlit/config.toml` enforce `127.0.0.1`, but the packaged distribution directory was not re-built after commit `9fa4f73`.
* **Reproduction Evidence:**
  Running `git diff --no-index winfix_launcher.py build/dist/WinFixAI/winfix_launcher.py` shows:
  ```diff
  -    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind the UI server to (default: 127.0.0.1 for Localhost)")
  +    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind the UI server to (default: 0.0.0.0 for Local & LAN)")
  ```
* **Recommended Remediation:**
  Execute `python build/build_windows.py` to overwrite `build/dist/WinFixAI` with the updated commit `9fa4f73` files, ensuring all distribution artifacts default strictly to `127.0.0.1`.
* **Regression Test Required:**
  Automated build test comparing SHA-256 hashes of root launcher and packaged launcher.

---

### Finding WF-SEC-02: Forward-Slash Path Separator Privacy Leak in Tutor Context

* **Severity:** **MEDIUM**
* **Release-Blocking Status:** **NO**
* **Affected File & Line:** `modes/tutor_context.py` (Line 15)
* **Entry Point:** Personal Tutor and Voice diagnostic reasoning context pipelines.
* **Attacker Prerequisites:** System diagnostics or error paths containing forward slashes (`/`), such as POSIX paths or Python `Path.as_posix()` outputs.
* **Attack Scenario:**
  1. Commit `9fa4f73` remediated `winfix-log-separator-leak-004` in `production/logging.py` by updating `USER_PATH_PATTERN` to `re.compile(r"([a-zA-Z]:[/\\\\]Users[/\\\\])[^/\\\\]+([/\\\\].*)?", re.IGNORECASE)`.
  2. However, an un-synchronized duplicate implementation of `USER_PATH_PATTERN` exists in `modes/tutor_context.py` line 15:
     ```python
     USER_PATH_PATTERN = re.compile(r"([a-zA-Z]:\\Users\\)[^\\]+(\\.*)?", re.IGNORECASE)
     ```
  3. When diagnostic text containing forward-slash paths (e.g. `C:/Users/Alice/AppData/Local/Temp/log.txt`) passes through `sanitize_tutor_text()` or `sanitize_tutor_payload()`, the regex fails to match.
  4. The unmasked username (`Alice`) is forwarded directly to the LLM reasoning prompt and saved in the tutor conversation history.
* **Potential Impact:** Unintended disclosure of the Windows user's personal account name to the LLM context and session records.
* **Existing Protections:** Logging to disk via `production/logging.py` masks the path correctly, but the in-memory tutor context and prompt payload remain unmasked.
* **Reproduction Evidence:**
  Executing `modes/tutor_context.py:sanitize_tutor_text("C:/Users/SecretUser/data")` returns `"C:/Users/SecretUser/data"` (unmasked), whereas `production/logging.py:sanitize_log_text("C:/Users/SecretUser/data")` returns `"C:/Users/<User>/data"` (masked).
* **Recommended Remediation:**
  Update line 15 of `modes/tutor_context.py` to use `re.compile(r"([a-zA-Z]:[/\\\\]Users[/\\\\])[^/\\\\]+([/\\\\].*)?", re.IGNORECASE)` or import `sanitize_log_text` directly from `production.logging`.
* **Regression Test Required:**
  Unit test asserting `sanitize_tutor_text("C:/Users/test/folder") == "C:/Users/<User>/folder"`.

---

### Finding WF-SEC-03: Confirmation Token Architecture Bypass via Autopilot Synthesis

* **Severity:** **MEDIUM**
* **Release-Blocking Status:** **NO**
* **Affected File & Line:**
  - `modes/autopilot.py` (Lines 1284, 1308, 1337)
  - `agent/safety.py` (Line 211)
* **Entry Point:** Autopilot multi-step execution loop (`_execute_single_step`).
* **Attacker Prerequisites:** User initiates an Autopilot session for storage cleanup or generic service restart.
* **Attack Scenario:**
  1. For several MEDIUM-risk repair tools (`clean_user_temp_cache`, `restart_service`, `stop_service`, `restart_bluetooth_service`), `modes/autopilot.py` bypasses the domain repair orchestrators (`StorageRepairsOrchestrator`, `ServiceRepairsOrchestrator`).
  2. Instead of obtaining an argument-bound token via `proposal.generate_confirmation_token()`, Autopilot synthesizes its own token string:
     ```python
     token = f"tok_{session_id}_{tool_name}_{time.time()}"
     raw_out = self.safety_engine.execute(
         tool_name=tool_name,
         arguments=step.arguments,
         session_id=session_id,
         user_confirmed=True,
         confirmation_token=token,
     )
     ```
  3. In `agent/safety.py`, line 211 only checks whether `confirmation_token` has been previously consumed in `_consumed_tokens`. It does not verify argument bindings or cryptographic integrity.
* **Potential Impact:** Inconsistency in authorization enforcement: repair orchestrator argument-binding checks are circumvented in Autopilot mode.
* **Existing Protections:** The user must explicitly approve the entire Autopilot plan in the UI by clicking "🛡 Authorize & Run Autopilot Plan", which verifies `plan.plan_hash`. Tools executed are still strictly constrained to registered allowlisted handlers.
* **Reproduction Evidence:**
  Lines 1284, 1308, and 1337 of `modes/autopilot.py` show direct synthesis of `f"tok_{session_id}_{tool_name}_{time.time()}"`.
* **Recommended Remediation:**
  Route all MEDIUM repair tools in Autopilot through their respective domain repair orchestrators, ensuring that tokens are strictly validated against argument schemas.
* **Regression Test Required:**
  Integration test verifying that `AutopilotEngine` invokes `StorageRepairsOrchestrator.execute_confirmed_repair` rather than raw `SafetyEngine.execute`.

---

### Finding WF-SEC-04: Path Traversal Prefix Collision Weakness in Path Validator

* **Severity:** **LOW**
* **Release-Blocking Status:** **NO**
* **Affected File & Line:** `production/paths.py` (Line 105)
* **Entry Point:** `is_safe_app_path(target_path, allowed_root)`
* **Attacker Prerequisites:** Ability to supply an arbitrary target path sharing a string prefix with the allowed root directory.
* **Attack Scenario:**
  Line 105 implements directory confinement using string prefix comparison:
  ```python
  return str(resolved_target).startswith(str(resolved_root))
  ```
  If `allowed_root` is `C:\AppData\WinFixAI`, a path such as `C:\AppData\WinFixAI-malicious\payload.dll` evaluates to `True` because `"C:\\AppData\\WinFixAI-malicious".startswith("C:\\AppData\\WinFixAI")` is `True`.
* **Potential Impact:** Flawed path boundary check allowing sibling directories sharing a prefix name to pass validation.
* **Existing Protections:** Application paths are currently constructed internally via `resolve_app_paths()` without direct untrusted path injection.
* **Reproduction Evidence:**
  Evaluating `is_safe_app_path(Path("C:/AppData/WinFixAI-test"), Path("C:/AppData/WinFixAI"))` returns `True`.
* **Recommended Remediation:**
  Replace line 105 with:
  ```python
  return resolved_target.is_relative_to(resolved_root)
  ```
* **Regression Test Required:**
  Unit test asserting `is_safe_app_path(Path("C:/Data-evil"), Path("C:/Data"))` is `False`.

---

### Finding WF-SEC-05: Unpinned Dependencies in Production Manifest

* **Severity:** **LOW**
* **Release-Blocking Status:** **NO**
* **Affected File & Line:** `requirements.txt` (Lines 1-8)
* **Entry Point:** Environment installation (`pip install -r requirements.txt`).
* **Attacker Prerequisites:** Compromise of an upstream PyPI package or dependency drift introducing incompatible/vulnerable code.
* **Attack Scenario:**
  `requirements.txt` lists unpinned top-level packages:
  ```text
  streamlit
  ollama
  psutil
  pywin32
  faster-whisper
  av
  pyyaml
  pillow
  ```
  A clean environment build without an exact lockfile could resolve to newer, untested versions containing vulnerabilities or breaking changes.
* **Potential Impact:** Non-reproducible builds and supply-chain drift.
* **Existing Protections:** The active virtual environment `.venv` contains a stable set of installed packages tested under Phase 10.
* **Reproduction Evidence:** Inspection of `requirements.txt`.
* **Recommended Remediation:**
  Generate a frozen `requirements.lock` with exact version specifiers (`==`) and hashes.
* **Regression Test Required:**
  CI lockfile integrity check.

---

### Finding WF-SEC-06: OS-Enforced Runtime Listener Isolation Remains Pending

* **Severity:** **NEEDS_VALIDATION**
* **Release-Blocking Status:** **NO**
* **Affected File & Line:** Runtime Streamlit Socket Binding (`winfix_launcher.py`, `.streamlit/config.toml`)
* **Entry Point:** Local TCP port `8501`.
* **Attacker Prerequisites:** Local network adjacency.
* **Attack Scenario:**
  While source configuration specifies `127.0.0.1`, runtime socket binding has not been independently verified inside an OS-enforced network sandbox via live socket inspection (`Get-NetTCPConnection -LocalPort 8501`) during an active UI session.
* **Potential Impact:** Undetected binding to `0.0.0.0` or IPv6 dual-stack (`::`) by underlying Tornado/Streamlit libraries.
* **Existing Protections:** `.streamlit/config.toml` specifies `address = "127.0.0.1"`, and launcher passes `--server.address 127.0.0.1`.
* **Reproduction Evidence:** Static inspection verified; runtime network socket verification remains pending per assessment safety constraints.
* **Recommended Remediation:**
  Conduct a sandboxed test launching the UI and verifying active socket listeners via `Get-NetTCPConnection -LocalPort 8501 | Select-Object LocalAddress, LocalPort, State`.
* **Regression Test Required:**
  Automated socket binding validation script.

---

## 3. Discarded False Positives

* **WF-FP-01 (Subprocess Usage in Launcher):** `winfix_launcher.py:92` invokes `subprocess.run(cmd)` where `cmd` is a hardcoded list executing `streamlit run app.py`. This is a benign process wrapper and not an exploitable command execution sink.
* **WF-FP-02 (PowerShell / CMD References in Codebase):** Multiple occurrences of `powershell`, `cmd.exe`, etc. in `agent/`, `ai/`, `database/` are security blocklists, evaluation test vectors, and regex filters. No shell commands are executed.
* **WF-FP-03 (Unregistered Tool Invocations):** When an unapproved tool name is passed to `SafetyEngine.evaluate()`, it fails closed immediately with `allowed=False, blocked=True`.
