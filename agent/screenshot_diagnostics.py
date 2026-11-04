"""Screenshot diagnostic mapping and tool resolution module for WinFix AI.

Maps visual observations, visible error codes, Windows Event IDs, and application
names to approved, read-only diagnostic tools registered in ToolRegistry.
Ensures no repair tools or arbitrary execution strings are ever suggested directly
from screenshot analysis.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set

from agent.tool_registry import ToolRegistry, default_tool_registry
from input.screenshot_models import (
    ScreenshotDiagnosticHint,
    ScreenshotEvidence,
    ScreenshotObservation,
)

logger = logging.getLogger(__name__)


# Specific error code mapping to diagnostic tools
ERROR_CODE_DIAGNOSTIC_MAP: Dict[str, List[Dict[str, Any]]] = {
    # Windows Update error codes
    "0x80070422": [
        {"tool": "get_windows_update_health", "reason": "Error 0x80070422 indicates Windows Update service is disabled."},
        {"tool": "get_windows_update_service_status", "reason": "Inspect active status of wuauserv service."},
    ],
    "0x80240020": [
        {"tool": "get_windows_update_diagnostics", "reason": "Error 0x80240020 indicates automatic update failure."},
    ],
    "0x80070002": [
        {"tool": "get_windows_update_health", "reason": "Error 0x80070002 (FILE_NOT_FOUND) often indicates update cache corruption."},
        {"tool": "get_storage_diagnostics", "reason": "Check drive health and file system availability."},
    ],
    "0x80070005": [
        {"tool": "get_windows_update_health", "reason": "Error 0x80070005 (ACCESS_DENIED) indicates permission or service lockout."},
        {"tool": "get_defender_diagnostics", "reason": "Check if Windows Defender or security policy blocked the action."},
    ],
    "0x8024402c": [
        {"tool": "check_internet_connectivity", "reason": "Error 0x8024402C indicates Windows Update server network/DNS resolution failure."},
        {"tool": "get_network_adapters_diagnostics", "reason": "Inspect network adapter and gateway status."},
    ],
    # Windows Defender error codes
    "0x8050800c": [
        {"tool": "get_defender_diagnostics", "reason": "Error 0x8050800C indicates Defender scan failed or was aborted."},
        {"tool": "get_defender_service_status", "reason": "Inspect WinDefend service state."},
    ],
    "0x800106ba": [
        {"tool": "get_defender_service_status", "reason": "Error 0x800106BA indicates Defender service failed to start."},
    ],
    "0x800704ec": [
        {"tool": "get_defender_diagnostics", "reason": "Error 0x800704EC indicates Defender blocked by policy or disabled."},
    ],
    # Application crash error codes
    "0xc0000005": [
        {"tool": "get_recent_application_crashes", "reason": "Exception 0xC0000005 is an Access Violation crash in user-mode application."},
        {"tool": "get_application_crash_summary", "reason": "Summarize recent application crash telemetry."},
    ],
    "0xc0000409": [
        {"tool": "get_recent_application_crashes", "reason": "Exception 0xC0000409 indicates a stack buffer overrun crash."},
    ],
}

# Event ID mapping to diagnostic tools
EVENT_ID_DIAGNOSTIC_MAP: Dict[str, List[Dict[str, Any]]] = {
    "1000": [
        {"tool": "get_recent_application_crashes", "reason": "Event ID 1000 records application fault/crash details."},
        {"tool": "get_application_crash_summary", "reason": "Inspect crash frequency and faulting modules."},
    ],
    "1001": [
        {"tool": "get_recent_application_crashes", "reason": "Event ID 1001 records Windows Error Reporting telemetry."},
    ],
    "1002": [
        {"tool": "get_recent_application_crashes", "reason": "Event ID 1002 indicates application hang."},
    ],
    "7000": [
        {"tool": "get_service_status", "reason": "Event ID 7000 records service start failure."},
    ],
    "7009": [
        {"tool": "get_service_status", "reason": "Event ID 7009 records service start timeout."},
    ],
    "7034": [
        {"tool": "get_service_status", "reason": "Event ID 7034 records unexpected service termination."},
    ],
    "19": [
        {"tool": "get_windows_update_diagnostics", "reason": "Event ID 19 indicates Windows Update installation failure."},
    ],
    "20": [
        {"tool": "get_windows_update_diagnostics", "reason": "Event ID 20 indicates Windows Update general failure."},
    ],
}


class ScreenshotDiagnosticMapper:
    """Resolves visual observations and extracted markers to validated diagnostic tools."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or default_tool_registry

    def map_evidence_to_hints(
        self,
        evidence: ScreenshotEvidence,
        suggested_areas: Optional[List[str]] = None,
        user_context: Optional[str] = None,
    ) -> List[ScreenshotDiagnosticHint]:
        """Resolve evidence markers into registered read-only diagnostic tool hints.

        Args:
            evidence: Extracted screenshot evidence.
            suggested_areas: Optional broad diagnostic categories from vision model.
            user_context: Optional user inquiry or problem description.

        Returns:
            List of validated ScreenshotDiagnosticHint objects.
        """
        hints: List[ScreenshotDiagnosticHint] = []
        seen_tools: Set[str] = set()

        # 1. Map explicit detected error codes
        for err_code in evidence.detected_error_codes:
            code_normalized = err_code.strip().lower()
            # Match exact or case-insensitive
            for map_code, tool_specs in ERROR_CODE_DIAGNOSTIC_MAP.items():
                if code_normalized == map_code.lower():
                    for spec in tool_specs:
                        t_name = spec["tool"]
                        if t_name not in seen_tools:
                            hint = self._build_validated_hint(t_name, spec["reason"])
                            if hint:
                                hints.append(hint)
                                seen_tools.add(t_name)

        # 2. Map explicit detected event IDs
        for ev_id in evidence.detected_event_ids:
            ev_clean = ev_id.strip()
            if ev_clean in EVENT_ID_DIAGNOSTIC_MAP:
                for spec in EVENT_ID_DIAGNOSTIC_MAP[ev_clean]:
                    t_name = spec["tool"]
                    if t_name not in seen_tools:
                        hint = self._build_validated_hint(t_name, spec["reason"])
                        if hint:
                            hints.append(hint)
                            seen_tools.add(t_name)

        # 3. Map application names and keywords in text/observations/user_context
        text_corpus = (
            f"{evidence.raw_text_extracted} "
            + " ".join(evidence.detected_applications)
            + " "
            + " ".join(o.text for o in evidence.observations)
            + " "
            + (str(user_context) if user_context else "")
        ).lower()

        # Keyword mapping rules
        keyword_rules = [
            (
                ["windows update", "update error", "wuauserv", "downloading updates", "installing updates"],
                "get_windows_update_health",
                "Visible reference or inquiry about Windows Update indicates checking update service health.",
            ),
            (
                ["windows update", "wuauserv"],
                "get_windows_update_service_status",
                "Inspect active state of Windows Update service.",
            ),
            (
                ["windows defender", "windefend", "virus & threat", "antivirus", "threat protection"],
                "get_defender_diagnostics",
                "Visible reference or inquiry about Windows Defender or Antivirus protection.",
            ),
            (
                ["dns", "resolv", "server not found", "no internet", "gateway", "disconnected", "wi-fi", "wifi", "ethernet", "network"],
                "check_internet_connectivity",
                "Network or connectivity context indicates verifying internet and DNS reachability.",
            ),
            (
                ["wifi", "wi-fi", "adapter", "network adapter", "ethernet"],
                "get_network_adapters_diagnostics",
                "Inspect network adapter state and configuration.",
            ),
            (
                ["dns cache", "dns error", "dns client"],
                "get_dns_client_config",
                "Inspect DNS client configuration and status.",
            ),
            (
                ["disk space", "low disk", "out of space", "drive full", "temporary files", "clean up"],
                "get_storage_diagnostics",
                "Visible storage or low disk warning indicates inspecting disk capacities.",
            ),
            (
                ["temp files", "temporary files", "temp folder"],
                "get_temp_storage_info",
                "Inspect temporary directory usage.",
            ),
            (
                ["has stopped working", "not responding", "crash", "appcrash", "exception", "faulting module"],
                "get_recent_application_crashes",
                "Visible application crash or hang dialog indicates reviewing recent event log crashes.",
            ),
            (
                ["bluetooth", "bthserv", "paired device", "bluetooth not available"],
                "get_bluetooth_diagnostics",
                "Visible Bluetooth dialog indicates inspecting Bluetooth radios and services.",
            ),
            (
                ["cpu", "high usage", "memory", "ram full", "freezing", "sluggish", "task manager"],
                "get_cpu_diagnostics",
                "Visible high resource consumption indicates inspecting CPU load.",
            ),
            (
                ["print spooler", "spoolsv", "printer error", "cannot print"],
                "get_printer_diagnostics",
                "Visible print error indicates inspecting printer devices and spooler status.",
            ),
            (
                ["battery", "charge", "power", "energy", "plugged", "discharging", "%"],
                "get_complete_system_info",
                "Visible battery level or power state indicates collecting complete system and hardware information.",
            ),
            (
                ["settings", "gear", "preferences", "system settings", "control panel"],
                "get_complete_system_info",
                "Visible Windows Settings dialog indicates collecting complete operating system and hardware status.",
            ),
            (
                ["device manager", "driver", "hardware", "specs", "processor", "system info"],
                "get_complete_system_info",
                "Visible hardware or device status indicates inspecting system environment and configuration.",
            ),
        ]

        def _matches_any_token(text: str, keywords: List[str]) -> bool:
            for kw in keywords:
                if " " in kw or len(kw) >= 5:
                    if kw in text:
                        return True
                else:
                    if re.search(rf"\b{re.escape(kw)}\b", text):
                        return True
            return False

        # Check if user inquiry or observations specifically target Bluetooth vs Wi-Fi
        uq_lower = (str(user_context) if user_context else "").lower()
        user_asks_bluetooth = _matches_any_token(uq_lower, [
            "bluetooth", "bthserv", "paired device", "bth", "bluetooth toggle", "turn on bluetooth",
            "bluetooth not working", "bluetooth is disable", "bluetooth is disabled", "bluetooth disabled", "bluetooth off"
        ])
        user_asks_wifi = _matches_any_token(uq_lower, [
            "wifi", "wi-fi", "wireless", "wlan", "network adapter", "ncpa.cpl",
            "no wifi", "wifi missing", "wifi is not shown", "not shown",
            "why the wifi", "where is wifi", "missing wifi", "no internet"
        ])

        is_quick_settings_panel = (
            ("quick settings" in text_corpus or "action center" in text_corpus or "quick panel" in text_corpus or "flyout" in text_corpus)
            or ("bluetooth" in text_corpus and ("airplane" in text_corpus or "night light" in text_corpus or "accessibility" in text_corpus or "studio effects" in text_corpus or "energy" in text_corpus or "26%" in text_corpus or "brightness" in text_corpus or "volume" in text_corpus))
            or ("airplane mode" in text_corpus and ("energy" in text_corpus or "night light" in text_corpus))
            or ("studio effects" in text_corpus and "accessibility" in text_corpus)
        )

        has_explicit_missing_wifi = any(p in text_corpus for p in [
            "wi-fi toggle is missing", "wifi toggle is missing", "wi-fi is missing", "wifi is missing",
            "missing wi-fi", "missing wifi", "wifi not found", "wi-fi not found", "wi-fi button is missing", "wifi button is missing"
        ])

        has_explicit_bluetooth_fault = any(p in text_corpus for p in [
            "bluetooth is disabled", "bluetooth is disable", "bluetooth disabled",
            "bluetooth off", "bluetooth not working", "bluetooth unavailable",
            "bluetooth greyed out", "bluetooth is off", "bluetooth error", "bthserv stopped"
        ])

        if user_asks_wifi and not user_asks_bluetooth:
            is_bluetooth_inquiry = False
            is_wifi_inquiry = True
        elif user_asks_bluetooth and not user_asks_wifi:
            is_bluetooth_inquiry = True
            is_wifi_inquiry = False
        else:
            if has_explicit_missing_wifi:
                is_wifi_inquiry = True
                is_bluetooth_inquiry = False
            elif has_explicit_bluetooth_fault:
                is_bluetooth_inquiry = True
                is_wifi_inquiry = False
            else:
                is_bluetooth_inquiry = False
                is_wifi_inquiry = has_explicit_missing_wifi

        if is_bluetooth_inquiry:
            for t_name, reason in [
                ("get_bluetooth_diagnostics", "Inspect Windows Bluetooth subsystem, controllers, and paired device enumeration."),
                ("get_bluetooth_service_status", "Check the operational state and startup type of Bluetooth Support Service (bthserv)."),
                ("get_bluetooth_radio_status", "Inspect hardware radio power and operational state for Bluetooth adapter."),
            ]:
                if t_name not in seen_tools:
                    hint = self._build_validated_hint(t_name, reason)
                    if hint:
                        hints.append(hint)
                        seen_tools.add(t_name)

        # Specialized Quick Settings missing Wi-Fi mapping
        is_quick_settings_missing_wifi = (
            is_quick_settings_panel
            and (is_wifi_inquiry or has_explicit_missing_wifi)
            and not is_bluetooth_inquiry
        )

        if is_quick_settings_missing_wifi:
            for t_name, reason in [
                ("get_network_adapters_diagnostics", "Wi-Fi quick toggle is missing from Windows Quick Settings. Inspect network adapter state and configuration in Windows."),
                ("get_services_diagnostics", "Inspect WLAN AutoConfig (WlanSvc) and background network services."),
                ("check_internet_connectivity", "Verify network and internet reachability."),
            ]:
                if t_name not in seen_tools:
                    hint = self._build_validated_hint(t_name, reason)
                    if hint:
                        hints.append(hint)
                        seen_tools.add(t_name)

        for keywords, tool_name, reason in keyword_rules:
            if tool_name not in seen_tools:
                if _matches_any_token(text_corpus, keywords):
                    hint = self._build_validated_hint(tool_name, reason)
                    if hint:
                        hints.append(hint)
                        seen_tools.add(tool_name)

        # 4. Fallback to broad suggested areas if provided
        if suggested_areas:
            area_tool_map = {
                "windows_update": "get_windows_update_health",
                "network": "check_internet_connectivity",
                "defender": "get_defender_diagnostics",
                "storage": "get_storage_diagnostics",
                "performance": "get_cpu_diagnostics",
                "application_crash": "get_recent_application_crashes",
                "bluetooth": "get_bluetooth_diagnostics",
                "printer": "get_printer_diagnostics",
                "power": "get_complete_system_info",
                "battery": "get_complete_system_info",
                "system_info": "get_complete_system_info",
                "general": "get_complete_system_info",
            }
            for area in suggested_areas:
                area_clean = area.strip().lower()
                if area_clean in area_tool_map:
                    t_name = area_tool_map[area_clean]
                    if t_name not in seen_tools:
                        hint = self._build_validated_hint(t_name, f"Vision model suggested investigating '{area}' area.")
                        if hint:
                            hints.append(hint)
                            seen_tools.add(t_name)

        # 5. Default fallback if nothing matched
        if not hints:
            default_hint = self._build_validated_hint(
                "get_complete_system_info",
                "General system baseline diagnostics.",
            )
            if default_hint:
                hints.append(default_hint)

        return hints

    def _build_validated_hint(self, tool_name: str, reason: str) -> Optional[ScreenshotDiagnosticHint]:
        """Validate candidate tool against ToolRegistry and ensure it is strictly read-only."""
        tool = self.registry.get(tool_name)
        if not tool and hasattr(self.registry, "get_tool"):
            tool = self.registry.get_tool(tool_name)
        if not tool:
            logger.debug("Rejected unapproved tool suggestion: %s", tool_name)
            return None

        # STRICT SAFETY: Reject repair tools from screenshot suggestion
        if not tool.read_only:
            logger.warning("Rejected non-read-only tool from screenshot diagnostic hint: %s", tool_name)
            return None

        r_val = tool.risk.value if hasattr(tool, "risk") else str(getattr(tool, "risk_level", "SAFE"))
        return ScreenshotDiagnosticHint(
            tool_name=tool.name,
            purpose=tool.description,
            risk_level=r_val,
            evidence_reason=reason,
            arguments={},
        )


default_screenshot_mapper = ScreenshotDiagnosticMapper()
