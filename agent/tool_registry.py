"""Central Tool Registry for WinFix AI.

Maintains the strict whitelist of approved, explicitly registered Windows tools.
Complies with the safety rule: LLM != Windows Shell.
"""

import logging
from typing import Any, Dict, List, Optional

from agent.tool_metadata import ParameterSpec, RiskLevel, ToolDefinition
import windows

logger = logging.getLogger(__name__)


class ToolRegistry:
    """In-memory registry storing verified, allowlisted Windows tool definitions."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a new approved tool definition.

        Raises ValueError if tool metadata is invalid or if tool is already registered.
        """
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError("Tool name must be a non-empty string.")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered in ToolRegistry.")
        if not isinstance(tool.risk, RiskLevel):
            raise ValueError(f"Invalid risk level '{tool.risk}' for tool '{tool.name}'.")
        if tool.handler is None or not callable(tool.handler):
            raise ValueError(f"Tool '{tool.name}' must have a callable handler function.")

        self._tools[tool.name] = tool
        logger.debug("Registered tool '%s' (domain=%s, risk=%s)", tool.name, tool.domain, tool.risk.value)

    def get(self, tool_name: str) -> Optional[ToolDefinition]:
        """Retrieve a registered tool definition by name."""
        return self._tools.get(tool_name)

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """Retrieve a registered tool definition by name (alias for get)."""
        return self.get(tool_name)

    def list_tools(self, domain: Optional[str] = None) -> List[ToolDefinition]:
        """List registered tool definitions, optionally filtered by domain."""
        if domain:
            return [t for t in self._tools.values() if t.domain == domain]
        return list(self._tools.values())

    def list_tool_names(self) -> List[str]:
        """List names of all registered tools."""
        return sorted(self._tools.keys())

    def count(self) -> int:
        """Return total number of registered tools."""
        return len(self._tools)

    def clear(self) -> None:
        """Clear all registered tools (used primarily for test isolation)."""
        self._tools.clear()


