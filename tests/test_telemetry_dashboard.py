"""WinFix AI — Telemetry Dashboard Component Tests (Phase 32)."""

import pytest
from unittest.mock import MagicMock, patch

from production.telemetry import TelemetryService
from production.telemetry_analytics import TelemetryAnalytics
from production.telemetry_models import TelemetryEventType
from ui.telemetry_dashboard import render_telemetry_dashboard


def test_dashboard_renders_without_error():
    """Verify render_telemetry_dashboard executes cleanly with mock Streamlit."""
    service = TelemetryService(db_manager=None)
    analytics = TelemetryAnalytics(telemetry_service=service)

    service.record_session_event("sess_ui", TelemetryEventType.SESSION_STARTED)
    service.record_workflow_event("sess_ui", TelemetryEventType.WORKFLOW_COMPLETED, domain="NETWORK", duration_ms=200)

    def mock_cols(n, **kwargs):
        count = n if isinstance(n, int) else len(n)
        return [MagicMock() for _ in range(count)]

    # Patch streamlit primitives to verify read-only rendering without exceptions
    with patch("streamlit.markdown") as mock_md, \
         patch("streamlit.caption") as mock_cap, \
         patch("streamlit.metric") as mock_metric, \
         patch("streamlit.columns", side_effect=mock_cols), \
         patch("streamlit.tabs", return_value=[MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()]), \
         patch("streamlit.table") as mock_tbl, \
         patch("streamlit.divider") as mock_div:

        render_telemetry_dashboard(analytics=analytics, session_id="sess_ui")
        assert mock_md.called
        assert mock_metric.called
