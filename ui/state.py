"""UI Session State and Lifecycle Management for WinFix AI (Phase 20).

Provides centralized, typed session state management, state transition guards,
stale result invalidators, and confirmation replay protection.
Strictly adheres to: LLM != Windows Shell and UI != Execution Layer.
"""

from enum import Enum
import hashlib
import logging
from typing import Any, Dict, List, Optional, Set, Union
import uuid

logger = logging.getLogger(__name__)


class AppMode(str, Enum):
    """Supported WinFix AI operating modes."""

    DIAGNOSTIC = "🔍 Diagnostic & Repair Assistant"
    TUTOR = "🎓 Personal Tutor Mode"
    AUTOPILOT = "🤖 Autopilot Mode"
    SCREENSHOT = "📷 Screenshot Diagnostics"
    VOICE = "🎤 Voice Diagnostics"


MODE_DESCRIPTIONS: Dict[str, str] = {
    AppMode.DIAGNOSTIC.value: "Diagnose Windows problems, explain findings, and safely perform approved repairs.",
    AppMode.TUTOR.value: "Learn what Windows is doing and why a diagnostic or repair may be needed.",
    AppMode.AUTOPILOT.value: "Run a bounded, verified troubleshooting plan with explicit authorization.",
    AppMode.SCREENSHOT.value: "Analyze visible Windows error information without treating screenshot text as instructions.",
    AppMode.VOICE.value: "Use local speech recognition to describe a Windows problem.",
}


class UIStatusState(str, Enum):
    """Standardized UI lifecycle and execution states (Phase 35)."""

    IDLE = "IDLE"
    LOADING = "LOADING"
    ANALYZING = "ANALYZING"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    UNRESOLVED = "UNRESOLVED"
    CANCELLED = "CANCELLED"
    RECOVERING = "RECOVERING"
    OFFLINE = "OFFLINE"


