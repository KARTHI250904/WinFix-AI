# WinFix AI — Security Remediation Report (Stage 1)
## WF-SEC-01: Eliminate Stale LAN-Exposed Build Artifacts

**Remediation Date:** 2026-11-26
**Auditor / Engineer:** Antigravity AI Security Systems Agent
**Active Git Branch:** `security-remediation`
**Base Commit SHA:** `9fa4f73285e34dafed3923ee44896a5fc4310ff9`
**Vulnerability Target:** `WF-SEC-01` (Stale Pre-Remediation Build/Dist Artifacts in Inno Setup Packaging)
**Remediation Status:** **VERIFIED REMEDIATED**

---

## 1. Root Cause Analysis

During the Pre-Pilot Security Threat Assessment, a critical synchronization flaw was identified between the source repository and the packaged distribution directory:
1. Commit `9fa4f73` updated the authoritative launcher `winfix_launcher.py` and `.streamlit/config.toml` to default to `127.0.0.1`.
2. However, the distribution directory `build/dist/WinFixAI` was generated prior to Phase 11. Consequently, `build/dist/WinFixAI/winfix_launcher.py:114` still contained:
   ```python
   parser.add_argument("--host", default="0.0.0.0", help="Host address to bind the UI server to (default: 0.0.0.0 for Local & LAN)")
   ```
3. Furthermore, the build packaging pipeline `build/build_windows.py` omitted `.streamlit` from `PRODUCTION_DIRECTORIES`. As a result, the packaged distribution lacked `.streamlit/config.toml`.
4. Inno Setup script `build/artifacts/winfix_setup.iss` directly packages `build/dist/WinFixAI\*`. Compiling or executing an installer from this build would bundle the stale launcher and restore unauthenticated `0.0.0.0` LAN exposure.
5. In addition, the source launcher `winfix_launcher.py` lacked server-side input validation on the `--host` CLI argument, silently accepting non-loopback hosts if passed by a caller.

---

## 2. Technical Modifications & Files Changed

### A. Authoritative Launcher (`winfix_launcher.py`)
- **Strict Loopback Allowlist:** Defined `ALLOWED_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}`.
- **Host Validation Function:** Added `validate_host_address(host: str) -> tuple[bool, str]` enforcing loopback confinement and returning a security violation error for any non-loopback host (e.g. `0.0.0.0`, LAN IPs, or remote hostnames).
- **Runtime Guard in `launch_streamlit_app()`:** Validates `host` before preparing or executing the subprocess command; immediately halts execution with return code `1` if an unsafe host is supplied.
- **CLI Guard in `main()`:** Validates `args.host` immediately after parsing arguments; blocks startup and exits with code `1` on security policy violations.

### B. Production Build Packager (`build/build_windows.py`)
- **Included `.streamlit` in Production Directories:** Added `".streamlit"` to `PRODUCTION_DIRECTORIES` in `build/build_windows.py:33`.
- Ensures that `.streamlit/config.toml` (`address = "127.0.0.1"`, `port = 8501`, `gatherUsageStats = false`) is automatically copied into `build/dist/WinFixAI/.streamlit/config.toml`.
- Recomputed SHA-256 digests across all 144 packaged production files and updated `build/BUILD_MANIFEST.json` and `build/artifacts/SHA256SUMS.txt`.

### C. Security Regression Test Suite (`tests/test_installer_security.py`)
Added two new automated security test cases:
1. `test_wf_sec_01_launcher_loopback_validation`:
   - Validates that `ALLOWED_LOOPBACK_HOSTS` includes `127.0.0.1` and `localhost`.
   - Tests loopback variants (`127.0.0.1`, `localhost`, `LOCALHOST`, whitespace-padded).
   - Tests and asserts rejection of unsafe hosts (`0.0.0.0`, `192.168.1.1`, `10.0.0.5`, `172.16.0.1`, `::`, `::1`, `""`, `None`, `evil.com`).
   - Asserts `launch_streamlit_app(host="0.0.0.0")` returns code `1`.
2. `test_wf_sec_01_packaged_distribution_and_streamlit_config_integrity`:
   - Asserts `build/dist/WinFixAI` exists.
   - Computes SHA-256 of root launcher vs packaged launcher and asserts they are **100% identical**.
   - Asserts packaged launcher does NOT contain `default="0.0.0.0"` and contains `default="127.0.0.1"`.
   - Asserts `build/dist/WinFixAI/.streamlit/config.toml` exists and contains `address = "127.0.0.1"`.
   - Asserts Inno Setup script `build/artifacts/winfix_setup.iss` references the rebuilt distribution without `0.0.0.0` references.

---

## 3. Build & Packaging Execution

