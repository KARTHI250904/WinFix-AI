"""WinFix AI — Troubleshooting Strategies (Phase 29).

Defines deterministic, domain-specific troubleshooting strategies containing structured
diagnostic sequences, required evidence, repair candidates, and verification requirements.
Strictly adheres to:
  Strategy != Windows Command
  Strategy Selection is Advisory / Orchestration Only
  Tools referenced in strategies must exist in approved ToolRegistry
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional

from agent.domain_models import TroubleshootingDomain
from agent.evidence_models import EvidenceItem, EvidenceType
from agent.tool_registry import ToolRegistry, default_tool_registry

logger = logging.getLogger("winfix.TROUBLESHOOTING_STRATEGIES")


@dataclass(frozen=True)
class TroubleshootingStrategy:
    """Structured troubleshooting strategy for a specific Windows problem category."""

    strategy_id: str
    domain: TroubleshootingDomain
    title: str
    description: str
    symptom_patterns: List[str]
    required_evidence_types: List[EvidenceType]
    optional_evidence_types: List[EvidenceType]
    diagnostic_sequence: List[str]  # Allowlisted SAFE tool names
    repair_candidates: List[Dict[str, Any]]  # Allowlisted MEDIUM repair definitions
    preconditions: Dict[str, Any]
    verification_tool: str
    failure_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy to dictionary."""
        return {
            "strategy_id": self.strategy_id,
            "domain": self.domain.value if isinstance(self.domain, TroubleshootingDomain) else str(self.domain),
            "title": self.title,
            "description": self.description,
            "symptom_patterns": list(self.symptom_patterns),
            "required_evidence_types": [e.value for e in self.required_evidence_types],
            "optional_evidence_types": [e.value for e in self.optional_evidence_types],
            "diagnostic_sequence": list(self.diagnostic_sequence),
            "repair_candidates": list(self.repair_candidates),
            "preconditions": dict(self.preconditions),
            "verification_tool": self.verification_tool,
            "failure_paths": dict(self.failure_paths),
        }


