"""WinFix AI — Recovery Manager (Phase 31).

Coordinates production workflow recovery, state revalidation, idempotency guards,
checkpoint lifecycles, and sanitized operational event auditing.
Strictly adheres to:
  Never assume a previous repair executed successfully.
  Authoritative verification before resuming.
  Zero repair replay.
  Fail-closed invariant enforcement.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from agent.checkpoint_manager import CheckpointManager
from agent.idempotency import IdempotencyEngine, IdempotencyStatus
from agent.recovery_models import (
    Checkpoint,
    RecoveryEvent,
    RecoveryEventType,
    RecoveryResult,
    RecoveryState,
    ResumeAction,
    ResumeDecision,
)
from agent.resume_engine import ResumeEngine
from agent.verification_registry import VerificationRegistry, default_verification_registry

logger = logging.getLogger("winfix.RECOVERY_MANAGER")


class RecoveryManager:
    """Central manager for crash recovery, checkpointing, and resumable troubleshooting workflows."""

    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
        resume_engine: Optional[ResumeEngine] = None,
        idempotency_engine: Optional[IdempotencyEngine] = None,
        verification_registry: Optional[VerificationRegistry] = None,
    ) -> None:
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.verification_registry = verification_registry or default_verification_registry
        self.resume_engine = resume_engine or ResumeEngine(verification_registry=self.verification_registry)
        self.idempotency_engine = idempotency_engine or IdempotencyEngine()
        self._events: List[RecoveryEvent] = []

    def record_checkpoint(
        self,
        session_id: str,
        workflow_id: str,
        step_id: int,
        workflow_state: str,
        current_step_index: int,
        domain: str,
        evidence_references: Optional[List[str]] = None,
        hypothesis_references: Optional[List[str]] = None,
        diagnostic_decisions: Optional[List[Dict[str, Any]]] = None,
        repair_candidate: Optional[Dict[str, Any]] = None,
        authorization_state: Optional[Dict[str, Any]] = None,
        execution_state: Optional[Dict[str, Any]] = None,
        verification_state: Optional[Dict[str, Any]] = None,
    ) -> Checkpoint:
        """Create a persistent checkpoint and log the operational event."""
        chk = self.checkpoint_manager.create_checkpoint(
            session_id=session_id,
            workflow_id=workflow_id,
            step_id=step_id,
            workflow_state=workflow_state,
            current_step_index=current_step_index,
            domain=domain,
            evidence_references=evidence_references,
            hypothesis_references=hypothesis_references,
            diagnostic_decisions=diagnostic_decisions,
            repair_candidate=repair_candidate,
            authorization_state=authorization_state,
            execution_state=execution_state,
            verification_state=verification_state,
        )

        self._record_event(
            session_id=session_id,
            workflow_id=workflow_id,
            event_type=RecoveryEventType.CHECKPOINT_CREATED,
            state_before=workflow_state,
            state_after="CHECKPOINTED",
            details=f"Checkpoint {chk.checkpoint_id} created at step {step_id}",
        )
        return chk

    def recover_session(
        self,
        session_id: str,
        live_telemetry: Optional[Dict[str, Any]] = None,
    ) -> RecoveryResult:
        """Attempt conservative recovery of an interrupted workflow for a given session."""
        recovery_id = f"recov-{uuid.uuid4().hex[:10]}"
        checkpoint = self.checkpoint_manager.get_latest_checkpoint_for_session(session_id)

        if not checkpoint:
            decision = ResumeDecision(
                decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
                action=ResumeAction.FAILED,
                rationale=f"No checkpoints found for session '{session_id}'.",
            )
            return RecoveryResult(
                recovery_id=recovery_id,
                session_id=session_id,
                workflow_id="unknown",
                state=RecoveryState.FAILED,
                decision=decision,
                explanation="Recovery failed: session has no saved checkpoints.",
            )

        self._record_event(
            session_id=session_id,
            workflow_id=checkpoint.workflow_id,
            event_type=RecoveryEventType.RECOVERY_STARTED,
            state_before=checkpoint.workflow_state,
            state_after=RecoveryState.RECOVERING.value,
            details=f"Starting recovery for workflow {checkpoint.workflow_id}",
        )

        # Evaluate safe resumption through ResumeEngine
        decision = self.resume_engine.evaluate_resumption(checkpoint, live_telemetry)

        # Map decision to operational recovery state
        if decision.action == ResumeAction.RESUME:
            recov_state = RecoveryState.RESUMABLE
            self._record_event(
                session_id=session_id,
                workflow_id=checkpoint.workflow_id,
                event_type=RecoveryEventType.WORKFLOW_RESUMED,
                state_before=RecoveryState.RECOVERING.value,
                state_after=RecoveryState.RESUMABLE.value,
                details=f"Workflow deemed safely resumable at step {decision.safe_step_index}",
            )
        elif decision.action == ResumeAction.REVALIDATE:
            recov_state = RecoveryState.REVALIDATING
            self._record_event(
                session_id=session_id,
                workflow_id=checkpoint.workflow_id,
                event_type=RecoveryEventType.STATE_REVALIDATED,
                state_before=RecoveryState.RECOVERING.value,
                state_after=RecoveryState.REVALIDATING.value,
                details=f"Revalidation requested: {decision.rationale}",
            )
        elif decision.action == ResumeAction.AUTHORIZATION_REQUIRED:
            recov_state = RecoveryState.AUTHORIZATION_REQUIRED
            self._record_event(
                session_id=session_id,
                workflow_id=checkpoint.workflow_id,
                event_type=RecoveryEventType.AUTHORIZATION_INVALIDATED,
                state_before=RecoveryState.RECOVERING.value,
                state_after=RecoveryState.AUTHORIZATION_REQUIRED.value,
                details="Prior authorization invalidated; fresh confirmation required.",
            )
        elif decision.action == ResumeAction.CANCEL:
            recov_state = RecoveryState.CANCELLED
            self._record_event(
                session_id=session_id,
                workflow_id=checkpoint.workflow_id,
                event_type=RecoveryEventType.WORKFLOW_CANCELLED,
                state_before=RecoveryState.RECOVERING.value,
                state_after=RecoveryState.CANCELLED.value,
                details="Workflow recovery cancelled.",
            )
        else:
            recov_state = RecoveryState.UNRESOLVED
            self._record_event(
                session_id=session_id,
                workflow_id=checkpoint.workflow_id,
                event_type=RecoveryEventType.RECOVERY_FAILED,
                state_before=RecoveryState.RECOVERING.value,
                state_after=RecoveryState.UNRESOLVED.value,
                details=decision.rationale,
            )

        return RecoveryResult(
            recovery_id=recovery_id,
            session_id=session_id,
            workflow_id=checkpoint.workflow_id,
            state=recov_state,
            decision=decision,
            explanation=decision.rationale,
        )

    def cancel_recovery(self, session_id: str, workflow_id: str) -> RecoveryResult:
        """Explicitly cancel an active or recovering workflow."""
        recovery_id = f"recov-cancel-{uuid.uuid4().hex[:8]}"
        decision = ResumeDecision(
            decision_id=f"resdec-{uuid.uuid4().hex[:8]}",
            action=ResumeAction.CANCEL,
            rationale="User or policy explicitly cancelled workflow recovery.",
        )

        self._record_event(
            session_id=session_id,
            workflow_id=workflow_id,
            event_type=RecoveryEventType.WORKFLOW_CANCELLED,
            state_before="RECOVERING",
            state_after="CANCELLED",
            details="Workflow recovery cancelled explicitly.",
        )

        return RecoveryResult(
            recovery_id=recovery_id,
            session_id=session_id,
            workflow_id=workflow_id,
            state=RecoveryState.CANCELLED,
            decision=decision,
            explanation="Recovery was cancelled.",
        )

    def get_recovery_events(self, session_id: Optional[str] = None) -> List[RecoveryEvent]:
        """Return audit trail of recovery events, optionally filtered by session."""
        if session_id:
            return [e for e in self._events if e.session_id == session_id]
        return list(self._events)

    def _record_event(
        self,
        session_id: str,
        workflow_id: str,
        event_type: RecoveryEventType,
        state_before: str,
        state_after: str,
        tool_id: Optional[str] = None,
        details: str = "",
    ) -> RecoveryEvent:
        """Append a sanitized event to the recovery telemetry log and forward to telemetry service."""
        event = RecoveryEvent(
            event_id=f"ev-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            workflow_id=workflow_id,
            event_type=event_type,
            state_before=state_before,
            state_after=state_after,
            tool_id=tool_id,
            details=details,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._events.append(event)

        # Forward to Phase 32 Telemetry Service
        try:
            from production.telemetry import default_telemetry_service
            from production.telemetry_models import TelemetryEventType
            # Map RecoveryEventType to TelemetryEventType safely
            te_type_str = event_type.value if hasattr(event_type, "value") else str(event_type)
            if hasattr(TelemetryEventType, te_type_str):
                te_enum = getattr(TelemetryEventType, te_type_str)
                default_telemetry_service.record_recovery_event(
                    session_id=session_id,
                    event_type=te_enum,
                    outcome=state_after,
                    metadata={"workflow_id": workflow_id, "state_before": state_before, "details": details},
                )
        except Exception as ex:
            logger.debug(f"Telemetry forwarding exception (ignored): {ex}")

        return event

    def clear(self) -> None:
        """Clear all recovery state (used primarily in test setups)."""
        self.checkpoint_manager.clear()
        self.idempotency_engine.clear()
        self._events.clear()


default_recovery_manager = RecoveryManager()
