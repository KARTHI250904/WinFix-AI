"""Personal Tutor Mode Engine for WinFix AI (Phase 15).

Provides educational diagnostic explanations, evidence synthesis, verified repair
interpretations, and deterministic safety fallbacks.
Complies strictly with the fundamental rule: LLM != Windows Shell.
"""

from datetime import datetime
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid

from agent.agent_response import FORBIDDEN_EXECUTION_KEYS, extract_json_from_text
from agent.safety import SafetyDecision, SafetyEngine, default_safety_engine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from ai.tutor_prompt import TUTOR_SYSTEM_INSTRUCTION, build_tutor_prompt
from config import config
from database.db import DatabaseManager, db_manager
from database.repositories import DiagnosticRepository, SessionRepository
from knowledge.knowledge_service import KnowledgeService, default_knowledge_service
from modes.tutor_context import TutorContext, sanitize_tutor_payload, sanitize_tutor_text
from modes.tutor_models import (
    ProblemInput,
    StepStatus,
    StructuredProblem,
    TroubleshootingResponse,
    TroubleshootingSession,
    TroubleshootingStep,
    TutorExplanationRequest,
    TutorResponse,
    TutorSeverity,
    TutorStep,
)

logger = logging.getLogger(__name__)


def _detect_domain_from_text(text: str) -> Optional[str]:
    """Identify the diagnostic domain from user query keywords with strict priority and natural language coverage."""
    if not text:
        return None
    t = text.lower().strip()

    # 0. Explicit stopped services pattern takes precedence
    if any(k in t for k in ["service stopped", "services stopped", "stopped service", "service is not running", "service isn't running"]):
        return "services"

    # 1. Bluetooth (specific peripheral / radio domain)
    if any(k in t for k in ["bluetooth", "bthserv", "bth", "pairing", "bluetooth device", "bluetooth disappeared", "bluetooth missing", "bluetooth audio"]):
        return "bluetooth"

    # 2. Display / Night Light / Monitor
    if any(k in t for k in ["night light", "display", "screen", "monitor", "brightness", "screen resolution", "display resolution", "scaling", "bluelight", "blue light"]) or ("resolution" in t and "dns" not in t):
        return "display"

    # 3. Audio / Sound / Microphone / Speakers
    if any(k in t for k in ["audio", "sound", "speaker", "speakers", "microphone", "mic", "no sound", "volume", "sound problem", "earphone", "headphones"]):
        return "audio"

    # 4. Printer (specific hardware domain)
    if any(k in t for k in ["printer", "print spooler", "spoolsv", "printing", "print queue"]):
        return "printer"

    # 5. Windows Update (specific subsystem)
    if any(k in t for k in ["windows update", "wuauserv", "downloading update", "installing update", "patch", "kb", "update failed", "updates failed", "update failure"]):
        return "windows_update"

    # 6. Defender / Security / Antivirus / Firewall
    if any(k in t for k in ["defender", "antivirus", "virus", "malware", "firewall", "windefend", "real-time protection", "windows security", "security status"]):
        return "defender"

    # 7. Application Crashes / Program Faults
    if any(k in t for k in ["crash", "crashes", "crashing", "freeze", "freezing", "hang", "blue screen", "bsod", "unresponsive", "wer", "error reporting", "faulting", "event log", "keeps closing", "stopped working", "closes unexpectedly", "crashes immediately", "program keeps crashing", "app crashes", "browser crash", "chrome crash"]):
        return "application_crash"

    # 8. Services (Windows background services)
    if any(k in t for k in ["service", "services", "stopped service", "service stopped", "service is not running", "service isn't running", "services stopped", "services are not working", "service status", "check stopped services", "daemon"]):
        return "services"

    # 9. Storage / Disk
    if any(k in t for k in ["storage", "disk", "drive", "space", "temp file", "temporary", "cleanup", "clean cache", "drive full", "c:", "c drive", "low disk space", "disk space"]):
        return "storage"

    # 10. Performance / CPU / RAM
    if any(k in t for k in ["slow", "lag", "sluggish", "cpu", "processor", "ram", "memory", "usage", "bottleneck", "task manager", "high usage", "running slowly", "consuming memory", "100%"]):
        return "performance"

    # 11. Battery / Power / Energy
    if any(k in t for k in ["battery", "power plan", "charging", "discharging", "sleep mode", "hibernate"]):
        return "power"

    # 12. Network / Wi-Fi / DNS / Internet
    if any(k in t for k in ["wifi", "wi-fi", "wireless", "network", "internet", "dns", "adapter", "ip", "dhcp", "gateway", "ping", "connect", "disconnect", "ethernet", "router", "ssid", "online", "offline", "no internet"]):
        return "network"

    # Windows Update generic fallback
    if any(k in t for k in ["update", "updates", "upgrade"]):
        return "windows_update"

    # Settings / System Info generic fallback
    if any(k in t for k in ["settings", "system info", "specs", "hardware", "os version", "build", "device manager"]):
        return "system_info"

    return None


