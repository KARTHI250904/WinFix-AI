"""WinFix AI — Telemetry Analytics Aggregation Tests (Phase 32)."""

import pytest
import uuid

from production.telemetry_models import (
    FailureTaxonomy,
    TelemetryEventType,
)
from production.telemetry import TelemetryService
from production.telemetry_analytics import TelemetryAnalytics


@pytest.fixture
def populated_analytics():
    service = TelemetryService(db_manager=None)
    sess_id = f"test-sess-{uuid.uuid4().hex[:6]}"

    # Workflow lifecycle events
    service.record_workflow_event(session_id=sess_id, event_type=TelemetryEventType.WORKFLOW_STARTED, domain="NETWORK", duration_ms=10)
    service.record_workflow_event(session_id=sess_id, event_type=TelemetryEventType.WORKFLOW_COMPLETED, domain="NETWORK", duration_ms=250)
    service.record_workflow_event(session_id=sess_id, event_type=TelemetryEventType.WORKFLOW_CANCELLED, domain="PERFORMANCE", duration_ms=150)
    service.record_workflow_event(session_id=sess_id, event_type=TelemetryEventType.WORKFLOW_UNRESOLVED, domain="STORAGE", duration_ms=400)

    # Diagnostic events
    service.record_diagnostic_event(session_id=sess_id, event_type=TelemetryEventType.HYPOTHESIS_CREATED, domain="NETWORK")
    service.record_diagnostic_event(session_id=sess_id, event_type=TelemetryEventType.HYPOTHESIS_SUPPORTED, domain="NETWORK")
    service.record_diagnostic_event(session_id=sess_id, event_type=TelemetryEventType.HYPOTHESIS_CONTRADICTED, domain="NETWORK")
    service.record_diagnostic_event(session_id=sess_id, event_type=TelemetryEventType.HYPOTHESIS_REASSESSED, domain="NETWORK")

    # Repair lifecycle events
    service.record_repair_event(session_id=sess_id, event_type=TelemetryEventType.REPAIR_CANDIDATE_CREATED, tool_name="flush_dns_cache", domain="NETWORK")
    service.record_repair_event(session_id=sess_id, event_type=TelemetryEventType.REPAIR_AUTHORIZATION_REQUIRED, tool_name="flush_dns_cache", domain="NETWORK")
    service.record_repair_event(session_id=sess_id, event_type=TelemetryEventType.REPAIR_AUTHORIZED, tool_name="flush_dns_cache", domain="NETWORK")
    service.record_repair_event(session_id=sess_id, event_type=TelemetryEventType.REPAIR_EXECUTION_STARTED, tool_name="flush_dns_cache", domain="NETWORK")
    service.record_repair_event(session_id=sess_id, event_type=TelemetryEventType.REPAIR_VERIFICATION_SUCCEEDED, tool_name="flush_dns_cache", domain="NETWORK")
    service.record_repair_event(session_id=sess_id, event_type=TelemetryEventType.REPAIR_RESOLVED, tool_name="flush_dns_cache", domain="NETWORK")

    # Recovery lifecycle events
    service.record_recovery_event(session_id=sess_id, event_type=TelemetryEventType.CHECKPOINT_CREATED, domain="NETWORK")
    service.record_recovery_event(session_id=sess_id, event_type=TelemetryEventType.RECOVERY_RESUMED, domain="NETWORK")
    service.record_recovery_event(session_id=sess_id, event_type=TelemetryEventType.DUPLICATE_EXECUTION_BLOCKED, domain="NETWORK")

    # Dependency event
    service.record_dependency_event("ollama_gemma", available=True)
    service.record_dependency_event("voice_stt", available=False, details="No microphone found")

    analytics = TelemetryAnalytics(telemetry_service=service)
    return analytics, sess_id


def test_workflow_summary_aggregation(populated_analytics):
    analytics, sess_id = populated_analytics
    summary = analytics.get_workflow_summary(session_id=sess_id)

    assert summary["completed"] == 1
    assert summary["cancelled"] == 1
    assert summary["unresolved"] == 1
    assert summary["duration_stats"]["sample_size"] >= 3
    assert summary["duration_stats"]["average_ms"] > 0


def test_diagnostic_effectiveness_aggregation(populated_analytics):
    analytics, sess_id = populated_analytics
    diag = analytics.get_diagnostic_effectiveness(session_id=sess_id)

    assert diag["hypotheses_created"] == 1
    assert diag["hypotheses_supported"] == 1
    assert diag["hypotheses_contradicted"] == 1
    assert diag["hypotheses_reassessed"] == 1
    assert diag["contradiction_rate"] == 1.0
    assert diag["reassessment_rate"] == 1.0


def test_repair_lifecycle_aggregation(populated_analytics):
    analytics, sess_id = populated_analytics
    rep = analytics.get_repair_lifecycle_stats(session_id=sess_id)

    assert rep["candidates_created"] == 1
    assert rep["authorizations_required"] == 1
    assert rep["authorizations_approved"] == 1
    assert rep["executions_started"] == 1
    assert rep["verifications_succeeded"] == 1
    assert rep["resolved_repairs"] == 1


def test_recovery_summary_aggregation(populated_analytics):
    analytics, sess_id = populated_analytics
    rec = analytics.get_recovery_summary(session_id=sess_id)

    assert rec["checkpoints_created"] == 1
    assert rec["recovery_resumed"] == 1
    assert rec["duplicate_executions_blocked"] == 1


def test_domain_and_dependency_analytics(populated_analytics):
    analytics, sess_id = populated_analytics
    domains = analytics.get_domain_analytics(session_id=sess_id)
    assert "NETWORK" in domains
    assert domains["NETWORK"]["workflows"] >= 1

    deps = analytics.get_dependency_reliability_stats()
    assert "ollama_gemma" in deps
    assert deps["ollama_gemma"]["available_count"] == 1
    assert "voice_stt" in deps
    assert deps["voice_stt"]["unavailable_count"] == 1
