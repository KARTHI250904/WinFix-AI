"""Structured response models and schemas for WinFix AI Personal Tutor Mode (Phase 15).

Defines typed containers for educational diagnostic explanations, evidence separation,
and safe tool recommendations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TutorSeverity(str, Enum):
    """Severity levels supported by Personal Tutor Mode."""

    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class TutorResponse:
    """Structured educational response from Personal Tutor Mode."""

    title: str = "WinFix AI Tutor Explanation"
    summary: str = ""
    what_happened: str = ""
    evidence: List[str] = field(default_factory=list)
    severity: str = "NORMAL"
    severity_explanation: str = ""
    possible_causes: List[str] = field(default_factory=list)
    what_this_means: str = ""
    recommended_next_steps: List[str] = field(default_factory=list)
    recommended_tools: List[str] = field(default_factory=list)
    safety_notes: List[str] = field(default_factory=list)
    verification_explanation: Optional[str] = None
    educational_notes: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    confidence: float = 0.8
    raw_json: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tutor response to standard dictionary."""
        return {
            "title": self.title,
            "summary": self.summary,
            "what_happened": self.what_happened,
            "evidence": list(self.evidence),
            "severity": self.severity,
            "severity_explanation": self.severity_explanation,
            "possible_causes": list(self.possible_causes),
            "what_this_means": self.what_this_means,
            "recommended_next_steps": list(self.recommended_next_steps),
            "recommended_tools": list(self.recommended_tools),
            "safety_notes": list(self.safety_notes),
            "verification_explanation": self.verification_explanation,
            "educational_notes": list(self.educational_notes),
            "limitations": list(self.limitations),
            "confidence": self.confidence,
        }


@dataclass
class TutorExplanationRequest:
    """Input parameters for generating a structured Tutor explanation."""

    user_question: str
    problem_category: Optional[str] = None
    diagnostic_data: Optional[Dict[str, Any]] = None
    repair_data: Optional[Dict[str, Any]] = None
    verification_status: Optional[str] = None
    session_id: Optional[str] = None


