# WinFix AI — Phase 29: Advanced Windows Troubleshooting Intelligence & Domain Coverage

## 1. Executive Summary

Phase 29 advances WinFix AI from a generic troubleshooting orchestrator into a structured, domain-aware Windows troubleshooting system. By integrating authoritative domain models, evidence correlation across multiple subsystems, deterministic strategy selection, and pre-validated workflow templates, Phase 29 empowers the agent to reason deeply about Windows operating system failures without creating new commands or weakening safety invariants.

### Core Non-Negotiable Invariants:
1. `Domain Classification != Execution Authority`: Categorizing a problem does not execute Windows tools.
2. `Strategy Selection != Repair Authorization`: Selecting a troubleshooting strategy merely defines a bounded diagnostic plan.
3. `Workflow Template != Repair Authorization`: Instantiating a workflow template is bounded by user confirmation boundaries for MEDIUM actions.
4. `Deterministic Verification is Authoritative`: Resolution is verified exclusively by factual before/after telemetry comparison via registered SAFE tools.
5. `59-Tool Registry Invariant`: No dynamic or unapproved tools are created; all strategies and templates bind strictly to the 59 allowlisted tools.

---

## 2. Supported Troubleshooting Domains

| Domain | Display Name | Primary Evidence Types | Core Diagnostic Tools | Approved Repair Tools |
|---|---|---|---|---|
| **NETWORK** | Network & Internet Connectivity | `NETWORK` | `get_network_adapters_diagnostics`, `check_dns_resolution`, `check_internet_connectivity`, `get_dns_client_config` | `flush_dns_cache`, `renew_dhcp_lease` |
| **PERFORMANCE** | Performance & Resource Consumption | `PERFORMANCE` | `get_top_cpu_processes`, `get_top_memory_processes`, `get_cpu_diagnostics`, `get_memory_diagnostics`, `get_resource_snapshot` | `terminate_user_process` |
| **STORAGE** | Storage & Disk Health | `STORAGE` | `get_storage_diagnostics`, `get_temp_storage_info`, `analyze_large_temporary_files`, `get_storage_pressure_analysis` | `clean_user_temp_cache` |
| **SERVICES** | Windows Services Management | `SERVICE` | `get_service_status`, `get_services_diagnostics`, `get_service_details`, `list_common_services` | `restart_service`, `start_service`, `stop_service` |
| **WINDOWS_UPDATE** | Windows Update Subsystem | `WINDOWS_UPDATE`, `SERVICE` | `get_windows_update_diagnostics`, `get_windows_update_history`, `get_windows_update_health`, `get_windows_update_errors` | `restart_windows_update_service` |
| **WINDOWS_DEFENDER** | Windows Defender & Security | `DEFENDER`, `SERVICE` | `get_defender_diagnostics`, `get_defender_antivirus_status`, `get_defender_realtime_protection_status`, `get_defender_threat_status` | `restart_defender_service` |
| **BLUETOOTH** | Bluetooth & Peripheral Radios | `BLUETOOTH`, `SERVICE` | `get_bluetooth_diagnostics`, `get_bluetooth_devices`, `get_bluetooth_adapters`, `get_bluetooth_radio_status` | `restart_bluetooth_service` |
| **APPLICATION_CRASH** | Application Fault Diagnostics | `APPLICATION_CRASH` | `get_application_crash_diagnostics`, `get_recent_application_crashes`, `get_application_crash_events`, `get_windows_error_reporting_status` | *(Read-only)* |
| **STARTUP** | Startup & Boot Programs | `PERFORMANCE` | `get_resource_snapshot`, `get_top_cpu_processes` | *(Read-only)* |
| **SYSTEM** | Core Windows OS Environment | `SYSTEM` | `get_complete_system_info`, `get_resource_snapshot` | *(Read-only)* |
| **UNKNOWN** | General / Unclassified | `SYSTEM` | `get_complete_system_info` | *(Read-only)* |

---

## 3. Evidence Correlator & Multi-Domain Grouping

The `EvidenceCorrelator` analyzes all active evidence items within a session to:
- Group evidence by primary domain.
- Detect cross-domain relationships (e.g., Windows Update failures tied to stopped services or low storage).
- Identify stale evidence exceeding domain TTLs.
- Identify contradictory observations across tools and user reports.
- Flag missing required evidence types before recommending repairs.

---

## 4. Verification Registry & Deterministic Evaluation

The `VerificationRegistry` maintains strict mappings between repair actions and post-repair verification tools:

| Repair Action | Designated Verification Tool | Expected State / Condition |
|---|---|---|
| `flush_dns_cache` | `check_dns_resolution` | `dns_resolved == True` |
| `renew_dhcp_lease` | `check_internet_connectivity` | `internet_connected == True` |
| `restart_service` | `get_service_status` | `state == Running` |
| `start_service` | `get_service_status` | `state == Running` |
| `stop_service` | `get_service_status` | `state == Stopped` |
| `clean_user_temp_cache` | `get_storage_diagnostics` | `status == ok` |
| `restart_windows_update_service`| `get_windows_update_diagnostics` | `wuauserv_running == True` |
| `restart_defender_service` | `get_defender_diagnostics` | `defender_running == True` |
| `restart_bluetooth_service` | `get_bluetooth_diagnostics` | `bthserv_running == True` |
| `terminate_user_process` | `get_top_cpu_processes` | `process_terminated == True` |

---

## 5. Offline Deterministic Fallback & Personal Tutor

- **Offline Operation**: If local LLM inference is degraded or unavailable, WinFix AI utilizes deterministic keyword matching, rule-based domain classification, and pre-validated workflow templates.
- **Personal Tutor**: Domain-aware tutor explanations detail why a specific domain was prioritized, what Windows telemetry indicated, and how deterministic verification proved the resolution.
