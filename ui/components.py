"""Reusable Streamlit presentation components for WinFix AI (Phases 20 & 35).

Provides structured cards, headers, status panels, confirmation dialogs,
evidence views, knowledge displays, recovery flows, and accessible UI controls.
Strictly adheres to: LLM != Windows Shell and UI != Execution Layer.
"""

from typing import Any, Callable, Dict, List, Optional
import streamlit as st

from agent.tool_metadata import RiskLevel, ToolDefinition
from database.knowledge_models import KnowledgeArticle
from ui.accessibility import (
    accessible_button_label,
    accessible_status_indicator,
    format_accessible_diff,
)
from ui.formatting import (
    ConfidenceLevel,
    format_bytes,
    format_human_verification_status,
    format_progress_step,
    format_risk_badge,
    format_severity_badge,
    format_status_badge,
    format_timestamp,
    format_tool_name,
    format_tutor_text_list,
    format_user_friendly_terminology,
    map_confidence,
    render_json_as_table,
    truncate_text_safely,
)
from ui.state import AppMode, MODE_DESCRIPTIONS, UIStatusState


def render_app_header(is_offline: bool = True) -> None:
    """Render top application banner with offline badge and description."""
    col_title, col_status = st.columns([4, 1])
    with col_title:
        st.title("🛠 WinFix AI")
        st.markdown("**Calm, Understandable Windows Troubleshooting & Verified Repair Assistant**")
    with col_status:
        if is_offline:
            st.success("● Local & Private")
        else:
            st.warning("● Hybrid Mode")
    st.markdown("---")


def render_welcome_guide(on_dismiss: Optional[Callable[[], None]] = None) -> None:
    """Render lightweight, dismissable first-run education and landing guide (Phase 35)."""
    with st.container(border=True):
        st.markdown("### 👋 Welcome to WinFix AI")
        st.markdown(
            "WinFix AI is your **local Windows troubleshooting assistant**. "
            "It checks your computer safely, explains what is happening in simple terms, "
            "and asks for your permission before making any repairs."
        )
        st.markdown(
            """
**How to get started:**
• **Describe a problem** — Type what you are experiencing in plain language
• **Analyze a screenshot** — Upload an image of an error message or dialog
• **Use voice** — Speak naturally to describe your PC symptom
• **Check my PC** — Run safe, read-only diagnostic checks
            """
        )
        c1, c2 = st.columns([3, 1])
        with c1:
            st.caption("🔒 All diagnostics and AI reasoning run locally on your PC. No data is sent to the cloud.")
        with c2:
            if st.button("✕ Dismiss Guide", key="btn_dismiss_welcome_guide", use_container_width=True):
                if on_dismiss:
                    on_dismiss()
                st.session_state["show_welcome_guide"] = False
                st.rerun()


def render_mode_selector(current_mode: str) -> str:
    """Render unified mode selector and display current mode purpose description."""
    mode_options = [
        AppMode.DIAGNOSTIC.value,
        AppMode.TUTOR.value,
        AppMode.AUTOPILOT.value,
        AppMode.SCREENSHOT.value,
        AppMode.VOICE.value,
    ]
    idx = mode_options.index(current_mode) if current_mode in mode_options else 0

    selected = st.radio(
        "Select Operating Mode:",
        mode_options,
        index=idx,
        key="ui_mode_selector_radio",
        horizontal=False,
    )
    desc = MODE_DESCRIPTIONS.get(selected, "")
    st.info(f"ℹ️ **{selected}**: {desc}")
    st.markdown("---")
    return selected


