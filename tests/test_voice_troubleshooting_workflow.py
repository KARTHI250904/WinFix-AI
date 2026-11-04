"""Tests for Voice Troubleshooting Workflow (End-to-End Post-Transcription Flow).

Validates:
Voice Transcript -> Problem Understanding -> Domain Detection -> SAFE Step-by-Step Diagnostic Plan
-> Execute SAFE Diagnostics -> Real Windows / Empirical Findings -> Plain-English Explanation
-> Evidence-Based Next Step -> Confirmation-Gated Safe Repair -> Deterministic Verification.

Classification:
- REAL: Real ToolRegistry handlers, real SafetyEngine, real PersonalTutor flow generation, real interpretation.
- SIMULATED: Voice transcript input simulation.
- STATIC: AST / schema validation.
"""

import pytest
from typing import Dict, Any

from agent.tool_registry import default_tool_registry
from agent.safety import default_safety_engine
from agent.voice_diagnostics import (
    default_voice_orchestrator,
    VoiceDiagnosticMapper,
    VoiceAnalysis,
    VoiceStatus,
    VoiceTranscript,
    VoiceDiagnosticCategory,
)
from modes.personal_tutor import default_personal_tutor
from modes.tutor_models import StepStatus, TroubleshootingSession


class TestVoiceTroubleshootingWorkflow:
    """Test suite for post-transcription interactive troubleshooting workflows."""

    def test_voice_storage_workflow_end_to_end(self):
        """TEST 1: 'My C drive is almost full.' -> STORAGE domain -> safe diagnostics -> repair -> verification."""
        transcript_text = "My C drive is almost full."
        
        # 1. Voice Domain Inference via Voice Diagnostic Mapper
        hints = default_voice_orchestrator.mapper.map_transcript_to_hints(transcript_text)
        assert len(hints) > 0
        assert hints[0].category == VoiceDiagnosticCategory.STORAGE.value

        # Formulate full VoiceAnalysis object
        import time
        from agent.voice_diagnostics import VoiceMetadata
        transcript_obj = VoiceTranscript(
            text=transcript_text,
            sanitized_text=transcript_text,
            confidence=0.98,
            duration_seconds=3.5,
            model_used="faster-whisper:base.en",
        )
        meta = VoiceMetadata(
            session_id="test_voice_storage_session",
            filename="microphone_test.wav",
            format="WAV",
            file_size=1024,
            audio_hash="abc" * 20,
        )
        analysis = VoiceAnalysis(
            metadata=meta,
            transcript=transcript_obj,
            hints=hints,
            inferred_intent=f"User reported: \"{transcript_text}\"",
            what_needs_verification=["Spoken statements reflect symptoms"],
            recommended_next_steps=["Check storage capacity"],
            privacy_warnings=[],
            status=VoiceStatus.COMPLETED,
            analysis_duration_ms=120,
            created_at=time.time(),
        )
        assert analysis.status == VoiceStatus.COMPLETED
        assert analysis.transcript is not None
        assert analysis.transcript.sanitized_text == transcript_text

        # Test Personal Tutor explanation synthesis for Voice
        tutor_exp = default_voice_orchestrator.explain_voice_analysis(analysis)
        assert tutor_exp is not None
        assert len(tutor_exp.summary) > 0

        # 2. Formulate SAFE Step-by-Step Troubleshooting Flow from Voice Transcript
        session: TroubleshootingSession = default_personal_tutor.create_troubleshooting_flow(
            user_question=transcript_text,
        )
        assert session.domain == "storage"
        assert len(session.steps) >= 3

        # Step 1: Check storage capacity (SAFE read-only diagnostic)
        step1 = session.steps[0]
        assert step1.tool_name == "get_storage_diagnostics"
        assert step1.risk == "SAFE"
        assert step1.requires_confirmation is False
        assert not step1.is_repair

        # Execute Step 1 and verify human-readable findings
        res_step1 = default_personal_tutor.execute_tutor_step(session, 1)
        assert res_step1.status == StepStatus.COMPLETED
        assert "Free space:" in res_step1.finding
        assert "Total space:" in res_step1.finding
        assert "Used space:" in res_step1.finding
        assert len(res_step1.meaning) > 0
        assert res_step1.next_step_hint is not None

        # Step 2: Inspect temporary storage cache (SAFE read-only diagnostic)
        step2 = session.steps[1]
        assert step2.tool_name == "get_temp_storage_info"
        assert step2.risk == "SAFE"
        assert step2.requires_confirmation is False

        # Execute Step 2
        res_step2 = default_personal_tutor.execute_tutor_step(session, 2)
        assert res_step2.status == StepStatus.COMPLETED
        assert "Temporary storage currently uses:" in res_step2.finding
        assert len(res_step2.meaning) > 0

        # Step 3: Clean temporary cache (MEDIUM risk repair)
        step3 = session.steps[2]
        assert step3.is_repair is True
        assert step3.risk == "MEDIUM"
        assert step3.requires_confirmation is True

        # Unconfirmed execution must be gated by SafetyEngine
        res_step3_unconf = default_personal_tutor.execute_tutor_step(session, 3, user_confirmed=False)
        assert res_step3_unconf.status == StepStatus.AWAITING_CONFIRMATION

        # Confirmed execution must run repair and verify
        res_step3_conf = default_personal_tutor.execute_tutor_step(session, 3, user_confirmed=True)
        assert res_step3_conf.status == StepStatus.COMPLETED
        assert res_step3_conf.verification_status is not None

    def test_voice_network_workflow_end_to_end(self):
        """TEST 2: 'My Wi-Fi keeps disconnecting every few minutes.' -> NETWORK domain -> adapter diagnostics -> reachability -> DNS."""
        transcript_text = "My Wi-Fi keeps disconnecting every few minutes."

        # 1. Voice Domain Inference
        hints = default_voice_orchestrator.mapper.map_transcript_to_hints(transcript_text)
        assert len(hints) > 0
        assert any(h.category == VoiceDiagnosticCategory.NETWORK.value for h in hints)

        # 2. Formulate Step-by-Step Flow
        session = default_personal_tutor.create_troubleshooting_flow(
            user_question=transcript_text,
        )
        assert session.domain == "network"
        assert len(session.steps) >= 3

        # Step 1: Adapter Diagnostics
        step1 = session.steps[0]
        assert step1.tool_name == "get_network_adapters_diagnostics"
        res1 = default_personal_tutor.execute_tutor_step(session, 1)
        assert res1.status == StepStatus.COMPLETED
        assert len(res1.finding) > 0
        assert len(res1.meaning) > 0

        # Step 2: Local Gateway Reachability
        step2 = session.steps[1]
        assert step2.tool_name == "check_internet_connectivity"
        res2 = default_personal_tutor.execute_tutor_step(session, 2)
        assert res2.status == StepStatus.COMPLETED
        assert len(res2.finding) > 0

        # Step 3: DNS Resolution
        step3 = session.steps[2]
        assert step3.tool_name == "check_dns_resolution"
        res3 = default_personal_tutor.execute_tutor_step(session, 3)
        assert res3.status == StepStatus.COMPLETED
        assert len(res3.finding) > 0

    def test_voice_performance_workflow_end_to_end(self):
        """TEST 3: 'My computer is very slow and the CPU usage is very high.' -> PERFORMANCE domain -> CPU -> RAM -> storage -> services."""
        transcript_text = "My computer is very slow and the CPU usage is very high."

        # 1. Domain Inference
        hints = default_voice_orchestrator.mapper.map_transcript_to_hints(transcript_text)
        assert len(hints) > 0
        assert any(h.category == VoiceDiagnosticCategory.PERFORMANCE.value for h in hints)

        # 2. Formulate Troubleshooting Flow
        session = default_personal_tutor.create_troubleshooting_flow(
            user_question=transcript_text,
        )
        assert session.domain == "performance"
        assert len(session.steps) >= 3

        # Step 1: CPU processes
        step1 = session.steps[0]
        assert step1.tool_name == "get_top_cpu_processes"
        res1 = default_personal_tutor.execute_tutor_step(session, 1)
        assert res1.status == StepStatus.COMPLETED
        assert len(res1.finding) > 0

        # Step 2: Memory processes
        step2 = session.steps[1]
        assert step2.tool_name == "get_top_memory_processes"
        res2 = default_personal_tutor.execute_tutor_step(session, 2)
        assert res2.status == StepStatus.COMPLETED
        assert len(res2.finding) > 0

    def test_all_voice_domains_flow_generation(self):
        """TEST 4: Validate that all supported voice domains produce structured step-by-step guides with plain-English findings."""
        domain_queries = {
            "bluetooth": "My Bluetooth headphones will not pair with Windows.",
            "windows_update": "Windows Update is stuck downloading updates with an error.",
            "defender": "Windows Defender antivirus protection is showing turned off.",
            "services": "The background Windows service is stopped and failing to start.",
            "application_crash": "My desktop software keeps crashing on startup with an error log.",
            "general": "My system is behaving strangely after rebooting.",
        }

        for expected_domain, query in domain_queries.items():
            session = default_personal_tutor.create_troubleshooting_flow(user_question=query)
            assert session.domain == expected_domain, f"Query '{query}' expected domain '{expected_domain}', got '{session.domain}'"
            assert len(session.steps) >= 1, f"Domain '{expected_domain}' must produce at least 1 diagnostic step"
            
            # Execute first step safely
            first_step = session.steps[0]
            if not first_step.is_repair:
                res = default_personal_tutor.execute_tutor_step(session, 1)
                assert res.status == StepStatus.COMPLETED
                assert len(res.finding) > 0
                assert len(res.meaning) > 0
