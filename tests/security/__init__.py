"""Security testing package for WinFix AI (Phase 21)."""

from tests.security.attack_cases import SecurityAttackScenario
from tests.security.malicious_inputs import generate_fuzz_strings
from tests.security.test_vectors import (
    COMMAND_INJECTIONS,
    FORBIDDEN_TOOL_INJECTIONS,
    MALFORMED_JSON_PAYLOADS,
    PATH_TRAVERSALS,
    PROMPT_INJECTIONS,
    SQL_INJECTIONS,
    SYNTHETIC_PRIVACY_PAYLOADS,
    UNICODE_ABUSE,
)

__all__ = [
    "SecurityAttackScenario",
    "generate_fuzz_strings",
    "PROMPT_INJECTIONS",
    "COMMAND_INJECTIONS",
    "SQL_INJECTIONS",
    "PATH_TRAVERSALS",
    "UNICODE_ABUSE",
    "MALFORMED_JSON_PAYLOADS",
    "FORBIDDEN_TOOL_INJECTIONS",
    "SYNTHETIC_PRIVACY_PAYLOADS",
]
