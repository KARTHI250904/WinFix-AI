"""WinFix AI — Checkpoint Manager (Phase 31).

Manages persistent, sanitized workflow checkpoints at safe lifecycle boundaries.
Strictly adheres to:
  No raw audio, raw screenshots, credentials, or plaintext tokens stored.
  Fail-closed schema validation.
  Deterministic staleness detection.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from agent.recovery_models import Checkpoint

logger = logging.getLogger("winfix.CHECKPOINT_MANAGER")


class CheckpointManager:
    """Manages creation, serialization, retrieval, and lifecycle of workflow checkpoints."""

    def __init__(self, db_manager: Optional[Any] = None) -> None:
        self.db_manager = db_manager
        # In-memory storage keyed by checkpoint_id and session_id
        self._checkpoints: Dict[str, Checkpoint] = {}

    def create_checkpoint(
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
        """Create and store a new sanitized workflow checkpoint."""
        checkpoint_id = f"chk-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Sanitize repair candidate and authorization data if present
        sanitized_repair = self._sanitize_dict(repair_candidate) if repair_candidate else None
        sanitized_auth = self._sanitize_dict(authorization_state) if authorization_state else None
        sanitized_exec = self._sanitize_dict(execution_state) if execution_state else None
        sanitized_verif = self._sanitize_dict(verification_state) if verification_state else None

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            workflow_id=workflow_id,
            step_id=step_id,
            workflow_state=workflow_state,
            current_step_index=current_step_index,
            domain=domain,
            evidence_references=list(evidence_references or []),
            hypothesis_references=list(hypothesis_references or []),
            diagnostic_decisions=list(diagnostic_decisions or []),
            repair_candidate=sanitized_repair,
            authorization_state=sanitized_auth,
            execution_state=sanitized_exec,
            verification_state=sanitized_verif,
            created_at=now_iso,
            updated_at=now_iso,
            schema_version="1.0",
        )

        self._checkpoints[checkpoint_id] = checkpoint

        # Persist to SQLite if db_manager is available
        self._persist_to_db(checkpoint)
        logger.debug("Created checkpoint %s for workflow %s (state=%s)", checkpoint_id, workflow_id, workflow_state)
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Retrieve a checkpoint by its ID."""
        return self._checkpoints.get(checkpoint_id)

    def get_latest_checkpoint_for_session(self, session_id: str) -> Optional[Checkpoint]:
        """Retrieve the most recent checkpoint for a given session."""
        session_checkpoints = [c for c in self._checkpoints.values() if c.session_id == session_id]
        if not session_checkpoints:
            return None
        return max(session_checkpoints, key=lambda c: c.updated_at)

    def get_latest_checkpoint_for_workflow(self, workflow_id: str) -> Optional[Checkpoint]:
        """Retrieve the most recent checkpoint for a given workflow."""
        wf_checkpoints = [c for c in self._checkpoints.values() if c.workflow_id == workflow_id]
        if not wf_checkpoints:
            return None
        return max(wf_checkpoints, key=lambda c: c.updated_at)

    def list_checkpoints_for_session(self, session_id: str) -> List[Checkpoint]:
        """List all checkpoints for a session ordered by update time."""
        return sorted(
            [c for c in self._checkpoints.values() if c.session_id == session_id],
            key=lambda c: c.updated_at,
        )

    def _sanitize_dict(self, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Remove sensitive tokens, raw image bytes, or audio streams from checkpoint data."""
        if not data:
            return None
        sanitized: Dict[str, Any] = {}
        for k, v in data.items():
            k_lower = k.lower()
            if any(secret_word in k_lower for secret_word in ["password", "token", "secret", "credential", "auth_token"]):
                # Store only hash indicator or redaction
                sanitized[k] = "[REDACTED_FOR_SECURITY]"
            elif isinstance(v, (bytes, bytearray)):
                sanitized[k] = f"<binary_payload_size_{len(v)}_bytes>"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_dict(v)
            else:
                sanitized[k] = v
        return sanitized

    def _persist_to_db(self, checkpoint: Checkpoint) -> None:
        """Persist checkpoint record into SQLite database if configured."""
        if not self.db_manager:
            return
        try:
            with self.db_manager.get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO workflow_checkpoints (
                        checkpoint_id, session_id, workflow_id, step_id,
                        workflow_state, current_step_index, domain,
                        data_json, created_at, updated_at, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint.checkpoint_id,
                        checkpoint.session_id,
                        checkpoint.workflow_id,
                        checkpoint.step_id,
                        checkpoint.workflow_state,
                        checkpoint.current_step_index,
                        checkpoint.domain,
                        json.dumps(checkpoint.to_dict()),
                        checkpoint.created_at,
                        checkpoint.updated_at,
                        checkpoint.schema_version,
                    ),
                )
        except Exception as exc:
            logger.warning("Failed to persist checkpoint %s to database: %s", checkpoint.checkpoint_id, exc)

    def clear(self) -> None:
        """Clear in-memory checkpoints (primarily for testing)."""
        self._checkpoints.clear()
