"""Tests for Phase 34 AI Evaluation Metrics.

Verifies calculation of diagnostic accuracy, evidence grounding rate, tool safety rates,
and summary report generation without metric fabrication.
"""

from agent.domain_models import TroubleshootingDomain
from agent.evaluation_models import (
    EvaluationOutcome,
    ScenarioEvaluationResult,
    EvaluationSummary,
)
from agent.evaluation_metrics import EvaluationMetricsCalculator


def test_metrics_calculator_empty():
    summary = EvaluationMetricsCalculator.calculate_summary([])
    assert summary.total_scenarios == 0
    assert summary.passed_scenarios == 0
    assert summary.failed_scenarios == 0
    assert summary.diagnostic_accuracy_rate == 0.0


def test_metrics_calculator_mixed_results():
    results = [
        ScenarioEvaluationResult(
            scenario_id="S1",
            domain=TroubleshootingDomain.NETWORK,
            outcome=EvaluationOutcome.PASS,
            domain_matched=True,
            hypotheses_grounded=True,
            unregistered_tools_count=0,
            forbidden_tools_count=0,
            contradiction_detected=False,
            hallucination_detected=False,
        ),
        ScenarioEvaluationResult(
            scenario_id="S2",
            domain=TroubleshootingDomain.STORAGE,
            outcome=EvaluationOutcome.PASS,
            domain_matched=True,
            hypotheses_grounded=True,
            unregistered_tools_count=0,
            forbidden_tools_count=0,
            contradiction_detected=False,
            hallucination_detected=False,
        ),
        ScenarioEvaluationResult(
            scenario_id="S3",
            domain=TroubleshootingDomain.SERVICES,
            outcome=EvaluationOutcome.FAIL,
            domain_matched=False,
            hypotheses_grounded=False,
            unregistered_tools_count=1,
            forbidden_tools_count=0,
            contradiction_detected=False,
            hallucination_detected=True,
        ),
    ]
    summary = EvaluationMetricsCalculator.calculate_summary(results)
    assert summary.total_scenarios == 3
    assert summary.passed_scenarios == 2
    assert summary.failed_scenarios == 1
    assert summary.unregistered_tool_rate > 0.0
    assert summary.hallucination_rate > 0.0
    assert summary.diagnostic_accuracy_rate == round(2 / 3, 4)


def test_metrics_calculator_perfect_run():
    results = [
        ScenarioEvaluationResult(
            scenario_id=f"S{i}",
            domain=TroubleshootingDomain.NETWORK,
            outcome=EvaluationOutcome.PASS,
            domain_matched=True,
            hypotheses_grounded=True,
            unregistered_tools_count=0,
            forbidden_tools_count=0,
            contradiction_detected=True,
            hallucination_detected=False,
        )
        for i in range(10)
    ]
    summary = EvaluationMetricsCalculator.calculate_summary(results)
    assert summary.total_scenarios == 10
    assert summary.passed_scenarios == 10
    assert summary.failed_scenarios == 0
    assert summary.diagnostic_accuracy_rate == 1.0
    assert summary.evidence_grounding_rate == 1.0
    assert summary.contradiction_detection_rate == 1.0
    assert summary.unregistered_tool_rate == 0.0
    assert summary.forbidden_tool_rate == 0.0
    assert summary.hallucination_rate == 0.0
