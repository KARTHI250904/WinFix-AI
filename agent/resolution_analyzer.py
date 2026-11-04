"""WinFix AI — Deterministic Resolution Analyzer (Phase 30).

Provides authoritative, deterministic evaluation of troubleshooting outcomes, strictly separating
tool execution from verification results.
Strictly adheres to:
  Execution Success != Verification Success
  Verification determines resolution
  No repair loops or fake resolutions
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from agent.adaptive_models import (
    BeforeAfterComparison,
    ResolutionAnalysis,
    ResolutionOutcome,
)
from agent.domain_models import FailureCategory, TroubleshootingDomain
from agent.workflow_models import ResolutionStatus

logger = logging.getLogger("winfix.RESOLUTION_ANALYZER")


class ResolutionAnalyzer:
    """Authoritative evaluator of workflow outcomes."""

    @staticmethod
    def analyze_resolution(
        session_id: str,
        workflow_id: str,
        primary_domain: TroubleshootingDomain,
        execution_succeeded: bool,
        verification_succeeded: bool,
        before_after: Optional[BeforeAfterComparison] = None,
        is_cancelled: bool = False,
        is_timeout: bool = False,
        is_unavailable: bool = False,
        has_contradictions: bool = False,
        remaining_symptoms: Optional[List[str]] = None,
        explanation: str = "",
    ) -> ResolutionAnalysis:
        """Deterministically determine the final troubleshooting resolution."""
        symptoms = list(remaining_symptoms or [])

        if is_cancelled:
            outcome = ResolutionOutcome.CANCELLED
            res_status = ResolutionStatus.NOT_RESOLVED
            failure_cat = FailureCategory.CANCELLED
            msg = explanation or "Troubleshooting was cancelled by user or safety policy."
        elif is_timeout:
            outcome = ResolutionOutcome.TIMEOUT
            res_status = ResolutionStatus.NOT_RESOLVED
            failure_cat = FailureCategory.TIMEOUT
            msg = explanation or "Diagnostic or repair step timed out."
        elif is_unavailable:
            outcome = ResolutionOutcome.UNAVAILABLE
            res_status = ResolutionStatus.NOT_RESOLVED
            failure_cat = FailureCategory.UNAVAILABLE
            msg = explanation or "Required diagnostic or repair tool is unavailable in this environment."
        elif has_contradictions:
            outcome = ResolutionOutcome.CONTRADICTORY
            res_status = ResolutionStatus.NOT_RESOLVED
            failure_cat = FailureCategory.CONFLICTING_EVIDENCE
            msg = explanation or "Contradictory evidence detected; cannot safely resolve."
        elif execution_succeeded and verification_succeeded:
            outcome = ResolutionOutcome.VERIFICATION_SUCCEEDED
            res_status = ResolutionStatus.RESOLVED
            failure_cat = None
            msg = explanation or "Repair executed and deterministic verification succeeded."
        elif execution_succeeded and not verification_succeeded:
            outcome = ResolutionOutcome.VERIFICATION_FAILED
            res_status = ResolutionStatus.NOT_RESOLVED
            failure_cat = FailureCategory.VERIFICATION_FAILED
            msg = explanation or "Repair executed, but post-repair verification failed. State not resolved."
        elif not execution_succeeded:
            outcome = ResolutionOutcome.UNRESOLVED
            res_status = ResolutionStatus.NOT_RESOLVED
            failure_cat = FailureCategory.EXECUTION_FAILED
            msg = explanation or "Tool execution failed during repair."
        else:
            outcome = ResolutionOutcome.UNRESOLVED
            res_status = ResolutionStatus.NOT_RESOLVED
            failure_cat = FailureCategory.UNRESOLVED
            msg = explanation or "Troubleshooting completed with inconclusive outcome."

        analysis = ResolutionAnalysis(
            session_id=session_id,
            workflow_id=workflow_id,
            primary_domain=primary_domain,
            execution_succeeded=execution_succeeded,
            verification_succeeded=verification_succeeded,
            outcome=outcome,
            resolution_status=res_status,
            failure_category=failure_cat,
            before_after=before_after,
            explanation=msg,
            remaining_symptoms=symptoms,
        )
        return analysis
