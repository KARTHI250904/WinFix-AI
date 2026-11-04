# WinFix AI — Troubleshooting & Diagnostics Guide

## Common Issues and Resolutions

---

### 1. Pre-Flight Health Check Reports `DEGRADED` (Ollama Offline)

**Symptom**:
`Local AI Model: DEGRADED (Local Ollama is currently offline / Model missing)`

**Explanation**:
WinFix AI operates 100% offline using deterministic rule-based templates. The core application (diagnostics, knowledge base, verified repairs, audit logging) is fully functional even when Ollama is unavailable.

**Resolution**:
1. Check if Ollama service is running:
   ```powershell
   ollama list
   ```
2. Start Ollama from the Windows Start menu or background tray.
3. Download the primary reasoning model:
   ```powershell
   ollama pull gemma4:12b
   ```

---

### 2. Repair Action Fails with `Administrative Privileges Required`

**Symptom**:
`Tool execution failed: Operation requires elevated Administrator permissions (Error 5 / Access Denied).`

**Explanation**:
Windows security boundaries prevent non-admin accounts from modifying system-level network adapters or restarting protected services (e.g., `wuauserv`, `WinDefend`, `Spooler`).

**Resolution**:
1. Close WinFix AI.
2. Launch PowerShell or Command Prompt as **Administrator**.
3. Run `winfix_launcher.exe` or `python winfix_launcher.py`.

---

### 3. Port Conflict / Address Already in Use

**Symptom**:
`Port 8501 is already bound by another process.`

**Explanation**:
Another application or prior WinFix AI instance is using port 8501.

**Resolution**:
Specify an alternate local port:
```powershell
python winfix_launcher.py --port 8502
```
*Note: WinFix AI binds exclusively to `127.0.0.1` and never exposes the interface to `0.0.0.0`.*

---

### 4. SQLite Database Locked (`busy_timeout`)

**Symptom**:
`Database locked (busy_timeout_ms exceeded).`

**Explanation**:
Another process is holding an active write transaction on `winfix.db`.

**Resolution**:
1. Check for orphaned WinFix AI processes:
   ```powershell
   Get-Process python | Where-Object { $_.MainWindowTitle -like "*WinFix*" }
   ```
2. Run the database migration utility:
   ```powershell
   python winfix_launcher.py --migrate
   ```

---

### 5. Application Integrity Failure / Corrupted Installation

**Symptom**:
`InstallationState.CORRUPTED` or missing manifest files.

**Explanation**:
One or more immutable application files have been modified or deleted.

**Resolution**:
Run the safe repair workflow:
```powershell
python -c "from production.installation import repair_installation; repair_installation()"
```
This restores missing/tampered files without touching your user data or audit history.

---

### 6. Viewing Diagnostic Application Logs

All production logs are privacy-sanitized and written to:
`%LOCALAPPDATA%\WinFixAI\Logs\winfix.log`

To inspect the last 50 log entries:
```powershell
Get-Content -Tail 50 -Path "$env:LOCALAPPDATA\WinFixAI\Logs\winfix.log"
```
