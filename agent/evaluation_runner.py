"""WinFix AI — AI Quality Evaluation Runner (Phase 34).

Coordinates end-to-end evaluation execution, metrics collection, and summary generation.
"""

from typing import List, Optional, Dict, Any
from agent.evaluation_models import (
    EvaluationScenario,
    ScenarioEvaluationResult,
    EvaluationSummary,
)
from agent.evaluation_dataset import get_evaluation_dataset
from agent.evaluation_engine import EvaluationEngine
from agent.evaluation_metrics import EvaluationMetricsCalculator


class EvaluationRunner:
    """Orchestrates test matrix runs and computes comprehensive quality metrics."""

    def __init__(self, engine: Optional[EvaluationEngine] = None) -> None:
        self._engine = engine or EvaluationEngine()
        self._metrics_calculator = EvaluationMetricsCalculator()

    def run_suite(self, scenarios: Optional[List[EvaluationScenario]] = None) -> Dict[str, Any]:
        """Run all evaluation scenarios and return structured results and summary metrics."""
        dataset = scenarios if scenarios is not None else get_evaluation_dataset()
        results: List[ScenarioEvaluationResult] = self._engine.evaluate_all(dataset)
        summary: EvaluationSummary = self._metrics_calculator.calculate_summary(results)

        return {
            "summary": summary.to_dict(),
            "results": [r.to_dict() for r in results],
            "total_count": len(results),
            "passed_count": summary.passed_scenarios,
            "failed_count": summary.failed_scenarios,
        }
