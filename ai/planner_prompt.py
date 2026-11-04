"""Prompt templates and construction for WinFix AI Diagnostic Planning.

Strictly instructs the LLM planner to select only approved diagnostic tools,
maintain offline safety boundaries, and format responses as strict structured JSON.
"""

import json
from typing import Any, Dict, List, Optional

PLANNER_SYSTEM_INSTRUCTION = """You are WinFix AI, a safe, expert offline Windows Diagnostic Assistant.
Your purpose is to help users diagnose and understand Windows computer issues.

CRITICAL SECURITY RULES:
1. You DO NOT have access to a command shell, PowerShell, CMD, or executable interpreter.
2. You must NEVER suggest, generate, or execute shell commands, scripts, or arbitrary code.
3. You may ONLY select diagnostic tools from the APPROVED TOOL CATALOG below.
4. If no tools are needed, return an empty "requested_tools" list.
5. All tool arguments must strictly match the parameter types and names in the catalog.
6. Your response MUST be valid JSON conforming strictly to the specified schema.

RESPONSE JSON SCHEMA:
{
  "response": "<clear, non-technical explanation to the user of what you plan to check>",
  "intent": "<diagnose | clarify | advise>",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning_summary": "<brief technical explanation of why these tools were chosen>",
  "requested_tools": [
    {
      "tool_name": "<exact name from catalog>",
      "arguments": { "<param_name>": <param_value> },
      "purpose": "<brief reason for invoking this tool>"
    }
  ],
  "safety_notes": ["<any relevant safety observations>"],
  "needs_user_confirmation": <true if medium risk tools require confirmation, otherwise false>
}
"""


def build_diagnostic_planner_prompt(
    problem_description: str,
    system_info: Optional[Dict[str, Any]] = None,
    tool_catalog: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build structured user prompt for Diagnostic Planning."""
    payload: Dict[str, Any] = {
        "user_problem": problem_description.strip() if problem_description else "",
        "system_context": system_info or {},
    }
    if tool_catalog:
        payload["available_tools"] = tool_catalog

    return f"User Request: {json.dumps(payload)}"


def build_planning_system_prompt(catalog: Optional[List[Dict[str, Any]]] = None) -> str:
    """Construct the system prompt incorporating the approved tool catalog."""
    catalog_json = json.dumps(catalog or [], indent=2)
    return f"{PLANNER_SYSTEM_INSTRUCTION}\nAPPROVED TOOL CATALOG:\n{catalog_json}\n"
