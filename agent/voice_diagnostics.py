"""Voice diagnostics orchestrator and tool resolution module for WinFix AI.

Coordinates safe audio ingestion, local transcription, transcript sanitization,
rule-based problem domain mapping to approved read-only diagnostic tools,
Personal Tutor explanation synthesis, and SQLite audit logging.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from ai.voice_prompt import VOICE_SYSTEM_INSTRUCTION, build_voice_prompt
from ai.voice_transcriber import VoiceTranscriber, default_voice_transcriber
from database.db import DatabaseManager, db_manager
from input.voice_input import (
    AudioValidationError,
    inspect_voice_privacy,
    validate_and_inspect_audio,
)
from input.voice_models import (
    VoiceAnalysis,
    VoiceDiagnosticCategory,
    VoiceDiagnosticHint,
    VoiceMetadata,
    VoiceStatus,
    VoiceTranscript,
)
from modes.personal_tutor import PersonalTutor, default_personal_tutor
from modes.tutor_models import TutorResponse

logger = logging.getLogger(__name__)

FORBIDDEN_EXECUTION_KEYS = {
    "cmd",
    "command",
    "shell",
    "powershell",
    "subprocess",
    "executable",
    "script",
    "code",
    "python",
    "eval",
    "exec",
    "os_system",
    "run_command",
    "run_process",
    "bash",
    "shlex",
}


def _check_security_violations(data: Any, path: str = "") -> None:
    """Recursively inspect structured data and reject forbidden command execution keys."""
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = str(k).lower().strip()
            current_path = f"{path}.{k}" if path else str(k)
            if k_lower in FORBIDDEN_EXECUTION_KEYS:
                raise ValueError(
                    f"Security Policy Rejection: Forbidden command execution field '{k}' detected at '{current_path}'."
                )
            _check_security_violations(v, current_path)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _check_security_violations(item, f"{path}[{idx}]")
    elif isinstance(data, str):
        val_lower = data.lower()
        for forbidden in ["powershell.exe", "cmd.exe", "format c:", "rmdir /s", "del /f /s"]:
            if forbidden in val_lower:
                raise ValueError(
                    f"Security Policy Rejection: Forbidden shell execution command '{forbidden}' detected in voice text."
                )


class VoiceDiagnosticMapper:
    """Maps sanitized voice transcripts to approved read-only diagnostic tools."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or default_tool_registry

    def map_transcript_to_hints(
        self,
        transcript_text: str,
        category_hint: Optional[str] = None,
    ) -> List[VoiceDiagnosticHint]:
        """Infer problem category and resolve candidate registered read-only diagnostic tools."""
        text_lower = transcript_text.lower().strip()
        hints: List[VoiceDiagnosticHint] = []

        # Domain rules configuration
        domain_rules: List[Tuple[VoiceDiagnosticCategory, List[str], List[Tuple[str, str]]]] = [
            (
                VoiceDiagnosticCategory.NETWORK,
                ["internet", "wi-fi", "wifi", "network", "adapter", "dns", "gateway", "ip address", "offline", "disconnect", "ethernet"],
                [
                    ("check_internet_connectivity", "Verify internet connectivity and gateway reachability."),
                    ("get_network_adapters_diagnostics", "Inspect active network adapters and IP configurations."),
                    ("get_dns_client_config", "Check DNS resolver configuration."),
                ],
            ),
            (
                VoiceDiagnosticCategory.WINDOWS_UPDATE,
                ["windows update", "update error", "wuauserv", "0x8024", "0x80070422", "installing update", "downloading update"],
                [
                    ("get_windows_update_health", "Check overall Windows Update service health."),
                    ("get_windows_update_service_status", "Inspect wuauserv service operational state."),
                    ("get_windows_update_diagnostics", "Collect update history and recent update errors."),
                ],
            ),
            (
                VoiceDiagnosticCategory.DEFENDER,
                ["defender", "antivirus", "security", "threat", "virus", "windefend", "real-time protection"],
                [
                    ("get_defender_diagnostics", "Inspect Windows Defender state and real-time protection."),
                    ("get_defender_service_status", "Check WinDefend service status."),
                ],
            ),
            (
                VoiceDiagnosticCategory.STORAGE,
                ["disk", "storage", "drive full", "low disk", "out of space", "clean up", "temp files", "c drive"],
                [
                    ("get_storage_diagnostics", "Inspect disk volume space and drive health."),
                    ("get_temp_storage_info", "Check temporary folder usage."),
                ],
            ),
            (
                VoiceDiagnosticCategory.PERFORMANCE,
                ["slow", "freezing", "lag", "cpu", "memory", "ram full", "high usage", "unresponsive", "sluggish", "task manager"],
                [
                    ("get_cpu_diagnostics", "Inspect CPU utilization metrics."),
                    ("get_memory_diagnostics", "Inspect RAM utilization metrics."),
                    ("get_top_cpu_processes", "Identify top CPU-consuming user processes."),
                ],
            ),
            (
                VoiceDiagnosticCategory.APPLICATION_CRASH,
                ["crash", "crashing", "stopped working", "not responding", "appcrash", "exception", "faulting", "event 1000", "hang"],
                [
                    ("get_recent_application_crashes", "Retrieve recent application crash events from Event Log."),
                    ("get_application_crash_summary", "Summarize application crash frequency and faulting modules."),
                ],
            ),
            (
                VoiceDiagnosticCategory.BLUETOOTH,
                ["bluetooth", "paired device", "bthserv", "headset", "bluetooth audio", "pairing"],
                [
                    ("get_bluetooth_diagnostics", "Inspect Bluetooth radio and adapter status."),
                    ("get_bluetooth_service_status", "Check bthserv service operational state."),
                ],
            ),
            (
                VoiceDiagnosticCategory.SERVICE,
                ["service", "daemon", "service stopped", "service failed", "svchost"],
                [
                    ("get_service_status", "Inspect specific service status."),
                    ("list_common_services", "Check baseline core Windows services."),
                ],
            ),
        ]

        matched = False
        for cat, keywords, tool_pairs in domain_rules:
            if any(kw in text_lower for kw in keywords) or (category_hint and category_hint.upper() == cat.value):
                matched = True
                valid_tools: List[str] = []
                reasons: Dict[str, str] = {}
                for t_name, reason in tool_pairs:
                    if self._is_valid_readonly_tool(t_name):
                        valid_tools.append(t_name)
                        reasons[t_name] = reason

                if valid_tools:
                    hints.append(
                        VoiceDiagnosticHint(
                            category=cat.value,
                            confidence=0.90,
                            candidate_tools=valid_tools,
                            reason=f"Spoken keywords indicate possible {cat.value.lower().replace('_', ' ')} issue.",
                            tool_reasons=reasons,
                        )
                    )

        # Default fallback if no specific category matched
        if not matched:
            fallback_tool = "get_complete_system_info"
            if self._is_valid_readonly_tool(fallback_tool):
                hints.append(
                    VoiceDiagnosticHint(
                        category=VoiceDiagnosticCategory.GENERAL.value,
                        confidence=0.50,
                        candidate_tools=[fallback_tool],
                        reason="No specific domain matched; recommending general baseline system diagnostic.",
                        tool_reasons={fallback_tool: "Inspect general OS and hardware baseline."},
                    )
                )

        return hints

    def _is_valid_readonly_tool(self, tool_name: str) -> bool:
        """Check if tool exists in ToolRegistry and is strictly read-only."""
        tool = self.registry.get(tool_name)
        if not tool and hasattr(self.registry, "get_tool"):
            tool = self.registry.get_tool(tool_name)
        if not tool:
            return False
        return bool(tool.read_only)


