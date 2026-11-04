"""WinFix AI — Multimodal Evidence Adapter.

Bridges multimodal inputs (Screenshots, Voice Transcripts, and User Text) to the
unified Evidence Model, EvidenceStore, Diagnostic Engine, and Autopilot Workflow Engine.

Strict Security Invariants:
1. Multimodal Input != Windows Command.
2. Multimodal Input != Repair Authorization.
3. LLM / Vision / STT != Windows Shell.
4. Input Type != Operating Mode (Operating mode determines workflow execution).
"""

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from agent.evidence_models import (
    DEFAULT_EVIDENCE_TTLS,
    EvidenceItem,
    EvidenceNormalizer,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
    default_evidence_store,
)
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from input.screenshot_models import (
    ScreenshotAnalysis,
    ScreenshotAnalysisStatus,
    ScreenshotEvidence,
    ScreenshotObservation,
)
from input.voice_models import (
    VoiceAnalysis,
    VoiceDiagnosticCategory,
    VoiceStatus,
    VoiceTranscript,
)
from modes.autopilot_models import AutopilotPlan, AutopilotStep
from modes.tutor_models import ProblemInput, StructuredProblem
from agent.intent_classifier import UserIntent, default_intent_classifier

logger = logging.getLogger("winfix.MULTIMODAL_ADAPTER")