class UIStateManager:
    """Manages Streamlit session state keys, transition guards, and cache invalidation."""

    def __init__(self, state_dict: Optional[Dict[str, Any]] = None) -> None:
        self._state = state_dict if state_dict is not None else {}
        self._init_defaults()

    def _init_defaults(self) -> None:
        """Ensure all required UI session keys exist with deterministic defaults."""
        defaults: Dict[str, Any] = {
            "session_id": f"sess_{uuid.uuid4().hex[:12]}",
            "current_mode": AppMode.DIAGNOSTIC.value,
            "current_ui_status": UIStatusState.IDLE.value,
            "show_welcome_guide": True,
            "active_problem": "",
            "active_problem_hash": "",
            "last_diag_result": None,
            "last_diag_hash": None,
            "last_repair_proposal": None,
            "last_repair_result": None,
            "last_verification_result": None,
            "pending_confirmation_token": None,
            "executed_repair_tokens": set(),
            "current_transcript": "",
            "current_transcript_hash": "",
            "current_screenshot_analysis": None,
            "current_screenshot_hash": "",
            "current_autopilot_plan": None,
            "current_autopilot_plan_hash": "",
            "is_repair_running": False,
            "ui_error_state": None,
            "active_workflow_step": "INPUT",
            "interrupted_session_id": None,
            "recovery_state": None,
        }
        for key, val in defaults.items():
            if key not in self._state:
                self._state[key] = val

    @property
    def session_id(self) -> str:
        return str(self._state.get("session_id", "sess_default"))

    @property
    def current_mode(self) -> str:
        return str(self._state.get("current_mode", AppMode.DIAGNOSTIC.value))

    def set_mode(self, new_mode: str) -> None:
        """Switch operating mode and safely reset mode-specific transient state."""
        if new_mode != self._state.get("current_mode"):
            logger.debug("Switching UI mode from '%s' to '%s'", self._state.get("current_mode"), new_mode)
            self._state["current_mode"] = new_mode
            self.reset_transient_mode_state()

    def reset_transient_mode_state(self) -> None:
        """Reset transient state when switching modes without invalidating overall session."""
        self._state["pending_confirmation_token"] = None
        self._state["is_repair_running"] = False
        self._state["ui_error_state"] = None
        self._state["active_workflow_step"] = "INPUT"

    def set_active_problem(self, problem_text: str) -> bool:
        """Set active problem description. If text changed, invalidate stale diagnostic results."""
        clean_text = problem_text.strip() if problem_text else ""
        new_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        old_hash = self._state.get("active_problem_hash", "")

        if new_hash != old_hash:
            logger.debug("Problem text changed. Invalidating stale diagnostic and repair proposals.")
            self._state["active_problem"] = clean_text
            self._state["active_problem_hash"] = new_hash
            self.invalidate_stale_results()
            return True
        return False

    def set_diagnostic_result(self, result: Dict[str, Any]) -> None:
        """Store fresh diagnostic result and compute result hash."""
        self._state["last_diag_result"] = result
        res_str = str(result.get("synthesis", "")) + str(result.get("tool_results", []))
        self._state["last_diag_hash"] = hashlib.sha256(res_str.encode("utf-8")).hexdigest()
        self._state["active_workflow_step"] = "DIAGNOSTIC"

    def set_voice_transcript(self, transcript: str) -> bool:
        """Set voice transcript. If changed, invalidate stale voice diagnostics."""
        clean = transcript.strip() if transcript else ""
        new_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        if new_hash != self._state.get("current_transcript_hash", ""):
            self._state["current_transcript"] = clean
            self._state["current_transcript_hash"] = new_hash
            self._state["last_diag_result"] = None
            self._state["last_repair_proposal"] = None
            return True
        return False

    def set_screenshot_analysis(self, analysis: Any, image_hash: str) -> bool:
        """Set screenshot analysis. If image changed, invalidate stale evidence."""
        if image_hash != self._state.get("current_screenshot_hash", ""):
            self._state["current_screenshot_analysis"] = analysis
            self._state["current_screenshot_hash"] = image_hash
            self._state["last_diag_result"] = None
            self._state["last_repair_proposal"] = None
            return True
        return False

    def invalidate_stale_results(self) -> None:
        """Invalidate diagnostic results, proposals, and pending confirmations."""
        self._state["last_diag_result"] = None
        self._state["last_diag_hash"] = None
        self._state["last_repair_proposal"] = None
        self._state["last_repair_result"] = None
        self._state["last_verification_result"] = None
        self._state["pending_confirmation_token"] = None
        self._state["active_workflow_step"] = "INPUT"

    def can_execute_repair(self, proposal_token: str) -> bool:
        """Verify confirmation token is valid and has not been executed previously (Replay Protection)."""
        if not proposal_token or not isinstance(proposal_token, str):
            return False
        executed_tokens: Set[str] = self._state.get("executed_repair_tokens", set())
        if proposal_token in executed_tokens:
            logger.warning("Replay attempt blocked: repair token '%s' was already executed.", proposal_token)
            return False
        return True

    @property
    def ui_status(self) -> str:
        return str(self._state.get("current_ui_status", UIStatusState.IDLE.value))

    def set_ui_status(self, status: Union[UIStatusState, str]) -> None:
        """Update current UI lifecycle state."""
        st_val = status.value if isinstance(status, UIStatusState) else str(status).upper()
        self._state["current_ui_status"] = st_val

    @property
    def show_welcome_guide(self) -> bool:
        return bool(self._state.get("show_welcome_guide", True))

    def dismiss_welcome_guide(self) -> None:
        """Dismiss first-run education banner."""
        self._state["show_welcome_guide"] = False

    def set_interrupted_session(self, session_id: str, recovery_state: Dict[str, Any]) -> None:
        """Track interrupted session found for safe resume."""
        self._state["interrupted_session_id"] = session_id
        self._state["recovery_state"] = recovery_state
        self._state["current_ui_status"] = UIStatusState.RECOVERING.value

    def clear_interrupted_session(self) -> None:
        """Clear interrupted session when resolved or discarded."""
        self._state["interrupted_session_id"] = None
        self._state["recovery_state"] = None
        if self._state.get("current_ui_status") == UIStatusState.RECOVERING.value:
            self._state["current_ui_status"] = UIStatusState.IDLE.value

    def mark_repair_executed(self, proposal_token: str, result: Dict[str, Any]) -> None:
        """Mark confirmation token as executed to prevent Streamlit rerun replay."""
        if "executed_repair_tokens" not in self._state:
            self._state["executed_repair_tokens"] = set()
        self._state["executed_repair_tokens"].add(proposal_token)
        self._state["last_repair_result"] = result
        self._state["pending_confirmation_token"] = None
        self._state["is_repair_running"] = False
        self._state["active_workflow_step"] = "VERIFICATION"
        self._state["current_ui_status"] = UIStatusState.VERIFYING.value

    def set_verification_result(self, result: Dict[str, Any]) -> None:
        """Record final deterministic verification outcome."""
        self._state["last_verification_result"] = result
        self._state["active_workflow_step"] = "VERIFICATION"
        v_status = str(result.get("status") or result.get("verification_status") or "").lower()
        if v_status in ("verified", "success"):
            self._state["current_ui_status"] = UIStatusState.SUCCESS.value
        elif "partial" in v_status:
            self._state["current_ui_status"] = UIStatusState.PARTIAL_SUCCESS.value
        elif v_status in ("failed", "blocked", "error"):
            self._state["current_ui_status"] = UIStatusState.FAILED.value
        else:
            self._state["current_ui_status"] = UIStatusState.UNRESOLVED.value

    def set_error(self, title: str, message: str, recovery_steps: Optional[List[str]] = None) -> None:
        """Set structured UI error state."""
        self._state["ui_error_state"] = {
            "title": title,
            "message": message,
            "recovery_steps": recovery_steps or [],
        }
        self._state["current_ui_status"] = UIStatusState.FAILED.value

    def clear_error(self) -> None:
        """Clear current UI error state."""
        self._state["ui_error_state"] = None
        if self._state.get("current_ui_status") == UIStatusState.FAILED.value:
            self._state["current_ui_status"] = UIStatusState.IDLE.value
