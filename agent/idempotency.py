"""WinFix AI — Idempotency & Repair Replay Protection (Phase 31).

Provides cryptographic hashing, duplicate execution detection, authorization binding verification,
and strict repair replay prevention.
Strictly adheres to:
  Never assume a previous repair executed successfully.
  Ambiguous execution -> Revalidate Windows state -> Authoritative Verification.
  Replay of unauthorized or mutated operations is strictly prohibited.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from agent.recovery_models import ExecutionRecord

logger = logging.getLogger("winfix.IDEMPOTENCY")


class IdempotencyStatus(str, Enum):
    """Evaluation status for an execution attempt."""

    UNIQUE = "UNIQUE"
    DUPLICATE_SUCCEEDED = "DUPLICATE_SUCCEEDED"
    DUPLICATE_IN_PROGRESS = "DUPLICATE_IN_PROGRESS"
    AMBIGUOUS_INTERRUPTED = "AMBIGUOUS_INTERRUPTED"
    DIFFERENT_ARGUMENTS = "DIFFERENT_ARGUMENTS"
    AUTHORIZATION_MISMATCH = "AUTHORIZATION_MISMATCH"


class IdempotencyEngine:
    """Manages execution records, validates authorization bindings, and prevents duplicate/replay operations."""

    def __init__(self) -> None:
        # In-memory execution registry keyed by execution_id
        self._records: Dict[str, ExecutionRecord] = {}

    @staticmethod
    def compute_argument_hash(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """Compute stable SHA-256 hash of normalized tool name and arguments."""
        args = arguments or {}
        # Deterministic canonical JSON serialization
        canonical_args = json.dumps(args, sort_keys=True, separators=(",", ":"))
        payload = f"tool:{tool_name}|args:{canonical_args}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_authorization_hash(
        session_id: str,
        workflow_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        confirmation_token: str = "",
    ) -> str:
        """Compute SHA-256 hash binding authorization to exact session, workflow, tool, and arguments."""
        arg_hash = IdempotencyEngine.compute_argument_hash(tool_name, arguments)
        payload = f"sess:{session_id}|wf:{workflow_id}|tool:{tool_name}|arghash:{arg_hash}|token:{confirmation_token}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_execution_start(
        self,
        session_id: str,
        workflow_id: str,
        step_id: int,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        confirmation_token: Optional[str] = None,
    ) -> ExecutionRecord:
        """Record the initiation of a tool execution attempt."""
        exec_id = f"exec-{uuid.uuid4().hex[:12]}"
        arg_hash = self.compute_argument_hash(tool_name, arguments)
        auth_hash = (
            self.compute_authorization_hash(session_id, workflow_id, tool_name, arguments, confirmation_token)
            if confirmation_token
            else None
        )

        record = ExecutionRecord(
            execution_id=exec_id,
            session_id=session_id,
            workflow_id=workflow_id,
            step_id=step_id,
            tool_name=tool_name,
            argument_hash=arg_hash,
            authorization_hash=auth_hash,
            started_at=datetime.now(timezone.utc).isoformat(),
            execution_status="STARTED",
        )
        self._records[exec_id] = record
        return record

    def record_execution_complete(
        self,
        execution_id: str,
        success: bool,
        verification_status: Optional[str] = None,
    ) -> Optional[ExecutionRecord]:
        """Record the completion of a tool execution."""
        rec = self._records.get(execution_id)
        if not rec:
            return None

        status = "SUCCEEDED" if success else "FAILED"
        completed_rec = ExecutionRecord(
            execution_id=rec.execution_id,
            session_id=rec.session_id,
            workflow_id=rec.workflow_id,
            step_id=rec.step_id,
            tool_name=rec.tool_name,
            argument_hash=rec.argument_hash,
            authorization_hash=rec.authorization_hash,
            started_at=rec.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            execution_status=status,
            verification_status=verification_status,
        )
        self._records[execution_id] = completed_rec
        return completed_rec

    def evaluate_idempotency(
        self,
        session_id: str,
        workflow_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        confirmation_token: Optional[str] = None,
    ) -> Tuple[IdempotencyStatus, Optional[ExecutionRecord]]:
        """Evaluate an execution request against prior execution records.
        
        Distinguishes:
          - Case A: Same tool, session, workflow, args -> Duplicate
          - Case B: Same tool, session, workflow, different args -> Different arguments
          - Case C: Same tool, different session -> Isolated
          - Case D: Interrupted in-progress execution -> Ambiguous / Replay blocked
        """
        target_arg_hash = self.compute_argument_hash(tool_name, arguments)
        target_auth_hash = (
            self.compute_authorization_hash(session_id, workflow_id, tool_name, arguments, confirmation_token)
            if confirmation_token
            else None
        )

        for rec in self._records.values():
            # Cross-session isolation: ignore records from other sessions
            if rec.session_id != session_id:
                continue

            # Check matching workflow and tool
            if rec.workflow_id == workflow_id and rec.tool_name == tool_name:
                if rec.argument_hash == target_arg_hash:
                    # Case D: In-progress / interrupted execution
                    if rec.execution_status == "STARTED" and rec.completed_at is None:
                        logger.warning(
                            "Ambiguous in-progress execution detected for tool '%s' in session '%s'",
                            tool_name,
                            session_id,
                        )
                        return IdempotencyStatus.AMBIGUOUS_INTERRUPTED, rec

                    # Case A: Same args, completed execution
                    if rec.execution_status == "SUCCEEDED":
                        return IdempotencyStatus.DUPLICATE_SUCCEEDED, rec

                    # Authorization mismatch check if authorization hash is present
                    if target_auth_hash and rec.authorization_hash and target_auth_hash != rec.authorization_hash:
                        return IdempotencyStatus.AUTHORIZATION_MISMATCH, rec
                else:
                    # Case B: Same tool & session, but different arguments
                    return IdempotencyStatus.DIFFERENT_ARGUMENTS, rec

        # Case C / New execution
        return IdempotencyStatus.UNIQUE, None

    def get_records_for_session(self, session_id: str) -> List[ExecutionRecord]:
        """Return all execution records bound to a given session."""
        return [r for r in self._records.values() if r.session_id == session_id]

    def clear(self) -> None:
        """Clear all in-memory execution records (primarily for testing)."""
        self._records.clear()
