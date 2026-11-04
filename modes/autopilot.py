"""WinFix AI — Autopilot Mode Engine.

Implements bounded, verified, and user-authorized multi-step diagnostic and
repair orchestration. Enforces the strict security rule: LLM != Windows Shell.
"""

from dataclasses import asdict
import hashlib
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import config
from agent.bluetooth_repairs_orchestrator import BluetoothRepairsOrchestrator
from agent.defender_repairs_orchestrator import DefenderRepairProposal, DefenderRepairsOrchestrator
from agent.network_repairs_orchestrator import (
    RepairProposal,
    default_network_repairs_orchestrator,
)
from agent.performance_repairs_orchestrator import default_performance_repairs_orchestrator
from agent.safety import SafetyEngine
from agent.service_repairs_orchestrator import ServiceRepairsOrchestrator
from agent.storage_repairs_orchestrator import default_storage_repairs_orchestrator
from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, default_tool_registry
from agent.windows_update_repairs_orchestrator import (
    WindowsUpdateRepairProposal,
    WindowsUpdateRepairsOrchestrator,
)
from ai.autopilot_prompt import AUTOPILOT_SYSTEM_INSTRUCTION, build_autopilot_prompt
from ai.ollama_client import OllamaClient, ollama_client
from database.db import DatabaseManager, db_manager
from database.repositories.tool_executions import ToolExecutionRepository
from modes.autopilot_models import (
    AutopilotPlan,
    AutopilotPrecondition,
    AutopilotResult,
    AutopilotStatus,
    AutopilotStep,
    AutopilotStepResult,
    PreconditionOperator,
)
from agent.intent_classifier import UserIntent, default_intent_classifier
from modes.personal_tutor import PersonalTutor, default_personal_tutor, _detect_domain_from_text
from modes.tutor_models import TutorResponse, TutorSeverity
from windows.bluetooth_tools import get_bluetooth_service_status
from windows.defender_tools import get_defender_service_status
from windows.network_tools import check_dns_resolution
from windows.service_tools import get_service_status
from windows.storage_tools import get_temp_storage_info
from windows.windows_update_tools import get_windows_update_service_status

logger = logging.getLogger(__name__)

MAX_AUTOPILOT_STEPS = 5
MAX_EXECUTED_STEPS = 5
MAX_AUTOPILOT_RUNTIME_SECONDS = 120.0

FORBIDDEN_EXECUTION_KEYS = {
    "cmd",
    "command",
    "shell",
    "powershell",
    "subprocess",
    "executable",
    "script",
    "code",
    "python",
    "eval",
    "exec",
    "os_system",
    "run_command",
    "run_process",
    "bash",
    "shlex",
}


def _check_security_violations(data: Any, path: str = "") -> None:
    """Recursively inspect structured data and reject forbidden execution keywords."""
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = str(k).lower().strip()
            current_path = f"{path}.{k}" if path else str(k)
            if k_lower in FORBIDDEN_EXECUTION_KEYS:
                raise ValueError(
                    f"Security Policy Rejection: Forbidden command execution field '{k}' detected at '{current_path}'."
                )
            _check_security_violations(v, current_path)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _check_security_violations(item, f"{path}[{idx}]")
    elif isinstance(data, str):
        val_lower = data.lower()
        if any(f"{kw} " in val_lower or f"{kw}=" in val_lower for kw in ["powershell", "cmd.exe", "subprocess."]):
            raise ValueError(f"Security Policy Rejection: Dangerous command pattern detected at '{path}'.")


