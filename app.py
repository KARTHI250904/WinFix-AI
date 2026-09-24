"""WinFix AI — Streamlit Application (Phases 0, 1, 2, 3, 4, 5, 6, and 7).

Presents system readiness, read-only Windows System Information, live diagnostics,
the local Gemma AI reasoning engine, and controlled Phase 7 verified network repairs.
"""

from typing import Any, Dict, Optional

import streamlit as st

from agent.bluetooth_diagnostics import BluetoothDiagnosticsOrchestrator
from agent.bluetooth_repairs_orchestrator import (
    BluetoothRepairProposal,
    BluetoothRepairsOrchestrator,
)
from agent.network_diagnostics import default_network_orchestrator
from agent.network_repairs_orchestrator import RepairProposal, default_network_repairs_orchestrator
from agent.performance_diagnostics import default_performance_orchestrator
from agent.performance_repairs_orchestrator import (
    PerformanceRepairProposal,
    default_performance_repairs_orchestrator,
)
from agent.planner import default_agent_planner
from agent.service_diagnostics import ServiceDiagnosticsOrchestrator
from agent.service_repairs_orchestrator import (
    ServiceRepairProposal,
    ServiceRepairsOrchestrator,
)
from agent.storage_diagnostics import default_storage_orchestrator
from agent.storage_repairs_orchestrator import (
    StorageRepairProposal,
    default_storage_repairs_orchestrator,
)
from agent.tool_registry import default_tool_registry
from ai.ollama_client import ollama_client
from config import config
from database.db import db_manager
from database.repositories import SessionRepository
from windows.bluetooth_repairs import restart_bluetooth_service
from windows.bluetooth_tools import (
    get_bluetooth_adapters,
    get_bluetooth_devices,
    get_bluetooth_diagnostics,
    get_bluetooth_radio_status,
    get_bluetooth_service_status,
)
from windows.defender_tools import get_defender_diagnostics
from windows.event_tools import get_recent_application_crashes
from windows.network_tools import (
    check_dns_resolution,
    check_internet_connectivity,
    get_network_adapters_diagnostics,
)
from windows.performance_tools import (
    get_cpu_diagnostics,
    get_memory_diagnostics,
    get_top_cpu_processes,
    get_top_memory_processes,
)
from windows.printer_tools import get_printer_diagnostics
from windows.service_tools import get_services_diagnostics, list_common_services
from windows.storage_tools import get_storage_diagnostics, get_temp_storage_info
from windows.system_info import get_complete_system_info
from windows.windows_update_tools import get_windows_update_diagnostics

default_service_orchestrator = ServiceDiagnosticsOrchestrator()
default_service_repairs_orchestrator = ServiceRepairsOrchestrator()
default_bluetooth_orchestrator = BluetoothDiagnosticsOrchestrator()
default_bluetooth_repairs_orchestrator = BluetoothRepairsOrchestrator()