def render_system_status_panel(
    ollama_status: Dict[str, Any],
    db_health: Dict[str, Any],
    session_count: int,
    tool_count: int,
    kb_stats: Optional[Dict[str, Any]] = None,
) -> None:
    """Render system status cards (Local AI, SQLite Database, Tool Registry, Knowledge Base)."""
    st.markdown("### 🔌 System Foundation & Safety Engine")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("#### 🧠 Local AI Engine")
        if ollama_status.get("connected"):
            if ollama_status.get("model_available"):
                st.success("✓ Local AI Ready")
                st.caption(f"Model: `{ollama_status.get('model', 'gemma4:12b')}`")
            else:
                st.warning("⚠️ Local AI Connected")
                st.caption("Model not pulled locally.")
        else:
            st.error("✕ Local AI Offline")
            st.caption("Deterministic fallback active.")

    with col2:
        st.markdown("#### 🗄 Storage")
        if db_health.get("connected"):
            st.success("✓ Database Ready")
            st.caption(f"{db_health.get('tables_count', 0)} tables | {session_count} sessions")
        else:
            st.error("✕ Storage Error")
            st.caption("Storage inaccessible.")

    with col3:
        st.markdown("#### 🛡 Tool Registry")
        st.success(f"✓ {tool_count} Tools Cataloged")
        st.caption("49 SAFE | 10 MEDIUM | 0 HIGH")

    with col4:
        st.markdown("#### 📚 Knowledge Base")
        if kb_stats and kb_stats.get("status") == "HEALTHY":
            st.success("✓ Knowledge Ready")
            st.caption(f"{kb_stats.get('total_articles', 9)} articles (v{kb_stats.get('version', 1)})")
        else:
            st.info("● Built-in Guidance")
            st.caption("Offline rules active.")

    st.markdown("---")


def render_privacy_notice(mode_name: str) -> None:
    """Render persistent privacy reassurance card."""
    with st.expander("🔒 Privacy & Local Processing Notice", expanded=False):
        st.markdown(
            f"""
**WinFix AI Local Privacy Safeguards:**
- All diagnostic checks, knowledge lookups, and AI planning are performed **locally on your Windows PC**.
- User profile paths (`C:\\Users\\<USER>`), emails, and credential strings are automatically **sanitized** before reasoning.
- Screenshots and voice recordings are processed locally and are **never uploaded to external cloud APIs**.
- Operating mode: `{mode_name}` adheres strictly to zero cloud telemetry.
            """
        )


def render_workflow_steps(active_step: str) -> None:
    """Visual workflow progression tracker with human-readable descriptions."""
    steps = ["INPUT", "ANALYSIS", "EVIDENCE", "KNOWLEDGE", "DIAGNOSTIC", "ACTION", "VERIFICATION"]
    active_idx = steps.index(active_step.upper()) if active_step.upper() in steps else 0

    cols = st.columns(len(steps))
    for idx, (col, step_label) in enumerate(zip(cols, steps)):
        with col:
            friendly_name = format_progress_step(step_label)
            if idx < active_idx:
                st.markdown(f"**✓ {step_label}**\n\n<small>{friendly_name}</small>", unsafe_allow_html=True)
            elif idx == active_idx:
                st.markdown(f"**🔷 {step_label}**\n\n<small>{friendly_name}</small>", unsafe_allow_html=True)
            else:
                st.caption(f"○ {step_label}\n\n<small>{friendly_name}</small>")
    st.markdown("---")


