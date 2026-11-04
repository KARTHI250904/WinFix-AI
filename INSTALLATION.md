# WinFix AI — Installation Guide (v1.0.0 Production Release)

## Overview

**WinFix AI** is an offline-first Windows troubleshooting assistant and personal tutor. It operates locally with zero required cloud dependencies, providing deterministic system diagnostics, guided educational explanations, and safe, user-confirmed repair workflows.

---

## 1. System Requirements

* **Operating System**: Windows 10 (64-bit) or Windows 11 (64-bit, Build 22000+)
* **Architecture**: x86_64 / AMD64
* **Memory (RAM)**: Minimum 8 GB (16 GB recommended for local Ollama LLM inference)
* **Disk Space**: 500 MB for WinFix AI core application; 8 GB+ if running local Ollama LLM models
* **Privileges**: Standard User for installation and read-only diagnostics; elevated Administrator privileges required only when confirming specific repair operations (e.g., restarting system services, DHCP renewal).

---

## 2. Packaging & Distribution Models

WinFix AI supports two installation workflows:

### A. Windows Installer Setup (`WinFixAI-1.0.0-Setup.exe`)
1. Download `WinFixAI-1.0.0-Setup.exe` from the verified release directory.
2. Verify package integrity via `SHA256SUMS.txt`:
   ```powershell
   Get-FileHash WinFixAI-1.0.0-Setup.exe -Algorithm SHA256
   ```
3. Run the installer. By default, it installs to per-user location (`%LOCALAPPDATA%\Programs\WinFixAI`) without requiring administrative elevation.
4. Choose optional shortcuts (Start Menu and Desktop).
5. Launch **WinFix AI**.

### B. Standalone Portable Distribution
1. Extract `WinFixAI-1.0.0-windows-x64.zip` to your desired immutable program directory (e.g. `C:\Program Files\WinFix AI` or `%LOCALAPPDATA%\Programs\WinFixAI`).
2. Run `winfix_launcher.exe` or `python winfix_launcher.py`.

---

## 3. Directory Architecture

WinFix AI strictly isolates immutable application code from mutable user data:

| Component | Path | Description |
|---|---|---|
| **Application Root** | `%LOCALAPPDATA%\Programs\WinFixAI` | Read-only binaries, UI code, tool definitions, manifest, and icons. |
| **User Data** | `%LOCALAPPDATA%\WinFixAI\Data` | `winfix.db` (SQLite audit history, sessions, knowledge index). |
| **Logs** | `%LOCALAPPDATA%\WinFixAI\Logs` | Sanitized, rotating privacy-safe diagnostic logs. |
| **Configuration** | `%LOCALAPPDATA%\WinFixAI\Config` | User preferences and runtime options. |
| **Temp** | `%LOCALAPPDATA%\WinFixAI\Temp` | Temporary scratch files (cleaned on shutdown). |

---

## 4. Offline Installation & AI Handling

WinFix AI is built **offline-first**:
* The core diagnostic engine, Tool Registry (59 tools), SafetyEngine, SQLite database, and Personal Tutor knowledge base require **zero internet connectivity**.
* Local AI inference uses Ollama locally.

### Setting Up Local Ollama (Optional Component)
If you wish to enable generative synthesis and enhanced natural language responses:
1. Install Ollama for Windows from `https://ollama.com/download`.
2. Open PowerShell and download the primary troubleshooting model:
   ```powershell
   ollama pull gemma4:12b
   ```
3. (Optional) For screenshot visual analysis:
   ```powershell
   ollama pull minicpm-v:latest
   ```

### Graceful Degradation
If Ollama is not installed or the model is missing:
* WinFix AI displays `Local AI Model: DEGRADED (Offline/Missing)`.
* **All diagnostics, knowledge lookups, audit tracking, and verified repairs remain 100% operational** via built-in deterministic templates.

---

## 5. First-Run Initialization & Health Check

On first launch, WinFix AI automatically and idempotently:
1. Validates application directory integrity against `BUILD_MANIFEST.json`.
2. Creates the `%LOCALAPPDATA%\WinFixAI` directory structure.
3. Initializes SQLite schema and seeds 9 baseline troubleshooting articles.
4. Verifies the Tool Registry (59 allowlisted tools) and SafetyEngine rules.
5. Runs pre-flight health checks and confirms `Production Health = READY`.

To manually verify system readiness:
```powershell
python winfix_launcher.py --check-only
```

---

## 6. Upgrades & Data Preservation

Upgrades preserve all user data:
* Installing a newer version (e.g. `1.0.1` over `1.0.0`) overwrites only the immutable application binaries.
* Your SQLite database (`winfix.db`), session logs, and audit trails in `%LOCALAPPDATA%\WinFixAI` are preserved and automatically migrated to the new schema version if needed.

---

## 7. Installation Repair

If application files become corrupted or missing:
```powershell
python -c "from production.installation import repair_installation; repair_installation()"
```
This safely validates checksums and restores required manifest assets without deleting user data or audit logs.

---

## 8. Uninstallation

Uninstalling via Windows **Settings > Apps > Installed apps**:
* Removes all immutable application files and shortcuts.
* Prompts whether to keep or remove user data in `%LOCALAPPDATA%\WinFixAI`.
