"""Tests for Phase 34 AI Evaluation Models.

Verifies immutability, serialization, outcome classifications, and dataclass integrity.
"""

import pytest
from agent.domain_models import TroubleshootingDomain
from agent.evaluation_models import (
    EvaluationOutcome,
    EvaluationScenario,
    ScenarioEvaluationResult,
    EvaluationSummary,
)


def test_evaluation_outcome_enum_values():
    assert EvaluationOutcome.PASS == "PASS"
    assert EvaluationOutcome.FAIL == "FAIL"
    assert EvaluationOutcome.PARTIAL == "PARTIAL"
    assert EvaluationOutcome.UNRESOLVED == "UNRESOLVED"
    assert EvaluationOutcome.NOT_APPLICABLE == "NOT_APPLICABLE"


def test_evaluation_scenario_immutability():
    scenario = EvaluationScenario(
        scenario_id="NET-TEST",
        domain=TroubleshootingDomain.NETWORK,
        symptoms="Cannot ping DNS",
        expected_domain=TroubleshootingDomain.NETWORK,
        expected_hypotheses=["DNS Failure"],
        expected_safe_tools=["check_dns_resolution"],
        forbidden_tools=["powershell"],
    )
    assert scenario.scenario_id == "NET-TEST"
    assert scenario.domain == TroubleshootingDomain.NETWORK
    
    with pytest.raises(Exception):
        scenario.scenario_id = "MUTATED"  # type: ignore


def test_evaluation_scenario_to_dict():
    scenario = EvaluationScenario(
        scenario_id="PERF-TEST",
        domain=TroubleshootingDomain.PERFORMANCE,
        symptoms="High CPU",
        expected_domain=TroubleshootingDomain.PERFORMANCE,
        expected_hypotheses=["High CPU spike"],
    )
    d = scenario.to_dict()
    assert d["scenario_id"] == "PERF-TEST"
    assert d["domain"] == "PERFORMANCE"
    assert d["expected_domain"] == "PERFORMANCE"
    assert "High CPU spike" in d["expected_hypotheses"]


def test_scenario_evaluation_result_serialization():
    result = ScenarioEvaluationResult(
        scenario_id="TEST-01",
        domain=TroubleshootingDomain.STORAGE,
        outcome=EvaluationOutcome.PASS,
        domain_matched=True,
        hypotheses_grounded=True,
        unregistered_tools_count=0,
        forbidden_tools_count=0,
        contradiction_detected=False,
        hallucination_detected=False,
        details="Success",
        duration_ms=15,
    )
    d = result.to_dict()
    assert d["scenario_id"] == "TEST-01"
    assert d["outcome"] == "PASS"
    assert d["unregistered_tools_count"] == 0
    assert d["forbidden_tools_count"] == 0


def test_evaluation_summary_fields():
    summary = EvaluationSummary(
        total_scenarios=10,
        passed_scenarios=10,
        failed_scenarios=0,
        partial_scenarios=0,
        diagnostic_accuracy_rate=1.0,
        evidence_grounding_rate=1.0,
        contradiction_detection_rate=1.0,
        unsupported_hypothesis_rate=0.0,
        tool_recommendation_accuracy_rate=1.0,
        unregistered_tool_rate=0.0,
        forbidden_tool_rate=0.0,
        hallucination_rate=0.0,
        multimodal_consistency_rate=1.0,
        fallback_success_rate=1.0,
        tutor_compliance_rate=1.0,
        autopilot_safety_rate=1.0,
        knowledge_retrieval_rate=1.0,
        determinism_rate=1.0,
    )
    d = summary.to_dict()
    assert d["total_scenarios"] == 10
    assert d["passed_scenarios"] == 10
    assert d["unregistered_tool_rate"] == 0.0
    assert d["forbidden_tool_rate"] == 0.0
    assert "timestamp_utc" in d
