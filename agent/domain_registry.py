"""WinFix AI — Troubleshooting Domain Registry (Phase 29).

Authoritative registry of all supported Windows troubleshooting domains,
their evidence types, diagnostic tools, repair capabilities, and verification mappings.
Strictly adheres to:
  Domain Registry is Authoritative
  Never dynamically create domains
  Unknown or malicious domain strings map fail-closed to UNKNOWN
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Set

from agent.domain_models import TroubleshootingDomain
from agent.evidence_models import EvidenceType

logger = logging.getLogger("winfix.DOMAIN_REGISTRY")


@dataclass(frozen=True)
class DomainMetadata:
    """Metadata specification for an approved troubleshooting domain."""

    domain: TroubleshootingDomain
    display_name: str
    description: str
    primary_evidence_types: List[EvidenceType]
    diagnostic_tools: List[str]
    repair_tools: List[str]
    symptom_keywords: List[str]
    related_domains: List[TroubleshootingDomain] = field(default_factory=list)


class DomainRegistry:
    """Central registry and authority for Windows troubleshooting domains."""

    def __init__(self) -> None:
        self._domains: Dict[TroubleshootingDomain, DomainMetadata] = {}
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Register the 10 built-in Windows domains plus UNKNOWN fallback."""
        # 1. NETWORK
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.NETWORK,
                display_name="Network & Internet Connectivity",
                description="Troubleshooting network adapters, DNS resolution, DHCP, gateway routing, and Wi-Fi.",
                primary_evidence_types=[
                    EvidenceType.NETWORK,
                ],
                diagnostic_tools=[
                    "get_network_adapters_diagnostics",
                    "check_dns_resolution",
                    "check_internet_connectivity",
                    "get_dns_client_config",
                ],
                repair_tools=[
                    "flush_dns_cache",
                    "renew_dhcp_lease",
                ],
                symptom_keywords=["internet", "wifi", "wi-fi", "dns", "gateway", "dhcp", "adapter", "network", "ping", "offline", "unreachable"],
                related_domains=[TroubleshootingDomain.SERVICES, TroubleshootingDomain.SYSTEM],
            )
        )

        # 2. PERFORMANCE
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.PERFORMANCE,
                display_name="System Performance & Resource Consumption",
                description="Troubleshooting high CPU, memory exhaustion, disk queue bottlenecks, and unresponsive processes.",
                primary_evidence_types=[
                    EvidenceType.PERFORMANCE,
                ],
                diagnostic_tools=[
                    "get_top_cpu_processes",
                    "get_top_memory_processes",
                    "get_cpu_diagnostics",
                    "get_memory_diagnostics",
                    "get_resource_snapshot",
                ],
                repair_tools=[
                    "terminate_user_process",
                ],
                symptom_keywords=["slow", "freeze", "lag", "cpu", "ram", "memory", "spike", "hang", "sluggish", "100%", "high usage"],
                related_domains=[TroubleshootingDomain.STORAGE, TroubleshootingDomain.SERVICES, TroubleshootingDomain.STARTUP],
            )
        )

        # 3. STORAGE
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.STORAGE,
                display_name="Storage & Disk Health",
                description="Troubleshooting low disk space, temporary junk accumulation, and file system volume integrity.",
                primary_evidence_types=[
                    EvidenceType.STORAGE,
                ],
                diagnostic_tools=[
                    "get_storage_diagnostics",
                    "get_temp_storage_info",
                    "analyze_large_temporary_files",
                    "get_storage_pressure_analysis",
                ],
                repair_tools=[
                    "clean_user_temp_cache",
                ],
                symptom_keywords=["disk", "drive", "storage", "c:", "space", "full", "temp", "recycle", "junk", "smart"],
                related_domains=[TroubleshootingDomain.SYSTEM, TroubleshootingDomain.WINDOWS_UPDATE],
            )
        )

        # 4. SERVICES
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.SERVICES,
                display_name="Windows Services Management",
                description="Troubleshooting stopped, hung, disabled, or failed background Windows services.",
                primary_evidence_types=[
                    EvidenceType.SERVICE,
                ],
                diagnostic_tools=[
                    "get_service_status",
                    "get_services_diagnostics",
                    "get_service_details",
                    "list_common_services",
                ],
                repair_tools=[
                    "restart_service",
                    "start_service",
                    "stop_service",
                ],
                symptom_keywords=["service", "spooler", "wuauserv", "dnscache", "bthserv", "stopped", "daemon", "service failed"],
                related_domains=[TroubleshootingDomain.SYSTEM, TroubleshootingDomain.WINDOWS_UPDATE, TroubleshootingDomain.BLUETOOTH],
            )
        )

        # 5. WINDOWS_UPDATE
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.WINDOWS_UPDATE,
                display_name="Windows Update Subsystem",
                description="Troubleshooting failed updates, corrupted SoftwareDistribution cache, and update errors.",
                primary_evidence_types=[
                    EvidenceType.WINDOWS_UPDATE,
                    EvidenceType.SERVICE,
                ],
                diagnostic_tools=[
                    "get_windows_update_diagnostics",
                    "get_windows_update_history",
                    "get_windows_update_health",
                    "get_windows_update_errors",
                ],
                repair_tools=[
                    "restart_windows_update_service",
                ],
                symptom_keywords=["update", "patch", "kb", "0x80", "windows update", "softwaredistribution", "pending reboot"],
                related_domains=[TroubleshootingDomain.SERVICES, TroubleshootingDomain.STORAGE, TroubleshootingDomain.NETWORK],
            )
        )

        # 6. WINDOWS_DEFENDER
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.WINDOWS_DEFENDER,
                display_name="Windows Defender & Security Subsystem",
                description="Troubleshooting antivirus signature freshness, real-time protection state, and threat scanning.",
                primary_evidence_types=[
                    EvidenceType.DEFENDER,
                    EvidenceType.SERVICE,
                ],
                diagnostic_tools=[
                    "get_defender_diagnostics",
                    "get_defender_antivirus_status",
                    "get_defender_realtime_protection_status",
                    "get_defender_threat_status",
                ],
                repair_tools=[
                    "restart_defender_service",
                ],
                symptom_keywords=["defender", "antivirus", "threat", "virus", "scan", "real-time", "malware", "security signature"],
                related_domains=[TroubleshootingDomain.SERVICES, TroubleshootingDomain.SYSTEM],
            )
        )

        # 7. BLUETOOTH
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.BLUETOOTH,
                display_name="Bluetooth & Peripheral Radio Subsystem",
                description="Troubleshooting Bluetooth radio presence, paired devices, and peripheral service availability.",
                primary_evidence_types=[
                    EvidenceType.BLUETOOTH,
                    EvidenceType.SERVICE,
                ],
                diagnostic_tools=[
                    "get_bluetooth_diagnostics",
                    "get_bluetooth_devices",
                    "get_bluetooth_adapters",
                    "get_bluetooth_radio_status",
                ],
                repair_tools=[
                    "restart_bluetooth_service",
                ],
                symptom_keywords=["bluetooth", "bth", "pairing", "headphone", "audio device", "wireless mouse", "radio"],
                related_domains=[TroubleshootingDomain.SERVICES, TroubleshootingDomain.SYSTEM],
            )
        )

        # 8. APPLICATION_CRASH
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.APPLICATION_CRASH,
                display_name="Application Crash & Fault Diagnostics",
                description="Troubleshooting application crashes, Windows Error Reporting (WER) reports, and Event Log application errors.",
                primary_evidence_types=[
                    EvidenceType.APPLICATION_CRASH,
                ],
                diagnostic_tools=[
                    "get_application_crash_diagnostics",
                    "get_recent_application_crashes",
                    "get_application_crash_events",
                    "get_windows_error_reporting_status",
                ],
                repair_tools=[],
                symptom_keywords=["crash", "wer", "fault", "exception", "event 1000", "stopped working", "closes", "exit code", "exception code"],
                related_domains=[TroubleshootingDomain.PERFORMANCE, TroubleshootingDomain.SYSTEM],
            )
        )

        # 9. DISPLAY
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.DISPLAY,
                display_name="Display, Monitor & Graphics Subsystem",
                description="Troubleshooting monitor resolution, display adapters, brightness, and Night Light.",
                primary_evidence_types=[
                    EvidenceType.SYSTEM,
                ],
                diagnostic_tools=[
                    "get_display_diagnostics",
                ],
                repair_tools=[],
                symptom_keywords=["display", "screen", "monitor", "resolution", "night light", "brightness", "scaling", "gpu", "graphics", "bluelight"],
                related_domains=[TroubleshootingDomain.SYSTEM, TroubleshootingDomain.PERFORMANCE],
            )
        )

        # 10. AUDIO
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.AUDIO,
                display_name="Audio, Speakers & Sound Subsystem",
                description="Troubleshooting audio endpoints, playback/recording devices, and Windows Audio services.",
                primary_evidence_types=[
                    EvidenceType.SERVICE,
                    EvidenceType.SYSTEM,
                ],
                diagnostic_tools=[
                    "get_audio_diagnostics",
                    "get_audio_endpoint_status",
                ],
                repair_tools=[],
                symptom_keywords=["audio", "sound", "volume", "speaker", "speakers", "microphone", "mic", "headphone", "no sound", "audiosrv"],
                related_domains=[TroubleshootingDomain.SERVICES, TroubleshootingDomain.BLUETOOTH],
            )
        )

        # 11. PRINTER
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.PRINTER,
                display_name="Printers & Print Spooler Subsystem",
                description="Troubleshooting printer enumeration, default printer routing, and Print Spooler service state.",
                primary_evidence_types=[
                    EvidenceType.SERVICE,
                    EvidenceType.SYSTEM,
                ],
                diagnostic_tools=[
                    "get_printer_diagnostics",
                ],
                repair_tools=[],
                symptom_keywords=["printer", "printing", "spooler", "print spooler", "spoolsv", "print queue"],
                related_domains=[TroubleshootingDomain.SERVICES, TroubleshootingDomain.SYSTEM],
            )
        )

        # 12. STARTUP
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.STARTUP,
                display_name="Windows Startup & Boot Programs",
                description="Troubleshooting slow boot times, high startup impact applications, and startup configuration items.",
                primary_evidence_types=[
                    EvidenceType.PERFORMANCE,
                ],
                diagnostic_tools=[
                    "get_resource_snapshot",
                    "get_top_cpu_processes",
                ],
                repair_tools=[],
                symptom_keywords=["boot", "startup", "startup program", "autostart", "slow boot", "login slow"],
                related_domains=[TroubleshootingDomain.PERFORMANCE, TroubleshootingDomain.SYSTEM],
            )
        )

        # 10. SYSTEM
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.SYSTEM,
                display_name="Core Windows Operating System & Environment",
                description="Troubleshooting Windows build metadata, OS integrity, UAC elevation, environment variables, and system event logs.",
                primary_evidence_types=[
                    EvidenceType.SYSTEM,
                ],
                diagnostic_tools=[
                    "get_complete_system_info",
                    "get_resource_snapshot",
                ],
                repair_tools=[],
                symptom_keywords=["system", "windows version", "build", "reboot", "bsod", "kernel", "os", "environment", "uac"],
                related_domains=[TroubleshootingDomain.SERVICES, TroubleshootingDomain.PERFORMANCE],
            )
        )

        # 11. UNKNOWN
        self.register(
            DomainMetadata(
                domain=TroubleshootingDomain.UNKNOWN,
                display_name="General / Unclassified Domain",
                description="Fallback unclassified domain for ambiguous, unrecognized, or general Windows issues.",
                primary_evidence_types=[
                    EvidenceType.SYSTEM,
                ],
                diagnostic_tools=[
                    "get_complete_system_info",
                ],
                repair_tools=[],
                symptom_keywords=[],
                related_domains=[],
            )
        )

    def register(self, metadata: DomainMetadata) -> None:
        """Register a domain definition."""
        self._domains[metadata.domain] = metadata

    def get(self, domain: TroubleshootingDomain) -> Optional[DomainMetadata]:
        """Look up metadata for a specific domain."""
        return self._domains.get(domain)

    def parse_domain(self, domain_str: Optional[str]) -> TroubleshootingDomain:
        """Parse a domain string safely, returning UNKNOWN on invalid or unapproved input."""
        if not domain_str:
            return TroubleshootingDomain.UNKNOWN

        clean_str = str(domain_str).strip().upper()
        try:
            return TroubleshootingDomain(clean_str)
        except ValueError:
            return TroubleshootingDomain.UNKNOWN

    def list_domains(self) -> List[TroubleshootingDomain]:
        """List all registered domains."""
        return list(self._domains.keys())

    def classify_symptom_heuristically(self, symptom_text: str) -> TroubleshootingDomain:
        """Deterministically classify a symptom text against domain keyword rules."""
        if not symptom_text:
            return TroubleshootingDomain.UNKNOWN

        text_lower = symptom_text.lower()
        best_domain = TroubleshootingDomain.UNKNOWN
        max_matches = 0

        for domain, meta in self._domains.items():
            if domain == TroubleshootingDomain.UNKNOWN:
                continue
            matches = sum(1 for kw in meta.symptom_keywords if re.search(r"\b" + re.escape(kw) + r"\b", text_lower))
            if matches > max_matches:
                max_matches = matches
                best_domain = domain

        return best_domain


default_domain_registry = DomainRegistry()
