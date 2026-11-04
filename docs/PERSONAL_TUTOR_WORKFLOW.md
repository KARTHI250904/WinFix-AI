# WinFix AI — Personal Tutor Troubleshooting Workflow

## 1. Educational Troubleshooting Paradigm

Personal Tutor Mode transforms low-level Windows diagnostics into a guided, educational conversation. It is designed specifically for non-technical users who want to understand what is happening on their PC without being overwhelmed by technical jargon or raw JSON payloads.

```
Explain → Ask → Execute/Guide → Verify → Teach
```

---

## 2. The 4-Part Step-by-Step Experience

Every step presented by the Personal Tutor follows a structured layout:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ❓ WHY are we checking this?                                                │
│    [Plain-English explanation of why this check is relevant]                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ 🔍 WHAT did we find?                                                        │
│    [Clear summary of observed metrics and states]                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ 💡 WHAT does the result mean?                                               │
│    [Empirical interpretation of the findings without unsupported root-causes]│
├─────────────────────────────────────────────────────────────────────────────┤
│ ➡️ What is the next step?                                                    │
│    [Actionable recommended path or proposed verified repair]                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supported Domains & Diagnostic Sequences

| Domain | Initial Check (SAFE) | Secondary Check (SAFE) | Repair Check (MEDIUM) | Post-Verification Tool |
| :--- | :--- | :--- | :--- | :--- |
| **Network** | `get_network_adapters_diagnostics` | `check_internet_connectivity` | `flush_dns_cache` | `check_dns_resolution` |
| **Performance** | `get_top_cpu_processes` | `get_top_memory_processes` | `terminate_user_process` | `get_top_cpu_processes` |
| **Storage** | `get_storage_diagnostics` | `get_temp_storage_info` | `clean_user_temp_cache` | `get_temp_storage_info` |
| **Services** | `get_service_status` | `get_services_diagnostics` | `restart_service` | `get_service_status` |
| **Bluetooth** | `get_bluetooth_status` | `get_bluetooth_service_status` | `restart_bluetooth_service` | `get_bluetooth_status` |
| **Windows Update**| `get_windows_update_diagnostics` | `get_services_diagnostics` | `restart_windows_update_service` | `get_windows_update_service_status` |
| **Defender** | `get_defender_diagnostics` | `get_services_diagnostics` | `restart_defender_service` | `get_defender_status` |
| **App Crash** | `get_windows_error_reporting_status` | `get_recent_application_crashes` | *(Guidance / Safe Reset)* | `get_recent_application_crashes` |
| **General** | `get_complete_system_info` | `get_services_diagnostics` | *(Advisory)* | `get_complete_system_info` |

---

## 4. Guardrails & Interactive Flow

1. **Read-Only Diagnostics (SAFE)**:
   - Users click `Execute Step` to run the tool.
   - The tutor interprets findings immediately into plain English.
2. **Repairs (MEDIUM)**:
   - High-contrast confirmation modal outlines:
     - What will change (e.g. *"Clears DNS resolver cache"*).
     - What will NOT change (e.g. *"Will not delete files or reset passwords"*).
     - Cryptographic confirmation token.
3. **Verification**:
   - Repair completion triggers paired verification.
   - If verified: *"Verified: Target component is healthy."*
   - If unverified: *"The repair completed, but verification could not confirm resolution. Reassessing next step."*