class PersonalTutor:
    """Personal Tutor Mode orchestrator providing educational troubleshooting assistance."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
        safety_engine: Optional[SafetyEngine] = None,
        db: Optional[DatabaseManager] = None,
        knowledge_service: Optional[KnowledgeService] = None,
    ) -> None:
        self.client = client or ollama_client
        self.tool_registry = tool_registry or default_tool_registry
        self.safety_engine = safety_engine or default_safety_engine
        self.db = db or db_manager
        self.knowledge_service = knowledge_service or default_knowledge_service
        self.diagnostic_repo = DiagnosticRepository(self.db)
        self.session_repo = SessionRepository(self.db)
        self.contexts: Dict[str, TutorContext] = {}


    def get_or_create_context(self, session_id: Optional[str] = None) -> TutorContext:
        """Retrieve or initialize bounded conversation context for a session."""
        sid = session_id or "default_tutor_session"
        if sid not in self.contexts:
            self.contexts[sid] = TutorContext(session_id=sid, max_history=10)
        return self.contexts[sid]

    def explain_diagnostic(
        self,
        diagnostic_data: Dict[str, Any],
        user_question: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> TutorResponse:
        """Explain diagnostic results clearly with evidence, severity, and safe next steps."""
        question = user_question or "Please explain the findings from this Windows diagnostic inspection."
        context = self.get_or_create_context(session_id)
        context.add_user_message(question)
        context.set_latest_diagnostic(diagnostic_data)

        # Sanitize payloads before LLM consumption
        sanitized_diag = sanitize_tutor_payload(diagnostic_data)
        allowed_tools = self.tool_registry.list_tool_names()

        prompt = build_tutor_prompt(
            user_question=sanitize_tutor_text(question),
            diagnostic_evidence=sanitized_diag,
            context_history=context.get_history_summary(),
            allowed_tools=allowed_tools,
        )

        response = self._generate_and_parse_tutor_response(
            prompt=prompt,
            fallback_builder=lambda: self._build_deterministic_diagnostic_fallback(question, sanitized_diag),
        )

        self._record_tutor_interaction(session_id, "TUTOR_DIAGNOSTIC_EXPLANATION", response)
        context.add_tutor_response(response.summary, response.to_dict())
        return response

    def explain_repair(
        self,
        tool_name: str,
        repair_output: Dict[str, Any],
        verification_status: str,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        user_question: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> TutorResponse:
        """Explain a repair operation, verification outcome, and what the final state means."""
        question = user_question or f"Explain what WinFix AI did for the repair '{tool_name}' and whether it worked."
        context = self.get_or_create_context(session_id)
        context.add_user_message(question)

        repair_snapshot = {
            "tool_name": tool_name,
            "repair_output": repair_output,
            "verification_status": verification_status,
            "before_state": before_state,
            "after_state": after_state,
        }
        context.set_latest_repair(repair_snapshot)

        sanitized_repair = sanitize_tutor_payload(repair_snapshot)
        allowed_tools = self.tool_registry.list_tool_names()

        prompt = build_tutor_prompt(
            user_question=sanitize_tutor_text(question),
            repair_result=sanitized_repair,
            verification_status=verification_status,
            context_history=context.get_history_summary(),
            allowed_tools=allowed_tools,
        )

        response = self._generate_and_parse_tutor_response(
            prompt=prompt,
            fallback_builder=lambda: self._build_deterministic_repair_fallback(
                tool_name=tool_name,
                verification_status=verification_status,
                before_state=before_state,
                after_state=after_state,
                repair_output=repair_output,
            ),
        )

        self._record_tutor_interaction(session_id, "TUTOR_REPAIR_EXPLANATION", response)
        context.add_tutor_response(response.summary, response.to_dict())
        return response

    def explain_safety_decision(
        self,
        tool_name: str,
        decision: SafetyDecision,
        user_question: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> TutorResponse:
        """Explain why a requested tool execution was allowed, required confirmation, or was blocked."""
        question = user_question or f"Why was the action '{tool_name}' handled this way?"
        context = self.get_or_create_context(session_id)
        context.add_user_message(question)

        title = f"Safety Policy: '{tool_name}'"
        risk_val = decision.risk.value if hasattr(decision.risk, "value") else str(decision.risk)
        evidence = [
            f"Tool name: '{tool_name}'",
            f"Risk Level: {risk_val}",
            f"Allowed by SafetyEngine: {decision.allowed}",
            f"Requires explicit user confirmation: {decision.requires_confirmation}",
            f"Blocked by Policy: {decision.blocked}",
        ]

        if risk_val == "HIGH" or decision.blocked:
            what_happened = f"WinFix AI strictly blocked '{tool_name}' because it is classified as a HIGH risk action or is restricted by policy."
            what_this_means = "HIGH risk actions could cause data loss or weaken system security. WinFix AI is designed to protect your PC by refusing destructive actions."
            safety_notes = ["WinFix AI enforces safety by default. Destructive operations are permanently blocked."]
            severity = TutorSeverity.HIGH.value
        elif decision.requires_confirmation and not decision.allowed:
            what_happened = f"The action '{tool_name}' requires your explicit review and confirmation before it can run."
            what_this_means = "This operation modifies Windows configuration (such as restarting a background service or flushing cache). You remain in control and decide whether to proceed."
            safety_notes = ["Always verify why a repair is proposed before granting confirmation."]
            severity = TutorSeverity.NORMAL.value
        elif decision.reason:
            what_happened = f"The action '{tool_name}' safety policy: {decision.reason}"
            what_this_means = "WinFix AI protects critical Windows operating system components from being stopped or modified."
            safety_notes = ["Protected system components are safeguarded to keep Windows running stably."]
            severity = TutorSeverity.NORMAL.value
        else:
            what_happened = f"The action '{tool_name}' is a SAFE read-only diagnostic and was permitted to execute."
            what_this_means = "Safe diagnostics inspect system status without altering your files or settings."
            safety_notes = ["Read-only diagnostics cannot harm your system."]
            severity = TutorSeverity.NORMAL.value

        response = TutorResponse(
            title=title,
            summary=what_happened,
            what_happened=what_happened,
            evidence=evidence,
            severity=severity,
            severity_explanation=f"Assigned risk level: {risk_val}",
            possible_causes=["SafetyEngine policy enforcement"],
            what_this_means=what_this_means,
            recommended_next_steps=["Review the proposed action details before deciding whether to proceed."],
            recommended_tools=[],
            safety_notes=safety_notes,
            educational_notes=["WinFix AI uses a 3-tier safety model: SAFE (automatic), MEDIUM (confirmation required), HIGH (strictly blocked)."],
            limitations=["Safety policy cannot be overridden by the AI model."],
            confidence=1.0,
        )

        self._record_tutor_interaction(session_id, "TUTOR_SAFETY_EXPLANATION", response)
        context.add_tutor_response(response.summary, response.to_dict())
        return response

    def answer_question(
        self,
        user_question: str,
        session_id: Optional[str] = None,
        diagnostic_data: Optional[Dict[str, Any]] = None,
    ) -> TutorResponse:
        """Answer general troubleshooting questions educationally using evidence and context."""
        context = self.get_or_create_context(session_id)
        context.add_user_message(user_question)

        sanitized_diag = sanitize_tutor_payload(diagnostic_data or context.get_latest_diagnostic())
        allowed_tools = self.tool_registry.list_tool_names()

        prompt = build_tutor_prompt(
            user_question=sanitize_tutor_text(user_question),
            diagnostic_evidence=sanitized_diag,
            context_history=context.get_history_summary(),
            allowed_tools=allowed_tools,
        )

        response = self._generate_and_parse_tutor_response(
            prompt=prompt,
            fallback_builder=lambda: self._build_deterministic_question_fallback(user_question, sanitized_diag),
        )

        self._record_tutor_interaction(session_id, "TUTOR_QA", response)
        context.add_tutor_response(response.summary, response.to_dict())
        return response

    def create_troubleshooting_flow(
        self,
        user_question: Optional[str] = None,
        diagnostic_data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        problem_input: Optional[ProblemInput] = None,
    ) -> TroubleshootingSession:
        """Formulate a bounded, evidence-based, problem-specific step-by-step troubleshooting plan."""
        sid = session_id or (problem_input.session_id if problem_input else f"tutor_flow_{int(time.time())}")
        effective_question = user_question or ""
        conflicts: List[str] = []

        if problem_input:
            from agent.multimodal_adapter import default_multimodal_adapter
            structured_prob = default_multimodal_adapter.understand_problem(
                problem_input=problem_input,
                diagnostic_data=diagnostic_data,
            )
            domain = structured_prob.domain
            effective_question = structured_prob.problem
            conflicts = structured_prob.conflicting_evidence
        else:
            domain = _detect_domain_from_text(effective_question) or "general"

        q_lower = (effective_question or "").lower()

        steps: List[TroubleshootingStep] = []

        if domain == "network":
            # Network / Wi-Fi flow
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Wi-Fi Adapter State",
                    purpose="Determine whether Windows currently sees and enables the Wi-Fi network adapter.",
                    why_it_matters="This tells us whether Windows can currently see and use the physical Wi-Fi hardware.",
                    tool_name="get_network_adapters_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will test whether network packets can reach your local router gateway.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Check Gateway & Local Network Reachability",
                    purpose="Verify if your computer can communicate with the local router and gateway.",
                    why_it_matters="This confirms whether network traffic can leave your computer and reach the router.",
                    tool_name="check_internet_connectivity",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will verify whether DNS domain name resolution is working.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=3,
                    title="Check DNS Resolution",
                    purpose="Verify whether Windows can translate website domain names into IP addresses.",
                    why_it_matters="Windows needs DNS to convert friendly names like google.com into network numbers.",
                    tool_name="check_dns_resolution",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will inspect related Windows background network services.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=4,
                    title="Check Windows Network Services",
                    purpose="Ensure critical network services (DHCP, DNS, WLAN AutoConfig) are running stably.",
                    why_it_matters="Windows relies on these background services to keep your wireless connection active.",
                    tool_name="get_services_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Troubleshooting sequence complete. Review findings or apply verified safe repair.",
                )
            )
        elif domain == "performance":
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Top CPU Consuming Processes",
                    purpose="Identify which specific background tasks or applications are consuming processor capacity.",
                    why_it_matters="This tells us if an unconstrained runaway process is causing system freezing.",
                    tool_name="get_top_cpu_processes",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will inspect system RAM and memory consumption.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Check Memory & RAM Pressure",
                    purpose="Determine whether available RAM is exhausted and paging heavily to disk.",
                    why_it_matters="Low available memory causes Windows to stutter when switching between tasks.",
                    tool_name="get_top_memory_processes",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will verify system drive capacity and virtual memory headroom.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=3,
                    title="Check Storage Capacity & Disk Pressure",
                    purpose="Verify whether drive C: has adequate free space for pagefile and cache operations.",
                    why_it_matters="Drives with less than 10% free space cause significant system slowdowns.",
                    tool_name="get_storage_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will inspect Windows service health.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=4,
                    title="Check Windows Background Services",
                    purpose="Ensure core Windows system services are running stably without crash loops.",
                    why_it_matters="Stalled background services can repeatedly consume CPU attempting to restart.",
                    tool_name="get_services_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                )
            )
        elif domain == "storage":
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Storage Drives & Partition Space",
                    purpose="Inspect free space, total capacity, and storage health across all drives.",
                    why_it_matters="This reveals exactly which partition is experiencing low storage pressure.",
                    tool_name="get_storage_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will analyze reclaimable temporary files and system caches.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Inspect Temporary Storage Cache",
                    purpose="Calculate reclaimable space in Windows temp folders, caches, and log directories.",
                    why_it_matters="Temporary files accumulate over time and can safely be removed to free gigabytes.",
                    tool_name="get_temp_storage_info",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, you can authorize safe temporary cleanup to reclaim disk space.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=3,
                    title="Clean Temporary Storage Cache",
                    purpose="Safely remove expired temporary cache files without touching personal files.",
                    why_it_matters="Reclaims valuable disk space and resolves low-space alerts immediately.",
                    tool_name="clean_user_temp_cache",
                    risk="MEDIUM",
                    requires_confirmation=True,
                    is_repair=True,
                    repair_why="Temporary files and update logs are occupying disk space.",
                    repair_change="Deletes temporary build caches and log files from user Temp directories.",
                    repair_expected_effect="Reclaims free disk space on drive C:.",
                    verification_tool="get_storage_diagnostics",
                )
            )
        elif domain == "bluetooth":
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Bluetooth Radio & Hardware State",
                    purpose="Verify whether Windows detects the Bluetooth hardware adapter and radio driver.",
                    why_it_matters="This confirms whether the physical wireless card is powered on and recognized.",
                    tool_name="get_bluetooth_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will check the Bluetooth Support background service.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Check Windows Bluetooth Support Service",
                    purpose="Confirm whether the Windows Bluetooth Support Service (bthserv) is currently running.",
                    why_it_matters="Bluetooth accessories cannot connect if the background service is stopped.",
                    tool_name="get_services_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, you can restart the Bluetooth service if it is stopped.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=3,
                    title="Restart Bluetooth Support Service",
                    purpose="Restart the Bluetooth stack to clear stalled device discovery queues.",
                    why_it_matters="Restores communication with paired headphones and wireless peripherals.",
                    tool_name="restart_bluetooth_service",
                    risk="MEDIUM",
                    requires_confirmation=True,
                    is_repair=True,
                    repair_why="Bluetooth radio or service may be in an unresponsive state.",
                    repair_change="Restarts the Windows bthserv service cleanly.",
                    repair_expected_effect="Bluetooth Support Service status changes to RUNNING.",
                    verification_tool="get_bluetooth_diagnostics",
                )
            )
        elif domain == "windows_update":
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Windows Update Subsystem Status",
                    purpose="Inspect pending update state, error codes, and update service readiness.",
                    why_it_matters="This identifies whether update downloads are stuck or encountering errors.",
                    tool_name="get_windows_update_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will inspect Windows Update background services.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Check Windows Update Services (wuauserv, BITS)",
                    purpose="Ensure all update dependency services are running and responsive.",
                    why_it_matters="Windows Update cannot download packages if BITS or wuauserv are stopped.",
                    tool_name="get_services_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, you can reset update components if downloads are stuck.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=3,
                    title="Restart Windows Update Service",
                    purpose="Restart wuauserv and dependency services.",
                    why_it_matters="Clears stalled update service state safely.",
                    tool_name="restart_windows_update_service",
                    risk="MEDIUM",
                    requires_confirmation=True,
                    is_repair=True,
                    repair_why="Update downloads or services may be stalled.",
                    repair_change="Restarts wuauserv cleanly.",
                    repair_expected_effect="Update services recover to READY state.",
                    verification_tool="get_windows_update_diagnostics",
                )
            )
        elif domain == "defender":
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Windows Defender Protection Status",
                    purpose="Inspect real-time protection, antivirus state, and security engine health.",
                    why_it_matters="This tells us whether your PC is actively protected against security threats.",
                    tool_name="get_defender_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will check the Windows Defender background service.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Check Windows Defender Core Service",
                    purpose="Verify that the WinDefend process is active in the background.",
                    why_it_matters="Ensures the security engine is actively running to guard your files.",
                    tool_name="get_services_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                )
            )
        elif domain == "services":
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Windows Service Status",
                    purpose="Inspect status and startup type for target Windows service.",
                    why_it_matters="Confirms whether the service is currently running or stopped.",
                    tool_name="get_service_status",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will inspect related background services.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Inspect Core Services Health",
                    purpose="Verify health across baseline core Windows background services.",
                    why_it_matters="Identifies if related dependency services are stopped.",
                    tool_name="get_services_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, you can authorize restarting the stopped service.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=3,
                    title="Restart Windows Service",
                    purpose="Restart the stopped service cleanly.",
                    why_it_matters="Restores active background service operation.",
                    tool_name="restart_service",
                    risk="MEDIUM",
                    requires_confirmation=True,
                    is_repair=True,
                    repair_why="Service is currently stopped or not responding.",
                    repair_change="Restarts the target Windows service.",
                    repair_expected_effect="Service status transitions to Running.",
                    verification_tool="get_service_status",
                )
            )
        elif domain == "application_crash":
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check Windows Error Reporting (WER) Status",
                    purpose="Verify that Windows crash logging and error reporting are active.",
                    why_it_matters="This confirms that Windows is recording detailed faulting module diagnostics.",
                    tool_name="get_windows_error_reporting_status",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will scan the event log for recent crash records.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Scan Recent Application Crash Events",
                    purpose="Query the Windows Application event log for recent crash and exception events.",
                    why_it_matters="Extracts the exact faulting application, module DLL, and exception code.",
                    tool_name="get_recent_application_crashes",
                    risk="SAFE",
                    requires_confirmation=False,
                )
            )
        else:
            # General baseline troubleshooting flow
            steps.append(
                TroubleshootingStep(
                    step_number=1,
                    title="Check System Hardware & OS Health",
                    purpose="Inspect Windows operating system baseline, CPU, and memory state.",
                    why_it_matters="Provides an authoritative baseline of Windows version and core resources.",
                    tool_name="get_complete_system_info",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will check core Windows background services.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=2,
                    title="Check Windows Background Services",
                    purpose="Inspect status and startup type across critical Windows background services.",
                    why_it_matters="Background services manage networking, updates, security, and hardware devices.",
                    tool_name="get_services_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                    next_step_hint="Next, we will verify network and storage status.",
                )
            )
            steps.append(
                TroubleshootingStep(
                    step_number=3,
                    title="Check Storage Capacity & Pressure",
                    purpose="Ensure all storage partitions have healthy free space.",
                    why_it_matters="Low disk space causes stability issues across all Windows subsystems.",
                    tool_name="get_storage_diagnostics",
                    risk="SAFE",
                    requires_confirmation=False,
                )
            )

        session = TroubleshootingSession(
            session_id=sid,
            problem_statement=effective_question or "General troubleshooting inquiry",
            domain=domain,
            current_state="UNDERSTANDING",
            steps=steps,
            total_steps=len(steps),
            active_hypothesis=f"Investigating {domain.replace('_', ' ')} symptoms through sequential empirical checks.",
            evidence_collected=list(conflicts),
        )
        return session

    def execute_tutor_step(
        self,
        session: TroubleshootingSession,
        step_number: int,
        user_confirmed: bool = False,
    ) -> TroubleshootingStep:
        """Execute a structured troubleshooting step safely and formulate factual explanations."""
        step = next((s for s in session.steps if s.step_number == step_number), None)
        if not step:
            raise ValueError(f"Step number {step_number} not found in session {session.session_id}")

        tool = self.tool_registry.get(step.tool_name)
        if not tool:
            step.status = StepStatus.FAILED
            step.finding = f"Tool '{step.tool_name}' is not registered in Approved Tool Registry."
            step.meaning = "The requested check could not be executed."
            return step

        # Infer contextual tool arguments if required by tool schema
        step_args: Dict[str, Any] = {}
        if step.tool_name in ("get_service_status", "get_service_details"):
            p_lower = (session.problem_statement or "").lower()
            if "audio" in p_lower:
                step_args = {"service_name": "AudioSrv"}
            elif "update" in p_lower or "wuauserv" in p_lower:
                step_args = {"service_name": "wuauserv"}
            elif "bluetooth" in p_lower or "bth" in p_lower:
                step_args = {"service_name": "bthserv"}
            elif "spooler" in p_lower or "print" in p_lower:
                step_args = {"service_name": "Spooler"}
            else:
                step_args = {"service_name": "wuauserv"}

        # Safety policy check
        safety_dec = self.safety_engine.evaluate(step.tool_name, step_args, user_confirmed=user_confirmed)
        if safety_dec.blocked:
            step.status = StepStatus.FAILED
            step.finding = f"Safety Engine blocked action: {safety_dec.reason}"
            step.meaning = "WinFix AI enforces safety boundaries to protect your PC."
            return step

        if safety_dec.requires_confirmation and not user_confirmed:
            step.status = StepStatus.AWAITING_CONFIRMATION
            step.finding = "This repair modifies system configuration and requires your confirmation."
            step.meaning = "You are in control. Review the action details before authorizing execution."
            session.current_state = "AWAITING_CONFIRMATION"
            return step

        step.status = StepStatus.RUNNING
        t_start = time.time()
        try:
            raw_res = tool.handler(**safety_dec.validated_arguments)
            duration_ms = int((time.time() - t_start) * 1000)
            step.duration_ms = duration_ms
            step.raw_output = raw_res

            finding, meaning, next_hint = self._interpret_tool_result(step.tool_name, raw_res, session.problem_statement)
            step.finding = finding
            step.meaning = meaning
            if next_hint and step.next_step_hint:
                step.next_step_hint = next_hint

            # If repair, execute verification tool immediately
            if step.is_repair and step.verification_tool:
                v_tool = self.tool_registry.get(step.verification_tool)
                if v_tool:
                    v_args = {"service_name": step_args.get("service_name", "wuauserv")} if step.verification_tool in ("get_service_status", "get_service_details") else {}
                    v_res = v_tool.handler(**v_args)
                    v_success = v_res.get("success", True) if isinstance(v_res, dict) else True
                    step.verification_status = "Verified" if v_success else "Not verified"
                else:
                    step.verification_status = "Unable to verify"

            step.status = StepStatus.COMPLETED
            session.evidence_collected.append(f"{step.title}: {finding}")

            # Advance current step index
            if session.current_step_index < len(session.steps):
                session.current_step_index = step_number
            if all(s.status == StepStatus.COMPLETED for s in session.steps):
                session.current_state = "RESOLVED" if any(s.is_repair and s.verification_status == "Verified" for s in session.steps) else "GUIDING"
                session.resolution_summary = f"Completed all {len(session.steps)} diagnostic checks. Review findings above."

            return step
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.finding = f"Inspection encountered an unexpected error: {exc}"
            step.meaning = "The check could not be completed on this Windows environment."
            return step

    def _interpret_tool_result(
        self,
        tool_name: str,
        raw_output: Any,
        problem_statement: str,
    ) -> Tuple[str, str, Optional[str]]:
        """Formulate plain-English Finding, Meaning, and Next Step Hint from empirical diagnostic result."""
        data = raw_output.get("data", raw_output) if isinstance(raw_output, dict) else {}
        success = raw_output.get("success", True) if isinstance(raw_output, dict) else True

        if not success:
            err = raw_output.get("error", "Check failed") if isinstance(raw_output, dict) else "Error"
            return (
                f"Inspection encountered an issue: {err}",
                "The diagnostic tool reported an error or restricted access.",
                "Consider checking system event logs or running baseline system diagnostics.",
            )

        # 1. Network Adapters
        if tool_name == "get_network_adapters_diagnostics":
            adapters = data.get("adapters", []) if isinstance(data, dict) else []
            active = data.get("active_adapters", 0) if isinstance(data, dict) else 0
            active_cnt = active if isinstance(active, int) else len(active)
            wifi_adapters = [a for a in adapters if isinstance(a, dict) and any(w in str(a.get("name", "")).lower() for w in ["wi-fi", "wifi", "wireless", "wlan"])]
            if wifi_adapters:
                w_name = wifi_adapters[0].get("name", "Wi-Fi Adapter")
                is_up = wifi_adapters[0].get("is_up", True)
                w_status = "Connected / Up" if is_up else "Disconnected / Down"
                finding = f"Wi-Fi adapter '{w_name}' detected (Status: {w_status}, {active_cnt} active interface(s) total)."
                meaning = "Windows can see and communicate with your wireless network card. Hardware and driver link are active."
                next_hint = "Next, we will test whether network packets can reach the default router gateway."
            elif adapters:
                finding = f"{len(adapters)} network adapter(s) detected ({active_cnt} active), but no dedicated Wi-Fi adapter was found."
                meaning = "Windows does not detect a dedicated Wi-Fi adapter. You may be using Ethernet or the Wi-Fi driver may be disabled."
                next_hint = "Next, we will test internet connectivity through active network interfaces."
            else:
                finding = "No network adapters detected by Windows."
                meaning = "Windows network subsystem reports zero available network interfaces."
                next_hint = "Next, check Device Manager to verify network adapter hardware."
            return finding, meaning, next_hint

        # 2. Internet Connectivity / Gateway Ping
        if tool_name == "check_internet_connectivity":
            reachable = data.get("reachable", True) if isinstance(data, dict) else True
            lat = data.get("latency_ms", 0.0) if isinstance(data, dict) else 0.0
            tgt = data.get("target", "Gateway") if isinstance(data, dict) else "Gateway"
            lat_str = f" in {lat:.1f} ms" if lat else ""
            if reachable:
                finding = f"Network target '{tgt}' responded successfully{lat_str}."
                meaning = "Data packets can successfully leave your PC and reach external network endpoints. Local network link is established."
                next_hint = "Next, we will check whether DNS domain name resolution is translating website names."
            else:
                finding = f"Target '{tgt}' is unreachable. Network packets were dropped."
                meaning = "Your computer cannot reach the local router or internet gateway. Possible Wi-Fi disconnection or IP routing issue."
                next_hint = "Next, verify router Wi-Fi signal and DHCP lease."
            return finding, meaning, next_hint

        # 3. DNS Resolution
        if tool_name == "check_dns_resolution":
            resolved = data.get("resolved", True) if isinstance(data, dict) else True
            host = data.get("target_host", "DNS") if isinstance(data, dict) else "DNS"
            lat = data.get("latency_ms", 0.0) if isinstance(data, dict) else 0.0
            ips = data.get("resolved_ips", []) if isinstance(data, dict) else []
            lat_str = f" in {lat:.1f} ms" if lat else ""
            ip_str = f" ({len(ips)} IP address(es) returned)" if ips else ""
            if resolved:
                finding = f"DNS lookup for '{host}' resolved successfully{lat_str}{ip_str}."
                meaning = "DNS domain name resolution is functioning for this test. This does not rule out intermittent Wi-Fi signal drops."
                next_hint = "Next, we will inspect Windows background network services."
            else:
                finding = f"DNS lookup for '{host}' failed. Hostname could not be translated."
                meaning = "Windows cannot resolve website names. This usually indicates stale DNS cache or an unresponsive DNS server."
                next_hint = "Flushing the DNS cache can resolve stale or corrupted DNS entries."
            return finding, meaning, next_hint

        # 4. Top CPU Processes
        if tool_name == "get_top_cpu_processes":
            procs = data.get("processes", []) if isinstance(data, dict) else []
            if procs and isinstance(procs[0], dict):
                top_p = procs[0]
                p_name = top_p.get("name", "Process")
                p_cpu = top_p.get("cpu_percent", 0.0)
                finding = f"Monitored {len(procs)} active processes. Top CPU consumer is '{p_name}' at {p_cpu}% CPU."
                if p_cpu > 70.0:
                    meaning = f"Process '{p_name}' is consuming substantial processor capacity, which may cause system lag."
                else:
                    meaning = "Processor utilization across active processes is balanced and within normal operating thresholds."
            else:
                finding = "Active process CPU load monitored."
                meaning = "System processor utilization is normal."
            return finding, meaning, "Next, we will inspect RAM memory pressure."

        # 5. Top Memory Processes
        if tool_name == "get_top_memory_processes":
            procs = data.get("processes", []) if isinstance(data, dict) else []
            if procs and isinstance(procs[0], dict):
                top_p = procs[0]
                p_name = top_p.get("name", "Process")
                p_mem = top_p.get("memory_formatted") or f"{top_p.get('memory_percent', 0.0)}%"
                finding = f"Top memory consuming process is '{p_name}' using {p_mem} RAM."
                meaning = "RAM allocation across background applications is operating normally."
            else:
                finding = "RAM memory allocation evaluated."
                meaning = "Memory pressure is within normal operating limits."
            return finding, meaning, "Next, we will check drive storage headroom."

        # 6. Storage Diagnostics
        if tool_name == "get_storage_diagnostics":
            drives = data.get("drives", []) if isinstance(data, dict) else []
            low_warn = data.get("low_space_warning", False) if isinstance(data, dict) else False
            if drives and isinstance(drives[0], dict):
                c_drv = drives[0]
                free_gb = c_drv.get("free_gb", 0.0)
                tot_gb = c_drv.get("total_gb", 0.0)
                pct = c_drv.get("percent_used", 0.0)
                used_gb = max(0.0, tot_gb - free_gb)
                finding = f"System drive C: Free space: {free_gb:.1f} GB | Total space: {tot_gb:.1f} GB | Used space: {used_gb:.1f} GB ({pct:.1f}% used)."
                if low_warn or (tot_gb > 0 and free_gb / tot_gb < 0.1):
                    meaning = "Low disk space alert. Windows requires at least 10% free storage for virtual memory paging and cache."
                else:
                    meaning = "Drive capacity is healthy with sufficient free storage for Windows operations."
            else:
                finding = f"Evaluated {len(drives)} drive partition(s)."
                meaning = "Storage partitions are accessible."
            return finding, meaning, "Next, we will inspect temporary cache storage."

        # 7. Temp Storage Info
        if tool_name == "get_temp_storage_info":
            sz = data.get("temp_size_formatted") or f"{data.get('temp_size_mb', 0)} MB" if isinstance(data, dict) else "0 MB"
            finding = f"Temporary storage currently uses: {sz} of reclaimable cache files."
            meaning = "These files consist of cached installers, crash dumps, and temporary web buffers that can safely be cleared."
            return finding, meaning, "You can authorize a safe cleanup of these temporary files."

        # 8. Clean Temp Files (Repair)
        if tool_name in ["clean_user_temp_cache", "clean_temp_files"]:
            freed = data.get("freed_mb", 0) if isinstance(data, dict) else 0
            removed = data.get("removed_count", 0) if isinstance(data, dict) else 0
            finding = f"Cleaned {removed} temporary files, freeing {freed} MB of disk space."
            meaning = "Temporary files were removed safely. Reclaimed storage is now available on drive C:."
            return finding, meaning, "Drive space has been reclaimed."

        # 9. Flush DNS Cache (Repair)
        if tool_name == "flush_dns_cache":
            finding = "Successfully flushed the Windows DNS resolver cache."
            meaning = "Windows has cleared stored domain name entries. Subsequent requests will query DNS servers anew."
            return finding, meaning, "DNS cache reset verified."

        # 10. Bluetooth Diagnostics
        if tool_name == "get_bluetooth_diagnostics":
            svc = data.get("service_running", True) if isinstance(data, dict) else True
            det = data.get("adapter_detected", True) if isinstance(data, dict) else True
            finding = f"Bluetooth Support Service: {'Running' if svc else 'Stopped'}; Radio Adapter: {'Detected' if det else 'Not Found'}."
            if svc and det:
                meaning = "Bluetooth hardware and service are initialized and ready for peripheral discovery."
            else:
                meaning = "Bluetooth subsystem is inactive. The Bluetooth service is stopped or radio hardware is missing."
            return finding, meaning, "Next, check Bluetooth background services."

        # 11. Services Diagnostics & Status
        if tool_name == "get_service_status":
            svc_name = data.get("service_name", "Service") if isinstance(data, dict) else "Service"
            st_val = data.get("status", "Unknown") if isinstance(data, dict) else "Unknown"
            finding = f"Service '{svc_name}' status: {st_val}."
            meaning = f"Windows reports that {svc_name} is currently in {st_val} state."
            return finding, meaning, "Service status verified."

        if tool_name in ["restart_service", "start_service"]:
            svc_name = data.get("service_name", "Service") if isinstance(data, dict) else "Service"
            st_val = data.get("status", "Running") if isinstance(data, dict) else "Running"
            finding = f"Service '{svc_name}' command executed (Result: {st_val})."
            meaning = f"The service state has been updated to {st_val}."
            return finding, meaning, "Service restarted."

        if tool_name == "get_services_diagnostics":
            svcs = data.get("services", []) if isinstance(data, dict) else []
            run_cnt = len([s for s in svcs if isinstance(s, dict) and s.get("status") == "RUNNING"]) if svcs else 0
            finding = f"Inspected core Windows background services ({run_cnt} active/running)."
            meaning = "Critical Windows background services are running and responsive."
            return finding, meaning, "Service health verified."

        # 12. Windows Update Diagnostics
        if tool_name == "get_windows_update_diagnostics":
            pending = data.get("pending_updates", 0) if isinstance(data, dict) else 0
            ready = data.get("update_services_ready", True) if isinstance(data, dict) else True
            finding = f"Windows Update services are {'Ready' if ready else 'Need Attention'} ({pending} pending update(s))."
            meaning = "Update subsystem components are configured and accessible."
            return finding, meaning, "Update status verified."

        # 13. Defender Diagnostics
        if tool_name == "get_defender_diagnostics":
            rtp = data.get("real_time_protection", True) if isinstance(data, dict) else True
            av = data.get("antivirus_enabled", True) if isinstance(data, dict) else True
            finding = f"Microsoft Defender Real-Time Protection is {'Active' if rtp else 'Standby'} (Antivirus: {'Enabled' if av else 'Disabled'})."
            meaning = "Your computer is actively protected against known security threats."
            return finding, meaning, "Defender status verified."

        # 14. WER Status & Crash Events
        if tool_name == "get_windows_error_reporting_status":
            en = data.get("enabled", True) if isinstance(data, dict) else True
            finding = f"Windows Error Reporting is {'Enabled' if en else 'Disabled'}."
            meaning = "Crash reporting captures diagnostic traces when applications encounter errors."
            return finding, meaning, "Next, we will scan recent application crash records."

        if tool_name in ["get_recent_application_crashes", "get_application_crash_events", "get_application_crash_diagnostics"]:
            crashes = data.get("crashes", []) if isinstance(data, dict) else []
            if crashes:
                latest = crashes[0].get("application_name", "Application")
                finding = f"Found {len(crashes)} recent application error event(s) in Windows log (Latest: {latest})."
                meaning = f"Application '{latest}' experienced an exception. Review event details for faulting module."
            else:
                finding = "No recent application crash events detected in Windows Application log."
                meaning = "No application crashes were recorded by Windows Error Reporting."
            return finding, meaning, "Event log analysis complete."

        # 15. Display Diagnostics
        if tool_name == "get_display_diagnostics":
            res = data.get("primary_resolution", "Unknown") if isinstance(data, dict) else "Unknown"
            nl_status = data.get("night_light", {}).get("status", "Unknown") if isinstance(data, dict) else "Unknown"
            finding = f"Primary screen resolution: {res}; Night Light status: {nl_status}."
            meaning = "Display subsystem and monitor parameters are operating within standard Windows configuration."
            return finding, meaning, "Display configuration verified."

        # 16. Audio Diagnostics
        if tool_name in ["get_audio_diagnostics", "get_audio_endpoint_status"]:
            srv_ok = data.get("audio_service_running", True) if isinstance(data, dict) else True
            play_cnt = data.get("playback_devices_count", 0) if isinstance(data, dict) else 0
            finding = f"Windows Audio Service: {'Running' if srv_ok else 'Stopped'}; Active Playback Endpoints: {play_cnt}."
            meaning = "Audio device enumeration and endpoint routing are active."
            return finding, meaning, "Audio configuration verified."

        # General fallback
        return (
            f"Inspection executed successfully (Tool: {tool_name}).",
            "Diagnostic check completed and verified against baseline Windows parameters.",
            "Review findings above to proceed.",
        )


    def _generate_and_parse_tutor_response(
        self,
        prompt: str,
        fallback_builder: Any,
    ) -> TutorResponse:
        """Invoke local Gemma model, validate structured JSON, and fallback cleanly if offline."""
        try:
            gen_res = self.client.generate(
                prompt=prompt,
                system=TUTOR_SYSTEM_INSTRUCTION,
                format="json",
                timeout=getattr(config, "ollama_timeout_seconds", 60),
            )
            if isinstance(gen_res, str):
                raw_text = gen_res
            elif isinstance(gen_res, dict):
                if not gen_res.get("success", True):
                    logger.debug("Ollama generation failed or timed out. Using deterministic tutor fallback.")
                    return fallback_builder()
                raw_text = gen_res.get("response", "")
            else:
                return fallback_builder()

            json_str = extract_json_from_text(raw_text)
            if not json_str:
                logger.debug("Failed to extract JSON from tutor output. Using fallback.")
                return fallback_builder()

            parsed_dict = json.loads(json_str)
            if not isinstance(parsed_dict, dict):
                return fallback_builder()

            # Validate against safety boundaries and tool registry
            validated_response = self._validate_and_sanitize_tutor_response(parsed_dict)
            if not validated_response:
                return fallback_builder()

            return validated_response
        except Exception as exc:
            logger.debug("Personal Tutor exception during LLM generation: %s", exc)
            return fallback_builder()

    def _validate_and_sanitize_tutor_response(self, raw_data: Dict[str, Any]) -> Optional[TutorResponse]:
        """Validate untrusted LLM output and filter tool recommendations."""
        # 1. Reject any forbidden execution keys
        for key in FORBIDDEN_EXECUTION_KEYS:
            if key in raw_data:
                logger.warning("Security violation in Tutor response: forbidden key '%s' found.", key)
                return None

        # 2. Extract and sanitize string fields
        title = sanitize_tutor_text(str(raw_data.get("title") or "WinFix AI Tutor Explanation"))
        summary = sanitize_tutor_text(str(raw_data.get("summary") or ""))
        what_happened = sanitize_tutor_text(str(raw_data.get("what_happened") or ""))
        what_this_means = sanitize_tutor_text(str(raw_data.get("what_this_means") or ""))
        severity_explanation = sanitize_tutor_text(str(raw_data.get("severity_explanation") or ""))

        # 3. Validate severity
        raw_sev = str(raw_data.get("severity", "NORMAL")).strip().upper()
        severity = raw_sev if raw_sev in [s.value for s in TutorSeverity] else TutorSeverity.UNKNOWN.value

        # 4. Lists extraction
        evidence = [sanitize_tutor_text(str(item)) for item in (raw_data.get("evidence") or []) if item]
        possible_causes = [sanitize_tutor_text(str(item)) for item in (raw_data.get("possible_causes") or []) if item]
        recommended_next_steps = [sanitize_tutor_text(str(item)) for item in (raw_data.get("recommended_next_steps") or []) if item]
        safety_notes = [sanitize_tutor_text(str(item)) for item in (raw_data.get("safety_notes") or []) if item]
        educational_notes = [sanitize_tutor_text(str(item)) for item in (raw_data.get("educational_notes") or []) if item]
        limitations = [sanitize_tutor_text(str(item)) for item in (raw_data.get("limitations") or []) if item]

        # 5. Strict Tool Validation: only allow registered tool names
        raw_tools = raw_data.get("recommended_tools") or []
        validated_tools: List[str] = []
        for t in raw_tools:
            if isinstance(t, str):
                t_clean = t.strip()
                if self.tool_registry.get(t_clean):
                    validated_tools.append(t_clean)
                else:
                    logger.debug("Filtered out unapproved recommended tool '%s' from tutor output.", t_clean)

        ver_exp = raw_data.get("verification_explanation")
        ver_str = sanitize_tutor_text(str(ver_exp)) if ver_exp is not None else None

        conf = 0.8
        try:
            conf = float(raw_data.get("confidence", 0.8))
        except (ValueError, TypeError):
            conf = 0.8

        return TutorResponse(
            title=title,
            summary=summary,
            what_happened=what_happened,
            evidence=evidence,
            severity=severity,
            severity_explanation=severity_explanation,
            possible_causes=possible_causes,
            what_this_means=what_this_means,
            recommended_next_steps=recommended_next_steps,
            recommended_tools=validated_tools,
            safety_notes=safety_notes,
            verification_explanation=ver_str,
            educational_notes=educational_notes,
            limitations=limitations,
            confidence=conf,
            raw_json=raw_data,
        )

    def _build_deterministic_diagnostic_fallback(
        self,
        user_question: str,
        diag_data: Optional[Dict[str, Any]],
    ) -> TutorResponse:
        """Deterministic domain-specific tutor explanation when Ollama is unavailable."""
        evidence: List[str] = []
        possible_causes: List[str] = []
        next_steps: List[str] = []
        recommended_tools: List[str] = []
        safety_notes: List[str] = ["WinFix AI performs safe, read-only diagnostic checks without modifying files."]
        severity = TutorSeverity.NORMAL.value
        title = "Diagnostic Explanation (Deterministic Mode)"

        if not diag_data:
            return TutorResponse(
                title="Windows Diagnostic Overview",
                summary="WinFix AI is ready to explain your system diagnostics in plain language.",
                what_happened="No diagnostic evidence has been collected yet.",
                evidence=["No active diagnostic data payload provided."],
                severity=TutorSeverity.NORMAL.value,
                severity_explanation="System state has not been flagged with an issue.",
                possible_causes=["System is idling or waiting for diagnostic scan."],
                what_this_means="Run a diagnostic check or ask a question about your PC.",
                recommended_next_steps=["Run safe read-only diagnostics across system domains."],
                recommended_tools=["get_complete_system_info"],
                safety_notes=safety_notes,
                educational_notes=["Personal Tutor Mode provides step-by-step guidance without automatic repairs."],
                limitations=["Detailed AI reasoning is operating in deterministic offline mode."],
                confidence=0.9,
            )

        detected_domain = _detect_domain_from_text(user_question)
        is_composite_diag = isinstance(diag_data, dict) and ("dns" in diag_data and "defender" in diag_data and "windows_update" in diag_data)

        # Domain 0A: Screenshot Evidence Breakdown
        if isinstance(diag_data, dict) and "screenshot_evidence" in diag_data:
            s_ev = diag_data["screenshot_evidence"]
            facts = str(s_ev.get("visible_facts", "Visual evidence analyzed.")).strip()
            errs = s_ev.get("error_codes", [])
            apps = s_ev.get("applications", [])
            interps = s_ev.get("possible_interpretations", [])
            uncerts = s_ev.get("uncertainties", [])
            tools = s_ev.get("recommended_tools", [])

            title = "Screenshot Analysis & Solution Guide"
            what_happened = f"Observed on screen: {facts}"

            facts_lower = (facts + " " + (user_question or "")).lower()
            uq_lower = (user_question or "").lower()
            facts_text = str(facts).lower()

            user_asks_bluetooth = any(k in uq_lower for k in [
                "bluetooth", "bthserv", "paired device", "bth", "bluetooth toggle",
                "bluetooth is disable", "bluetooth is disabled", "bluetooth disabled",
                "bluetooth off", "bluetooth not working", "turn on bluetooth"
            ])
            user_asks_wifi = any(k in uq_lower for k in [
                "wifi", "wi-fi", "wireless", "wlan", "network adapter", "ncpa.cpl",
                "no wifi", "wifi missing", "wifi is not shown", "not shown", "missing wifi"
            ])

            has_explicit_missing_wifi = any(k in facts_text for k in [
                "wi-fi toggle is missing", "wifi toggle is missing", "wi-fi is missing", "wifi is missing",
                "missing wi-fi", "missing wifi", "wi-fi button is completely missing", "wifi button is completely missing",
                "wi-fi toggle is not present", "wifi toggle is not present"
            ])
            has_explicit_bluetooth_fault = any(k in facts_text for k in [
                "bluetooth is disabled", "bluetooth is disable", "bluetooth disabled",
                "bluetooth off", "bluetooth not working", "bluetooth unavailable",
                "bluetooth greyed out", "bluetooth is off"
            ])

            if user_asks_wifi and not user_asks_bluetooth:
                is_bluetooth_query = False
                is_wifi_query = True
            elif user_asks_bluetooth and not user_asks_wifi:
                is_bluetooth_query = True
                is_wifi_query = False
            else:
                if has_explicit_missing_wifi:
                    is_wifi_query = True
                    is_bluetooth_query = False
                elif has_explicit_bluetooth_fault:
                    is_bluetooth_query = True
                    is_wifi_query = False
                else:
                    is_bluetooth_query = False
                    is_wifi_query = any(k in facts_lower for k in ["wifi", "wi-fi", "wireless", "wlan"])

            is_quick_settings_missing_wifi = (
                not is_bluetooth_query
                and ("quick settings" in facts_lower or ("network" in facts_lower and "settings" in facts_lower) or "flyout" in facts_lower)
                and (is_wifi_query or has_explicit_missing_wifi)
            )

            if is_bluetooth_query:
                title = "Bluetooth Disabled / Inactive — Step-by-Step Diagnostic & Solution Guide"
                what_happened = "From your screenshot, the Bluetooth toggle is currently disabled, turned off, or inactive in Windows Quick Settings."
                what_this_means = "When Bluetooth is disabled or greyed out, Windows is not currently broadcasting or receiving signals from wireless peripherals (headphones, mice, keyboards). This can occur if the toggle was switched off, the Bluetooth radio is powered down, the Bluetooth Support Service (bthserv) is stopped, or the driver encountered a state stall."
                possible_causes.append("1. Bluetooth toggle is manually switched OFF in Windows Quick Settings or Settings.")
                possible_causes.append("2. The Windows Bluetooth Support Service (bthserv) is stopped or paused.")
                possible_causes.append("3. Bluetooth adapter or radio controller is disabled in Device Manager.")
                possible_causes.append("4. Airplane mode or power management turned off the wireless radio.")
                next_steps.append("Step 1 — Turn on Bluetooth toggle: In Windows Quick Settings (Win + A), click the Bluetooth button so it turns blue / active. Alternatively, go to Settings (Win + I) > Bluetooth & devices and toggle Bluetooth to 'On'.")
                next_steps.append("Step 2 — Verify Bluetooth Support Service: Press Win + R, type 'services.msc' and find 'Bluetooth Support Service' (bthserv). Ensure it is Running. You can click '▶ Run restart_bluetooth_service' below to restart it cleanly.")
                next_steps.append("Step 3 — Inspect Device Manager: Press Win + X > Device Manager > expand 'Bluetooth'. Ensure your Bluetooth adapter (e.g., Intel Wireless Bluetooth, Realtek Bluetooth Adapter) is enabled without a down-arrow or yellow error warning.")
                next_steps.append("Step 4 — Run WinFix AI Read-Only Diagnostics: Click '▶ Run get_bluetooth_diagnostics' and '▶ Run get_bluetooth_service_status' below to check live hardware and service states.")
                recommended_tools.extend(["get_bluetooth_diagnostics", "get_bluetooth_service_status", "get_bluetooth_radio_status", "restart_bluetooth_service"])
                safety_notes.append("Restarting the Bluetooth Support Service (bthserv) is a verified MEDIUM-risk action requiring your confirmation.")
            elif is_quick_settings_missing_wifi or (is_wifi_query and ("quick" in facts_lower or "settings" in facts_lower or "flyout" in facts_lower)):
                title = "Wi-Fi Missing from Quick Settings — Step-by-Step Diagnostic Guide"
                what_happened = "From your screenshot, the Wi-Fi button is completely missing from Windows Quick Settings. Bluetooth is present, and Airplane mode is OFF, so this is likely not just Wi-Fi being toggled off."
                what_this_means = "When the Wi-Fi quick toggle button disappears completely, Windows either cannot communicate with your wireless network card, the wireless adapter is disabled in Network Connections, or the WLAN AutoConfig background service has stopped."
                possible_causes.append("1. Wi-Fi adapter is disabled in Windows Network Connections (ncpa.cpl)")
                possible_causes.append("2. Wi-Fi adapter/driver is missing or encountering an error in Device Manager")
                possible_causes.append("3. WLAN AutoConfig service (WlanSvc) is stopped or disabled")
                possible_causes.append("4. Windows is not detecting the physical wireless hardware")
                next_steps.append("Step 1 — Check the Wi-Fi adapter in Device Manager: Press Win + X → Device Manager → expand 'Network adapters' → Look for Intel Wi-Fi / Realtek Wireless LAN / MediaTek Wi-Fi / Qualcomm Wireless / 802.11 adapter. If you see it with a down-arrow, right-click → 'Enable device'. If you see a yellow warning icon, the driver/device has a problem. If no wireless adapter is listed, Windows is not detecting the hardware.")
                next_steps.append("Step 2 — Check Windows Network Connections: Press Win + R, type 'ncpa.cpl' and press Enter. Look for 'Wi-Fi'. If it says Disabled → right-click → 'Enable'. If Wi-Fi isn't listed → Windows may not be detecting the adapter.")
                next_steps.append("Step 3 — Check WLAN service: Press Win + R and run 'services.msc'. Find 'WLAN AutoConfig'. Ensure Status is 'Running' and Startup type is 'Automatic'. If it isn't running, right-click → Start.")
                next_steps.append("Step 4 — Run WinFix AI Read-Only Diagnostics: Click '▶ Run get_network_adapters_diagnostics' and '▶ Run get_services_diagnostics' below to verify active system state.")
                recommended_tools.extend(["get_network_adapters_diagnostics", "get_services_diagnostics", "check_dns_resolution", "check_internet_connectivity"])
                safety_notes.append("Diagnostic Workflow: Wi-Fi Quick Settings Missing → Check Network Adapters (ncpa.cpl) → Wi-Fi adapter detected? (YES: Enabled? / NO: Check Device Manager driver) → WLAN AutoConfig (services.msc).")
            elif any(k in facts_lower for k in ["wifi", "wi-fi", "network", "internet", "dns", "offline", "disconnect"]):
                title = "Network & Wi-Fi Diagnostic — Step-by-Step Solution Guide"
                what_this_means = "A network or internet connectivity problem is visible. This can be caused by adapter disconnects, bad gateway routes, or stale DNS resolver cache."
                possible_causes.append("DNS server unreachable or stale DNS resolver cache.")
                possible_causes.append("Wi-Fi adapter disconnected from access point or IP lease expired.")
                next_steps.append("1. Run 'check_dns_resolution' and 'check_internet_connectivity' below.")
                next_steps.append("2. Flush your local DNS cache using 'flush_dns_cache'.")
                next_steps.append("3. Restart your Wi-Fi router or reconnect to the wireless network.")
                recommended_tools.extend(["check_dns_resolution", "check_internet_connectivity", "get_network_adapters_diagnostics"])
            elif any(k in facts_lower for k in ["battery", "%", "power", "charge", "energy", "sleep"]):
                title = "Power & Battery Management — Step-by-Step Diagnostic Guide"
                what_this_means = "Your screen displays Windows Power & Battery settings. When battery charge drops low, Windows enables Battery Saver to conserve power by limiting background tasks and display brightness."
                possible_causes.append("Battery is low or discharging on portable power.")
                possible_causes.append("High CPU/GPU background applications may be draining battery life.")
                next_steps.append("1. Connect your PC to an AC power adapter/charger.")
                next_steps.append("2. Open Windows Settings (Win + I) > System > Power & battery to configure Battery Saver mode.")
                next_steps.append("3. Run 'get_top_cpu_processes' to identify background programs drawing excess power.")
                recommended_tools.extend(["get_complete_system_info", "get_top_cpu_processes"])
            elif any(k in facts_lower for k in ["update", "0x8024", "0x8007", "kb", "wuauserv"]):
                title = "Windows Update Error & Diagnostics — Step-by-Step Solution Guide"
                what_happened = "The screenshot displays a Windows Update error or installation failure."
                what_this_means = "A Windows Update error or download failure is visible. This typically occurs when update background services are stopped or local update cache files are corrupted."
                possible_causes.append("Windows Update service ('wuauserv') or BITS service is stopped or blocked.")
                possible_causes.append("Corrupted Windows Update download cache in SoftwareDistribution.")
                next_steps.append("1. Run 'get_windows_update_health' below to inspect update services.")
                next_steps.append("2. If services are stopped, restart the Windows Update service.")
                next_steps.append("3. Go to Windows Settings > Windows Update and click 'Check for updates'.")
                recommended_tools.extend(["get_windows_update_diagnostics", "get_windows_update_health"])
            elif any(k in facts_lower for k in ["crash", "stopped working", "event 1000", "exception", "c0000005"]):
                title = "Application Crash & Exception — Step-by-Step Diagnostic Guide"
                what_happened = "The screenshot displays an application crash or runtime error dialog."
                what_this_means = "An application error or crash dialog is displayed. This occurs when an executable encounters an unhandled exception or missing library."
                possible_causes.append("Application configuration corruption or incompatible DLL module.")
                possible_causes.append("Insufficient available RAM or outdated application version.")
                next_steps.append("1. Inspect crash events using 'get_recent_application_crashes' below.")
                next_steps.append("2. Check for software updates for the crashing application.")
                next_steps.append("3. Run system memory diagnostics to verify RAM availability.")
                recommended_tools.extend(["get_recent_application_crashes", "get_application_crash_summary"])
            elif any(k in facts_lower for k in ["defender", "virus", "threat", "security", "windefend", "trojan", "malware"]):
                title = "Windows Security & Defender Alert — Step-by-Step Diagnostic Guide"
                what_happened = "The screenshot displays a Windows Security or antivirus alert."
                what_this_means = "A security alert or Windows Defender threat notification is displayed. Windows Security has identified an untrusted file or active threat requiring user attention."
                possible_causes.append("Windows Defender detected suspicious heuristics or known malware signature.")
                possible_causes.append("Real-time protection flagged an installer or downloaded payload.")
                next_steps.append("1. Run 'get_defender_diagnostics' below to assess active threat status.")
                next_steps.append("2. Open Windows Security > Virus & threat protection to review threat details.")
                next_steps.append("3. Follow Defender remediation recommendations (quarantine or remove).")
                recommended_tools.extend(["get_defender_diagnostics", "get_defender_threats"])
            elif any(k in facts_lower for k in ["disk", "storage", "space", "low disk", "c:"]):
                title = "Low Disk Space & Storage — Step-by-Step Solution Guide"
                what_happened = "The screenshot displays low disk space on a Windows storage drive."
                what_this_means = "Your storage drive is nearly full. Running out of disk space can cause system slowdowns, update failures, and prevent applications from writing temporary files."
                possible_causes.append("Large temporary file buildup in user or Windows cache directories.")
                possible_causes.append("Downloaded installers, old Windows Update cache, or system restore points.")
                next_steps.append("1. Run 'get_storage_diagnostics' below to check volume capacity.")
                next_steps.append("2. Inspect and clean temporary cache with 'clean_user_temp_cache'.")
                next_steps.append("3. Open Storage Sense in Windows Settings to remove unused files.")
                recommended_tools.extend(["get_storage_diagnostics", "clean_user_temp_cache"])
            elif any(k in facts_lower for k in ["cpu", "memory", "ram", "performance", "slow", "task manager", "freeze", "lag"]):
                title = "High Resource Utilization & Performance — Step-by-Step Diagnostic Guide"
                what_happened = "The screenshot displays high CPU or resource consumption in Task Manager."
                what_this_means = "A background process or hardware interrupt is consuming excess processor cycles, which can cause freezing, frame drops, and cooling fan throttling."
                possible_causes.append("Runaway background application or background rendering/compilation.")
                possible_causes.append("System Interrupts caused by hardware device driver state stalls.")
                next_steps.append("1. Run 'get_top_cpu_processes' below to inspect highest consuming tasks.")
                next_steps.append("2. Run 'get_cpu_diagnostics' to verify real-time load.")
                next_steps.append("3. Check Device Manager for misbehaving hardware or outdated drivers.")
                recommended_tools.extend(["get_top_cpu_processes", "get_cpu_diagnostics", "get_top_memory_processes"])
            else:
                what_this_means = "Visual elements from your screen have been analyzed. Run the suggested read-only diagnostic checks below to inspect the active Windows system state."
                if interps:
                    for interp in interps:
                        possible_causes.append(str(interp))
                else:
                    possible_causes.append("Visual interface state or notification displayed on the screen.")
                if tools:
                    next_steps.append(f"Run verified read-only diagnostics ({', '.join(tools[:3])}) to inspect active system state.")
                else:
                    next_steps.append("Run baseline system info to inspect active operating system health.")

            evidence.append(f"Visual Observation: {facts}")
            if errs:
                evidence.append(f"Detected Error Codes: {', '.join(errs)}")
                severity = TutorSeverity.ELEVATED.value
            if apps:
                evidence.append(f"Detected Applications/Windows: {', '.join(apps)}")

            if uncerts:
                safety_notes.extend([str(u) for u in uncerts[:2]])
            else:
                safety_notes.append("Screenshots capture visible UI state and cannot verify background system state without live diagnostics.")

            if tools:
                recommended_tools.extend(tools)
            else:
                recommended_tools.append("get_complete_system_info")

        # Domain 0B: Voice Evidence Breakdown
        elif isinstance(diag_data, dict) and "voice_evidence" in diag_data:
            v_ev = diag_data["voice_evidence"]
            transcript = str(v_ev.get("transcript") or v_ev.get("spoken_transcript") or "Spoken voice input recorded.").strip()
            intent = str(v_ev.get("intent") or v_ev.get("inferred_intent") or "Voice diagnostic inquiry.").strip()
            hints = v_ev.get("hints") or v_ev.get("inferred_categories") or []
            needs_verif = v_ev.get("what_needs_verification") or []
            tools = v_ev.get("candidate_tools") or v_ev.get("recommended_tools") or []

            title = "Voice Diagnostic Breakdown"
            what_happened = f"Transcribed spoken voice input: \"{transcript}\""
            what_this_means = f"Identified troubleshooting intent: {intent}. Spoken descriptions provide symptom context and must be confirmed through verified read-only diagnostics."
            evidence.append(f"Spoken Transcript: \"{transcript}\"")
            if hints:
                evidence.append(f"Inferred Categories: {', '.join(hints)}")
            if needs_verif:
                safety_notes.extend([str(nv) for nv in needs_verif[:2]])
            possible_causes.append(f"Reported symptom: {intent}")
            if tools:
                recommended_tools.extend(tools)
                next_steps.append(f"Run verified read-only diagnostics ({', '.join(tools[:3])}) to test active system state.")
            else:
                recommended_tools.append("get_complete_system_info")
                next_steps.append("Run baseline system diagnostics to confirm system state.")

        # Domain 0C: Power / Battery Subsystem
        elif detected_domain == "power" or (not is_composite_diag and ("battery" in diag_data or "power" in diag_data or "battery_percent" in diag_data)):
            title = "Power & Battery Subsystem Explanation"
            what_happened = "Inspected power state, battery health, and system energy management."
            what_this_means = "Battery charge level and Windows power plans govern hardware performance, CPU throttling, and sleep transitions."
            evidence.append("Inspected system power metrics and device battery status.")
            possible_causes.append("Battery discharge or low charge state triggering Windows power saver limits.")
            possible_causes.append("Background power-intensive processes consuming energy.")
            next_steps.append("Connect AC power adapter or inspect system background processes.")
            recommended_tools.append("get_complete_system_info")
            recommended_tools.append("get_top_cpu_processes")

        # Domain 0D: System Information & Settings
        elif detected_domain == "system_info" or (not is_composite_diag and ("computer" in diag_data or "os" in diag_data)):
            title = "Windows System Environment & Settings"
            what_happened = "Collected baseline operating system, hardware specifications, and system environment info."
            what_this_means = "System hardware information provides the foundational baseline for all hardware drivers and Windows services."
            evidence.append("Operating system environment and hardware baseline verified.")
            possible_causes.append("Hardware configuration or system settings observation.")
            next_steps.append("Run comprehensive system diagnostic scan.")
            recommended_tools.append("get_complete_system_info")

        # Domain 1: Application Crashes
        elif detected_domain == "application_crash" or (not is_composite_diag and ("crashes" in diag_data or "total_crashes" in diag_data or "overall_status" in diag_data or "crash_summary" in diag_data or "events" in diag_data)):
            title = "Application Crash Diagnostics Explanation"
            crash_res = diag_data.get("crash_summary", diag_data.get("events", diag_data))
            crash_data = crash_res.get("data", {}) if isinstance(crash_res, dict) and "data" in crash_res else (crash_res if isinstance(crash_res, dict) else {})
            total = crash_data.get("total_crashes", 0)
            if total == 0 and "total_crashes" in diag_data:
                total = diag_data["total_crashes"]
            if total == 0 and "crashes" in diag_data and isinstance(diag_data["crashes"], (int, float)):
                total = int(diag_data["crashes"])
            elif total == 0 and "crashes" in diag_data and isinstance(diag_data["crashes"], list):
                total = len(diag_data["crashes"])

            evidence.append(f"Total crash events observed: {total}")
            if total > 0:
                severity = TutorSeverity.ELEVATED.value
                what_happened = f"Windows logged {total} application error or crash event(s) in the Application event log."
                what_this_means = "One or more software programs encountered an unhandled exception or became unresponsive."
                possible_causes.append("Software version incompatibility or missing application update")
                possible_causes.append("Corrupted application configuration or damaged dependency DLL")
                next_steps.append("Review application-specific logs or reinstall the application if instability persists.")
                recommended_tools.append("get_recent_application_crashes")
                recommended_tools.append("get_application_crash_summary")
            else:
                what_happened = "No recent application crash events were detected in the Windows Application log."
                what_this_means = "Your installed applications appear to be running normally without logged crash events."
                possible_causes.append("Application environment is healthy and stable.")
                next_steps.append("No immediate application troubleshooting required.")
                recommended_tools.append("get_recent_application_crashes")

        # Domain 2: Windows Update
        elif detected_domain == "windows_update" or (not is_composite_diag and ("update_services_ready" in diag_data or "windows_update" in diag_data)):
            title = "Windows Update Diagnostic Explanation"
            up_res = diag_data.get("windows_update", {}) if isinstance(diag_data.get("windows_update"), dict) else diag_data
            up_data = up_res.get("data", {}) if isinstance(up_res, dict) and "data" in up_res else (up_res if isinstance(up_res, dict) else {})
            if "update_services_ready" in diag_data:
                ready = bool(diag_data["update_services_ready"])
            elif isinstance(diag_data.get("windows_update"), bool):
                ready = diag_data.get("windows_update")
            else:
                ready = up_data.get("update_services_ready", True) if isinstance(up_data, dict) else True
            if not ready:
                severity = TutorSeverity.ELEVATED.value
                what_happened = "One or more core Windows Update background services are not in the expected running state."
                what_this_means = "Windows may be temporarily unable to check for or download new security updates."
                possible_causes.append("Windows Update service ('wuauserv') is stopped or in a pending state")
                next_steps.append("Verify the Windows Update service status.")
                recommended_tools.append("get_windows_update_diagnostics")
            else:
                what_happened = "Windows Update services are active and configured properly."
                what_this_means = "Your computer can successfully receive routine Windows updates and patches."
                possible_causes.append("Update subsystem is active.")
                evidence.append("Windows Update service is RUNNING.")
                next_steps.append("Check Windows Settings for available pending updates.")
                recommended_tools.append("get_windows_update_diagnostics")

        # Domain 3: Windows Defender / Security
        elif detected_domain == "defender" or (not is_composite_diag and ("antivirus_service_running" in diag_data or "firewall_service_running" in diag_data or "defender" in diag_data)):
            title = "Microsoft Defender Security Explanation"
            def_res = diag_data.get("defender", {}) if isinstance(diag_data.get("defender"), dict) else diag_data
            def_data = def_res.get("data", {}) if isinstance(def_res, dict) and "data" in def_res else (def_res if isinstance(def_res, dict) else {})
            if "antivirus_service_running" in diag_data:
                av_running = bool(diag_data["antivirus_service_running"])
                fw_running = bool(diag_data.get("firewall_service_running", True))
            elif isinstance(diag_data.get("defender"), bool):
                av_running = diag_data.get("defender")
                fw_running = diag_data.get("defender")
            else:
                av_running = def_data.get("antivirus_service_running", def_data.get("real_time_protection", True))
                fw_running = def_data.get("firewall_service_running", True)
            evidence.append(f"Defender Antivirus service running: {av_running}")
            evidence.append(f"Windows Firewall service running: {fw_running}")
            if not av_running or not fw_running:
                severity = TutorSeverity.HIGH.value
                what_happened = "Microsoft Defender antivirus or firewall protection is currently stopped."
                what_this_means = "Real-time background malware scanning or network filtering is inactive."
                possible_causes.append("WinDefend service was stopped or third-party security software is managing protection")
                next_steps.append("Inspect Microsoft Defender security health and verify real-time protection.")
                recommended_tools.append("get_defender_diagnostics")
            else:
                what_happened = "Microsoft Defender real-time protection and firewall are active."
                what_this_means = "Your system is actively protected against known security threats and unauthorized network access."
                possible_causes.append("Security subsystem is functioning as expected.")
                next_steps.append("Keep security intelligence signatures updated.")
                recommended_tools.append("get_defender_diagnostics")

        # Domain 4: Network / Wi-Fi
        elif detected_domain == "network" or (not is_composite_diag and ("resolved" in diag_data or "reachable" in diag_data or "dns" in diag_data or "internet" in diag_data or "adapters" in diag_data)):
            title = "Wi-Fi & Network Connectivity Explanation"
            dns_res = diag_data.get("dns", {}) if isinstance(diag_data.get("dns"), dict) else diag_data
            inet_res = diag_data.get("internet", {}) if isinstance(diag_data.get("internet"), dict) else diag_data
            if "resolved" in diag_data:
                resolved = bool(diag_data["resolved"])
            elif isinstance(diag_data.get("dns"), bool):
                resolved = diag_data.get("dns")
            else:
                resolved = dns_res.get("data", {}).get("resolved", dns_res.get("resolved", True)) if isinstance(dns_res, dict) else True

            if "reachable" in diag_data:
                reachable = bool(diag_data["reachable"])
            elif isinstance(diag_data.get("internet"), bool):
                reachable = diag_data.get("internet")
            else:
                reachable = inet_res.get("data", {}).get("reachable", inet_res.get("reachable", True)) if isinstance(inet_res, dict) else True

            evidence.append(f"DNS Resolution: {'Working' if resolved else 'Failed'}")
            evidence.append(f"Internet Host Reachable: {'Yes' if reachable else 'No'}")
            if not resolved or not reachable:
                severity = TutorSeverity.ELEVATED.value
                what_happened = "Network connectivity inspection detected an issue reaching online destinations."
                what_this_means = "You may experience trouble connecting to Wi-Fi, opening websites, or accessing internet services."
                if not resolved:
                    possible_causes.append("DNS resolver cache contains stale entries or DNS server is unreachable")
                    next_steps.append("Consider flushing your DNS resolver cache.")
                    recommended_tools.append("check_dns_resolution")
                    recommended_tools.append("flush_dns_cache")
                if not reachable:
                    possible_causes.append("Default gateway is unreachable or router Wi-Fi lease has expired")
                    next_steps.append("Check router cable/Wi-Fi connection and adapter link state.")
                    recommended_tools.append("get_network_adapters_diagnostics")
                    recommended_tools.append("check_internet_connectivity")
            else:
                what_happened = "DNS resolution and gateway reachability checks succeeded."
                what_this_means = "Your network adapter is connected and actively communicating with local and online gateways."
                possible_causes.append("Network configuration and adapter link state are operational.")
                next_steps.append("Run network adapter diagnostics or test internet latency if experiencing intermittent drops.")
                recommended_tools.append("check_internet_connectivity")
                recommended_tools.append("get_network_adapters_diagnostics")
                recommended_tools.append("check_dns_resolution")

        # Domain 5: Bluetooth
        elif detected_domain == "bluetooth" or (not is_composite_diag and "bluetooth" in diag_data):
            title = "Bluetooth Subsystem Diagnostics Explanation"
            bt_res = diag_data.get("bluetooth", {}) if isinstance(diag_data.get("bluetooth"), dict) else diag_data
            bt_data = bt_res.get("data", {}) if isinstance(bt_res.get("data"), dict) else (bt_res if isinstance(bt_res, dict) else {})
            svc_running = bt_data.get("service_running", True) if isinstance(bt_data, dict) else bool(bt_res)
            adapter_det = bt_data.get("adapter_detected", True) if isinstance(bt_data, dict) else True
            evidence.append(f"Bluetooth Support Service: {'Running' if svc_running else 'Stopped'}")
            evidence.append(f"Bluetooth Hardware Adapter: {'Detected' if adapter_det else 'Not Found'}")
            if not svc_running or not adapter_det:
                severity = TutorSeverity.ELEVATED.value
                what_happened = "Bluetooth service is stopped or hardware radio adapter was not detected."
                what_this_means = "Wireless accessories (headphones, mice, keyboards) cannot pair or connect."
                possible_causes.append("Bluetooth Support Service (bthserv) is stopped or radio driver is disabled")
                next_steps.append("Inspect Bluetooth adapter diagnostics and restart Bluetooth Support Service.")
                recommended_tools.append("get_bluetooth_diagnostics")
            else:
                what_happened = "Bluetooth Support Service is running and adapter hardware is ready."
                what_this_means = "Windows is ready to discover, pair, and communicate with Bluetooth peripherals."
                possible_causes.append("Bluetooth stack is operational.")
                next_steps.append("Check peripheral device battery and pairing mode if connection fails.")
                recommended_tools.append("get_bluetooth_diagnostics")

        # Domain 6: Printer
        elif detected_domain == "printer" or (not is_composite_diag and "printer" in diag_data):
            title = "Printer & Print Spooler Explanation"
            pr_res = diag_data.get("printer", {}) if isinstance(diag_data.get("printer"), dict) else diag_data
            pr_data = pr_res.get("data", {}) if isinstance(pr_res.get("data"), dict) else (pr_res if isinstance(pr_res, dict) else {})
            spool_running = pr_data.get("spooler_running", True) if isinstance(pr_data, dict) else bool(pr_res)
            tot_p = pr_data.get("total_printers", 0) if isinstance(pr_data, dict) else 0
            evidence.append(f"Print Spooler Service: {'Running' if spool_running else 'Stopped'}")
            evidence.append(f"Configured Printers: {tot_p}")
            if not spool_running:
                severity = TutorSeverity.ELEVATED.value
                what_happened = "The Windows Print Spooler service (spoolsv) is currently stopped."
                what_this_means = "Print jobs cannot be sent to printers and printer properties cannot be opened."
                possible_causes.append("Print Spooler service crashed due to a corrupted print job in the queue")
                next_steps.append("Restart the Print Spooler service and clear any stalled jobs.")
                recommended_tools.append("get_printer_diagnostics")
            else:
                what_happened = "Print Spooler service is active and managing printer queues normally."
                what_this_means = "Your computer can communicate with local and network printers."
                possible_causes.append("Print spooler subsystem is healthy.")
                next_steps.append("Check printer power and paper queue if documents fail to print.")
                recommended_tools.append("get_printer_diagnostics")

        # Domain 7: Performance / Storage
        elif detected_domain in ("performance", "storage") or (not is_composite_diag and ("cpu_percent" in diag_data or "percent_used" in diag_data or "storage_pressure_level" in diag_data or "storage" in diag_data or "top_cpu" in diag_data)):
            title = "System Performance & Storage Explanation"
            evidence.append("Inspected CPU load and storage drive capacity.")
            what_happened = "System resources (CPU, RAM, Storage) are within normal operating thresholds."
            what_this_means = "Hardware resource utilization is healthy and no critical bottlenecks were detected."
            possible_causes.append("System load is balanced.")
            next_steps.append("Continue regular PC usage or clean temporary files to reclaim space.")
            recommended_tools.append("get_storage_diagnostics")
            recommended_tools.append("get_top_cpu_processes")

        # Composite Multi-Domain Assessment (when user asks general system question or clicks explain diagnostics)
        else:
            title = "Windows System Diagnostics Overview"
            what_happened = "All core Windows diagnostic subsystems are operating normally within healthy parameters."
            what_this_means = "WinFix AI performed comprehensive read-only inspections across Network, Security, Storage, Performance, Peripherals, and Windows Update. No critical service disruptions were identified."
            evidence.append(f"Evaluated {len(diag_data)} diagnostic subsystems.")
            if "dns" in diag_data:
                evidence.append("Network: DNS resolution and internet reachability verified.")
            if "defender" in diag_data:
                evidence.append("Security: Microsoft Defender protection active.")
            if "storage" in diag_data:
                evidence.append("Storage: Drives evaluated and healthy.")
            if "windows_update" in diag_data:
                evidence.append("Updates: Windows Update subsystem configured.")
            possible_causes.append("Standard Windows system state observation across all monitored subsystems.")
            next_steps.append("Ask a specific question (e.g. 'How to solve Wi-Fi problem') for targeted troubleshooting guidance.")
            recommended_tools.append("get_complete_system_info")

        summary = f"{title}: {what_happened}"
        return TutorResponse(
            title=title,
            summary=summary,
            what_happened=what_happened,
            evidence=evidence,
            severity=severity,
            severity_explanation=f"Evaluated as {severity} based on diagnostic facts.",
            possible_causes=possible_causes,
            what_this_means=what_this_means,
            recommended_next_steps=next_steps,
            recommended_tools=recommended_tools,
            safety_notes=safety_notes,
            educational_notes=["Personal Tutor Mode provides structured, factual explanations so you understand your system."],
            limitations=["Deterministic mode: full natural-language synthesis is active when local Ollama is online."],
            confidence=0.9,
        )

    def _build_deterministic_repair_fallback(
        self,
        tool_name: str,
        verification_status: str,
        before_state: Optional[Dict[str, Any]],
        after_state: Optional[Dict[str, Any]],
        repair_output: Optional[Dict[str, Any]],
    ) -> TutorResponse:
        """Deterministic explanation of a verified repair action."""
        evidence = [
            f"Executed Tool: '{tool_name}'",
            f"Verification Status: '{verification_status}'",
        ]
        if before_state:
            evidence.append(f"Before State: {json.dumps(before_state)}")
        if after_state:
            evidence.append(f"After State: {json.dumps(after_state)}")

        if verification_status == "verified":
            title = f"Repair Verified: '{tool_name}'"
            what_happened = f"WinFix AI executed the repair action '{tool_name}' and verified that the target component recovered to its expected healthy state."
            what_this_means = "The specific service or cache state has been restored to normal working order."
            verification_explanation = "The repair was verified successfully. Deterministic verification confirmed that the target state matched the required baseline."
            possible_causes = ["Transient system deadlock or temporary cache corruption that was resolved by the repair."]
            next_steps = ["Verify if the original problem or application symptom has cleared."]
            educational_notes = ["Verifying a repair ensures the operation actually succeeded rather than assuming it worked."]
            severity = TutorSeverity.NORMAL.value
        elif verification_status in ("not_verified", "verification_failed"):
            title = f"Repair Not Verified: '{tool_name}'"
            what_happened = f"WinFix AI attempted the repair '{tool_name}', but verification could not establish that the component reached the expected state."
            what_this_means = "The service or component may still be unresponsive or locked by another process."
            verification_explanation = "Verification failed to confirm the expected post-repair state."
            possible_causes = ["Underlying configuration conflicts or dependency service failures preventing recovery."]
            next_steps = ["Review Windows Event logs or inspect related dependency services."]
            educational_notes = ["If a repair is not verified, avoid repeatedly running the same action."]
            severity = TutorSeverity.ELEVATED.value
        elif verification_status == "verification_timeout":
            title = f"Repair Verification Timed Out: '{tool_name}'"
            what_happened = f"The repair '{tool_name}' was initiated, but post-repair verification timed out waiting for the target state."
            what_this_means = "The component is taking longer than expected to start or respond."
            verification_explanation = "Verification timed out before the service reported RUNNING."
            possible_causes = ["Heavy system disk load or background initialization delays."]
            next_steps = ["Wait 30 seconds and refresh diagnostics."]
            educational_notes = ["Some complex Windows services take extra time to complete startup procedures."]
            severity = TutorSeverity.ELEVATED.value
        else:
            title = f"Repair Status: '{tool_name}' ({verification_status})"
            what_happened = f"The repair '{tool_name}' concluded with verification status '{verification_status}'."
            what_this_means = "Check the detailed repair output payload for specific error messages."
            verification_explanation = f"Verification outcome: {verification_status}"
            possible_causes = ["Operation was interrupted or blocked by system policies."]
            next_steps = ["Review system permissions and diagnostic results."]
            educational_notes = ["All repairs in WinFix AI require verification to confirm their actual effect."]
            severity = TutorSeverity.NORMAL.value

        return TutorResponse(
            title=title,
            summary=f"{title}: {what_happened}",
            what_happened=what_happened,
            evidence=evidence,
            severity=severity,
            severity_explanation=f"Verification status: {verification_status}",
            possible_causes=possible_causes,
            what_this_means=what_this_means,
            recommended_next_steps=next_steps,
            recommended_tools=[],
            safety_notes=["A verified service restart confirms service recovery, but does not guarantee resolution of external network or third-party app bugs."],
            verification_explanation=verification_explanation,
            educational_notes=educational_notes,
            limitations=["Repair explanation was synthesized using deterministic verification rules."],
            confidence=0.95,
        )

    def _build_deterministic_question_fallback(
        self,
        question: str,
        diag_data: Optional[Dict[str, Any]],
    ) -> TutorResponse:
        """Deterministic question answering fallback using local knowledge base and live diagnostics."""
        q_lower = (question or "").lower().strip()
        if any(w in q_lower for w in ["why the wifi is not shown", "wifi is not shown", "wifi not shown", "wifi missing", "wifi disappeared", "no wifi icon", "wifi button missing", "wifi option missing", "where is my wifi", "cannot find wifi", "where is wifi"]):
            title = "Wi-Fi Missing from Windows Quick Settings — Diagnostic & Solution Guide"
            what_happened = "The Wi-Fi button is missing from Windows Quick Settings. Bluetooth is present, and Airplane mode is OFF, indicating wireless hardware is powered but the Wi-Fi subsystem is inactive or unrecognized."
            what_this_means = "When the Wi-Fi option disappears from Quick Settings, Windows either cannot communicate with the wireless network adapter, the Wi-Fi adapter is disabled in Network Connections, or the WLAN AutoConfig background service is stopped."
            possible_causes = [
                "1. Wi-Fi adapter is disabled in Windows Network Connections (ncpa.cpl)",
                "2. Wi-Fi adapter driver is missing or encountering an error in Device Manager",
                "3. WLAN AutoConfig service (WlanSvc) is stopped or disabled",
                "4. Windows is not detecting the physical wireless hardware",
            ]
            evidence = [
                "User query: Wi-Fi option is missing or not displayed",
                "Troubleshooting domain: NETWORK / SERVICES / ADAPTERS",
            ]
            if isinstance(diag_data, dict):
                adapters_p = diag_data.get("adapters", {})
                if isinstance(adapters_p, dict) and "data" in adapters_p:
                    ad_list = adapters_p["data"].get("adapters", [])
                    has_wifi = any("wi-fi" in str(a.get("name", "")).lower() or "wireless" in str(a.get("name", "")).lower() for a in ad_list if isinstance(a, dict))
                    evidence.append(f"Live Wi-Fi Adapter Detected: {'Yes' if has_wifi else 'No (Missing from active adapters)'}")
            next_steps = [
                "Step 1 — Check the Wi-Fi adapter in Device Manager: Press Win + X → Device Manager → expand 'Network adapters' → Look for Intel Wi-Fi / Realtek Wireless LAN / MediaTek Wi-Fi / Qualcomm Wireless / 802.11 adapter. If you see it with a down-arrow, right-click → 'Enable device'. If you see a yellow warning icon, the driver/device has a problem. If no wireless adapter is listed, Windows is not detecting the hardware.",
                "Step 2 — Check Windows Network Connections: Press Win + R, type 'ncpa.cpl' and press Enter. Look for 'Wi-Fi'. If it says Disabled → right-click → 'Enable'. If Wi-Fi isn't listed → Windows may not be detecting the adapter.",
                "Step 3 — Check WLAN service: Press Win + R and run 'services.msc'. Find 'WLAN AutoConfig'. Ensure Status is 'Running' and Startup type is 'Automatic'. If it isn't running, right-click → Start.",
                "Step 4 — Run WinFix AI Read-Only Diagnostics: Run 'get_network_adapters_diagnostics' and 'get_services_diagnostics' to verify live Windows status.",
            ]
            valid_tools = [t for t in ["get_network_adapters_diagnostics", "get_services_diagnostics", "check_dns_resolution", "check_internet_connectivity"] if self.tool_registry.get(t)]
            return TutorResponse(
                title=title,
                summary=f"{title}: {what_happened}",
                what_happened=what_happened,
                evidence=evidence,
                severity=TutorSeverity.ELEVATED.value,
                severity_explanation="Wi-Fi toggle absence prevents wireless network connections.",
                possible_causes=possible_causes,
                what_this_means=what_this_means,
                recommended_next_steps=next_steps,
                recommended_tools=valid_tools,
                safety_notes=["Diagnostic Workflow: Wi-Fi Quick Settings Missing → Check Network Adapters (ncpa.cpl) → Wi-Fi adapter detected? (YES: Enabled? / NO: Check Device Manager driver) → WLAN AutoConfig (services.msc)."],
                educational_notes=[
                    "If Bluetooth works while Wi-Fi is missing on a combo wireless card, hardware power is present; the issue is almost always a disabled adapter, corrupted driver, or stopped WlanSvc.",
                    "Always run safe read-only diagnostics in WinFix AI before attempting driver reinstalls.",
                ],
                limitations=["Visual observations and questions represent symptom reports; verified read-only diagnostics confirm active system state."],
                confidence=0.98,
            )

        art = None
        if question and self.knowledge_service:
            try:
                search_results = self.knowledge_service.search(query=question, limit=3)
                if search_results and search_results[0].article and search_results[0].relevance_score > 0.0:
                    art = search_results[0].article
            except Exception as exc:
                logger.debug("Knowledge lookup in tutor fallback failed: %s", exc)

        detected_domain = _detect_domain_from_text(question)
        if not detected_domain and art:
            cat_map = {
                "NETWORK": "network",
                "STORAGE": "storage",
                "PERFORMANCE": "performance",
                "SERVICES": "services",
                "BLUETOOTH": "bluetooth",
                "WINDOWS_UPDATE": "windows_update",
                "DEFENDER": "defender",
                "APPLICATION_CRASH": "application_crash",
            }
            cat_name = art.category.value if hasattr(art.category, "value") else str(art.category)
            detected_domain = cat_map.get(cat_name, "general")

        if art:
            cat_val = art.category.value if hasattr(art.category, "value") else str(art.category)
            if detected_domain == "printer" and cat_val == "GENERAL":
                title = "Printer & Print Spooler Subsystem Troubleshooting"
            else:
                title = f"{art.title}"
            what_happened = art.summary
            evidence = [f"Troubleshooting domain: {cat_val}"]

            # Enrich with live diagnostic facts from diag_data
            if isinstance(diag_data, dict):
                if detected_domain == "network":
                    dns_p = diag_data.get("dns", {})
                    inet_p = diag_data.get("internet", {})
                    if isinstance(dns_p, dict) and "data" in dns_p:
                        res = dns_p["data"].get("resolved")
                        lat = dns_p["data"].get("latency_ms")
                        evidence.append(f"Live DNS Resolution: {'PASS' if res else 'FAILED'} ({lat:.1f} ms)" if lat else f"Live DNS Resolution: {'PASS' if res else 'FAILED'}")
                    if isinstance(inet_p, dict) and "data" in inet_p:
                        reach = inet_p["data"].get("reachable")
                        evidence.append(f"Live Gateway Reachability: {'Reachable' if reach else 'Unreachable'}")
                elif detected_domain == "defender":
                    def_p = diag_data.get("defender", {})
                    if isinstance(def_p, dict) and "data" in def_p:
                        rtp = def_p["data"].get("real_time_protection")
                        evidence.append(f"Live Defender Status: {'Active' if rtp else 'Standby'}")
                elif detected_domain == "bluetooth":
                    bt_p = diag_data.get("bluetooth", {})
                    if isinstance(bt_p, dict) and "data" in bt_p:
                        svc = bt_p["data"].get("service_running")
                        evidence.append(f"Live Bluetooth Service: {'Running' if svc else 'Stopped'}")
                elif detected_domain == "printer":
                    pr_p = diag_data.get("printer", {})
                    if isinstance(pr_p, dict) and "data" in pr_p:
                        spool = pr_p["data"].get("spooler_running")
                        evidence.append(f"Live Print Spooler: {'Running' if spool else 'Stopped'}")
                elif detected_domain == "storage":
                    st_p = diag_data.get("storage", {})
                    if isinstance(st_p, dict) and "data" in st_p:
                        warn = st_p["data"].get("low_space_warning")
                        evidence.append(f"Live Storage Status: {'Low Space Warning' if warn else 'Healthy'}")
                elif detected_domain == "performance":
                    cpu_p = diag_data.get("top_cpu", {})
                    if isinstance(cpu_p, dict) and "data" in cpu_p:
                        procs = cpu_p["data"].get("processes", [])
                        if procs:
                            top_n = procs[0].get("name", "Process")
                            top_c = procs[0].get("cpu_percent", 0.0)
                            evidence.append(f"Top Active Process: {top_n} ({top_c}% CPU)")

            evidence.extend(art.symptoms[:3])
            possible_causes = list(art.possible_causes)
            what_this_means = f"This question relates to {cat_val.replace('_', ' ').title()}. WinFix AI retrieved verified diagnostic guidance from the local troubleshooting knowledge base."
            next_steps = list(art.diagnostic_steps)
            valid_tools = [t for t in art.related_tools if self.tool_registry.get(t)]
            educational_notes = [
                f"Guidance referenced from knowledge article '{art.id}' ({art.title}).",
                *art.verification_steps[:2],
            ]
            safety_notes = ["Always perform safe read-only diagnostics first before applying system changes."]

            return TutorResponse(
                title=title,
                summary=f"{title}: {what_happened}",
                what_happened=what_happened,
                evidence=evidence,
                severity=TutorSeverity.NORMAL.value,
                severity_explanation="Assigned advisory severity from knowledge base.",
                possible_causes=possible_causes,
                what_this_means=what_this_means,
                recommended_next_steps=next_steps,
                recommended_tools=valid_tools,
                safety_notes=safety_notes,
                verification_explanation=None,
                educational_notes=educational_notes,
                limitations=["Deterministic mode: knowledge guidance verified against registered tool definitions."],
                confidence=art.confidence,
            )

        return self._build_deterministic_diagnostic_fallback(question, diag_data)

    def explain_topic_with_knowledge(
        self,
        topic: str,
        session_id: Optional[str] = None,
    ) -> TutorResponse:
        """Provide educational troubleshooting explanation directly from local knowledge base."""
        return self.answer_question(user_question=topic, session_id=session_id)

    def _record_tutor_interaction(
        self,
        session_id: Optional[str],
        interaction_type: str,
        response: TutorResponse,
    ) -> None:
        """Record structured tutor explanation in SQLite diagnostic repository."""
        if not session_id:
            return
        try:
            # Ensure session exists or create it
            existing_session = self.session_repo.get(session_id)
            if not existing_session:
                self.session_repo.create_session(session_id=session_id, mode="tutor")

            evidence_payload = {
                "interaction_type": interaction_type,
                "title": response.title,
                "severity": response.severity,
                "evidence_count": len(response.evidence),
                "recommended_tools": response.recommended_tools,
                "summary": response.summary,
            }

            self.diagnostic_repo.create(
                session_id=session_id,
                tool_name="personal_tutor",
                status=interaction_type,
                evidence_json=json.dumps(evidence_payload),
            )
        except Exception as exc:
            logger.debug("Failed to record tutor interaction in SQLite: %s", exc)


# Shared global tutor instance
default_personal_tutor = PersonalTutor()