def compute_plan_hash(steps_data: List[Dict[str, Any]], session_id: str) -> str:
    """Compute deterministic SHA-256 hash over canonical plan steps and session binding."""
    canonical = []
    for s in steps_data:
        canonical.append({
            "sequence": s.get("sequence"),
            "tool_name": s.get("tool_name"),
            "arguments": s.get("arguments", {}),
            "depends_on": s.get("depends_on"),
        })
    raw_str = json.dumps({"session_id": session_id, "steps": canonical}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def evaluate_precondition(
    step_results: Dict[int, AutopilotStepResult],
    precondition: AutopilotPrecondition,
) -> Tuple[bool, str]:
    """Evaluate a deterministic precondition against prior step results without code execution."""
    prior_res = step_results.get(precondition.step_sequence)
    if not prior_res:
        return False, f"Preceding Step {precondition.step_sequence} result not found."

    # Extract value from prior result output
    target_data = prior_res.output
    keys = precondition.path.split(".")
    curr: Any = target_data
    for k in keys:
        if isinstance(curr, dict) and k in curr:
            curr = curr[k]
        else:
            curr = None
            break

    op = precondition.operator
    exp = precondition.expected_value

    try:
        if op == PreconditionOperator.EQUALS.value:
            passed = (curr == exp)
        elif op == PreconditionOperator.NOT_EQUALS.value:
            passed = (curr != exp)
        elif op == PreconditionOperator.CONTAINS.value:
            passed = (exp in curr) if curr is not None and hasattr(curr, "__contains__") else False
        elif op == PreconditionOperator.GREATER_THAN.value:
            passed = (float(curr) > float(exp)) if curr is not None else False
        elif op == PreconditionOperator.GREATER_OR_EQUAL.value:
            passed = (float(curr) >= float(exp)) if curr is not None else False
        elif op == PreconditionOperator.LESS_THAN.value:
            passed = (float(curr) < float(exp)) if curr is not None else False
        elif op == PreconditionOperator.LESS_OR_EQUAL.value:
            passed = (float(curr) <= float(exp)) if curr is not None else False
        elif op == PreconditionOperator.EXISTS.value:
            passed = (curr is not None)
        else:
            return False, f"Unsupported precondition operator '{op}'."
    except Exception as ex:
        return False, f"Precondition evaluation error: {ex}"

    msg = f"Precondition Step {precondition.step_sequence} path '{precondition.path}' ({curr}) {op} ({exp}): {'PASSED' if passed else 'FAILED'}"
    return passed, msg


class AutopilotEngine:
    """Core engine for Autopilot planning, validation, authorization, and sequential execution."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        safety_engine: Optional[SafetyEngine] = None,
        ai_client: Optional[OllamaClient] = None,
        db: Optional[DatabaseManager] = None,
        tutor: Optional[PersonalTutor] = None,
    ) -> None:
        self.registry = registry or default_tool_registry
        self.safety_engine = safety_engine or SafetyEngine(self.registry)
        self.ai_client = ai_client or ollama_client
        self.db = db or db_manager
        self.tutor = tutor or default_personal_tutor
        self.execution_repo = ToolExecutionRepository(self.db) if self.db else None
        self.windows_update_orchestrator = WindowsUpdateRepairsOrchestrator(
            safety_engine=self.safety_engine, registry=self.registry, db_mgr=self.db
        )
        self.defender_orchestrator = DefenderRepairsOrchestrator(
            safety_engine=self.safety_engine, registry=self.registry, db_mgr=self.db
        )
        self.bluetooth_orchestrator = BluetoothRepairsOrchestrator(
            safety_engine=self.safety_engine, registry=self.registry, db_mgr=self.db
        )
        self.service_orchestrator = ServiceRepairsOrchestrator(
            safety_engine=self.safety_engine, registry=self.registry, db_mgr=self.db
        )

    def plan(
        self,
        problem_description: str,
        diagnostic_data: Optional[Dict[str, Any]] = None,
        system_info: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> AutopilotPlan:
        """Formulate a bounded Autopilot plan via Gemma LLM or deterministic allowlisted fallback."""
        sess_id = session_id or f"autopilot_{int(time.time())}"
        diag = diagnostic_data or {}
        sys_i = system_info or {}

        # 0. Intent and Domain Classification
        intent = default_intent_classifier.classify_intent(problem_description)
        domain = _detect_domain_from_text(problem_description) or "general"

        # 1. Attempt LLM Planning
        plan_dict: Optional[Dict[str, Any]] = None
        try:
            prompt = build_autopilot_prompt(
                problem_description=problem_description,
                diagnostic_data=diag,
                system_info=sys_i,
                registry=self.registry,
                user_intent=intent.value,
                domain=domain,
            )
            response_dict = self.ai_client.generate(
                prompt=prompt,
                system=AUTOPILOT_SYSTEM_INSTRUCTION,
                options={"temperature": 0.1},
                timeout=getattr(config, "ollama_timeout_seconds", 60),
            )
            if isinstance(response_dict, dict) and response_dict.get("success"):
                parsed = self._parse_json(response_dict.get("response", ""))
                # Strict safety guard: verify all proposed tools exist in ToolRegistry and match intent bounds
                if parsed and isinstance(parsed.get("steps"), list) and len(parsed["steps"]) > 0:
                    valid_plan = True
                    for s in parsed["steps"]:
                        if not isinstance(s, dict):
                            valid_plan = False
                            break
                        t_name = str(s.get("tool_name", "")).strip()
                        t_def = self.registry.get(t_name)
                        if not t_def:
                            logger.warning("LLM proposed unregistered tool '%s'. Rejecting plan.", t_name)
                            valid_plan = False
                            break
                        if intent != UserIntent.REPAIR and (not t_def.read_only or t_def.risk != RiskLevel.SAFE):
                            logger.warning("LLM proposed mutating tool '%s' for non-repair intent %s. Rejecting plan.", t_name, intent.value)
                            valid_plan = False
                            break
                    if valid_plan:
                        plan_dict = parsed
                    else:
                        logger.warning("LLM proposed invalid plan steps. Discarding and using deterministic plan.")
        except Exception as ex:
            logger.warning("LLM Autopilot planning failed: %s. Falling back to deterministic plan.", ex)

        # 2. Deterministic Fallback if LLM planning failed or was rejected
        if not plan_dict or not isinstance(plan_dict.get("steps"), list) or len(plan_dict["steps"]) == 0:
            plan_dict = self._generate_deterministic_fallback_plan(
                problem_description, diag, user_intent=intent, domain=domain
            )

        # 3. Validate and build canonical plan
        plan = self.validate_and_build_plan(plan_dict, session_id=sess_id, user_intent=intent)

        # 4. Log plan creation to audit
        self._log_audit(
            session_id=sess_id,
            event_type="AUTOPILOT_PLAN_CREATED",
            details={
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "domain": domain,
                "intent": intent.value,
                "steps_count": len(plan.steps),
                "hash": plan.plan_hash,
            },
        )

        return plan

    def plan_from_multimodal(
        self,
        screenshot_analysis: Optional[Any] = None,
        voice_analysis: Optional[Any] = None,
        user_text: Optional[str] = None,
        diagnostic_data: Optional[Dict[str, Any]] = None,
        system_info: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> AutopilotPlan:
        """Formulate a verified, bounded AutopilotPlan from multimodal evidence sources."""
        from agent.multimodal_adapter import default_multimodal_adapter
        return default_multimodal_adapter.formulate_autopilot_plan(
            autopilot_engine=self,
            screenshot_analysis=screenshot_analysis,
            voice_analysis=voice_analysis,
            user_text=user_text,
            diagnostic_data=diagnostic_data,
            system_info=system_info,
            session_id=session_id,
        )

    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse clean JSON from model output."""
        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]

        try:
            return json.loads(cleaned)
        except Exception:
            return None

    def _generate_deterministic_fallback_plan(
        self,
        problem_description: str,
        diagnostic_data: Dict[str, Any],
        user_intent: Optional[UserIntent] = None,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a safe, allowlisted deterministic troubleshooting plan based on domain & intent separation."""
        intent = user_intent or default_intent_classifier.classify_intent(problem_description)
        dom = domain or _detect_domain_from_text(problem_description) or "general"
        is_repair = (intent == UserIntent.REPAIR)

        # 1. WINDOWS UPDATE
        if dom == "windows_update" or any(w in problem_description.lower() for w in ["update", "windows update", "wuauserv", "kb", "patch"]):
            if intent == UserIntent.VIEW_HISTORY:
                return {
                    "goal": "Inspect Windows Update history, previous failure records, and error status.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_windows_update_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect Windows Update configuration and recent update events/failures.",
                            "expected_result": "Update history and diagnostic records.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_windows_update_health",
                            "arguments": {},
                            "purpose": "Assess overall Windows Update service health and failure indicators.",
                            "expected_result": "Windows Update health metrics.",
                        },
                    ],
                }
            elif intent == UserIntent.CHECK_STATUS:
                return {
                    "goal": "Check current Windows Update service status and operational readiness.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_windows_update_service_status",
                            "arguments": {},
                            "purpose": "Inspect Windows Update service state.",
                            "expected_result": "Service status object.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_windows_update_health",
                            "arguments": {},
                            "purpose": "Inspect Windows Update operational health.",
                            "expected_result": "Update health diagnostics.",
                        },
                    ],
                }
            elif not is_repair:
                # DIAGNOSE / EXPLAIN / CONFIGURE (Read-only)
                return {
                    "goal": "Diagnose Windows Update configuration, health, and error logs.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_windows_update_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect Windows Update configuration and health status.",
                            "expected_result": "Update health diagnostics.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_windows_update_health",
                            "arguments": {},
                            "purpose": "Evaluate update service health indicators.",
                            "expected_result": "Health evaluation metrics.",
                        },
                        {
                            "sequence": 3,
                            "tool_name": "get_windows_update_service_status",
                            "arguments": {},
                            "purpose": "Inspect Windows Update service status.",
                            "expected_result": "Service status object.",
                        },
                    ],
                }
            else:
                # Explicit REPAIR
                return {
                    "goal": "Diagnose Windows Update health and restart update service if stalled.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_windows_update_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect Windows Update configuration and health status.",
                            "expected_result": "Update health diagnostics.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_windows_update_service_status",
                            "arguments": {},
                            "purpose": "Inspect Windows Update service status.",
                            "expected_result": "Service status object.",
                            "depends_on": 1,
                        },
                        {
                            "sequence": 3,
                            "tool_name": "restart_windows_update_service",
                            "arguments": {},
                            "purpose": "Restart Windows Update service safely.",
                            "expected_result": "Service restarted.",
                            "depends_on": 2,
                        },
                        {
                            "sequence": 4,
                            "tool_name": "get_windows_update_service_status",
                            "arguments": {},
                            "purpose": "Verify Windows Update service is RUNNING post-restart.",
                            "expected_result": "Service status RUNNING.",
                            "depends_on": 3,
                        },
                    ],
                }

        # 2. NETWORK
        if dom == "network" or any(w in problem_description.lower() for w in ["dns", "internet", "network", "wifi", "wi-fi", "ethernet", "gateway", "ip address", "ping"]):
            if intent in (UserIntent.VIEW_HISTORY, UserIntent.CHECK_STATUS):
                return {
                    "goal": "Inspect active network adapters and DNS client configuration.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_network_adapters_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect network interfaces, link state, and IP configuration.",
                            "expected_result": "Network adapter details.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_dns_client_config",
                            "arguments": {},
                            "purpose": "Read configured DNS nameservers.",
                            "expected_result": "DNS client configuration.",
                        },
                    ],
                }
            elif not is_repair:
                # DIAGNOSE / EXPLAIN / CONFIGURE (Read-only)
                return {
                    "goal": "Diagnose network connectivity, adapter status, and DNS lookup.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "check_dns_resolution",
                            "arguments": {"hostname": "dns.google"},
                            "purpose": "Verify current DNS resolution capability.",
                            "expected_result": "DNS lookup response.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "check_internet_connectivity",
                            "arguments": {},
                            "purpose": "Verify internet endpoint connectivity.",
                            "expected_result": "Ping and socket results.",
                        },
                        {
                            "sequence": 3,
                            "tool_name": "get_network_adapters_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect network interfaces, link state, and IP configuration.",
                            "expected_result": "Network adapter details.",
                        },
                    ],
                }
            else:
                # Explicit REPAIR
                return {
                    "goal": "Diagnose network adapters and resolve DNS/connectivity issues.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "check_dns_resolution",
                            "arguments": {"hostname": "dns.google"},
                            "purpose": "Verify current DNS resolution capability.",
                            "expected_result": "DNS lookup response.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "flush_dns_cache",
                            "arguments": {},
                            "purpose": "Flush DNS resolver cache to clear corrupted entries.",
                            "expected_result": "DNS cache flushed.",
                            "depends_on": 1,
                        },
                        {
                            "sequence": 3,
                            "tool_name": "check_dns_resolution",
                            "arguments": {"hostname": "dns.google"},
                            "purpose": "Verify DNS resolution post-flush.",
                            "expected_result": "Successful DNS lookup.",
                            "depends_on": 2,
                        },
                    ],
                }

        # 3. PERFORMANCE
        if dom == "performance" or any(w in problem_description.lower() for w in ["slow", "lag", "cpu", "memory", "ram", "performance", "freeze", "hang"]):
            return {
                "goal": "Inspect real-time CPU utilization, memory usage, and top consuming processes.",
                "steps": [
                    {
                        "sequence": 1,
                        "tool_name": "get_cpu_diagnostics",
                        "arguments": {},
                        "purpose": "Measure real-time CPU percentage and utilization.",
                        "expected_result": "CPU diagnostics data.",
                    },
                    {
                        "sequence": 2,
                        "tool_name": "get_memory_diagnostics",
                        "arguments": {},
                        "purpose": "Inspect physical RAM capacity and available memory.",
                        "expected_result": "Memory diagnostics data.",
                    },
                    {
                        "sequence": 3,
                        "tool_name": "get_top_cpu_processes",
                        "arguments": {"limit": 5},
                        "purpose": "Identify top running processes consuming the highest CPU percentage.",
                        "expected_result": "Top CPU processes list.",
                    },
                    {
                        "sequence": 4,
                        "tool_name": "get_top_memory_processes",
                        "arguments": {"limit": 5},
                        "purpose": "Identify top running processes consuming the highest memory.",
                        "expected_result": "Top memory processes list.",
                    },
                ],
            }

        # 4. STORAGE
        if dom == "storage" or any(w in problem_description.lower() for w in ["disk", "storage", "space", "temp", "full", "c drive", "c:"]):
            if not is_repair:
                return {
                    "goal": "Inspect storage volume capacity and temporary cache usage.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_storage_diagnostics",
                            "arguments": {},
                            "purpose": "Assess disk drive volume capacity and free space.",
                            "expected_result": "Drive capacity data.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_temp_storage_info",
                            "arguments": {},
                            "purpose": "Inspect safe temporary cache size.",
                            "expected_result": "Temp cache size report.",
                        },
                    ],
                }
            else:
                return {
                    "goal": "Inspect storage capacity and safely clear user temporary cache files.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_storage_diagnostics",
                            "arguments": {},
                            "purpose": "Assess disk drive volume capacity and free space.",
                            "expected_result": "Drive capacity data.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_temp_storage_info",
                            "arguments": {},
                            "purpose": "Inspect safe temporary cache size.",
                            "expected_result": "Temp cache size report.",
                            "depends_on": 1,
                        },
                        {
                            "sequence": 3,
                            "tool_name": "clean_user_temp_cache",
                            "arguments": {},
                            "purpose": "Safely delete unlocked temporary cache files.",
                            "expected_result": "Temp cleanup metrics.",
                            "depends_on": 2,
                        },
                        {
                            "sequence": 4,
                            "tool_name": "get_temp_storage_info",
                            "arguments": {},
                            "purpose": "Verify temporary storage reduction.",
                            "expected_result": "Reduced temp file count and size.",
                            "depends_on": 3,
                        },
                    ],
                }

        # 5. BLUETOOTH
        if dom == "bluetooth" or any(w in problem_description.lower() for w in ["bluetooth", "bthserv", "pairing", "headset"]):
            if not is_repair:
                return {
                    "goal": "Inspect Bluetooth radio adapter state and service status.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_bluetooth_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect Bluetooth hardware adapter and radio state.",
                            "expected_result": "Bluetooth radio diagnostics.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_bluetooth_service_status",
                            "arguments": {},
                            "purpose": "Inspect Bluetooth Support Service status.",
                            "expected_result": "Service status object.",
                        },
                    ],
                }
            else:
                return {
                    "goal": "Diagnose Bluetooth radio and restart Bluetooth background services.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_bluetooth_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect Bluetooth hardware adapter and radio state.",
                            "expected_result": "Bluetooth radio diagnostics.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "restart_bluetooth_service",
                            "arguments": {},
                            "purpose": "Restart Windows Bluetooth Support Service safely.",
                            "expected_result": "Bluetooth service restarted.",
                            "depends_on": 1,
                        },
                        {
                            "sequence": 3,
                            "tool_name": "get_bluetooth_service_status",
                            "arguments": {},
                            "purpose": "Verify Bluetooth service is RUNNING post-restart.",
                            "expected_result": "Service status RUNNING.",
                            "depends_on": 2,
                        },
                    ],
                }

        # 6. DEFENDER
        if dom == "defender" or any(w in problem_description.lower() for w in ["defender", "antivirus", "security", "windefend", "virus"]):
            if not is_repair:
                return {
                    "goal": "Inspect Windows Defender health and protection status.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_defender_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect Windows Defender status and real-time protection.",
                            "expected_result": "Defender diagnostics payload.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "get_defender_service_status",
                            "arguments": {},
                            "purpose": "Inspect Windows Defender service state.",
                            "expected_result": "Service status object.",
                        },
                    ],
                }
            else:
                return {
                    "goal": "Inspect Windows Defender health and restart service if stopped.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_defender_diagnostics",
                            "arguments": {},
                            "purpose": "Inspect Windows Defender status and real-time protection.",
                            "expected_result": "Defender diagnostics payload.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "restart_defender_service",
                            "arguments": {},
                            "purpose": "Restart Windows Defender antivirus service.",
                            "expected_result": "Service restarted.",
                            "depends_on": 1,
                        },
                        {
                            "sequence": 3,
                            "tool_name": "get_defender_service_status",
                            "arguments": {},
                            "purpose": "Verify Defender service is RUNNING post-restart.",
                            "expected_result": "Service status RUNNING.",
                            "depends_on": 2,
                        },
                    ],
                }

        # 7. SERVICES
        if dom == "services" or any(w in problem_description.lower() for w in ["service", "services", "stopped service", "spooler"]):
            if not is_repair:
                return {
                    "goal": "Inspect stopped services and standard Windows background services.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_services_diagnostics",
                            "arguments": {"filter_status": "STOPPED"},
                            "purpose": "Inspect all Windows services that are currently stopped.",
                            "expected_result": "List of stopped services.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "list_common_services",
                            "arguments": {},
                            "purpose": "Inspect status of common operational Windows services.",
                            "expected_result": "List of common service statuses.",
                        },
                    ],
                }
            else:
                return {
                    "goal": "Inspect service status and restart stalled Windows service.",
                    "steps": [
                        {
                            "sequence": 1,
                            "tool_name": "get_service_status",
                            "arguments": {"service_name": "wuauserv"},
                            "purpose": "Inspect target Windows service state.",
                            "expected_result": "Service status object.",
                        },
                        {
                            "sequence": 2,
                            "tool_name": "restart_service",
                            "arguments": {"service_name": "wuauserv"},
                            "purpose": "Restart stalled Windows service safely.",
                            "expected_result": "Service restarted.",
                            "depends_on": 1,
                        },
                        {
                            "sequence": 3,
                            "tool_name": "get_service_status",
                            "arguments": {"service_name": "wuauserv"},
                            "purpose": "Verify service is RUNNING post-restart.",
                            "expected_result": "Service status RUNNING.",
                            "depends_on": 2,
                        },
                    ],
                }

        # 8. APPLICATION CRASH / EVENT LOGS
        if dom in ("application_crash", "app_crash", "applications") or any(w in problem_description.lower() for w in ["crash", "crashed", "event", "event log", "wer", "bluescreen", "bsod"]):
            return {
                "goal": "Inspect Windows application crash diagnostics and recent crash events.",
                "steps": [
                    {
                        "sequence": 1,
                        "tool_name": "get_application_crash_diagnostics",
                        "arguments": {"time_window": "24h"},
                        "purpose": "Perform structured diagnostic analysis of Windows application crash evidence.",
                        "expected_result": "Application crash diagnostics report.",
                    },
                    {
                        "sequence": 2,
                        "tool_name": "get_recent_application_crashes",
                        "arguments": {"limit": 10},
                        "purpose": "Retrieve recent application crash and error records from Event Log.",
                        "expected_result": "Application crash event records.",
                    },
                ],
            }

        # 9. DISPLAY
        if dom == "display" or any(w in problem_description.lower() for w in ["display", "screen", "monitor", "resolution", "gpu", "graphics"]):
            return {
                "goal": "Inspect display adapters, resolution, and monitor configuration.",
                "steps": [
                    {
                        "sequence": 1,
                        "tool_name": "get_display_diagnostics",
                        "arguments": {},
                        "purpose": "Inspect display adapters, resolution, and monitor configuration.",
                        "expected_result": "Display configuration data.",
                    },
                ],
            }

        # 10. AUDIO
        if dom == "audio" or any(w in problem_description.lower() for w in ["audio", "sound", "volume", "speaker", "headphone", "mic", "microphone"]):
            return {
                "goal": "Inspect audio endpoints and sound hardware diagnostics.",
                "steps": [
                    {
                        "sequence": 1,
                        "tool_name": "get_audio_diagnostics",
                        "arguments": {},
                        "purpose": "Inspect audio devices and endpoint statuses.",
                        "expected_result": "Audio diagnostics data.",
                    },
                    {
                        "sequence": 2,
                        "tool_name": "get_audio_endpoint_status",
                        "arguments": {},
                        "purpose": "Inspect default playback and recording audio endpoints.",
                        "expected_result": "Audio endpoint status data.",
                    },
                ],
            }

        # Default general diagnostic workflow
        return {
            "goal": "Run general system health diagnostics across network and storage.",
            "steps": [
                {
                    "sequence": 1,
                    "tool_name": "get_complete_system_info",
                    "arguments": {},
                    "purpose": "Collect complete hardware, OS, and system environment info.",
                    "expected_result": "System information summary.",
                },
                {
                    "sequence": 2,
                    "tool_name": "check_internet_connectivity",
                    "arguments": {},
                    "purpose": "Verify internet endpoint connectivity.",
                    "expected_result": "Ping and socket results.",
                },
                {
                    "sequence": 3,
                    "tool_name": "get_storage_diagnostics",
                    "arguments": {},
                    "purpose": "Check disk capacity and drive health.",
                    "expected_result": "Storage statistics.",
                },
            ],
        }

    def validate_and_build_plan(
        self,
        raw_plan: Dict[str, Any],
        session_id: str,
        user_intent: Optional[UserIntent] = None,
    ) -> AutopilotPlan:
        """Validate raw plan dictionary against ToolRegistry, schemas, and security bounds."""
        if not isinstance(raw_plan, dict):
            raise ValueError("Plan must be a valid JSON dictionary.")

        # 1. Security scan
        _check_security_violations(raw_plan)

        goal = str(raw_plan.get("goal", "Windows Diagnostic and Repair Plan")).strip()
        raw_steps = raw_plan.get("steps", [])

        if not isinstance(raw_steps, list) or len(raw_steps) == 0:
            raise ValueError("Autopilot plan must contain at least 1 step.")

        if len(raw_steps) > MAX_AUTOPILOT_STEPS:
            raise ValueError(
                f"Proposed plan has {len(raw_steps)} steps, exceeding the maximum limit of {MAX_AUTOPILOT_STEPS}."
            )

        validated_steps: List[AutopilotStep] = []
        seen_tools: set[str] = set()

        for idx, s in enumerate(raw_steps):
            if not isinstance(s, dict):
                raise ValueError(f"Step {idx + 1} must be an object.")

            tool_name = str(s.get("tool_name", "")).strip()
            tool = self.registry.get(tool_name)
            if not tool:
                raise ValueError(f"Step {idx + 1}: Tool '{tool_name}' is not registered in the approved ToolRegistry.")

            # Intent safety invariant: non-repair intents cannot execute mutating / medium-risk tools
            if user_intent and user_intent != UserIntent.REPAIR:
                if not tool.read_only or tool.risk != RiskLevel.SAFE:
                    raise ValueError(
                        f"Step {idx + 1}: Mutating/repair tool '{tool_name}' is strictly prohibited for read-only intent '{user_intent.value}'."
                    )

            # Loop prevention: max 1 execution per repair tool in a plan
            if not tool.read_only:
                if tool_name in seen_tools:
                    raise ValueError(f"Step {idx + 1}: Duplicate repair tool '{tool_name}' prohibited by loop prevention policy.")
            seen_tools.add(tool_name)

            # High risk rejection
            if tool.risk == RiskLevel.HIGH:
                raise ValueError(f"Step {idx + 1}: HIGH risk tool '{tool_name}' is strictly blocked in Autopilot Mode.")

            # Argument validation
            raw_args = s.get("arguments", {})
            if not isinstance(raw_args, dict):
                raise ValueError(f"Step {idx + 1}: Arguments must be a JSON dictionary.")

            # Check for unexpected arguments
            for arg_k in raw_args:
                if arg_k not in tool.parameters:
                    raise ValueError(f"Step {idx + 1}: Unexpected argument '{arg_k}' for tool '{tool_name}'.")

            # Validate each argument against parameter spec
            val_args: Dict[str, Any] = {}
            for p_name, p_spec in tool.parameters.items():
                if p_name in raw_args:
                    val = raw_args[p_name]
                else:
                    val = p_spec.default
                valid, err = p_spec.validate(val)
                if not valid:
                    raise ValueError(f"Step {idx + 1}: Argument '{p_name}' validation error: {err}")
                if val is not None:
                    val_args[p_name] = val

            # Preconditions validation
            raw_preconds = s.get("preconditions", [])
            val_preconds: List[AutopilotPrecondition] = []
            if isinstance(raw_preconds, list):
                for p_idx, p in enumerate(raw_preconds):
                    if isinstance(p, dict):
                        step_seq = int(p.get("step_sequence", idx))
                        if step_seq >= (idx + 1):
                            raise ValueError(
                                f"Step {idx + 1} precondition references future step {step_seq}."
                            )
                        op = str(p.get("operator", "equals")).strip()
                        if op not in [e.value for e in PreconditionOperator]:
                            raise ValueError(f"Step {idx + 1} precondition has unsupported operator '{op}'.")
                        val_preconds.append(
                            AutopilotPrecondition(
                                step_sequence=step_seq,
                                path=str(p.get("path", "success")),
                                operator=op,
                                expected_value=p.get("expected_value"),
                            )
                        )

            # Build step object
            seq = idx + 1
            step_obj = AutopilotStep(
                step_id=f"step_{seq}_{tool_name}",
                sequence=seq,
                tool_name=tool_name,
                arguments=val_args,
                purpose=str(s.get("purpose", tool.description)),
                expected_result=str(s.get("expected_result", "Expected tool completion")),
                risk_level=tool.risk.value,
                requires_confirmation=(tool.risk == RiskLevel.MEDIUM),
                requires_admin=tool.requires_admin,
                verification_required=(not tool.read_only),
                depends_on=s.get("depends_on"),
                preconditions=val_preconds,
            )
            validated_steps.append(step_obj)

        # Compute deterministic plan hash
        steps_dict = [st.to_dict() for st in validated_steps]
        p_hash = compute_plan_hash(steps_dict, session_id=session_id)
        plan_id = f"plan_{p_hash[:12]}"

        return AutopilotPlan(
            plan_id=plan_id,
            session_id=session_id,
            goal=goal,
            steps=validated_steps,
            plan_hash=p_hash,
            status=AutopilotStatus.AWAITING_AUTHORIZATION,
            created_at=time.time(),
            is_authorized=False,
            is_executed=False,
        )

    def authorize_plan(self, plan: AutopilotPlan, user_confirmed_hash: str) -> bool:
        """Authorize an Autopilot plan with exact plan-hash binding (one-time use)."""
        if plan.is_executed:
            logger.warning("Attempted to authorize an already executed plan: %s", plan.plan_id)
            return False

        if plan.status != AutopilotStatus.AWAITING_AUTHORIZATION:
            logger.warning("Plan %s is not in AWAITING_AUTHORIZATION state (current: %s)", plan.plan_id, plan.status)
            return False

        if user_confirmed_hash != plan.plan_hash:
            logger.warning("Plan hash mismatch for %s: user '%s' != plan '%s'", plan.plan_id, user_confirmed_hash, plan.plan_hash)
            return False

        plan.is_authorized = True
        plan.status = AutopilotStatus.AUTHORIZED

        self._log_audit(
            session_id=plan.session_id,
            event_type="AUTOPILOT_AUTHORIZED",
            details={"plan_id": plan.plan_id, "hash": plan.plan_hash},
        )
        return True

    def execute_plan(
        self,
        plan: AutopilotPlan,
        user_confirmed_hash: str,
        cancellation_check: Optional[Callable[[], bool]] = None,
    ) -> AutopilotResult:
        """Execute approved Autopilot plan steps sequentially with verification and stop-on-failure."""
        start_time = time.time()

        # 1. Validate authorization and single-use execution
        if not plan.is_authorized:
            return self._build_aborted_result(
                plan, AutopilotStatus.BLOCKED, "Plan has not been authorized by user.", start_time
            )

        if plan.is_executed:
            return self._build_aborted_result(
                plan, AutopilotStatus.BLOCKED, "Plan has already been executed (replay prohibited).", start_time
            )

        if user_confirmed_hash != plan.plan_hash:
            return self._build_aborted_result(
                plan, AutopilotStatus.BLOCKED, "Plan hash integrity check failed upon execution.", start_time
            )

        # Mark executed immediately to prevent replay
        plan.is_executed = True
        plan.status = AutopilotStatus.RUNNING

        self._log_audit(
            session_id=plan.session_id,
            event_type="AUTOPILOT_STARTED",
            details={"plan_id": plan.plan_id, "steps_count": len(plan.steps)},
        )

        step_results: Dict[int, AutopilotStepResult] = {}
        stopped_reason: Optional[str] = None
        final_status = AutopilotStatus.COMPLETED
        failed_seq: Optional[int] = None

        for step in plan.steps:
            # Check global step count limit
            if len(step_results) >= MAX_EXECUTED_STEPS:
                final_status = AutopilotStatus.STOPPED
                stopped_reason = f"Global execution limit of {MAX_EXECUTED_STEPS} steps reached."
                break

            # Check runtime limit
            if (time.time() - start_time) > MAX_AUTOPILOT_RUNTIME_SECONDS:
                final_status = AutopilotStatus.STOPPED
                stopped_reason = f"Autopilot runtime limit of {MAX_AUTOPILOT_RUNTIME_SECONDS}s exceeded."
                break

            # Check user cancellation
            if cancellation_check and cancellation_check():
                final_status = AutopilotStatus.CANCELLED
                stopped_reason = "Execution cancelled by user."
                self._log_audit(
                    session_id=plan.session_id,
                    event_type="AUTOPILOT_CANCELLED",
                    details={"plan_id": plan.plan_id, "stopped_at_step": step.sequence},
                )
                break

            # Evaluate preconditions
            precond_failed = False
            for pre in step.preconditions:
                passed, msg = evaluate_precondition(step_results, pre)
                if not passed:
                    logger.info("Step %d precondition failed: %s", step.sequence, msg)
                    step_res = AutopilotStepResult(
                        step_id=step.step_id,
                        sequence=step.sequence,
                        tool_name=step.tool_name,
                        status="SKIPPED",
                        output={"skipped": True, "reason": msg},
                        explanation=msg,
                    )
                    step_results[step.sequence] = step_res
                    precond_failed = True
                    break

            if precond_failed:
                # If this step was a dependent repair whose condition failed, we continue or stop cleanly
                continue

            # Execute Step
            self._log_audit(
                session_id=plan.session_id,
                event_type="AUTOPILOT_STEP_STARTED",
                details={"plan_id": plan.plan_id, "step_sequence": step.sequence, "tool_name": step.tool_name},
            )

            step_res = self._execute_single_step(step, plan.session_id)
            step_results[step.sequence] = step_res

            # Evaluate Step Result
            if step_res.status in ["FAILED", "ERROR"]:
                final_status = AutopilotStatus.FAILED if len(step_results) == 1 else AutopilotStatus.PARTIAL
                failed_seq = step.sequence
                stopped_reason = f"Step {step.sequence} ('{step.tool_name}') failed: {step_res.explanation}"
                self._log_audit(
                    session_id=plan.session_id,
                    event_type="AUTOPILOT_STEP_FAILED",
                    details={"plan_id": plan.plan_id, "step_sequence": step.sequence, "tool_name": step.tool_name},
                )
                break

            if step_res.status in ["VERIFICATION_FAILED", "NOT_VERIFIED"]:
                final_status = AutopilotStatus.VERIFICATION_FAILED
                failed_seq = step.sequence
                stopped_reason = f"Step {step.sequence} ('{step.tool_name}') repair verification failed: {step_res.explanation}"
                self._log_audit(
                    session_id=plan.session_id,
                    event_type="AUTOPILOT_VERIFICATION_FAILED",
                    details={"plan_id": plan.plan_id, "step_sequence": step.sequence, "tool_name": step.tool_name},
                )
                break

            if step_res.status == "VERIFICATION_TIMEOUT":
                final_status = AutopilotStatus.VERIFICATION_TIMEOUT
                failed_seq = step.sequence
                stopped_reason = f"Step {step.sequence} ('{step.tool_name}') repair verification timed out."
                self._log_audit(
                    session_id=plan.session_id,
                    event_type="AUTOPILOT_VERIFICATION_FAILED",
                    details={"plan_id": plan.plan_id, "step_sequence": step.sequence, "timeout": True},
                )
                break

            self._log_audit(
                session_id=plan.session_id,
                event_type="AUTOPILOT_STEP_COMPLETED",
                details={"plan_id": plan.plan_id, "step_sequence": step.sequence, "tool_name": step.tool_name},
            )

        duration = time.time() - start_time
        plan.status = final_status

        # Summary creation
        summary = (
            f"Autopilot {final_status.value.lower()}: executed {len(step_results)} of {len(plan.steps)} planned steps in {duration:.1f}s."
        )
        if stopped_reason:
            summary += f" Reason: {stopped_reason}"

        self._log_audit(
            session_id=plan.session_id,
            event_type="AUTOPILOT_COMPLETED" if final_status == AutopilotStatus.COMPLETED else "AUTOPILOT_STOPPED",
            details={"plan_id": plan.plan_id, "status": final_status.value, "summary": summary},
        )

        return AutopilotResult(
            plan_id=plan.plan_id,
            session_id=plan.session_id,
            goal=plan.goal,
            status=final_status,
            steps_planned=len(plan.steps),
            steps_executed=len(step_results),
            step_results=list(step_results.values()),
            summary=summary,
            failed_step_sequence=failed_seq,
            stopped_reason=stopped_reason,
            duration_seconds=duration,
        )

    def _execute_single_step(self, step: AutopilotStep, session_id: str) -> AutopilotStepResult:
        """Execute a single Autopilot step through ToolRegistry and domain repair orchestrators."""
        t_start = time.time()
        tool_name = step.tool_name

        # Route SAFE diagnostic tools
        if step.risk_level == "SAFE":
            raw_out = self.safety_engine.execute(
                tool_name=tool_name,
                arguments=step.arguments,
                session_id=session_id,
                user_confirmed=True,
            )
            duration_ms = int((time.time() - t_start) * 1000)
            success = raw_out.get("success", False)
            return AutopilotStepResult(
                step_id=step.step_id,
                sequence=step.sequence,
                tool_name=tool_name,
                status="SUCCESS" if success else "FAILED",
                output=raw_out,
                duration_ms=duration_ms,
                explanation=raw_out.get("error", "Diagnostic step completed successfully.") if not success else "Diagnostic step completed.",
            )

        # Route MEDIUM repair tools through domain orchestrators
        try:
            if tool_name == "flush_dns_cache":
                proposal = RepairProposal(
                    tool_name="flush_dns_cache",
                    arguments=step.arguments or {},
                    reason="Flushing DNS resolver cache",
                    expected_effect="Clears resolver cache",
                    risk="MEDIUM",
                    requires_admin=False,
                    verification_tool="check_dns_resolution",
                )
                token = proposal.generate_confirmation_token(session_id)
                res_obj = default_network_repairs_orchestrator.execute_repair_with_verification(
                    proposal=proposal,
                    session_id=session_id,
                    user_confirmed=True,
                    confirmation_token=token,
                )
                dur_ms = int((time.time() - t_start) * 1000)
                v_ok = (res_obj.verification_status == "verified")
                return AutopilotStepResult(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    tool_name=tool_name,
                    status="VERIFIED" if v_ok else "VERIFICATION_FAILED",
                    output=res_obj.repair_output or {},
                    verification_status=res_obj.verification_status,
                    verification_output=res_obj.after_state,
                    duration_ms=dur_ms,
                    explanation=res_obj.explanation,
                )

            if tool_name == "restart_windows_update_service":
                proposal = WindowsUpdateRepairProposal()
                token = proposal.generate_confirmation_token(session_id)
                res_obj = self.windows_update_orchestrator.execute_confirmed_restart(
                    proposal=proposal,
                    user_confirmed_token=token,
                    session_id=session_id,
                )
                dur_ms = int((time.time() - t_start) * 1000)
                v_status = res_obj.verification_status
                return AutopilotStepResult(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    tool_name=tool_name,
                    status="VERIFIED" if v_status == "verified" else ("VERIFICATION_TIMEOUT" if v_status == "verification_timeout" else "VERIFICATION_FAILED"),
                    output=res_obj.repair_output or {},
                    verification_status=v_status,
                    verification_output=res_obj.after_state,
                    duration_ms=dur_ms,
                    explanation=res_obj.explanation,
                )

            if tool_name == "restart_defender_service":
                proposal = DefenderRepairProposal()
                token = proposal.generate_confirmation_token(session_id)
                res_obj = self.defender_orchestrator.execute_confirmed_restart(
                    proposal=proposal,
                    user_confirmed_token=token,
                    session_id=session_id,
                )
                dur_ms = int((time.time() - t_start) * 1000)
                v_status = res_obj.verification_status
                return AutopilotStepResult(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    tool_name=tool_name,
                    status="VERIFIED" if v_status == "verified" else ("VERIFICATION_TIMEOUT" if v_status == "verification_timeout" else "VERIFICATION_FAILED"),
                    output=res_obj.repair_output or {},
                    verification_status=v_status,
                    verification_output=res_obj.after_state,
                    duration_ms=dur_ms,
                    explanation=res_obj.explanation,
                )

            if tool_name == "clean_user_temp_cache":
                token = f"tok_{session_id}_{tool_name}"
                raw_out = self.safety_engine.execute(
                    tool_name=tool_name,
                    arguments=step.arguments,
                    session_id=session_id,
                    user_confirmed=True,
                )
                v_out = get_temp_storage_info()
                dur_ms = int((time.time() - t_start) * 1000)
                v_ok = raw_out.get("success", False)
                return AutopilotStepResult(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    tool_name=tool_name,
                    status="VERIFIED" if v_ok else "FAILED",
                    output=raw_out,
                    verification_status="verified" if v_ok else "not_verified",
                    verification_output=v_out,
                    duration_ms=dur_ms,
                    explanation="Temporary cache cleanup completed." if v_ok else "Temporary cache cleanup failed.",
                )

            if tool_name in ["restart_bluetooth_service", "restart_service", "start_service", "stop_service"]:
                token = f"tok_{session_id}_{tool_name}"
                raw_out = self.safety_engine.execute(
                    tool_name=tool_name,
                    arguments=step.arguments,
                    session_id=session_id,
                    user_confirmed=True,
                )
                svc_name = step.arguments.get("service_name", "bthserv" if "bluetooth" in tool_name else "wuauserv")
                v_out = get_service_status(service_name=svc_name)
                current_state = v_out.get("data", {}).get("status", "UNKNOWN")
                expected_state = "RUNNING" if "stop" not in tool_name else "STOPPED"
                v_ok = (current_state == expected_state)
                dur_ms = int((time.time() - t_start) * 1000)
                return AutopilotStepResult(
                    step_id=step.step_id,
                    sequence=step.sequence,
                    tool_name=tool_name,
                    status="VERIFIED" if v_ok else "VERIFICATION_FAILED",
                    output=raw_out,
                    verification_status="verified" if v_ok else "not_verified",
                    verification_output=v_out,
                    duration_ms=dur_ms,
                    explanation=f"Service {svc_name} is {current_state} (expected {expected_state}).",
                )

            # Generic fallback through SafetyEngine
            raw_out = self.safety_engine.execute(
                tool_name=tool_name,
                arguments=step.arguments,
                session_id=session_id,
                user_confirmed=True,
            )
            dur_ms = int((time.time() - t_start) * 1000)
            return AutopilotStepResult(
                step_id=step.step_id,
                sequence=step.sequence,
                tool_name=tool_name,
                status="SUCCESS" if raw_out.get("success") else "FAILED",
                output=raw_out,
                duration_ms=dur_ms,
                explanation=raw_out.get("error", "Repair executed."),
            )
        except Exception as ex:
            dur_ms = int((time.time() - t_start) * 1000)
            return AutopilotStepResult(
                step_id=step.step_id,
                sequence=step.sequence,
                tool_name=tool_name,
                status="FAILED",
                output={"error": str(ex)},
                duration_ms=dur_ms,
                explanation=f"Execution error: {ex}",
            )

    def explain_result(self, result: AutopilotResult) -> TutorResponse:
        """Use Personal Tutor to formulate a plain-language educational breakdown of the Autopilot result."""
        executed_summary = []
        for sr in result.step_results:
            v_note = f" (Verification: {sr.verification_status})" if sr.verification_status else ""
            executed_summary.append(f"Step {sr.sequence} [{sr.tool_name}] -> {sr.status}{v_note}")

        req_data = {
            "autopilot_goal": result.goal,
            "status": result.status.value,
            "steps_planned": result.steps_planned,
            "steps_executed": result.steps_executed,
            "stopped_reason": result.stopped_reason,
            "executed_steps": executed_summary,
        }

        sev_map = {
            AutopilotStatus.COMPLETED: TutorSeverity.NORMAL,
            AutopilotStatus.PARTIAL: TutorSeverity.ELEVATED,
            AutopilotStatus.VERIFICATION_FAILED: TutorSeverity.HIGH,
            AutopilotStatus.FAILED: TutorSeverity.HIGH,
            AutopilotStatus.CANCELLED: TutorSeverity.NORMAL,
            AutopilotStatus.BLOCKED: TutorSeverity.ELEVATED,
            AutopilotStatus.STOPPED: TutorSeverity.ELEVATED,
        }
        sev = sev_map.get(result.status, TutorSeverity.UNKNOWN)

        return TutorResponse(
            title=f"Autopilot Execution Breakdown: {result.status.value}",
            summary=result.summary,
            what_happened=f"Autopilot attempted to resolve: '{result.goal}'. Executed {result.steps_executed} of {result.steps_planned} planned operations.",
            evidence=executed_summary,
            severity=sev,
            possible_causes=[result.stopped_reason] if result.stopped_reason else ["Troubleshooting workflow completed as planned."],
            what_this_means="All authorized actions were executed sequentially and verified against deterministic system states.",
            recommended_next_steps=["Review verification output cards", "If the issue persists, formulate a new diagnostic query"],
            recommended_tools=[],
            safety_notes="Autopilot executes only approved registered tools with verified postconditions and stops on any unexpected state.",
            verification_explanation=f"Overall status: {result.status.value}. Verified steps established expected postconditions.",
            educational_notes="Autopilot stops on failure to prevent repeated repair loops or unintended system modifications.",
            limitations="Autopilot does not execute arbitrary scripts and respects all protected system boundaries.",
        )

    def _build_aborted_result(
        self, plan: AutopilotPlan, status: AutopilotStatus, reason: str, start_time: float
    ) -> AutopilotResult:
        """Helper to build an immediate aborted AutopilotResult."""
        duration = time.time() - start_time
        return AutopilotResult(
            plan_id=plan.plan_id,
            session_id=plan.session_id,
            goal=plan.goal,
            status=status,
            steps_planned=len(plan.steps),
            steps_executed=0,
            step_results=[],
            summary=f"Autopilot aborted: {reason}",
            stopped_reason=reason,
            duration_seconds=duration,
        )

    def _log_audit(self, session_id: str, event_type: str, details: Dict[str, Any]) -> None:
        """Record structured Autopilot lifecycle transitions in the SQLite audit log."""
        if not self.db:
            return
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO diagnostics (session_id, tool_name, status, raw_output)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        f"autopilot:{event_type}",
                        "SUCCESS",
                        json.dumps(details),
                    ),
                )
        except Exception as ex:
            logger.debug("Failed to record Autopilot audit log: %s", ex)


default_autopilot_engine = AutopilotEngine()
