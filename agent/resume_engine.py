"""WinFix AI — Resume Engine & Resumption Logic (Phase 31).

Evaluates checkpoints upon session recovery and determines safe, deterministic resumption actions.
Strictly adheres to:
  Never assume a previous repair executed successfully.
  Incomplete / ambiguous repair -> Authoritative verification first.
  Reauthorization is strictly required if repair state remains unresolved.
  Zero repair loops.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from agent.domain_models import TroubleshootingDomain
from agent.domain_registry import DomainRegistry
from agent.recovery_models import Checkpoint, ResumeAction, ResumeDecision
from agent.verification_registry import VerificationRegistry
from agent.workflow_models import WorkflowStatus

logger = logging.getLogger("winfix.RESUME_ENGINE")


class ResumeEngine:
    """Evaluates checkpoint state and produces safe, deterministic resumption decisions."""

    def __init__(self, verification_registry: Optional[VerificationRegistry] = None) -> None:
        self.verification_registry = verification_registry or VerificationRegistry()

    def evaluate_resumption(
        self,
        checkpoint: Optional[Checkpoint],
        live_telemetry: Optional[Dict[str, Any]] = None,
    ) -> ResumeDecision:
        """Analyze checkpoint integrity, state, and telemetry to generate a safe ResumeDecision."""
        if checkpoint is None:
            return ResumeDecision(
                decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
                action=ResumeAction.FAILED,
                rationale="No valid checkpoint available to resume.",
            )

        # 1. Terminal workflow states cannot be resumed
        terminal_states = [
            WorkflowStatus.RESOLVED.value,
            WorkflowStatus.FAILED.value,
            WorkflowStatus.CANCELLED.value,
            WorkflowStatus.UNRESOLVED.value,
            WorkflowStatus.EXPIRED.value,
        ]
        if checkpoint.workflow_state in terminal_states:
            return ResumeDecision(
                decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
                action=ResumeAction.CANCEL if checkpoint.workflow_state == WorkflowStatus.CANCELLED.value else ResumeAction.UNRESOLVED,
                rationale=f"Workflow is in terminal state '{checkpoint.workflow_state}' and cannot be resumed.",
                safe_step_index=checkpoint.current_step_index,
            )

        # 2. Stale Checkpoint Handling (TTL expired)
        if checkpoint.is_stale(max_age_seconds=1800):
            return ResumeDecision(
                decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
                action=ResumeAction.REVALIDATE,
                rationale="Checkpoint is stale (> 30 minutes old). Factual telemetry must be revalidated.",
                safe_step_index=0,
                requires_reauthorization=True,
            )

        # 3. Interrupted Repair Execution or Verification
        # CRITICAL SAFETY INVARIANT: If interrupted in REPAIRING, VERIFYING, or WAITING_FOR_CONFIRMATION,
        # we NEVER assume repair succeeded or failed. We trigger authoritative REVALIDATION.
        interrupted_repair_states = [
            WorkflowStatus.REPAIRING.value,
            WorkflowStatus.VERIFYING.value,
            WorkflowStatus.WAITING_FOR_CONFIRMATION.value,
        ]
        if checkpoint.workflow_state in interrupted_repair_states:
            repair_cand = checkpoint.repair_candidate or {}
            repair_tool = repair_cand.get("tool_name") if isinstance(repair_cand, dict) else str(repair_cand)

            # Determine verification tool for the repair
            verif_rule = self.verification_registry.get_rule_for_tool(repair_tool) if repair_tool else None
            verif_tool = verif_rule.verification_tool if verif_rule else "check_dns_resolution"

            # If live revalidation telemetry was provided, evaluate if issue is resolved
            if live_telemetry and repair_tool:
                res_status, expl = self.verification_registry.evaluate_verification(
                    repair_tool=repair_tool,
                    before_state=checkpoint.execution_state or {},
                    after_state=live_telemetry,
                )
                if res_status.value == "RESOLVED":
                    return ResumeDecision(
                        decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
                        action=ResumeAction.RESUME,
                        rationale=f"System revalidation confirmed issue resolved: {expl}",
                        safe_step_index=checkpoint.current_step_index + 1,
                        target_tool=verif_tool,
                        requires_reauthorization=False,
                        revalidation_evidence=live_telemetry,
                    )

            # Otherwise, demand state revalidation and invalidate prior authorization
            return ResumeDecision(
                decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
                action=ResumeAction.REVALIDATE,
                rationale=f"Workflow was interrupted during/after repair '{repair_tool}'. Revalidating Windows state via '{verif_tool}'.",
                safe_step_index=checkpoint.current_step_index,
                target_tool=verif_tool,
                requires_reauthorization=True,
            )

        # 4. Interrupted during DIAGNOSING or VERIFY_PRECONDITION
        if checkpoint.workflow_state in (WorkflowStatus.DIAGNOSING.value, WorkflowStatus.VERIFY_PRECONDITION.value):
            return ResumeDecision(
                decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
                action=ResumeAction.RESUME,
                rationale=f"Resuming diagnostic sequence at step {checkpoint.current_step_index}.",
                safe_step_index=checkpoint.current_step_index,
                requires_reauthorization=False,
            )

        # Default safe fallback
        return ResumeDecision(
            decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
            action=ResumeAction.REVALIDATE,
            rationale=f"Workflow in state '{checkpoint.workflow_state}'; revalidating system telemetry.",
            safe_step_index=0,
            requires_reauthorization=True,
        )
