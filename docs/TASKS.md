# WinFix AI — Development Tasks

## Status Legend

* [ ] Not started
* [~] In progress
* [x] Completed
* [!] Blocked

---

## Phase 0 — Foundation

* [x] Standard directory structure (`ai/`, `agent/`, `database/`, `input/`, `modes/`, `windows/`, `knowledge/`, `tests/`, `assets/`)
* [x] Central configuration module (`config.py`)
* [x] Ollama connectivity & health verification
* [x] Configurable model setup (`gemma4:12b` default)
* [x] Streamlit baseline UI shell
* [x] SQLite database connection & schema baseline
* [x] Testing framework setup (`tests/`)

---

## Phase 1 — System Information

* [x] Windows version & build detection
* [x] CPU hardware information
* [x] RAM hardware information
* [x] Disk drive hardware information
* [x] Network adapter hardware detection
* [x] System uptime calculation
* [x] System architecture detection
* [x] Unit & integration tests for system information

---

## Phase 2 — SQLite Foundation

* [x] Database connection manager & connection pooling
* [x] Schema migration baseline (`schema.sql`)
* [x] Session repository (`sessions`, `problems`)
* [x] Diagnostic & tool execution logging (`diagnostics`, `tool_executions`)
* [x] Solution & verification tracking (`solutions`)
* [x] User feedback store (`feedback`)
* [x] Application settings store (`settings`)
* [x] Parameterized query safety enforcement & tests

---

## Phase 3 — Read-only Windows Tools

* [x] Read-only system state inspection
* [x] Process list & resource consumption inspection
* [x] Windows services status inspection
* [x] Network interface & IP configuration inspection
* [x] Storage space & volume inspection
* [x] Un-elevated execution safety validation
* [x] Structured tool return format compliance
* [x] Timeout and error handling tests

---

## Phase 4 — Tool Registry + Safety

* [x] Central Tool Registry data structures & decorators
* [x] Tool metadata (name, domain, risk, requires_admin, automatic_allowed, verification_tool)
* [x] 3-tier risk classification enforcement (SAFE, MEDIUM, HIGH)
* [x] Safety validation engine (`agent/safety.py`)
* [x] Administrator / UAC elevation control mechanism (metadata tracking & fail-closed enforcement)
* [x] Strict blocking of LLM arbitrary command execution (`LLM != Windows Shell`)
* [x] Tool parameter validation & sanitization
* [x] Comprehensive safety test suite

---

## Phase 5 — Ollama/Gemma Agent Core

* [x] Robust Ollama API client with error handling & retries (`ai/ollama_client.py`)
* [x] Central model configuration (`gemma4:12b`)
* [x] Structured JSON prompting & schema enforcement (`agent/agent_response.py`)
* [x] Problem classifier & category detector (`agent/planner.py`)
* [x] Diagnostic planner (`agent/planner.py`)
* [x] Tool execution loop & state management (`agent/planner.py` via `SafetyEngine`)
* [x] Evidence synthesis & result explanation (`agent/planner.py`)
* [x] Graceful offline/missing model error handling & deterministic fallback plan

---

## Phase 6 — Network Diagnostics

* [x] Wi-Fi connection & adapter status (`get_network_adapters_diagnostics`)
* [x] IP address & subnet configuration (`get_network_adapters_diagnostics`)
* [x] Default gateway discovery & reachability test (`check_internet_connectivity`)
* [x] DNS configuration inspection (`get_dns_client_config`)
* [x] DNS resolution test (`check_dns_resolution`)
* [x] Internet connectivity test (`check_internet_connectivity`)
* [x] Multi-step network diagnostic plan & scenarios (`agent/network_diagnostics.py`)
* [x] Network diagnostic tests (`tests/test_network_diagnostics.py`)

---

## Phase 7 — Network Repairs + Verification

