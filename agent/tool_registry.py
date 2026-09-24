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

    return registry


# Shared default global registry instance
default_tool_registry = create_default_registry()