class MultimodalEvidenceAdapter:
    """Normalizes and routes multimodal evidence into the unified WinFix AI engine."""

    def __init__(
        self,
        evidence_store: Optional[EvidenceStore] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.evidence_store = evidence_store or default_evidence_store
        self.tool_registry = tool_registry or default_tool_registry

    def ingest_problem_input(
        self,
        problem_input: ProblemInput,
    ) -> List[EvidenceItem]:
        """Normalize all elements of a ProblemInput into the EvidenceStore preserving source and quality."""
        items: List[EvidenceItem] = []
        now_str = problem_input.timestamp or datetime.now(timezone.utc).isoformat()
        session_id = problem_input.session_id or f"problem_in_{int(datetime.now().timestamp())}"

        # 1. User Text (source = USER, quality = USER_REPORTED)
        if problem_input.text and problem_input.text.strip():
            u_clean = EvidenceNormalizer.sanitize_text(problem_input.text.strip())
            u_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.USER_REPORTED,
                source=EvidenceSource.USER,
                category="user_reported_text",
                observation=f"User stated: {u_clean}",
                value={"text": u_clean},
                status=EvidenceStatus.VALID,
                quality=EvidenceQuality.USER_REPORTED,
                timestamp=now_str,
                session_id=session_id,
                provenance="UserInputText",
                ttl_seconds=DEFAULT_EVIDENCE_TTLS.get(EvidenceType.USER_REPORTED, 300),
            )
            items.append(u_item)
            self.evidence_store.add_evidence(u_item)

        # 2. User Context if provided
        if problem_input.user_context and problem_input.user_context.strip():
            ctx_clean = EvidenceNormalizer.sanitize_text(problem_input.user_context.strip())
            ctx_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.USER_REPORTED,
                source=EvidenceSource.USER,
                category="user_context",
                observation=f"User context: {ctx_clean}",
                value={"context": ctx_clean},
                status=EvidenceStatus.VALID,
                quality=EvidenceQuality.USER_REPORTED,
                timestamp=now_str,
                session_id=session_id,
                provenance="UserContext",
                ttl_seconds=DEFAULT_EVIDENCE_TTLS.get(EvidenceType.USER_REPORTED, 300),
            )
            items.append(ctx_item)
            self.evidence_store.add_evidence(ctx_item)

        # 3. Voice Transcript (source = VOICE, quality = USER_REPORTED)
        if problem_input.voice_transcript and problem_input.voice_transcript.strip():
            v_clean = EvidenceNormalizer.sanitize_text(problem_input.voice_transcript.strip())
            v_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.VOICE,
                source=EvidenceSource.VOICE,
                category="voice_transcript",
                observation=f"Voice transcript: {v_clean}",
                value={"transcript": v_clean},
                status=EvidenceStatus.VALID,
                quality=EvidenceQuality.USER_REPORTED,
                timestamp=now_str,
                session_id=session_id,
                provenance="VoiceTranscriber",
                ttl_seconds=DEFAULT_EVIDENCE_TTLS.get(EvidenceType.VOICE, 300),
            )
            items.append(v_item)
            self.evidence_store.add_evidence(v_item)

        # 4. Screenshot Evidence (source = SCREENSHOT, quality = INFERRED)
        if problem_input.screenshot_evidence:
            for s_ev in problem_input.screenshot_evidence:
                obs_str = EvidenceNormalizer.sanitize_text(str(s_ev))
                s_item = EvidenceItem(
                    evidence_id=str(uuid.uuid4())[:8],
                    evidence_type=EvidenceType.SCREENSHOT,
                    source=EvidenceSource.SCREENSHOT,
                    category="screenshot_observation",
                    observation=obs_str,
                    value={"evidence": s_ev},
                    status=EvidenceStatus.VALID,
                    quality=EvidenceQuality.INFERRED,
                    timestamp=now_str,
                    session_id=session_id,
                    provenance="ScreenshotEvidence",
                    ttl_seconds=DEFAULT_EVIDENCE_TTLS.get(EvidenceType.SCREENSHOT, 300),
                )
                items.append(s_item)
                self.evidence_store.add_evidence(s_item)

        return items

    def understand_problem(
        self,
        problem_input: ProblemInput,
        diagnostic_data: Optional[Dict[str, Any]] = None,
        system_info: Optional[Dict[str, Any]] = None,
    ) -> StructuredProblem:
        """Analyze multimodal problem input, ingest into EvidenceStore, identify domain, symptoms, hypotheses, and conflicts."""
        # 1. Ingest into EvidenceStore
        self.ingest_problem_input(problem_input)

        parts = []
        if problem_input.text and problem_input.text.strip():
            parts.append(problem_input.text.strip())
        if problem_input.voice_transcript and problem_input.voice_transcript.strip():
            parts.append(f"Voice: {problem_input.voice_transcript.strip()}")
        if problem_input.user_context and problem_input.user_context.strip():
            parts.append(problem_input.user_context.strip())
        if problem_input.screenshot_evidence:
            parts.append(f"Screenshot: {', '.join(str(e) for e in problem_input.screenshot_evidence)}")

        full_text = " ".join(parts).lower()

        # 2. Domain classification
        domain = "general"
        if any(w in full_text for w in ["wifi", "wi-fi", "wireless", "network", "internet", "dns", "ip", "dhcp", "gateway", "ping", "disconnect", "connect", "ethernet", "router"]):
            domain = "network"
        elif any(w in full_text for w in ["audio", "sound", "volume", "speaker", "headphone", "mic", "microphone"]):
            domain = "audio"
        elif any(w in full_text for w in ["storage", "disk", "drive", "space", "temp", "cache", "full"]):
            domain = "storage"
        elif any(w in full_text for w in ["slow", "lag", "cpu", "ram", "memory", "usage", "performance", "high cpu", "bottleneck"]):
            domain = "performance"
        elif any(w in full_text for w in ["update", "wuauserv", "patch", "upgrade", "kb"]):
            domain = "windows_update"
        elif any(w in full_text for w in ["bluetooth", "bthserv", "pair", "bt"]):
            domain = "bluetooth"
        elif any(w in full_text for w in ["defender", "virus", "malware", "firewall", "antivirus", "threat"]):
            domain = "defender"
        elif any(w in full_text for w in ["crash", "freeze", "hang", "bsod", "fault", "wer", "unresponsive"]):
            domain = "application_crash"
        elif any(w in full_text for w in ["service", "services", "daemon"]):
            domain = "services"

        # 3. Detect Contradictions / Conflicts
        conflicts = []
        if diagnostic_data:
            if domain == "network":
                adapters = diagnostic_data.get("network_adapters", {})
                active_count = adapters.get("data", {}).get("active_adapters", 0) if isinstance(adapters, dict) else 0
                if "disconnect" in full_text and active_count > 0:
                    conflicts.append("User reports disconnection, but Windows reports active network adapters.")
            elif domain == "storage":
                st = diagnostic_data.get("storage", {})
                free_gb = st.get("data", {}).get("free_gb", 100) if isinstance(st, dict) else 100
                if "disk is full" in full_text and free_gb > 20:
                    conflicts.append("User reports disk is full, but drive has substantial free storage capacity.")

        # 4. Symptoms Extraction
        known_symptoms = [
            ("wifi_disconnects_intermittently", ["wifi", "disconnect"]),
            ("dns_resolution_failing", ["dns", "resolve", "website"]),
            ("high_cpu_utilization", ["cpu", "slow", "processor"]),
            ("storage_space_low", ["storage", "disk", "full", "space"]),
            ("bluetooth_unpaired", ["bluetooth", "pair", "unpair"]),
            ("service_stopped", ["service", "stopped", "wuauserv"]),
        ]
        symptoms = []
        for sym_id, keywords in known_symptoms:
            if all(k in full_text for k in keywords):
                symptoms.append(sym_id)
        if not symptoms:
            symptoms = ["user_reported_anomaly"]

        # 5. User Goal
        goals = {
            "network": "Restore stable internet and local network connectivity.",
            "storage": "Reclaim disk space and clean safe temporary files.",
            "performance": "Reduce processor/RAM pressure and restore system responsiveness.",
            "bluetooth": "Restore Bluetooth device pairing and service operation.",
            "windows_update": "Clear update queue bottlenecks and verify update service.",
            "defender": "Verify real-time protection and antivirus threat status.",
            "application_crash": "Identify faulting module and stabilize crashing application.",
            "services": "Verify critical Windows service execution states.",
        }
        user_goal = goals.get(domain, "Investigate system state and provide safe resolution guidance.")

        return StructuredProblem(
            problem=" | ".join(parts) if parts else "General Windows diagnostic inquiry",
            domain=domain,
            symptoms=symptoms,
            severity="NORMAL",
            confidence=0.88,
            user_goal=user_goal,
            hypotheses=[f"Diagnostic anomaly in Windows {domain} subsystem."],
            candidate_tools=[],
            conflicting_evidence=conflicts,
        )

    def normalize_screenshot_analysis(
        self,
        analysis: ScreenshotAnalysis,
        user_context: Optional[str] = None,
        session_id: str = "default_session",
    ) -> List[EvidenceItem]:
        """Convert a structured ScreenshotAnalysis into normalized EvidenceItem records."""
        items: List[EvidenceItem] = []
        now_str = datetime.now(timezone.utc).isoformat()
        ttl = DEFAULT_EVIDENCE_TTLS.get(EvidenceType.SCREENSHOT, 300)

        # 1. Normalized User Context if provided
        if user_context and user_context.strip():
            u_sanitized = EvidenceNormalizer.sanitize_text(user_context)
            u_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.USER_REPORTED,
                source=EvidenceSource.USER,
                category="user_inquiry",
                observation=u_sanitized,
                value={"user_context": u_sanitized},
                status=EvidenceStatus.VALID,
                quality=EvidenceQuality.USER_REPORTED,
                timestamp=now_str,
                session_id=session_id,
                provenance="UserPromptWithScreenshot",
                ttl_seconds=ttl,
            )
            items.append(u_item)
            self.evidence_store.add_evidence(u_item)

        # 2. Check Vision Analysis Status
        status_val = analysis.status.value if hasattr(analysis.status, "value") else str(analysis.status).upper()
        if status_val not in ["SUCCESS", "VISION_SUCCESS"]:
            # Record that visual analysis was unavailable without inventing observations
            status_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.SCREENSHOT,
                source=EvidenceSource.SCREENSHOT,
                category="vision_status",
                observation=f"Screenshot received but visual extraction status is '{status_val}'.",
                value={"status": status_val, "summary": analysis.visible_facts_summary},
                status=EvidenceStatus.UNAVAILABLE,
                quality=EvidenceQuality.INFERRED,
                timestamp=now_str,
                session_id=session_id,
                provenance="ScreenshotVisionAnalyzer",
                ttl_seconds=ttl,
            )
            items.append(status_item)
            self.evidence_store.add_evidence(status_item)
            return items

        # 3. Primary visual facts summary
        if analysis.visible_facts_summary and analysis.visible_facts_summary.strip():
            summary_sanitized = EvidenceNormalizer.sanitize_text(analysis.visible_facts_summary)
            s_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.SCREENSHOT,
                source=EvidenceSource.SCREENSHOT,
                category="visual_summary",
                observation=summary_sanitized,
                value={"summary": summary_sanitized},
                status=EvidenceStatus.VALID,
                quality=EvidenceQuality.INFERRED,
                timestamp=now_str,
                session_id=session_id,
                provenance="ScreenshotVisionAnalyzer",
                ttl_seconds=ttl,
            )
            items.append(s_item)
            self.evidence_store.add_evidence(s_item)

        # 4. Detected Error Codes
        if analysis.evidence and analysis.evidence.detected_error_codes:
            for ec in analysis.evidence.detected_error_codes:
                ec_clean = EvidenceNormalizer.sanitize_text(ec)
                ec_item = EvidenceItem(
                    evidence_id=str(uuid.uuid4())[:8],
                    evidence_type=EvidenceType.SCREENSHOT,
                    source=EvidenceSource.SCREENSHOT,
                    category="error_code",
                    observation=f"Visible Windows error code: {ec_clean}",
                    value={"error_code": ec_clean},
                    status=EvidenceStatus.VALID,
                    quality=EvidenceQuality.INFERRED,
                    timestamp=now_str,
                    session_id=session_id,
                    provenance="ScreenshotVisionAnalyzer",
                    ttl_seconds=ttl,
                )
                items.append(ec_item)
                self.evidence_store.add_evidence(ec_item)

        # 5. Detected Event IDs
        if analysis.evidence and analysis.evidence.detected_event_ids:
            for eid in analysis.evidence.detected_event_ids:
                eid_clean = EvidenceNormalizer.sanitize_text(str(eid))
                eid_item = EvidenceItem(
                    evidence_id=str(uuid.uuid4())[:8],
                    evidence_type=EvidenceType.SCREENSHOT,
                    source=EvidenceSource.SCREENSHOT,
                    category="event_id",
                    observation=f"Visible Windows Event ID: {eid_clean}",
                    value={"event_id": eid_clean},
                    status=EvidenceStatus.VALID,
                    quality=EvidenceQuality.INFERRED,
                    timestamp=now_str,
                    session_id=session_id,
                    provenance="ScreenshotVisionAnalyzer",
                    ttl_seconds=ttl,
                )
                items.append(eid_item)
                self.evidence_store.add_evidence(eid_item)

        # 6. Detected Applications
        if analysis.evidence and analysis.evidence.detected_applications:
            for app in analysis.evidence.detected_applications:
                app_clean = EvidenceNormalizer.sanitize_text(app)
                app_item = EvidenceItem(
                    evidence_id=str(uuid.uuid4())[:8],
                    evidence_type=EvidenceType.SCREENSHOT,
                    source=EvidenceSource.SCREENSHOT,
                    category="application",
                    observation=f"Visible application context: {app_clean}",
                    value={"application": app_clean},
                    status=EvidenceStatus.VALID,
                    quality=EvidenceQuality.INFERRED,
                    timestamp=now_str,
                    session_id=session_id,
                    provenance="ScreenshotVisionAnalyzer",
                    ttl_seconds=ttl,
                )
                items.append(app_item)
                self.evidence_store.add_evidence(app_item)

        # 7. Granular observations
        if analysis.evidence and analysis.evidence.observations:
            for obs in analysis.evidence.observations:
                obs_text = EvidenceNormalizer.sanitize_text(obs.text)
                if obs_text:
                    obs_item = EvidenceItem(
                        evidence_id=str(uuid.uuid4())[:8],
                        evidence_type=EvidenceType.SCREENSHOT,
                        source=EvidenceSource.SCREENSHOT,
                        category=obs.category.lower(),
                        observation=obs_text,
                        value={"category": obs.category, "confidence": obs.confidence, "location": obs.location},
                        status=EvidenceStatus.VALID,
                        quality=EvidenceQuality.INFERRED,
                        timestamp=now_str,
                        session_id=session_id,
                        provenance="ScreenshotVisionAnalyzer",
                        ttl_seconds=ttl,
                    )
                    items.append(obs_item)
                    self.evidence_store.add_evidence(obs_item)

        return items

    def normalize_voice_analysis(
        self,
        analysis: VoiceAnalysis,
        user_context: Optional[str] = None,
        session_id: str = "default_session",
    ) -> List[EvidenceItem]:
        """Convert a structured VoiceAnalysis into normalized EvidenceItem records."""
        items: List[EvidenceItem] = []
        now_str = datetime.now(timezone.utc).isoformat()
        ttl = DEFAULT_EVIDENCE_TTLS.get(EvidenceType.VOICE, 300)

        # 1. User Context if typed in conjunction with audio
        if user_context and user_context.strip():
            u_sanitized = EvidenceNormalizer.sanitize_text(user_context)
            u_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.USER_REPORTED,
                source=EvidenceSource.USER,
                category="user_inquiry",
                observation=u_sanitized,
                value={"user_context": u_sanitized},
                status=EvidenceStatus.VALID,
                quality=EvidenceQuality.USER_REPORTED,
                timestamp=now_str,
                session_id=session_id,
                provenance="UserPromptWithVoice",
                ttl_seconds=ttl,
            )
            items.append(u_item)
            self.evidence_store.add_evidence(u_item)

        # 2. Check Voice Transcription Status
        st_val = analysis.status.value if hasattr(analysis.status, "value") else str(analysis.status).upper()
        if st_val not in [VoiceStatus.COMPLETED.value, VoiceStatus.READY.value, "COMPLETED", "READY"]:
            status_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.VOICE,
                source=EvidenceSource.VOICE,
                category="voice_status",
                observation=f"Voice audio received but transcription status is '{st_val}'.",
                value={"status": st_val},
                status=EvidenceStatus.UNAVAILABLE,
                quality=EvidenceQuality.USER_REPORTED,
                timestamp=now_str,
                session_id=session_id,
                provenance="VoiceTranscriber",
                ttl_seconds=ttl,
            )
            items.append(status_item)
            self.evidence_store.add_evidence(status_item)
            return items

        # 3. Transcribed Speech
        if analysis.transcript and analysis.transcript.sanitized_text and analysis.transcript.sanitized_text.strip():
            t_text = EvidenceNormalizer.sanitize_text(analysis.transcript.sanitized_text)
            t_item = EvidenceItem(
                evidence_id=str(uuid.uuid4())[:8],
                evidence_type=EvidenceType.VOICE,
                source=EvidenceSource.VOICE,
                category="voice_transcript",
                observation=f"User spoken statement: {t_text}",
                value={
                    "transcript": t_text,
                    "confidence": analysis.transcript.confidence,
                    "model_used": analysis.transcript.model_used,
                },
                status=EvidenceStatus.VALID,
                quality=EvidenceQuality.USER_REPORTED,
                timestamp=now_str,
                session_id=session_id,
                provenance="VoiceTranscriber",
                ttl_seconds=ttl,
            )
            items.append(t_item)
            self.evidence_store.add_evidence(t_item)

        # 4. Inferred problem category from hints or intent
        if analysis.hints:
            for h in analysis.hints:
                cat_val = getattr(h, "category", "")
                if cat_val and cat_val != "UNKNOWN":
                    cat_item = EvidenceItem(
                        evidence_id=str(uuid.uuid4())[:8],
                        evidence_type=EvidenceType.VOICE,
                        source=EvidenceSource.VOICE,
                        category="inferred_domain",
                        observation=f"Inferred voice problem domain: {str(cat_val).lower().replace('_', ' ')}",
                        value={"category": str(cat_val)},
                        status=EvidenceStatus.VALID,
                        quality=EvidenceQuality.INFERRED,
                        timestamp=now_str,
                        session_id=session_id,
                        provenance="VoiceDiagnosticMapper",
                        ttl_seconds=ttl,
                    )
                    items.append(cat_item)
                    self.evidence_store.add_evidence(cat_item)

        return items

    def synthesize_problem_description(
        self,
        screenshot_analysis: Optional[ScreenshotAnalysis] = None,
        voice_analysis: Optional[VoiceAnalysis] = None,
        user_text: Optional[str] = None,
    ) -> Tuple[str, List[str]]:
        """Synthesize a unified, safe problem description and collect candidate tool names from multimodal inputs."""
        parts: List[str] = []
        candidate_tools: Set[str] = set()

        # 1. User Text context
        if user_text and user_text.strip():
            parts.append(EvidenceNormalizer.sanitize_text(user_text.strip()))

        # 2. Voice transcript
        if voice_analysis and voice_analysis.transcript and voice_analysis.transcript.sanitized_text:
            cleaned_voice = EvidenceNormalizer.sanitize_text(voice_analysis.transcript.sanitized_text.strip())
            if cleaned_voice:
                parts.append(f"Voice report: {cleaned_voice}")
            if voice_analysis.hints:
                for h in voice_analysis.hints:
                    for t in h.candidate_tools:
                        if self.tool_registry.get(t):
                            candidate_tools.add(t)

        # 3. Screenshot observations
        if screenshot_analysis:
            status_val = screenshot_analysis.status.value if hasattr(screenshot_analysis.status, "value") else str(screenshot_analysis.status).upper()
            if status_val in ["SUCCESS", "VISION_SUCCESS"]:
                if screenshot_analysis.visible_facts_summary:
                    cleaned_facts = EvidenceNormalizer.sanitize_text(screenshot_analysis.visible_facts_summary.strip())
                    if cleaned_facts:
                        parts.append(f"Visual evidence: {cleaned_facts}")
                if screenshot_analysis.evidence and screenshot_analysis.evidence.detected_error_codes:
                    codes = ", ".join(screenshot_analysis.evidence.detected_error_codes)
                    parts.append(f"Error codes: {codes}")
                if screenshot_analysis.diagnostic_hints:
                    for hint in screenshot_analysis.diagnostic_hints:
                        t_name = getattr(hint, "tool_name", "")
                        if self.tool_registry.get(t_name):
                            candidate_tools.add(t_name)

        if not parts:
            return "General Windows system diagnostic inspection.", sorted(candidate_tools)

        unified_description = " | ".join(parts)
        return unified_description, sorted(candidate_tools)

    def formulate_autopilot_plan(
        self,
        autopilot_engine: Any,
        screenshot_analysis: Optional[ScreenshotAnalysis] = None,
        voice_analysis: Optional[VoiceAnalysis] = None,
        user_text: Optional[str] = None,
        diagnostic_data: Optional[Dict[str, Any]] = None,
        system_info: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> AutopilotPlan:
        """Formulate a bounded AutopilotPlan from multimodal evidence sources.

        Enforces that multimodal evidence only suggests problem scope and candidate tools;
        the plan is strictly bounded, validated against ToolRegistry and SafetyEngine,
        and requires user authorization before any repair step executes.
        """
        sess_id = session_id or f"multimodal_auto_{int(datetime.now().timestamp())}"

        # 1. Normalize all inputs into EvidenceStore
        if screenshot_analysis:
            self.normalize_screenshot_analysis(screenshot_analysis, user_context=user_text, session_id=sess_id)
        if voice_analysis:
            self.normalize_voice_analysis(voice_analysis, user_context=user_text, session_id=sess_id)

        # 2. Synthesize unified problem description
        problem_desc, candidate_tools = self.synthesize_problem_description(
            screenshot_analysis=screenshot_analysis,
            voice_analysis=voice_analysis,
            user_text=user_text,
        )

        # 3. Call standard AutopilotEngine.plan
        plan: AutopilotPlan = autopilot_engine.plan(
            problem_description=problem_desc,
            diagnostic_data=diagnostic_data,
            system_info=system_info,
            session_id=sess_id,
        )

        # 4. If candidate diagnostic tools were identified and not yet in plan, prepend safe read-only diagnostics if space permits
        if candidate_tools and len(plan.steps) < 5:
            existing_tool_names = {s.tool_name for s in plan.steps}
            new_steps: List[AutopilotStep] = []
            seq = 1

            for c_tool in candidate_tools:
                if c_tool not in existing_tool_names and len(new_steps) + len(plan.steps) < 5:
                    tool_def = self.tool_registry.get(c_tool)
                    if tool_def and tool_def.risk == RiskLevel.SAFE and tool_def.read_only:
                        new_step = AutopilotStep(
                            step_id=f"step_{seq}_{c_tool}",
                            sequence=seq,
                            tool_name=c_tool,
                            arguments={},
                            purpose=f"Multimodal diagnostic check: {tool_def.description}",
                            expected_result=f"Valid execution output from {c_tool}.",
                            risk_level=tool_def.risk.value,
                            requires_admin=tool_def.requires_admin,
                            verification_required=False,
                        )
                        new_steps.append(new_step)
                        seq += 1

            if new_steps:
                # Re-index remaining steps
                for s in plan.steps:
                    s.sequence = seq
                    seq += 1
                all_steps = new_steps + plan.steps
                raw_dict = {
                    "goal": plan.goal,
                    "steps": [
                        {
                            "sequence": st.sequence,
                            "tool_name": st.tool_name,
                            "arguments": st.arguments,
                            "purpose": st.purpose,
                            "expected_result": st.expected_result,
                            "depends_on": st.depends_on,
                        }
                        for st in all_steps
                    ],
                }
                intent = default_intent_classifier.classify_intent(problem_desc)
                plan = autopilot_engine.validate_and_build_plan(raw_dict, session_id=sess_id, user_intent=intent)

        return plan


default_multimodal_adapter = MultimodalEvidenceAdapter()
