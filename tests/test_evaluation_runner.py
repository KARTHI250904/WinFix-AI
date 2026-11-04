"""Tests for Phase 34 AI Evaluation Runner and Report Generator.

Verifies end-to-end suite coordination, report formatting, and metric aggregation.
"""

from agent.evaluation_dataset import get_evaluation_dataset
from agent.evaluation_runner import EvaluationRunner
from agent.evaluation_report import EvaluationReportGenerator


def test_evaluation_runner_run_suite():
    runner = EvaluationRunner()
    run_output = runner.run_suite()
    
    assert "summary" in run_output
    assert "results" in run_output
    assert run_output["total_count"] >= 50
    assert run_output["failed_count"] == 0
    assert run_output["summary"]["unregistered_tool_rate"] == 0.0
    assert run_output["summary"]["forbidden_tool_rate"] == 0.0


def test_evaluation_report_generator_markdown():
    runner = EvaluationRunner()
    run_output = runner.run_suite()
    
    md = EvaluationReportGenerator.generate_markdown(run_output["summary"], run_output["results"])
    assert "PHASE 34 AI QUALITY & DIAGNOSTIC EVALUATION REPORT" in md
    assert "LLM != Windows Shell" in md
    assert "Unregistered Tool Rate" in md
    assert "| NET-01 |" in md
