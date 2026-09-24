"""Bluetooth Diagnostics Orchestrator for WinFix AI (Phase 11).

Coordinates evidence collection across approved read-only Bluetooth diagnostic tools,
evaluates adapter presence, radio state, Bluetooth Support Service readiness,
and connected peripheral device status.

Strictly read-only: NO device unpairing, pairing, or state modification is performed.
"""

from dataclasses import dataclass, field
import json
import logging
from typing import Any, Dict, List, Optional

from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import DiagnosticRepository, SessionRepository

logger = logging.getLogger(__name__)

# Valid Bluetooth problem categories
BLUETOOTH_CATEGORIES = {
    "service_stopped",
    "service_disabled",
    "radio_off",
    "adapter_missing",
    "device_connection_issue",
    "general_bluetooth",
}


@dataclass
class BluetoothDiagnosis:
    """Structured, evidence-based Bluetooth diagnosis result."""

    problem_category: str
    summary: str
    observed_evidence: List[str] = field(default_factory=list)
    interpretation: List[str] = field(default_factory=list)
    confidence: float = 0.8
    recommended_next_steps: List[str] = field(default_factory=list)
    repair_available: bool = False
    proposed_tool: Optional[str] = None
    proposed_args: Optional[Dict[str, Any]] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize diagnosis result to dictionary."""
        return {
            "problem_category": self.problem_category,
            "summary": self.summary,
            "observed_evidence": self.observed_evidence,
            "interpretation": self.interpretation,
            "confidence": self.confidence,
            "recommended_next_steps": self.recommended_next_steps,
            "repair_available": self.repair_available,
            "proposed_tool": self.proposed_tool,
            "proposed_args": self.proposed_args,
            "tool_results": self.tool_results,
        }


class BluetoothDiagnosticsOrchestrator:
    """Coordinates read-only Bluetooth diagnostics, radio evaluation, and scenario analysis."""

    def __init__(
        self,
        safety_engine: Optional[SafetyEngine] = None,
        registry: Optional[ToolRegistry] = None,
        llm_client: Optional[OllamaClient] = None,
        db_mgr: Optional[DatabaseManager] = None,
    ) -> None:
        self.safety_engine = safety_engine or default_safety_engine
        self.registry = registry or default_tool_registry
        self.llm = llm_client or ollama_client
        self.db_manager = db_mgr or default_db_manager
        self.session_repo = SessionRepository(self.db_manager)
        self.diagnostic_repo = DiagnosticRepository(self.db_manager)

    def run_diagnostics(
        self,
        session_id: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> BluetoothDiagnosis:
        """Execute read-only Bluetooth diagnostic tools and synthesize findings."""
        tool_results: List[Dict[str, Any]] = []
        observed_evidence: List[str] = []
        interpretation: List[str] = []
        recommended_next_steps: List[str] = []

        # 1. Execute unified aggregator
        diag_res = self.safety_engine.execute(
            tool_name="get_bluetooth_diagnostics",
            session_id=session_id,
        )
        tool_results.append(diag_res)

        if not diag_res.get("success"):
            err_msg = diag_res.get("error", {}).get("message", "Bluetooth diagnostic query failed.")
            return BluetoothDiagnosis(
                problem_category="general_bluetooth",
                summary=f"Bluetooth query failed: {err_msg}",
                observed_evidence=[f"Diagnostic aggregator error: {err_msg}"],
                interpretation=["Unable to query Windows Bluetooth subsystem."],
                confidence=0.5,
                recommended_next_steps=["Check Windows Device Manager manually to inspect Bluetooth radio hardware."],
                repair_available=False,
                tool_results=tool_results,
            )

        data = diag_res.get("data", {})
        health = data.get("health", "HEALTHY")
        summary = data.get("summary", "")
        issues = data.get("issues", [])
        adapters = data.get("adapters", [])
        has_adapter = data.get("adapter_detected", False)
        radio = data.get("radio", {})
        radio_status = radio.get("radio_status", "UNKNOWN")
        service = data.get("service", {})
        svc_running = service.get("service_running", False)
        svc_status = service.get("status", "UNKNOWN")
        svc_start_type = service.get("start_type", "UNKNOWN")
        devices = data.get("devices", [])
        dev_count = len(devices)

        # Record observed facts
        if has_adapter:
            ad_name = adapters[0].get("name", "Standard Bluetooth Adapter") if adapters else "Standard Adapter"
            observed_evidence.append(f"Bluetooth controller detected: '{ad_name}'.")
        else:
            observed_evidence.append("No Bluetooth adapter hardware detected by Windows.")

        observed_evidence.append(f"Bluetooth Support Service (bthserv) status is {svc_status} (Startup: {svc_start_type}).")
        observed_evidence.append(f"Bluetooth Radio operational state is {radio_status}.")
        observed_evidence.append(f"Paired Bluetooth peripheral device count: {dev_count}.")

        # Scenario A: Hardware missing
        if not has_adapter:
            interpretation.append("No physical or virtual Bluetooth radio hardware was detected on this PC.")
            interpretation.append("Bluetooth capabilities require an integrated controller or USB Bluetooth dongle.")
            recommended_next_steps.append("Insert a compatible USB Bluetooth adapter or verify motherboard BIOS settings.")
            return BluetoothDiagnosis(
                problem_category="adapter_missing",
                summary="No Bluetooth adapter hardware is present on this device.",
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.95,
                recommended_next_steps=recommended_next_steps,
                repair_available=False,
                tool_results=tool_results,
            )

        # Scenario B: Service Disabled
        if svc_start_type == "DISABLED":
            interpretation.append("Bluetooth Support Service ('bthserv') is set to DISABLED in Windows.")
            interpretation.append("WinFix AI does not automatically alter service startup configuration in this phase.")
            recommended_next_steps.append("Open Windows Services (services.msc) and set 'Bluetooth Support Service' startup type to Manual or Automatic.")
            return BluetoothDiagnosis(
                problem_category="service_disabled",
                summary="Bluetooth Support Service is currently DISABLED in Windows configuration.",
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.95,
                recommended_next_steps=recommended_next_steps,
                repair_available=False,
                tool_results=tool_results,
            )

        # Scenario C: Service Stopped or Radio OFF with stopped service
        if not svc_running or svc_status == "STOPPED":
            interpretation.append(f"Bluetooth Support Service ('bthserv') is currently {svc_status}.")
            interpretation.append("Restarting the Bluetooth service will restore the Windows Bluetooth radio stack.")
            recommended_next_steps.append("Execute controlled restart of the Bluetooth Support Service.")
            return BluetoothDiagnosis(
                problem_category="service_stopped",
                summary="Bluetooth Support Service is stopped, preventing radio and device operation.",
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.9,
                recommended_next_steps=recommended_next_steps,
                repair_available=True,
                proposed_tool="restart_bluetooth_service",
                proposed_args={},
                tool_results=tool_results,
            )

        # Scenario D: Radio OFF despite service running (e.g. Device Manager disabled)
        if radio_status == "OFF":
            interpretation.append("Bluetooth radio is currently turned OFF or disabled in Device Manager.")
            recommended_next_steps.append("Toggle Bluetooth ON in Windows Settings (Settings > Bluetooth & devices).")
            return BluetoothDiagnosis(
                problem_category="radio_off",
                summary="Bluetooth radio is currently switched off.",
                observed_evidence=observed_evidence,
                interpretation=interpretation,
                confidence=0.85,
                recommended_next_steps=recommended_next_steps,
                repair_available=False,
                tool_results=tool_results,
            )

        # Scenario E: Healthy / General
        interpretation.append("Bluetooth radio controller and background services are active and operational.")
        if dev_count > 0:
            interpretation.append(f"{dev_count} known paired Bluetooth device(s) registered.")
        recommended_next_steps.append("Subsystem is healthy. If a specific peripheral fails, verify battery and pairing mode.")

        return BluetoothDiagnosis(
            problem_category="general_bluetooth",
            summary="Bluetooth subsystem is operational (Radio: ON, Service: RUNNING).",
            observed_evidence=observed_evidence,
            interpretation=interpretation,
            confidence=0.9,
            recommended_next_steps=recommended_next_steps,
            repair_available=False,
            tool_results=tool_results,
        )
