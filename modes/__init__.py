"""Operational modes module for WinFix AI (Tutor, Autopilot)."""

from modes.autopilot import (
    AutopilotEngine,
    compute_plan_hash,
    default_autopilot_engine,
    evaluate_precondition,
)
from modes.autopilot_models import (
    AutopilotPlan,
    AutopilotPrecondition,
    AutopilotResult,
    AutopilotStatus,
    AutopilotStep,
    AutopilotStepResult,
    PreconditionOperator,
)
from modes.personal_tutor import PersonalTutor, default_personal_tutor
from modes.tutor_context import TutorContext, sanitize_tutor_payload, sanitize_tutor_text
from modes.tutor_models import TutorExplanationRequest, TutorResponse, TutorSeverity

__all__ = [
    "PersonalTutor",
    "default_personal_tutor",
    "TutorContext",
    "sanitize_tutor_text",
    "sanitize_tutor_payload",
    "TutorSeverity",
    "TutorResponse",
    "TutorExplanationRequest",
    "AutopilotEngine",
    "default_autopilot_engine",
    "compute_plan_hash",
    "evaluate_precondition",
    "AutopilotStatus",
    "PreconditionOperator",
    "AutopilotPrecondition",
    "AutopilotStep",
    "AutopilotStepResult",
    "AutopilotPlan",
    "AutopilotResult",
]
