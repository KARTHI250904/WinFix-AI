"""Tool metadata schemas and risk definitions for WinFix AI.

Defines the 3-tier risk model (SAFE, MEDIUM, HIGH), argument validation specifications,
and structured tool definition containers.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


class RiskLevel(str, Enum):
    """3-Tier Risk Classification for Windows tools."""

    SAFE = "SAFE"        # Read-only diagnostics & harmless inspections. Auto-allowed.
    MEDIUM = "MEDIUM"    # Controlled reversible state modifications. Requires confirmation.
    HIGH = "HIGH"        # Potentially destructive / security-lowering. Strictly blocked.


@dataclass(frozen=True)
class ParameterSpec:
    """Specification and validation constraints for a single tool argument."""

    name: str
    param_type: Type  # e.g. str, int, float, bool
    required: bool = False
    default: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    description: str = ""

    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """Validate an argument value against this specification."""
        if value is None:
            if self.required:
                return False, f"Parameter '{self.name}' is required."
            return True, None

        # Type validation
        # Handle int/float compatibility (int is valid when float is expected)
        if self.param_type is float and isinstance(value, (int, float)):
            val = float(value)
        elif not isinstance(value, self.param_type):
            return False, (
                f"Parameter '{self.name}' expected type {self.param_type.__name__}, "
                f"got {type(value).__name__}."
            )
        else:
            val = value

        # Numerical bounds validation
        if isinstance(val, (int, float)):
            if self.min_value is not None and val < self.min_value:
                return False, (
                    f"Parameter '{self.name}' value {val} is below minimum {self.min_value}."
                )
            if self.max_value is not None and val > self.max_value:
                return False, (
                    f"Parameter '{self.name}' value {val} exceeds maximum {self.max_value}."
                )

        # String security checks & length bounds
        if isinstance(val, str):
            # Check for forbidden command injection or shell sequences
            forbidden_tokens = [";", "&&", "||", "`", "$", "|", "\n", "\r", "<", ">"]
            for token in forbidden_tokens:
                if token in val:
                    return False, f"Parameter '{self.name}' contains forbidden character '{token}'."
            if self.max_value is not None and len(val) > int(self.max_value):
                return False, f"Parameter '{self.name}' length exceeds limit of {int(self.max_value)} chars."

        # Allowed values whitelist
        if self.allowed_values is not None and val not in self.allowed_values:
            return False, f"Parameter '{self.name}' value '{val}' not in allowed choices: {self.allowed_values}."

        return True, None


@dataclass
class ToolDefinition:
    """Metadata container for an approved, registered Windows tool."""

    name: str
    domain: str
    description: str
    risk: RiskLevel
    requires_admin: bool = False
    automatic_allowed: bool = True
    read_only: bool = True
    verification_tool: Optional[str] = None
    parameters: Dict[str, ParameterSpec] = field(default_factory=dict)
    handler: Optional[Callable[..., Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tool metadata for inspection and documentation."""
        return {
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "risk": self.risk.value,
            "requires_admin": self.requires_admin,
            "automatic_allowed": self.automatic_allowed,
            "read_only": self.read_only,
            "verification_tool": self.verification_tool,
            "parameters": {
                p_name: {
                    "type": p_spec.param_type.__name__,
                    "required": p_spec.required,
                    "default": p_spec.default,
                    "description": p_spec.description,
                }
                for p_name, p_spec in self.parameters.items()
            },
        }