def render_standardized_diagnosis_card(
    summary: str,
    likely_cause: str,
    evidence: List[str],
    recommendations: List[str],
    confidence_level: Optional[str] = None,
    observations: Optional[List[str]] = None,
    inferences: Optional[List[str]] = None,
    unknowns: Optional[List[str]] = None,
    contradictions: Optional[List[str]] = None,
    technical_details: Optional[Dict[str, Any]] = None,
) -> None:
    """Render standardized diagnostic finding card (Phase 35)."""
    with st.container(border=True):
        st.markdown("### 🔍 What WinFix AI Found")
        
        # Plain Problem & Cause
        st.markdown(f"**Possible Cause:** {likely_cause}")
        st.write(summary)

        # Confidence Grounding
        conf = confidence_level or map_confidence(evidence_count=len(evidence), contradictions_found=bool(contradictions), is_uncertain=bool(unknowns))
        st.markdown(f"**Confidence:** `{conf}`")

        # Contradiction warning if conflicting evidence found
        if contradictions:
            st.warning("⚠️ **Conflicting Evidence Detected:** Some diagnostic findings do not agree. WinFix AI will not guess and recommends further safe inspection.")
            for c in contradictions:
                st.write(f"• {c}")

        # Why we think this (Evidence)
        if evidence or observations:
            with st.expander("📋 Why We Think This (Evidence)", expanded=True):
                if observations:
                    st.markdown("**Direct Windows Observations:**")
                    for obs in observations:
                        st.write(f"✓ {obs}")
                elif evidence:
                    for ev in evidence:
                        st.write(f"✓ {ev}")
                if inferences:
                    st.markdown("**Diagnostic Inferences:**")
                    for inf in inferences:
                        st.write(f"💡 {inf}")

        # What we know vs what we don't know
        if unknowns:
            with st.expander("❓ What We Don't Know Yet", expanded=False):
                st.caption("WinFix AI separates confirmed facts from hypotheses:")
                for u in unknowns:
                    st.write(f"• {u}")

        # Safe Next Steps
        if recommendations:
            st.markdown("#### 🛡️ Recommended Safe Next Steps")
            for rec in recommendations:
                st.write(f"• {rec}")

        # Safe Technical Details
        if technical_details:
            with st.expander("🛠 Technical Details (For Advanced Users)", expanded=False):
                for k, v in technical_details.items():
                    st.write(f"**{k}:** `{v}`")


def render_evidence_card(
    evidence_list: List[str],
    observed: Optional[List[str]] = None,
    inferred: Optional[List[str]] = None,
    unverified: Optional[List[str]] = None,
) -> None:
    """Render structured evidence breakdown separating observed facts from unverified hypotheses."""
    container = st.container(border=True)
    with container:
        st.markdown("#### 📋 Diagnostic Evidence Breakdown")

        if observed:
            st.markdown("**🔍 Observed Windows Facts:**")
            for item in observed:
                st.write(f"• {item}")
        elif evidence_list:
            st.markdown("**🔍 Verified Facts:**")
            for item in evidence_list:
                st.write(f"• {item}")

        if inferred:
            st.markdown("**💡 Plausible Inferences:**")
            for item in inferred:
                st.write(f"• {item}")

        if unverified:
            st.markdown("**⚠️ Not Yet Verified:**")
            for item in unverified:
                st.caption(f"○ {item}")


def render_knowledge_card(article: KnowledgeArticle) -> None:
    """Render local troubleshooting knowledge guidance card."""
    with st.expander(f"📚 Local Knowledge Guide: {article.title}", expanded=True):
        cat_val = article.category.value if hasattr(article.category, "value") else str(article.category)
        sev_val = article.severity.value if hasattr(article.severity, "value") else str(article.severity)
        st.markdown(f"**Domain:** `{cat_val}` | **Severity:** `{format_severity_badge(sev_val)}` | **Version:** `v{article.version}`")
        st.markdown(f"**Summary:** {article.summary}")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Possible Root Causes:**")
            for cause in article.possible_causes:
                st.write(f"• {cause}")
        with col2:
            st.markdown("**Recommended Diagnostic Checks:**")
            for step in article.diagnostic_steps:
                st.write(f"• {step}")

        st.markdown("**Deterministic Verification Criteria:**")
        for vstep in article.verification_steps:
            st.write(f"✓ {vstep}")
        st.caption("ℹ️ Local Knowledge is informational reference data. Live deterministic tools verify active system state.")


def render_tool_card(tool_def: ToolDefinition) -> None:
    """Render tool metadata card."""
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**Tool:** `{tool_def.name}`")
            st.write(tool_def.description)
        with col2:
            st.markdown(f"**Domain:** `{tool_def.domain}`")
            st.markdown(f"**Risk:** {format_risk_badge(tool_def.risk)}")
            st.caption(f"Admin Required: {'Yes' if tool_def.requires_admin else 'No'}")


