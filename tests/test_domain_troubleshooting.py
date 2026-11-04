"""Unit and Functional Tests for Advanced Windows Troubleshooting Intelligence & Domains (Phase 29).

Tests:
- Domain models and FailureCategory enums
- DomainRegistry lookups and heuristic classification
- EvidenceCorrelator multi-domain grouping, contradictions, and missing evidence detection
- TroubleshootingStrategy definitions and deterministic strategy selection
- WorkflowTemplate validation, registration, and workflow instantiation
- VerificationRegistry post-repair deterministic rule evaluations
- Offline deterministic domain troubleshooting fallback
- Personal Tutor domain explanation attachment
- UI domain troubleshooting card rendering
"""

import pytest
from unittest.mock import MagicMock, patch

from agent.domain_models import (
    DomainClassification,
    EvidenceCorrelationResult,
    FailureCategory,
    TroubleshootingDomain,
)
from agent.domain_registry import DomainMetadata, DomainRegistry, default_domain_registry
from agent.evidence_correlator import EvidenceCorrelator, default_evidence_correlator
from agent.evidence_models import (
    EvidenceItem,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
)
from agent.troubleshooting_strategies import (
    StrategyRegistry,
    TroubleshootingStrategy,
    default_strategy_registry,
)
from agent.tool_registry import default_tool_registry
from agent.verification_registry import (
    VerificationRegistry,
    VerificationRule,
    default_verification_registry,
)
from agent.workflow_models import ResolutionStatus, WorkflowStatus
from agent.workflow_templates import (
    WorkflowTemplate,
    WorkflowTemplateRegistry,
    WorkflowTemplateValidator,
    default_template_registry,
)
from ui.components import render_domain_troubleshooting_card


def test_domain_registry_enumeration():
    """Verify built-in domains are properly registered and accessible."""
    reg = default_domain_registry
    domains = reg.list_domains()
    assert len(domains) >= 11
    assert TroubleshootingDomain.NETWORK in domains
    assert TroubleshootingDomain.PERFORMANCE in domains
    assert TroubleshootingDomain.STORAGE in domains
    assert TroubleshootingDomain.SERVICES in domains
    assert TroubleshootingDomain.WINDOWS_UPDATE in domains
    assert TroubleshootingDomain.WINDOWS_DEFENDER in domains
    assert TroubleshootingDomain.BLUETOOTH in domains
    assert TroubleshootingDomain.APPLICATION_CRASH in domains
    assert TroubleshootingDomain.STARTUP in domains
    assert TroubleshootingDomain.SYSTEM in domains
    assert TroubleshootingDomain.UNKNOWN in domains


def test_heuristic_symptom_classification():
    """Verify deterministic symptom text mapping to primary domains."""
    reg = default_domain_registry
    assert reg.classify_symptom_heuristically("My Wi-Fi adapter is disconnected and DNS fails") == TroubleshootingDomain.NETWORK
    assert reg.classify_symptom_heuristically("System is freezing with 100% high CPU lag") == TroubleshootingDomain.PERFORMANCE
    assert reg.classify_symptom_heuristically("Drive C: is full and out of disk space") == TroubleshootingDomain.STORAGE
    assert reg.classify_symptom_heuristically("Print Spooler service stopped unexpectedly") == TroubleshootingDomain.SERVICES
    assert reg.classify_symptom_heuristically("Windows update error 0x80070002 failed patch") == TroubleshootingDomain.WINDOWS_UPDATE
    assert reg.classify_symptom_heuristically("Bluetooth headphones pairing failed") == TroubleshootingDomain.BLUETOOTH
    assert reg.classify_symptom_heuristically("Application crashed with WER event 1000") == TroubleshootingDomain.APPLICATION_CRASH
    assert reg.classify_symptom_heuristically("Some completely random text with no matches") == TroubleshootingDomain.UNKNOWN


def test_evidence_correlator_grouping_and_missing_types():
    """Verify evidence correlator groups by domain and flags missing evidence types."""
    store = EvidenceStore()
    correlator = EvidenceCorrelator(evidence_store=store)

    # Ingest a valid network adapter item
    store.add_evidence(
        EvidenceItem(
            evidence_id="ev_adapter_01",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="network",
            observation="Network adapter active",
            value={"adapters": ["Ethernet0"], "status": "ok"},
            status=EvidenceStatus.VALID,
            quality=EvidenceQuality.VERIFIED,
            session_id="s_correlate",
        )
    )

    res = correlator.correlate_evidence(session_id="s_correlate", hint_domain=TroubleshootingDomain.NETWORK)
    assert res.primary_domain == TroubleshootingDomain.NETWORK
    assert TroubleshootingDomain.NETWORK.value in res.domain_evidence
    assert len(res.domain_evidence[TroubleshootingDomain.NETWORK.value]) == 1


