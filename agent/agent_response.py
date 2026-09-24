"""Structured response and tool request schemas for WinFix AI agent.

Defines the strictly typed AgentResponse, ToolRequest, and untrusted JSON parsing
boundary that sits between Gemma's LLM text output and the SafetyEngine.
"""

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Forbidden keys in LLM output that indicate attempts to inject command execution
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


@dataclass
class ToolRequest:
    """A single diagnostic tool request produced by the agent."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    purpose: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tool request to dictionary."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "purpose": self.purpose,
        }


@dataclass
class AgentResponse:
    """Structured, verified internal representation of Gemma's reasoning and diagnostic plan."""

    response: str = ""
    intent: str = "diagnose"
    confidence: float = 0.8
    reasoning_summary: str = ""
    requested_tools: List[ToolRequest] = field(default_factory=list)
    safety_notes: List[str] = field(default_factory=list)
    needs_user_confirmation: bool = False
    raw_json: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent response to standard dictionary."""
        return {
            "response": self.response,
            "intent": self.intent,
            "confidence": self.confidence,
            "reasoning_summary": self.reasoning_summary,
            "requested_tools": [tr.to_dict() for tr in self.requested_tools],
            "safety_notes": self.safety_notes,
            "needs_user_confirmation": self.needs_user_confirmation,
        }


def extract_json_from_text(raw_text: str) -> Optional[str]:
    """Extract a valid JSON string from raw text (handling markdown fences or surrounding chatter)."""
    if not raw_text or not isinstance(raw_text, str):
        return None

    stripped = raw_text.strip()

    # Case 1: Markdown code fence ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Case 2: Direct JSON object enclosed in { ... }
    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        return stripped[brace_start : brace_end + 1]

    return None


def parse_agent_response(
    raw_text: str, allowed_tool_names: Optional[List[str]] = None
) -> tuple[bool, Optional[AgentResponse], Optional[str]]:
    """Strictly parse and validate untrusted LLM output into an AgentResponse.

    Returns:
        (success: bool, response: Optional[AgentResponse], error_message: Optional[str])
    """
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        return False, None, "Empty response received from model."

    json_str = extract_json_from_text(raw_text)
    if not json_str:
        return False, None, "Failed to locate JSON object in model output."

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as err:
        return False, None, f"Malformed JSON syntax: {err}"

    if not isinstance(data, dict):
        return False, None, f"Expected JSON object at root, got {type(data).__name__}."

    # Recursive check for forbidden command execution keys
    def check_forbidden_keys(obj: Any, path: str = "") -> Optional[str]:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in FORBIDDEN_EXECUTION_KEYS:
                    return f"Forbidden command execution field '{k}' detected at '{path}'."
                err = check_forbidden_keys(v, f"{path}.{k}" if path else k)
                if err:
                    return err
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                err = check_forbidden_keys(item, f"{path}[{idx}]")
                if err:
                    return err
        return None

    sec_err = check_forbidden_keys(data)
    if sec_err:
        logger.warning("Security violation in LLM response: %s", sec_err)
        return False, None, f"Security Policy Rejection: {sec_err}"

    # Extract top-level fields with safe type conversions and bounds
    response_msg = str(data.get("response", ""))
    intent = str(data.get("intent", "diagnose"))
    
    # Confidence (float between 0.0 and 1.0)
    raw_conf = data.get("confidence", 0.8)
    try:
        confidence = float(raw_conf)
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.8

    reasoning_summary = str(data.get("reasoning_summary", ""))
    needs_user_confirmation = bool(data.get("needs_user_confirmation", False))

    raw_safety_notes = data.get("safety_notes", [])
    safety_notes: List[str] = []
    if isinstance(raw_safety_notes, list):
        safety_notes = [str(n) for n in raw_safety_notes if n is not None]

    # Validate requested tools list
    raw_tools = data.get("requested_tools", [])
    if not isinstance(raw_tools, list):
        return False, None, f"'requested_tools' must be a list, got {type(raw_tools).__name__}."

    validated_tools: List[ToolRequest] = []
    for idx, item in enumerate(raw_tools):
        if not isinstance(item, dict):
            return False, None, f"Tool request #{idx+1} must be an object."

        tool_name = item.get("tool_name")
        if not tool_name or not isinstance(tool_name, str):
            return False, None, f"Tool request #{idx+1} is missing a valid 'tool_name'."

        tool_name = tool_name.strip()

        # Verify against allowed tool names if provided
        if allowed_tool_names is not None and tool_name not in allowed_tool_names:
            return (
                False,
                None,
                f"Requested tool '{tool_name}' is not in the approved ToolRegistry catalog.",
            )

        args = item.get("arguments", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return (
                False,
                None,
                f"Arguments for tool '{tool_name}' must be a dictionary, got {type(args).__name__}.",
            )

        purpose = str(item.get("purpose", ""))

        validated_tools.append(
            ToolRequest(
                tool_name=tool_name,
                arguments=args,
                purpose=purpose,
            )
        )

    agent_resp = AgentResponse(
        response=response_msg,
        intent=intent,
        confidence=confidence,
        reasoning_summary=reasoning_summary,
        requested_tools=validated_tools,
        safety_notes=safety_notes,
        needs_user_confirmation=needs_user_confirmation,
        raw_json=data,
    )

    return True, agent_resp, None