def create_default_registry() -> ToolRegistry:
    """Instantiate and populate the ToolRegistry with all standard Phase 3 read-only tools."""
    registry = ToolRegistry()

    # 1. Complete System Information
    registry.register(
        ToolDefinition(
            name="get_complete_system_info",
            domain="system",
            description="Collect complete hardware, OS, and system environment information.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_complete_system_info,
        )
    )

    # 2. Network Adapters
    registry.register(
        ToolDefinition(
            name="get_network_adapters_diagnostics",
            domain="network",
            description="Inspect network interfaces, link state, IP configuration, and MAC addresses.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_network_adapters_diagnostics,
        )
    )

    # 3. DNS Resolution
    registry.register(
        ToolDefinition(
            name="check_dns_resolution",
            domain="network",
            description="Test DNS hostname lookup and measure resolution latency in milliseconds.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "hostname": ParameterSpec(
                    name="hostname",
                    param_type=str,
                    required=False,
                    default="dns.google",
                    max_value=255,
                    description="Target hostname to resolve via DNS.",
                ),
                "timeout": ParameterSpec(
                    name="timeout",
                    param_type=float,
                    required=False,
                    default=3.0,
                    min_value=0.1,
                    max_value=30.0,
                    description="Lookup timeout in seconds.",
                ),
            },
            handler=windows.check_dns_resolution,
        )
    )

    # 4. Internet Connectivity
    registry.register(
        ToolDefinition(
            name="check_internet_connectivity",
            domain="network",
            description="Test TCP/UDP socket reachability to an external host.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "target_host": ParameterSpec(
                    name="target_host",
                    param_type=str,
                    required=False,
                    default="1.1.1.1",
                    max_value=255,
                    description="Target IP address or host.",
                ),
                "port": ParameterSpec(
                    name="port",
                    param_type=int,
                    required=False,
                    default=53,
                    min_value=1,
                    max_value=65535,
                    description="Target port number.",
                ),
                "timeout": ParameterSpec(
                    name="timeout",
                    param_type=float,
                    required=False,
                    default=3.0,
                    min_value=0.1,
                    max_value=30.0,
                    description="Socket connection timeout in seconds.",
                ),
            },
            handler=windows.check_internet_connectivity,
        )
    )

    # 5. DNS Client Config
    registry.register(
        ToolDefinition(
            name="get_dns_client_config",
            domain="network",
            description="Read configured DNS nameservers from the Windows registry.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_dns_client_config,
        )
    )

    # 6. CPU Diagnostics
    registry.register(
        ToolDefinition(
            name="get_cpu_diagnostics",
            domain="performance",
            description="Measure real-time CPU percentage and per-core utilization.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "interval": ParameterSpec(
                    name="interval",
                    param_type=float,
                    required=False,
                    default=0.1,
                    min_value=0.01,
                    max_value=5.0,
                    description="Sampling interval in seconds.",
                )
            },
            handler=windows.get_cpu_diagnostics,
        )
    )

    # 7. Memory Diagnostics
    registry.register(
        ToolDefinition(
            name="get_memory_diagnostics",
            domain="performance",
            description="Inspect physical RAM capacity, available RAM, and pagefile usage.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_memory_diagnostics,
        )
    )

    # 8. Top CPU Processes
    registry.register(
        ToolDefinition(
            name="get_top_cpu_processes",
            domain="performance",
            description="Identify top running processes consuming the highest CPU percentage.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=5,
                    min_value=1,
                    max_value=50,
                    description="Number of top processes to return.",
                )
            },
            handler=windows.get_top_cpu_processes,
        )
    )

    # 9. Top Memory Processes
    registry.register(
        ToolDefinition(
            name="get_top_memory_processes",
            domain="performance",
            description="Identify top running processes consuming the highest physical RAM.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=5,
                    min_value=1,
                    max_value=50,
                    description="Number of top processes to return.",
                )
            },
            handler=windows.get_top_memory_processes,
        )
    )

    # 10. Storage Diagnostics
    registry.register(
        ToolDefinition(
            name="get_storage_diagnostics",
            domain="storage",
            description="Inspect drive partitions, capacities, filesystem types, and free space.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_storage_diagnostics,
        )
    )

    # 11. Temp Storage Diagnostics
    registry.register(
        ToolDefinition(
            name="get_temp_storage_info",
            domain="storage",
            description="Inspect occupancy of standard temporary storage folders in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_temp_storage_info,
        )
    )

    # 12. Single Service Status
    registry.register(
        ToolDefinition(
            name="get_service_status",
            domain="services",
            description="Query the status and startup type of a specific Windows service.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "service_name": ParameterSpec(
                    name="service_name",
                    param_type=str,
                    required=True,
                    max_value=100,
                    description="Name of the service to query.",
                )
            },
            handler=windows.get_service_status,
        )
    )

    # 13. List Common Services
    registry.register(
        ToolDefinition(
            name="list_common_services",
            domain="services",
            description="Inspect the operational state of standard monitored Windows services.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.list_common_services,
        )
    )

    # 14. Bluetooth Diagnostics
    registry.register(
        ToolDefinition(
            name="get_bluetooth_diagnostics",
            domain="bluetooth",
            description="Inspect Bluetooth support service state and radio adapter presence.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_bluetooth_diagnostics,
        )
    )

    # 15. Printer Diagnostics
    registry.register(
        ToolDefinition(
            name="get_printer_diagnostics",
            domain="printer",
            description="Inspect installed printers, default printer, and Print Spooler status.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_printer_diagnostics,
        )
    )

    # 16. Windows Update Diagnostics
    registry.register(
        ToolDefinition(
            name="get_windows_update_diagnostics",
            domain="windows_update",
            description="Inspect update services readiness and auto-update configuration.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_windows_update_diagnostics,
        )
    )

    # 17. Microsoft Defender Diagnostics
    registry.register(
        ToolDefinition(
            name="get_defender_diagnostics",
            domain="defender",
            description="Inspect Microsoft Defender Antivirus and Firewall service status.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_defender_diagnostics,
        )
    )

    # 18. Application Crashes Event Log
    registry.register(
        ToolDefinition(
            name="get_recent_application_crashes",
            domain="applications",
            description="Inspect recent application error and crash events from the Windows Application log.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=10,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of crash events to return.",
                ),
                "max_scan": ParameterSpec(
                    name="max_scan",
                    param_type=int,
                    required=False,
                    default=200,
                    min_value=10,
                    max_value=1000,
                    description="Maximum number of log events to scan backwards.",
                ),
            },
            handler=windows.get_recent_application_crashes,
        )
    )

    # 19. Flush DNS Resolver Cache (Phase 7 Repair)
    registry.register(
        ToolDefinition(
            name="flush_dns_cache",
            domain="network",
            description="Clear and flush the local Windows DNS resolver cache to resolve stale DNS entries.",
            risk=RiskLevel.MEDIUM,
            requires_admin=False,
            automatic_allowed=False,
            read_only=False,
            verification_tool="check_dns_resolution",
            handler=windows.flush_dns_cache,
        )
    )

    # 20. Renew DHCP Lease (Phase 7 Repair)
    registry.register(
        ToolDefinition(
            name="renew_dhcp_lease",
            domain="network",
            description="Request a fresh DHCP IP address lease for active network adapters from the router.",
            risk=RiskLevel.MEDIUM,
            requires_admin=True,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_network_adapters_diagnostics",
            parameters={
                "adapter_index": ParameterSpec(
                    name="adapter_index",
                    param_type=int,
                    required=False,
                    default=None,
                    min_value=0,
                    max_value=65535,
                    description="Optional adapter index to renew.",
                )
            },
            handler=windows.renew_dhcp_lease,
        )
    )

    # 21. Process Details (Phase 8 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_process_details",
            domain="performance",
            description="Retrieve detailed read-only diagnostics, thread count, and memory metrics for a process.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "pid": ParameterSpec(
                    name="pid",
                    param_type=int,
                    required=True,
                    min_value=0,
                    max_value=2147483647,
                    description="Process ID to inspect.",
                )
            },
            handler=windows.get_process_details,
        )
    )

    # 22. Disk Performance Diagnostics (Phase 8 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_disk_performance_diagnostics",
            domain="performance",
            description="Inspect partition occupancy and real-time disk read/write throughput counters.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_disk_performance_diagnostics,
        )
    )

    # 23. Resource Snapshot (Phase 8 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_resource_snapshot",
            domain="performance",
            description="Capture a point-in-time snapshot of CPU, RAM, swap, disk usage, and top consumer processes.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_resource_snapshot,
        )
    )

    # 24. Terminate User Process (Phase 8 Repair)
    registry.register(
        ToolDefinition(
            name="terminate_user_process",
            domain="performance",
            description="Terminate a runaway user-space process with strict protection for critical Windows services.",
            risk=RiskLevel.MEDIUM,
            requires_admin=False,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_process_details",
            parameters={
                "pid": ParameterSpec(
                    name="pid",
                    param_type=int,
                    required=True,
                    min_value=5,
                    max_value=2147483647,
                    description="Process ID of the user process to terminate.",
                ),
                "process_name": ParameterSpec(
                    name="process_name",
                    param_type=str,
                    required=False,
                    default=None,
                    max_value=128,
                    description="Expected executable name to ensure PID target integrity.",
                ),
            },
            handler=windows.terminate_user_process,
        )
    )

    # 25. Clean User Temp Cache (Phase 8/9 Repair)
    registry.register(
        ToolDefinition(
            name="clean_user_temp_cache",
            domain="storage",
            description="Safely purge obsolete cached files from the current user temporary directory.",
            risk=RiskLevel.MEDIUM,
            requires_admin=False,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_temp_storage_info",
            parameters={
                "max_file_age_hours": ParameterSpec(
                    name="max_file_age_hours",
                    param_type=float,
                    required=False,
                    default=0.0,
                    min_value=0.0,
                    max_value=8760.0,
                    description="Minimum age of temporary files in hours before purging (0.0 cleans all unlockable files).",
                ),
                "dry_run": ParameterSpec(
                    name="dry_run",
                    param_type=bool,
                    required=False,
                    default=False,
                    description="Simulate cache cleanup without deleting files.",
                ),
            },
            handler=windows.clean_user_temp_cache,
        )
    )

    # 26. Storage Pressure Analysis (Phase 9 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_storage_pressure_analysis",
            domain="storage",
            description="Analyze storage volume capacity and compute deterministic pressure severity levels.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_storage_pressure_analysis,
        )
    )

    # 27. Analyze Large Temporary Files (Phase 9 Diagnostic)
    registry.register(
        ToolDefinition(
            name="analyze_large_temporary_files",
            domain="storage",
            description="Inspect the user temporary directory to identify bounded large files exceeding a threshold.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "min_size_mb": ParameterSpec(
                    name="min_size_mb",
                    param_type=float,
                    required=False,
                    default=50.0,
                    min_value=1.0,
                    max_value=10000.0,
                    description="Minimum file size in megabytes to match.",
                ),
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=20,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of large files to return.",
                ),
            },
            handler=windows.analyze_large_temporary_files,
        )
    )

    # 28. Services Diagnostics (Phase 10 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_services_diagnostics",
            domain="services",
            description="Enumerate Windows services inventory with bounded limits, normalized statuses, and startup configurations.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=50,
                    min_value=1,
                    max_value=100,
                    description="Maximum number of services to return.",
                ),
                "filter_status": ParameterSpec(
                    name="filter_status",
                    param_type=str,
                    required=False,
                    default=None,
                    max_value=32,
                    description="Optional status filter (e.g., 'RUNNING', 'STOPPED').",
                ),
            },
            handler=windows.get_services_diagnostics,
        )
    )

    # 29. Service Details (Phase 10 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_service_details",
            domain="services",
            description="Retrieve comprehensive metadata, description, startup type, and account information for a specific Windows service.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "service_name": ParameterSpec(
                    name="service_name",
                    param_type=str,
                    required=True,
                    max_value=128,
                    description="Exact name of the Windows service.",
                ),
            },
            handler=windows.get_service_details,
        )
    )

    # 30. Start Service (Phase 10 Repair)
    registry.register(
        ToolDefinition(
            name="start_service",
            domain="services",
            description="Start a specific approved stopped Windows service via native Windows Service Control APIs.",
            risk=RiskLevel.MEDIUM,
            requires_admin=True,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_service_status",
            parameters={
                "service_name": ParameterSpec(
                    name="service_name",
                    param_type=str,
                    required=True,
                    max_value=128,
                    description="Exact name of the Windows service to start.",
                ),
            },
            handler=windows.start_service,
        )
    )

    # 31. Stop Service (Phase 10 Repair)
    registry.register(
        ToolDefinition(
            name="stop_service",
            domain="services",
            description="Gracefully stop a specific approved non-critical Windows service via native Windows Service Control APIs.",
            risk=RiskLevel.MEDIUM,
            requires_admin=True,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_service_status",
            parameters={
                "service_name": ParameterSpec(
                    name="service_name",
                    param_type=str,
                    required=True,
                    max_value=128,
                    description="Exact name of the Windows service to stop.",
                ),
            },
            handler=windows.stop_service,
        )
    )

    # 32. Restart Service (Phase 10 Repair)
    registry.register(
        ToolDefinition(
            name="restart_service",
            domain="services",
            description="Restart a specific approved non-critical Windows service using sequential stop and start verification.",
            risk=RiskLevel.MEDIUM,
            requires_admin=True,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_service_status",
            parameters={
                "service_name": ParameterSpec(
                    name="service_name",
                    param_type=str,
                    required=True,
                    max_value=128,
                    description="Exact name of the Windows service to restart.",
                ),
            },
            handler=windows.restart_service,
        )
    )

    # 33. Bluetooth Adapters (Phase 11 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_bluetooth_adapters",
            domain="bluetooth",
            description="Inspect hardware controllers and adapters for the Windows Bluetooth subsystem.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_bluetooth_adapters,
        )
    )

    # 34. Bluetooth Radio Status (Phase 11 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_bluetooth_radio_status",
            domain="bluetooth",
            description="Inspect operational radio power and hardware controller state for Bluetooth.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_bluetooth_radio_status,
        )
    )

    # 35. Bluetooth Devices (Phase 11 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_bluetooth_devices",
            domain="bluetooth",
            description="Enumerate paired and known Bluetooth peripheral devices in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_bluetooth_devices,
        )
    )

    # 36. Bluetooth Service Status (Phase 11 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_bluetooth_service_status",
            domain="bluetooth",
            description="Inspect the operational state and startup configuration of the Bluetooth Support Service.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_bluetooth_service_status,
        )
    )

    # 37. Restart Bluetooth Service (Phase 11 Repair)
    registry.register(
        ToolDefinition(
            name="restart_bluetooth_service",
            domain="bluetooth",
            description="Restart the Windows Bluetooth Support Service ('bthserv') with sequential stop and start verification.",
            risk=RiskLevel.MEDIUM,
            requires_admin=True,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_service_status",
            handler=windows.restart_bluetooth_service,
        )
    )

    # 38. Windows Update Service Status (Phase 12 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_windows_update_service_status",
            domain="windows_update",
            description="Inspect the operational state and startup configuration of the Windows Update service ('wuauserv').",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_windows_update_service_status,
        )
    )

    # 39. Windows Update Dependency Services (Phase 12 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_windows_update_dependency_services",
            domain="windows_update",
            description="Inspect the operational state of critical services required by Windows Update (BITS, CryptSvc, RpcSs, DcomLaunch).",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_windows_update_dependency_services,
        )
    )

    # 40. Windows Update Configuration (Phase 12 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_windows_update_configuration",
            domain="windows_update",
            description="Inspect Windows Update registry policies and settings (AUOptions, WSUS, scheduled time) in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_windows_update_configuration,
        )
    )

    # 41. Windows Update History (Phase 12 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_windows_update_history",
            domain="windows_update",
            description="Query recent Windows Update installation and update history in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=20,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of update history records to retrieve.",
                ),
            },
            handler=windows.get_windows_update_history,
        )
    )

    # 42. Windows Update Errors (Phase 12 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_windows_update_errors",
            domain="windows_update",
            description="Inspect recent Windows Update failure events and error codes from the Windows Event Log in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=20,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of error records to retrieve.",
                ),
            },
            handler=windows.get_windows_update_errors,
        )
    )

    # 43. Windows Update Health (Phase 12 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_windows_update_health",
            domain="windows_update",
            description="Synthesize a factual, high-level health assessment of the Windows Update subsystem based on observed evidence.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_windows_update_health,
        )
    )

    # 44. Restart Windows Update Service (Phase 12 Repair)
    registry.register(
        ToolDefinition(
            name="restart_windows_update_service",
            domain="windows_update",
            description="Restart the Windows Update service ('wuauserv') with sequential stop and start verification.",
            risk=RiskLevel.MEDIUM,
            requires_admin=True,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_windows_update_service_status",
            handler=windows.restart_windows_update_service,
        )
    )

    # 45. Defender Service Status (Phase 13 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_defender_service_status",
            domain="defender",
            description="Inspect the operational state and startup configuration of the Microsoft Defender Antivirus service ('WinDefend').",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_defender_service_status,
        )
    )

    # 46. Defender Security Health (Phase 13 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_defender_security_health",
            domain="defender",
            description="Synthesize a factual, high-level health assessment of Microsoft Defender based on observable signals.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_defender_security_health,
        )
    )

    # 47. Defender Real-time Protection Status (Phase 13 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_defender_realtime_protection_status",
            domain="defender",
            description="Inspect whether Microsoft Defender real-time protection is currently enabled in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_defender_realtime_protection_status,
        )
    )

    # 48. Defender Antivirus Status (Phase 13 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_defender_antivirus_status",
            domain="defender",
            description="Inspect Microsoft Defender antivirus engine, signature versions, and provider state in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_defender_antivirus_status,
        )
    )

    # 49. Defender Threat Status (Phase 13 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_defender_threat_status",
            domain="defender",
            description="Query current active, detected, or unresolved malware and security threats in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_defender_threat_status,
        )
    )

    # 50. Defender Recent Events (Phase 13 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_defender_recent_events",
            domain="defender",
            description="Inspect recent Microsoft Defender operational log events and detection records from Windows Event Log.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=20,
                    min_value=1,
                    max_value=100,
                    description="Maximum number of Defender event records to retrieve.",
                ),
                "max_scan": ParameterSpec(
                    name="max_scan",
                    param_type=int,
                    required=False,
                    default=200,
                    min_value=10,
                    max_value=1000,
                    description="Maximum number of log records to scan backwards.",
                ),
            },
            handler=windows.get_defender_recent_events,
        )
    )

    # 51. Defender Configuration (Phase 13 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_defender_configuration",
            domain="defender",
            description="Inspect allowlisted Microsoft Defender configuration and registry policies in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_defender_configuration,
        )
    )

    # 52. Restart Defender Service (Phase 13 Repair)
    registry.register(
        ToolDefinition(
            name="restart_defender_service",
            domain="defender",
            description="Restart the Microsoft Defender Antivirus service ('WinDefend') with sequential stop and start verification.",
            risk=RiskLevel.MEDIUM,
            requires_admin=True,
            automatic_allowed=False,
            read_only=False,
            verification_tool="get_defender_service_status",
            handler=windows.restart_defender_service,
        )
    )

    # 53. Application Crash Details (Phase 14 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_application_crash_details",
            domain="applications",
            description="Retrieve detailed crash records for a specific application name from Windows Event Log.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "application_name": ParameterSpec(
                    name="application_name",
                    param_type=str,
                    required=False,
                    default=None,
                    description="Optional application executable name to filter crash details for.",
                ),
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=10,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of crash detail records to return.",
                ),
                "max_scan": ParameterSpec(
                    name="max_scan",
                    param_type=int,
                    required=False,
                    default=200,
                    min_value=10,
                    max_value=1000,
                    description="Maximum number of log events to scan backwards.",
                ),
            },
            handler=windows.get_application_crash_details,
        )
    )

    # 54. Application Crash Summary (Phase 14 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_application_crash_summary",
            domain="applications",
            description="Aggregate high-level summary of recent application crashes across a bounded time window.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "time_window": ParameterSpec(
                    name="time_window",
                    param_type=str,
                    required=False,
                    default="24h",
                    allowed_values=["1h", "6h", "24h", "7d", "30d"],
                    description="Time window for aggregating crash metrics ('1h', '6h', '24h', '7d', '30d').",
                ),
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=20,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of crash events to inspect.",
                ),
                "max_scan": ParameterSpec(
                    name="max_scan",
                    param_type=int,
                    required=False,
                    default=200,
                    min_value=10,
                    max_value=1000,
                    description="Maximum number of log records to scan backwards.",
                ),
            },
            handler=windows.get_application_crash_summary,
        )
    )

    # 55. Application Crash Frequency (Phase 14 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_application_crash_frequency",
            domain="applications",
            description="Calculate deterministic recurrence frequencies and time-window metrics for application crashes.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "time_window": ParameterSpec(
                    name="time_window",
                    param_type=str,
                    required=False,
                    default="24h",
                    allowed_values=["1h", "6h", "24h", "7d", "30d"],
                    description="Time window for frequency calculation ('1h', '6h', '24h', '7d', '30d').",
                ),
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=20,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of crash events to inspect.",
                ),
                "max_scan": ParameterSpec(
                    name="max_scan",
                    param_type=int,
                    required=False,
                    default=200,
                    min_value=10,
                    max_value=1000,
                    description="Maximum number of log records to scan backwards.",
                ),
            },
            handler=windows.get_application_crash_frequency,
        )
    )

    # 56. Faulting Module Information (Phase 14 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_faulting_module_information",
            domain="applications",
            description="Inspect observed faulting modules and DLL associations from crash event records in read-only mode.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "module_name": ParameterSpec(
                    name="module_name",
                    param_type=str,
                    required=False,
                    default=None,
                    description="Optional DLL or binary module name to filter observed faults for.",
                ),
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=10,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of module records to retrieve.",
                ),
                "max_scan": ParameterSpec(
                    name="max_scan",
                    param_type=int,
                    required=False,
                    default=200,
                    min_value=10,
                    max_value=1000,
                    description="Maximum number of log events to scan backwards.",
                ),
            },
            handler=windows.get_faulting_module_information,
        )
    )

    # 57. Windows Error Reporting Status (Phase 14 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_windows_error_reporting_status",
            domain="applications",
            description="Inspect Windows Error Reporting (WER) service status and read-only policy configuration.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_windows_error_reporting_status,
        )
    )

    # 58. Application Crash Events (Phase 14 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_application_crash_events",
            domain="applications",
            description="Retrieve bounded, sanitized application crash event records filtered by time window and application.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "time_window": ParameterSpec(
                    name="time_window",
                    param_type=str,
                    required=False,
                    default="24h",
                    allowed_values=["1h", "6h", "24h", "7d", "30d"],
                    description="Time window for event collection ('1h', '6h', '24h', '7d', '30d').",
                ),
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=10,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of events to return.",
                ),
                "max_scan": ParameterSpec(
                    name="max_scan",
                    param_type=int,
                    required=False,
                    default=200,
                    min_value=10,
                    max_value=1000,
                    description="Maximum number of log records to scan backwards.",
                ),
                "application_name": ParameterSpec(
                    name="application_name",
                    param_type=str,
                    required=False,
                    default=None,
                    description="Optional application executable name to filter crash events for.",
                ),
            },
            handler=windows.get_application_crash_events,
        )
    )

    # 59. Application Crash Diagnostics Orchestrator (Phase 14 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_application_crash_diagnostics",
            domain="applications",
            description="Perform complete structured diagnostic analysis of Windows application crash evidence and WER state.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            parameters={
                "time_window": ParameterSpec(
                    name="time_window",
                    param_type=str,
                    required=False,
                    default="24h",
                    allowed_values=["1h", "6h", "24h", "7d", "30d"],
                    description="Time window for crash analysis ('1h', '6h', '24h', '7d', '30d').",
                ),
                "limit": ParameterSpec(
                    name="limit",
                    param_type=int,
                    required=False,
                    default=10,
                    min_value=1,
                    max_value=50,
                    description="Maximum number of crash events to analyze.",
                ),
            },
            handler=windows.get_application_crash_diagnostics,
        )
    )

    # 60. Display Diagnostics (Phase 30 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_display_diagnostics",
            domain="display",
            description="Inspect display adapters, active monitors, screen resolution, and Night Light status.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_display_diagnostics,
        )
    )

    # 61. Audio Diagnostics (Phase 30 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_audio_diagnostics",
            domain="audio",
            description="Inspect Windows Audio subsystem health, core audio services, and device counts.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_audio_diagnostics,
        )
    )

    # 62. Audio Endpoint Status (Phase 30 Diagnostic)
    registry.register(
        ToolDefinition(
            name="get_audio_endpoint_status",
            domain="audio",
            description="Inspect status of audio playback and recording endpoints.",
            risk=RiskLevel.SAFE,
            requires_admin=False,
            automatic_allowed=True,
            read_only=True,
            handler=windows.get_audio_endpoint_status,
        )
    )

    return registry



# Shared default global registry instance
default_tool_registry = create_default_registry()


