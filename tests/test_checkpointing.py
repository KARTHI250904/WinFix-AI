"""WinFix AI — Phase 31 Checkpoint Management Unit Tests.

Validates:
1. Checkpoint creation at safe lifecycle boundaries
2. Sanitization of sensitive data (credentials, tokens, binary bytes)
3. Staleness detection against TTL limits
4. Checkpoint retrieval by session and workflow
5. Checkpoint serialization and deserialization
"""

from datetime import datetime, timedelta, timezone
import pytest
import uuid

from agent.checkpoint_manager import CheckpointManager
from agent.recovery_models import Checkpoint


class TestCheckpointManager:
    """Test suite for workflow checkpoint creation, sanitization, and retrieval."""

    @pytest.fixture
    def manager(self):
        return CheckpointManager()

    def test_checkpoint_creation_and_retrieval(self, manager):
        session_id = "sess-chk-1"
        wf_id = "wf-chk-1"

        chk = manager.create_checkpoint(
            session_id=session_id,
            workflow_id=wf_id,
            step_id=2,
            workflow_state="DIAGNOSING",
            current_step_index=2,
            domain="NETWORK",
            evidence_references=["ev-1", "ev-2"],
            hypothesis_references=["hyp-1"],
        )

        assert chk.checkpoint_id.startswith("chk-")
        assert chk.session_id == session_id
        assert chk.workflow_id == wf_id
        assert chk.step_id == 2
        assert chk.workflow_state == "DIAGNOSING"
        assert len(chk.evidence_references) == 2

        # Retrieval by ID
        fetched = manager.get_checkpoint(chk.checkpoint_id)
        assert fetched is not None
        assert fetched.checkpoint_id == chk.checkpoint_id

        # Retrieval by Session
        latest = manager.get_latest_checkpoint_for_session(session_id)
        assert latest is not None
        assert latest.checkpoint_id == chk.checkpoint_id

        # Retrieval by Workflow
        latest_wf = manager.get_latest_checkpoint_for_workflow(wf_id)
        assert latest_wf is not None
        assert latest_wf.checkpoint_id == chk.checkpoint_id

    def test_checkpoint_sanitization(self, manager):
        """Verify sensitive credentials and raw binary payloads are redacted in checkpoints."""
        raw_auth = {
            "token": "super_secret_auth_token_123",
            "password": "plain_text_password",
            "api_key": "secret_key_abc",
            "safe_metadata": "public_data",
        }
        raw_exec = {
            "binary_stream": b"\x00\x01\x02\x03\x04",
            "returncode": 0,
        }

        chk = manager.create_checkpoint(
            session_id="sess-sec-1",
            workflow_id="wf-sec-1",
            step_id=3,
            workflow_state="REPAIRING",
            current_step_index=3,
            domain="SERVICES",
            authorization_state=raw_auth,
            execution_state=raw_exec,
        )

        assert chk.authorization_state["token"] == "[REDACTED_FOR_SECURITY]"
        assert chk.authorization_state["password"] == "[REDACTED_FOR_SECURITY]"
        assert chk.authorization_state["safe_metadata"] == "public_data"
        assert "<binary_payload_size_5_bytes>" in chk.execution_state["binary_stream"]

    def test_checkpoint_staleness_detection(self):
        """Verify checkpoints exceeding TTL are flagged as stale."""
        now = datetime.now(timezone.utc)
        fresh_chk = Checkpoint(
            checkpoint_id="chk-fresh",
            session_id="s1",
            workflow_id="w1",
            step_id=1,
            workflow_state="DIAGNOSING",
            current_step_index=1,
            domain="NETWORK",
            updated_at=now.isoformat(),
        )
        assert fresh_chk.is_stale(max_age_seconds=1800) is False

        # Stale checkpoint (1 hour old)
        old_time = (now - timedelta(seconds=3600)).isoformat()
        stale_chk = Checkpoint(
            checkpoint_id="chk-stale",
            session_id="s1",
            workflow_id="w1",
            step_id=1,
            workflow_state="DIAGNOSING",
            current_step_index=1,
            domain="NETWORK",
            updated_at=old_time,
        )
        assert stale_chk.is_stale(max_age_seconds=1800) is True

    def test_checkpoint_serialization_roundtrip(self):
        chk = Checkpoint(
            checkpoint_id="chk-roundtrip",
            session_id="sess-rt",
            workflow_id="wf-rt",
            step_id=4,
            workflow_state="VERIFYING",
            current_step_index=4,
            domain="STORAGE",
            evidence_references=["ev-10"],
            repair_candidate={"tool_name": "clean_user_temp_cache"},
        )
        as_dict = chk.to_dict()
        restored = Checkpoint.from_dict(as_dict)

        assert restored.checkpoint_id == chk.checkpoint_id
        assert restored.workflow_state == chk.workflow_state
        assert restored.domain == chk.domain
        assert restored.repair_candidate == chk.repair_candidate
