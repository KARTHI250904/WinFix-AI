# WinFix AI — Real-World Windows Compatibility & Hardware Validation (Phase 36)

## 1. Executive Summary & Validation Objective
WinFix AI is built to operate reliably on real-world Windows installations, diverse hardware configurations, varying user permission levels, missing optional peripherals, and degraded local AI environments.

The core objective of Phase 36 is to validate that:
1. **Host Environment Detection**: Real Windows 10/11 operating systems, x64/ARM64 architectures, physical RAM, storage partitions, and network adapters are accurately inspected without guessing.
2. **Non-Destructive Principles**: All compatibility queries execute strictly in read-only mode, without modifying user files, deleting caches, or reconfiguring adapters.
3. **Graceful Degradation**: When optional hardware (e.g. Bluetooth) or local AI dependencies (e.g. Ollama) are unavailable, WinFix AI degrades gracefully to deterministic offline guidance rather than crashing.
4. **Failure Isolation**: An outage in one subsystem (e.g. Bluetooth service stopped) never breaks unrelated subsystems (e.g. Storage or Network diagnostics).
5. **Privacy Sanitization**: System telemetry collected into `EnvironmentSnapshot` contains zero passwords, tokens, credentials, or private user paths.

---

## 2. Compatibility Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   WindowsCompatibilityValidator                        │
├────────────────────────────────┬───────────────────────────────────────┤
│ Real-World Hardware & OS       │ Graceful Degradation & Fallbacks      │
├────────────────────────────────┼───────────────────────────────────────┤
│ • Windows OS & Build           │ • Ollama Offline → Rule-Based Planner │
│ • CPU & Execution Threads      │ • Vision Model Offline → Text Mode    │
│ • RAM & Swap Usage             │ • Voice STT Offline → Text Input      │
│ • System Storage & Filesystem  │ • Bluetooth Absent → Informative N/A  │
│ • Network Adapters & IP Config │ • Low Memory → Ephemeral Cache Mode   │
│ • DNS Resolution Diagnostics   │ • Standard User → Elevated Prompt     │
│ • Win32 Service Manager        │ • Database Locked → In-Memory Store   │
│ • Windows Update Service       │ • Subsystem Isolation → Zero Cascades │
│ • Windows Defender Service     │                                       │
│ • Bluetooth Radio Hardware     │                                       │
│ • Windows Error Reporting Log  │                                       │
│ • SQLite Database Engine       │                                       │
└────────────────────────────────┴───────────────────────────────────────┘
```

---

## 3. Real vs Simulated Validation Classification

WinFix AI explicitly separates real physical hardware verification from simulated/mock verification:
- **`REAL`**: Verified against the active host Windows environment via native Win32/Python system APIs.
- **`SIMULATED`**: Verified against controlled synthetic profiles (e.g. `OFFLINE_AI`, `NO_BLUETOOTH`, `DISK_FULL`) to test edge cases safely without mutating Windows.
- **`STATIC`**: Verified through AST code analysis (0 prohibited execution calls).
- **`UNTESTED`**: Explicitly documented when a hardware component or architecture was not physically present during test execution.

---

## 4. Subsystem Absence & Fallback Matrix

| Subsystem / Peripheral | Present State | Absent / Unavailable State | Safe Fallback Behavior |
| :--- | :--- | :--- | :--- |
| **Windows OS** | `READY` (Native) | `DEGRADED` (Cross-platform) | Heuristic simulation mode |
| **Local AI (Ollama)** | `READY` (Gemma 4 12B) | `DEGRADED` (Offline) | High-reliability deterministic troubleshooting |
| **Vision Model** | `READY` (minicpm-v) | `DEGRADED` (Offline) | Text-based error code & symptom search |
| **Voice STT** | `READY` (Whisper) | `DEGRADED` (No Mic / STT) | Text-based Diagnostic Assistant |
| **Bluetooth Radio** | `READY` (Adapter UP) | `UNAVAILABLE` (No Hardware) | Clear *"Hardware Not Present"* message |
| **Network Adapters** | `READY` (IP Assigned) | `DEGRADED` / `UNAVAILABLE` | Local knowledge base & offline guides |
| **Windows Defender** | `READY` (WinDefend) | `DEGRADED` (Restricted API) | Educational Windows Security guidance |
| **Windows Update** | `READY` (wuauserv) | `DEGRADED` (Restricted API) | Controlled restart proposal |
| **SQLite Storage** | `READY` (25 tables) | `DEGRADED` (Disk Read-Only) | Ephemeral in-memory session cache |
