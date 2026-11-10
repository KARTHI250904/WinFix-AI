"""WinFix AI — Streamlit Application (Phases 0, 1, 2, 3, 4, 5, 6, and 7).

Presents system readiness, read-only Windows System Information, live diagnostics,
the local Gemma AI reasoning engine, and controlled Phase 7 verified network repairs.
"""

from datetime import datetime
import os
import time
from typing import Any, Dict, Optional, Set

# Enforce 100% offline air-gapped execution environment
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

import streamlit as st

from production.config import prod_config
from production.logging import setup_production_logging

# Initialize production logging with privacy sanitization (idempotent across Streamlit script reruns)
setup_production_logging(prod_config)

from agent.application_crash_diagnostics import (
    ApplicationCrashDiagnosticsOrchestrator,
    default_application_crash_orchestrator,
)
from agent.bluetooth_diagnostics import BluetoothDiagnosticsOrchestrator
from agent.bluetooth_repairs_orchestrator import (
    BluetoothRepairProposal,
    BluetoothRepairsOrchestrator,
)
from agent.defender_diagnostics import DefenderDiagnosticsOrchestrator
from agent.defender_repairs_orchestrator import (
    DefenderRepairProposal,
    DefenderRepairsOrchestrator,
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
from modes.autopilot import default_autopilot_engine
from modes.autopilot_models import AutopilotPlan, AutopilotResult, AutopilotStatus
from modes.personal_tutor import default_personal_tutor
from modes.tutor_models import (
    ProblemInput,
    StepStatus,
    TroubleshootingSession,
    TroubleshootingStep,
    TutorResponse,
    TutorSeverity,
)
from ai.screenshot_analyzer import default_screenshot_analyzer
from input.screenshot_models import ScreenshotAnalysis
from agent.voice_diagnostics import default_voice_orchestrator
from ai.voice_transcriber import is_valid_transcript
from input.voice_models import VoiceAnalysis, VoiceStatus, VoiceTranscript
from knowledge.knowledge_service import default_knowledge_service
from database.knowledge_models import KnowledgeArticle
from ui import (
    AppMode,
    ConfidenceLevel,
    MODE_DESCRIPTIONS,
    UIStateManager,
    UIStatusState,
    format_bytes,
    format_human_verification_status,
    format_progress_step,
    format_risk_badge,
    format_severity_badge,
    format_status_badge,
    format_timestamp,
    format_tool_name,
    format_tutor_prose,
    format_tutor_text_list,
    format_tutor_tool_description,
    format_user_friendly_terminology,
    map_confidence,
    render_ai_lifecycle_panel,
    render_app_header,
    render_confirmation_card,
    render_empty_state,
    render_error_state,
    render_evidence_card,
    render_knowledge_card,
    render_mode_selector,
    render_privacy_notice,
    render_recovery_card,
    render_standardized_diagnosis_card,
    render_diagnostic_results_table,
    render_runtime_health_tables,
    render_standardized_repair_proposal_card,
    render_standardized_verification_card,
    render_structured_diagnostic_card,
    render_system_info_table,
    render_system_status_panel,
    render_tool_card,
    render_user_friendly_error,
    render_verification_result,
    render_welcome_guide,
    render_workflow_steps,
    render_json_as_table,
)

from windows.application_crash_tools import (
    get_application_crash_details,
    get_application_crash_diagnostics,
    get_application_crash_events,
    get_application_crash_frequency,
    get_application_crash_summary,
    get_faulting_module_information,
    get_recent_application_crashes,
    get_windows_error_reporting_status,
)
from windows.bluetooth_repairs import restart_bluetooth_service
from windows.bluetooth_tools import (
    get_bluetooth_adapters,
    get_bluetooth_devices,
    get_bluetooth_diagnostics,
    get_bluetooth_radio_status,
    get_bluetooth_service_status,
)
from windows.defender_tools import get_defender_diagnostics
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

from agent.windows_update_diagnostics import WindowsUpdateDiagnosticsOrchestrator
from agent.windows_update_repairs_orchestrator import (
    WindowsUpdateRepairProposal,
    WindowsUpdateRepairsOrchestrator,
)

default_service_orchestrator = ServiceDiagnosticsOrchestrator()
default_service_repairs_orchestrator = ServiceRepairsOrchestrator()
default_bluetooth_orchestrator = BluetoothDiagnosticsOrchestrator()
default_bluetooth_repairs_orchestrator = BluetoothRepairsOrchestrator()
default_windows_update_orchestrator = WindowsUpdateDiagnosticsOrchestrator()
default_windows_update_repairs_orchestrator = WindowsUpdateRepairsOrchestrator()
default_defender_orchestrator = DefenderDiagnosticsOrchestrator()
default_defender_repairs_orchestrator = DefenderRepairsOrchestrator()




# Page configuration
st.set_page_config(
    page_title=f"{config.app_name} — Assistant & Verified Repairs",
    page_icon="🛠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Force pure white background and clear high-contrast light theme
st.markdown(
    """
    <style>
    /* Main application canvas */
    .stApp {
        background-color: #FFFFFF !important;
        color: #1E293B !important;
    }
    /* Content block */
    .main .block-container {
        background-color: #FFFFFF !important;
    }
    /* Clean light sidebar */
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
    }
    /* High contrast text & headers */
    h1, h2, h3, h4, h5, h6, p, label, .stMarkdown {
        color: #1E293B;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_header() -> None:
    """Render top application header and description."""
    render_app_header(is_offline=True)


def render_foundation_status(
    ollama_status: Dict[str, Any],
    db_health: Dict[str, Any],
    session_count: int,
    tool_count: int,
) -> None:
    """Render foundation readiness cards (Ollama, Model, SQLite, Tool Registry, Knowledge)."""
    kb_stats = default_knowledge_service.get_stats()
    render_system_status_panel(
        ollama_status=ollama_status,
        db_health=db_health,
        session_count=session_count,
        tool_count=tool_count,
        kb_stats=kb_stats,
    )
    try:
        from ai.model_manager import ai_model_manager
        if "cached_ai_agg" not in st.session_state:
            st.session_state["cached_ai_agg"] = ai_model_manager.check_aggregate_ai_health()
        ai_agg = st.session_state["cached_ai_agg"]
        render_ai_lifecycle_panel(ai_agg.to_dict())
    except Exception:
        pass
    render_privacy_notice(st.session_state.get("app_operating_mode", "🔍 Diagnostic & Repair Assistant"))


def log_session_task(
    mode: str,
    title: str,
    summary: str,
    status: str = "COMPLETED",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a completed task or diagnostic evaluation to the active session activity log."""
    if "session_task_history" not in st.session_state:
        st.session_state["session_task_history"] = []

    time_str = datetime.now().strftime("%H:%M:%S")
    entry = {
        "id": f"task_{int(time.time() * 1000)}",
        "timestamp": time_str,
        "mode": mode,
        "title": title,
        "summary": summary,
        "status": status,
        "details": details or {},
    }
    # Avoid duplicate consecutive entries with identical mode & title
    if st.session_state["session_task_history"]:
        last = st.session_state["session_task_history"][-1]
        if last["mode"] == mode and last["title"] == title and last["summary"] == summary:
            return
    st.session_state["session_task_history"].append(entry)


def render_sidebar_task_reports() -> None:
    """Render dynamic session task reports and export drawer in the sidebar."""
    st.markdown("---")
    history = st.session_state.get("session_task_history", [])
    task_count = len(history)

    st.markdown(f"### 📋 Session Task Reports ({task_count})")
    if not history:
        st.caption("No tasks recorded yet in this session. Activity reports will appear here in real-time as you diagnose, ask Tutor, upload screenshots/audio, or run Autopilot.")
        return

    # Render each task (most recent first)
    for idx, t in enumerate(reversed(history)):
        mode_icons = {
            "🔍 Diagnostic Assistant": "🔍",
            "🔧 Verified Repair": "🔧",
            "🎓 Personal Tutor": "🎓",
            "🤖 Autopilot Planned": "📋",
            "🤖 Autopilot Executed": "🤖",
            "📷 Screenshot Diagnostics": "📷",
            "📷 Screenshot Q&A": "💬",
            "🎤 Voice Diagnostics": "🎤",
        }
        icon = mode_icons.get(t["mode"], "📝")
        
        status_badges = {
            "COMPLETED": "🟢",
            "SUCCESS": "🟢",
            "VERIFIED": "🟢",
            "PARTIAL": "🟡",
            "PLANNED": "🔵",
            "FAILED": "🔴",
            "BLOCKED": "🔴",
            "DEGRADED": "🟠",
        }
        st_icon = status_badges.get(str(t["status"]).upper(), "⚪")

        with st.expander(f"{icon} {t['timestamp']} — {t['title'][:26]}", expanded=(idx == 0)):
            st.markdown(f"**Mode:** `{t['mode']}`")
            st.markdown(f"**Status:** {st_icon} `{t['status']}`")
            st.write(f"**Summary:** {t['summary']}")
            if t.get("details"):
                for k, v in t["details"].items():
                    st.caption(f"• **{k}:** {v}")

    # Export & Clear controls
    col_dl, col_clr = st.columns([3, 2])
    with col_dl:
        md_lines = [
            f"# WinFix AI — Session Task & Activity Report",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Tasks Recorded:** {len(history)}",
            "\n---\n",
        ]
        for item in history:
            md_lines.append(f"### [{item['timestamp']}] {item['mode']} — {item['title']}")
            md_lines.append(f"- **Status:** `{item['status']}`")
            md_lines.append(f"- **Summary:** {item['summary']}")
            if item.get("details"):
                for dk, dv in item["details"].items():
                    md_lines.append(f"  - **{dk}:** {dv}")
            md_lines.append("")

        report_md = "\n".join(md_lines)
        st.download_button(
            label="📥 Export Report",
            data=report_md,
            file_name=f"WinFix_Session_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            use_container_width=True,
            key="btn_download_session_report",
        )
    with col_clr:
        if st.button("🗑️ Clear Log", use_container_width=True, key="btn_clear_session_tasks"):
            st.session_state["session_task_history"] = []
            st.rerun()


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
            synthesis = diag_result.get("synthesis", {})
            log_session_task(
                mode="🔍 Diagnostic Assistant",
                title=f"Diagnose: {problem_text[:35]}",
                summary=synthesis.get("summary", "Diagnostics completed"),
                status="COMPLETED",
                details={
                    "Likely Cause": synthesis.get("likely_cause", "Under Investigation"),
                    "Tools Inspected": f"{len(diag_result.get('tool_results', []))} checks performed",
                },
            )

    # Render previous diagnostic findings if available
    if "last_diag_result" in st.session_state:
        diag_result = st.session_state["last_diag_result"]
        problem_text = st.session_state.get("active_problem", "")
        plan = diag_result.get("plan", {})
        synthesis = diag_result.get("synthesis", {})
        tool_results = diag_result.get("tool_results", [])
        session_id = diag_result.get("session_id", "sess_default")

        # Render standardized diagnostic card (Phase 35)
        evidence = synthesis.get("evidence_found", [])
        recommendations = synthesis.get("recommendations", [])
        tech_details = {
            "Session ID": session_id,
            "Tools Inspected": len(tool_results),
            "Planning Model": diag_result.get("model", "Local Gemma AI / Deterministic Engine"),
        }
        render_standardized_diagnosis_card(
            summary=synthesis.get("summary", "Analysis completed."),
            likely_cause=synthesis.get("likely_cause", "Under Investigation"),
            evidence=evidence,
            recommendations=recommendations,
            observations=synthesis.get("observations"),
            inferences=synthesis.get("inferences"),
            unknowns=synthesis.get("uncertainty"),
            contradictions=synthesis.get("contradictions"),
            technical_details=tech_details,
        )

        # Local Troubleshooting Knowledge Integration (Phase 19)
        kb_matches = default_knowledge_service.search(problem_text, limit=1, session_id=session_id)
        if kb_matches and kb_matches[0].article:
            kb_art = kb_matches[0].article
            render_knowledge_card(kb_art)

        # Check for Domain Repair Proposals
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

        wu_diag = default_windows_update_orchestrator.run_diagnostics(session_id=session_id, user_prompt=problem_text)
        wu_proposal = default_windows_update_repairs_orchestrator.prepare_restart_proposal(session_id=session_id, diagnosis=wu_diag) if wu_diag.repair_available else None

        def_diag = default_defender_orchestrator.run_diagnostics(session_id=session_id, user_prompt=problem_text)
        def_proposal = default_defender_repairs_orchestrator.prepare_restart_proposal(session_id=session_id, diagnosis=def_diag) if def_diag.repair_available else None

        proposal = net_proposal or perf_proposal or storage_proposal or svc_proposal or bth_proposal or wu_proposal or def_proposal
        proposal_domain = (
            "defender"
            if proposal == def_proposal and def_proposal is not None
            else (
                "windows_update"
                if proposal == wu_proposal and wu_proposal is not None
                else (
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
            )
        )

        if proposal:
            domain_label = (
                "Windows Defender"
                if proposal_domain == "defender"
                else (
                    "Windows Update"
                    if proposal_domain == "windows_update"
                    else (
                        "Bluetooth"
                        if proposal_domain == "bluetooth"
                        else (
                            "Windows Services"
                            if proposal_domain == "services"
                            else (
                                "Storage"
                                if proposal_domain == "storage"
                                else (
                                    "System Performance"
                                    if proposal_domain == "performance"
                                    else "Network & Internet"
                                )
                            )
                        )
                    )
                )
            )
            render_standardized_repair_proposal_card(proposal, domain_label=domain_label)

            token = proposal.generate_confirmation_token(session_id)

            col_conf1, col_conf2 = st.columns([1, 3])
            with col_conf1:
                confirm_btn = st.button("🛡 Confirm & Apply Fix", type="primary", key="confirm_repair_btn")

            if confirm_btn:
                with st.spinner(f"Applying approved fix and verifying Windows state..."):
                    if proposal_domain == "defender":
                        repair_res = default_defender_repairs_orchestrator.execute_confirmed_restart(
                            proposal=proposal,
                            user_confirmed_token=token,
                            session_id=session_id,
                        )
                    elif proposal_domain == "windows_update":
                        repair_res = default_windows_update_repairs_orchestrator.execute_confirmed_restart(
                            proposal=proposal,
                            user_confirmed_token=token,
                            session_id=session_id,
                        )
                    elif proposal_domain == "bluetooth":
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

                st.session_state["last_repair_result"] = repair_res
                log_session_task(
                    mode="🔧 Verified Repair",
                    title=f"Repair: {repair_res.tool_name}",
                    summary=repair_res.explanation,
                    status="VERIFIED" if str(repair_res.verification_status).lower() == "verified" else "COMPLETED",
                    details={
                        "Tool": repair_res.tool_name,
                        "Verification": str(repair_res.verification_status),
                    },
                )
                render_standardized_verification_card(
                    verification_status=repair_res.verification_status,
                    explanation=repair_res.explanation,
                    tool_name=repair_res.tool_name,
                    before_state=repair_res.before_state,
                    after_state=repair_res.after_state,
                    verification_tool=repair_res.verification_tool,
                )

        # Tools Executed Details
        if tool_results:
            with st.expander(f"🛠 Diagnostic Inspection Details ({len(tool_results)} checks performed)", expanded=False):
                for tr in tool_results:
                    t_name = tr.get("tool_name")
                    res_obj = tr.get("result", {})
                    success = res_obj.get("success", False)
                    dur = res_obj.get("duration_ms", 0)
                    icon = "🟢" if success else "🔴"
                    st.write(f"{icon} **`{format_tool_name(t_name)}`** ({dur} ms) — *{tr.get('purpose', '')}*")
    else:
        render_empty_state(
            mode_name="Diagnostic & Repair Assistant",
            headline="Ready to diagnose your PC",
            suggestions=[
                "Describe a problem above (e.g. 'Wi-Fi disconnected' or 'Windows Update is stuck')",
                "WinFix AI inspects relevant components using read-only diagnostic tools",
                "If a verified repair is suggested, you will review and explicitly approve it before execution",
            ],
        )

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

    # Tab 6: Application Crash Diagnostics
    with diag_tabs[5]:
        evt_res = diag_data.get("events", {})
        sum_res = diag_data.get("crash_summary", {})
        wer_res = diag_data.get("wer_status", {})

        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.markdown("##### 📊 24-Hour Crash Summary")
            if sum_res.get("success"):
                s_data = sum_res.get("data", {})
                st.write(f"• **Total Crashes Observed:** {s_data.get('total_crashes', 0)}")
                st.write(f"• **Unique Faulting Apps:** {s_data.get('unique_applications', 0)}")
                st.write(f"• **Unique Faulting Modules:** {s_data.get('unique_faulting_modules', 0)}")
                if s_data.get("recurring_applications"):
                    st.warning(f"⚠️ Recurring Crashes: {', '.join(s_data['recurring_applications'])}")
            else:
                st.caption("Crash summary metrics unavailable.")

        with c_col2:
            st.markdown("##### ⚙️ Windows Error Reporting (WER)")
            if wer_res.get("success"):
                w_data = wer_res.get("data", {})
                w_svc = "Running" if w_data.get("service_running") else "Stopped"
                w_dis = "Yes (Disabled)" if w_data.get("disabled") else "No (Active)"
                st.write(f"• **WER Service:** {w_svc}")
                st.write(f"• **WER Disabled Policy:** {w_dis}")
                st.write(f"• **Crash Reporting Ready:** {'Yes' if w_data.get('error_reporting_ready') else 'No'}")
            else:
                st.caption("WER status unavailable.")

        st.markdown("---")
        st.markdown("##### 🔍 Recent Application Crash Events")
        if evt_res.get("success"):
            crashes = evt_res.get("data", {}).get("crashes", [])
            st.write(f"**Scanned {evt_res.get('data', {}).get('events_scanned', 0)} recent events (found {len(crashes)} error/crash events):**")
            if crashes:
                for c in crashes:
                    with st.container():
                        st.markdown(f"**[{c.get('event_type')}] {c.get('source')}** — *{c.get('timestamp')}* (Event ID: {c.get('event_id')})")
                        if c.get("application_name"):
                            st.write(f"• **Application:** `{c.get('application_name')}` (PID: {c.get('process_id') or 'N/A'})")
                        if c.get("faulting_module"):
                            st.write(f"• **Faulting Module:** `{c.get('faulting_module')}` (Exception: `{c.get('exception_code') or 'N/A'}`)")
                        st.caption(f"{c.get('message_summary')}")
                        st.markdown("---")
            else:
                st.success("No recent application crash events detected in the Windows Application log.")
        else:
            st.info("Windows Application event log query is not supported or restricted.")


def render_tutor_response_card(resp: TutorResponse) -> None:
    """Render a structured TutorResponse with human-readable sentences and educational sections."""
    sev = resp.severity.upper() if isinstance(resp.severity, str) else (resp.severity.value if hasattr(resp.severity, "value") else "UNKNOWN")
    sev_colors = {
        "NORMAL": "🟢 NORMAL",
        "ELEVATED": "🟡 ELEVATED",
        "HIGH": "🟠 HIGH",
        "CRITICAL": "🔴 CRITICAL",
        "UNKNOWN": "⚪ UNKNOWN",
    }
    sev_badge = sev_colors.get(sev, f"⚪ {sev}")

    title_text = format_tutor_prose(resp.title, fallback="WinFix AI Tutor Explanation")
    st.markdown(f"### 🎓 {title_text}")
    st.caption(f"Diagnostic Severity: **{sev_badge}**")

    # Summary box
    summary_text = format_tutor_prose(resp.summary, fallback="Educational diagnostic explanation.")
    if summary_text:
        st.info(f"**Summary:** {summary_text}")

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("#### 📖 What Happened?")
            what_happened_text = format_tutor_prose(resp.what_happened, fallback="No specific incident reported.")
            st.write(what_happened_text)

            st.markdown("#### 🔍 Verified Diagnostic Evidence")
            evidence_items = format_tutor_text_list(resp.evidence)
            if evidence_items:
                for ev in evidence_items:
                    st.write(f"• {ev}")
            else:
                st.write("No specific factual anomalies logged.")

            st.markdown("#### 💡 What This Means")
            what_this_means_text = format_tutor_prose(resp.what_this_means, fallback="System operating within expected parameters.")
            st.write(what_this_means_text)

    with c2:
        with st.container(border=True):
            st.markdown("#### ❓ Possible Causes")
            causes_items = format_tutor_text_list(resp.possible_causes)
            if causes_items:
                for pc in causes_items:
                    st.write(f"• {pc}")
            else:
                st.write("No specific root cause has been identified from the available evidence.")

            st.markdown("#### 🛡️ Safe Recommendations & Next Steps")
            rec_steps = format_tutor_text_list(resp.recommended_next_steps)
            if rec_steps:
                for step in rec_steps:
                    st.write(f"• {step}")
            else:
                st.write("Continue standard usage.")

            st.markdown("#### 🛠️ Recommended Safe Tools")
            rec_tools = format_tutor_text_list(resp.recommended_tools)
            if rec_tools:
                st.write("You can safely run these diagnostic checks:")
                for tool in rec_tools:
                    tool_desc = format_tutor_tool_description(tool)
                    st.write(f"• {tool_desc}")
            else:
                st.write("No specific tool execution is recommended at this time.")

    # Educational notes & Safety
    with st.container(border=True):
        col_edu, col_saf = st.columns(2)
        with col_edu:
            st.markdown("#### 📚 Educational Notes")
            edu_notes = format_tutor_text_list(
                resp.educational_notes,
                fallback="Personal Tutor Mode provides structured, factual explanations so you understand your system.",
            )
            if len(edu_notes) == 1:
                st.write(edu_notes[0])
            else:
                for note in edu_notes:
                    st.write(f"• {note}")

            verif_items = format_tutor_text_list(resp.verification_explanation)
            if verif_items:
                st.markdown("#### 🔎 Verification Explanation")
                if len(verif_items) == 1:
                    st.write(verif_items[0])
                else:
                    for v_item in verif_items:
                        st.write(f"• {v_item}")

        with col_saf:
            st.markdown("#### ⚠️ Safety & Boundaries")
            safety_notes = format_tutor_text_list(
                resp.safety_notes,
                fallback="WinFix AI performs safe, read-only diagnostic checks without modifying files.",
            )
            if len(safety_notes) == 1:
                st.write(safety_notes[0])
            else:
                for s_note in safety_notes:
                    st.write(f"• {s_note}")

            limitations_items = format_tutor_text_list(resp.limitations)
            if limitations_items:
                st.markdown("#### 🔒 Limitations")
                if len(limitations_items) == 1:
                    st.write(limitations_items[0])
                else:
                    for lim in limitations_items:
                        st.write(f"• {lim}")


def render_step_by_step_tutor_guide(session: TroubleshootingSession) -> None:
    """Render interactive, problem-specific step-by-step guidance answering WHY, FINDINGS, and MEANINGS."""
    st.markdown("---")
    st.markdown(f"### 🧭 Interactive Troubleshooting Guide: *\"{session.problem_statement}\"*")
    st.caption(
        f"Domain: **{session.domain.replace('_', ' ').title()}** | "
        f"Total Steps: **{len(session.steps)}** | "
        f"Session Status: **{session.current_state}**"
    )

    # Action Toolbar
    col_bar1, col_bar2 = st.columns([3, 1])
    with col_bar1:
        if st.button("⚡ Run All Safe Diagnostics Sequentially", key=f"btn_run_all_tutor_{session.session_id}", type="primary"):
            with st.spinner("Executing diagnostic steps and gathering verified empirical findings..."):
                for s in session.steps:
                    if not s.is_repair and s.status != StepStatus.COMPLETED:
                        default_personal_tutor.execute_tutor_step(session, s.step_number)
                st.rerun()
    with col_bar2:
        if st.button("✕ Clear Troubleshooting Flow", key=f"btn_clear_tutor_flow_{session.session_id}"):
            if "active_tutor_session" in st.session_state:
                del st.session_state["active_tutor_session"]
            if "voice_tutor_session" in st.session_state:
                del st.session_state["voice_tutor_session"]
            if "voice_tutor_transcript" in st.session_state:
                del st.session_state["voice_tutor_transcript"]
            st.rerun()

    # Render each step
    for step in session.steps:
        with st.container(border=True):
            status_icons = {
                StepStatus.COMPLETED: "✅ Completed",
                StepStatus.RUNNING: "🔵 Running...",
                StepStatus.AWAITING_CONFIRMATION: "🟠 Requires Your Authorization",
                StepStatus.FAILED: "❌ Failed",
                StepStatus.SKIPPED: "⚪ Skipped",
                StepStatus.PENDING: "⚪ Ready to Check",
            }
            s_icon = status_icons.get(step.status, f"⚪ {step.status}")
            risk_label = "🟢 SAFE (Read-only check)" if step.risk == "SAFE" else "🟠 MEDIUM (Controlled repair)"

            col_h1, col_h2 = st.columns([3, 1])
            with col_h1:
                st.markdown(f"#### Step {step.step_number} of {len(session.steps)}: {step.title}")
                st.caption(f"Tool: `{step.tool_name}` | Risk: **{risk_label}**")
            with col_h2:
                st.markdown(f"**Status:** {s_icon}")

            # 1. WHY are we checking this?
            st.markdown("**Why are we checking this?**")
            st.write(step.why_it_matters)

            # 2. Result & Meaning if completed
            if step.status == StepStatus.COMPLETED:
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    st.markdown("**What we found:**")
                    st.info(step.finding or "Inspection completed successfully.")
                with c_f2:
                    st.markdown("**What this means:**")
                    st.write(step.meaning or "System status verified against baseline parameters.")

                if step.is_repair and step.verification_status:
                    st.success(f"🔍 **Verification Outcome:** {step.verification_status}")

                if step.next_step_hint and step.step_number < len(session.steps):
                    st.caption(f"👉 **Next Step:** {step.next_step_hint}")

                # Raw Output Expandable Drawer for Developers only
                if step.raw_output:
                    with st.expander("🔍 Raw Payload — Developer View", expanded=False):
                        render_json_as_table(step.raw_output, st)

            # 3. Action Buttons if pending or awaiting confirmation
            elif step.status in (StepStatus.PENDING, StepStatus.AWAITING_CONFIRMATION):
                if step.is_repair:
                    st.warning(
                        f"🛡️ **Proposed Repair Action:** `{step.tool_name}`\n\n"
                        f"• **Why:** {step.repair_why or 'Repair identified to restore system component.'}\n"
                        f"• **What will change:** {step.repair_change or 'Will restart or reset target component configuration.'}\n"
                        f"• **Expected effect:** {step.repair_expected_effect or 'Target component state recovers to healthy baseline.'}\n\n"
                        f"**Do you want WinFix AI to perform this repair?**"
                    )
                    c_auth, c_skip = st.columns(2)
                    with c_auth:
                        if st.button(f"✅ Authorize & Apply {step.title}", key=f"auth_step_{step.step_number}_{session.session_id}", type="primary"):
                            with st.spinner(f"Executing {step.title} and verifying outcome..."):
                                default_personal_tutor.execute_tutor_step(session, step.step_number, user_confirmed=True)
                                st.rerun()
                    with c_skip:
                        if st.button(f"✕ Skip This Repair", key=f"skip_step_{step.step_number}_{session.session_id}"):
                            step.status = StepStatus.SKIPPED
                            st.rerun()
                else:
                    if st.button(f"▶ Run Step {step.step_number}: {step.title}", key=f"run_step_btn_{step.step_number}_{session.session_id}", use_container_width=True):
                        with st.spinner(f"Running {step.title}..."):
                            default_personal_tutor.execute_tutor_step(session, step.step_number)
                            st.rerun()


def render_personal_tutor_mode(
    sys_info: Dict[str, Any],
    diag_data: Dict[str, Any],
    ollama_status: Dict[str, Any],
) -> None:
    """Render Personal Tutor Mode interface for interactive learning and explanation."""
    st.markdown("### 🎓 Personal Tutor Mode")
    st.markdown(
        "Welcome to **Personal Tutor Mode**. Here, WinFix AI acts as your educational troubleshooting guide. "
        "Learn what Windows diagnostics detect, understand what technical errors mean, and step through evidence-based troubleshooting plans. "
        "\n\n*Note: Personal Tutor explains and educates — it never automatically modifies your system without explicit authorization.*"
    )

    if not (ollama_status.get("connected") and ollama_status.get("model_available")):
        st.info("ℹ️ **Offline Learning Engine:** Ollama local AI is currently offline or loading. Personal Tutor is operating in high-reliability deterministic educational mode.")

    # Quick Question Chips / Buttons
    st.markdown("#### 💡 Quick Troubleshooting & Learning Topics")
    col1, col2, col3 = st.columns(3)
    quick_question = None
    with col1:
        if st.button("🐢 Why is my PC slow?", use_container_width=True):
            quick_question = "Why is my computer running slowly and what resources should I check?"
        if st.button("🌐 Why is Internet/DNS failing?", use_container_width=True):
            quick_question = "Why is my network connectivity or DNS resolution failing?"
        if st.button("💾 Why is my disk almost full?", use_container_width=True):
            quick_question = "Why is my disk space low and how does WinFix AI handle storage safely?"
    with col2:
        if st.button("💥 Why did my application crash?", use_container_width=True):
            quick_question = "Why did my application crash and what does the faulting module mean?"
        if st.button("🔄 Why is Windows Update failing?", use_container_width=True):
            quick_question = "Why does Windows Update get stuck or fail to download updates?"
        if st.button("🛡️ What is Windows Defender doing?", use_container_width=True):
            quick_question = "How does Windows Defender protect my system and what does service health mean?"
    with col3:
        if st.button("📶 Why is Bluetooth disconnected?", use_container_width=True):
            quick_question = "Why is Bluetooth disconnected or failing to discover devices?"
        if st.button("⚙️ What does a Windows Service do?", use_container_width=True):
            quick_question = "What are Windows Services and why do some services stop?"
        if st.button("🔍 Explain Current Diagnostics", use_container_width=True):
            quick_question = "__EXPLAIN_CURRENT_DIAG__"

    # 2. Problem Input & Multimodal Evidence
    st.markdown("#### 📝 Tutor Question & Multimodal Evidence")

    # Check for forwarded evidence from Screenshot or Voice mode
    if "forwarded_tutor_evidence" in st.session_state:
        f_type, f_data, f_context = st.session_state["forwarded_tutor_evidence"]
        with st.container(border=True):
            st.info(f"📥 **Multimodal Evidence Loaded ({f_type.capitalize()}):** Ready to formulate an interactive step-by-step troubleshooting guide.")
            c_f1, c_f2 = st.columns([3, 1])
            with c_f1:
                if f_type == "screenshot":
                    st.write(f"• **Visual Summary:** {getattr(f_data, 'visible_facts_summary', 'Screenshot evidence loaded')}")
                else:
                    t_text = getattr(getattr(f_data, 'transcript', None), 'sanitized_text', 'Spoken voice input')
                    st.write(f"• **Spoken Input:** \"{t_text}\"")
                if f_context:
                    st.write(f"• **User Notes:** {f_context}")
            with c_f2:
                if st.button("🎓 Start Step-by-Step Guide", key="btn_tutor_from_forwarded", type="primary", use_container_width=True):
                    with st.spinner("Personal Tutor is analyzing evidence and generating a step-by-step troubleshooting guide..."):
                        if f_type == "screenshot":
                            prob_desc = f_context or getattr(f_data, 'visible_facts_summary', 'Screenshot diagnostic inquiry')
                            tutor_resp = default_screenshot_analyzer.explain_screenshot_analysis(
                                analysis=f_data,
                                user_question=f_context,
                            )
                        else:
                            t_text = getattr(getattr(f_data, 'transcript', None), 'sanitized_text', '')
                            prob_desc = t_text if is_valid_transcript(t_text) else (f_context or "Voice diagnostic inquiry")
                            tutor_resp = default_voice_orchestrator.explain_voice_analysis(
                                analysis=f_data,
                                user_question=f_context or prob_desc,
                            )
                        session = default_personal_tutor.create_troubleshooting_flow(
                            user_question=prob_desc,
                            diagnostic_data=diag_data,
                        )
                        st.session_state["last_tutor_response"] = tutor_resp
                        st.session_state["active_tutor_session"] = session
                        st.session_state["active_tutor_question"] = prob_desc
                        del st.session_state["forwarded_tutor_evidence"]
                        st.rerun()

    tutor_tabs = st.tabs(["✍️ Written Description", "📷 Upload Screenshot", "🎤 Spoken Voice Input"])

    with tutor_tabs[0]:
        c_in, c_btn = st.columns([4, 1])
        with c_in:
            custom_q = st.text_input(
                "Ask a question about Windows, an error code, or a symptom:",
                placeholder="e.g. DNS resolution is failing and I cannot connect to web pages.",
                key="tutor_custom_question_input",
                label_visibility="collapsed",
            )
        with c_btn:
            ask_btn = st.button("🎓 Ask Tutor", use_container_width=True, type="primary", key="btn_text_tutor_ask")

        active_question = None
        if quick_question:
            active_question = quick_question
        elif ask_btn and custom_q.strip():
            active_question = custom_q.strip()

        if active_question:
            with st.spinner("Personal Tutor is analyzing diagnostic evidence and formulating an educational lesson..."):
                if active_question == "__EXPLAIN_CURRENT_DIAG__":
                    tutor_resp = default_personal_tutor.explain_diagnostic(
                        diagnostic_data=diag_data,
                        user_question="Explain the current Windows system diagnostic state.",
                    )
                else:
                    tutor_resp = default_personal_tutor.answer_question(
                        user_question=active_question,
                        diagnostic_data=diag_data,
                    )
                session = default_personal_tutor.create_troubleshooting_flow(
                    user_question=active_question if active_question != "__EXPLAIN_CURRENT_DIAG__" else "General Windows Diagnostics Overview",
                    diagnostic_data=diag_data,
                )
                st.session_state["last_tutor_response"] = tutor_resp
                st.session_state["active_tutor_session"] = session
                st.session_state["active_tutor_question"] = active_question
                q_title = "Current Diagnostics Overview" if active_question == "__EXPLAIN_CURRENT_DIAG__" else active_question
                log_session_task(
                    mode="🎓 Personal Tutor",
                    title=f"Q: {q_title[:35]}",
                    summary=getattr(tutor_resp, 'what_happened', 'Explained Windows system concepts'),
                    status="COMPLETED",
                    details={
                        "Severity": getattr(tutor_resp, 'severity', 'NORMAL').value if hasattr(getattr(tutor_resp, 'severity', None), 'value') else str(getattr(tutor_resp, 'severity', 'NORMAL')),
                    },
                )
                st.rerun()

    with tutor_tabs[1]:
        tutor_screenshot = st.file_uploader(
            "Upload Windows screenshot for Tutor analysis (PNG, JPEG, WEBP):",
            type=["png", "jpg", "jpeg", "webp"],
            key="tutor_screenshot_uploader",
        )
        tutor_screen_context = st.text_input(
            "Optional context about this screen:",
            placeholder="e.g., Wi-Fi keeps disconnecting",
            key="tutor_screen_ctx",
        )
        if tutor_screenshot is not None:
            if st.button("🔍 Analyze Screenshot & Explain", key="btn_tutor_screen_explain", type="primary"):
                with st.spinner("Analyzing screenshot and generating educational lesson with Personal Tutor..."):
                    img_bytes = tutor_screenshot.getvalue()
                    analysis = default_screenshot_analyzer.analyze_screenshot(
                        image_bytes=img_bytes,
                        filename=tutor_screenshot.name,
                        user_question=tutor_screen_context,
                        session_id=f"tutor_screen_{int(time.time())}",
                    )
                    tutor_resp = default_screenshot_analyzer.explain_screenshot_analysis(
                        analysis=analysis,
                        user_question=tutor_screen_context,
                        session_id=f"tutor_screen_exp_{int(time.time())}",
                    )
                    prob_desc = tutor_screen_context or analysis.visible_facts_summary
                    session = default_personal_tutor.create_troubleshooting_flow(
                        user_question=prob_desc,
                        diagnostic_data=diag_data,
                    )
                    st.session_state["last_tutor_response"] = tutor_resp
                    st.session_state["active_tutor_session"] = session
                    st.session_state["active_tutor_question"] = prob_desc
                    log_session_task(
                        mode="🎓 Personal Tutor",
                        title=f"Screenshot: {tutor_screenshot.name}",
                        summary=getattr(tutor_resp, 'summary', analysis.visible_facts_summary),
                        status="COMPLETED",
                    )
                    st.rerun()

    with tutor_tabs[2]:
        col_v1, col_v2 = st.columns([1, 1])
        tutor_voice_file = None

        with col_v1:
            st.markdown("#### 📁 Upload Audio File")
            upload_tutor_voice = st.file_uploader(
                "Upload voice recording for Tutor (WAV, MP3, OGG, FLAC, M4A, WEBM):",
                type=["wav", "mp3", "ogg", "flac", "m4a", "webm"],
                key="tutor_voice_uploader",
            )
            if upload_tutor_voice is not None:
                tutor_voice_file = upload_tutor_voice

        with col_v2:
            st.markdown("#### 🎙️ Microphone Recording")
            if hasattr(st, "audio_input"):
                mic_audio = st.audio_input("Record voice problem directly:", key="tutor_voice_mic_recorder")
                if mic_audio is not None:
                    tutor_voice_file = mic_audio
            else:
                st.info("Browser microphone capture: Use file uploader to submit local audio recordings.")

        if tutor_voice_file is not None:
            audio_bytes = tutor_voice_file.getvalue()
            st.audio(audio_bytes, format=getattr(tutor_voice_file, "type", "audio/wav"))

            btn_col1, btn_col2 = st.columns([1, 1])
            with btn_col1:
                if st.button("🎤 Transcribe Audio", key="btn_tutor_voice_transcribe", type="primary"):
                    with st.spinner("Transcribing audio locally with faster-whisper..."):
                        fname = getattr(tutor_voice_file, "name", "microphone_input.wav") or "microphone_input.wav"
                        v_analysis = default_voice_orchestrator.process_voice_input(
                            audio_bytes=audio_bytes,
                            filename=fname,
                            session_id=f"tutor_voice_{int(time.time())}",
                        )
                        st.session_state["tutor_voice_analysis"] = v_analysis
                        st.session_state["tutor_voice_fname"] = fname
                        st.rerun()
            with btn_col2:
                if "tutor_voice_analysis" in st.session_state:
                    if st.button("✕ Clear Audio & Transcript", key="btn_tutor_voice_clear"):
                        del st.session_state["tutor_voice_analysis"]
                        st.rerun()

        # Display Transcription Results / Quality Gate
        if "tutor_voice_analysis" in st.session_state:
            v_analysis: VoiceAnalysis = st.session_state["tutor_voice_analysis"]
            st.markdown("---")

            if v_analysis.status == VoiceStatus.COMPLETED and is_valid_transcript(v_analysis.transcript.sanitized_text):
                st.markdown("#### 🎙️ What I heard")
                st.caption(f"Model: `{v_analysis.transcript.model_used}` | Duration: `{v_analysis.transcript.duration_seconds}s` | Language Confidence: `{v_analysis.transcript.confidence:.2f}`")

                edited_transcript = st.text_area(
                    "Review / Edit Transcribed Problem (Primary User Problem):",
                    value=v_analysis.transcript.sanitized_text,
                    key="tutor_voice_transcript_edit",
                    height=90,
                )

                tutor_voice_context = st.text_input(
                    "Optional Additional Context / Notes:",
                    placeholder="e.g., It started after yesterday's update.",
                    key="tutor_voice_ctx",
                )

                if st.button("🎓 Formulate Personal Tutor Troubleshooting Guide", key="btn_tutor_voice_explain", type="primary"):
                    with st.spinner("Personal Tutor is analyzing evidence and formulating your step-by-step troubleshooting guide..."):
                        prob_desc = edited_transcript.strip() if is_valid_transcript(edited_transcript) else v_analysis.transcript.sanitized_text
                        fname = st.session_state.get("tutor_voice_fname", "microphone_input.wav")
                        
                        v_analysis.transcript.sanitized_text = prob_desc
                        v_analysis.transcript.text = prob_desc

                        tutor_resp = default_voice_orchestrator.explain_voice_analysis(
                            analysis=v_analysis,
                            user_question=tutor_voice_context or prob_desc,
                        )
                        
                        full_problem_query = f"{prob_desc} ({tutor_voice_context})" if tutor_voice_context else prob_desc
                        session = default_personal_tutor.create_troubleshooting_flow(
                            user_question=full_problem_query,
                            diagnostic_data=diag_data,
                        )
                        st.session_state["last_tutor_response"] = tutor_resp
                        st.session_state["active_tutor_session"] = session
                        st.session_state["active_tutor_question"] = prob_desc
                        log_session_task(
                            mode="🎓 Personal Tutor",
                            title=f"Voice: {fname}",
                            summary=getattr(tutor_resp, 'summary', f"Voice: {prob_desc}"),
                            status="COMPLETED",
                        )
                        st.rerun()

            elif v_analysis.status == VoiceStatus.TRANSCRIPTION_UNAVAILABLE:
                st.warning(
                    "⚠️ **Speech-to-Text Model Unavailable:** WinFix AI received your audio, but the local "
                    "speech-to-text model (`faster-whisper`) is not ready.\n\n"
                    "**Next Steps:** You can type your problem directly in the **✍️ Written Description** tab."
                )
            else:
                st.error("⚠️ **Speech Not Understood:** Your recording was received, but WinFix AI couldn't understand any spoken speech.")
                st.info("💡 **What to do:** Speak clearly into your microphone, upload a clean WAV/WebM audio file, or type your problem description directly.")

    # Display Step-by-Step Interactive Troubleshooting Guide
    if "active_tutor_session" in st.session_state:
        render_step_by_step_tutor_guide(st.session_state["active_tutor_session"])

    # Display Last Tutor Response Card
    if "last_tutor_response" in st.session_state:
        st.markdown("---")
        with st.expander("🎓 View Deep Educational Explanation & Safety Notes", expanded=True):
            render_tutor_response_card(st.session_state["last_tutor_response"])

    # Recent Repair Explanation option if available
    if "last_repair_result" in st.session_state:
        last_rep = st.session_state["last_repair_result"]
        st.markdown("---")
        st.markdown("#### 🔧 Recent Repair Explanation")
        st.write(f"Last executed action: `{getattr(last_rep, 'tool_name', 'Unknown')}` — Verification: `{getattr(last_rep, 'verification_status', 'Unknown')}`")
        if st.button("📖 Explain This Repair Result", key="explain_last_repair_btn"):
            with st.spinner("Personal Tutor is generating an educational explanation of the repair result..."):
                rep_tutor_resp = default_personal_tutor.explain_repair(
                    tool_name=getattr(last_rep, "tool_name", ""),
                    repair_output=getattr(last_rep, "repair_output", {}),
                    verification_status=getattr(last_rep, "verification_status", "not_verified"),
                    before_state=getattr(last_rep, "before_state", {}),
                    after_state=getattr(last_rep, "after_state", {}),
                )
                st.session_state["last_tutor_response"] = rep_tutor_resp
                log_session_task(
                    mode="🎓 Personal Tutor",
                    title=f"Explain: {getattr(last_rep, 'tool_name', 'Repair')}",
                    summary=getattr(rep_tutor_resp, 'what_happened', 'Explained repair result and verification'),
                    status="COMPLETED",
                )
                st.rerun()


def render_autopilot_mode(
    sys_info: Dict[str, Any],
    diag_data: Dict[str, Any],
    ollama_status: Dict[str, Any],
) -> None:
    """Render Autopilot Mode interface for bounded, verified multi-step repair workflows."""
    st.markdown("### 🤖 Autopilot Mode")
    st.markdown(
        "Autopilot formulates a **bounded, sequential troubleshooting plan** (up to 5 steps) to resolve your Windows issue. "
        "\n\n*Safety Model: Every proposed tool is validated against the Safety Engine. You must authorize the plan before any repair executes. "
        "Every repair is verified immediately, and Autopilot stops instantly if an unexpected state occurs.*"
    )

    if not (ollama_status.get("connected") and ollama_status.get("model_available")):
        st.info("ℹ️ **Offline Execution Engine:** Ollama local AI is offline or loading. Autopilot is utilizing high-reliability deterministic allowlisted troubleshooting workflows.")

    # 1. Quick Topic Buttons
    st.markdown("#### 💡 Quick Autopilot Workflows")
    col1, col2, col3 = st.columns(3)
    quick_problem = None
    with col1:
        if st.button("🌐 Fix DNS / Connectivity Issues", use_container_width=True):
            quick_problem = "My internet is not working and DNS resolution is failing."
        if st.button("💾 Clean Temporary Cache", use_container_width=True):
            quick_problem = "My disk is full and temporary storage needs cleanup."
    with col2:
        if st.button("🔄 Resolve Windows Update Stalls", use_container_width=True):
            quick_problem = "Windows Update service is stuck or failing to install updates."
        if st.button("🛡️ Repair Windows Defender Service", use_container_width=True):
            quick_problem = "Windows Defender service is stopped or not running."
    with col3:
        if st.button("📶 Restore Bluetooth Service", use_container_width=True):
            quick_problem = "Bluetooth is disconnected and service needs to be restored."
        if st.button("⚡ General Performance Diagnostics", use_container_width=True):
            quick_problem = "Diagnose high CPU, memory, and slow process usage."

    # 2. Problem Input & Multimodal Evidence
    st.markdown("#### 📝 Autopilot Problem Input & Multimodal Evidence")

    # Check for forwarded evidence from Screenshot or Voice mode
    if "forwarded_multimodal_evidence" in st.session_state:
        f_type, f_data, f_context = st.session_state["forwarded_multimodal_evidence"]
        with st.container(border=True):
            st.info(f"📥 **Multimodal Evidence Loaded ({f_type.capitalize()}):** Ready to formulate an Autopilot troubleshooting plan.")
            c_f1, c_f2 = st.columns([3, 1])
            with c_f1:
                if f_type == "screenshot":
                    st.write(f"• **Visual Summary:** {getattr(f_data, 'visible_facts_summary', 'Screenshot evidence loaded')}")
                else:
                    t_text = getattr(getattr(f_data, 'transcript', None), 'sanitized_text', 'Spoken voice input')
                    st.write(f"• **Spoken Input:** \"{t_text}\"")
                if f_context:
                    st.write(f"• **User Notes:** {f_context}")
            with c_f2:
                if st.button("📋 Formulate Plan from Evidence", key="btn_formulate_from_forwarded", type="primary", use_container_width=True):
                    with st.spinner("Autopilot is formulating a plan from multimodal evidence..."):
                        session_id = f"auto_multi_{int(time.time())}"
                        try:
                            if f_type == "screenshot":
                                plan = default_autopilot_engine.plan_from_multimodal(
                                    screenshot_analysis=f_data,
                                    user_text=f_context,
                                    diagnostic_data=diag_data,
                                    system_info=sys_info,
                                    session_id=session_id,
                                )
                            else:
                                plan = default_autopilot_engine.plan_from_multimodal(
                                    voice_analysis=f_data,
                                    user_text=f_context,
                                    diagnostic_data=diag_data,
                                    system_info=sys_info,
                                    session_id=session_id,
                                )
                            st.session_state["active_autopilot_plan"] = plan
                            st.session_state["active_autopilot_problem"] = plan.goal
                            del st.session_state["forwarded_multimodal_evidence"]
                            if "last_autopilot_result" in st.session_state:
                                del st.session_state["last_autopilot_result"]
                            st.rerun()
                        except Exception as ex:
                            st.error(f"✕ Failed to formulate plan: {ex}")

    auto_tabs = st.tabs(["✍️ Written Description", "📷 Upload Screenshot", "🎤 Spoken Voice Input"])

    with auto_tabs[0]:
        c_in, c_btn = st.columns([4, 1])
        with c_in:
            custom_problem = st.text_input(
                "Describe the Windows issue you want Autopilot to resolve:",
                placeholder="e.g. DNS resolution is failing and I cannot connect to web pages.",
                key="autopilot_problem_input",
                label_visibility="collapsed",
            )
        with c_btn:
            plan_btn = st.button("📋 Formulate Plan", use_container_width=True, type="primary", key="btn_text_autopilot_plan")

        active_problem = None
        if quick_problem:
            active_problem = quick_problem
        elif plan_btn and custom_problem.strip():
            active_problem = custom_problem.strip()

        if active_problem:
            with st.spinner("Autopilot is analyzing diagnostics and formulating a bounded, safe repair plan..."):
                session_id = f"auto_sess_{int(time.time())}"
                try:
                    plan = default_autopilot_engine.plan(
                        problem_description=active_problem,
                        diagnostic_data=diag_data,
                        system_info=sys_info,
                        session_id=session_id,
                    )
                    st.session_state["active_autopilot_plan"] = plan
                    st.session_state["active_autopilot_problem"] = active_problem
                    if "last_autopilot_result" in st.session_state:
                        del st.session_state["last_autopilot_result"]
                except Exception as ex:
                    st.error(f"✕ Failed to formulate plan: {ex}")

    with auto_tabs[1]:
        auto_screenshot = st.file_uploader(
            "Upload Windows screenshot for Autopilot analysis (PNG, JPEG, WEBP):",
            type=["png", "jpg", "jpeg", "webp"],
            key="auto_screenshot_uploader",
        )
        auto_screen_context = st.text_input("Optional context about this screen:", placeholder="e.g., Wi-Fi keeps disconnecting", key="auto_screen_ctx")
        if auto_screenshot is not None:
            if st.button("🔍 Analyze Screenshot & Formulate Autopilot Plan", key="btn_auto_screen_plan", type="primary"):
                with st.spinner("Analyzing screenshot and formulating bounded Autopilot plan..."):
                    img_bytes = auto_screenshot.getvalue()
                    analysis = default_screenshot_analyzer.analyze_screenshot(
                        image_bytes=img_bytes,
                        filename=auto_screenshot.name,
                        user_question=auto_screen_context,
                        session_id=f"auto_screen_{int(time.time())}",
                    )
                    plan = default_autopilot_engine.plan_from_multimodal(
                        screenshot_analysis=analysis,
                        user_text=auto_screen_context,
                        diagnostic_data=diag_data,
                        system_info=sys_info,
                    )
                    st.session_state["active_autopilot_plan"] = plan
                    st.session_state["active_autopilot_problem"] = plan.goal
                    if "last_autopilot_result" in st.session_state:
                        del st.session_state["last_autopilot_result"]
                    st.rerun()

    with auto_tabs[2]:
        col_v1, col_v2 = st.columns([1, 1])
        auto_voice_file = None

        with col_v1:
            st.markdown("#### 📁 Upload Audio File")
            upload_mic_file = st.file_uploader(
                "Upload voice recording for Autopilot (WAV, MP3, OGG, FLAC, M4A, WEBM):",
                type=["wav", "mp3", "ogg", "flac", "m4a", "webm"],
                key="auto_voice_uploader",
            )
            if upload_mic_file is not None:
                auto_voice_file = upload_mic_file

        with col_v2:
            st.markdown("#### 🎙️ Microphone Recording")
            if hasattr(st, "audio_input"):
                mic_audio = st.audio_input("Record voice problem directly:", key="auto_voice_mic_recorder")
                if mic_audio is not None:
                    auto_voice_file = mic_audio
            else:
                st.info("Browser microphone capture: Use file uploader to submit local audio recordings.")

        if auto_voice_file is not None:
            audio_bytes = auto_voice_file.getvalue()
            st.audio(audio_bytes, format=getattr(auto_voice_file, "type", "audio/wav"))

            btn_col1, btn_col2 = st.columns([1, 1])
            with btn_col1:
                if st.button("🎤 Transcribe Audio", key="btn_auto_voice_transcribe", type="primary"):
                    with st.spinner("Transcribing audio locally with faster-whisper..."):
                        fname = getattr(auto_voice_file, "name", "microphone_input.wav") or "microphone_input.wav"
                        analysis = default_voice_orchestrator.process_voice_input(
                            audio_bytes=audio_bytes,
                            filename=fname,
                            session_id=f"auto_voice_{int(time.time())}",
                        )
                        st.session_state["auto_voice_analysis"] = analysis
                        st.session_state["auto_voice_fname"] = fname
                        st.rerun()
            with btn_col2:
                if "auto_voice_analysis" in st.session_state:
                    if st.button("✕ Clear Audio & Transcript", key="btn_auto_voice_clear"):
                        del st.session_state["auto_voice_analysis"]
                        st.rerun()

        # Display Transcription Results / Quality Gate
        if "auto_voice_analysis" in st.session_state:
            analysis: VoiceAnalysis = st.session_state["auto_voice_analysis"]
            st.markdown("---")

            if analysis.status == VoiceStatus.COMPLETED and is_valid_transcript(analysis.transcript.sanitized_text):
                st.markdown("#### 🎙️ What I heard")
                st.caption(f"Model: `{analysis.transcript.model_used}` | Duration: `{analysis.transcript.duration_seconds}s` | Language Confidence: `{analysis.transcript.confidence:.2f}`")

                edited_transcript = st.text_area(
                    "Review / Edit Transcribed Problem (Primary User Problem):",
                    value=analysis.transcript.sanitized_text,
                    key="auto_voice_transcript_edit",
                    height=90,
                )

                auto_voice_context = st.text_input(
                    "Optional Additional Context / Notes:",
                    placeholder="e.g., It started after yesterday's update.",
                    key="auto_voice_ctx",
                )

                if st.button("🤖 Formulate Autopilot Plan", key="btn_auto_voice_plan", type="primary"):
                    with st.spinner("Formulating bounded Autopilot plan from verified voice transcript..."):
                        prob_desc = edited_transcript.strip() if is_valid_transcript(edited_transcript) else analysis.transcript.sanitized_text
                        fname = st.session_state.get("auto_voice_fname", "microphone_input.wav")
                        
                        analysis.transcript.sanitized_text = prob_desc
                        analysis.transcript.text = prob_desc

                        plan = default_autopilot_engine.plan_from_multimodal(
                            voice_analysis=analysis,
                            user_text=auto_voice_context,
                            diagnostic_data=diag_data,
                            system_info=sys_info,
                        )
                        st.session_state["active_autopilot_plan"] = plan
                        st.session_state["active_autopilot_problem"] = plan.goal
                        if "last_autopilot_result" in st.session_state:
                            del st.session_state["last_autopilot_result"]
                        st.rerun()

            elif analysis.status == VoiceStatus.TRANSCRIPTION_UNAVAILABLE:
                st.warning(
                    "⚠️ **Speech-to-Text Model Unavailable:** WinFix AI received your audio, but the local "
                    "speech-to-text model (`faster-whisper`) is not ready.\n\n"
                    "**Next Steps:** You can describe your problem directly in the **✍️ Written Description** tab."
                )
            else:
                st.error("⚠️ **Speech Not Understood:** Your recording was received, but WinFix AI couldn't understand any spoken speech.")
                st.info("💡 **What to do:** Speak clearly into your microphone, upload a clean WAV/WebM audio file, or type your problem description directly.")

    # 3. Display Proposed Plan & Authorization Box
    if "active_autopilot_plan" in st.session_state and "last_autopilot_result" not in st.session_state:
        plan: AutopilotPlan = st.session_state["active_autopilot_plan"]
        st.markdown("---")
        st.markdown(f"### 📋 Proposed Plan: {plan.goal}")
        st.caption(f"Plan ID: `{plan.plan_id}` | SHA-256 Hash: `{plan.plan_hash[:16]}...` | Total Operations: **{len(plan.steps)}** (Max: 5)")

        for step in plan.steps:
            with st.container(border=True):
                r_badge = "🟢 SAFE" if step.risk_level == "SAFE" else "🟠 MEDIUM (Requires Authorization)"
                st.markdown(f"**Step {step.sequence}:** `{step.tool_name}` — Risk: **{r_badge}**")
                st.write(f"• **Purpose:** {step.purpose}")
                st.write(f"• **Expected Result:** {step.expected_result}")
                if step.requires_admin:
                    st.caption("🔒 Requires Administrator Privileges")
                if step.verification_required:
                    st.caption("🔍 Automatic verification will be performed immediately after this step.")

        # Authorization Box
        with st.container(border=True):
            st.markdown("#### 🛡️ User Authorization Required")
            st.warning(
                "Authorizing this plan will sequentially execute only the validated tools listed above. "
                "Autopilot will verify every step and stop automatically on any error or verification failure."
            )
            col_a, col_b = st.columns([2, 1])
            with col_a:
                auth_btn = st.button("🛡 Authorize & Run Autopilot Plan", type="primary", use_container_width=True, key="auth_autopilot_btn")
            with col_b:
                cancel_btn = st.button("✕ Discard Plan", use_container_width=True, key="cancel_autopilot_btn")

            if cancel_btn:
                del st.session_state["active_autopilot_plan"]
                st.info("Plan discarded.")
                st.rerun()

            if auth_btn:
                with st.spinner("Authorizing plan and sequentially executing verified steps..."):
                    # 1. Authorize
                    authorized = default_autopilot_engine.authorize_plan(plan, user_confirmed_hash=plan.plan_hash)
                    if not authorized:
                        st.error("✕ Authorization failed: Plan hash mismatch or plan has already been executed.")
                    else:
                        # 2. Execute
                        res = default_autopilot_engine.execute_plan(plan, user_confirmed_hash=plan.plan_hash)
                        st.session_state["last_autopilot_result"] = res
                        log_session_task(
                            mode="🤖 Autopilot Executed",
                            title=f"Autopilot: {plan.goal[:35]}",
                            summary=res.summary,
                            status=res.status.value if hasattr(res.status, 'value') else str(res.status),
                            details={
                                "Steps Executed": f"{res.steps_executed} of {len(plan.steps)}",
                                "Duration": f"{getattr(res, 'duration_seconds', 0.0):.2f}s",
                            },
                        )
                        st.rerun()

    # 4. Display Execution Outcome & Personal Tutor Breakdown
    if "last_autopilot_result" in st.session_state:
        res: AutopilotResult = st.session_state["last_autopilot_result"]
        st.markdown("---")
        st.markdown("### 📊 Autopilot Execution Results")

        st_badges = {
            AutopilotStatus.COMPLETED: "🟢 COMPLETED",
            AutopilotStatus.PARTIAL: "🟡 PARTIAL",
            AutopilotStatus.VERIFICATION_FAILED: "🟠 VERIFICATION FAILED",
            AutopilotStatus.VERIFICATION_TIMEOUT: "🟠 VERIFICATION TIMEOUT",
            AutopilotStatus.FAILED: "🔴 FAILED",
            AutopilotStatus.CANCELLED: "🔵 CANCELLED",
            AutopilotStatus.STOPPED: "🟡 STOPPED",
            AutopilotStatus.BLOCKED: "🔴 BLOCKED",
        }
        st_badge = st_badges.get(res.status, f"⚪ {res.status.value}")

        st.info(f"**Outcome:** {st_badge} — {res.summary}")

        st.markdown(f"#### 🔍 Detailed Step Execution Results ({res.steps_executed} steps executed)")
        for sr in res.step_results:
            icon = "✅" if sr.status in ["SUCCESS", "VERIFIED"] else "❌"
            with st.container(border=True):
                st.markdown(f"##### {icon} Step {sr.sequence}: `{sr.tool_name}` — Status: `{sr.status}` ({sr.duration_ms} ms)")
                st.write(f"• **Explanation:** {sr.explanation}")
                if sr.verification_status:
                    st.write(f"• **Verification Status:** `{sr.verification_status}`")
                
                # Check for key metrics in repair/diagnostic output
                if isinstance(sr.output, dict):
                    data_payload = sr.output.get("data", sr.output)
                    if isinstance(data_payload, dict):
                        m_cols = []
                        if "bytes_freed_formatted" in data_payload:
                            m_cols.append(("Storage Freed", data_payload["bytes_freed_formatted"]))
                        elif "freed_mb" in data_payload:
                            m_cols.append(("Storage Freed", f"{data_payload['freed_mb']} MB"))
                        if "removed_count" in data_payload:
                            m_cols.append(("Files Cleaned", f"{data_payload['removed_count']} files"))
                        if "scanned_count" in data_payload:
                            m_cols.append(("Files Scanned", f"{data_payload['scanned_count']} files"))
                        
                        if m_cols:
                            c_list = st.columns(len(m_cols))
                            for idx, (label, val) in enumerate(m_cols):
                                with c_list[idx]:
                                    st.metric(label, val)

                if sr.output:
                    with st.expander("📊 View Detailed Output Table", expanded=True):
                        render_json_as_table(sr.output, st)

        # Personal Tutor Explanation of Autopilot Outcome
        st.markdown("#### 🎓 Personal Tutor Breakdown of Autopilot Run")
        tutor_exp = default_autopilot_engine.explain_result(res)
        render_tutor_response_card(tutor_exp)

        if st.button("🔄 Start New Autopilot Session", use_container_width=True):
            if "active_autopilot_plan" in st.session_state:
                del st.session_state["active_autopilot_plan"]
            if "last_autopilot_result" in st.session_state:
                del st.session_state["last_autopilot_result"]
            st.rerun()


def render_screenshot_diagnostics_mode(
    sys_info: Dict[str, Any],
    diag_data: Dict[str, Any],
    ollama_status: Dict[str, Any],
) -> None:
    """Render Phase 17 Screenshot Diagnostics interface with vision analysis and tool mapping."""
    st.markdown("### 📷 Screenshot Diagnostics")
    st.markdown(
        """
Upload a Windows screenshot of an error dialog, crash alert, setting screen, or unexpected behavior.
WinFix AI will extract visible facts, error codes, and map them to **safe read-only diagnostic tools**.
"""
    )

    # Privacy Warning Notice
    st.warning(
        "🔒 **Privacy Notice**: Screenshots may contain personal file paths, account usernames, browser tabs, or sensitive notifications. "
        "Review your image before analysis. WinFix AI executes vision analysis locally and offline without external cloud transmission."
    )

    uploaded_file = st.file_uploader(
        "Upload Windows Screenshot (PNG, JPEG, WEBP — Max 10 MB):",
        type=["png", "jpg", "jpeg", "webp"],
        key="screenshot_uploader",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        col_img, col_meta = st.columns([3, 2])

        with col_img:
            st.image(uploaded_file, caption=f"Uploaded Screenshot: {uploaded_file.name}", use_container_width=True)

        with col_meta:
            st.markdown("#### 📄 Image Properties")
            st.write(f"• **Filename:** `{uploaded_file.name}`")
            st.write(f"• **File Size:** `{len(file_bytes) / 1024:.1f} KB` ({len(file_bytes)} bytes)")
            st.write(f"• **MIME / Type:** `{uploaded_file.type}`")

            user_question = st.text_input(
                "Optional inquiry or context about this screen:",
                placeholder="e.g., What does error 0x80070422 mean and how can I inspect it?",
                key="screenshot_user_query",
            )

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                analyze_btn = st.button("🔍 Analyze Screenshot", type="primary", use_container_width=True, key="btn_analyze_screenshot")
            with col_btn2:
                clear_btn = st.button("✕ Clear Results", use_container_width=True, key="btn_clear_screenshot")

            if clear_btn:
                if "active_screenshot_analysis" in st.session_state:
                    del st.session_state["active_screenshot_analysis"]
                st.rerun()

        if analyze_btn:
            with st.spinner("Analyzing visible screenshot evidence with local AI vision engine..."):
                analysis: ScreenshotAnalysis = default_screenshot_analyzer.analyze_screenshot(
                    image_bytes=file_bytes,
                    filename=uploaded_file.name,
                    user_question=user_question,
                    session_id="screenshot_active_session",
                )
                st.session_state["active_screenshot_analysis"] = analysis
                log_session_task(
                    mode="📷 Screenshot Diagnostics",
                    title=f"Screenshot: {uploaded_file.name}",
                    summary=analysis.visible_facts_summary,
                    status=str(analysis.status.value if hasattr(analysis.status, 'value') else analysis.status),
                    details={
                        "Error Codes": ", ".join(analysis.evidence.detected_error_codes) or "None detected",
                        "Applications": ", ".join(analysis.evidence.detected_applications) or "None detected",
                        "Recommended Step": analysis.recommended_next_step or "Inspect diagnostic state",
                    },
                )
                st.rerun()

    # Display Analysis Outcome if present
    if "active_screenshot_analysis" in st.session_state:
        analysis: ScreenshotAnalysis = st.session_state["active_screenshot_analysis"]
        st.markdown("---")
        st.markdown("### 📊 Screenshot Evidence & Diagnostic Assessment")

        # Multimodal Assessment Banner (ChatGPT / Claude Style)
        status_val = str(analysis.status).upper()
        if status_val in ["SUCCESS", "VISION_SUCCESS"]:
            st.success(f"🟢 **Visual Analysis Complete:** {analysis.visible_facts_summary} ({analysis.analysis_duration_ms} ms)")
        else:
            st.success(f"🟢 **Visual & Contextual Analysis:** {analysis.visible_facts_summary}")
            st.caption("🔒 Analyzed locally using WinFix AI offline diagnostic engine.")

        # 1. Observed Evidence & Findings
        st.markdown("#### 🔍 Observed Evidence & Detected Elements")
        st.info(f"**Visual Findings:** {analysis.visible_facts_summary}")

        # Show detected markers
        if analysis.evidence.detected_error_codes or analysis.evidence.detected_event_ids or analysis.evidence.detected_applications:
            ec_cols = st.columns(3)
            with ec_cols[0]:
                st.markdown("**Detected Error Codes:**")
                if analysis.evidence.detected_error_codes:
                    for ec in analysis.evidence.detected_error_codes:
                        st.code(ec, language="text")
                else:
                    st.caption("None detected")

            with ec_cols[1]:
                st.markdown("**Detected Event IDs:**")
                if analysis.evidence.detected_event_ids:
                    for eid in analysis.evidence.detected_event_ids:
                        st.code(f"Event ID {eid}", language="text")
                else:
                    st.caption("None detected")

            with ec_cols[2]:
                st.markdown("**Detected Applications / Subsystems:**")
                if analysis.evidence.detected_applications:
                    for app in analysis.evidence.detected_applications:
                        st.markdown(f"• `{app}`")
                else:
                    st.caption("None detected")

        # 2. Personal Tutor Solution Guide (ChatGPT/Claude Style Direct Breakdown)
        st.markdown("---")
        st.markdown("#### 💡 AI Diagnosis & Step-by-Step Solution")
        tutor_resp = default_screenshot_analyzer.explain_screenshot_analysis(analysis, user_question=user_question)
        render_tutor_response_card(tutor_resp)

        # 3. Detailed visual observations & evidence if present
        if analysis.evidence.observations:
            with st.expander(f"🔍 Detailed Visual Observations ({len(analysis.evidence.observations)} elements)"):
                for obs in analysis.evidence.observations:
                    loc_str = f" [{obs.location}]" if obs.location else ""
                    st.write(f"• **`{obs.category}`**{loc_str}: {obs.text} *(Confidence: {obs.confidence:.2f})*")

        # 4. What We Cannot Confirm & Hypotheses
        col_uncert, col_hypo = st.columns(2)
        with col_uncert:
            st.markdown("#### ⚠️ What We Cannot Confirm")
            with st.container(border=True):
                if analysis.uncertainties:
                    for item in analysis.uncertainties:
                        st.markdown(f"• {item}")
                else:
                    st.markdown("• Visual state is historical and does not verify current background process conditions.")

        with col_hypo:
            st.markdown("#### 🔍 Possible Interpretations")
            with st.container(border=True):
                if analysis.possible_interpretations:
                    for item in analysis.possible_interpretations:
                        st.markdown(f"• {item}")
                else:
                    st.markdown("• No specific visual interpretation generated.")

        # 5. Recommended Next Step & Read-Only Diagnostics
        st.markdown("---")
        st.markdown("#### 🛠️ Recommended Next Step & Direct Diagnostics")
        st.write(f"**Action:** {analysis.recommended_next_step}")
        st.caption("WinFix AI connects visual evidence to safe, read-only diagnostic tools. Run these checks to verify active system state:")

        if analysis.diagnostic_hints:
            for hint in analysis.diagnostic_hints:
                with st.container():
                    h_col1, h_col2 = st.columns([3, 1])
                    with h_col1:
                        st.markdown(f"**`{hint.tool_name}`** — *{hint.evidence_reason}*")
                        st.caption(f"Purpose: {hint.purpose} | Risk Level: `{hint.risk_level}`")
                    with h_col2:
                        if st.button(f"▶ Run {hint.tool_name}", key=f"run_hint_{hint.tool_name}", use_container_width=True):
                            tool = default_tool_registry.get_tool(hint.tool_name)
                            if tool:
                                res = tool.handler(**hint.arguments)
                                st.session_state[f"hint_result_{hint.tool_name}"] = res
                    if f"hint_result_{hint.tool_name}" in st.session_state:
                        with st.expander(f"Diagnostic Output: {hint.tool_name}", expanded=True):
                            render_structured_diagnostic_card(hint.tool_name, st.session_state[f"hint_result_{hint.tool_name}"])
                    st.divider()
        else:
            st.info("No domain-specific diagnostic hints found. Consider standard baseline system info.")

        # 6. Interactive Multi-turn Chat About This Screenshot (ChatGPT / Claude Style)
        st.markdown("---")
        st.markdown("#### 💬 Chat with WinFix AI About This Screenshot")
        st.caption("Ask questions or discuss solutions regarding this screen like you would in ChatGPT or Claude:")

        if "screenshot_chat_messages" not in st.session_state:
            st.session_state["screenshot_chat_messages"] = []

        # Render chat history
        for msg in st.session_state["screenshot_chat_messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        follow_up_input = st.chat_input("Ask a question about this screen (e.g. 'How do I restart the Bluetooth service?' or 'What should I do first?')...")
        if follow_up_input and follow_up_input.strip():
            # Add user message
            st.session_state["screenshot_chat_messages"].append({"role": "user", "content": follow_up_input})
            with st.chat_message("user"):
                st.markdown(follow_up_input)

            # Generate assistant response
            with st.chat_message("assistant"):
                with st.spinner("WinFix AI is analyzing..."):
                    fu_resp = default_personal_tutor.answer_question(
                        user_question=f"Regarding the uploaded screenshot ({analysis.visible_facts_summary}): {follow_up_input.strip()}",
                        session_id="screenshot_active_session",
                        diagnostic_data={
                            "screenshot_evidence": {
                                "visible_facts": analysis.visible_facts_summary,
                                "error_codes": analysis.evidence.detected_error_codes,
                                "applications": analysis.evidence.detected_applications,
                            }
                        }
                    )
                    ans_parts = []
                    if getattr(fu_resp, "what_happened", None):
                        ans_parts.append(fu_resp.what_happened)
                    if getattr(fu_resp, "what_this_means", None):
                        ans_parts.append(f"**Explanation:** {fu_resp.what_this_means}")
                    if getattr(fu_resp, "recommended_next_steps", None):
                        ans_parts.append("**Recommended Next Steps:**\n" + "\n".join(f"• {step}" for step in fu_resp.recommended_next_steps))
                    ans_text = "\n\n".join(ans_parts) or str(getattr(fu_resp, "summary", "I have reviewed your inquiry against the screenshot evidence."))
                    st.markdown(ans_text)
                    st.session_state["screenshot_chat_messages"].append({"role": "assistant", "content": ans_text})

            log_session_task(
                mode="📷 Screenshot Q&A",
                title=f"Q: {follow_up_input[:35]}",
                summary=ans_text[:80],
                status="COMPLETED",
            )

        # 7. Operating Mode Actions
        st.markdown("---")
        st.markdown("#### 🚀 Action Options")
        st.caption("Choose how you would like to proceed with this visual evidence:")
        c_act1, c_act2, c_act3 = st.columns(3)
        with c_act1:
            if st.button("🤖 Launch Autopilot with this Screenshot", key="btn_screenshot_to_autopilot", type="primary", use_container_width=True):
                st.session_state["forwarded_multimodal_evidence"] = ("screenshot", analysis, user_question)
                st.session_state["pending_mode_navigation"] = "🤖 Autopilot Mode"
                st.rerun()
        with c_act2:
            if st.button("🎓 Explain with Personal Tutor", key="btn_screenshot_to_tutor", use_container_width=True):
                st.session_state["forwarded_tutor_evidence"] = ("screenshot", analysis, user_question)
                st.session_state["pending_mode_navigation"] = "🎓 Personal Tutor Mode"
                st.rerun()
        with c_act3:
            if st.button("🔍 Send to Diagnostic Assistant", key="btn_screenshot_to_assistant", use_container_width=True):
                st.session_state["active_problem"] = user_question or analysis.visible_facts_summary
                st.session_state["pending_mode_navigation"] = "🔍 Diagnostic & Repair Assistant"
                st.rerun()


def render_voice_diagnostics_mode(
    sys_info: Dict[str, Any],
    diag_data: Dict[str, Any],
    ollama_status: Dict[str, Any],
) -> None:
    """Render Phase 18 Voice Diagnostics interface with local transcription and diagnostic hints."""
    st.markdown("### 🎤 Voice Diagnostics")
    st.markdown(
        """
Speak or upload an audio recording of your Windows problem (WAV, MP3, OGG, FLAC, M4A, WEBM).
WinFix AI transcribes speech **strictly offline** using local models and maps symptoms to **safe read-only diagnostic tools**.
"""
    )

    # Privacy Warning Notice
    st.warning(
        "🔒 **Privacy Notice**: Voice recordings may capture background speech, usernames, passwords, or personal details. "
        "Audio is processed locally offline when a local speech model is configured. Raw audio is never transmitted to external cloud services."
    )

    col_input1, col_input2 = st.columns([1, 1])
    uploaded_audio = None

    with col_input1:
        st.markdown("#### 📁 Upload Audio File")
        uploaded_audio = st.file_uploader(
            "Upload recorded audio file (Max 25 MB / 2 min):",
            type=["wav", "mp3", "ogg", "flac", "m4a", "webm"],
            key="voice_file_uploader",
        )

    with col_input2:
        st.markdown("#### 🎙️ Microphone Recording")
        if hasattr(st, "audio_input"):
            mic_audio = st.audio_input("Record voice problem directly:", key="voice_mic_recorder")
            if mic_audio is not None:
                uploaded_audio = mic_audio
        else:
            st.info("Browser microphone capture: Use file uploader to submit local audio recordings.")

    if uploaded_audio is not None:
        audio_bytes = uploaded_audio.getvalue()
        st.audio(audio_bytes, format=getattr(uploaded_audio, "type", "audio/wav"))

        st.markdown("#### 📄 Audio Properties")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.write(f"• **Filename:** `{uploaded_audio.name}`")
            st.write(f"• **File Size:** `{len(audio_bytes) / 1024:.1f} KB` ({len(audio_bytes)} bytes)")
        with col_m2:
            st.write(f"• **Type:** `{getattr(uploaded_audio, 'type', 'audio')}`")

        user_clarification = st.text_input(
            "Optional additional text notes or context:",
            placeholder="e.g., This happened after installing the latest update.",
            key="voice_user_clarification",
        )

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            transcribe_btn = st.button("🔍 Transcribe & Analyze Voice", type="primary", use_container_width=True, key="btn_transcribe_voice")
        with btn_col2:
            clear_btn = st.button("✕ Clear Results", use_container_width=True, key="btn_clear_voice")

        if clear_btn:
            if "active_voice_analysis" in st.session_state:
                del st.session_state["active_voice_analysis"]
            if "voice_tutor_session" in st.session_state:
                del st.session_state["voice_tutor_session"]
            if "voice_tutor_transcript" in st.session_state:
                del st.session_state["voice_tutor_transcript"]
            st.rerun()

        if transcribe_btn:
            with st.spinner("Transcribing audio locally and mapping symptoms..."):
                analysis: VoiceAnalysis = default_voice_orchestrator.process_voice_input(
                    audio_bytes=audio_bytes,
                    filename=uploaded_audio.name,
                    user_clarification=user_clarification,
                    session_id="voice_active_session",
                )
                st.session_state["active_voice_analysis"] = analysis
                if analysis.status == VoiceStatus.COMPLETED and analysis.transcript and is_valid_transcript(analysis.transcript.sanitized_text):
                    t_text = analysis.transcript.sanitized_text
                    st.session_state["voice_tutor_session"] = default_personal_tutor.create_troubleshooting_flow(
                        user_question=t_text,
                        diagnostic_data=diag_data,
                    )
                    st.session_state["voice_tutor_transcript"] = t_text
                log_session_task(
                    mode="🎤 Voice Diagnostics",
                    title=f"Voice: {uploaded_audio.name}",
                    summary=analysis.transcript.sanitized_text if (analysis.transcript and analysis.transcript.sanitized_text) else "Voice audio processed",
                    status=str(analysis.status.value if hasattr(analysis.status, 'value') else analysis.status),
                    details={
                        "Inferred Domain": str(analysis.hints[0].category if analysis.hints else "General"),
                        "Duration": f"{analysis.transcript.duration_seconds:.1f}s" if analysis.transcript else "N/A",
                    },
                )
                st.rerun()

    # Display Voice Analysis Outcome if present
    if "active_voice_analysis" in st.session_state:
        analysis: VoiceAnalysis = st.session_state["active_voice_analysis"]
        st.markdown("---")
        st.markdown("### 📊 Voice Transcript & Diagnostic Assessment")

        if analysis.status == VoiceStatus.COMPLETED:
            st.success(f"🟢 **Processing Status:** Spoken input transcribed successfully ({analysis.analysis_duration_ms} ms).")
        elif analysis.status == VoiceStatus.TRANSCRIPTION_UNAVAILABLE:
            st.warning(
                "🎙️ **Voice Processing:** Your audio file was received successfully, but WinFix AI cannot transcribe it "
                "because the local speech-to-text model is not currently available.\n\n"
                "**What I Can Do:** You can install/configure the supported local speech-to-text model (`faster-whisper`), "
                "or type the problem manually using Text Diagnostics."
            )
        elif analysis.status == VoiceStatus.TRANSCRIPT_EMPTY:
            st.info("🎙️ **Voice Processing:** Audio was received, but no spoken words were detected in the recording.")
        else:
            st.error(f"🔴 **Status:** {analysis.inferred_intent or analysis.status.value}")

        # 1. Transcript Display & Review
        st.markdown("#### 🗣️ What I Heard")
        if analysis.transcript.text:
            edited_transcript = st.text_area(
                "Review / Edit Transcript before running diagnostics:",
                value=analysis.transcript.sanitized_text,
                key="voice_transcript_editor",
            )
            st.caption(f"Model: `{analysis.transcript.model_used}` | Duration: {analysis.transcript.duration_seconds}s | Language Confidence: {analysis.transcript.confidence:.2f}")

            # Keep troubleshooting flow synchronized if user edits the transcript text
            curr_text = edited_transcript.strip() if is_valid_transcript(edited_transcript) else analysis.transcript.sanitized_text
            if curr_text and curr_text != st.session_state.get("voice_tutor_transcript"):
                st.session_state["voice_tutor_session"] = default_personal_tutor.create_troubleshooting_flow(
                    user_question=curr_text,
                    diagnostic_data=diag_data,
                )
                st.session_state["voice_tutor_transcript"] = curr_text
        else:
            if analysis.status == VoiceStatus.TRANSCRIPTION_UNAVAILABLE:
                st.info("The spoken audio could not be transcribed because the local speech-to-text model is unavailable.")
            else:
                st.info(analysis.inferred_intent or "No transcript available.")

        # 2. Inferred Problem Domain & What Voice Cannot Prove
        col_intent, col_verif = st.columns(2)
        with col_intent:
            st.markdown("#### 💡 Inferred Problem Domain")
            if analysis.hints:
                for h in analysis.hints:
                    st.write(f"• **Domain:** `{h.category}` — {h.reason}")
            else:
                st.write("• Domain not automatically classified.")

        with col_verif:
            st.markdown("#### ⚠️ What Voice Cannot Prove")
            if analysis.what_needs_verification:
                for item in analysis.what_needs_verification:
                    st.write(f"• {item}")
            else:
                st.write("• Spoken statements must be verified against active Windows services and network adapters.")

        # 3. Interactive Step-by-Step Troubleshooting Guide
        has_transcript = (analysis.status == VoiceStatus.COMPLETED and analysis.transcript and is_valid_transcript(analysis.transcript.sanitized_text))
        if has_transcript:
            if "voice_tutor_session" not in st.session_state:
                st.session_state["voice_tutor_session"] = default_personal_tutor.create_troubleshooting_flow(
                    user_question=analysis.transcript.sanitized_text,
                    diagnostic_data=diag_data,
                )
                st.session_state["voice_tutor_transcript"] = analysis.transcript.sanitized_text
            render_step_by_step_tutor_guide(st.session_state["voice_tutor_session"])
        else:
            st.info("ℹ️ A valid speech transcript is required to formulate an interactive troubleshooting guide.")

        # Developer view expander for underlying tool registry mappings
        with st.expander("🛠️ Candidate Diagnostic Tools — Developer View", expanded=False):
            st.caption("Underlying diagnostic tools mapped to this voice domain:")
            all_candidate_tools: Set[str] = set()
            for h in analysis.hints:
                for t_name in h.candidate_tools:
                    all_candidate_tools.add(t_name)
            if all_candidate_tools:
                for t_name in sorted(all_candidate_tools):
                    tool = default_tool_registry.get(t_name)
                    if tool:
                        st.markdown(f"• **`{tool.name}`** — *{tool.description}* (`{tool.domain}` | Risk: `{tool.risk.value}`)")
            else:
                st.write("• No specific candidate diagnostic tools mapped.")

        # 4. Personal Tutor Breakdown
        st.markdown("---")
        st.markdown("#### 🎓 Personal Tutor Breakdown")
        tutor_resp = default_voice_orchestrator.explain_voice_analysis(analysis)
        render_tutor_response_card(tutor_resp)

        # 5. Operating Mode Actions
        st.markdown("---")
        st.markdown("#### 🚀 Action Options")
        st.caption("Choose how you would like to proceed with this voice evidence:")
        if has_transcript:
            c_act1, c_act2, c_act3 = st.columns(3)
            with c_act1:
                if st.button("🤖 Launch Autopilot with this Voice Evidence", key="btn_voice_to_autopilot", type="primary", use_container_width=True):
                    st.session_state["forwarded_multimodal_evidence"] = ("voice", analysis, st.session_state.get("voice_user_clarification"))
                    st.session_state["pending_mode_navigation"] = "🤖 Autopilot Mode"
                    st.rerun()
            with c_act2:
                if st.button("🎓 Explain with Personal Tutor", key="btn_voice_to_tutor", use_container_width=True):
                    st.session_state["forwarded_tutor_evidence"] = ("voice", analysis, st.session_state.get("voice_user_clarification"))
                    st.session_state["pending_mode_navigation"] = "🎓 Personal Tutor Mode"
                    st.rerun()
            with c_act3:
                if st.button("🔍 Send to Diagnostic Assistant", key="btn_voice_to_assistant", use_container_width=True):
                    st.session_state["active_problem"] = analysis.transcript.sanitized_text
                    st.session_state["pending_mode_navigation"] = "🔍 Diagnostic & Repair Assistant"
                    st.rerun()
        else:
            st.info("ℹ️ Automated routing to Autopilot and Personal Tutor requires a valid speech transcript. You can switch modes manually using the sidebar selector.")


def render_technical_drawer(
    sys_info: Dict[str, Any],
    ollama_status: Dict[str, Any],
    db_health: Dict[str, Any],
    diag_data: Dict[str, Any],
) -> None:
    """Render expandable drawer with complete diagnostic data and tool registry status in clean tables."""
    with st.expander("🔍 Expand Technical Details & Raw Diagnostics"):
        st.markdown("#### Approved Tool Registry")
        tools = default_tool_registry.list_tools()
        table_rows = [
            f"| `{t.name}` | {t.domain.capitalize()} | `{t.risk.value}` | {'Yes' if t.read_only else 'No'} | {'Yes' if t.requires_admin else 'No'} |"
            for t in tools
        ]
        table_md = "| Tool | Domain | Risk | Read Only | Requires Admin |\n| --- | --- | --- | --- | --- |\n" + "\n".join(table_rows)
        st.markdown(table_md)

        st.markdown("---")
        st.markdown("#### Complete Read-Only Diagnostics Payload")
        render_diagnostic_results_table(diag_data)

        st.markdown("---")
        st.markdown("#### Complete System Information Payload")
        render_system_info_table(sys_info)

        st.markdown("---")
        st.markdown("#### Runtime & Database Subsystem Status")
        render_runtime_health_tables(ollama_status, db_health)


def main() -> None:
    """Main application loop."""
    # Process pending mode navigation before rendering sidebar widgets
    if "pending_mode_navigation" in st.session_state:
        st.session_state["app_operating_mode"] = st.session_state.pop("pending_mode_navigation")

    render_header()

    # 1. Database Health Check & Auto-Init
    if "cached_db_health" not in st.session_state:
        db_health = db_manager.check_health()
        if db_health["connected"] and db_health["tables_count"] == 0:
            db_manager.init_db()
            db_health = db_manager.check_health()
        st.session_state["cached_db_health"] = db_health
    else:
        db_health = st.session_state["cached_db_health"]

    if "cached_session_count" not in st.session_state:
        session_repo = SessionRepository(db_manager)
        st.session_state["cached_session_count"] = session_repo.count() if db_health["connected"] else 0
    session_count = st.session_state["cached_session_count"]
    tool_count = default_tool_registry.count()

    # 2. Ollama & Model Health Check
    if "cached_ollama_status" not in st.session_state:
        with st.spinner("Checking Ollama runtime..."):
            st.session_state["cached_ollama_status"] = ollama_client.check_model_availability()
    ollama_status = st.session_state["cached_ollama_status"]

    # 3. Collect Read-Only System Information
    if "cached_sys_info" not in st.session_state:
        with st.spinner("Collecting Windows system information..."):
            st.session_state["cached_sys_info"] = get_complete_system_info()
    sys_info = st.session_state["cached_sys_info"]

    # 4. Collect Read-Only Windows Diagnostics across Domains
    if "cached_diag_data" not in st.session_state:
        with st.spinner("Running safe read-only diagnostics..."):
            st.session_state["cached_diag_data"] = {
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
                "crash_summary": get_application_crash_summary(time_window="24h", limit=10, max_scan=50),
                "wer_status": get_windows_error_reporting_status(),
            }
    diag_data = st.session_state["cached_diag_data"]

    # Sidebar: About and Roadmap & Mode selection
    with st.sidebar:
        st.markdown(f"### 🛠 {config.app_name}")
        st.caption(f"Version {config.app_version}")
        st.markdown("---")

        mode_options = [
            "🔍 Diagnostic & Repair Assistant",
            "🎓 Personal Tutor Mode",
            "🤖 Autopilot Mode",
            "📷 Screenshot Diagnostics",
            "🎤 Voice Diagnostics",
        ]
        curr_mode = st.session_state.get("app_operating_mode", mode_options[0])
        mode_index = mode_options.index(curr_mode) if curr_mode in mode_options else 0

        mode = st.radio(
            "Operating Mode:",
            mode_options,
            index=mode_index,
            key="app_operating_mode",
        )
        st.markdown("---")
        kb_stats = default_knowledge_service.get_stats()
        st.caption(f"📚 Knowledge Base: {kb_stats['total_articles']} Articles (v{kb_stats['version']})")
        st.caption(f"ℹ️ Mode: {MODE_DESCRIPTIONS.get(mode, '')}")
        st.markdown("---")
        st.markdown("**Safety Rule:**")
        st.info("`LLM != Windows Shell`\n\nAll actions must use explicitly registered tools and pass strict safety validation.")

        # Live Session Task Reports & Export
        render_sidebar_task_reports()

    # Render Welcome Guide (Phase 35) if not dismissed
    if st.session_state.get("show_welcome_guide", True):
        render_welcome_guide()

    # Render dashboard sections based on Mode
    render_foundation_status(ollama_status, db_health, session_count, tool_count)

    # Check for interrupted session recovery (Phase 35)
    interrupted_id = st.session_state.get("interrupted_session_id")
    if interrupted_id:
        render_recovery_card(
            session_id=interrupted_id,
            interrupted_step=st.session_state.get("interrupted_step", "DIAGNOSTIC_VERIFICATION"),
            on_resume=lambda: st.session_state.pop("interrupted_session_id", None),
            on_start_over=lambda: (
                st.session_state.pop("interrupted_session_id", None),
                st.session_state.pop("last_diag_result", None),
                st.session_state.pop("last_repair_result", None),
            ),
        )

    if mode == "🎓 Personal Tutor Mode":
        render_personal_tutor_mode(sys_info, diag_data, ollama_status)
    elif mode == "🤖 Autopilot Mode":
        render_autopilot_mode(sys_info, diag_data, ollama_status)
    elif mode == "📷 Screenshot Diagnostics":
        render_screenshot_diagnostics_mode(sys_info, diag_data, ollama_status)
    elif mode == "🎤 Voice Diagnostics":
        render_voice_diagnostics_mode(sys_info, diag_data, ollama_status)
    else:
        render_ai_diagnostic_assistant(sys_info, ollama_status)
        render_system_information(sys_info)
        render_readonly_diagnostics(diag_data)

    st.markdown("---")

    # Maintenance & Refresh
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        if st.button("🔄 Refresh All Diagnostics", use_container_width=True):
            for k in ["cached_db_health", "cached_session_count", "cached_ollama_status", "cached_sys_info", "cached_diag_data", "cached_ai_agg"]:
                st.session_state.pop(k, None)
            try:
                from ai.model_manager import ai_model_manager
                ai_model_manager._last_health_aggregation = None
            except Exception:
                pass
            st.rerun()
    with m_col2:
        if st.button("📦 Re-initialize Database Schema", use_container_width=True):
            res = db_manager.init_db()
            if res["success"]:
                st.success(f"Database initialized with {len(res['tables'])} tables!")
            for k in ["cached_db_health", "cached_session_count", "cached_ollama_status", "cached_sys_info", "cached_diag_data"]:
                st.session_state.pop(k, None)
            st.rerun()

    # Technical Details Drawer
    render_technical_drawer(sys_info, ollama_status, db_health, diag_data)


if __name__ == "__main__":
    main()

