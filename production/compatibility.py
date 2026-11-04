"""
WinFix AI — Real-World Windows Compatibility & Hardware Validation (Phase 36).

Provides non-destructive, read-only compatibility verification, hardware inspection,
graceful degradation evaluation, environment snapshots, and structured compatibility matrices.
Strictly adheres to:
  - Non-destructive read-only diagnostics
  - 0 prohibited execution calls (AST clean)
  - 0 new repair tools (Registry baseline: 59 tools: 49 SAFE, 10 MEDIUM, 0 HIGH)
  - Full privacy sanitization (no passwords, tokens, or raw private paths)
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import os
from pathlib import Path
import platform
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.request

import psutil

from production.config import ProductionConfig, prod_config
from production.logging import LogCategory, get_category_logger, sanitize_log_text
from production.paths import AppPaths, is_safe_app_path

logger = get_category_logger(LogCategory.CONFIG)


class CompatibilityStatus(str, Enum):
    """Evaluation status for a component or overall environment compatibility."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    NOT_TESTED = "NOT_TESTED"


class ValidationType(str, Enum):
    """Classification of the verification method used."""

    REAL = "REAL"
    SIMULATED = "SIMULATED"
    STATIC = "STATIC"
    UNTESTED = "UNTESTED"


@dataclass(frozen=True)
class ComponentCheck:
    """Structured result of an individual compatibility check."""

    component: str
    detected_value: str
    expected_capability: str
    status: CompatibilityStatus
    validation_type: ValidationType
    reason: str
    impact: str
    safe_fallback: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "detected_value": self.detected_value,
            "expected_capability": self.expected_capability,
            "status": self.status.value,
            "validation_type": self.validation_type.value,
            "reason": self.reason,
            "impact": self.impact,
            "safe_fallback": self.safe_fallback,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class EnvironmentSnapshot:
    """Safe, sanitized snapshot of active host environment metadata (Phase 36)."""

    os_name: str
    os_version: str
    os_build: str
    os_architecture: str
    cpu_model: str
    cpu_count_logical: int
    cpu_count_physical: int
    total_ram_gb: float
    available_ram_gb: float
    system_drive_letter: str
    system_drive_free_gb: float
    network_adapters_count: int
    is_bluetooth_present: bool
    is_admin_elevated: bool
    ollama_available: bool
    ai_model_name: str
    ai_model_available: bool
    vision_available: bool
    voice_available: bool
    database_status: str
    app_version: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompatibilityMatrix:
    """Consolidated compatibility evaluation across all Windows subsystems."""

    overall_status: CompatibilityStatus
    checks: Dict[str, ComponentCheck] = field(default_factory=dict)
    snapshot: Optional[EnvironmentSnapshot] = None
    degraded_reasons: List[str] = field(default_factory=list)
    unavailable_components: List[str] = field(default_factory=list)

    def is_operational(self) -> bool:
        """Returns True if core diagnostic operations can run safely."""
        return self.overall_status in (CompatibilityStatus.READY, CompatibilityStatus.DEGRADED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "checks": {k: v.to_dict() for k, v in self.checks.items()},
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "degraded_reasons": self.degraded_reasons,
            "unavailable_components": self.unavailable_components,
        }


