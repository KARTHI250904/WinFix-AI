"""Read-only Windows Services Diagnostic Tools for WinFix AI (Phase 10).

Provides structured service status, bounded service inventory, detailed service inspection,
and normalized startup type analysis without altering service states or configurations.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)

# List of common Windows services relevant to system operations and troubleshooting
ALLOWLISTED_COMMON_SERVICES = [
    {"name": "wuauserv", "display_name": "Windows Update", "domain": "windows_update"},
    {"name": "bits", "display_name": "Background Intelligent Transfer Service", "domain": "windows_update"},
    {"name": "Spooler", "display_name": "Print Spooler", "domain": "printer"},
    {"name": "bthserv", "display_name": "Bluetooth Support Service", "domain": "bluetooth"},
    {"name": "WinDefend", "display_name": "Microsoft Defender Antivirus Service", "domain": "defender"},
    {"name": "Dhcp", "display_name": "DHCP Client", "domain": "network"},
    {"name": "Dnscache", "display_name": "DNS Client", "domain": "network"},
    {"name": "W32Time", "display_name": "Windows Time", "domain": "system"},
    {"name": "mpssvc", "display_name": "Windows Defender Firewall", "domain": "defender"},
    {"name": "EventLog", "display_name": "Windows Event Log", "domain": "system"},
]

# Canonical normalized service status mappings
STATUS_NORMALIZATION_MAP = {
    "running": "RUNNING",
    "stopped": "STOPPED",
    "start_pending": "START_PENDING",
    "stop_pending": "STOP_PENDING",
    "paused": "PAUSED",
    "pause_pending": "PAUSE_PENDING",
    "continue_pending": "CONTINUE_PENDING",
}

# Canonical normalized startup type mappings
STARTUP_NORMALIZATION_MAP = {
    "automatic": "AUTO",
    "auto": "AUTO",
    "manual": "DEMAND",
    "demand": "DEMAND",
    "disabled": "DISABLED",
    "boot": "BOOT",
    "system": "SYSTEM",
}


def normalize_service_status(status_str: Optional[str]) -> str:
    """Normalize native Windows service status into canonical uppercase string."""
    if not status_str or not isinstance(status_str, str):
        return "UNKNOWN"
    clean = status_str.strip().lower()
    return STATUS_NORMALIZATION_MAP.get(clean, clean.upper() if clean else "UNKNOWN")


def normalize_startup_type(startup_str: Optional[str]) -> str:
    """Normalize native Windows startup type into canonical uppercase string."""
    if not startup_str or not isinstance(startup_str, str):
        return "UNKNOWN"
    clean = startup_str.strip().lower()
    return STARTUP_NORMALIZATION_MAP.get(clean, clean.upper() if clean else "UNKNOWN")


def validate_service_name(service_name: Optional[str]) -> tuple[bool, str, Optional[str]]:
    """Validate and sanitize a Windows service identifier.

    Rejects empty names, command separators, path characters, shell metacharacters, and excessive length.
    """
    if not service_name or not isinstance(service_name, str):
        return False, "", "Service name must be a non-empty string."

    cleaned = service_name.strip()
    if not cleaned:
        return False, "", "Service name cannot be empty."

    if len(cleaned) > 128:
        return False, "", "Service name exceeds maximum permitted length of 128 characters."

    # Forbidden shell metacharacters, command separators, and path traversal tokens
    forbidden_chars = [";", "&", "|", "`", "$", "\n", "\r", "<", ">", "\\", "/", ":", "..", '"', "'"]
    for ch in forbidden_chars:
        if ch in cleaned:
            return False, "", f"Service name contains forbidden character or separator '{ch}'."

    # Windows service names must match standard identifier pattern
    if not re.match(r"^[a-zA-Z0-9_\-\. ]+$", cleaned):
        return False, "", f"Invalid service name format: '{cleaned}'."

    return True, cleaned, None


def get_service_status(service_name: str) -> Dict[str, Any]:
    """Query the read-only status and startup configuration of a specific Windows service."""
    tool_name = "get_service_status"
    domain = "services"

    valid, clean_name, err_msg = validate_service_name(service_name)
    if not valid:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "INVALID_SERVICE_NAME", "message": err_msg or "Invalid service name."},
        }

    try:
        service = psutil.win_service_get(clean_name)
        info = service.as_dict()

        raw_status = info.get("status")
        raw_start = info.get("start_type")
        norm_status = normalize_service_status(raw_status)
        norm_start = normalize_startup_type(raw_start)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "name": info.get("name") or clean_name,
                "display_name": info.get("display_name") or clean_name,
                "status": norm_status,
                "start_type": norm_start,
                "is_running": norm_status == "RUNNING",
                "pid": info.get("pid"),
            },
            "error": None,
        }
    except psutil.NoSuchProcess:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "name": clean_name,
                "status": "NOT_INSTALLED",
                "is_running": False,
            },
            "error": {"code": "SERVICE_NOT_FOUND", "message": f"Service '{clean_name}' is not installed on this system."},
        }
    except Exception as exc:
        logger.error("%s failed for %s: %s", tool_name, clean_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "SERVICE_QUERY_ERROR", "message": str(exc)},
        }


def get_service_details(service_name: str) -> Dict[str, Any]:
    """Retrieve comprehensive read-only metadata and description for a specific Windows service."""
    tool_name = "get_service_details"
    domain = "services"

    valid, clean_name, err_msg = validate_service_name(service_name)
    if not valid:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "INVALID_SERVICE_NAME", "message": err_msg or "Invalid service name."},
        }

    try:
        service = psutil.win_service_get(clean_name)
        info = service.as_dict()

        norm_status = normalize_service_status(info.get("status"))
        norm_start = normalize_startup_type(info.get("start_type"))

        # Safe description retrieval
        desc = ""
        try:
            desc = service.description() or ""
        except Exception:
            pass

        # Safe username/account retrieval
        account = ""
        try:
            account = info.get("username") or ""
        except Exception:
            pass

        # Safe binary path retrieval
        bin_path = ""
        try:
            bin_path = info.get("binpath") or ""
        except Exception:
            pass

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "name": info.get("name") or clean_name,
                "display_name": info.get("display_name") or clean_name,
                "status": norm_status,
                "start_type": norm_start,
                "is_running": norm_status == "RUNNING",
                "description": desc,
                "account": account,
                "binpath": bin_path,
                "pid": info.get("pid"),
            },
            "error": None,
        }
    except psutil.NoSuchProcess:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "name": clean_name,
                "status": "NOT_INSTALLED",
                "is_running": False,
            },
            "error": {"code": "SERVICE_NOT_FOUND", "message": f"Service '{clean_name}' is not installed on this system."},
        }
    except Exception as exc:
        logger.error("%s failed for %s: %s", tool_name, clean_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "SERVICE_DETAILS_ERROR", "message": str(exc)},
        }


def get_services_diagnostics(
    limit: int = 50,
    filter_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Enumerate Windows services inventory with bounded limits and normalized state fields."""
    tool_name = "get_services_diagnostics"
    domain = "services"
    try:
        bounded_limit = max(1, min(limit, 100))
        filter_clean = filter_status.strip().upper() if filter_status else None

        services_list: List[Dict[str, Any]] = []
        total_running = 0
        total_stopped = 0

        for svc in psutil.win_service_iter():
            try:
                info = svc.as_dict()
                norm_status = normalize_service_status(info.get("status"))
                norm_start = normalize_startup_type(info.get("start_type"))

                if norm_status == "RUNNING":
                    total_running += 1
                elif norm_status == "STOPPED":
                    total_stopped += 1

                if filter_clean and norm_status != filter_clean:
                    continue

                if len(services_list) < bounded_limit:
                    services_list.append({
                        "name": info.get("name") or "Unknown",
                        "display_name": info.get("display_name") or "Unknown",
                        "status": norm_status,
                        "start_type": norm_start,
                        "is_running": norm_status == "RUNNING",
                        "pid": info.get("pid"),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "total_services_scanned": total_running + total_stopped,
                "total_running": total_running,
                "total_stopped": total_stopped,
                "filter_applied": filter_clean,
                "returned_count": len(services_list),
                "services": services_list,
            },
            "error": None,
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "SERVICES_DIAG_ERROR", "message": str(exc)},
        }


def list_common_services() -> Dict[str, Any]:
    """Inspect the status of all standard allowlisted troubleshooting services."""
    tool_name = "list_common_services"
    domain = "services"
    try:
        service_statuses: List[Dict[str, Any]] = []
        for svc_meta in ALLOWLISTED_COMMON_SERVICES:
            s_name = svc_meta["name"]
            res = get_service_status(s_name)
            if res["success"]:
                item = res["data"]
                item["category"] = svc_meta["domain"]
                service_statuses.append(item)
            else:
                service_statuses.append(
                    {
                        "name": s_name,
                        "display_name": svc_meta["display_name"],
                        "category": svc_meta["domain"],
                        "status": "NOT_INSTALLED" if res["error"]["code"] == "SERVICE_NOT_FOUND" else "ERROR",
                        "start_type": "UNKNOWN",
                        "is_running": False,
                    }
                )

        running_count = sum(1 for s in service_statuses if s.get("is_running"))

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "total_monitored": len(service_statuses),
                "running_count": running_count,
                "services": service_statuses,
            },
            "error": None,
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "SERVICES_LIST_ERROR", "message": str(exc)},
        }
