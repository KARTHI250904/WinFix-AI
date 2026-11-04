"""WinFix AI — Resource Boundedness & Memory Reliability Tests (Phase 33)."""

import pytest
import sys
from production.telemetry import TelemetryService
from production.telemetry_models import TelemetryEventType
from agent.checkpoint_manager import CheckpointManager


def test_telemetry_memory_buffer_bounding():
    """Verify in-memory event buffer does not grow unbounded under excessive event volume."""
    service = TelemetryService(db_manager=None)

    # Insert 5,000 events into memory buffer capped at 2,000
    for i in range(5000):
        service.record_session_event(f"sess_{i}", TelemetryEventType.SESSION_STARTED)

    assert len(service._memory_events) <= service._max_memory_events
    assert len(service._memory_events) == 2000


def test_checkpoint_store_memory_cleanup():
    """Verify in-memory checkpoint store can be cleared completely without retaining leaked objects."""
    mgr = CheckpointManager(db_manager=None)

    for i in range(50):
        mgr.create_checkpoint(
            session_id=f"clean_sess_{i}",
            workflow_id=f"wf_{i}",
            step_id=1,
            workflow_state="DIAGNOSING",
            current_step_index=0,
            domain="NETWORK",
        )

    assert len(mgr._checkpoints) == 50
    mgr.clear()
    assert len(mgr._checkpoints) == 0
