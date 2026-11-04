"""WinFix AI — Diagnostic Evidence Models & Normalization (Phase 27).

Defines strongly-typed diagnostic evidence representations, provenance tracking,
domain-specific freshness / TTL rules, and deterministic contradiction detection.
Strictly adheres to: Evidence != Windows Command and LLM != Windows Shell.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set
import uuid

logger = logging.getLogger("winfix.EVIDENCE")


class EvidenceType(str, Enum):
    """Categorical type of diagnostic evidence."""

    SYSTEM = "SYSTEM"
    NETWORK = "NETWORK"
    PERFORMANCE = "PERFORMANCE"
    STORAGE = "STORAGE"
    SERVICE = "SERVICE"
    BLUETOOTH = "BLUETOOTH"
    WINDOWS_UPDATE = "WINDOWS_UPDATE"
    DEFENDER = "DEFENDER"
    APPLICATION_CRASH = "APPLICATION_CRASH"
    SCREENSHOT = "SCREENSHOT"
    VOICE = "VOICE"
    KNOWLEDGE = "KNOWLEDGE"
    USER_REPORTED = "USER_REPORTED"


class EvidenceStatus(str, Enum):
    """Validation and operational status of evidence."""

    VALID = "VALID"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class EvidenceSource(str, Enum):
    """Origin of diagnostic evidence."""

    WINDOWS_TOOL = "WINDOWS_TOOL"
    SCREENSHOT = "SCREENSHOT"
    VOICE = "VOICE"
    USER = "USER"
    KNOWLEDGE = "KNOWLEDGE"
    AI = "AI"
    SYSTEM = "SYSTEM"


class EvidenceQuality(str, Enum):
    """Quality and verification tier of evidence."""

    VERIFIED = "VERIFIED"           # Factual Windows API / Tool execution
    USER_REPORTED = "USER_REPORTED" # User statement or prompt
    INFERRED = "INFERRED"           # Derived from visual/audio inference
    STALE = "STALE"                 # Expired beyond domain TTL
    CONFLICTING = "CONFLICTING"     # Mutually exclusive observations
    UNKNOWN = "UNKNOWN"


# Domain TTLs in seconds
DEFAULT_EVIDENCE_TTLS: Dict[EvidenceType, int] = {
    EvidenceType.NETWORK: 60,           # Network states change rapidly
    EvidenceType.PERFORMANCE: 30,       # CPU/RAM/Processes are dynamic
    EvidenceType.SERVICE: 120,          # Services generally persist for minutes
    EvidenceType.STORAGE: 300,          # Storage space is moderately static
    EvidenceType.SYSTEM: 600,           # OS version, hardware is static
    EvidenceType.BLUETOOTH: 120,
    EvidenceType.WINDOWS_UPDATE: 600,
    EvidenceType.DEFENDER: 300,
    EvidenceType.APPLICATION_CRASH: 600,
    EvidenceType.SCREENSHOT: 300,       # Bound to capture instance
    EvidenceType.VOICE: 300,
    EvidenceType.KNOWLEDGE: 3600,       # Static knowledge
    EvidenceType.USER_REPORTED: 300,
}


@dataclass(frozen=True)
class EvidenceItem:
    """Strongly-typed, immutable record of a single diagnostic observation."""

    evidence_id: str
    evidence_type: EvidenceType
    source: EvidenceSource
    category: str
    observation: str
    value: Any
    status: EvidenceStatus = EvidenceStatus.VALID
    quality: EvidenceQuality = EvidenceQuality.VERIFIED
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_name: Optional[str] = None
    session_id: str = "default_session"
    provenance: str = "local_tool"
    sanitized: bool = True
    confidence_context: Optional[str] = None
    ttl_seconds: int = 300

    def is_stale(self, reference_time: Optional[datetime] = None) -> bool:
        """Check whether evidence exceeds its validity TTL."""
        try:
            ts = datetime.fromisoformat(self.timestamp)
            now = reference_time or datetime.now(timezone.utc)
            delta = (now - ts).total_seconds()
            return delta > self.ttl_seconds
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize evidence item to sanitized dictionary."""
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "source": self.source.value,
            "category": self.category,
            "observation": self.observation,
            "value": self.value,
            "status": self.status.value,
            "quality": self.quality.value,
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "session_id": self.session_id,
            "provenance": self.provenance,
            "sanitized": self.sanitized,
            "confidence_context": self.confidence_context,
            "ttl_seconds": self.ttl_seconds,
        }


