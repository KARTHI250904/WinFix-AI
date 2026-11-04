"""WinFix AI — User Intent Classification Engine.

Disambiguates user intent (e.g. VIEW_HISTORY, CHECK_STATUS, DIAGNOSE, EXPLAIN, REPAIR, CONFIGURE)
from the problem domain (e.g. WINDOWS_UPDATE, NETWORK, STORAGE, etc.) to ensure that
Autopilot and troubleshooting planners never propose repairs or MEDIUM actions for read-only
requests.
"""

from enum import Enum
import re
from typing import Optional, Set, Tuple


class UserIntent(str, Enum):
    VIEW_HISTORY = "VIEW_HISTORY"
    CHECK_STATUS = "CHECK_STATUS"
    DIAGNOSE = "DIAGNOSE"
    EXPLAIN = "EXPLAIN"
    REPAIR = "REPAIR"
    CONFIGURE = "CONFIGURE"


class UserIntentClassifier:
    """Classifies user problem text or voice transcripts into actionable intent categories."""

    def classify_intent(self, text: str) -> UserIntent:
        """Determine user intent from text query."""
        if not text:
            return UserIntent.DIAGNOSE

        t = text.lower().strip()

        # Imperative repair commands take priority over descriptive context (e.g. "restart service to fix failed updates")
        imperative_repair = ["restart ", "fix ", "repair ", "clean ", "cleanup ", "reset ", "flush ", "unblock "]
        if any(t.startswith(prefix) for prefix in imperative_repair):
            return UserIntent.REPAIR

        # 1. VIEW_HISTORY (strong historical / log / past failure inspection signals)
        history_phrases = [
            "previous failure",
            "previous failures",
            "past failure",
            "past failures",
            "failed update",
            "failed updates",
            "view history",
            "show history",
            "see history",
            "check history",
            "update history",
            "crash history",
            "previous error",
            "previous errors",
            "past error",
            "past errors",
            "last failure",
            "last error",
            "last crash",
            "previous crash",
            "previous problem",
            "previous problems",
            "past problem",
            "past problems",
            "event log",
            "crash log",
            "error log",
            "what happened",
            "history of",
        ]
        if any(trig in t for trig in history_phrases):
            return UserIntent.VIEW_HISTORY

        # Regex for phrases like: "how to view/see/show/find/get/check [the] previous/past/last failure/error/problem/update"
        if re.search(r"\b(view|see|show|check|display|find|list|inspect|get)\b.*\b(previous|past|history|last failure|failed update|last error)\b", t):
            return UserIntent.VIEW_HISTORY

        # Check if words "previous", "history", "past", "log" are combined with view/see/show/check
        has_history_word = any(w in t for w in ["history", "previous", "past", "logs", "record", "records"])
        has_view_word = any(w in t for w in ["view", "see", "show", "check", "display", "find", "list", "inspect"])
        if has_history_word and has_view_word:
            return UserIntent.VIEW_HISTORY

        # 2. CHECK_STATUS (inspecting current state, adapter details, resource usage, is running/active)
        if not t.startswith("why ") and not t.startswith("why is"):
            if re.search(r"\bis\b.*\b(running|active|enabled|started|stopped|online|healthy|turned on|turned off)\b", t):
                return UserIntent.CHECK_STATUS
            if re.search(r"\b(check if|is|are)\b.*\b(turned on|turned off|enabled|disabled|active|running|protected)\b", t):
                return UserIntent.CHECK_STATUS

        status_phrases = [
            "check status",
            "check state",
            "show status",
            "view status",
            "current status",
            "service status",
            "adapter info",
            "adapter information",
            "system info",
            "system information",
            "specs",
            "hardware info",
            "what is using",
            "what's using",
            "what is taking",
            "what's taking",
            "see what is using",
            "see what's using",
            "see what is taking",
            "see what's taking",
            "show what is using",
            "show what's using",
            "show what is taking",
            "show what's taking",
            "how to see my",
            "how do i see my",
            "how to view my",
            "how do i view my",
            "how to check my",
            "how do i check my",
            "current usage",
            "current capacity",
            "free space on",
            "space on",
        ]
        if any(trig in t for trig in status_phrases):
            return UserIntent.CHECK_STATUS

        if re.search(r"\b(how (?:do|can) i (?:see|view|check|find)|show me|what is|what's)\b.*\b(using|taking|space|cpu|ram|memory|status|adapter|ip|dns)\b", t):
            return UserIntent.CHECK_STATUS

        # 3. REPAIR (explicit request to fix, restart, reset, clean, solve, repair)
        repair_keywords = [
            "fix",
            "repair",
            "restart",
            "reset",
            "clean",
            "cleanup",
            "flush",
            "restore",
            "solve",
            "make it work",
            "resolve",
            "clear cache",
            "clear temp",
            "free up space",
            "unblock",
        ]
        if any(re.search(rf"\b{re.escape(w)}\b", t) for w in repair_keywords):
            # Guard against inquiries like "why did restart fail?" or "how to see if fixed"
            if not any(t.startswith(prefix) for prefix in ["why ", "how does ", "what is ", "explain "]):
                return UserIntent.REPAIR

        # 4. EXPLAIN (educational inquiry, what is X, how does X work)
        explain_keywords = [
            "explain",
            "what is",
            "what does",
            "how does",
            "tell me about",
            "what does this mean",
            "teach me",
            "understand",
            "meaning of",
        ]
        if any(trig in t for trig in explain_keywords):
            return UserIntent.EXPLAIN

        # 5. CONFIGURE (setting changes, enable/disable)
        config_keywords = [
            "configure",
            "change setting",
            "change settings",
            "enable",
            "disable",
            "turn on",
            "turn off",
            "switch to",
        ]
        if any(trig in t for trig in config_keywords):
            return UserIntent.CONFIGURE

        # 6. Default to DIAGNOSE for general problem symptoms (e.g., "slow", "disconnecting", "failed", "crash", "why...")
        return UserIntent.DIAGNOSE


default_intent_classifier = UserIntentClassifier()
