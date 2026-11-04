# WinFix AI — Installer & Packaging Architecture

## Version: 1.0.0
**Status:** Production Standard  
**Platform Target:** Windows 10 / Windows 11 (x64)

---

## 1. Executive Summary & Strategy Evaluation

WinFix AI is an offline-first Windows troubleshooting AI agent designed for ordinary users who need deterministic, verifiable diagnostic and repair assistance without managing Python virtual environments, developer tooling, or remote cloud connections.

### Packaging Technology Evaluation

| Strategy | Advantages | Trade-offs / Risks | Selected? |
| :--- | :--- | :--- | :---: |
| **Inno Setup + Standalone Dist** | Native Windows GUI installer; non-elevated per-user installation; clean Start Menu/Desktop shortcuts; deterministic uninstaller; zero cloud dependency; reproducible builds. | Requires compilation step on build system. | **YES (Primary)** |
| **PyInstaller / Nuitka** | Bundles Python interpreter and dependencies into binary directory. | Increases packaging size; Streamlit dynamic imports require careful hook management. | **YES (Compatible Engine)** |
| **MSIX / Windows App SDK** | Sandboxed Windows modern package format. | Strict filesystem isolation can interfere with native Windows diagnostic APIs (Event Logs, Registry, Services). | No |
| **WiX Toolset (MSI)** | Enterprise Group Policy deployment. | High complexity; typically requires elevated administrator rights for basic installation. | No |

### Decision & Rationale
We employ a **Reproducible Standalone Distribution Directory** managed by [`build/build_windows.py`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/build/build_windows.py) paired with an **Inno Setup Definition Script** (`winfix_setup.iss`). This approach guarantees:
1. **Zero Internet Requirement:** All runtime files and dependencies are packaged locally.
2. **Per-User Security:** Default installation target is `%LOCALAPPDATA%\Programs\WinFix AI` (or `%ProgramFiles%\WinFix AI` when elevated), requiring no unnecessary admin privileges for normal usage.
3. **Cryptographic Integrity:** Every build produces [`build/BUILD_MANIFEST.json`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/build/BUILD_MANIFEST.json) and [`build/artifacts/SHA256SUMS.txt`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/build/artifacts/SHA256SUMS.txt) for automated tamper detection.

---

## 2. Production Directory Model

To ensure security, seamless version upgrades, and clean uninstallation, WinFix AI strictly separates immutable program binaries from mutable user data.

```text
=============================================================================
1. IMMUTABLE APPLICATION FILES (%ProgramFiles%\WinFix AI\ or Per-User App Dir)
=============================================================================
├── winfix_launcher.py          (Production launcher entrypoint)
├── app.py                      (Streamlit web application)
├── config.py                   (Environment configuration)
├── BUILD_MANIFEST.json         (Cryptographic file manifest & SHA-256 sums)
├── requirements.txt            (Runtime dependency specification)
├── agent/                      (Orchestrators, planners, ToolRegistry, SafetyEngine)
├── ai/                         (Local Ollama client, prompt templates, vision, STT)
├── database/                   (SQLite connection manager, schema.sql, models, repos)
├── input/                      (Screenshot & voice sanitizers, validation models)
├── knowledge/                  (Knowledge service, seed articles)
├── modes/                      (Personal Tutor, Autopilot engines)
├── production/                 (Health check, lifecycle, paths, version, profiler)
├── ui/                         (Streamlit components, formatting, accessibility)
└── windows/                    (Native Windows diagnostic & repair handlers)

=============================================================================
2. MUTABLE USER DATA & AUDIT TRAIL (%LOCALAPPDATA%\WinFixAI\)
=============================================================================
├── Data/
│   └── winfix.db               (Local SQLite database: sessions, audits, knowledge)
├── Config/
│   ├── .initialized            (First-run setup completion marker)
│   └── settings.json           (User preferences and UI theme state)
├── Logs/
│   ├── winfix.log              (Privacy-sanitized rotating application logs)
│   └── startup.log             (Pre-flight health check logs)
└── Temp/                       (Isolated temporary working directory for diagnostics)
```

---

## 3. Installation, Upgrade, & Repair Lifecycles

### 3.1 First-Run Initialization
On first execution, [`production/setup.py`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/production/setup.py) coordinates idempotent environment setup:
1. Creates directory hierarchy in `%LOCALAPPDATA%\WinFixAI`.
2. Initializes SQLite schema and creates performance indexes.
3. Seeds default troubleshooting knowledge base (9 verified articles).
4. Runs [`HealthCheckEngine`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/production/health_check.py) across all 59 registered tools and local AI connections.

### 3.2 Upgrades & Migrations
During application updates:
- Application binaries in the installation folder are replaced with new versions.
- User data in `%LOCALAPPDATA%\WinFixAI` is **never overwritten or deleted**.
- [`run_database_migration`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/production/lifecycle.py#L110) applies schema updates transactionally while preserving all audit records and session histories.

### 3.3 Safe Non-Destructive Repair
The [`InstallationManager.repair_installation`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/production/installation.py#L225) routine restores missing knowledge articles, repairs missing tables, and re-validates directory permissions without purging existing user records.

### 3.4 Uninstallation Safety
Uninstallation follows the selected [`UninstallPolicy`](file:///c:/Users/karth/OneDrive/Desktop/WinFix-AI/production/lifecycle.py#L26):
- `KEEP_USER_DATA` (Default): Removes application binaries and shortcut entries while retaining `%LOCALAPPDATA%\WinFixAI\Data\winfix.db` and logs.
- `PURGE_ALL` (Explicit Opt-In): Removes both application binaries and user data directory.

---

## 4. Localhost & Network Security

1. **Localhost Binding Only:** WinFix AI binds exclusively to `127.0.0.1` (`localhost`).
2. **Zero Cloud Telemetry:** No external network requests, usage metrics, or telemetry are ever transmitted.
3. **No Automatic Elevation:** The launcher runs with standard user privileges. Individual repair operations requiring elevation explicitly request authorization through the `requires_admin` metadata flag in `SafetyEngine`.