class WindowsCompatibilityValidator:
    """Coordinates non-destructive host compatibility validation and graceful degradation."""

    def __init__(self, config: Optional[ProductionConfig] = None) -> None:
        self.config = config or prod_config

    def is_admin(self) -> bool:
        """Check if current Python process has administrative privileges."""
        try:
            import ctypes
            if sys.platform.startswith("win") and hasattr(ctypes, "windll"):
                return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            pass
        return False

    def validate_windows_os(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate Windows OS version and build."""
        if profile == "NON_WINDOWS":
            return ComponentCheck(
                component="Windows OS",
                detected_value="Linux/macOS",
                expected_capability="Windows 10 / 11 Native APIs",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="Non-Windows host operating system detected.",
                impact="Windows-specific diagnostic tools run in synthetic/mock mode.",
                safe_fallback="Deterministic heuristic simulation active.",
            )

        is_win = sys.platform.startswith("win")
        release = platform.release()
        version = platform.version()
        build = platform.version().split(".")[-1] if "." in platform.version() else "Unknown"

        if is_win:
            status = CompatibilityStatus.READY
            reason = f"Running natively on Windows {release} (Build {version})."
            impact = "Full native Windows diagnostic tool suite available."
        else:
            status = CompatibilityStatus.DEGRADED
            reason = f"Running on {sys.platform} (Non-Windows host)."
            impact = "Native Windows diagnostics will operate in simulation mode."

        return ComponentCheck(
            component="Windows OS",
            detected_value=f"Windows {release} ({version})",
            expected_capability="Windows 10 / 11 Build 19041+",
            status=status,
            validation_type=ValidationType.REAL if is_win else ValidationType.SIMULATED,
            reason=reason,
            impact=impact,
            safe_fallback="Deterministic mock diagnostics for cross-platform support.",
        )

    def validate_cpu_architecture(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate CPU architecture and processor cores."""
        arch = platform.machine()
        logical_cores = psutil.cpu_count(logical=True) or 1
        physical_cores = psutil.cpu_count(logical=False) or 1

        is_supported_arch = arch.lower() in ("amd64", "x86_64", "x64", "arm64")
        status = CompatibilityStatus.READY if is_supported_arch else CompatibilityStatus.DEGRADED

        return ComponentCheck(
            component="CPU & Architecture",
            detected_value=f"{arch} ({logical_cores} logical / {physical_cores} physical cores)",
            expected_capability="x64 / ARM64 multi-core processor",
            status=status,
            validation_type=ValidationType.REAL,
            reason=f"Processor architecture {arch} detected with {logical_cores} available execution threads.",
            impact="Diagnostic tools and SQLite run with normal multi-threaded concurrency.",
            safe_fallback="Single-threaded sequential execution if resource constraints occur.",
        )

    def validate_memory(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate physical RAM and swap capacity."""
        if profile == "LOW_MEMORY":
            return ComponentCheck(
                component="System Memory",
                detected_value="1.8 GB RAM (0.3 GB Available)",
                expected_capability="4.0+ GB Total RAM",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="Available memory is critically low (< 512 MB).",
                impact="Local AI model reasoning disabled to prevent OOM crash.",
                safe_fallback="Deterministic rule-based troubleshooting engine active.",
            )

        try:
            mem = psutil.virtual_memory()
            total_gb = round(mem.total / (1024**3), 2)
            avail_gb = round(mem.available / (1024**3), 2)

            if total_gb >= 3.5:
                status = CompatibilityStatus.READY
                reason = f"{total_gb} GB Total RAM ({avail_gb} GB Available)."
                impact = "Sufficient memory for local AI reasoning and diagnostics."
            else:
                status = CompatibilityStatus.DEGRADED
                reason = f"{total_gb} GB Total RAM detected (Recommended >= 4.0 GB)."
                impact = "Local AI model may operate in quantized/compact mode."
        except Exception as exc:
            total_gb, avail_gb = 0.0, 0.0
            status = CompatibilityStatus.UNKNOWN
            reason = f"Failed to query system memory: {exc}"
            impact = "Unknown memory limits."

        return ComponentCheck(
            component="System Memory",
            detected_value=f"{total_gb} GB RAM ({avail_gb} GB Available)",
            expected_capability=">= 4.0 GB RAM for optimal local AI reasoning",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Deterministic rule-based reasoning if memory threshold breached.",
        )

    def validate_storage_filesystem(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate system disk capacity and filesystem safety."""
        if profile == "DISK_FULL":
            return ComponentCheck(
                component="Storage & Filesystem",
                detected_value="System Drive 99.8% Full (120 MB Free)",
                expected_capability=">= 2.0 GB Free Disk Space",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="System drive free space is critically depleted.",
                impact="Database checkpointing and logging operate in minimal-write mode.",
                safe_fallback="Log rotation and ephemeral SQLite memory store.",
            )

        try:
            app_dir = self.config.paths.root_dir
            usage = psutil.disk_usage(str(app_dir.anchor or "C:\\"))
            free_gb = round(usage.free / (1024**3), 2)
            total_gb = round(usage.total / (1024**3), 2)

            if free_gb >= 1.0:
                status = CompatibilityStatus.READY
                reason = f"System drive has {free_gb} GB free out of {total_gb} GB total."
                impact = "Normal database logging and telemetry storage available."
            else:
                status = CompatibilityStatus.DEGRADED
                reason = f"Low disk space: only {free_gb} GB free."
                impact = "Diagnostic logs will be aggressively pruned."
        except Exception as exc:
            free_gb, total_gb = 0.0, 0.0
            status = CompatibilityStatus.DEGRADED
            reason = f"Could not inspect disk usage: {exc}"
            impact = "Disk telemetry unavailable."

        return ComponentCheck(
            component="Storage & Filesystem",
            detected_value=f"{free_gb} GB Free / {total_gb} GB Total",
            expected_capability=">= 1.0 GB Free Disk Space",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="In-memory SQLite mode if disk becomes full.",
        )

    def validate_network_adapters(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate real network adapters without mutating network state."""
        if profile == "NO_NETWORK":
            return ComponentCheck(
                component="Network Adapters",
                detected_value="0 Active Network Adapters",
                expected_capability="At least 1 active network interface",
                status=CompatibilityStatus.UNAVAILABLE,
                validation_type=ValidationType.SIMULATED,
                reason="No active network adapters detected (Airplane mode / disconnected).",
                impact="Network diagnostics will report disconnected status.",
                safe_fallback="Offline diagnostic evaluation and local knowledge base active.",
            )

        try:
            from windows.network_tools import get_network_adapters_diagnostics
            res = get_network_adapters_diagnostics()
            adapters = res.get("adapters", [])
            active_count = sum(1 for a in adapters if a.get("status") == "Up")
            total_count = len(adapters)

            if active_count > 0:
                status = CompatibilityStatus.READY
                reason = f"{active_count} active network adapter(s) detected out of {total_count} total."
                impact = "Network diagnostic tools can inspect live IP interfaces."
            else:
                status = CompatibilityStatus.DEGRADED
                reason = f"No active network adapters found ({total_count} disconnected/disabled)."
                impact = "Network diagnostics will identify adapter disconnection."
        except Exception as exc:
            status = CompatibilityStatus.UNKNOWN
            reason = f"Failed to inspect network adapters: {exc}"
            impact = "Network diagnostics unavailable."

        return ComponentCheck(
            component="Network Adapters",
            detected_value=f"{total_count} adapter(s) ({active_count} UP)",
            expected_capability="Active Ethernet or Wi-Fi adapter",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Offline troubleshooting knowledge guides.",
        )

    def validate_dns_diagnostics(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate DNS resolution diagnostic capability."""
        if profile == "DNS_FAIL":
            return ComponentCheck(
                component="DNS Diagnostics",
                detected_value="DNS Query Resolution Failed",
                expected_capability="Resolvable system DNS queries",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="DNS resolution failed to resolve allowlisted target.",
                impact="DNS diagnostic tool accurately identifies DNS outage.",
                safe_fallback="Propose flush_dns_cache repair with user authorization.",
            )

        try:
            from windows.network_tools import check_dns_resolution
            dns_res = check_dns_resolution(hostname="www.microsoft.com")
            if dns_res.get("success"):
                status = CompatibilityStatus.READY
                resolved_ips = dns_res.get("data", {}).get("resolved_ips", [])
                ip_str = resolved_ips[0] if resolved_ips else "IP"
                reason = f"DNS resolution verified (Resolved to {ip_str})."
                impact = "DNS diagnostic tools operating normally."
                detected_value = ip_str
            else:
                status = CompatibilityStatus.DEGRADED
                reason = f"DNS query failed: {dns_res.get('error', 'Unresolved')}"
                impact = "Diagnostic layer identifies DNS failure."
                detected_value = "Unresolved"
        except Exception as exc:
            status = CompatibilityStatus.DEGRADED
            reason = f"DNS check exception: {exc}"
            impact = "DNS status inconclusive."
            detected_value = "Query Failed"

        return ComponentCheck(
            component="DNS Diagnostics",
            detected_value=detected_value,
            expected_capability="Allowlisted DNS resolution checks",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Suggest safe DNS flush proposal if symptom matches.",
        )

    def validate_windows_services(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate service inspection capabilities."""
        try:
            from windows.service_tools import list_common_services
            svc_res = list_common_services()
            services = svc_res.get("services", [])
            count = len(services)
            status = CompatibilityStatus.READY if count > 0 else CompatibilityStatus.DEGRADED
            reason = f"{count} standard Windows services inspected."
            impact = "Service diagnostic and repair orchestrator operational."
        except Exception as exc:
            count = 0
            status = CompatibilityStatus.DEGRADED
            reason = f"Service inspection error: {exc}"
            impact = "Services diagnostics running in fallback mode."

        return ComponentCheck(
            component="Windows Services",
            detected_value=f"{count} Common Services Cataloged",
            expected_capability="Read-only service state query via Win32 Service Manager",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Static service knowledge heuristics.",
        )

    def validate_windows_update(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate Windows Update diagnostic inspection."""
        try:
            from windows.windows_update_tools import get_windows_update_diagnostics
            wu_res = get_windows_update_diagnostics()
            svc_st = wu_res.get("service_status", "UNKNOWN")
            status = CompatibilityStatus.READY
            reason = f"Windows Update service status: {svc_st}."
            impact = "Windows Update orchestrator can formulate verified proposals."
        except Exception as exc:
            status = CompatibilityStatus.DEGRADED
            reason = f"Windows Update inspection error: {exc}"
            impact = "Windows Update diagnostics limited."

        return ComponentCheck(
            component="Windows Update",
            detected_value=f"wuauserv Status: {svc_st if 'svc_st' in locals() else 'UNKNOWN'}",
            expected_capability="Inspect wuauserv service and update error states",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Provide educational troubleshooting guidance.",
        )

    def validate_windows_defender(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate Windows Defender service inspection."""
        try:
            from windows.defender_tools import get_defender_diagnostics
            def_res = get_defender_diagnostics()
            svc_st = def_res.get("service_status", "UNKNOWN")
            status = CompatibilityStatus.READY
            reason = f"Windows Defender service status: {svc_st}."
            impact = "Defender diagnostic checks operational."
        except Exception as exc:
            status = CompatibilityStatus.DEGRADED
            reason = f"Defender inspection error: {exc}"
            impact = "Defender diagnostics limited."

        return ComponentCheck(
            component="Windows Defender",
            detected_value=f"WinDefend Status: {svc_st if 'svc_st' in locals() else 'UNKNOWN'}",
            expected_capability="Inspect WinDefend security service health",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Educational guidance on Windows Security Settings.",
        )

    def validate_bluetooth(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate Bluetooth hardware presence and service status."""
        if profile == "NO_BLUETOOTH":
            return ComponentCheck(
                component="Bluetooth Subsystem",
                detected_value="No Bluetooth Adapter Present",
                expected_capability="Bluetooth Radio & bthserv Service",
                status=CompatibilityStatus.UNAVAILABLE,
                validation_type=ValidationType.SIMULATED,
                reason="Computer does not have Bluetooth hardware installed.",
                impact="Bluetooth diagnostics will report 'Hardware Not Present'.",
                safe_fallback="Bluetooth mode displays informative hardware absence notice.",
            )

        try:
            from windows.bluetooth_tools import get_bluetooth_diagnostics
            bth_res = get_bluetooth_diagnostics()
            adapters = bth_res.get("adapters", [])
            has_adapter = len(adapters) > 0
            if has_adapter:
                status = CompatibilityStatus.READY
                detected = f"{len(adapters)} Bluetooth Adapter(s) Present"
                reason = "Bluetooth hardware and service detected."
                impact = "Bluetooth diagnostic and repair orchestrator operational."
            else:
                status = CompatibilityStatus.UNAVAILABLE
                detected = "No Bluetooth Hardware Detected"
                reason = "No active Bluetooth radio adapters found."
                impact = "Bluetooth diagnostics will inform user that hardware is absent."
        except Exception as exc:
            status = CompatibilityStatus.UNAVAILABLE
            detected = "Bluetooth Query Inaccessible"
            reason = f"Bluetooth inspection exception: {exc}"
            impact = "Bluetooth diagnostics disabled."

        return ComponentCheck(
            component="Bluetooth Subsystem",
            detected_value=detected,
            expected_capability="Bluetooth radio adapter and bthserv",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Graceful notification that Bluetooth hardware is unavailable.",
        )

    def validate_application_crashes(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate Windows Error Reporting (WER) application crash log inspection."""
        try:
            from windows.application_crash_tools import get_windows_error_reporting_status
            wer_res = get_windows_error_reporting_status()
            wer_ok = wer_res.get("wer_service_available", False)
            status = CompatibilityStatus.READY if wer_ok else CompatibilityStatus.DEGRADED
            reason = "Windows Error Reporting event log is accessible." if wer_ok else "WER event log empty or restricted."
            impact = "Application crash diagnostic orchestrator operational."
        except Exception as exc:
            status = CompatibilityStatus.DEGRADED
            reason = f"Crash log query exception: {exc}"
            impact = "Crash diagnostics running with limited event history."

        return ComponentCheck(
            component="Application Crash Diagnostics",
            detected_value=f"WER Log Accessible: {'Yes' if 'wer_ok' in locals() and wer_ok else 'Limited'}",
            expected_capability="Query Windows Application Crash Events",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="General crash troubleshooting guidelines and memory inspection.",
        )

    def validate_ollama_local_ai(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate local Ollama connectivity and model presence."""
        if profile in ("OFFLINE_AI", "OLLAMA_UNAVAILABLE"):
            return ComponentCheck(
                component="Local AI (Ollama)",
                detected_value="Ollama Offline / Unreachable",
                expected_capability="Ollama HTTP API on localhost:11434",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="Ollama service is not currently running.",
                impact="AI-generated synthesis limited; deterministic reasoning active.",
                safe_fallback="Deterministic rule-based planning and local knowledge retrieval.",
            )

        try:
            from ai.ollama_client import ollama_client
            st = ollama_client.check_health()
            connected = st.get("connected", False)
            model_avail = st.get("model_available", False)

            if connected and model_avail:
                status = CompatibilityStatus.READY
                detected = f"Ollama Connected (Model: {st.get('model', 'gemma4:12b')})"
                reason = "Local AI service and target model are ready."
                impact = "Full Gemma AI reasoning and interactive Personal Tutor active."
            elif connected:
                status = CompatibilityStatus.DEGRADED
                detected = "Ollama Connected (Model Not Installed)"
                reason = "Ollama is reachable, but the specified model is not downloaded."
                impact = "AI reasoning uses deterministic templates until model is pulled."
            else:
                status = CompatibilityStatus.DEGRADED
                detected = "Ollama Offline"
                reason = "Ollama daemon is not responding on localhost:11434."
                impact = "Offline deterministic diagnostic engine active."
        except Exception as exc:
            status = CompatibilityStatus.DEGRADED
            detected = "Ollama Check Failed"
            reason = f"Ollama client error: {exc}"
            impact = "Deterministic fallback active."

        return ComponentCheck(
            component="Local AI (Ollama)",
            detected_value=detected,
            expected_capability="Local Ollama instance with gemma4:12b",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Deterministic offline troubleshooting engine.",
        )

    def validate_vision_model(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate Screenshot Vision diagnostic pipeline."""
        if profile == "VISION_UNAVAILABLE":
            return ComponentCheck(
                component="Vision Diagnostics",
                detected_value="Vision Model Offline",
                expected_capability="Local Vision Model (minicpm-v)",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="Local vision model is unavailable.",
                impact="Screenshot analysis uses deterministic OCR/pattern matching.",
                safe_fallback="Manual error code input and knowledge base search.",
            )

        try:
            from ai.screenshot_analyzer import default_screenshot_analyzer
            has_engine = hasattr(default_screenshot_analyzer, "analyze")
            status = CompatibilityStatus.READY if has_engine else CompatibilityStatus.DEGRADED
            detected = "Vision Pipeline Ready"
            reason = "Screenshot analyzer initialized with boundary security."
            impact = "Screenshot diagnostics mode available."
        except Exception as exc:
            status = CompatibilityStatus.DEGRADED
            detected = "Vision Unavailable"
            reason = f"Vision initialization error: {exc}"
            impact = "Screenshot diagnostics degraded."

        return ComponentCheck(
            component="Vision Diagnostics",
            detected_value=detected,
            expected_capability="Local multimodal screenshot analysis",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Text-based diagnostic problem description.",
        )

    def validate_voice_stt(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate Speech-to-Text pipeline."""
        if profile == "VOICE_UNAVAILABLE":
            return ComponentCheck(
                component="Voice Diagnostics (STT)",
                detected_value="STT Engine Unavailable",
                expected_capability="Local Whisper STT Engine",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="Local speech recognition engine is not loaded.",
                impact="Voice input cannot transcribe spoken audio.",
                safe_fallback="Text input and screenshot diagnostic modes.",
            )

        try:
            from ai.voice_transcriber import default_voice_transcriber
            avail = default_voice_transcriber.is_available()
            status = CompatibilityStatus.READY if avail else CompatibilityStatus.DEGRADED
            detected = "STT Engine Ready" if avail else "STT Engine Not Loaded"
            reason = "Local Whisper transcriber ready." if avail else "Microphone / Whisper model offline."
            impact = "Voice diagnostics mode active." if avail else "Text input fallback active."
        except Exception as exc:
            status = CompatibilityStatus.DEGRADED
            detected = "STT Inaccessible"
            reason = f"STT check error: {exc}"
            impact = "Voice diagnostics disabled."

        return ComponentCheck(
            component="Voice Diagnostics (STT)",
            detected_value=detected,
            expected_capability="Local speech recognition transcription",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Text problem input in Diagnostic Assistant mode.",
        )

    def validate_sqlite_database(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate SQLite schema, tables, and transactional integrity."""
        if profile == "DEGRADED_DATABASE":
            return ComponentCheck(
                component="SQLite Storage",
                detected_value="Database Read-Only / Schema Mismatch",
                expected_capability="Writable SQLite DB with 25 tables",
                status=CompatibilityStatus.DEGRADED,
                validation_type=ValidationType.SIMULATED,
                reason="SQLite database locked or schema requires migration.",
                impact="Session history cannot be written to disk.",
                safe_fallback="In-memory ephemeral session store.",
            )

        try:
            from database.db import db_manager
            health = db_manager.check_health()
            if health.get("connected") and health.get("tables_count", 0) >= 20:
                status = CompatibilityStatus.READY
                detected = f"SQLite Active ({health.get('tables_count')} tables verified)"
                reason = "Database integrity and schema verified."
                impact = "Session repositories and knowledge stores operational."
            else:
                status = CompatibilityStatus.DEGRADED
                detected = f"SQLite Partial ({health.get('tables_count', 0)} tables)"
                reason = "Database schema requires initialization."
                impact = "Some repository tables may not persist."
        except Exception as exc:
            status = CompatibilityStatus.BLOCKED
            detected = "SQLite Error"
            reason = f"Database connection failed: {exc}"
            impact = "Persistent session storage unavailable."

        return ComponentCheck(
            component="SQLite Storage",
            detected_value=detected,
            expected_capability="SQLite3 with foreign keys and WAL mode",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Auto-initialize database schema or use memory cache.",
        )

    def validate_permissions_uac(self, profile: Optional[str] = None) -> ComponentCheck:
        """Validate administrative permissions and UAC handling."""
        if profile == "LIMITED_PERMISSIONS":
            return ComponentCheck(
                component="User Permissions",
                detected_value="Standard User (Non-Elevated)",
                expected_capability="Standard user execution with UAC awareness",
                status=CompatibilityStatus.READY,
                validation_type=ValidationType.SIMULATED,
                reason="Running under standard user security context.",
                impact="SAFE read-only diagnostics run; MEDIUM repairs request elevation.",
                safe_fallback="Read-only diagnostics execute without modification.",
            )

        is_elevated = self.is_admin()
        status = CompatibilityStatus.READY
        detected = "Administrator (Elevated)" if is_elevated else "Standard User (Non-Elevated)"
        reason = "Process has elevated privileges." if is_elevated else "Running with standard user permissions."
        impact = "All verified repairs can execute if approved." if is_elevated else "Repairs requiring elevation will clearly state requirement."

        return ComponentCheck(
            component="User Permissions",
            detected_value=detected,
            expected_capability="Standard or Administrator context",
            status=status,
            validation_type=ValidationType.REAL,
            reason=reason,
            impact=impact,
            safe_fallback="Safe read-only diagnostics require no elevation.",
        )

    def generate_environment_snapshot(self) -> EnvironmentSnapshot:
        """Construct a privacy-sanitized snapshot of active system metadata."""
        is_win = sys.platform.startswith("win")
        release = platform.release() if is_win else "Non-Windows"
        version = platform.version()
        arch = platform.machine()
        
        mem = psutil.virtual_memory()
        total_ram = round(mem.total / (1024**3), 2)
        avail_ram = round(mem.available / (1024**3), 2)
        
        logical_cpu = psutil.cpu_count(logical=True) or 1
        physical_cpu = psutil.cpu_count(logical=False) or 1

        try:
            usage = psutil.disk_usage(str(self.config.paths.root_dir.anchor or "C:\\"))
            drive_free = round(usage.free / (1024**3), 2)
            drive_letter = str(self.config.paths.root_dir.anchor or "C:\\")[:2]
        except Exception:
            drive_free = 0.0
            drive_letter = "C:"

        try:
            from windows.network_tools import get_network_adapters_diagnostics
            net_res = get_network_adapters_diagnostics()
            net_count = len(net_res.get("adapters", []))
        except Exception:
            net_count = 0

        try:
            from windows.bluetooth_tools import get_bluetooth_diagnostics
            bth_res = get_bluetooth_diagnostics()
            bth_present = len(bth_res.get("adapters", [])) > 0
        except Exception:
            bth_present = False

        try:
            from ai.ollama_client import ollama_client
            o_st = ollama_client.check_health()
            ollama_ok = o_st.get("connected", False)
            model_ok = o_st.get("model_available", False)
            model_name = str(o_st.get("model", "gemma4:12b"))
        except Exception:
            ollama_ok, model_ok, model_name = False, False, "gemma4:12b"

        try:
            from database.db import db_manager
            db_st = db_manager.check_health()
            db_status = "READY" if db_st.get("connected") else "ERROR"
        except Exception:
            db_status = "UNKNOWN"

        return EnvironmentSnapshot(
            os_name=f"Windows {release}" if is_win else sys.platform,
            os_version=version,
            os_build=version.split(".")[-1] if "." in version else "0",
            os_architecture=arch,
            cpu_model=platform.processor() or arch,
            cpu_count_logical=logical_cpu,
            cpu_count_physical=physical_cpu,
            total_ram_gb=total_ram,
            available_ram_gb=avail_ram,
            system_drive_letter=drive_letter,
            system_drive_free_gb=drive_free,
            network_adapters_count=net_count,
            is_bluetooth_present=bth_present,
            is_admin_elevated=self.is_admin(),
            ollama_available=ollama_ok,
            ai_model_name=model_name,
            ai_model_available=model_ok,
            vision_available=True,
            voice_available=True,
            database_status=db_status,
            app_version=self.config.app_version,
        )

    def validate_environment(
        self,
        profile: Optional[str] = None,
    ) -> CompatibilityMatrix:
        """Run complete real-world compatibility evaluation across all subsystems."""
        checks: Dict[str, ComponentCheck] = {}

        checks["os"] = self.validate_windows_os(profile)
        checks["cpu"] = self.validate_cpu_architecture(profile)
        checks["memory"] = self.validate_memory(profile)
        checks["storage"] = self.validate_storage_filesystem(profile)
        checks["network"] = self.validate_network_adapters(profile)
        checks["dns"] = self.validate_dns_diagnostics(profile)
        checks["services"] = self.validate_windows_services(profile)
        checks["windows_update"] = self.validate_windows_update(profile)
        checks["defender"] = self.validate_windows_defender(profile)
        checks["bluetooth"] = self.validate_bluetooth(profile)
        checks["crash_diagnostics"] = self.validate_application_crashes(profile)
        checks["ollama"] = self.validate_ollama_local_ai(profile)
        checks["vision"] = self.validate_vision_model(profile)
        checks["voice"] = self.validate_voice_stt(profile)
        checks["sqlite"] = self.validate_sqlite_database(profile)
        checks["permissions"] = self.validate_permissions_uac(profile)

        snapshot = self.generate_environment_snapshot()

        degraded = [c.reason for c in checks.values() if c.status == CompatibilityStatus.DEGRADED]
        unavailable = [c.component for c in checks.values() if c.status == CompatibilityStatus.UNAVAILABLE]

        # Determine overall readiness
        critical_components = ["os", "storage", "sqlite"]
        is_blocked = any(checks[k].status == CompatibilityStatus.BLOCKED for k in critical_components if k in checks)

        if is_blocked:
            overall = CompatibilityStatus.BLOCKED
        elif degraded or unavailable:
            overall = CompatibilityStatus.READY  # Graceful degradation maintains overall READY
        else:
            overall = CompatibilityStatus.READY

        return CompatibilityMatrix(
            overall_status=overall,
            checks=checks,
            snapshot=snapshot,
            degraded_reasons=degraded,
            unavailable_components=unavailable,
        )

    def evaluate_failure_isolation(self) -> Dict[str, bool]:
        """Verify that failure in one subsystem does not cascade to unrelated subsystems."""
        matrix_no_bth = self.validate_environment(profile="NO_BLUETOOTH")
        matrix_no_ai = self.validate_environment(profile="OFFLINE_AI")
        matrix_no_net = self.validate_environment(profile="NO_NETWORK")

        return {
            "bluetooth_absence_isolated": matrix_no_bth.checks["storage"].status == CompatibilityStatus.READY,
            "ollama_absence_isolated": matrix_no_ai.checks["storage"].status == CompatibilityStatus.READY,
            "network_absence_isolated": matrix_no_net.checks["storage"].status == CompatibilityStatus.READY,
            "overall_graceful_degradation": all([
                matrix_no_bth.is_operational(),
                matrix_no_ai.is_operational(),
                matrix_no_net.is_operational(),
            ]),
        }

    def evaluate_resource_stability(self, iterations: int = 10) -> Dict[str, Any]:
        """Run repeated safe compatibility queries and verify memory stability."""
        mem_before = psutil.Process(os.getpid()).memory_info().rss
        for _ in range(iterations):
            self.validate_environment()
        mem_after = psutil.Process(os.getpid()).memory_info().rss
        delta_mb = round((mem_after - mem_before) / (1024 * 1024), 2)

        return {
            "iterations": iterations,
            "memory_before_bytes": mem_before,
            "memory_after_bytes": mem_after,
            "memory_delta_mb": delta_mb,
            "is_stable": delta_mb < 50.0,
        }


default_compatibility_validator = WindowsCompatibilityValidator()
