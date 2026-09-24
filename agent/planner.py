"""AI Agent Planner and Reasoning Core for WinFix AI.

Orchestrates the safe interaction loop between the user's problem, local Gemma model,
ToolRegistry, and SafetyEngine. Complies strictly with the fundamental rule:
LLM != Windows Shell.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from agent.agent_response import AgentResponse, ToolRequest, parse_agent_response
from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import (
    DiagnosticRepository,
    ProblemRepository,
    SessionRepository,
    SolutionRepository,
    ToolExecutionRepository,
)

logger = logging.getLogger(__name__)


class AgentPlanner:
    """Safe reasoning and diagnostic planning orchestrator."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        registry: Optional[ToolRegistry] = None,
        safety_engine: Optional[SafetyEngine] = None,
        db_mgr: Optional[DatabaseManager] = None,
    ) -> None:
        self.client = client or ollama_client
        self.registry = registry or default_tool_registry
        self.safety_engine = safety_engine or default_safety_engine
        self.db_manager = db_mgr or default_db_manager

        # Database repositories for audit and state persistence
        self.session_repo = SessionRepository(self.db_manager)
        self.problem_repo = ProblemRepository(self.db_manager)
        self.diag_repo = DiagnosticRepository(self.db_manager)
        self.exec_repo = ToolExecutionRepository(self.db_manager)
        self.solution_repo = SolutionRepository(self.db_manager)

    def get_tool_catalog_for_prompt(self) -> List[Dict[str, Any]]:
        """Export serialized tool metadata catalog for LLM planning prompts."""
        tools = self.registry.list_tools()
        catalog = []
        for t in tools:
            catalog.append(
                {
                    "name": t.name,
                    "domain": t.domain,
                    "description": t.description,
                    "risk": t.risk.value,
                    "read_only": t.read_only,
                    "requires_admin": t.requires_admin,
                    "parameters": {
                        p_name: {
                            "type": p_spec.param_type.__name__,
                            "required": p_spec.required,
                            "default": p_spec.default,
                            "description": p_spec.description,
                        }
                        for p_name, p_spec in t.parameters.items()
                    },
                }
            )
        return catalog

    def _build_planning_system_prompt(self) -> str:
        """Construct the immutable system prompt establishing safety boundaries and catalog."""
        catalog_json = json.dumps(self.get_tool_catalog_for_prompt(), indent=2)
        return f"""You are WinFix AI, a safe, expert offline Windows Diagnostic Assistant.
Your purpose is to help users diagnose and understand Windows computer issues.

CRITICAL SECURITY RULES:
1. You DO NOT have access to a command shell, PowerShell, CMD, or executable interpreter.
2. You must NEVER suggest, generate, or execute shell commands, scripts, or arbitrary code.
3. You may ONLY select diagnostic tools from the APPROVED TOOL CATALOG below.
4. If no tools are needed, return an empty "requested_tools" list.
5. All tool arguments must strictly match the parameter types and names in the catalog.
6. Your response MUST be valid JSON conforming strictly to the specified schema.

APPROVED TOOL CATALOG:
{catalog_json}

RESPONSE JSON SCHEMA:
{{
  "response": "<clear, non-technical explanation to the user of what you plan to check>",
  "intent": "<diagnose | clarify | advise>",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning_summary": "<brief technical explanation of why these tools were chosen>",
  "requested_tools": [
    {{
      "tool_name": "<exact name from catalog>",
      "arguments": {{ "<param_name>": <param_value> }},
      "purpose": "<brief reason for invoking this tool>"
    }}
  ],
  "safety_notes": ["<any relevant safety observations>"],
  "needs_user_confirmation": <true if medium risk tools require confirmation, otherwise false>
}}
"""

    def plan_diagnostics(
        self,
        problem_description: str,
        system_info: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
    ) -> tuple[bool, AgentResponse, Optional[str]]:
        """Prompt Gemma to select appropriate diagnostic tools and parse structured output."""
        if not problem_description or not problem_description.strip():
            empty_resp = AgentResponse(
                response="Please describe the issue or symptoms you are experiencing with your Windows PC.",
                intent="clarify",
                confidence=1.0,
            )
            return True, empty_resp, None

        system_prompt = self._build_planning_system_prompt()
        allowed_tools = self.registry.list_tool_names()

        user_prompt_content = {
            "user_problem": problem_description.strip(),
            "system_context": system_info or {},
        }
        current_prompt = f"User Request: {json.dumps(user_prompt_content)}"

        for attempt in range(max_retries + 1):
            gen_res = self.client.generate(
                prompt=current_prompt,
                system=system_prompt,
                format="json",
            )

            if not gen_res["success"]:
                err = gen_res.get("error", "Failed to connect to local Ollama runtime.")
                logger.warning("Planning generation failed on attempt %d: %s", attempt + 1, err)
                # If connection failed completely, return safe fallback
                if attempt == max_retries:
                    fallback = self._create_deterministic_fallback_plan(problem_description)
                    return True, fallback, f"Ollama unavailable ({err}). Used deterministic fallback."
                continue

            raw_text = gen_res.get("response", "")
            valid, parsed_resp, parse_err = parse_agent_response(raw_text, allowed_tool_names=allowed_tools)

            if valid and parsed_resp is not None:
                return True, parsed_resp, None

            logger.warning("Response parsing failed on attempt %d: %s", attempt + 1, parse_err)
            if attempt < max_retries:
                # Controlled retry prompt
                current_prompt = (
                    f"Previous response was invalid: {parse_err}. "
                    f"Please re-generate your response as strict valid JSON conforming to the schema "
                    f"for user problem: {problem_description}"
                )

        # Fallback if all retries produced invalid format
        fallback = self._create_deterministic_fallback_plan(problem_description)
        return True, fallback, "LLM response format was invalid after retries. Used safe deterministic plan."

    def _create_deterministic_fallback_plan(self, problem_description: str) -> AgentResponse:
        """Create a safe, deterministic diagnostic plan when Ollama is unreachable or invalid."""
        prob_lower = problem_description.lower()
        tools: List[ToolRequest] = []

        if any(w in prob_lower for w in ["internet", "wifi", "network", "dns", "ping", "web"]):
            tools.append(ToolRequest("get_network_adapters_diagnostics", {}, "Inspect network adapters"))
            tools.append(ToolRequest("check_internet_connectivity", {}, "Verify connectivity"))
            tools.append(ToolRequest("check_dns_resolution", {}, "Verify DNS resolution"))
        elif any(w in prob_lower for w in ["slow", "lag", "cpu", "memory", "ram", "freeze", "hang"]):
            tools.append(ToolRequest("get_cpu_diagnostics", {}, "Measure CPU usage"))
            tools.append(ToolRequest("get_memory_diagnostics", {}, "Measure RAM usage"))
            tools.append(ToolRequest("get_top_cpu_processes", {"limit": 5}, "Identify high CPU tasks"))
        elif any(w in prob_lower for w in ["disk", "storage", "space", "drive", "full"]):
            tools.append(ToolRequest("get_storage_diagnostics", {}, "Inspect disk volume space"))
            tools.append(ToolRequest("get_temp_storage_info", {}, "Inspect temporary files"))
        elif any(w in prob_lower for w in ["print", "spooler"]):
            tools.append(ToolRequest("get_printer_diagnostics", {}, "Inspect printer and spooler state"))
        elif any(w in prob_lower for w in ["bluetooth", "audio", "device"]):
            tools.append(ToolRequest("get_bluetooth_diagnostics", {}, "Inspect Bluetooth service and adapter"))
        elif any(w in prob_lower for w in ["update", "patch"]):
            tools.append(ToolRequest("get_windows_update_diagnostics", {}, "Inspect update readiness"))
        elif any(w in prob_lower for w in ["crash", "error", "event"]):
            tools.append(ToolRequest("get_recent_application_crashes", {"limit": 5}, "Inspect crash logs"))
        else:
            tools.append(ToolRequest("get_complete_system_info", {}, "Gather baseline system information"))

        return AgentResponse(
            response="I will run safe read-only diagnostics to investigate this issue.",
            intent="diagnose",
            confidence=0.7,
            reasoning_summary="Deterministic rule-based fallback based on problem keywords.",
            requested_tools=tools,
        )

    def execute_plan(
        self,
        agent_response: AgentResponse,
        session_id: Optional[str] = None,
        user_confirmed: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute the validated tool requests through SafetyEngine."""
        results: List[Dict[str, Any]] = []

        for req in agent_response.requested_tools:
            logger.info("Executing requested tool '%s' (session=%s)", req.tool_name, session_id)
            res = self.safety_engine.execute(
                tool_name=req.tool_name,
                arguments=req.arguments,
                session_id=session_id,
                user_confirmed=user_confirmed,
            )
            results.append(
                {
                    "tool_name": req.tool_name,
                    "purpose": req.purpose,
                    "arguments": req.arguments,
                    "result": res,
                }
            )

        return results

    def synthesize_findings(
        self,
        problem_description: str,
        tool_results: List[Dict[str, Any]],
        system_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ask Gemma to synthesize diagnostic evidence into an understandable summary."""
        if not tool_results:
            return {
                "summary": "No diagnostic tools were executed.",
                "likely_cause": "Unknown",
                "recommendations": ["Provide more details about the problem."],
            }

        # Prepare sanitized evidence payload
        sanitized_results = []
        for tr in tool_results:
            res_obj = tr.get("result", {})
            sanitized_results.append(
                {
                    "tool": tr.get("tool_name"),
                    "purpose": tr.get("purpose"),
                    "success": res_obj.get("success", False),
                    "data": res_obj.get("data"),
                    "error": res_obj.get("error"),
                }
            )

        synth_system_prompt = """You are WinFix AI. Analyze the following Windows diagnostic evidence.
Provide a clear, friendly, and non-technical explanation of findings.

Return strictly JSON conforming to:
{
  "summary": "<plain English summary of findings>",
  "likely_cause": "<probable cause of the issue based strictly on the evidence>",
  "evidence_found": ["<key observation 1>", "<key observation 2>"],
  "recommendations": ["<safe recommendation 1>", "<safe recommendation 2>"],
  "user_action_required": <true | false>
}
"""

        synth_user_prompt = json.dumps(
            {
                "user_problem": problem_description,
                "diagnostic_evidence": sanitized_results,
                "system_context": system_info or {},
            }
        )

        gen_res = self.client.generate(
            prompt=synth_user_prompt,
            system=synth_system_prompt,
            format="json",
        )

        if gen_res["success"]:
            valid, parsed, _ = parse_agent_response(gen_res.get("response", ""))
            if valid and parsed and parsed.raw_json:
                return parsed.raw_json

        # Deterministic fallback summary if LLM synthesis fails
        successful_tools = [t["tool"] for t in sanitized_results if t["success"]]
        failed_tools = [t["tool"] for t in sanitized_results if not t["success"]]

        evidence = [f"Checked: {t}" for t in successful_tools]
        if failed_tools:
            evidence.append(f"Tools with errors: {', '.join(failed_tools)}")

        return {
            "summary": f"Completed diagnostic checks on {len(tool_results)} subsystem(s).",
            "likely_cause": "Diagnostics collected successfully. Review technical findings below.",
            "evidence_found": evidence,
            "recommendations": ["Review the diagnostic evidence in the technical details drawer."],
            "user_action_required": False,
        }

    def diagnose(
        self,
        problem_description: str,
        session_id: Optional[str] = None,
        system_info: Optional[Dict[str, Any]] = None,
        user_confirmed: bool = False,
    ) -> Dict[str, Any]:
        """Execute full safe diagnostic cycle: Plan -> Validate -> Execute -> Synthesize -> Persist."""
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"

        # Record session and problem in SQLite if database is initialized
        try:
            if not self.session_repo.get(sid):
                self.session_repo.create(session_id=sid)
            self.problem_repo.create(
                session_id=sid,
                raw_input=problem_description,
                problem_type="general",
            )
        except Exception as db_err:
            logger.debug("Database session record note: %s", db_err)

        # Step 1: Plan
        plan_ok, plan, plan_err = self.plan_diagnostics(
            problem_description=problem_description,
            system_info=system_info,
        )

        # Step 2: Execute
        tool_results = self.execute_plan(
            agent_response=plan,
            session_id=sid,
            user_confirmed=user_confirmed,
        )

        # Step 3: Synthesize
        synthesis = self.synthesize_findings(
            problem_description=problem_description,
            tool_results=tool_results,
            system_info=system_info,
        )

        # Step 4: Persist diagnostic results for executed tools
        for tr in tool_results:
            t_name = tr.get("tool_name", "unknown")
            res_obj = tr.get("result", {})
            status_str = "success" if res_obj.get("success", False) else "failed"
            try:
                self.diag_repo.create(
                    session_id=sid,
                    tool_name=t_name,
                    status=status_str,
                    evidence_json=json.dumps(res_obj.get("data"), default=str),
                )
            except Exception as diag_err:
                logger.debug("Diag record note for %s: %s", t_name, diag_err)

        # Step 5: Persist AI synthesis as overall diagnostic record
        try:
            self.diag_repo.create(
                session_id=sid,
                tool_name="ai_synthesis",
                status="completed",
                evidence_json=json.dumps(synthesis, default=str),
            )
        except Exception as diag_db_err:
            logger.debug("Diagnostic DB persist note: %s", diag_db_err)

        return {
            "success": True,
            "session_id": sid,
            "problem": problem_description,
            "plan": plan.to_dict(),
            "tool_results": tool_results,
            "synthesis": synthesis,
            "error": plan_err,
        }


# Default shared planner instance
default_agent_planner = AgentPlanner()
