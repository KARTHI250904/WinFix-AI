"""WinFix AI — Reliability & Observability Dashboard (Phase 32).

Read-only presentation component for troubleshooting telemetry and reliability metrics.
Guarantees:
  - Strictly read-only presentation (zero execution, authorization, or recovery hooks).
  - Sanitized structured data display with complete secret scrubbing.
  - Independent of LLM decision making.
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from production.telemetry_analytics import TelemetryAnalytics, default_telemetry_analytics


def render_telemetry_dashboard(
    analytics: Optional[TelemetryAnalytics] = None,
    session_id: Optional[str] = None,
) -> None:
    """Render the comprehensive reliability and telemetry analytics dashboard."""
    analyzer = analytics or default_telemetry_analytics

    st.markdown("### 📊 Production Reliability & Observability Dashboard")
    st.caption("Local-only, privacy-preserving diagnostics telemetry and operational analytics.")

    # 1. High-Level Summary Cards
    wf_summary = analyzer.get_workflow_summary(session_id=session_id)
    rec_summary = analyzer.get_recovery_summary(session_id=session_id)
    repair_summary = analyzer.get_repair_lifecycle_stats(session_id=session_id)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Total Workflows", value=wf_summary.get("total_workflows", 0))
    with col2:
        st.metric(label="Completed", value=wf_summary.get("completed", 0))
    with col3:
        st.metric(label="Cancelled / Timed Out", value=f"{wf_summary.get('cancelled', 0)} / {wf_summary.get('timed_out', 0)}")
    with col4:
        st.metric(label="Unresolved", value=wf_summary.get("unresolved", 0))

    st.divider()

    # 2. Tabs for Detailed Metrics
    tab_wf, tab_diag, tab_rep, tab_rec, tab_dep, tab_fail = st.tabs([
        "⚡ Workflow Performance",
        "🔍 Diagnostics & Evidence",
        "🔧 Repair Lifecycle",
        "🛡️ Recovery & Checkpoints",
        "🔌 Subsystems & Health",
        "⚠️ Recent Failures",
    ])

    with tab_wf:
        st.markdown("#### Workflow Timing & Outcome Distribution")
        dur_stats = wf_summary.get("duration_stats", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Avg Duration", f"{dur_stats.get('average_ms', 0)} ms")
        with c2:
            st.metric("Median Duration", f"{dur_stats.get('median_ms', 0)} ms")
        with c3:
            st.metric("Max Duration", f"{dur_stats.get('max_ms', 0)} ms")

        domain_data = analyzer.get_domain_analytics(session_id=session_id)
        if domain_data:
            st.markdown("##### Activity by Domain")
            domain_rows = [
                {
                    "Domain": dom,
                    "Workflows": stats.get("workflows", 0),
                    "Diagnostics": stats.get("diagnostics", 0),
                    "Unresolved": stats.get("unresolved", 0),
                    "Verification Failures": stats.get("verification_failures", 0),
                }
                for dom, stats in domain_data.items()
            ]
            st.table(domain_rows)
        else:
            st.info("No domain workflow telemetry recorded in current scope.")

    with tab_diag:
        st.markdown("#### Diagnostic Effectiveness & Hypothesis Evolution")
        diag_stats = analyzer.get_diagnostic_effectiveness(session_id=session_id)
        d1, d2, d3 = st.columns(3)
        with d1:
            st.metric("Hypotheses Created", diag_stats.get("hypotheses_created", 0))
            st.metric("Hypotheses Supported", diag_stats.get("hypotheses_supported", 0))
        with d2:
            st.metric("Contradictions", diag_stats.get("hypotheses_contradicted", 0))
            st.metric("Contradiction Rate", f"{diag_stats.get('contradiction_rate', 0.0) * 100:.1f}%")
        with d3:
            st.metric("Reassessments", diag_stats.get("hypotheses_reassessed", 0))
            st.metric("Reassessment Rate", f"{diag_stats.get('reassessment_rate', 0.0) * 100:.1f}%")

    with tab_rep:
        st.markdown("#### Distinct Repair Lifecycle Stages")
        st.caption("WinFix AI tracks repair stages independently: Execution != Verification != Resolution.")
        r1, r2, r3, r4 = st.columns(4)
        with r1:
            st.metric("Candidates", repair_summary.get("candidates_created", 0))
            st.metric("Auth Required", repair_summary.get("authorizations_required", 0))
        with r2:
            st.metric("Authorized", repair_summary.get("authorizations_approved", 0))
            st.metric("Auth Rejected", repair_summary.get("authorizations_rejected", 0))
        with r3:
            st.metric("Executions Started", repair_summary.get("executions_started", 0))
            st.metric("Executions Failed", repair_summary.get("executions_failed", 0))
        with r4:
            st.metric("Verifications Succeeded", repair_summary.get("verifications_succeeded", 0))
            st.metric("Resolved Repairs", repair_summary.get("resolved_repairs", 0))

    with tab_rec:
        st.markdown("#### Phase 31 Recovery & Replay Protection")
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.metric("Checkpoints Created", rec_summary.get("checkpoints_created", 0))
            st.metric("Checkpoints Restored", rec_summary.get("checkpoints_restored", 0))
        with rc2:
            st.metric("Recovery Resumed", rec_summary.get("recovery_resumed", 0))
            st.metric("Duplicate Replays Blocked", rec_summary.get("duplicate_executions_blocked", 0))
        with rc3:
            st.metric("Authorizations Invalidated", rec_summary.get("authorizations_invalidated", 0))
            st.metric("Stale States Detected", rec_summary.get("stale_states_detected", 0))

    with tab_dep:
        st.markdown("#### Subsystem & Model Availability")
        deps = analyzer.get_dependency_reliability_stats()
        if deps:
            dep_rows = [
                {
                    "Dependency": dep,
                    "Available Events": stats.get("available_count", 0),
                    "Unavailable Events": stats.get("unavailable_count", 0),
                }
                for dep, stats in deps.items()
            ]
            st.table(dep_rows)
        else:
            st.info("All local dependencies (Ollama, Vision, Voice, SQLite) operating normally.")

    with tab_fail:
        st.markdown("#### Recent Sanitized Failures")
        failures = analyzer.get_recent_failures(limit=15)
        if failures:
            for f in failures:
                with st.container():
                    st.markdown(
                        f"**{f.get('timestamp_utc', '')}** — `{f.get('component', '')}`: "
                        f"**{f.get('failure_type', 'NONE')}** ({f.get('event_type', '')})"
                    )
                    if f.get("metadata"):
                        from ui.formatting import render_json_as_table
                        render_json_as_table(f.get("metadata"), st)
        else:
            st.success("No critical failures recorded.")