class StepStatus(str, Enum):
    """Execution status for a troubleshooting step."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"


@dataclass
class TroubleshootingStep:
    """Individual structured diagnostic or repair step in a troubleshooting flow."""

    step_number: int
    title: str
    purpose: str
    why_it_matters: str
    tool_name: str
    risk: str = "SAFE"  # SAFE | MEDIUM | HIGH
    requires_confirmation: bool = False
    requires_admin: bool = False
    status: StepStatus = StepStatus.PENDING
    result_summary: Optional[str] = None
    finding: Optional[str] = None
    meaning: Optional[str] = None
    next_step_hint: Optional[str] = None
    is_repair: bool = False
    repair_why: Optional[str] = None
    repair_change: Optional[str] = None
    repair_expected_effect: Optional[str] = None
    verification_tool: Optional[str] = None
    verification_status: Optional[str] = None
    raw_output: Optional[Dict[str, Any]] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize step to dictionary."""
        return {
            "step_number": self.step_number,
            "title": self.title,
            "purpose": self.purpose,
            "why_it_matters": self.why_it_matters,
            "tool_name": self.tool_name,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "requires_admin": self.requires_admin,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "result_summary": self.result_summary,
            "finding": self.finding,
            "meaning": self.meaning,
            "next_step_hint": self.next_step_hint,
            "is_repair": self.is_repair,
            "repair_why": self.repair_why,
            "repair_change": self.repair_change,
            "repair_expected_effect": self.repair_expected_effect,
            "verification_tool": self.verification_tool,
            "verification_status": self.verification_status,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ProblemInput:
    """Unified multimodal problem input model across Text, Screenshot, and Voice."""

    session_id: str
    mode: str = "TUTOR"  # "TUTOR" | "AUTOPILOT" | "ASSISTANT"
    text: Optional[str] = None
    screenshot_evidence: List[Any] = field(default_factory=list)
    voice_transcript: Optional[str] = None
    user_context: Optional[str] = None
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize problem input to dictionary."""
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "text": self.text,
            "screenshot_evidence": list(self.screenshot_evidence),
            "voice_transcript": self.voice_transcript,
            "user_context": self.user_context,
            "timestamp": self.timestamp,
        }


@dataclass
class StructuredProblem:
    """Structured, normalized problem definition generated by the understanding layer."""

    problem: str
    domain: str
    symptoms: List[str] = field(default_factory=list)
    severity: str = "NORMAL"
    confidence: float = 0.85
    user_goal: str = ""
    hypotheses: List[str] = field(default_factory=list)
    candidate_tools: List[str] = field(default_factory=list)
    conflicting_evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize structured problem definition."""
        return {
            "problem": self.problem,
            "domain": self.domain,
            "symptoms": list(self.symptoms),
            "severity": self.severity,
            "confidence": self.confidence,
            "user_goal": self.user_goal,
            "hypotheses": list(self.hypotheses),
            "candidate_tools": list(self.candidate_tools),
            "conflicting_evidence": list(self.conflicting_evidence),
        }


@dataclass
class TutorStep:
    """Explicit educational troubleshooting step model with 3-layer diagnostic explanations."""

    step_number: int
    title: str
    explanation: str = ""
    why_this_step: str = ""
    action_type: str = "DIAGNOSTIC"  # "DIAGNOSTIC" | "REPAIR" | "VERIFICATION"
    tool_name: Optional[str] = None
    expected_result: str = ""
    actual_result: Optional[str] = None
    status: str = "PENDING"  # PENDING | RUNNING | PASSED | FAILED | SKIPPED | BLOCKED | VERIFIED | UNRESOLVED
    verification: Optional[str] = None
    what_i_checked: Optional[str] = None
    what_i_found: Optional[str] = None
    what_this_means: Optional[str] = None
    next_step: Optional[str] = None
    risk: str = "SAFE"
    requires_confirmation: bool = False
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tutor step to dictionary."""
        return {
            "step_number": self.step_number,
            "title": self.title,
            "explanation": self.explanation,
            "why_this_step": self.why_this_step,
            "action_type": self.action_type,
            "tool_name": self.tool_name,
            "expected_result": self.expected_result,
            "actual_result": self.actual_result,
            "status": self.status,
            "verification": self.verification,
            "what_i_checked": self.what_i_checked,
            "what_i_found": self.what_i_found,
            "what_this_means": self.what_this_means,
            "next_step": self.next_step,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "duration_ms": self.duration_ms,
        }


@dataclass
class TroubleshootingResponse:
    """Structured natural-language response layer for conversational troubleshooting."""

    title: str
    problem_summary: str
    current_step: int = 1
    explanation: str = ""
    evidence: List[str] = field(default_factory=list)
    what_it_means: str = ""
    next_action: str = ""
    expected_result: str = ""
    verification_status: Optional[str] = None
    limitations: List[str] = field(default_factory=list)
    completion_status: str = "IN_PROGRESS"  # IN_PROGRESS | WAITING_FOR_USER | WAITING_FOR_AUTHORIZATION | RESOLVED | UNRESOLVED | BLOCKED | UNAVAILABLE | CANCELLED

    def to_dict(self) -> Dict[str, Any]:
        """Serialize troubleshooting response to dictionary."""
        return {
            "title": self.title,
            "problem_summary": self.problem_summary,
            "current_step": self.current_step,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "what_it_means": self.what_it_means,
            "next_action": self.next_action,
            "expected_result": self.expected_result,
            "verification_status": self.verification_status,
            "limitations": list(self.limitations),
            "completion_status": self.completion_status,
        }


@dataclass
class TroubleshootingSession:
    """Bounded, adaptive troubleshooting session containing sequential structured steps."""

    session_id: str
    problem_statement: str
    domain: str = "general"
    current_state: str = "CREATED"  # CREATED, UNDERSTANDING, COLLECTING_EVIDENCE, EXPLAINING, GUIDING, AWAITING_CONFIRMATION, REPAIRING, VERIFYING, RESOLVED, REASSESSING, UNRESOLVED, FAILED, CANCELLED
    steps: List[TroubleshootingStep] = field(default_factory=list)
    current_step_index: int = 0
    total_steps: int = 0
    active_hypothesis: str = ""
    is_resolved: bool = False
    resolution_summary: str = ""
    evidence_collected: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize troubleshooting session."""
        return {
            "session_id": self.session_id,
            "problem_statement": self.problem_statement,
            "domain": self.domain,
            "current_state": self.current_state,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "total_steps": self.total_steps or len(self.steps),
            "active_hypothesis": self.active_hypothesis,
            "is_resolved": self.is_resolved,
            "resolution_summary": self.resolution_summary,
            "evidence_collected": list(self.evidence_collected),
        }