def render_confirmation_card(
    proposal_title: str,
    proposal_description: str,
    tool_name: str,
    risk: str = "MEDIUM",
    requires_admin: bool = True,
    verification_target: Optional[str] = None,
) -> None:
    """Render high-visibility confirmation card for proposed repair operations."""
    st.warning("⚠️ **Explicit User Confirmation Required**")
    container = st.container(border=True)
    with container:
        st.markdown(f"### Proposed Repair: {proposal_title}")
        st.write(proposal_description)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Target Tool:** `{tool_name}`")
            st.markdown(f"**Risk Classification:** {format_risk_badge(risk)}")
        with col2:
            st.markdown(f"**Administrator Privileges:** {'Required' if requires_admin else 'Not Required'}")
            st.markdown(f"**Post-Repair Verification:** `{verification_target or 'Active State Check'}`")

def render_standardized_medium_confirmation(
    proposal_title: str,
    action_description: str,
    what_will_happen: str,
    what_will_not_happen: str,
    risk: str = "MEDIUM",
    is_stale: bool = False,
) -> None:
    """Render high-visibility explicit confirmation card for MEDIUM operations (Phase 35)."""
    with st.container(border=True):
        st.warning("⚠️ **Before continuing — Your Explicit Approval is Required**")
        if is_stale:
            st.error("⚠️ **This approval is no longer valid.** The Windows state has changed. Please review the action again.")
            return

        st.markdown(f"### Proposed Action: {proposal_title}")
        st.write(action_description)

        st.markdown(f"**Risk Classification:** {format_risk_badge(risk)}")
        st.markdown(f"**What will happen:** {what_will_happen}")
        st.markdown(f"**What will NOT happen:** {what_will_not_happen}")
        st.caption("🔒 All actions execute strictly through allowlisted Windows tools with immediate post-repair verification.")


def render_standardized_repair_proposal_card(
    proposal: Any,
    domain_label: str = "Windows Component",
    is_stale: bool = False,
) -> None:
    """Render standardized repair proposal card with explicit permissions and safety guarantees (Phase 35)."""
    with st.container(border=True):
        st.markdown(f"### ⚙️ Recommended Fix — {domain_label}")
        
        if is_stale:
            st.error("⚠️ **This approval is no longer valid.** The Windows state has changed or this action was already processed. Please review the diagnosis again.")
            return

        tool_name = getattr(proposal, "tool_name", "repair_action")
        risk_val = getattr(proposal, "risk", "MEDIUM")
        reason = getattr(proposal, "reason", "Resolve identified Windows state anomaly.")
        expected = getattr(proposal, "expected_effect", "Restore normal component operation.")
        verif_tool = getattr(proposal, "verification_tool", "diagnostic_check")
        req_admin = getattr(proposal, "requires_admin", False)

        st.markdown(f"**Action:** `{format_tool_name(tool_name)}`")
        st.markdown(f"**Risk Level:** {format_risk_badge(risk_val)}")
        st.write(f"**Why this is recommended:** {reason}")
        st.write(f"**What will happen:** {expected}")
        st.caption(f"**What will NOT happen:** WinFix AI will NOT modify unrelated services, files, or settings.")
        
        if req_admin:
            st.info("🔒 **Administrator Permission:** This operation requires Windows administrator privileges.")

        st.caption(f"🔍 WinFix AI will immediately verify this fix using `{verif_tool}`.")


def render_standardized_verification_card(
    verification_status: str,
    explanation: str,
    tool_name: str,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    verification_tool: Optional[str] = None,
) -> None:
    """Render standardized post-repair verification card (Phase 35)."""
    with st.container(border=True):
        st.markdown("### 🔍 Post-Repair State Verification")
        
        st_clean = str(verification_status).lower().strip()
        if st_clean in ("verified", "success"):
            st.success(f"✓ **Fix Verified:** {explanation}")
            st.markdown("Windows is now confirmed to be in the expected healthy state.")
        elif "partial" in st_clean:
            st.warning(f"⚠️ **Partially Resolved:** {explanation}")
            st.markdown("The repair improved the situation, but the original issue is not fully resolved.")
        elif "timeout" in st_clean:
            st.warning(f"⚠️ **Verification Timeout:** {explanation}")
            st.markdown("The service did not reach running status within the timeout window.")
        else:
            st.error(f"✕ **Fix Did Not Resolve Problem:** {explanation}")
            st.markdown("The repair was attempted, but Windows is still not in the expected state. No additional repair was performed automatically.")

        # Before vs After State Comparison
        if before_state or after_state:
            with st.expander("📊 State Comparison Table (Before vs After)", expanded=True):
                col_b, col_a = st.columns(2)
                with col_b:
                    st.markdown("**State Before Repair:**")
                    render_json_as_table(before_state or {"status": "unrecorded"}, st)
                with col_a:
                    st.markdown("**State After Repair:**")
                    render_json_as_table(after_state or {"status": "unrecorded"}, st)

        if verification_tool:
            st.caption(f"Verified using read-only tool: `{verification_tool}`")