* [x] Flush DNS cache repair tool (`windows/network_repairs.py` -> `flush_dns_cache`, Risk: MEDIUM)
* [x] Renew DHCP lease repair tool (`windows/network_repairs.py` -> `renew_dhcp_lease`, Risk: MEDIUM, requires_admin=True)
* [x] Verification tool: `check_dns_resolution` (for `flush_dns_cache`)
* [x] Verification tool: `get_network_adapters_diagnostics` (for `renew_dhcp_lease`)
* [x] Explicit user confirmation & cryptographic token binding (`agent/network_repairs_orchestrator.py`)
* [x] Before/After state comparison & deterministic verification engine (`agent/network_repairs_orchestrator.py`)
* [x] Phase 7 network repair and safety test suite (`tests/test_network_repairs.py`)
* [!] Deferred repairs: Generic adapter reset, Winsock reset, TCP/IP stack reset (deferred to preserve zero-shell security boundary)

---

## Phase 8 — Performance

* [x] Real-time CPU utilization detection (`get_cpu_diagnostics`, Risk: SAFE)
* [x] Real-time RAM utilization detection (`get_memory_diagnostics`, Risk: SAFE)
* [x] Real-time Disk I/O utilization detection (`get_disk_performance_diagnostics`, Risk: SAFE)
* [x] Point-in-time unified resource health snapshot (`get_resource_snapshot`, Risk: SAFE)
* [x] Detailed process tree inspection by PID (`get_process_details`, Risk: SAFE)
* [x] Top CPU-consuming process identification (`get_top_cpu_processes`, Risk: SAFE)
* [x] Top RAM-consuming process identification (`get_top_memory_processes`, Risk: SAFE)
* [x] Performance diagnostic analyzer & orchestrator (`agent/performance_diagnostics.py`)
* [x] Allowlisted user-space process termination (`windows/performance_repairs.py` -> `terminate_user_process`, Risk: MEDIUM)
* [x] Hard blocklist protection for kernel/OS/system processes (PID 0, PID 4, svchost, csrss, lsass, explorer, System32 paths)
* [x] Safe user temporary cache cleanup with path sandbox verification (`windows/performance_repairs.py` -> `clean_user_temp_cache`, Risk: MEDIUM)
* [x] Performance repair orchestrator with cryptographic tokens & verification (`agent/performance_repairs_orchestrator.py`)
* [x] Performance diagnostic, safety, and verification test suite (`tests/test_performance.py`)

---

## Phase 9 — Storage

* [x] Free disk space analysis & volume inventory (`get_storage_diagnostics`, Risk: SAFE)
* [x] Storage pressure threshold calculation (`get_storage_pressure_analysis`, Risk: SAFE)
* [x] Temporary storage occupancy & locked file diagnostics (`get_temp_storage_info`, Risk: SAFE)
* [x] Bounded large temporary file discovery (`analyze_large_temporary_files`, Risk: SAFE)
* [x] Safe user temporary cache cleanup (`clean_user_temp_cache`, Risk: MEDIUM)
* [x] Strict sandbox boundary & symlink escape protection (`is_relative_to` containment check)
* [x] Storage diagnostics and repairs orchestrator (`agent/storage_diagnostics.py`, `agent/storage_repairs_orchestrator.py`)
* [x] Storage unit, safety, and verification test suite (`tests/test_storage.py`)

---

## Phase 10 — Windows Services

* [x] Allowlisted Windows service status inspection (`get_service_status`, `list_common_services`, `get_services_diagnostics`, Risk: SAFE)
* [x] Service startup type inspection & normalization (`get_service_details`, `get_services_diagnostics`, Risk: SAFE)
* [x] Controlled service state changes: start, stop, restart (`windows/service_repairs.py`, Risk: MEDIUM)
* [x] Service status verification & protected services policy (`is_service_stop_protected`, verification_tool: `get_service_status`)
* [x] Service diagnostic & repair orchestrators (`agent/service_diagnostics.py`, `agent/service_repairs_orchestrator.py`)
* [x] Service diagnostic, safety, AST audit, and verification test suite (`tests/test_services.py`)


---

## Phase 11 — Bluetooth

* [x] Bluetooth adapter detection & radio state (`get_bluetooth_adapters`, `get_bluetooth_radio_status`, Risk: SAFE)
* [x] Bluetooth support service status (`get_bluetooth_service_status`, `bthserv`, Risk: SAFE)
* [x] Paired/visible Bluetooth device information (`get_bluetooth_devices`, Risk: SAFE)
* [x] Aggregate Bluetooth diagnostics (`get_bluetooth_diagnostics`, Risk: SAFE)
* [x] Controlled Bluetooth service restart (`restart_bluetooth_service`, Risk: MEDIUM, requires_admin=True, verification_tool: `get_service_status`)
* [x] Bluetooth diagnostics & repairs orchestrators (`agent/bluetooth_diagnostics.py`, `agent/bluetooth_repairs_orchestrator.py`)
* [x] Deterministic verification & safety test suite with AST audit (`tests/test_bluetooth.py`)
* [!] Intentionally unsupported: Uncontrolled device removal/unpairing, registry tweaks, and shell-based adapter toggling (to preserve zero-shell security boundary)

