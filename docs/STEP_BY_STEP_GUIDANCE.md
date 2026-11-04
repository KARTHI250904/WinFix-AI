# WinFix AI — Step-by-Step Educational Troubleshooting Guidance

## 1. Design Philosophy

The Personal Tutor mode transforms complex system diagnostics into accessible, non-technical explanations. For every diagnostic action taken, the UI presents structured guidance with zero raw JSON dumps:

```
┌─────────────────────────────────────────────────────────────┐
│ ❓ WHY are we checking this?                                │
│    [Plain-English explanation of why this check is relevant] │
├─────────────────────────────────────────────────────────────┤
│ 🔍 WHAT did we find?                                        │
│    [Clear summary of observed metrics and states]           │
├─────────────────────────────────────────────────────────────┤
│ 💡 WHAT does the result mean?                               │
│    [Empirical interpretation of the findings]               │
├─────────────────────────────────────────────────────────────┤
│ ➡️ What is the next step?                                    │
│    [Actionable recommended path or proposed repair]         │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Domain-Specific Guidance Interpretations

### 2.1 Network Connectivity
- **Tool**: `check_network_connectivity`
  - **WHY**: Verifies basic local network and default gateway reachability.
  - **WHAT found**: Gateway ping status, packet loss, and round-trip latency.
  - **WHAT it means**: Normal latency indicates healthy local physical/Wi-Fi connection; packet loss indicates RF interference or loose cable.
  - **Next Step**: Check DNS resolution or diagnose Wi-Fi adapter.
- **Tool**: `check_dns_resolution`
  - **WHY**: Confirms domain names (e.g. `google.com`) translate into IP addresses.
  - **WHAT found**: Resolution status, resolved IP, and query response time.
  - **WHAT it means**: If resolution fails, internet browsing will be broken even if connected to Wi-Fi.
  - **Next Step**: Flush local DNS cache with user authorization.
- **Tool**: `flush_dns_cache` (MEDIUM)
  - **WHY**: Clears corrupt or stale local name resolver entries.
  - **WHAT found**: Cache purge confirmation.
  - **WHAT it means**: Windows will query DNS servers afresh for all future domain lookups.
  - **Next Step**: Run post-repair DNS verification.

### 2.2 System Performance & High CPU
- **Tool**: `get_cpu_usage`
  - **WHY**: Measures total CPU load and top consuming processes.
  - **WHAT found**: Percentage CPU utilization across cores.
  - **WHAT it means**: Sustained >90% load causes system unresponsiveness and fan noise.
  - **Next Step**: Identify offending process and assess termination safely.
- **Tool**: `get_ram_usage`
  - **WHY**: Evaluates system memory pressure and paging.
  - **WHAT found**: Total, used, available RAM and swap space.
  - **WHAT it means**: Low available RAM forces Windows into heavy disk swap thrashing.
  - **Next Step**: Close high-memory background applications.

### 2.3 Storage & Temp Cache
- **Tool**: `get_disk_space`
  - **WHY**: Inspects free storage capacity across all system drives.
  - **WHAT found**: Used/free gigabytes per drive letter.
  - **WHAT it means**: Under 10% free space on C: causes update failures and system lag.
  - **Next Step**: Check temporary files and system cache.
- **Tool**: `clean_user_temp_cache` (MEDIUM)
  - **WHY**: Deletes safe-to-remove temporary cache files.
  - **WHAT found**: Number of files purged and megabytes reclaimed.
  - **WHAT it means**: Immediately frees disk space without touching user personal files.
  - **Next Step**: Verify updated disk free space.

### 2.4 Windows Services & Updates
- **Tool**: `get_service_status`
  - **WHY**: Checks whether critical background Windows services are running.
  - **WHAT found**: Service state (RUNNING, STOPPED, PAUSED) and startup type.
  - **WHAT it means**: A stopped core service prevents related features from operating.
  - **Next Step**: Propose service restart with explicit confirmation.
- **Tool**: `restart_windows_update_service` (MEDIUM)
  - **WHY**: Restarts Windows Update service (`wuauserv`) to clear stuck update queues.
  - **WHAT found**: Service stop and restart sequence results.
  - **WHAT it means**: Windows Update subsystem re-initializes its worker threads.
  - **Next Step**: Verify service is actively RUNNING.

### 2.5 Bluetooth & Audio
- **Tool**: `get_bluetooth_status`
  - **WHY**: Determines if the Bluetooth adapter is enabled and responsive.
  - **WHAT found**: Adapter power state and paired device inventory.
  - **WHAT it means**: Disabled or hung radio adapter prevents device pairing.
  - **Next Step**: Check Bluetooth service status (`bthserv`).
- **Tool**: `restart_bluetooth_service` (MEDIUM)
  - **WHY**: Cycles the Windows Bluetooth Support Service.
  - **WHAT found**: Service restart status.
  - **WHAT it means**: Resets the Bluetooth stack without requiring a full PC reboot.
  - **Next Step**: Verify Bluetooth radio status.

---

## 3. Safety & Confirmation Guardrails

1. **SAFE Tools**: Run automatically upon user clicking `Execute Step` without secondary prompts.
2. **MEDIUM Repair Tools**: Trigger an explicit, high-contrast modal dialog displaying:
   - Tool name & targeted parameters.
   - Plain-English explanation of what changes will be made.
   - Cryptographic confirmation token.
   - `Confirm & Execute` or `Cancel` options.
3. **No Hidden State**: All execution outputs, verification results, and transition logs are recorded in SQLite and rendered cleanly in the UI.
