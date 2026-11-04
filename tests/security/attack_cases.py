"""Attack scenario definitions and mock context fixtures for WinFix AI security test suites."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SecurityAttackScenario:
    """Represents an isolated security attack scenario with expected failure outcome."""

    scenario_id: str
    name: str
    threat_category: str
    payload: Any
    target_component: str
    expected_exception: Optional[type] = None
    expected_rejection: bool = True