---

## Phase 12 — Printer

* [ ] Installed printer detection & status
* [ ] Print queue job inspection
* [ ] Print Spooler service status
* [ ] Controlled print spooler restart (MEDIUM)
* [ ] Controlled stuck queue clearing (MEDIUM)
* [ ] Printer verification tools & tests

---

## Phase 13 — Windows Update

* [ ] Windows Update service status (`wuauserv`, `bits`, `cryptsvc`)
* [ ] Windows Update error code & history diagnostics
* [ ] Update connectivity validation
* [ ] Controlled update service restart (MEDIUM)
* [ ] Windows update verification tools & tests

---

## Phase 14 — Windows Defender

* [ ] Windows Defender & Security Center status
* [ ] Real-time protection status inspection
* [ ] Antivirus definition status reporting
* [ ] Strict read-only enforcement (no disabling of security controls)
* [ ] Security explanation & diagnostic tests

---

## Phase 15 — Application Crashes

* [ ] Application crash event log inspection (Application Error events)
* [ ] Target process crash pattern analysis
* [ ] Safe application troubleshooting recommendations
* [ ] Diagnostic reporting without arbitrary file modification

---

## Phase 16 — Personal Tutor

* [ ] Plain-language explanation engine
* [ ] Step-by-step diagnostic breakdown
* [ ] Technical term glossaries & simple analogies
* [ ] Mandatory user confirmation before every repair action
* [ ] Expandable technical details for advanced users
* [ ] Tutor mode workflow tests

---

## Phase 17 — Autopilot

* [ ] Autonomous diagnostic workflow
* [ ] Automatic execution of SAFE diagnostic tools
* [ ] Automatic execution of approved SAFE repairs
* [ ] User prompt & elevation request for MEDIUM-risk repairs
* [ ] Strict blocking of HIGH-risk operations
* [ ] Real-time progress workflow UI
* [ ] Mandatory post-repair verification & reporting

---

## Phase 18 — Screenshot

* [ ] Screenshot / image file upload support (PNG, JPG, JPEG)
* [ ] Local multimodal image analysis via Ollama/Gemma
* [ ] Error message & dialog text extraction
* [ ] Evidence synthesis (screenshot = evidence, not proof)
* [ ] Automatic validation of screenshot evidence against Windows tools
* [ ] Multimodal diagnostic tests

---

## Phase 19 — Voice

* [ ] Local microphone audio capture
* [ ] Local speech-to-text integration
* [ ] Transcription display & user confirmation
* [ ] Direct feed into standard WinFix Agent pipeline
* [ ] Offline voice input testing

---

## Phase 20 — SQLite Knowledge System

* [ ] Local troubleshooting knowledge base seeding
* [ ] Historical session tracking & problem pattern matching
* [ ] Past resolution search & recommendation
* [ ] User feedback loop & resolution scoring
* [ ] Local settings management

---

## Phase 21 — UI/UX Polish

* [ ] Friendly non-technical onboarding experience
* [ ] Tutor vs. Autopilot mode selector
* [ ] Real-time visual progress steppers
* [ ] Standardized Diagnosis, Repair, Success, and Failure Cards
* [ ] Expandable "Technical Details" drawer
* [ ] Sidebar troubleshooting history & session browser
* [ ] Accessibility & visual refinement

---

## Phase 22 — Comprehensive Testing

* [ ] End-to-end integration test suite
* [ ] Offline environment enforcement tests
* [ ] Safety & permission boundary penetration tests
* [ ] UAC elevation failure & timeout scenario tests
* [ ] UI regression testing
* [ ] Performance & memory leak validation

---

## Current Task

Phase 11 completed and validated (193/193 tests passing). Ready for Phase 12 — Printer (Awaiting user prompt before implementing).
