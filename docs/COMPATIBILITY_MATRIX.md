# WinFix AI — Hardware & Environment Compatibility Matrix (Phase 36)

## 1. Real-World Host Environment Verification

| Component | Status | Validation Type | Detected Value / Findings |
| :--- | :--- | :--- | :--- |
| **Windows OS** | `READY` | `REAL` | Windows 11 Build 26200+ (Native Win32 APIs accessible) |
| **CPU Architecture** | `READY` | `REAL` | x64 Architecture (Multi-core multi-threaded execution) |
| **System Memory** | `READY` | `REAL` | > 8.0 GB Physical RAM (> 2.0 GB Available) |
| **Storage & Filesystem** | `READY` | `REAL` | System Drive NTFS (> 10.0 GB Free Space) |
| **Network Adapters** | `READY` | `REAL` | Active Wi-Fi / Ethernet adapters inspected |
| **DNS Diagnostics** | `READY` | `REAL` | Allowlisted domain resolution query verified |
| **Windows Services** | `READY` | `REAL` | Common services cataloged via Service Manager |
| **Windows Update** | `READY` | `REAL` | `wuauserv` service status inspected |
| **Windows Defender** | `READY` | `REAL` | `WinDefend` service status inspected |
| **Bluetooth Subsystem** | `READY` / `UNAVAILABLE` | `REAL` | Hardware presence checked; absence handled gracefully |
| **WER Crash Diagnostics**| `READY` | `REAL` | Windows Error Reporting application crash events accessible |
| **Local AI (Ollama)** | `READY` / `DEGRADED` | `REAL` | Reachable on localhost:11434 (`gemma4:12b`); deterministic fallback active |
| **Vision Diagnostics** | `READY` | `REAL` | Multi-modal screenshot analysis pipeline initialized |
| **Voice Diagnostics** | `READY` | `REAL` | Local Whisper speech-to-text provider initialized |
| **SQLite Storage** | `READY` | `REAL` | 25 tables active with foreign key integrity |
| **User Permissions** | `READY` | `REAL` | Standard user and Administrator contexts supported |

---

## 2. Simulated Edge-Case Environment Validation

| Simulation Profile | Target Subsystem | Resulting Status | Fallback Behavior Verified |
| :--- | :--- | :--- | :--- |
| `OFFLINE_AI` | Local AI | `DEGRADED` | Deterministic rule-based planner activated |
| `NO_BLUETOOTH` | Bluetooth | `UNAVAILABLE` | Informative hardware absence badge displayed |
| `NO_NETWORK` | Network Adapters | `UNAVAILABLE` | Offline local knowledge guide presented |
| `DNS_FAIL` | DNS Diagnostics | `DEGRADED` | Safe `flush_dns_cache` repair proposed |
| `DISK_FULL` | Storage | `DEGRADED` | Minimal write mode with log rotation active |
| `LOW_MEMORY` | Memory | `DEGRADED` | Compact execution profile activated |
| `LIMITED_PERMISSIONS`| Permissions | `READY` | Read-only checks proceed; repairs prompt for elevation |
| `DEGRADED_DATABASE` | SQLite | `DEGRADED` | Ephemeral memory cache activated |
| `NON_WINDOWS` | Host OS | `DEGRADED` | Cross-platform simulation heuristics activated |
| `VISION_UNAVAILABLE` | Vision Model | `DEGRADED` | Fallback to text problem description |
| `VOICE_UNAVAILABLE` | Voice STT | `DEGRADED` | Fallback to text diagnostic assistant |
