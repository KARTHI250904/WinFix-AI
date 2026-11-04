"""Personal Tutor prompt construction and system instruction adapters.

Provides prompt formatting utilities for Personal Tutor educational explanations.
"""

from typing import Any, Dict, List, Optional
from ai.tutor_prompt import TUTOR_SYSTEM_INSTRUCTION, build_tutor_prompt


def build_tutor_system_prompt() -> str:
    """Return the base system prompt for Personal Tutor mode."""
    return TUTOR_SYSTEM_INSTRUCTION


__all__ = ["TUTOR_SYSTEM_INSTRUCTION", "build_tutor_prompt", "build_tutor_system_prompt"]