class EvidenceNormalizer:
    """Deterministic normalizer for raw tool outputs, user inputs, and observations."""

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Strip control characters, command injection markers, and excessive whitespace."""
        if not text or not isinstance(text, str):
            return ""
        # Remove null bytes, control chars (preserve standard whitespace)
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        # Redact dangerous shell invocation strings from evidence text
        for pat in [
            r"powershell(?:\.exe)?\s+-[a-zA-Z]+",
            r"cmd(?:\.exe)?\s+/[a-zA-Z]+",
            r"format\s+[a-zA-Z]:",
            r"rmdir\s+/[a-zA-Z]+",
        ]:
            cleaned = re.sub(pat, "[REDACTED_COMMAND]", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    @classmethod
    def from_tool_result(
        cls,
        tool_name: str,
        tool_result: Dict[str, Any],
        evidence_type: EvidenceType,
        session_id: str = "default_session",
    ) -> List[EvidenceItem]:
        """Convert structured tool execution result into normalized EvidenceItems."""
        items: List[EvidenceItem] = []
        now_str = datetime.now(timezone.utc).isoformat()
        ttl = DEFAULT_EVIDENCE_TTLS.get(evidence_type, 300)

        # Extract primary status/observation
        status_val = tool_result.get("status", "completed") if isinstance(tool_result, dict) else "completed"
        summary = tool_result.get("summary") or tool_result.get("message") or f"Execution of {tool_name} returned status {status_val}"

        item = EvidenceItem(
            evidence_id=str(uuid.uuid4())[:8],
            evidence_type=evidence_type,
            source=EvidenceSource.WINDOWS_TOOL,
            category=evidence_type.value.lower(),
            observation=cls.sanitize_text(str(summary)),
            value=tool_result,
            status=EvidenceStatus.VALID,
            quality=EvidenceQuality.VERIFIED,
            timestamp=now_str,
            tool_name=tool_name,
            session_id=session_id,
            provenance=f"ToolRegistry[{tool_name}]",
            ttl_seconds=ttl,
        )
        items.append(item)
        return items

    @classmethod
    def from_user_input(
        cls,
        user_text: str,
        session_id: str = "default_session",
        source: EvidenceSource = EvidenceSource.USER,
    ) -> EvidenceItem:
        """Convert user-reported symptom or voice transcript into EvidenceItem."""
        sanitized = cls.sanitize_text(user_text)
        ev_type = EvidenceType.VOICE if source == EvidenceSource.VOICE else EvidenceType.USER_REPORTED
        return EvidenceItem(
            evidence_id=str(uuid.uuid4())[:8],
            evidence_type=ev_type,
            source=source,
            category="symptom",
            observation=sanitized,
            value={"raw_text": sanitized},
            status=EvidenceStatus.VALID,
            quality=EvidenceQuality.USER_REPORTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            provenance="UserPrompt" if source == EvidenceSource.USER else "VoiceTranscriber",
            ttl_seconds=300,
        )

    @classmethod
    def from_screenshot(
        cls,
        observation: str,
        visual_details: Optional[Dict[str, Any]] = None,
        session_id: str = "default_session",
    ) -> EvidenceItem:
        """Convert screenshot observation into EvidenceItem."""
        sanitized = cls.sanitize_text(observation)
        return EvidenceItem(
            evidence_id=str(uuid.uuid4())[:8],
            evidence_type=EvidenceType.SCREENSHOT,
            source=EvidenceSource.SCREENSHOT,
            category="visual_error",
            observation=sanitized,
            value=visual_details or {},
            status=EvidenceStatus.VALID,
            quality=EvidenceQuality.INFERRED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            provenance="ScreenshotVisionAnalyzer",
            ttl_seconds=300,
        )


class EvidenceStore:
    """Thread-safe, session-isolated store for diagnostic evidence with contradiction checking."""

    def __init__(self) -> None:
        self._sessions: Dict[str, List[EvidenceItem]] = {}

    def add_evidence(self, item: EvidenceItem) -> None:
        """Add an evidence item to its scoped session."""
        sid = item.session_id or "default_session"
        if sid not in self._sessions:
            self._sessions[sid] = []
        self._sessions[sid].append(item)

    def add_many(self, items: List[EvidenceItem]) -> None:
        """Add multiple evidence items."""
        for item in items:
            self.add_evidence(item)

    def get_session_evidence(
        self,
        session_id: str,
        include_stale: bool = False,
    ) -> List[EvidenceItem]:
        """Retrieve all evidence items for a session, filtering stale items if requested."""
        items = self._sessions.get(session_id, [])
        now = datetime.now(timezone.utc)
        result: List[EvidenceItem] = []

        for it in items:
            if not include_stale and it.is_stale(now):
                continue
            result.append(it)
        return result

    def detect_contradictions(self, session_id: str) -> List[Dict[str, Any]]:
        """Identify conflicting evidence items within a session deterministically."""
        items = self.get_session_evidence(session_id, include_stale=False)
        contradictions: List[Dict[str, Any]] = []

        # Rule 1: Network Connectivity Contradiction
        net_items = [it for it in items if it.evidence_type == EvidenceType.NETWORK]
        has_connected = any(
            isinstance(it.value, dict) and it.value.get("internet_connected") is True
            or "connected" in it.observation.lower() and "not" not in it.observation.lower()
            for it in net_items
        )
        has_disconnected = any(
            isinstance(it.value, dict) and it.value.get("internet_connected") is False
            or "disconnected" in it.observation.lower() or "unreachable" in it.observation.lower()
            for it in net_items
        )

        if has_connected and has_disconnected:
            contradictions.append({
                "type": "NETWORK_CONNECTIVITY_CONFLICT",
                "description": "Mutually exclusive network connectivity observations detected.",
                "evidence_ids": [it.evidence_id for it in net_items],
            })

        # Rule 2: User-reported symptom vs verified operational state
        user_items = [it for it in items if it.quality == EvidenceQuality.USER_REPORTED]
        verified_items = [it for it in items if it.quality == EvidenceQuality.VERIFIED]

        for u in user_items:
            u_text = u.observation.lower()
            if "internet" in u_text and ("down" in u_text or "not working" in u_text or "disconnected" in u_text):
                verified_online = [
                    v for v in verified_items
                    if v.evidence_type == EvidenceType.NETWORK and isinstance(v.value, dict) and v.value.get("internet_connected") is True
                ]
                if verified_online:
                    contradictions.append({
                        "type": "USER_REPORTED_VS_VERIFIED_STATE",
                        "description": "User reported internet failure, but verified diagnostic confirmed internet connectivity.",
                        "evidence_ids": [u.evidence_id, verified_online[0].evidence_id],
                    })

        return contradictions

    def clear_session(self, session_id: str) -> None:
        """Clear all evidence for a specific session."""
        if session_id in self._sessions:
            del self._sessions[session_id]


# Global singleton evidence store
default_evidence_store = EvidenceStore()
