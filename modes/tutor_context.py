"""Context management and privacy sanitization for Personal Tutor Mode (Phase 15).

Ensures that user profiles, sensitive tokens, passwords, and private file paths
are sanitized before being passed into the LLM reasoning context or audit logs.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Patterns for sensitive data matching
USER_PATH_PATTERN = re.compile(r"([a-zA-Z]:\\Users\\)[^\\]+(\\.*)?", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
API_KEY_PATTERN = re.compile(r"\b(?:api_key|token|password|secret|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}['\"]?", re.IGNORECASE)


def sanitize_tutor_text(text: Optional[str]) -> str:
    """Sanitize sensitive personal identifiers and user paths from a string."""
    if not text or not isinstance(text, str):
        return ""

    sanitized = text

    # 1. Mask User Profiles in Windows paths
    sanitized = USER_PATH_PATTERN.sub(r"\1<User>\2", sanitized)

    # 2. Mask Email addresses
    sanitized = EMAIL_PATTERN.sub("<email-masked>", sanitized)

    # 3. Mask Key/Token patterns
    sanitized = API_KEY_PATTERN.sub("<credential-masked>", sanitized)

    return sanitized


def sanitize_tutor_payload(payload: Any) -> Any:
    """Recursively sanitize dictionary, list, or scalar diagnostic payloads."""
    if isinstance(payload, dict):
        return {k: sanitize_tutor_payload(v) for k, v in payload.items()}
    elif isinstance(payload, list):
        return [sanitize_tutor_payload(item) for item in payload]
    elif isinstance(payload, str):
        return sanitize_tutor_text(payload)
    else:
        return payload


@dataclass
class TutorContextEntry:
    """A single bounded entry in the Tutor conversation history."""

    role: str  # "user" or "tutor"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class TutorContext:
    """Bounded, memory-safe context container for Personal Tutor interactions."""

    def __init__(self, session_id: Optional[str] = None, max_history: int = 10) -> None:
        self.session_id = session_id or "default_tutor_session"
        self.max_history = max_history
        self._history: List[TutorContextEntry] = []
        self._latest_diagnostic: Optional[Dict[str, Any]] = None
        self._latest_repair: Optional[Dict[str, Any]] = None

    def add_user_message(self, message: str) -> None:
        """Add a sanitized user question to history."""
        sanitized = sanitize_tutor_text(message)
        self._history.append(TutorContextEntry(role="user", content=sanitized))
        self._trim_history()

    def add_tutor_response(self, summary: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Add a sanitized tutor explanation summary to history."""
        sanitized_summary = sanitize_tutor_text(summary)
        sanitized_meta = sanitize_tutor_payload(details or {})
        self._history.append(TutorContextEntry(role="tutor", content=sanitized_summary, metadata=sanitized_meta))
        self._trim_history()

    def set_latest_diagnostic(self, diagnostic_payload: Dict[str, Any]) -> None:
        """Record the latest diagnostic evidence payload."""
        self._latest_diagnostic = sanitize_tutor_payload(diagnostic_payload)

    def set_latest_repair(self, repair_payload: Dict[str, Any]) -> None:
        """Record the latest repair & verification result payload."""
        self._latest_repair = sanitize_tutor_payload(repair_payload)

    def get_latest_diagnostic(self) -> Optional[Dict[str, Any]]:
        """Retrieve sanitized latest diagnostic snapshot."""
        return self._latest_diagnostic

    def get_latest_repair(self) -> Optional[Dict[str, Any]]:
        """Retrieve sanitized latest repair & verification snapshot."""
        return self._latest_repair

    def get_history_summary(self) -> List[Dict[str, str]]:
        """Return serialized, sanitized conversation history."""
        return [{"role": e.role, "content": e.content} for e in self._history]

    def _trim_history(self) -> None:
        """Enforce maximum history boundary to prevent unbounded memory growth."""
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history :]
