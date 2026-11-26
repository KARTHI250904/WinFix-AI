# WinFix AI — Security Remediation Report (Stage 5)
## WF-SEC-05: Dependency Pinning, Supply-Chain Hardening & Vulnerability Audit

**Remediation Date:** 2026-11-26
**Auditor / Engineer:** Antigravity AI Security Systems Agent
**Active Git Branch:** `security-remediation`
**Base Commit SHA:** `9fa4f73285e34dafed3923ee44896a5fc4310ff9`
**Vulnerability Target:** `WF-SEC-05` (Unpinned Dependencies, Lack of Reproducible Lockfile, Supply-Chain Exposure)
**Remediation Status:** **VERIFIED REMEDIATED**

---

## 1. Vulnerability & Root Cause Overview

During the Pre-Pilot Security Threat Assessment, a critical supply-chain and dependency management weakness was identified:

1. **Unpinned Direct Dependencies:**
   `requirements.txt` contained only 8 bare, unpinned package names:
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
2. **Missing Lockfile for Offline Reproducibility:**
   The repository lacked a cryptographic lockfile (`requirements.lock`) specifying the complete transitive closure of installed packages. Re-running `pip install -r requirements.txt` on a user machine or CI runner risked pulling breaking, incompatible, or compromised newer releases.
3. **Missing Direct Dependency (`numpy`):**
   `numpy` was directly imported in `ai/voice_transcriber.py` for raw audio PCM normalization, yet was omitted from direct requirement declarations.
4. **Vulnerability Audit Gap:**
   Installed dependencies had not been audited against authoritative vulnerability databases (OSV/PyPI).

---

## 2. Technical Modifications & Files Changed

### A. Authoritative Dependency Pinning (`requirements.txt`)
All 9 direct runtime dependencies have been pinned to explicit, tested versions compatible with Python 3.12+ (tested on Python 3.14.2 on Windows x64):
```text
streamlit==1.64.0
ollama==0.6.2
psutil==7.2.2
pywin32==312
faster-whisper==1.2.1
av==19.0.0
PyYAML==6.0.3
pillow==12.3.0
numpy==2.5.3
```

### B. Reproducible Transitive Lockfile (`requirements.lock`)
Generated `requirements.lock` documenting the exact pinned versions of the entire runtime dependency closure (including all transitive packages for Streamlit, CTranslate2, PyAV, ONNX Runtime, HuggingFace Hub, HTTP transport, and data schemas).

### C. Vulnerability Auditing & Security Upgrades
1. **Auditing Direct Requirements:**
   Ran `pip-audit -r requirements.txt` against OSV and PyPI vulnerability databases:
   ```text
   No known vulnerabilities found
   ```
2. **Transitive Security Updates in `.venv`:**
   Upgraded vulnerable transitive packages to patched releases:
   - `tornado`: Upgraded from 6.5.10 to `6.6.1` (resolves CVE-2026-116577, CVE-2026-115927, CVE-2026-116578, CVE-2026-126347).
   - `certifi`: Upgraded to `2026.11.20` (resolves PYSEC-2026-4320).
   - `filelock`: Upgraded to `4.3.1` (resolves CVE-2026-112940 and related advisories).
3. **Upstream Framework Constraints Analyzed (Pillow):**
   Streamlit 1.64.0 metadata requires `pillow<13,>=7.1.0`. `pillow==12.3.0` was verified and pinned as the latest compatible release within Streamlit's constraints, with `pip check` confirming 0 conflicts.

### D. Build System & Packaging (`build/build_windows.py`)
1. **Added `requirements.lock` to Production Files:**
   Added `"requirements.lock"` to `PRODUCTION_FILES` in `build/build_windows.py`, ensuring the lockfile is packaged alongside `requirements.txt` in `build/dist/WinFixAI`.
2. **Robust Read-Only Artifact Cleanup on Windows (`_force_remove`):**
   Implemented `_force_remove()` with an error callback resetting `stat.S_IWRITE` before unlinking. This prevents Windows `[WinError 5] Access is denied` when purging previous build outputs, and guarantees `__pycache__` directories are never packaged into distribution releases.

### E. Security Regression Test Suite (`tests/test_installer_security.py`)
Added 3 dedicated automated tests for WF-SEC-05:
1. `test_wf_sec_05_requirements_pinned_strictly`:
   - Verifies `requirements.txt` exists and is non-empty.
   - Enforces that every line contains an explicit `==` pin with non-empty version.
   - Asserts all 9 required direct runtime dependencies are declared.
2. `test_wf_sec_05_reproducible_lockfile_exists_and_valid`:
   - Verifies `requirements.lock` exists and contains >20 pinned transitive entries with `==`.
3. `test_wf_sec_05_package_dependency_consistency`:
   - Executes `pip check` programmatically, asserting exit code 0 and verifying no broken requirements or dependency conflicts exist.

---

## 3. Verification Evidence & Test Execution

### A. Environment Consistency Check
```powershell
pip check
```
**Result:** `No broken requirements found.` (Exit code `0`).

### B. Vulnerability Audit
```powershell
pip-audit -r requirements.txt
```
**Result:** `No known vulnerabilities found` (Exit code `0`).

### C. Installer Security & Package Contents Suite
```powershell
pytest tests/test_installer_security.py tests/test_package_contents.py -v
```
**Result:** **23 passed, 122 subtests passed in 28.75s** (Exit code `0`, 0 failures).

### D. Core Regression Suite (13 test files)
```powershell
pytest tests/test_authorization_security.py tests/test_installer_security.py tests/test_package_contents.py tests/test_personal_tutor.py tests/test_production.py tests/test_lifecycle_compatibility.py tests/test_database.py tests/test_network_repairs.py tests/test_services.py tests/test_storage.py tests/test_system_info.py tests/test_windows_update.py tests/test_bluetooth.py -q
```
**Result:** **221 passed, 136 subtests passed in 69.77s** (Exit code `0`, 0 failures).

### E. Production Distribution Synchronization
Rebuilt the Windows distribution package via `build/build_windows.py`:
- Packaged 145 files (1,838,732 bytes).
- Both `requirements.txt` and `requirements.lock` present in `build/dist/WinFixAI`.
- Cryptographic manifests regenerated: `build/BUILD_MANIFEST.json` and `build/artifacts/SHA256SUMS.txt`.

---

## 4. Scope & Git Policy Compliance

- **Active Branch:** `security-remediation` (HEAD at commit `9fa4f73`, no branch switches).
- **Commits / Pushes:** None performed (0 commits, 0 pushes).
- **Preserved Artifacts:** All previous survey documents, threat models, security baseline reports, and stage remediation reports (`WF_SEC_01`, `WF_SEC_02`, `WF_SEC_03`, `WF_SEC_04`) preserved intact.
- **Scope Limit:** Restricted exclusively to `WF-SEC-05`. `WF-SEC-06` (Runtime Network Socket Isolation) has not been started and requires separate authorization.