class StrategyRegistry:
    """Registry and deterministic selector for domain troubleshooting strategies."""

    def __init__(self, tool_registry: Optional[ToolRegistry] = None) -> None:
        self.tool_registry = tool_registry or default_tool_registry
        self._strategies: Dict[str, TroubleshootingStrategy] = {}
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Register built-in strategies across all 10 core domains."""
        # 1. NETWORK - DNS Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_net_dns",
                domain=TroubleshootingDomain.NETWORK,
                title="DNS Resolution Failure Strategy",
                description="Diagnoses name resolution timeouts and clears corrupted local DNS cache.",
                symptom_patterns=["dns", "cannot resolve", "domain not found", "websites won't load", "server not found"],
                required_evidence_types=[EvidenceType.NETWORK],
                optional_evidence_types=[],
                diagnostic_sequence=["get_network_adapters_diagnostics", "check_dns_resolution"],
                repair_candidates=[{
                    "tool_name": "flush_dns_cache",
                    "purpose": "Flush and reset the Windows DNS resolver cache",
                    "risk": "MEDIUM",
                    "arguments": {},
                }],
                preconditions={"required_evidence_type": "network"},
                verification_tool="check_dns_resolution",
                failure_paths={"precondition_failed": "Check physical network cable or Wi-Fi radio connection"},
            )
        )

        # 2. NETWORK - DHCP / Gateway Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_net_dhcp",
                domain=TroubleshootingDomain.NETWORK,
                title="DHCP Lease & Gateway Strategy",
                description="Diagnoses missing IP configuration, default gateway unreachable, and renews DHCP lease.",
                symptom_patterns=["dhcp", "ip address", "169.254", "unidentified network", "no internet access", "gateway unreachable"],
                required_evidence_types=[EvidenceType.NETWORK],
                optional_evidence_types=[],
                diagnostic_sequence=["get_network_adapters_diagnostics", "check_internet_connectivity"],
                repair_candidates=[{
                    "tool_name": "renew_dhcp_lease",
                    "purpose": "Release and renew DHCP address lease from router",
                    "risk": "MEDIUM",
                    "arguments": {},
                }],
                preconditions={"required_evidence_type": "network"},
                verification_tool="check_internet_connectivity",
                failure_paths={"precondition_failed": "Verify router connectivity and DHCP server status"},
            )
        )

        # 3. SERVICES - Service Recovery Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_services_recovery",
                domain=TroubleshootingDomain.SERVICES,
                title="Windows Service Recovery Strategy",
                description="Inspects stopped automatic background services and restarts target service.",
                symptom_patterns=["service", "spooler", "print spooler", "wuauserv", "service stopped", "service hung"],
                required_evidence_types=[EvidenceType.SERVICE],
                optional_evidence_types=[EvidenceType.SYSTEM],
                diagnostic_sequence=["get_service_status", "get_services_diagnostics"],
                repair_candidates=[{
                    "tool_name": "restart_service",
                    "purpose": "Safely restart the stalled target Windows service",
                    "risk": "MEDIUM",
                    "arguments": {"service_name": "wuauserv"},
                }],
                preconditions={},
                verification_tool="get_service_status",
                failure_paths={"verification_failed": "Inspect dependent service configurations and Windows event logs"},
            )
        )

        # 4. STORAGE - Temp Cleanup Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_storage_cleanup",
                domain=TroubleshootingDomain.STORAGE,
                title="Temporary Files Cleanup Strategy",
                description="Identifies low disk space and cleans obsolete temporary files.",
                symptom_patterns=["disk space", "low storage", "drive full", "c: is full", "clean disk", "temp files"],
                required_evidence_types=[EvidenceType.STORAGE],
                optional_evidence_types=[],
                diagnostic_sequence=["get_storage_diagnostics", "get_temp_storage_info"],
                repair_candidates=[{
                    "tool_name": "clean_user_temp_cache",
                    "purpose": "Purge temporary and stale cache files from approved user temp directories",
                    "risk": "MEDIUM",
                    "arguments": {},
                }],
                preconditions={},
                verification_tool="get_storage_diagnostics",
                failure_paths={"precondition_failed": "Inspect large user media files or run Storage Sense"},
            )
        )

        # 5. WINDOWS_UPDATE - Update Reset Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_win_update_reset",
                domain=TroubleshootingDomain.WINDOWS_UPDATE,
                title="Windows Update Reset Strategy",
                description="Diagnoses failed patch installation and resets Windows Update components.",
                symptom_patterns=["update error", "windows update", "0x80", "update failed", "patch failed", "stuck update"],
                required_evidence_types=[EvidenceType.WINDOWS_UPDATE, EvidenceType.SERVICE],
                optional_evidence_types=[EvidenceType.STORAGE],
                diagnostic_sequence=["get_windows_update_diagnostics", "get_windows_update_history"],
                repair_candidates=[{
                    "tool_name": "restart_windows_update_service",
                    "purpose": "Restart the Windows Update background service",
                    "risk": "MEDIUM",
                    "arguments": {},
                }],
                preconditions={},
                verification_tool="get_windows_update_diagnostics",
                failure_paths={"verification_failed": "Verify internet connectivity and disk space before retrying update"},
            )
        )

        # 6. WINDOWS_DEFENDER - Defender Maintenance Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_defender_maintenance",
                domain=TroubleshootingDomain.WINDOWS_DEFENDER,
                title="Windows Defender Status Strategy",
                description="Inspects real-time antivirus status and restarts Defender service if stalled.",
                symptom_patterns=["defender", "antivirus", "out of date", "signatures old", "security scan", "malware check"],
                required_evidence_types=[EvidenceType.DEFENDER, EvidenceType.SERVICE],
                optional_evidence_types=[],
                diagnostic_sequence=["get_defender_diagnostics", "get_defender_antivirus_status"],
                repair_candidates=[
                    {
                        "tool_name": "restart_defender_service",
                        "purpose": "Restart Windows Defender antivirus service",
                        "risk": "MEDIUM",
                        "arguments": {},
                    },
                ],
                preconditions={},
                verification_tool="get_defender_diagnostics",
                failure_paths={"verification_failed": "Verify network connection to Microsoft Update servers"},
            )
        )

        # 7. BLUETOOTH - Bluetooth Recovery Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_bluetooth_recovery",
                domain=TroubleshootingDomain.BLUETOOTH,
                title="Bluetooth Radio & Service Recovery Strategy",
                description="Diagnoses Bluetooth radio presence and restarts the Bluetooth Support Service.",
                symptom_patterns=["bluetooth", "bluetooth missing", "bthserv", "headphones not connecting", "bluetooth toggle"],
                required_evidence_types=[EvidenceType.BLUETOOTH, EvidenceType.SERVICE],
                optional_evidence_types=[],
                diagnostic_sequence=["get_bluetooth_diagnostics", "get_bluetooth_devices"],
                repair_candidates=[{
                    "tool_name": "restart_bluetooth_service",
                    "purpose": "Restart the Windows Bluetooth Support Service (bthserv)",
                    "risk": "MEDIUM",
                    "arguments": {},
                }],
                preconditions={},
                verification_tool="get_bluetooth_diagnostics",
                failure_paths={"verification_failed": "Verify physical Bluetooth radio adapter is enabled in Device Manager"},
            )
        )

        # 8. PERFORMANCE - Resource Diagnostics Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_performance_diagnostics",
                domain=TroubleshootingDomain.PERFORMANCE,
                title="Performance & Resource Consumption Strategy",
                description="Inspects high CPU, RAM, and disk utilization processes.",
                symptom_patterns=["high cpu", "100% disk", "out of memory", "lag", "pc freezing", "sluggish"],
                required_evidence_types=[EvidenceType.PERFORMANCE],
                optional_evidence_types=[],
                diagnostic_sequence=["get_top_cpu_processes", "get_top_memory_processes"],
                repair_candidates=[],
                preconditions={},
                verification_tool="get_top_cpu_processes",
                failure_paths={},
            )
        )

        # 9. APPLICATION_CRASH - Crash Diagnostics Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_app_crash_diagnostics",
                domain=TroubleshootingDomain.APPLICATION_CRASH,
                title="Application Fault & Crash Diagnostics Strategy",
                description="Extracts Windows Error Reporting (WER) crash logs and application Event Log records.",
                symptom_patterns=["app crash", "event 1000", "wer", "stopped working", "application error", "faulting module"],
                required_evidence_types=[EvidenceType.APPLICATION_CRASH],
                optional_evidence_types=[EvidenceType.SYSTEM],
                diagnostic_sequence=["get_application_crash_diagnostics", "get_recent_application_crashes"],
                repair_candidates=[],
                preconditions={},
                verification_tool="get_application_crash_diagnostics",
                failure_paths={},
            )
        )

        # 10. SYSTEM - Core OS & Reboot Strategy
        self.register(
            TroubleshootingStrategy(
                strategy_id="strat_system_diagnostics",
                domain=TroubleshootingDomain.SYSTEM,
                title="System Health & Event Log Strategy",
                description="Inspects Windows build metadata, pending reboot flags, and critical system events.",
                symptom_patterns=["system info", "windows build", "pending reboot", "system error", "event log"],
                required_evidence_types=[EvidenceType.SYSTEM],
                optional_evidence_types=[],
                diagnostic_sequence=["get_complete_system_info", "get_resource_snapshot"],
                repair_candidates=[],
                preconditions={},
                verification_tool="get_complete_system_info",
                failure_paths={},
            )
        )

    def register(self, strategy: TroubleshootingStrategy) -> None:
        """Register a strategy."""
        self._strategies[strategy.strategy_id] = strategy

    def get(self, strategy_id: str) -> Optional[TroubleshootingStrategy]:
        """Look up a strategy by ID."""
        return self._strategies.get(strategy_id)

    def select_strategy(
        self,
        domain: TroubleshootingDomain,
        symptom_text: str = "",
        evidence_items: Optional[List[EvidenceItem]] = None,
    ) -> Optional[TroubleshootingStrategy]:
        """Deterministically select the most appropriate strategy for a domain and symptom."""
        candidates = [s for s in self._strategies.values() if s.domain == domain]
        if not candidates:
            return None

        if not symptom_text:
            return candidates[0]

        symptom_lower = symptom_text.lower()
        best_match = candidates[0]
        max_score = 0

        for strat in candidates:
            score = sum(1 for p in strat.symptom_patterns if re.search(r"\b" + re.escape(p) + r"\b", symptom_lower))
            if score > max_score:
                max_score = score
                best_match = strat

        return best_match


default_strategy_registry = StrategyRegistry()
