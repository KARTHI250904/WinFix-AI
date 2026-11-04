"""Windows Diagnostic and Repair Tools Package for WinFix AI.

Exposes read-only Windows diagnostic tools across all supported troubleshooting domains
and controlled allowlisted Phase 7, 8 & 9 repair operations.
"""

from windows.bluetooth_repairs import (
    BLUETOOTH_SERVICE_NAME,
    restart_bluetooth_service,
)
from windows.bluetooth_tools import (
    get_bluetooth_adapters,
    get_bluetooth_devices,
    get_bluetooth_diagnostics,
    get_bluetooth_radio_status,
    get_bluetooth_service_status,
)
from windows.defender_tools import (
    get_defender_antivirus_status,
    get_defender_configuration,
    get_defender_diagnostics,
    get_defender_realtime_protection_status,
    get_defender_recent_events,
    get_defender_security_health,
    get_defender_service_status,
    get_defender_threat_status,
)
from windows.application_crash_tools import (
    get_application_crash_details,
    get_application_crash_diagnostics,
    get_application_crash_events,
    get_application_crash_frequency,
    get_application_crash_summary,
    get_faulting_module_information,
    get_recent_application_crashes,
    get_windows_error_reporting_status,
)
from windows.network_repairs import flush_dns_cache, renew_dhcp_lease

from windows.network_tools import (
    check_dns_resolution,
    check_internet_connectivity,
    get_dns_client_config,
    get_network_adapters_diagnostics,
)
from windows.performance_repairs import (
    clean_user_temp_cache,
    is_process_termination_blocked,
    terminate_user_process,
)
from windows.performance_tools import (
    get_cpu_diagnostics,
    get_disk_performance_diagnostics,
    get_memory_diagnostics,
    get_process_details,
    get_resource_snapshot,
    get_top_cpu_processes,
    get_top_memory_processes,
)
from windows.printer_tools import get_printer_diagnostics
from windows.service_repairs import (
    is_service_stop_protected,
    restart_service,
    start_service,
    stop_service,
)
from windows.service_tools import (
    get_service_details,
    get_service_status,
    get_services_diagnostics,
    list_common_services,
)
from windows.storage_tools import (
    analyze_large_temporary_files,
    calculate_storage_pressure_level,
    get_storage_diagnostics,
    get_storage_pressure_analysis,
    get_temp_storage_info,
)
from windows.system_info import get_complete_system_info
from windows.windows_defender_repairs import (
    DEFENDER_SERVICE_NAME,
    restart_defender_service,
)
from windows.windows_update_repairs import (
    WINDOWS_UPDATE_SERVICE_NAME,
    restart_windows_update_service,
)
from windows.windows_update_tools import (
    get_windows_update_configuration,
    get_windows_update_dependency_services,
    get_windows_update_diagnostics,
    get_windows_update_errors,
    get_windows_update_health,
    get_windows_update_history,
    get_windows_update_service_status,
)

from windows.audio_tools import (
    get_audio_diagnostics,
    get_audio_endpoint_status,
)
from windows.display_tools import get_display_diagnostics

__all__ = [
    "get_complete_system_info",
    "get_network_adapters_diagnostics",
    "check_dns_resolution",
    "check_internet_connectivity",
    "get_dns_client_config",
    "flush_dns_cache",
    "renew_dhcp_lease",
    "get_cpu_diagnostics",
    "get_memory_diagnostics",
    "get_top_cpu_processes",
    "get_top_memory_processes",
    "get_process_details",
    "get_disk_performance_diagnostics",
    "get_resource_snapshot",
    "terminate_user_process",
    "clean_user_temp_cache",
    "is_process_termination_blocked",
    "get_storage_diagnostics",
    "get_storage_pressure_analysis",
    "get_temp_storage_info",
    "analyze_large_temporary_files",
    "calculate_storage_pressure_level",
    "get_service_status",
    "get_service_details",
    "get_services_diagnostics",
    "list_common_services",
    "start_service",
    "stop_service",
    "restart_service",
    "is_service_stop_protected",
    "get_bluetooth_diagnostics",
    "get_bluetooth_adapters",
    "get_bluetooth_radio_status",
    "get_bluetooth_devices",
    "get_bluetooth_service_status",
    "restart_bluetooth_service",
    "get_windows_update_service_status",
    "get_windows_update_dependency_services",
    "get_windows_update_diagnostics",
    "get_windows_update_history",
    "get_windows_update_errors",
    "get_windows_update_configuration",
    "get_windows_update_health",
    "restart_windows_update_service",
    "get_printer_diagnostics",
    "get_defender_diagnostics",
    "get_defender_service_status",
    "get_defender_security_health",
    "get_defender_realtime_protection_status",
    "get_defender_antivirus_status",
    "get_defender_threat_status",
    "get_defender_recent_events",
    "get_defender_configuration",
    "DEFENDER_SERVICE_NAME",
    "restart_defender_service",
    "get_recent_application_crashes",
    "get_application_crash_details",
    "get_application_crash_summary",
    "get_application_crash_frequency",
    "get_faulting_module_information",
    "get_windows_error_reporting_status",
    "get_application_crash_events",
    "get_application_crash_diagnostics",
    "get_display_diagnostics",
    "get_audio_diagnostics",
    "get_audio_endpoint_status",
]