# Page configuration
st.set_page_config(
    page_title=f"{config.app_name} — Assistant & Verified Repairs",
    page_icon="🛠",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_header() -> None:
    """Render top application header and description."""
    st.title(f"🛠 {config.app_name}")
    st.subheader(config.app_tagline)
    st.markdown(
        """
WinFix AI is your **offline Windows troubleshooting assistant**. Powered by local **Gemma AI**
and a hardened **Safety Engine**, it safely diagnoses issues and executes verified repairs with explicit confirmation.
"""
    )
    st.divider()


def render_foundation_status(
    ollama_status: Dict[str, Any],
    db_health: Dict[str, Any],
    session_count: int,
    tool_count: int,
) -> None:
    """Render foundation readiness cards (Ollama, Model, SQLite, Tool Registry)."""
    st.markdown("### 🔌 Foundation & Safety Engine")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### 🧠 Local AI Engine")
        if ollama_status["connected"]:
            if ollama_status["model_available"]:
                st.success(f"✓ Ollama Online & Model Ready (`{config.default_model}`)")
            else:
                st.warning(
                    f"⚠️ Ollama Online, but model `{config.default_model}` is not downloaded locally."
                )
        else:
            st.error("✕ Ollama Offline / Not Reachable")
            st.caption("Ensure the Ollama application is running (`ollama serve`).")

    with col2:
        st.markdown("#### 🗄 Local Database & Repositories")
        if db_health["connected"] and db_health["tables_count"] > 0:
            st.success(
                f"✓ SQLite Ready ({db_health['tables_count']} tables, {session_count} stored sessions)"
            )
        else:
            st.error("✕ Database Not Initialized")

    with col3:
        st.markdown("#### 🛡 Tool Registry & Safety")
        repair_tools = [t for t in default_tool_registry.list_tools() if not t.read_only]
        safe_tools = [t for t in default_tool_registry.list_tools() if t.read_only]
        st.success(f"✓ {tool_count} Tools Registered ({len(safe_tools)} SAFE, {len(repair_tools)} Verified MEDIUM Repairs)")

    st.markdown("---")


def render_ai_diagnostic_assistant(sys_info: Dict[str, Any], ollama_status: Dict[str, Any]) -> None:
    """Render the interactive AI Diagnostic and Verified Repair Assistant interface."""
    st.markdown("### 🤖 AI Diagnostic & Repair Assistant")
    st.markdown(
        "Describe what problem or symptom you are experiencing with your Windows PC. "
        "WinFix AI will diagnose the issue and formulate controlled, verified repair proposals."
    )

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        problem_text = st.text_input(
            "Describe your Windows problem:",
            placeholder="e.g. My internet is not working, or my computer is running slowly.",
            key="user_problem_input",
            label_visibility="collapsed",
        )
    with col_btn:
        diagnose_clicked = st.button("🔍 Diagnose", use_container_width=True, type="primary")

    if diagnose_clicked and problem_text.strip():
        with st.spinner("Gemma is reasoning and executing safe diagnostic checks..."):
            diag_result = default_agent_planner.diagnose(
                problem_description=problem_text,
                system_info=sys_info,
            )
            st.session_state["last_diag_result"] = diag_result
            st.session_state["active_problem"] = problem_text

    # Render previous diagnostic findings if available
    if "last_diag_result" in st.session_state:
        diag_result = st.session_state["last_diag_result"]
        problem_text = st.session_state.get("active_problem", "")
        plan = diag_result.get("plan", {})
        synthesis = diag_result.get("synthesis", {})
        tool_results = diag_result.get("tool_results", [])
        session_id = diag_result.get("session_id", "sess_default")

        st.markdown("#### 📋 Diagnostic Plan & Analysis")
        res_box = st.container(border=True)
        with res_box:
            st.markdown(f"**Likely Cause:** {synthesis.get('likely_cause', 'Under Investigation')}")
            st.write(synthesis.get("summary", ""))

            evidence = synthesis.get("evidence_found", [])
            if evidence:
                st.markdown("**Verified Evidence:**")
                for ev in evidence:
                    st.write(f"• {ev}")

            recommendations = synthesis.get("recommendations", [])
            if recommendations:
                st.markdown("**Safe Next Steps:**")
                for rec in recommendations:
                    st.write(f"• {rec}")

            if diag_result.get("error"):
                st.caption(f"Note: {diag_result.get('error')}")

        # Check for Phase 7 (Network), Phase 8 (Performance), Phase 9 (Storage), Phase 10 (Services), or Phase 11 (Bluetooth) Repair Proposal
        net_category = default_network_orchestrator.classify_network_problem(problem_text)
        net_proposal = default_network_repairs_orchestrator.propose_repair_from_diagnosis(
            problem_category=net_category,
            observed_evidence=evidence or [synthesis.get("summary", "")],
        )

        perf_diag = default_performance_orchestrator.run_diagnostics(session_id=session_id)
        perf_proposal = default_performance_repairs_orchestrator.propose_repair_from_diagnosis(perf_diag)

        storage_diag = default_storage_orchestrator.run_diagnostics(session_id=session_id)
        storage_proposal = default_storage_repairs_orchestrator.propose_repair_from_diagnosis(storage_diag)

        svc_diag = default_service_orchestrator.run_diagnostics(session_id=session_id, user_prompt=problem_text)
        svc_proposal = default_service_repairs_orchestrator.prepare_repair_proposal(svc_diag, session_id=session_id)

        bth_diag = default_bluetooth_orchestrator.run_diagnostics(session_id=session_id, user_prompt=problem_text)
        bth_proposal = default_bluetooth_repairs_orchestrator.prepare_repair_proposal(bth_diag, session_id=session_id)

        proposal = net_proposal or perf_proposal or storage_proposal or svc_proposal or bth_proposal
        proposal_domain = (
            "bluetooth"
            if proposal == bth_proposal and bth_proposal is not None
            else (
                "services"
                if proposal == svc_proposal and svc_proposal is not None
                else (
                    "storage"
                    if proposal == storage_proposal and storage_proposal is not None
                    else (
                        "performance"
                        if proposal == perf_proposal and perf_proposal is not None
                        else "network"
                    )
                )
            )
        )

        if proposal:
            domain_label = (
                "Phase 11 (Bluetooth)"
                if proposal_domain == "bluetooth"
                else (
                    "Phase 10 (Services)"
                    if proposal_domain == "services"
                    else (
                        "Phase 9 (Storage)"
                        if proposal_domain == "storage"
                        else (
                            "Phase 8 (Performance)"
                            if proposal_domain == "performance"
                            else "Phase 7 (Network)"
                        )
                    )
                )
            )
            st.markdown(f"#### ⚙️ Controlled Repair Proposal — {domain_label}")
            repair_box = st.container(border=True)
            with repair_box:
                st.warning(f"⚠️ **Proposed Action:** `{proposal.tool_name}` (Risk: **{proposal.risk}**)")
                st.write(f"**Why:** {proposal.reason}")
                st.write(f"**Expected Effect:** {proposal.expected_effect}")
                if proposal.requires_admin:
                    st.info("ℹ️ **Administrator Permission:** This operation may require administrator privileges.")
                st.caption(f"Verification will be performed automatically using: `{proposal.verification_tool}`")

                token = proposal.generate_confirmation_token(session_id)

                col_conf1, col_conf2 = st.columns([1, 3])
                with col_conf1:
                    confirm_btn = st.button(f"🛡 Confirm & Execute Repair", type="primary", key="confirm_repair_btn")

                if confirm_btn:
                    with st.spinner(f"Executing `{proposal.tool_name}` and running verification..."):
                        if proposal_domain == "bluetooth":
                            repair_res = default_bluetooth_repairs_orchestrator.execute_confirmed_repair(
                                tool_name=proposal.tool_name,
                                arguments=proposal.arguments,
                                confirmation_token=token,
                                session_id=session_id,
                            )
                        elif proposal_domain == "services":
                            repair_res = default_service_repairs_orchestrator.execute_confirmed_repair(
                                tool_name=proposal.tool_name,
                                arguments=proposal.arguments,
                                confirmation_token=token,
                                session_id=session_id,
                            )
                        elif proposal_domain == "storage":
                            repair_res = default_storage_repairs_orchestrator.execute_repair_with_verification(
                                proposal=proposal,
                                session_id=session_id,
                                user_confirmed=True,
                                confirmation_token=token,
                            )
                        elif proposal_domain == "performance":
                            repair_res = default_performance_repairs_orchestrator.execute_repair_with_verification(
                                proposal=proposal,
                                session_id=session_id,
                                user_confirmed=True,
                                confirmation_token=token,
                            )
                        else:
                            repair_res = default_network_repairs_orchestrator.execute_repair_with_verification(
                                proposal=proposal,
                                session_id=session_id,
                                user_confirmed=True,
                                confirmation_token=token,
                            )


                    st.markdown("##### 🔍 Repair & Verification Results")
                    if repair_res.verification_status == "verified":
                        st.success(f"✓ **Repair Verified:** {repair_res.explanation}")
                    elif repair_res.verification_status == "not_verified":
                        st.warning(f"⚠️ **Not Verified:** {repair_res.explanation}")
                    else:
                        st.error(f"✕ **Repair Failed:** {repair_res.explanation}")

                    with st.expander("📊 State Comparison (Before vs After)"):
                        st.json({
                            "repair_action": repair_res.tool_name,
                            "repair_output": repair_res.repair_output,
                            "before_state": repair_res.before_state,
                            "after_state": repair_res.after_state,
                            "verification_tool": repair_res.verification_tool,
                            "verification_status": repair_res.verification_status,
                        })


        # Tools Executed Details
        if tool_results:
            with st.expander(f"🛠 Inspected Diagnostic Subsystems ({len(tool_results)} tools executed)"):
                for tr in tool_results:
                    t_name = tr.get("tool_name")
                    res_obj = tr.get("result", {})
                    success = res_obj.get("success", False)
                    dur = res_obj.get("duration_ms", 0)
                    icon = "🟢" if success else "🔴"
                    st.write(f"{icon} **`{t_name}`** ({dur} ms) — *{tr.get('purpose', '')}*")

    st.markdown("---")


def render_system_information(sys_info: Dict[str, Any]) -> None:
    """Render structured read-only Windows system information cards."""
    st.markdown("### 💻 Your Computer Information")

    os_info = sys_info.get("os", {})
    comp_info = sys_info.get("computer", {})
    cpu_info = sys_info.get("cpu", {})
    mem_info = sys_info.get("memory", {})
    disk_info = sys_info.get("disk", {})
    uptime_info = sys_info.get("uptime", {})

    # Row 1: OS & Processor
    col_os, col_cpu = st.columns(2)

    with col_os:
        st.markdown("#### 🪟 Windows & Device")
        if os_info.get("status") == "available":
            st.write(f"**Edition:** {os_info.get('edition', 'Windows')}")
            st.write(f"**Version / Build:** {os_info.get('display_version', '')} (Build {os_info.get('build_number', 'Unknown')})")
            st.write(f"**Architecture:** {os_info.get('architecture', '64-bit')}")
        else:
            st.warning("Could not read operating system details.")

        if comp_info.get("status") == "available":
            st.write(f"**Computer Name:** `{comp_info.get('computer_name', 'Unknown')}`")
            st.write(f"**Current User:** `{comp_info.get('username', 'Unknown')}`")

    with col_cpu:
        st.markdown("#### ⚡ Processor (CPU)")
        if cpu_info.get("status") == "available":
            st.write(f"**Model:** {cpu_info.get('model', 'Unknown')}")
            st.write(f"**Physical Cores:** {cpu_info.get('physical_cores', 'Unknown')}")
            st.write(f"**Logical Threads:** {cpu_info.get('logical_threads', 'Unknown')}")
            freq = cpu_info.get("frequency")
            if freq and freq.get("current_mhz"):
                st.write(f"**Current Frequency:** {freq['current_mhz']} MHz")
        else:
            st.warning("Could not read processor details.")

    st.markdown("---")

    # Row 2: Memory & System Uptime
    col_mem, col_upt = st.columns(2)

    with col_mem:
        st.markdown("#### 🧠 Memory (RAM)")
        if mem_info.get("status") == "available":
            total = mem_info.get("total_formatted", "Unknown")
            available = mem_info.get("available_formatted", "Unknown")
            used = mem_info.get("used_formatted", "Unknown")
            pct = mem_info.get("percent_used", 0.0)

            st.write(f"**Total RAM:** {total} (Used: {used} | Available: {available})")
            st.progress(min(max(pct / 100.0, 0.0), 1.0), text=f"RAM Usage: {pct:.1f}%")
        else:
            st.warning("Could not read memory details.")

    with col_upt:
        st.markdown("#### ⏱ System Uptime")
        if uptime_info.get("status") == "available":
            st.write(f"**Current Uptime:** {uptime_info.get('uptime_formatted', 'Unknown')}")
            st.write(f"**Last Booted:** {uptime_info.get('boot_time_formatted', 'Unknown')}")
        else:
            st.warning("Could not read uptime details.")

    st.markdown("---")

    # Row 3: Storage & Drives
    st.markdown("#### 💾 Storage Drives")
    if disk_info.get("status") == "available" and disk_info.get("drives"):
        d_cols = st.columns(len(disk_info["drives"]))
        for idx, drive in enumerate(disk_info["drives"]):
            with d_cols[idx]:
                is_sys = " (System Drive)" if drive.get("is_system_drive") else ""
                st.markdown(f"**Drive {drive.get('mountpoint', '')}{is_sys}**")
                if drive.get("accessible"):
                    st.write(f"Free: **{drive.get('free_formatted', 'Unknown')}** / {drive.get('total_formatted', 'Unknown')}")
                    pct = drive.get("percent_used") or 0.0
                    st.progress(min(max(pct / 100.0, 0.0), 1.0), text=f"Used: {pct:.1f}%")
                else:
                    st.caption("Drive details not accessible.")
    else:
        st.warning("Could not read storage drive information.")

    st.markdown("---")


def render_readonly_diagnostics(diag_data: Dict[str, Any]) -> None:
    """Render live read-only diagnostic checks across domains."""
    st.markdown("### 🩺 System Diagnostics Overview")

    diag_tabs = st.tabs(
        [
            "🌐 Network & DNS",
            "⚡ Top Processes",
            "⚙️ Windows Services",
            "🛡 Security & Defender",
            "🖨 Devices & Printers",
            "🚨 Application Events",
        ]
    )

    # Tab 1: Network & DNS
    with diag_tabs[0]:
        dns_res = diag_data.get("dns", {})
        net_conn = diag_data.get("internet", {})
        adapters_res = diag_data.get("adapters", {})

        n_col1, n_col2 = st.columns(2)
        with n_col1:
            st.markdown("##### 🔍 DNS Resolution Check")
            if dns_res.get("success") and dns_res.get("data", {}).get("resolved"):
                st.success(f"✓ DNS Resolution Working ({dns_res['data'].get('latency_ms')} ms)")
                ips = ", ".join(dns_res["data"].get("resolved_ips", []))
                st.caption(f"Resolved IPs for `{dns_res['data'].get('target_host')}`: {ips}")
            else:
                st.error("✕ DNS Lookup Failed")

        with n_col2:
            st.markdown("##### 🌐 Internet Reachability Check")
            if net_conn.get("success") and net_conn.get("data", {}).get("reachable"):
                st.success(f"✓ Internet Gateway Reachable ({net_conn['data'].get('latency_ms')} ms)")
                st.caption(f"Target: {net_conn['data'].get('target')}")
            else:
                st.error("✕ Internet Host Unreachable")

        st.markdown("##### 🔌 Network Interfaces")
        if adapters_res.get("success"):
            adapters = adapters_res.get("data", {}).get("adapters", [])
            for ad in adapters:
                if ad.get("is_up") and ad.get("ipv4"):
                    ips = ", ".join(ad.get("ipv4", []))
                    speed = f" — {ad.get('speed_mbps')} Mbps" if ad.get("speed_mbps") else ""
                    st.write(f"✓ **{ad.get('name')}**: `{ips}`{speed}")

    # Tab 2: Top Processes
    with diag_tabs[1]:
        p_col1, p_col2 = st.columns(2)
        top_cpu = diag_data.get("top_cpu", {}).get("data", {}).get("processes", [])
        top_mem = diag_data.get("top_mem", {}).get("data", {}).get("processes", [])

        with p_col1:
            st.markdown("##### 🔥 Top CPU Consuming Processes")
            if top_cpu:
                for p in top_cpu:
                    st.write(f"• **{p.get('name')}** (PID: {p.get('pid')}): `{p.get('cpu_percent')}% CPU`")
            else:
                st.caption("No active process CPU metrics available.")

        with p_col2:
            st.markdown("##### 🧠 Top Memory Consuming Processes")
            if top_mem:
                for p in top_mem:
                    st.write(f"• **{p.get('name')}** (PID: {p.get('pid')}): `{p.get('memory_formatted')}` ({p.get('memory_percent')}%)")
            else:
                st.caption("No active process memory metrics available.")

    # Tab 3: Windows Services
    with diag_tabs[2]:
        services_res = diag_data.get("services", {})
        if services_res.get("success"):
            services = services_res.get("data", {}).get("services", [])
            st.write(f"**Monitored {len(services)} standard Windows troubleshooting services:**")
            s_cols = st.columns(2)
            for idx, svc in enumerate(services):
                with s_cols[idx % 2]:
                    status_icon = "🟢" if svc.get("is_running") else "⚪"
                    st.write(f"{status_icon} **{svc.get('display_name')}** (`{svc.get('name')}`): *{svc.get('status')}*")

    # Tab 4: Security & Defender
    with diag_tabs[3]:
        def_res = diag_data.get("defender", {})
        wu_res = diag_data.get("windows_update", {})

        sec_col1, sec_col2 = st.columns(2)
        with sec_col1:
            st.markdown("##### 🛡 Microsoft Defender")
            if def_res.get("success"):
                d_data = def_res.get("data", {})
                av_status = "Active & Running" if d_data.get("antivirus_service_running") else "Stopped / Inactive"
                fw_status = "Active & Running" if d_data.get("firewall_service_running") else "Stopped / Inactive"
                st.write(f"• **Antivirus Protection:** {av_status}")
                st.write(f"• **Windows Firewall:** {fw_status}")
                if d_data.get("signature_version"):
                    st.write(f"• **Signature Version:** `{d_data.get('signature_version')}`")

        with sec_col2:
            st.markdown("##### 🔄 Windows Update Service")
            if wu_res.get("success"):
                w_data = wu_res.get("data", {})
                w_ready = "Ready" if w_data.get("update_services_ready") else "Attention Needed"
                st.write(f"• **Update Services State:** {w_ready}")
                if w_data.get("last_success_time"):
                    st.write(f"• **Last Successful Update:** `{w_data.get('last_success_time')}`")

    # Tab 5: Devices & Printers
    with diag_tabs[4]:
        prn_res = diag_data.get("printer", {})
        bth_res = diag_data.get("bluetooth", {})

        dev_col1, dev_col2 = st.columns(2)
        with dev_col1:
            st.markdown("##### 🖨 Printers & Spooler")
            if prn_res.get("success"):
                p_data = prn_res.get("data", {})
                spooler = "Running" if p_data.get("spooler_running") else "Stopped"
                st.write(f"• **Print Spooler:** {spooler}")
                st.write(f"• **Default Printer:** `{p_data.get('default_printer') or 'None'}`")
                st.write(f"• **Total Installed Printers:** {p_data.get('total_printers')}")

        with dev_col2:
            st.markdown("##### 📶 Bluetooth")
            if bth_res.get("success"):
                b_data = bth_res.get("data", {})
                b_svc = "Running" if b_data.get("service_running") else "Stopped"
                b_hw = "Detected" if b_data.get("adapter_detected") else "Not Detected"
                st.write(f"• **Bluetooth Support Service:** {b_svc}")
                st.write(f"• **Bluetooth Adapter Hardware:** {b_hw}")

    # Tab 6: Application Crash Events
    with diag_tabs[5]:
        evt_res = diag_data.get("events", {})
        if evt_res.get("success"):
            crashes = evt_res.get("data", {}).get("crashes", [])
            st.write(f"**Scanned {evt_res.get('data', {}).get('events_scanned', 0)} recent events (found {len(crashes)} error/crash events):**")
            if crashes:
                for c in crashes:
                    with st.container():
                        st.markdown(f"**[{c.get('event_type')}] {c.get('source')}** — *{c.get('timestamp')}* (Event ID: {c.get('event_id')})")
                        st.caption(f"{c.get('message_summary')}")
                        st.markdown("---")
            else:
                st.success("No recent application crash events detected in the Windows Application log.")
        else:
            st.info("Windows Application event log query is not supported or restricted.")


def render_technical_drawer(
    sys_info: Dict[str, Any],
    ollama_status: Dict[str, Any],
    db_health: Dict[str, Any],
    diag_data: Dict[str, Any],
) -> None:
    """Render expandable drawer with complete diagnostic JSON data and tool registry status."""
    with st.expander("🔍 Expand Technical Details & Raw Diagnostics"):
        st.markdown("#### Approved Tool Registry Metadata")
        tools_summary = [t.to_dict() for t in default_tool_registry.list_tools()]
        st.json(tools_summary)

        st.markdown("#### Complete Read-Only Diagnostics Payload")
        st.json(diag_data)

        st.markdown("#### Complete System Information Payload")
        st.json(sys_info)

        st.markdown("#### Ollama Status Payload")
        st.json(ollama_status)

        st.markdown("#### SQLite Database Diagnostics")
        st.json(db_health)


def main() -> None:
    """Main application loop."""
    render_header()

    # 1. Database Health Check & Auto-Init
    db_health = db_manager.check_health()
    if db_health["connected"] and db_health["tables_count"] == 0:
        db_manager.init_db()
        db_health = db_manager.check_health()

    session_repo = SessionRepository(db_manager)
    session_count = session_repo.count() if db_health["connected"] else 0
    tool_count = default_tool_registry.count()

    # 2. Ollama & Model Health Check
    with st.spinner("Checking Ollama runtime..."):
        ollama_status = ollama_client.check_model_availability()

    # 3. Collect Read-Only System Information
    with st.spinner("Collecting Windows system information..."):
        sys_info = get_complete_system_info()

    # 4. Collect Read-Only Windows Diagnostics across Domains
    with st.spinner("Running safe read-only diagnostics..."):
        diag_data = {
            "dns": check_dns_resolution(),
            "internet": check_internet_connectivity(),
            "adapters": get_network_adapters_diagnostics(),
            "top_cpu": get_top_cpu_processes(limit=5),
            "top_mem": get_top_memory_processes(limit=5),
            "storage": get_storage_diagnostics(),
            "temp_storage": get_temp_storage_info(),
            "services": list_common_services(),
            "defender": get_defender_diagnostics(),
            "windows_update": get_windows_update_diagnostics(),
            "printer": get_printer_diagnostics(),
            "bluetooth": get_bluetooth_diagnostics(),
            "events": get_recent_application_crashes(limit=5, max_scan=50),
        }

    # Render dashboard sections
    render_foundation_status(ollama_status, db_health, session_count, tool_count)
    render_ai_diagnostic_assistant(sys_info, ollama_status)
    render_system_information(sys_info)
    render_readonly_diagnostics(diag_data)

    st.markdown("---")

    # Maintenance & Refresh
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        if st.button("🔄 Refresh All Diagnostics", use_container_width=True):
            st.rerun()
    with m_col2:
        if st.button("📦 Re-initialize Database Schema", use_container_width=True):
            res = db_manager.init_db()
            if res["success"]:
                st.success(f"Database initialized with {len(res['tables'])} tables!")
            st.rerun()

    # Technical Details Drawer
    render_technical_drawer(sys_info, ollama_status, db_health, diag_data)

    # Sidebar: About and Roadmap
    with st.sidebar:
        st.markdown(f"### 🛠 {config.app_name}")
        st.caption(f"Version {config.app_version}")
        st.markdown("---")
        st.markdown("**Completed Phases:**")
        st.markdown(
            """
- [x] Phase 0 — Foundation
- [x] Phase 1 — System Information
- [x] Phase 2 — SQLite Foundation
- [x] Phase 3 — Read-only Windows Tools
- [x] Phase 4 — Tool Registry + Safety
- [x] Phase 5 — Ollama/Gemma Agent Core
- [x] Phase 6 — Network Diagnostics
- [x] Phase 7 — Network Repairs + Verification
"""
        )
        st.markdown("---")
        st.markdown("**Safety Rule:**")
        st.info("`LLM != Windows Shell`\n\nAll actions must use explicitly registered tools and pass strict safety validation.")


if __name__ == "__main__":
    main()