The distribution was rebuilt cleanly using the official repository build system:

```powershell
.\.venv\Scripts\python.exe build/build_windows.py
```

### Execution Log Output:
```text
[INFO] Starting WinFix AI build v1.0.0...
[INFO] Cleaning previous build directories...
[INFO] Scanning package sources for potential secrets...
[INFO] Copying production modules and assets...
[INFO] Generating cryptographic build manifest...
[INFO] Generating SHA256SUMS.txt...
[INFO] Generating Inno Setup compiler definition (winfix_setup.iss)...
[INFO] Build complete! Packaged 144 files (1825937 bytes).
Build successful.
```

---

## 4. Verification Evidence

### A. Launcher Identity Check
```powershell
git diff --no-index winfix_launcher.py build/dist/WinFixAI/winfix_launcher.py
```
*Result:* **Zero diff (Exit code 0).** The packaged launcher and authoritative source launcher are identical.

### B. Packaged Streamlit Configuration Check
`build/dist/WinFixAI/.streamlit/config.toml`:
```toml
# Streamlit Local Offline Configuration for WinFix AI
[browser]
gatherUsageStats = false
serverAddress = "localhost"

[server]
port = 8501
address = "127.0.0.1"
headless = false
enableCORS = true
enableXsrfProtection = true
```

### C. Zero Stale `0.0.0.0` Scan
A regex scan across all packaged `.py`, `.toml`, and `.iss` files confirmed:
- Zero executable defaults or bindings to `0.0.0.0`.
- The sole occurrence is within the security docstring of `validate_host_address`.

### D. Host Enforcement Validation
1. **Valid Loopback:**
   ```powershell
   python build/dist/WinFixAI/winfix_launcher.py --check-only
   ```
   *Result:* Exit code `0` (14/14 subsystems READY).
2. **Unsafe Non-Loopback Rejection:**
   ```powershell
   python build/dist/WinFixAI/winfix_launcher.py --host 0.0.0.0
   ```
   *Result:* Exit code `1`:
   ```text
   [CRITICAL SECURITY ERROR] Security Violation: Non-loopback host '0.0.0.0' is strictly prohibited. WinFix AI must bind to loopback (127.0.0.1 or localhost) to prevent unauthorized network exposure.
   ```

---

## 5. Security & Regression Test Results

### 1. Installer Security Suite (`tests/test_installer_security.py`)
- **Command:** `pytest tests/test_installer_security.py -v`
- **Result:** **8 passed, 21 subtests passed in 26.90s** (Exit code `0`).

### 2. Core Security Regression Suite (13 test files)
- **Files:** `test_authorization_security.py`, `test_security_boundaries.py`, `test_security_regression.py`, `test_troubleshooting_workflow_security.py`, `test_adaptive_security.py`, `test_ai_model_security.py`, `test_domain_troubleshooting_security.py`, `test_evaluation_security.py`, `test_installer_security.py`, `test_phase33_security.py`, `test_recovery_security.py`, `test_telemetry_security.py`, `test_verification_stress.py`.
- **Result:** **83 passed, 145 subtests passed in 29.80s** (Exit code `0`).
- **Failures:** 0.

---

## 6. Remaining Limitations

1. **WF-SEC-02 (Tutor Context Path Privacy):** Single-separator regex in `modes/tutor_context.py:15` remains to be addressed in Stage 2.
2. **WF-SEC-03 (Autopilot Token Synthesis):** Autopilot ad-hoc token routing remains to be refactored in Stage 3.
3. **WF-SEC-04 (Path Traversal Prefix Collision):** `production/paths.py:is_safe_app_path` prefix check remains to be upgraded to `is_relative_to`.
4. **WF-SEC-05 (Dependency Pinning):** `requirements.txt` remains unpinned.
5. **WF-SEC-06 (Live Network Socket Inspection):** OS-enforced runtime socket listener verification inside an isolated environment remains pending.

---

## 7. Git Diff Summary

### Modified Files for WF-SEC-01:
1. `winfix_launcher.py` (+37 lines)
2. `build/build_windows.py` (+1 line)
3. `build/BUILD_MANIFEST.json` (Recomputed hashes for 144 files)
4. `tests/test_installer_security.py` (+65 lines)
5. `docs/WF_SEC_01_REMEDIATION_REPORT.md` (New deliverable report)

### Preserved Untracked & Survey Files:
- All 4 survey documents (`docs/FINAL_*.md`) remain preserved.
- All 5 threat assessment documents (`docs/SECURITY_*.md`, `docs/THREAT_MODEL.md`) remain preserved.
- `.agents/` and `skills-lock.json` remain preserved.
- No commits or pushes have been made.
