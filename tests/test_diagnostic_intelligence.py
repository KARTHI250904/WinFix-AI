"""WinFix AI — Phase 27 AI Decision & Diagnostic Intelligence Unit Tests.

Validates evidence normalization, provenance, freshness TTL, contradiction detection,
observation/interpretation separation, hypothesis generation, ToolRegistry recommendation
validation, bounded diagnostic plans, loop protection, and degraded offline operation.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agent.diagnostic_engine import AIDiagnosticEngine
from agent.diagnostic_models import (
    DiagnosticHypothesis,
    DiagnosticPlan,
    DiagnosticPlanStep,
    DiagnosticResponse,
    HypothesisStatus,
)
from agent.evidence_models import (
    EvidenceItem,
    EvidenceNormalizer,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
)
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry

from ai.ollama_client import OllamaClient
from production.performance import default_profiler


class TestDiagnosticIntelligence:
    """Test suite for Phase 27 AI Decision & Diagnostic Intelligence."""

    def test_evidence_creation_and_normalization(self) -> None:
        """Verify normalization of tool outputs, user text, and screenshots."""
        # 1. From tool result
        tool_res = {"status": "ok", "summary": "Ethernet adapter is active and connected."}
        items = EvidenceNormalizer.from_tool_result(
            tool_name="get_network_adapters_diagnostics",
            tool_result=tool_res,
            evidence_type=EvidenceType.NETWORK,
            session_id="session_01",
        )
        assert len(items) == 1
        ev = items[0]
        assert ev.evidence_type == EvidenceType.NETWORK
        assert ev.source == EvidenceSource.WINDOWS_TOOL
        assert ev.quality == EvidenceQuality.VERIFIED
        assert ev.status == EvidenceStatus.VALID
        assert "Ethernet adapter" in ev.observation

        # 2. From user text
        user_ev = EvidenceNormalizer.from_user_input(
            user_text="My internet is not working at all.",
            session_id="session_01",
        )
        assert user_ev.evidence_type == EvidenceType.USER_REPORTED
        assert user_ev.quality == EvidenceQuality.USER_REPORTED
        assert user_ev.source == EvidenceSource.USER

        # 3. From screenshot
        screen_ev = EvidenceNormalizer.from_screenshot(
            observation="Windows network tray icon displays a red cross.",
            visual_details={"dialog": "Network Error"},
            session_id="session_01",
        )
        assert screen_ev.evidence_type == EvidenceType.SCREENSHOT
        assert screen_ev.quality == EvidenceQuality.INFERRED

    def test_evidence_provenance_and_freshness(self) -> None:
        """Verify evidence TTL freshness checking."""
        now = datetime.now(timezone.utc)
        fresh_item = EvidenceItem(
            evidence_id="ev_fresh",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="network",
            observation="Ping successful",
            value={},
            timestamp=now.isoformat(),
            ttl_seconds=60,
        )
        assert fresh_item.is_stale(now) is False

        # Stale item (older than 60s TTL)
        past_time = now - timedelta(seconds=120)
        stale_item = EvidenceItem(
            evidence_id="ev_stale",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="network",
            observation="Ping successful",
            value={},
            timestamp=past_time.isoformat(),
            ttl_seconds=60,
        )
        assert stale_item.is_stale(now) is True

    def test_contradiction_detection_network_states(self) -> None:
        """Verify contradiction detection when mutually exclusive observations exist."""
        store = EvidenceStore()
        sid = "test_contra_session"

        ev1 = EvidenceItem(
            evidence_id="ev_01",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="network",
            observation="Network interface is connected.",
            value={"internet_connected": True},
            session_id=sid,
        )
        ev2 = EvidenceItem(
            evidence_id="ev_02",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="network",
            observation="Network gateway is unreachable and disconnected.",
            value={"internet_connected": False},
            session_id=sid,
        )

        store.add_many([ev1, ev2])
        contradictions = store.detect_contradictions(sid)
        assert len(contradictions) >= 1
        assert contradictions[0]["type"] == "NETWORK_CONNECTIVITY_CONFLICT"

    def test_contradiction_detection_user_vs_verified(self) -> None:
        """Verify detection of conflict between user statement and verified tool state."""
        store = EvidenceStore()
        sid = "user_vs_state"

        u_ev = EvidenceItem(
            evidence_id="ev_user",
            evidence_type=EvidenceType.USER_REPORTED,
            source=EvidenceSource.USER,
            category="symptom",
            observation="My internet is down and disconnected.",
            value={},
            quality=EvidenceQuality.USER_REPORTED,
            session_id=sid,
        )
        v_ev = EvidenceItem(
            evidence_id="ev_tool",
            evidence_type=EvidenceType.NETWORK,
            source=EvidenceSource.WINDOWS_TOOL,
            category="network",
            observation="DNS resolution succeeded and gateway is online.",
            value={"internet_connected": True},
            quality=EvidenceQuality.VERIFIED,
            session_id=sid,
        )

        store.add_many([u_ev, v_ev])
        contradictions = store.detect_contradictions(sid)
        assert len(contradictions) >= 1
        assert any(c["type"] == "USER_REPORTED_VS_VERIFIED_STATE" for c in contradictions)

    def test_session_isolation_in_evidence_store(self) -> None:
        """Verify evidence is strictly scoped by session_id."""
        store = EvidenceStore()

        ev_a = EvidenceItem(
            evidence_id="a1",
            evidence_type=EvidenceType.SYSTEM,
            source=EvidenceSource.WINDOWS_TOOL,
            category="system",
            observation="Session A info",
            value={},
            session_id="session_A",
        )
        ev_b = EvidenceItem(
            evidence_id="b1",
            evidence_type=EvidenceType.SYSTEM,
            source=EvidenceSource.WINDOWS_TOOL,
            category="system",
            observation="Session B info",
            value={},
            session_id="session_B",
        )

        store.add_evidence(ev_a)
        store.add_evidence(ev_b)

        items_a = store.get_session_evidence("session_A")
        items_b = store.get_session_evidence("session_B")

        assert len(items_a) == 1
        assert items_a[0].evidence_id == "a1"
        assert len(items_b) == 1
        assert items_b[0].evidence_id == "b1"

    def test_observation_interpretation_separation(self) -> None:
        """Verify DiagnosticResponse cleanly separates Observations from Interpretations."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = True
        mock_client.generate.return_value = {
            "success": True,
            "response": """{
              "summary": "DNS Resolution degraded.",
              "observations": ["Ping to 8.8.8.8 succeeded", "DNS query for google.com failed"],
              "interpretations": ["Internet gateway is reachable, but name resolution service is failing"],
              "hypotheses": [
                {
                  "category": "network",
                  "statement": "DNS Cache corruption or invalid resolver IP",
                  "affected_component": "DNS",
                  "severity": "NORMAL",
                  "status": "SUPPORTED",
                  "recommended_tools": ["check_dns_resolution"]
                }
              ],
              "recommended_tools": ["check_dns_resolution"],
              "uncertainty": ["Primary DNS server address not yet queried"]
            }""",
        }

        engine = AIDiagnosticEngine(client=mock_client)
        resp = engine.evaluate_diagnosis("Why can't I open websites by name?")

        assert len(resp.observations) == 2
        assert "Ping to 8.8.8.8" in resp.observations[0]
        assert len(resp.interpretations) == 1
        assert "name resolution" in resp.interpretations[0]
        assert len(resp.hypotheses) == 1
        assert resp.hypotheses[0].status == HypothesisStatus.SUPPORTED

    def test_recommended_tool_validation_against_registry(self) -> None:
        """Verify that only tools in ToolRegistry are accepted into recommendations."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = True
        mock_client.generate.return_value = {
            "success": True,
            "response": """{
              "summary": "Storage check",
              "recommended_tools": [
                "get_storage_diagnostics",
                "malicious_powershell_tool",
                "format_drive_tool"
              ]
            }""",
        }

        engine = AIDiagnosticEngine(client=mock_client)
        resp = engine.evaluate_diagnosis("Check my hard drive")

        assert "get_storage_diagnostics" in resp.recommended_tools
        assert "malicious_powershell_tool" not in resp.recommended_tools
        assert "format_drive_tool" not in resp.recommended_tools

    def test_diagnostic_plan_bounded_limits_and_loop_protection(self) -> None:
        """Verify diagnostic plans enforce max 5 steps and 1 execution per tool."""
        engine = AIDiagnosticEngine()
        tool_names = [
            "get_cpu_diagnostics",
            "get_memory_diagnostics",
            "get_top_cpu_processes",
            "get_cpu_diagnostics",  # Duplicate (loop attempt)
            "get_services_diagnostics",
            "get_storage_diagnostics",
            "get_complete_system_info",  # 6th tool (overflow)
        ]

        plan = engine.build_diagnostic_plan(tool_names, session_id="plan_test_session")
        assert len(plan.steps) <= 5
        assert plan.validate_plan_limits() is True

        unique_tools = [s.tool_name for s in plan.steps]
        assert len(unique_tools) == len(set(unique_tools)), "Duplicate tool found in plan"

    def test_plan_step_execution_with_safe_tools(self) -> None:
        """Verify executing a diagnostic step invokes the registered tool handler safely."""
        engine = AIDiagnosticEngine()
        plan = engine.build_diagnostic_plan(["get_complete_system_info"], session_id="exec_test_session")

        assert len(plan.steps) == 1
        success, result, msg = engine.execute_plan_step(plan, step_index=0)

        assert success is True
        assert result is not None
        assert plan.steps[0].status == "COMPLETED"
        assert plan.status == "COMPLETED"

        # Check evidence was automatically ingested
        evidence = engine.evidence_store.get_session_evidence("exec_test_session")
        assert len(evidence) >= 1
        assert any(e.tool_name == "get_complete_system_info" for e in evidence)

    def test_degraded_mode_diagnostic_fallback(self) -> None:
        """Verify deterministic rule-based evaluation when Ollama is offline."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = False

        engine = AIDiagnosticEngine(client=mock_client)
        resp = engine.evaluate_diagnosis("My printer spooler service keeps stopping", session_id="degraded_sess")

        assert resp.is_degraded is True
        assert "service" in resp.summary.lower()
        assert len(resp.hypotheses) >= 1
        assert len(resp.recommended_tools) >= 1
        assert "get_services_diagnostics" in resp.recommended_tools

    def test_screenshot_and_voice_evidence_ingestion(self) -> None:
        """Verify multi-modal evidence ingestion pipeline."""
        engine = AIDiagnosticEngine()
        sid = "multimodal_session"

        engine.ingest_screenshot(
            observation="Blue screen showing CRITICAL_PROCESS_DIED",
            visual_details={"code": "0xEF"},
            session_id=sid,
        )
        engine.ingest_user_symptom(
            user_text="Computer crashed suddenly while gaming.",
            session_id=sid,
            source=EvidenceSource.VOICE,
        )

        ev_list = engine.evidence_store.get_session_evidence(sid)
        assert len(ev_list) == 2
        types = [e.evidence_type for e in ev_list]
        assert EvidenceType.SCREENSHOT in types
        assert EvidenceType.VOICE in types

    def test_profiler_records_diagnostic_intelligence_metrics(self) -> None:
        """Verify performance measurements are captured for diagnostic engine operations."""
        default_profiler.clear()
        engine = AIDiagnosticEngine()
        engine.ingest_user_symptom("Test performance profiling", session_id="perf_sess")

        metrics = default_profiler.get_metrics("ingest_user_symptom")
        assert len(metrics) > 0
        assert metrics[0].status == "SUCCESS"
        assert metrics[0].duration_ms >= 0.0

    def test_knowledge_article_evidence_ingestion(self) -> None:
        """Verify ingestion of knowledge base articles as diagnostic evidence."""
        store = EvidenceStore()
        item = EvidenceItem(
            evidence_id="kb_01",
            evidence_type=EvidenceType.KNOWLEDGE,
            source=EvidenceSource.KNOWLEDGE,
            category="network",
            observation="Knowledge Article: DNS resolution failures frequently stem from stale DNS client cache.",
            value={"article_id": 1, "topic": "DNS Troubleshooting"},
            quality=EvidenceQuality.VERIFIED,
            session_id="kb_sess",
            ttl_seconds=3600,
        )
        store.add_evidence(item)
        evs = store.get_session_evidence("kb_sess")
        assert len(evs) == 1
        assert evs[0].source == EvidenceSource.KNOWLEDGE
        assert evs[0].is_stale() is False

    def test_hypothesis_and_response_serialization(self) -> None:
        """Verify serialization of DiagnosticHypothesis and DiagnosticResponse."""
        hyp = DiagnosticHypothesis(
            hypothesis_id="h1",
            category="network",
            statement="Gateway unreachable",
            supporting_evidence_ids=["ev1"],
            status=HypothesisStatus.POSSIBLE,
        )
        d_hyp = hyp.to_dict()
        assert d_hyp["hypothesis_id"] == "h1"
        assert d_hyp["status"] == "POSSIBLE"

        resp = DiagnosticResponse(
            summary="Test summary",
            observations=["Obs 1"],
            interpretations=["Interp 1"],
            hypotheses=[hyp],
            recommended_tools=["check_dns_resolution"],
        )
        d_resp = resp.to_dict()
        assert d_resp["summary"] == "Test summary"
        assert len(d_resp["hypotheses"]) == 1

    def test_step_failure_handling_in_plan_execution(self) -> None:
        """Verify that step execution failures are captured without raising unhandled crashes."""
        mock_registry = MagicMock(spec=ToolRegistry)
        mock_tool_def = MagicMock(spec=ToolDefinition)
        mock_tool_def.risk = RiskLevel.SAFE
        mock_tool_def.name = "failing_tool"
        mock_tool_def.handler = MagicMock(side_effect=RuntimeError("Simulated tool hardware failure"))
        mock_registry.get.return_value = mock_tool_def

        mock_safety = MagicMock(spec=SafetyEngine)
        mock_safety.evaluate.return_value = MagicMock(allowed=True, requires_confirmation=False)

        engine = AIDiagnosticEngine(tool_registry=mock_registry, safety_engine=mock_safety)
        plan = engine.build_diagnostic_plan(["failing_tool"], session_id="fail_sess")
        plan.steps = [DiagnosticPlanStep(step_id=1, tool_name="failing_tool", purpose="Test fail")]

        success, res, msg = engine.execute_plan_step(plan, step_index=0)
        assert success is False
        assert plan.steps[0].status == "FAILED"
        assert "Simulated tool hardware failure" in str(plan.steps[0].result)


    def test_clear_session_evidence(self) -> None:
        """Verify clearing session evidence removes all records for that session."""
        store = EvidenceStore()
        ev = EvidenceItem(
            evidence_id="cl_01",
            evidence_type=EvidenceType.SYSTEM,
            source=EvidenceSource.WINDOWS_TOOL,
            category="system",
            observation="Clear test",
            value={},
            session_id="clear_me",
        )
        store.add_evidence(ev)
        assert len(store.get_session_evidence("clear_me")) == 1

        store.clear_session("clear_me")
        assert len(store.get_session_evidence("clear_me")) == 0

    def test_oversized_text_sanitization(self) -> None:
        """Verify that control characters and null bytes in raw inputs are sanitized."""
        dirty = "System report\x00 with null bytes\x08 and control\x1f characters."
        cleaned = EvidenceNormalizer.sanitize_text(dirty)
        assert "\x00" not in cleaned
        assert "\x08" not in cleaned
        assert "System report with null bytes and control characters." == cleaned

