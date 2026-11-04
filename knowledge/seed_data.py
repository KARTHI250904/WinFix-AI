"""Deterministic seed data for WinFix AI Troubleshooting Knowledge System (Phase 19).

Provides verified, structured troubleshooting guidance for all core Windows diagnostic domains.
Strictly references only registered ToolRegistry tools and adheres to the rule:
LLM != Windows Shell and Knowledge != Windows Command.
"""

import logging
from typing import Any, Dict, List

from database.knowledge_models import (
    KnowledgeArticle,
    KnowledgeCategory,
    KnowledgeSeverity,
)
from database.knowledge_repository import KnowledgeRepository

logger = logging.getLogger(__name__)

KNOWLEDGE_VERSION = 1


def get_seed_articles() -> List[KnowledgeArticle]:
    """Construct deterministic baseline knowledge articles for WinFix AI."""
    return [
        # 1. NETWORK
        KnowledgeArticle(
            id="kb_net_001",
            title="Wi-Fi and Internet Connectivity Troubleshooting",
            category=KnowledgeCategory.NETWORK,
            summary="Guidance for diagnosing network adapter disconnections, DNS resolution failures, and DHCP lease timeouts.",
            symptoms=[
                "Cannot connect to the internet",
                "Wi-Fi connected but no internet access",
                "DNS server not responding",
                "IP address assignment or DHCP failure",
            ],
            possible_causes=[
                "Network adapter disabled or link state disconnected",
                "Stale or corrupted DNS client cache",
                "Expired or invalid DHCP lease assignment",
                "Gateway or upstream DNS resolver unreachable",
            ],
            diagnostic_steps=[
                "Inspect network adapter state, MAC address, and IPv4/IPv6 addresses",
                "Test DNS hostname resolution against public and local nameservers",
                "Verify end-to-end internet connectivity and round-trip ping latency",
                "Check DNS client configuration and configured DNS servers",
            ],
            related_tools=[
                "check_internet_connectivity",
                "get_network_adapters_diagnostics",
                "check_dns_resolution",
                "get_dns_client_config",
            ],
            repair_references=[
                "flush_dns_cache",
                "renew_dhcp_lease",
            ],
            verification_steps=[
                "Confirm network adapter link status is operational",
                "Confirm DNS query resolves successfully within acceptable latency",
                "Confirm internet connectivity health endpoint returns HTTP 200",
            ],
            severity=KnowledgeSeverity.HIGH,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 2. STORAGE
        KnowledgeArticle(
            id="kb_storage_001",
            title="Storage Pressure and Temporary File Accumulation",
            category=KnowledgeCategory.STORAGE,
            summary="Troubleshooting low free disk space, system drive storage pressure, and bloated user temporary directories.",
            symptoms=[
                "Low disk space warning on system drive C:",
                "Windows updates failing due to insufficient space",
                "Applications sluggish or failing to allocate cache",
                "Large temporary files accumulating in user AppData",
            ],
            possible_causes=[
                "User temp directory contains excessive stale cache files",
                "Old Windows installation or crash dump files occupying storage",
                "Unusually large temporary application artifacts",
            ],
            diagnostic_steps=[
                "Inspect total capacity, free space, and drive health indicators",
                "Measure user temporary directory size and file count",
                "Analyze disk storage pressure and threshold warnings",
                "Identify top large temporary files in the user profile",
            ],
            related_tools=[
                "get_storage_diagnostics",
                "get_temp_storage_info",
                "get_storage_pressure_analysis",
                "analyze_large_temporary_files",
            ],
            repair_references=[
                "clean_user_temp_cache",
            ],
            verification_steps=[
                "Verify system drive free percentage exceeds critical threshold",
                "Confirm user temporary folder size was reduced safely",
            ],
            severity=KnowledgeSeverity.MEDIUM,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 3. PERFORMANCE
        KnowledgeArticle(
            id="kb_perf_001",
            title="High CPU and Memory Resource Bottlenecks",
            category=KnowledgeCategory.PERFORMANCE,
            summary="Diagnostic guidance for identifying runaway processes, excessive CPU utilization, and system memory starvation.",
            symptoms=[
                "System responsiveness is extremely sluggish",
                "Fan noise high with constant elevated CPU utilization",
                "Out of memory warnings or high committed page file usage",
                "Specific background task consuming excessive system resources",
            ],
            possible_causes=[
                "Runaway background process stuck in an infinite loop",
                "Memory leak in an active application process",
                "High disk I/O queue or storage saturation",
            ],
            diagnostic_steps=[
                "Collect CPU core count, overall load percentage, and clock frequency",
                "Inspect total physical memory, available RAM, and percent utilization",
                "List top processes ordered by active CPU consumption",
                "List top processes ordered by resident memory footprint",
                "Capture comprehensive system resource utilization snapshot",
            ],
            related_tools=[
                "get_cpu_diagnostics",
                "get_memory_diagnostics",
                "get_top_cpu_processes",
                "get_top_memory_processes",
                "get_resource_snapshot",
                "get_disk_performance_diagnostics",
                "get_process_details",
            ],
            repair_references=[
                "terminate_user_process",
            ],
            verification_steps=[
                "Verify overall CPU load drops below sustained threshold",
                "Confirm available memory stabilizes to normal operating baseline",
            ],
            severity=KnowledgeSeverity.HIGH,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 4. SERVICES
        KnowledgeArticle(
            id="kb_serv_001",
            title="Critical Windows Service Failures and State Issues",
            category=KnowledgeCategory.SERVICES,
            summary="Guidance for diagnosing stopped, failed, or unresponsive critical Windows background services.",
            symptoms=[
                "Required Windows service is not running",
                "Service fails to start or crashes immediately upon startup",
                "Dependent features or subsystems fail with service errors",
            ],
            possible_causes=[
                "Service process crashed or was terminated unexpectedly",
                "Service startup type is disabled or misconfigured",
                "Required dependency service is not in running state",
            ],
            diagnostic_steps=[
                "Inspect target service status, start type, and process identifier",
                "Check status of common core Windows background services",
                "Collect detailed diagnostic telemetry for service group",
            ],
            related_tools=[
                "get_service_status",
                "list_common_services",
                "get_services_diagnostics",
                "get_service_details",
            ],
            repair_references=[
                "start_service",
                "stop_service",
                "restart_service",
            ],
            verification_steps=[
                "Confirm target service status is verified as RUNNING",
                "Verify service process PID is active and responsive",
            ],
            severity=KnowledgeSeverity.HIGH,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 5. BLUETOOTH
        KnowledgeArticle(
            id="kb_bt_001",
            title="Bluetooth Radio and Device Connectivity Troubleshooting",
            category=KnowledgeCategory.BLUETOOTH,
            summary="Troubleshooting Bluetooth radio adapter state, pairing disconnections, and Bluetooth Support Service failures.",
            symptoms=[
                "Bluetooth toggle missing from Windows Action Center or Settings",
                "Bluetooth devices fail to connect or pair",
                "Bluetooth audio stuttering or dropping connection",
            ],
            possible_causes=[
                "Bluetooth Support Service (bthserv) is stopped or stuck",
                "Bluetooth radio adapter hardware is disabled or in error state",
                "Paired device state is out of synchronization",
            ],
            diagnostic_steps=[
                "Inspect Bluetooth adapter status and hardware radio readiness",
                "Check Bluetooth Support Service (bthserv) operational state",
                "Enumerate paired and discovered Bluetooth peripheral devices",
                "Collect overall Bluetooth subsystem diagnostic health",
            ],
            related_tools=[
                "get_bluetooth_diagnostics",
                "get_bluetooth_adapters",
                "get_bluetooth_radio_status",
                "get_bluetooth_devices",
                "get_bluetooth_service_status",
            ],
            repair_references=[
                "restart_bluetooth_service",
            ],
            verification_steps=[
                "Confirm Bluetooth radio status is operational and discoverable",
                "Confirm Bluetooth Support Service is active and running",
            ],
            severity=KnowledgeSeverity.MEDIUM,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 6. WINDOWS UPDATE
        KnowledgeArticle(
            id="kb_wu_001",
            title="Windows Update Service and Download Troubleshooting",
            category=KnowledgeCategory.WINDOWS_UPDATE,
            summary="Investigating stuck Windows Update downloads, service initialization errors, and component store issues.",
            symptoms=[
                "Windows Update download stuck at 0% or specific percentage",
                "Windows Update error codes during check or installation",
                "Windows Update service (wuauserv) failing to start",
            ],
            possible_causes=[
                "Windows Update service (wuauserv) or BITS is stopped/frozen",
                "Windows Update dependency services (cryptsvc, dosvc) unresponsive",
                "Update download queue or temporary cache corruption",
            ],
            diagnostic_steps=[
                "Inspect Windows Update service (wuauserv) operational state",
                "Check all required dependency services (BITS, CryptSvc, DoSvc)",
                "Inspect Windows Update configuration and automatic update policy",
                "Query recent Windows Update installation history and error events",
                "Collect consolidated Windows Update subsystem health summary",
            ],
            related_tools=[
                "get_windows_update_diagnostics",
                "get_windows_update_service_status",
                "get_windows_update_dependency_services",
                "get_windows_update_configuration",
                "get_windows_update_history",
                "get_windows_update_errors",
                "get_windows_update_health",
            ],
            repair_references=[
                "restart_windows_update_service",
            ],
            verification_steps=[
                "Verify Windows Update service is verified as RUNNING",
                "Verify required dependency services are active and healthy",
            ],
            severity=KnowledgeSeverity.HIGH,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 7. DEFENDER
        KnowledgeArticle(
            id="kb_def_001",
            title="Windows Defender Security and Antivirus Diagnostics",
            category=KnowledgeCategory.DEFENDER,
            summary="Guidance for inspecting Windows Defender security health, real-time protection status, and service health.",
            symptoms=[
                "Windows Security indicates Defender service is not running",
                "Real-time protection toggle is disabled or greyed out",
                "Antivirus signature definitions are out of date",
            ],
            possible_causes=[
                "Windows Defender Antivirus Service (WinDefend) stopped or unresponsive",
                "Real-time protection engine encountered an internal fault",
                "Security policy or third-party conflict affecting Defender state",
            ],
            diagnostic_steps=[
                "Inspect WinDefend service status and process state",
                "Check Windows Defender security health and protection status",
                "Query real-time protection, antivirus engine, and signature versions",
                "Review recent Defender security events and threat detection logs",
                "Inspect Defender configuration settings and operational flags",
            ],
            related_tools=[
                "get_defender_diagnostics",
                "get_defender_service_status",
                "get_defender_security_health",
                "get_defender_realtime_protection_status",
                "get_defender_antivirus_status",
                "get_defender_threat_status",
                "get_defender_recent_events",
                "get_defender_configuration",
            ],
            repair_references=[
                "restart_defender_service",
            ],
            verification_steps=[
                "Confirm Windows Defender service (WinDefend) is verified RUNNING",
                "Verify real-time protection health indicator reports active",
            ],
            severity=KnowledgeSeverity.CRITICAL,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 8. APPLICATION CRASH
        KnowledgeArticle(
            id="kb_app_001",
            title="Application Crashes and Faulting Module Analysis",
            category=KnowledgeCategory.APPLICATION_CRASH,
            summary="Investigating frequent desktop application crashes, exception faulting modules, and Windows Error Reporting logs.",
            symptoms=[
                "Desktop application crashes immediately upon launch or during use",
                "Application stops responding and closes without an error dialog",
                "Repeated crash reports recorded in Windows Application Event Log",
            ],
            possible_causes=[
                "Corrupted or missing application dependency DLL",
                "Access violation (0xc0000005) or unhandled runtime exception",
                "Incompatible third-party hook or graphics driver conflict",
            ],
            diagnostic_steps=[
                "Query recent application crash events from Windows Event Log",
                "Inspect faulting module, exception code, and crash offset details",
                "Generate crash frequency summary grouped by application executable",
                "Analyze specific faulting module library properties",
                "Check Windows Error Reporting (WER) operational readiness",
                "Collect consolidated application crash diagnostics overview",
            ],
            related_tools=[
                "get_recent_application_crashes",
                "get_application_crash_details",
                "get_application_crash_summary",
                "get_application_crash_frequency",
                "get_faulting_module_information",
                "get_windows_error_reporting_status",
                "get_application_crash_events",
                "get_application_crash_diagnostics",
            ],
            repair_references=[],
            verification_steps=[
                "Verify crash frequency history for target executable",
                "Confirm Windows Error Reporting logs event accurately",
            ],
            severity=KnowledgeSeverity.MEDIUM,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),

        # 9. GENERAL / SYSTEM
        KnowledgeArticle(
            id="kb_gen_001",
            title="General Windows System Health and Hardware Environment",
            category=KnowledgeCategory.GENERAL,
            summary="Baseline guidance for collecting hardware inventory, OS version details, printer subsystem status, and overall system state.",
            symptoms=[
                "General system instability or unspecified hardware behavior",
                "Printer spooler or printing subsystem errors",
                "Need to verify Windows build, architecture, and system specs",
            ],
            possible_causes=[
                "Outdated OS build or pending reboot requirement",
                "Print Spooler service stopped or spool directory error",
                "Hardware driver compatibility or baseline configuration issue",
            ],
            diagnostic_steps=[
                "Collect comprehensive OS, hardware architecture, and computer metadata",
                "Inspect local printer devices and Print Spooler operational status",
                "Check common Windows background services health",
            ],
            related_tools=[
                "get_complete_system_info",
                "get_printer_diagnostics",
                "list_common_services",
            ],
            repair_references=[],
            verification_steps=[
                "Confirm complete system info is queryable without errors",
            ],
            severity=KnowledgeSeverity.LOW,
            confidence=1.0,
            platform="Windows 10/11",
            source="WinFix Knowledge Base",
            version=KNOWLEDGE_VERSION,
        ),
    ]


def seed_default_knowledge(
    repository: KnowledgeRepository,
    force: bool = False,
) -> Dict[str, Any]:
    """Seed the baseline troubleshooting knowledge articles into SQLite.

    Idempotent: if articles already exist and version matches, skips unless force=True.
    """
    try:
        current_version_str = repository.get_metadata("knowledge_version")
        current_version = int(current_version_str) if current_version_str else 0

        existing_count = repository.count_articles()
        if existing_count > 0 and current_version >= KNOWLEDGE_VERSION and not force:
            logger.debug(
                "Knowledge database already seeded with %d articles (version=%d). Skipping seed.",
                existing_count,
                current_version,
            )
            return {
                "success": True,
                "seeded": False,
                "article_count": existing_count,
                "version": current_version,
            }

        articles = get_seed_articles()
        seeded_count = 0
        for article in articles:
            # Check if article exists
            existing = repository.get_article(article.id)
            if existing:
                repository.update_article(article, validate=True)
            else:
                repository.create_article(article, validate=True)
            seeded_count += 1

        repository.set_metadata("knowledge_version", str(KNOWLEDGE_VERSION))
        logger.info("Successfully seeded %d knowledge articles (version=%d).", seeded_count, KNOWLEDGE_VERSION)
        return {
            "success": True,
            "seeded": True,
            "article_count": seeded_count,
            "version": KNOWLEDGE_VERSION,
        }
    except Exception as exc:
        logger.error("Failed to seed knowledge database: %s", exc)
        return {
            "success": False,
            "seeded": False,
            "error": str(exc),
            "article_count": 0,
            "version": 0,
        }
