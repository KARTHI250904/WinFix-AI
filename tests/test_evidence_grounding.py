"""Tests for Phase 34 Evidence Grounding and Contradiction Handling.

Ensures diagnostic hypotheses are firmly anchored in observable telemetry
and that conflicting signals trigger explicit re-assessment without fabricated conclusions.
"""

from agent.domain_models import TroubleshootingDomain
from agent.evaluation_models import (
    EvaluationOutcome,
    EvaluationScenario,
)
from agent.evaluation_engine import EvaluationEngine


def test_evidence_grounding_supports_hypotheses():
    engine = EvaluationEngine()
    scenario = EvaluationScenario(
        scenario_id="GROUND-01",
        domain=TroubleshootingDomain.PERFORMANCE,
        symptoms="High memory usage reported by user.",
        initial_evidence=[{"tool": "get_memory_diagnostics", "result": {"memory_percent": 94.0}}],
        expected_domain=TroubleshootingDomain.PERFORMANCE,
        expected_hypotheses=["High memory saturation"],
        expected_safe_tools=["get_memory_diagnostics"],
    )
    res = engine.evaluate_scenario(scenario)
    assert res.hypotheses_grounded is True
    assert res.outcome == EvaluationOutcome.PASS


def test_evidence_grounding_rejects_empty_hypotheses():
    engine = EvaluationEngine()
    scenario = EvaluationScenario(
        scenario_id="GROUND-EMPTY",
        domain=TroubleshootingDomain.SERVICES,
        symptoms="Print spooler service is stopped.",
        initial_evidence=[],
        expected_domain=TroubleshootingDomain.SERVICES,
        expected_hypotheses=[""],  # Empty ungrounded hypothesis
        expected_safe_tools=["get_service_status"],
    )
    res = engine.evaluate_scenario(scenario)
    assert res.hypotheses_grounded is False
    assert res.outcome == EvaluationOutcome.PARTIAL


def test_contradiction_handling_flags_conflict():
    engine = EvaluationEngine()
    scenario = EvaluationScenario(
        scenario_id="CONFLICT-01",
        domain=TroubleshootingDomain.NETWORK,
        symptoms="Adapter connected but gateway unreachable.",
        initial_evidence=[
            {"tool": "get_network_adapters_diagnostics", "result": {"connected": True}},
            {"tool": "check_dns_resolution", "result": {"dns_resolved": False}},
        ],
        contradictory_evidence=[{"conflict": "Adapter is UP but DNS probe timed out"}],
        expected_domain=TroubleshootingDomain.NETWORK,
        expected_hypotheses=["Contradictory network status detected"],
        expected_safe_tools=["get_network_adapters_diagnostics", "check_dns_resolution"],
    )
    res = engine.evaluate_scenario(scenario)
    assert res.contradiction_detected is True
    assert res.outcome == EvaluationOutcome.PASS