class VoiceDiagnosticOrchestrator:
    """Main orchestrator for voice ingestion, local transcription, diagnostic mapping, and tutoring."""

    def __init__(
        self,
        transcriber: Optional[VoiceTranscriber] = None,
        mapper: Optional[VoiceDiagnosticMapper] = None,
        client: Optional[OllamaClient] = None,
        tutor: Optional[PersonalTutor] = None,
        db: Optional[DatabaseManager] = None,
    ) -> None:
        self.transcriber = transcriber or default_voice_transcriber
        self.mapper = mapper or VoiceDiagnosticMapper()
        self.client = client or ollama_client
        self.tutor = tutor or default_personal_tutor
        self.db = db or db_manager

    def process_voice_input(
        self,
        audio_bytes: bytes,
        filename: Optional[str] = None,
        user_clarification: Optional[str] = None,
        user_notes: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> VoiceAnalysis:
        """Complete workflow: Validate Audio -> Local STT -> Sanitization -> Diagnostic Mapping -> Analysis.

        Strict Invariant: The voice transcript must be the PRIMARY user problem.
        Optional text notes are treated strictly as additional context, NEVER replacing or overwriting the transcript.
        """
        from ai.voice_transcriber import is_valid_transcript

        start_time = time.time()
        sid = session_id or f"voice_sess_{int(time.time() * 1000)}"
        notes_text = (user_notes or user_clarification or "").strip()

        # 1. Audit: Received
        self._log_audit(sid, "VOICE_RECEIVED", {"filename": filename, "size": len(audio_bytes)})

        # 2. Validate audio container and size/duration bounds
        try:
            metadata = validate_and_inspect_audio(audio_bytes, filename=filename, session_id=sid)
        except AudioValidationError as val_err:
            logger.warning("Voice validation error: %s", val_err)
            self._log_audit(sid, "VOICE_VALIDATED", {"status": "FAILED", "error": str(val_err)})
            return self._build_error_analysis(
                error_msg=str(val_err),
                status=VoiceStatus.AUDIO_TOO_LARGE if "exceeds maximum limit" in str(val_err) else VoiceStatus.INVALID_AUDIO,
                filename=filename or "voice.wav",
                file_size=len(audio_bytes),
                start_time=start_time,
                session_id=sid,
            )

        self._log_audit(
            sid,
            "VOICE_VALIDATED",
            {"status": "SUCCESS", "hash": metadata.audio_hash, "format": metadata.format, "size": metadata.file_size},
        )

        # 3. Privacy review
        privacy_warnings = inspect_voice_privacy(metadata.filename)

        # 4. Check local STT provider availability
        if not self.transcriber.is_available():
            self._log_audit(sid, "VOICE_TRANSCRIPTION_FAILED", {"reason": "STT provider unavailable"})
            return self._build_unavailable_analysis(
                metadata=metadata,
                reason="Local speech-to-text model is not installed or available.",
                privacy_warnings=privacy_warnings,
                start_time=start_time,
                status=VoiceStatus.TRANSCRIPTION_UNAVAILABLE,
            )

        # 5. Execute local transcription
        self._log_audit(sid, "VOICE_TRANSCRIPTION_STARTED", {"hash": metadata.audio_hash})
        transcript = self.transcriber.transcribe_audio(audio_bytes, metadata)

        if not is_valid_transcript(transcript.text) or transcript.quality_status not in (VoiceStatus.COMPLETED, VoiceStatus.READY):
            reason_msg = "Your recording was received, but no intelligible speech could be recognized."
            if transcript.quality_status == VoiceStatus.AUDIO_SILENT:
                reason_msg = "Your recording was received, but the audio appears silent."
            elif transcript.quality_status == VoiceStatus.AUDIO_EMPTY:
                reason_msg = "Your recording was received, but the audio file contains no samples."
            elif transcript.quality_status == VoiceStatus.TRANSCRIPT_LOW_CONFIDENCE:
                reason_msg = "Speech was detected, but audio confidence was too low for reliable transcription."

            status_val = transcript.quality_status if transcript.quality_status in (
                VoiceStatus.TRANSCRIPT_EMPTY,
                VoiceStatus.TRANSCRIPT_LOW_CONFIDENCE,
                VoiceStatus.AUDIO_SILENT,
                VoiceStatus.AUDIO_EMPTY,
            ) else VoiceStatus.TRANSCRIPT_EMPTY

            self._log_audit(sid, "VOICE_TRANSCRIPTION_FAILED", {"reason": reason_msg, "status": str(status_val)})
            return self._build_unavailable_analysis(
                metadata=metadata,
                reason=reason_msg,
                privacy_warnings=privacy_warnings,
                start_time=start_time,
                status=status_val,
            )

        self._log_audit(
            sid,
            "VOICE_TRANSCRIPTION_COMPLETED",
            {"hash": metadata.audio_hash, "char_count": len(transcript.text), "model": transcript.model_used},
        )

        # 6. Analyze transcript and map diagnostic hints (Transcript is primary input)
        self._log_audit(sid, "VOICE_ANALYSIS_STARTED", {"hash": metadata.audio_hash})
        hints = self.mapper.map_transcript_to_hints(transcript.sanitized_text)

        # 7. Formulate intent and verification items
        inferred_intent = f"User reported: \"{transcript.sanitized_text}\""
        what_needs_verification = [
            "Spoken statements reflect symptoms; active deterministic inspection is required to confirm hardware and service states."
        ]
        recommended_next_steps = [
            f"Run proposed read-only diagnostic tools ({', '.join(h.candidate_tools[0] for h in hints if h.candidate_tools)}) to verify system state."
        ]

        duration_ms = int((time.time() - start_time) * 1000)

        analysis = VoiceAnalysis(
            metadata=metadata,
            transcript=transcript,
            hints=hints,
            inferred_intent=inferred_intent,
            what_needs_verification=what_needs_verification,
            recommended_next_steps=recommended_next_steps,
            privacy_warnings=privacy_warnings,
            status=VoiceStatus.COMPLETED,
            analysis_duration_ms=duration_ms,
            created_at=time.time(),
        )

        self._log_audit(
            sid,
            "VOICE_ANALYSIS_COMPLETED",
            {"hash": metadata.audio_hash, "hints_count": len(hints), "duration_ms": duration_ms},
        )

        return analysis

    def analyze_voice(
        self,
        audio_bytes: bytes,
        filename: Optional[str] = None,
        user_notes: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> VoiceAnalysis:
        """Alias for process_voice_input to maintain uniform multimodal interface."""
        return self.process_voice_input(
            audio_bytes=audio_bytes,
            filename=filename,
            user_notes=user_notes,
            session_id=session_id,
        )

    def explain_voice_analysis(
        self,
        analysis: VoiceAnalysis,
        user_question: Optional[str] = None,
    ) -> TutorResponse:
        """Use Personal Tutor to explain spoken symptoms, hypotheses, and required diagnostic steps."""
        diag_payload = {
            "voice_evidence": {
                "transcript": analysis.transcript.sanitized_text,
                "spoken_transcript": analysis.transcript.sanitized_text,
                "intent": analysis.inferred_intent,
                "inferred_intent": analysis.inferred_intent,
                "hints": [h.category for h in analysis.hints],
                "inferred_categories": [h.category for h in analysis.hints],
                "candidate_tools": [t for h in analysis.hints for t in h.candidate_tools],
                "recommended_tools": [t for h in analysis.hints for t in h.candidate_tools],
                "what_needs_verification": analysis.what_needs_verification,
            }
        }
        question = (
            user_question
            or f"Explain what the spoken problem '{analysis.transcript.sanitized_text}' indicates and why these diagnostics should be run."
        )
        return self.tutor.explain_diagnostic(
            diagnostic_data=diag_payload,
            user_question=question,
            session_id=analysis.metadata.session_id,
        )

    def _build_unavailable_analysis(
        self,
        metadata: VoiceMetadata,
        reason: str,
        privacy_warnings: List[str],
        start_time: float,
        status: VoiceStatus = VoiceStatus.TRANSCRIPTION_UNAVAILABLE,
    ) -> VoiceAnalysis:
        duration_ms = int((time.time() - start_time) * 1000)
        metadata.status = status
        empty_transcript = VoiceTranscript(
            text="",
            sanitized_text="",
            confidence=0.0,
            duration_seconds=0.0,
            model_used="none",
        )
        hints = self.mapper.map_transcript_to_hints("")
        next_steps = [
            "Your recording was received, but speech could not be transcribed.",
            "You can try recording again, upload a cleaner audio file, or type the problem directly.",
        ]

        return VoiceAnalysis(
            metadata=metadata,
            transcript=empty_transcript,
            hints=hints,
            inferred_intent=f"Voice processing notice: {reason}",
            what_needs_verification=["Spoken voice input could not be transcribed."],
            recommended_next_steps=next_steps,
            privacy_warnings=privacy_warnings,
            status=status,
            analysis_duration_ms=duration_ms,
            created_at=time.time(),
        )

    def _build_error_analysis(
        self,
        error_msg: str,
        status: VoiceStatus,
        filename: str,
        file_size: int,
        start_time: float,
        session_id: str,
    ) -> VoiceAnalysis:
        duration_ms = int((time.time() - start_time) * 1000)
        dummy_meta = VoiceMetadata(
            session_id=session_id,
            filename=filename,
            format="UNKNOWN",
            file_size=file_size,
            audio_hash="0" * 64,
            status=status,
        )
        return VoiceAnalysis(
            metadata=dummy_meta,
            transcript=VoiceTranscript("", "", 0.0, "en", False, 0.0, "none"),
            hints=[],
            inferred_intent=f"Audio validation failed: {error_msg}",
            what_needs_verification=["Invalid audio buffer."],
            recommended_next_steps=["Provide a valid WAV, MP3, OGG, or WEBM audio file under 25 MB."],
            privacy_warnings=[],
            status=status,
            analysis_duration_ms=duration_ms,
            created_at=time.time(),
        )

    def _log_audit(self, session_id: str, event_type: str, details: Dict[str, Any]) -> None:
        """Write voice lifecycle transitions to SQLite without storing raw audio bytes."""
        if not self.db:
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO sessions (id, mode) VALUES (?, ?)",
                    (session_id, "voice"),
                )
                cursor.execute(
                    """
                    INSERT INTO diagnostics (id, session_id, tool_name, status, evidence_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"voice_{int(time.time() * 1000)}",
                        session_id,
                        f"voice:{event_type}",
                        "SUCCESS",
                        json.dumps(details),
                    ),
                )
        except Exception as ex:
            logger.debug("Failed to record voice audit log: %s", ex)


default_voice_orchestrator = VoiceDiagnosticOrchestrator()
