"""Knowledge models, schemas, and validation for WinFix AI (Phase 19).

Provides strongly-typed dataclasses, enums, and strict validation for the
local SQLite-backed troubleshooting knowledge system.
Strictly complies with the security principle: LLM != Windows Shell and
Knowledge != Windows Command.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Set


class KnowledgeCategory(str, Enum):
    """Supported diagnostic and troubleshooting knowledge categories."""

    NETWORK = "NETWORK"
    STORAGE = "STORAGE"
    PERFORMANCE = "PERFORMANCE"
    SERVICES = "SERVICES"
    BLUETOOTH = "BLUETOOTH"
    WINDOWS_UPDATE = "WINDOWS_UPDATE"
    DEFENDER = "DEFENDER"
    APPLICATION_CRASH = "APPLICATION_CRASH"
    GENERAL = "GENERAL"


class KnowledgeSeverity(str, Enum):
    """Severity classification for troubleshooting knowledge articles."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    INFO = "INFO"


class KnowledgeToolRole(str, Enum):
    """Role of a linked tool in a knowledge article."""

    DIAGNOSTIC = "DIAGNOSTIC"
    REPAIR = "REPAIR"


class KnowledgeValidationError(ValueError):
    """Raised when a knowledge article or component violates safety or schema rules."""

    pass


# Security blacklist for prohibited executable / command keys in knowledge data
FORBIDDEN_KNOWLEDGE_PATTERNS = [
    re.compile(r"\bpowershell(?:\.exe)?\b", re.IGNORECASE),
    re.compile(r"\bcmd(?:\.exe)?\b", re.IGNORECASE),
    re.compile(r"\bpwsh(?:\.exe)?\b", re.IGNORECASE),
    re.compile(r"\bsubprocess\b", re.IGNORECASE),
    re.compile(r"\bos\.system\b", re.IGNORECASE),
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bexec\s*\(", re.IGNORECASE),
    re.compile(r"\bshell=True\b", re.IGNORECASE),
    re.compile(r"\bCreateProcess\b", re.IGNORECASE),
    re.compile(r"\bWinExec\b", re.IGNORECASE),
    re.compile(r"\bShellExecute\b", re.IGNORECASE),
]

# Prohibited execution keys
FORBIDDEN_EXECUTION_KEYS = {
    "shell_command",
    "powershell",
    "cmd",
    "bash",
    "exec",
    "script",
    "python_code",
    "code",
    "command",
    "run_command",
    "subcommand",
    "system_command",
    "eval",
}

# Prohibited dictionary / JSON keys for knowledge records
FORBIDDEN_KNOWLEDGE_KEYS = set(FORBIDDEN_EXECUTION_KEYS) | {
    "command",
    "commands",
    "shell",
    "shell_command",
    "powershell",
    "cmd",
    "script",
    "script_body",
    "executable",
    "exec",
    "subprocess",
}

# Bounds for safety & Denial-of-Service prevention
MAX_TITLE_LENGTH = 200
MAX_SUMMARY_LENGTH = 2000
MAX_TEXT_FIELD_LENGTH = 1000
MAX_QUERY_LENGTH = 4000
MAX_LIST_ITEMS = 50
MAX_RESULTS_LIMIT = 50


@dataclass
class KnowledgeSymptom:
    """A symptom associated with a troubleshooting article."""

    id: str
    article_id: str
    symptom_text: str
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeCause:
    """A potential root cause associated with a troubleshooting article."""

    id: str
    article_id: str
    cause_text: str
    likelihood: str = "POSSIBLE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeDiagnosticStep:
    """An ordered diagnostic investigation step."""

    id: str
    article_id: str
    step_order: int
    step_text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeToolLink:
    """Reference linking an article to a registered ToolRegistry tool ID."""

    id: str
    article_id: str
    tool_id: str
    tool_role: KnowledgeToolRole = KnowledgeToolRole.DIAGNOSTIC

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "article_id": self.article_id,
            "tool_id": self.tool_id,
            "tool_role": self.tool_role.value if isinstance(self.tool_role, KnowledgeToolRole) else str(self.tool_role),
        }


@dataclass
class KnowledgeVerificationStep:
    """An ordered verification requirement to confirm health/resolution."""

    id: str
    article_id: str
    step_order: int
    step_text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeArticle:
    """Structured troubleshooting knowledge article."""

    id: str
    title: str
    category: KnowledgeCategory
    summary: str
    symptoms: List[str] = field(default_factory=list)
    possible_causes: List[str] = field(default_factory=list)
    diagnostic_steps: List[str] = field(default_factory=list)
    related_tools: List[str] = field(default_factory=list)
    repair_references: List[str] = field(default_factory=list)
    verification_steps: List[str] = field(default_factory=list)
    severity: KnowledgeSeverity = KnowledgeSeverity.MEDIUM
    confidence: float = 1.0
    platform: str = "Windows 10/11"
    source: str = "Built-in"
    version: int = 1
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category.value if isinstance(self.category, KnowledgeCategory) else str(self.category),
            "summary": self.summary,
            "symptoms": list(self.symptoms),
            "possible_causes": list(self.possible_causes),
            "diagnostic_steps": list(self.diagnostic_steps),
            "related_tools": list(self.related_tools),
            "repair_references": list(self.repair_references),
            "verification_steps": list(self.verification_steps),
            "severity": self.severity.value if isinstance(self.severity, KnowledgeSeverity) else str(self.severity),
            "confidence": self.confidence,
            "platform": self.platform,
            "source": self.source,
            "version": self.version,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KnowledgeSearchResult:
    """Result of a deterministic knowledge search query."""

    article_id: str
    title: str
    category: str
    summary: str
    matched_terms: List[str]
    relevance_score: float
    article: Optional[KnowledgeArticle] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "category": self.category,
            "summary": self.summary,
            "matched_terms": list(self.matched_terms),
            "relevance_score": self.relevance_score,
            "article": self.article.to_dict() if self.article else None,
        }