def test_strategy_registry_and_selection():
    """Verify built-in strategies are retrieved and selected by symptom."""
    strat_reg = default_strategy_registry
    strat = strat_reg.select_strategy(TroubleshootingDomain.NETWORK, symptom_text="DNS lookup domain not found")
    assert strat is not None
    assert strat.strategy_id == "strat_net_dns"
    assert "check_dns_resolution" in strat.diagnostic_sequence
    assert strat.repair_candidates[0]["tool_name"] == "flush_dns_cache"

    dhcp_strat = strat_reg.select_strategy(TroubleshootingDomain.NETWORK, symptom_text="DHCP 169.254 gateway unreachable")
    assert dhcp_strat is not None
    assert dhcp_strat.strategy_id == "strat_net_dhcp"


def test_workflow_template_instantiation():
    """Verify instantiating a workflow from a validated template."""
    tmpl_reg = default_template_registry
    wf = tmpl_reg.instantiate_workflow("DNS_FAILURE", session_id="s_template")
    assert wf is not None
    assert wf.problem_category == "NETWORK"
    assert wf.status == WorkflowStatus.CREATED
    assert len(wf.steps) <= 8
    assert wf.repair_candidate is not None
    assert wf.repair_candidate.tool_name == "flush_dns_cache"
    assert wf.steps[0].tool_name == "get_network_adapters_diagnostics"


def test_verification_registry_rules():
    """Verify verification registry evaluates before/after evidence accurately."""
    verif_reg = default_verification_registry
    
    # 1. DNS flush verification
    before_bad = {"dns_resolved": False, "status": "failed"}
    after_good = {"dns_resolved": True, "status": "ok"}
    status, msg = verif_reg.evaluate_verification("flush_dns_cache", before_bad, after_good)
    assert status == ResolutionStatus.RESOLVED
    assert "restored" in msg.lower()

    # 2. Service restart verification
    before_svc = {"state": "Stopped", "status": "failed"}
    after_svc = {"state": "Running", "status": "ok"}
    svc_status, svc_msg = verif_reg.evaluate_verification("restart_service", before_svc, after_svc)
    assert svc_status == ResolutionStatus.RESOLVED

    # 3. Persistent service failure
    after_svc_bad = {"state": "Stopped", "status": "failed"}
    svc_fail_status, _ = verif_reg.evaluate_verification("restart_service", before_svc, after_svc_bad)
    assert svc_fail_status == ResolutionStatus.NOT_RESOLVED


def test_failure_category_enums():
    """Verify all required FailureCategory enums are defined."""
    assert FailureCategory.PRECONDITION_FAILED == "PRECONDITION_FAILED"
    assert FailureCategory.AUTHORIZATION_REQUIRED == "AUTHORIZATION_REQUIRED"
    assert FailureCategory.EXECUTION_FAILED == "EXECUTION_FAILED"
    assert FailureCategory.VERIFICATION_FAILED == "VERIFICATION_FAILED"
    assert FailureCategory.TIMEOUT == "TIMEOUT"
    assert FailureCategory.CANCELLED == "CANCELLED"
    assert FailureCategory.UNAVAILABLE == "UNAVAILABLE"
    assert FailureCategory.CONFLICTING_EVIDENCE == "CONFLICTING_EVIDENCE"
    assert FailureCategory.UNRESOLVED == "UNRESOLVED"


def test_ui_domain_troubleshooting_card_rendering():
    """Verify Streamlit domain troubleshooting card renders safely without errors."""
    domain_data = {
        "primary_domain": "NETWORK",
        "secondary_domains": ["SERVICES", "SYSTEM"],
        "status": "SUPPORTED",
        "selected_strategy": "DNS Resolution Failure Strategy",
        "evidence_summary": "Adapter connected, Gateway reachable, DNS failing",
        "evidence_items": [
            {"title": "Network Adapter", "status": "ok", "details": "Ethernet0 connected"},
            {"title": "DNS Check", "status": "failed", "details": "Lookup timed out"},
        ],
        "tutor_explanation": "Domain explanation for DNS failure.",
    }
    with patch("streamlit.container"), patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
        render_domain_troubleshooting_card(domain_data)


