# WinFix AI — Real-World Troubleshooting Validation (Phase 30)

## 1. Scope & Framework

Real-world validation in Phase 30 verifies WinFix AI across 10 core troubleshooting domain families and noisy/contradictory telemetry scenarios using deterministic test doubles (`FakeWindowsEnvironment`) and live host read-only compatibility inspection (`RealWindowsValidator`).

---

## 2. Validated Scenario Families

| Domain | Scenario ID | Initial Symptom | Diagnostic Tool | Repair Candidate | Verification Rule | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **NETWORK** | `net-dns-01` | Websites will not load | `check_dns_resolution` | `flush_dns_cache` | `check_dns_resolution` | `RESOLVED` |
| **NETWORK** | `net-dhcp-01` | No IP address assigned | `get_network_adapters_diagnostics` | `renew_dhcp_lease` | `check_internet_connectivity` | `RESOLVED` |
| **SERVICES** | `svc-print-01` | Print spooler stopped | `get_service_status` | `start_service` | `get_service_status` | `RESOLVED` |
| **WINDOWS_UPDATE** | `wu-stuck-01` | WU error 0x80070422 | `get_windows_update_diagnostics` | `restart_windows_update_service` | `get_windows_update_diagnostics` | `RESOLVED` |
| **WINDOWS_DEFENDER** | `def-disabled-01` | Real-time protection off | `get_defender_diagnostics` | `restart_defender_service` | `get_defender_diagnostics` | `RESOLVED` |
| **BLUETOOTH** | `bt-radio-01` | Audio device disconnected | `get_bluetooth_diagnostics` | `restart_bluetooth_service` | `get_bluetooth_diagnostics` | `RESOLVED` |
| **STORAGE** | `stor-temp-01` | Temp installer files | `get_temp_storage_info` | `clean_user_temp_cache` | `get_temp_storage_info` | `RESOLVED` |
| **PERFORMANCE** | `perf-cpu-01` | High CPU load on PID | `get_top_cpu_processes` | `terminate_user_process` | `get_resource_snapshot` | `RESOLVED` |
| **APPLICATION_CRASH** | `app-crash-01` | App crash on launch | `get_application_crash_diagnostics` | N/A (Diagnostic investigation) | Diagnostic completed | `RESOLVED` |
| **SYSTEM** | `sys-info-01` | OS build check | `get_complete_system_info` | N/A (Diagnostic investigation) | Diagnostic completed | `RESOLVED` |

---

## 3. Noisy & Contradictory Telemetry Handling

- **Contradicted Hypothesis:** When user symptom indicates DNS failure but telemetry verifies DNS resolution is functional, the engine transitions hypothesis from `POSSIBLE` $\rightarrow$ `CONTRADICTED` and shifts to adapted domain/strategy.
- **Missing Telemetry:** Diagnostic steps degrade safely when telemetry is missing or unavailable without attempting dangerous repairs.
- **Stale Telemetry:** Telemetry exceeding domain TTL is flagged as `STALE` and refreshed prior to evaluation.

---

## 4. Live Windows Read-Only Compatibility

- `RealWindowsValidator` safely interrogates OS release/build, Win32 ctypes bridge, registry read access, and storage telemetry paths.
- Enforces strict read-only execution without OS mutation.