def render_verification_result(
    verification_status: str,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> None:
    """Legacy verification outcome card."""
    render_standardized_verification_card(
        verification_status=verification_status,
        explanation=notes or format_human_verification_status(verification_status),
        tool_name="repair_action",
        before_state=before_state,
        after_state=after_state,
    )


def render_recovery_card(
    session_id: str,
    interrupted_step: str,
    on_resume: Optional[Callable[[], None]] = None,
    on_start_over: Optional[Callable[[], None]] = None,
) -> None:
    """Render safe recovery card for interrupted troubleshooting sessions (Phases 31 & 35)."""
    with st.container(border=True):
        st.warning("⚠️ **Interrupted Troubleshooting Session Found**")
        st.markdown(
            f"WinFix AI detected an incomplete troubleshooting session (`{session_id}`) "
            f"that was interrupted at step **`{interrupted_step}`**."
        )
        st.info("🛡️ **Safety Guarantee:** Before continuing, WinFix AI will re-check the live Windows state. It will never assume a previous repair succeeded.")
        
        col_res, col_reset = st.columns(2)
        with col_res:
            if st.button("🔄 Resume Safely (Re-check PC First)", type="primary", use_container_width=True, key="btn_resume_recovery"):
                if on_resume:
                    on_resume()
        with col_reset:
            if st.button("✕ Start Fresh Session", use_container_width=True, key="btn_discard_recovery"):
                if on_start_over:
                    on_start_over()


def render_error_state(
    title: str,
    what_happened: str,
    what_to_do: List[str],
    debug_details: Optional[str] = None,
) -> None:
    """Render standardized user-friendly failure card without raw tracebacks."""
    st.error(f"⚠️ {title}")
    container = st.container(border=True)
    with container:
        st.markdown(f"**What Happened:** {what_happened}")
        if what_to_do:
            st.markdown("**What You Can Do:**")
            for action in what_to_do:
                st.write(f"• {action}")
        if debug_details:
            with st.expander("🛠 Technical Debug Details", expanded=False):
                st.code(debug_details)


def render_user_friendly_error(
    title: str,
    message: str,
    recovery_steps: Optional[List[str]] = None,
    technical_details: Optional[str] = None,
) -> None:
    """Render calm, human-friendly error notification (Phase 35)."""
    with st.container(border=True):
        st.error(f"⚠️ {title}")
        st.markdown(f"**What happened:** {message}")
        st.caption("🔒 No changes were made to your computer.")
        
        if recovery_steps:
            st.markdown("**What you can do:**")
            for step in recovery_steps:
                st.write(f"• {step}")
                
        if technical_details:
            with st.expander("🛠 Technical Error Details (Advanced)", expanded=False):
                st.code(technical_details)


def render_empty_state(
    mode_name: str,
    headline: str,
    suggestions: List[str],
) -> None:
    """Render informative empty state for modes awaiting user input."""
    container = st.container(border=True)
    with container:
        st.markdown(f"### {headline}")
        st.write(f"WinFix AI is ready in **{mode_name}**.")
        if suggestions:
            st.markdown("**Getting Started:**")
            for s in suggestions:
                st.write(f"• {s}")


def render_ai_lifecycle_panel(ai_status: Optional[Dict[str, Any]] = None) -> None:
    """Render local AI model status and capability breakdown panel."""
    with st.expander("🧠 Local AI Models & Capabilities", expanded=False):
        if not ai_status:
            st.info("AI status not available.")
            return

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("##### 📝 Text Generation Model")
            text_data = ai_status.get("text_model") or {}
            m_id = text_data.get("model_id", "gemma4:12b")
            status = text_data.get("status", "UNKNOWN")
            st.write(f"**Model:** `{m_id}`")
            st.write(f"**Status:** {status}")
            caps = text_data.get("capabilities", [])
            if caps:
                st.caption(f"Capabilities: {', '.join(caps)}")

        with col2:
            st.markdown("##### 📷 Vision Model")
            vision_data = ai_status.get("vision_model") or {}
            v_id = vision_data.get("model_id", "minicpm-v:latest")
            v_status = vision_data.get("status", "UNKNOWN")
            st.write(f"**Model:** `{v_id}`")
            st.write(f"**Status:** {v_status}")
            v_caps = vision_data.get("capabilities", [])
            if v_caps:
                st.caption(f"Capabilities: {', '.join(v_caps)}")

        with col3:
            st.markdown("##### 🎤 Speech-to-Text")
            stt_data = ai_status.get("stt_model") or {}
            s_id = stt_data.get("model_id", "whisper_cpp")
            s_status = stt_data.get("status", "UNKNOWN")
            st.write(f"**Engine:** `{s_id}`")
            st.write(f"**Status:** {s_status}")
            s_caps = stt_data.get("capabilities", [])
            if s_caps:
                st.caption(f"Capabilities: {', '.join(s_caps)}")

        overall_st = ai_status.get("overall_status", "UNKNOWN")
        degraded_label = "Inactive (Full AI Active)" if overall_st == "READY" else "Active (Fallback Engaged)"
        st.caption(f"Last Evaluation: {ai_status.get('timestamp', 'N/A')} | Degraded Mode: {degraded_label}")


def render_diagnostic_intelligence_card(diag_data: Dict[str, Any]) -> None:
    """Render structured AI diagnostic intelligence card separating Observations, Interpretations, Hypotheses, and Next Steps."""
    container = st.container(border=True)
    with container:
        st.markdown(f"### 🧠 Diagnostic Summary: {diag_data.get('summary', 'Diagnostic Evaluation')}")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 👁️ Observed Facts")
            obs = diag_data.get("observations", [])
            if obs:
                for o in obs:
                    st.write(f"• {o}")
            else:
                st.caption("No specific factual observations recorded.")

            st.markdown("#### 💡 Inferred Interpretation")
            interps = diag_data.get("interpretations", [])
            if interps:
                for i in interps:
                    st.write(f"• {i}")
            else:
                st.caption("No additional inferences derived.")

        with col2:
            st.markdown("#### 🔬 Diagnostic Hypotheses")
            hyps = diag_data.get("hypotheses", [])
            if hyps:
                for h in hyps:
                    status_str = h.get("status", "POSSIBLE")
                    stmt = h.get("statement", "")
                    st.write(f"• **[{status_str}]** {stmt}")
                    if h.get("explanation"):
                        st.caption(f"Explanation: {h.get('explanation')}")
            else:
                st.caption("No active hypotheses formulated.")

            st.markdown("#### ❓ Uncertainty & Unknowns")
            unc = diag_data.get("uncertainty", [])
            if unc:
                for u in unc:
                    st.write(f"• {u}")
            else:
                st.caption("No unresolved uncertainty notes.")

        rec_tools = diag_data.get("recommended_tools", [])
        if rec_tools:
            st.markdown("#### 🛠️ Recommended Next Diagnostic Tools")
            st.write(f"Tools: `{'`, `'.join(rec_tools)}`")

        if diag_data.get("tutor_explanation"):
            exp_items = format_tutor_text_list(diag_data.get("tutor_explanation"))
            if exp_items:
                with st.expander("🎓 Educational Explanation", expanded=False):
                    if len(exp_items) == 1:
                        st.write(exp_items[0])
                    else:
                        for it in exp_items:
                            st.write(f"• {it}")


def render_troubleshooting_workflow_card(workflow_data: Dict[str, Any]) -> None:
    """Render guided Phase 28 Troubleshooting Workflow card with progress, current step, and verification."""
    container = st.container(border=True)
    with container:
        st.markdown(f"### 📋 Troubleshooting Workflow: {workflow_data.get('title', 'Active Workflow')}")
        
        status = workflow_data.get("status", "CREATED")
        current_step_idx = workflow_data.get("current_step", 0)
        steps = workflow_data.get("steps", [])
        total_steps = len(steps)
        
        col_stat, col_prog = st.columns([1, 2])
        with col_stat:
            st.markdown(f"**Status:** `{status}`")
            res = workflow_data.get("resolution_status", "INCONCLUSIVE")
            st.markdown(f"**Resolution:** `{res}`")
        with col_prog:
            prog_val = min(1.0, float(current_step_idx) / float(total_steps)) if total_steps > 0 else 0.0
            st.progress(prog_val, text=f"Step {min(current_step_idx + 1, total_steps)} of {total_steps}")

        st.markdown("---")
        
        if current_step_idx < total_steps:
            current_step = steps[current_step_idx]
            st.markdown(f"#### 🔍 Current Step: {current_step.get('purpose', 'Step Execution')}")
            st.write(f"• **Step Type:** `{current_step.get('step_type', 'DIAGNOSE')}`")
            if current_step.get("tool_name"):
                st.write(f"• **Tool:** `{current_step.get('tool_name')}`")
            if current_step.get("authorization_required"):
                st.warning("⚠️ This step requires explicit user confirmation before executing.")
        else:
            st.success("All workflow steps completed.")

        before = workflow_data.get("before_evidence")
        after = workflow_data.get("after_evidence")
        if before or after:
            st.markdown("#### ⚖️ Verification Evidence Comparison Table")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Before Action:**")
                render_json_as_table(before or {"status": "unrecorded"}, st)
            with c2:
                st.markdown("**After Action:**")
                render_json_as_table(after or {"status": "pending_verification"}, st)

        if workflow_data.get("tutor_explanation"):
            wf_items = format_tutor_text_list(workflow_data.get("tutor_explanation"))
            if wf_items:
                with st.expander("🎓 Tutor Resolution Context", expanded=False):
                    if len(wf_items) == 1:
                        st.write(wf_items[0])
                    else:
                        for it in wf_items:
                            st.write(f"• {it}")


def render_domain_troubleshooting_card(domain_data: Dict[str, Any]) -> None:
    """Render Phase 29 domain-aware troubleshooting card with evidence correlation and strategy info."""
    container = st.container(border=True)
    with container:
        primary_domain = domain_data.get("primary_domain", "UNKNOWN")
        st.markdown(f"### 🌐 Domain Intelligence: `{primary_domain}`")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Primary Domain:** `{primary_domain}`")
            secondary = domain_data.get("secondary_domains", [])
            if secondary:
                st.markdown(f"**Related Domains:** `{', '.join(secondary)}`")
            else:
                st.markdown("**Related Domains:** None identified")

        with c2:
            status = domain_data.get("status", "SUPPORTED")
            st.markdown(f"**Classification Status:** `{status}`")
            strat = domain_data.get("selected_strategy", "Standard Strategy")
            st.markdown(f"**Active Strategy:** `{strat}`")

        st.markdown("---")

        st.markdown("#### 🔍 Correlated Domain Evidence")
        evidence_summary = domain_data.get("evidence_summary", "")
        if evidence_summary:
            st.info(evidence_summary)

        ev_list = domain_data.get("evidence_items", [])
        if ev_list:
            for ev in ev_list:
                status_icon = "✓" if ev.get("status") in ["ok", "healthy", "success", "reachable", "normal"] else "✗"
                st.write(f"{status_icon} **{ev.get('title', 'Evidence')}**: {ev.get('details', '')}")
        else:
            st.caption("No domain-specific evidence collected yet.")

        if domain_data.get("tutor_explanation"):
            dom_items = format_tutor_text_list(domain_data.get("tutor_explanation"))
            if dom_items:
                with st.expander("🎓 Domain Tutor Explanation", expanded=False):
                    if len(dom_items) == 1:
                        st.write(dom_items[0])
                    else:
                        for it in dom_items:
                            st.write(f"• {it}")