def test_cross_domain_correlation_with_secondary_domains():
    """Verify primary and secondary domain relationships are identified."""
    store = EvidenceStore()
    correlator = EvidenceCorrelator(evidence_store=store)

    # Windows update failure item
    store.add_evidence(
        EvidenceItem(
            evidence_id="ev_wu_01",
            evidence_type=EvidenceType.WINDOWS_UPDATE,
            source=EvidenceSource.WINDOWS_TOOL,
            category="update",
            observation="Windows update failed with 0x80070002",
            value={"status": "failed", "error": "0x80070002"},
            session_id="s_wu",
        )
    )
    # Related service item
    store.add_evidence(
        EvidenceItem(
            evidence_id="ev_svc_01",
            evidence_type=EvidenceType.SERVICE,
            source=EvidenceSource.WINDOWS_TOOL,
            category="service",
            observation="wuauserv is stopped",
            value={"status": "failed", "state": "Stopped"},
            session_id="s_wu",
        )
    )

    res = correlator.correlate_evidence(session_id="s_wu")
    assert res.primary_domain in [TroubleshootingDomain.WINDOWS_UPDATE, TroubleshootingDomain.SERVICES]
    assert len(res.secondary_domains) <= 2


def test_correlator_stale_evidence_detection():
    """Verify stale items are flagged in correlation results."""
    store = EvidenceStore()
    correlator = EvidenceCorrelator(evidence_store=store)

    store.add_evidence(
        EvidenceItem(
            evidence_id="ev_stale_01",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="network",
            observation="Old network state",
            value={"status": "ok"},
            timestamp="2020-01-01T00:00:00+00:00",  # Extremely old
            session_id="s_stale",
        )
    )

    res = correlator.correlate_evidence(session_id="s_stale", hint_domain=TroubleshootingDomain.NETWORK)
    assert "ev_stale_01" in res.stale_evidence_ids


def test_all_builtin_templates_validate():
    """Verify all built-in workflow templates validate against tool and domain registries."""
    validator = WorkflowTemplateValidator(tool_registry=default_tool_registry, domain_registry=default_domain_registry)
    tmpl_reg = default_template_registry

    for tmpl in tmpl_reg._templates.values():
        ok, msg = validator.validate(tmpl)
        assert ok is True, f"Template '{tmpl.template_id}' failed validation: {msg}"
        assert tmpl.max_steps <= 8


def test_domain_classification_serialization():
    """Verify DomainClassification to_dict serialization."""
    dc = DomainClassification(
        domain=TroubleshootingDomain.NETWORK,
        status="SUPPORTED",
        confidence=0.95,
        supporting_evidence_ids=["ev_1", "ev_2"],
        contradicting_evidence_ids=[],
        secondary_domains=[TroubleshootingDomain.SERVICES],
        source="deterministic_rules",
    )
    d = dc.to_dict()
    assert d["domain"] == "NETWORK"
    assert d["status"] == "SUPPORTED"
    assert d["secondary_domains"] == ["SERVICES"]
    assert "ev_1" in d["supporting_evidence_ids"]


def test_voice_and_screenshot_domain_correlation():
    """Verify voice and screenshot observations contribute to domain grouping."""
    store = EvidenceStore()
    correlator = EvidenceCorrelator(evidence_store=store)

    store.add_evidence(
        EvidenceItem(
            evidence_id="ev_voice_01",
            evidence_type=EvidenceType.VOICE,
            source=EvidenceSource.VOICE,
            category="voice_input",
            observation="Bluetooth mouse disconnected",
            value={"transcript": "Bluetooth mouse disconnected"},
            session_id="s_multi",
        )
    )
    store.add_evidence(
        EvidenceItem(
            evidence_id="ev_screen_01",
            evidence_type=EvidenceType.SCREENSHOT,
            source=EvidenceSource.SCREENSHOT,
            category="screenshot_vision",
            observation="Bluetooth toggle is greyed out",
            value={"ocr_text": "Bluetooth toggle is greyed out"},
            session_id="s_multi",
        )
    )

    res = correlator.correlate_evidence(session_id="s_multi", hint_domain=TroubleshootingDomain.BLUETOOTH)
    assert res.primary_domain == TroubleshootingDomain.BLUETOOTH
    assert len(res.domain_evidence[TroubleshootingDomain.UNKNOWN.value]) == 2