def validate_knowledge_article(
    article: KnowledgeArticle,
    valid_tool_ids: Optional[Set[str]] = None,
    allow_unregistered_tools: bool = False,
) -> None:
    """Validate a knowledge article against schema, bounds, and safety invariants.

    Raises:
        KnowledgeValidationError: If any rule or security check is violated.
    """
    if not article.id or not isinstance(article.id, str) or not article.id.strip():
        raise KnowledgeValidationError("Article ID must be a non-empty string.")

    if not article.title or not isinstance(article.title, str) or not article.title.strip():
        raise KnowledgeValidationError("Article title must be a non-empty string.")

    if len(article.title) > MAX_TITLE_LENGTH:
        raise KnowledgeValidationError(f"Article title exceeds maximum length of {MAX_TITLE_LENGTH} characters.")

    # Validate Category
    category_val = article.category.value if isinstance(article.category, KnowledgeCategory) else str(article.category)
    valid_categories = {c.value for c in KnowledgeCategory}
    if category_val not in valid_categories:
        raise KnowledgeValidationError(f"Invalid knowledge category '{category_val}'. Allowed: {sorted(valid_categories)}")

    # Validate Severity
    severity_val = article.severity.value if isinstance(article.severity, KnowledgeSeverity) else str(article.severity)
    valid_severities = {s.value for s in KnowledgeSeverity}
    if severity_val not in valid_severities:
        raise KnowledgeValidationError(f"Invalid severity '{severity_val}'. Allowed: {sorted(valid_severities)}")

    if not article.summary or not isinstance(article.summary, str):
        raise KnowledgeValidationError("Article summary must be a non-empty string.")

    if len(article.summary) > MAX_SUMMARY_LENGTH:
        raise KnowledgeValidationError(f"Article summary exceeds maximum length of {MAX_SUMMARY_LENGTH} characters.")

    if article.version < 1:
        raise KnowledgeValidationError("Article version must be an integer >= 1.")

    if not (0.0 <= article.confidence <= 1.0):
        raise KnowledgeValidationError(f"Confidence score {article.confidence} must be between 0.0 and 1.0.")

    # Validate list sizes
    for field_name, items in [
        ("symptoms", article.symptoms),
        ("possible_causes", article.possible_causes),
        ("diagnostic_steps", article.diagnostic_steps),
        ("related_tools", article.related_tools),
        ("repair_references", article.repair_references),
        ("verification_steps", article.verification_steps),
    ]:
        if not isinstance(items, (list, tuple)):
            raise KnowledgeValidationError(f"Field '{field_name}' must be a list.")
        if len(items) > MAX_LIST_ITEMS:
            raise KnowledgeValidationError(f"Field '{field_name}' exceeds maximum items limit of {MAX_LIST_ITEMS}.")
        for item in items:
            if not isinstance(item, str):
                raise KnowledgeValidationError(f"All elements in '{field_name}' must be strings.")
            if len(item) > MAX_TEXT_FIELD_LENGTH:
                raise KnowledgeValidationError(f"Element in '{field_name}' exceeds max length of {MAX_TEXT_FIELD_LENGTH}.")

    # Validate Tool References against registered catalog
    if valid_tool_ids is not None and not allow_unregistered_tools:
        all_tool_refs = set(article.related_tools) | set(article.repair_references)
        for tool_id in all_tool_refs:
            if tool_id not in valid_tool_ids:
                raise KnowledgeValidationError(
                    f"Tool reference '{tool_id}' in article '{article.id}' is not registered in ToolRegistry."
                )

    # Security check: verify no executable / script injection in text fields
    all_text_blocks = [
        article.title,
        article.summary,
        *article.symptoms,
        *article.possible_causes,
        *article.diagnostic_steps,
        *article.verification_steps,
    ]
    for block in all_text_blocks:
        for pattern in FORBIDDEN_KNOWLEDGE_PATTERNS:
            if pattern.search(block):
                raise KnowledgeValidationError(
                    f"Security Policy Violation: Prohibited execution pattern '{pattern.pattern}' detected in article text: '{block}'"
                )


def scan_dict_for_forbidden_keys(data: Any, path: str = "") -> None:
    """Recursively scan dictionaries for forbidden command/execution keys."""
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if key.lower() in FORBIDDEN_KNOWLEDGE_KEYS:
                raise KnowledgeValidationError(
                    f"Security Policy Violation: Forbidden key '{key}' detected in knowledge data at '{current_path}'"
                )
            scan_dict_for_forbidden_keys(value, current_path)
    elif isinstance(data, (list, tuple)):
        for idx, item in enumerate(data):
            scan_dict_for_forbidden_keys(item, f"{path}[{idx}]")
