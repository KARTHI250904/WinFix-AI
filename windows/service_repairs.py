"""Controlled Windows Service Repair Operations for WinFix AI (Phase 10).

Provides explicit, safe, bounded service state-changing operations (start, stop, restart)
implemented directly through native Windows Service APIs (win32serviceutil / win32service / ctypes).

Adheres strictly to the core security architecture:
- Zero subprocess / os.system / powershell / cmd / sc.exe / net.exe
- Strict input validation (no path traversal, no command separators)
- Protected service policy (blocks stopping or restarting critical/security services)
- Bounded timeouts (no infinite loops or hangs)
- Deterministic verification and before/after state capture
"""

import logging
import platform
import time
from typing import Any, Dict, Optional, Set

from windows.service_tools import (
    get_service_status,
    validate_service_name,
)

logger = logging.getLogger(__name__)

# List of critical system and security services strictly protected from stopping or restarting
PROTECTED_SERVICES: Set[str] = {
    "windefend",
    "wdnissvc",
    "mpssvc",
    "bfe",
    "eventlog",
    "rpcss",
    "rpceptmapper",
    "dcomlaunch",
    "plugplay",
    "lsm",
    "samss",
    "profsvc",
    "schedule",
    "winmgmt",
    "cryptsvc",
    "bits",
    "wuauserv",
    "dhcp",
    "dnscache",
    "wscsvc",
    "securityhealthservice",
    "appinfo",
    "lsass",
    "smss",
    "csrss",
    "services",
}

# Maximum time in seconds to poll for service state transitions
SERVICE_OPERATION_TIMEOUT_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 0.5


def is_service_stop_protected(service_name: str) -> tuple[bool, str]:
    """Check whether a service is protected against stopping or restarting.

    Returns:
        tuple[bool, str]: (is_protected, reason)
    """
    valid, clean_name, err = validate_service_name(service_name)
    if not valid:
        return True, err or "Invalid service name."

    if clean_name.lower() in PROTECTED_SERVICES:
        return (
            True,
            f"Service '{clean_name}' is a critical Windows system or security service and cannot be stopped or restarted.",
        )

    return False, ""


def _wait_for_service_status(
    service_name: str,
    target_status: str,
    timeout_seconds: float = SERVICE_OPERATION_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Poll the service status until it matches target_status or timeout occurs.

    Returns:
        tuple[bool, str]: (matched, final_status)
    """
    start_time = time.time()
    last_status = "UNKNOWN"

    while (time.time() - start_time) < timeout_seconds:
        status_res = get_service_status(service_name)
        if status_res["success"] and status_res.get("data"):
            last_status = status_res["data"].get("status", "UNKNOWN")
            if last_status == target_status:
                return True, last_status
        time.sleep(POLL_INTERVAL_SECONDS)

    # Final query
    final_res = get_service_status(service_name)
    if final_res["success"] and final_res.get("data"):
        last_status = final_res["data"].get("status", "UNKNOWN")

    return last_status == target_status, last_status


def start_service(service_name: str) -> Dict[str, Any]:
    """Start a specific approved Windows service using native Windows Service APIs.

    Follows deterministic verification:
    1. Validates service name
    2. Queries before-state
    3. Calls native Windows Service Start API
    4. Polls for RUNNING state within bounded timeout
    5. Returns structured result with verification status
    """
    tool_name = "start_service"
    domain = "services"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Service management is only supported on Windows."},
        }

    # 1. Validate service name
    valid, clean_name, err_msg = validate_service_name(service_name)
    if not valid:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "INVALID_SERVICE_NAME", "message": err_msg or "Invalid service name."},
        }

    # 2. Capture before-state
    before_res = get_service_status(clean_name)
    if not before_res["success"]:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": before_res.get("error", {"code": "SERVICE_QUERY_FAILED", "message": "Failed to query before-state."}),
        }

    before_data = before_res["data"]
    before_status = before_data.get("status", "UNKNOWN")

    # If already running, no state change needed
    if before_status == "RUNNING":
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": clean_name,
                "display_name": before_data.get("display_name", clean_name),
                "operation": "start",
                "before_state": before_status,
                "after_state": "RUNNING",
                "verification": "verified",
                "message": f"Service '{clean_name}' is already RUNNING.",
            },
            "error": None,
        }

    # Check if disabled
    if before_data.get("start_type") == "DISABLED":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": clean_name,
                "before_state": before_status,
                "after_state": before_status,
                "verification": "blocked",
            },
            "error": {
                "code": "SERVICE_DISABLED",
                "message": f"Cannot start service '{clean_name}' because its startup type is DISABLED.",
            },
        }

    # 3. Execute native StartService API
    try:
        import win32serviceutil
        import pywintypes

        try:
            win32serviceutil.StartService(clean_name)
        except pywintypes.error as win_err:
            # Error 1056: An instance of the service is already running
            if win_err.winerror != 1056:
                raise win_err
    except ImportError:
        # Fallback to ctypes Advapi32 if pywin32 is not directly imported
        try:
            import ctypes
            advapi32 = ctypes.windll.advapi32
            SC_MANAGER_ALL_ACCESS = 0xF003F
            SERVICE_START = 0x0010
            SERVICE_QUERY_STATUS = 0x0004

            schSCManager = advapi32.OpenSCManagerW(None, None, SC_MANAGER_ALL_ACCESS)
            if not schSCManager:
                return {
                    "success": False,
                    "tool": tool_name,
                    "domain": domain,
                    "data": None,
                    "error": {"code": "ACCESS_DENIED", "message": "Failed to open Service Control Manager (Elevation required)."},
                }
            try:
                schService = advapi32.OpenServiceW(schSCManager, clean_name, SERVICE_START | SERVICE_QUERY_STATUS)
                if not schService:
                    return {
                        "success": False,
                        "tool": tool_name,
                        "domain": domain,
                        "data": None,
                        "error": {"code": "SERVICE_OPEN_FAILED", "message": f"Failed to open service '{clean_name}'."},
                    }
                try:
                    res = advapi32.StartServiceW(schService, 0, None)
                    if res == 0:
                        err_code = ctypes.windll.kernel32.GetLastError()
                        if err_code != 1056:  # ERROR_SERVICE_ALREADY_RUNNING
                            return {
                                "success": False,
                                "tool": tool_name,
                                "domain": domain,
                                "data": None,
                                "error": {"code": "START_SERVICE_FAILED", "message": f"StartService failed with error code {err_code}."},
                            }
                finally:
                    advapi32.CloseServiceHandle(schService)
            finally:
                advapi32.CloseServiceHandle(schSCManager)
        except Exception as fallback_exc:
            logger.error("StartService ctypes fallback error for %s: %s", clean_name, fallback_exc)
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": {"code": "START_SERVICE_FAILED", "message": str(fallback_exc)},
            }
    except Exception as exc:
        logger.error("StartService failed for %s: %s", clean_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "START_SERVICE_FAILED", "message": str(exc)},
        }

    # 4. Wait & Verify
    matched, final_status = _wait_for_service_status(clean_name, "RUNNING")
    verification = "verified" if matched else "not_verified"

    return {
        "success": matched,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "service_name": clean_name,
            "display_name": before_data.get("display_name", clean_name),
            "operation": "start",
            "before_state": before_status,
            "after_state": final_status,
            "verification": verification,
            "message": f"Service '{clean_name}' start {verification} (final state: {final_status}).",
        },
        "error": None if matched else {"code": "VERIFICATION_TIMEOUT", "message": f"Service did not reach RUNNING state in time. Current: {final_status}"},
    }


def stop_service(service_name: str) -> Dict[str, Any]:
    """Stop a specific approved Windows service using native Windows Service APIs.

    Follows conservative safety rules:
    1. Validates service name
    2. Checks protected-service policy (rejects system/security services)
    3. Queries before-state
    4. Calls native Windows Service Stop API (graceful control, no kill)
    5. Polls for STOPPED state within bounded timeout
    6. Returns structured result with verification status
    """
    tool_name = "stop_service"
    domain = "services"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Service management is only supported on Windows."},
        }

    # 1. Validate service name
    valid, clean_name, err_msg = validate_service_name(service_name)
    if not valid:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "INVALID_SERVICE_NAME", "message": err_msg or "Invalid service name."},
        }

    # 2. Check protected service policy
    is_protected, prot_reason = is_service_stop_protected(clean_name)
    if is_protected:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": clean_name,
                "operation": "stop",
                "verification": "blocked",
            },
            "error": {"code": "PROTECTED_SERVICE_BLOCKED", "message": prot_reason},
        }

    # 3. Capture before-state
    before_res = get_service_status(clean_name)
    if not before_res["success"]:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": before_res.get("error", {"code": "SERVICE_QUERY_FAILED", "message": "Failed to query before-state."}),
        }

    before_data = before_res["data"]
    before_status = before_data.get("status", "UNKNOWN")

    # If already stopped
    if before_status == "STOPPED":
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": clean_name,
                "display_name": before_data.get("display_name", clean_name),
                "operation": "stop",
                "before_state": before_status,
                "after_state": "STOPPED",
                "verification": "verified",
                "message": f"Service '{clean_name}' is already STOPPED.",
            },
            "error": None,
        }

    # 4. Execute native StopService API (Graceful control code)
    try:
        import win32serviceutil
        import pywintypes

        try:
            win32serviceutil.StopService(clean_name)
        except pywintypes.error as win_err:
            # Error 1062: The service has not been started
            if win_err.winerror != 1062:
                raise win_err
    except ImportError:
        try:
            import ctypes
            advapi32 = ctypes.windll.advapi32
            SC_MANAGER_ALL_ACCESS = 0xF003F
            SERVICE_STOP = 0x0020
            SERVICE_QUERY_STATUS = 0x0004
            SERVICE_CONTROL_STOP = 0x00000001

            class SERVICE_STATUS(ctypes.Structure):
                _fields_ = [
                    ("dwServiceType", ctypes.c_ulong),
                    ("dwCurrentState", ctypes.c_ulong),
                    ("dwControlsAccepted", ctypes.c_ulong),
                    ("dwWin32ExitCode", ctypes.c_ulong),
                    ("dwServiceSpecificExitCode", ctypes.c_ulong),
                    ("dwCheckPoint", ctypes.c_ulong),
                    ("dwWaitHint", ctypes.c_ulong),
                ]

            schSCManager = advapi32.OpenSCManagerW(None, None, SC_MANAGER_ALL_ACCESS)
            if not schSCManager:
                return {
                    "success": False,
                    "tool": tool_name,
                    "domain": domain,
                    "data": None,
                    "error": {"code": "ACCESS_DENIED", "message": "Failed to open Service Control Manager (Elevation required)."},
                }
            try:
                schService = advapi32.OpenServiceW(schSCManager, clean_name, SERVICE_STOP | SERVICE_QUERY_STATUS)
                if not schService:
                    return {
                        "success": False,
                        "tool": tool_name,
                        "domain": domain,
                        "data": None,
                        "error": {"code": "SERVICE_OPEN_FAILED", "message": f"Failed to open service '{clean_name}'."},
                    }
                try:
                    s_status = SERVICE_STATUS()
                    res = advapi32.ControlService(schService, SERVICE_CONTROL_STOP, ctypes.byref(s_status))
                    if res == 0:
                        err_code = ctypes.windll.kernel32.GetLastError()
                        if err_code != 1062:
                            return {
                                "success": False,
                                "tool": tool_name,
                                "domain": domain,
                                "data": None,
                                "error": {"code": "STOP_SERVICE_FAILED", "message": f"ControlService failed with code {err_code}."},
                            }
                finally:
                    advapi32.CloseServiceHandle(schService)
            finally:
                advapi32.CloseServiceHandle(schSCManager)
        except Exception as fallback_exc:
            logger.error("StopService ctypes fallback error for %s: %s", clean_name, fallback_exc)
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": {"code": "STOP_SERVICE_FAILED", "message": str(fallback_exc)},
            }
    except Exception as exc:
        logger.error("StopService failed for %s: %s", clean_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "STOP_SERVICE_FAILED", "message": str(exc)},
        }

    # 5. Wait & Verify
    matched, final_status = _wait_for_service_status(clean_name, "STOPPED")
    verification = "verified" if matched else "not_verified"

    return {
        "success": matched,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "service_name": clean_name,
            "display_name": before_data.get("display_name", clean_name),
            "operation": "stop",
            "before_state": before_status,
            "after_state": final_status,
            "verification": verification,
            "message": f"Service '{clean_name}' stop {verification} (final state: {final_status}).",
        },
        "error": None if matched else {"code": "VERIFICATION_TIMEOUT", "message": f"Service did not reach STOPPED state in time. Current: {final_status}"},
    }


def restart_service(service_name: str) -> Dict[str, Any]:
    """Restart a specific approved Windows service using sequential stop-and-start controls.

    Flow:
    1. Validate service name
    2. Check protected service policy
    3. Query before-state
    4. Stop service -> verify stopped
    5. Start service -> verify running
    6. Return structured result
    """
    tool_name = "restart_service"
    domain = "services"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Service management is only supported on Windows."},
        }

    # 1. Validate service name
    valid, clean_name, err_msg = validate_service_name(service_name)
    if not valid:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "INVALID_SERVICE_NAME", "message": err_msg or "Invalid service name."},
        }

    # 2. Check protected service policy
    is_protected, prot_reason = is_service_stop_protected(clean_name)
    if is_protected:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": clean_name,
                "operation": "restart",
                "verification": "blocked",
            },
            "error": {"code": "PROTECTED_SERVICE_BLOCKED", "message": prot_reason},
        }

    # 3. Capture before-state
    before_res = get_service_status(clean_name)
    if not before_res["success"]:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": before_res.get("error", {"code": "SERVICE_QUERY_FAILED", "message": "Failed to query before-state."}),
        }

    before_data = before_res["data"]
    before_status = before_data.get("status", "UNKNOWN")

    # If stopped, just start it
    if before_status == "STOPPED":
        start_res = start_service(clean_name)
        if start_res["success"]:
            return {
                "success": True,
                "tool": tool_name,
                "domain": domain,
                "data": {
                    "service_name": clean_name,
                    "display_name": before_data.get("display_name", clean_name),
                    "operation": "restart",
                    "before_state": before_status,
                    "after_state": start_res["data"].get("after_state", "RUNNING"),
                    "verification": "verified",
                    "message": f"Service '{clean_name}' was stopped and has been started successfully.",
                },
                "error": None,
            }
        else:
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": {
                    "service_name": clean_name,
                    "before_state": before_status,
                    "after_state": "STOPPED",
                    "verification": "failed",
                },
                "error": start_res.get("error", {"code": "START_FAILED", "message": "Failed to start service during restart."}),
            }

    # 4. Stop service
    stop_res = stop_service(clean_name)
    if not stop_res["success"]:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": clean_name,
                "before_state": before_status,
                "after_state": stop_res.get("data", {}).get("after_state", before_status),
                "verification": "failed",
            },
            "error": stop_res.get("error", {"code": "STOP_FAILED", "message": "Failed to stop service during restart sequence."}),
        }

    # 5. Start service
    start_res = start_service(clean_name)
    final_status = start_res.get("data", {}).get("after_state", "UNKNOWN") if start_res.get("data") else "UNKNOWN"
    verification = "verified" if start_res["success"] else "not_verified"

    return {
        "success": start_res["success"],
        "tool": tool_name,
        "domain": domain,
        "data": {
            "service_name": clean_name,
            "display_name": before_data.get("display_name", clean_name),
            "operation": "restart",
            "before_state": before_status,
            "after_state": final_status,
            "verification": verification,
            "message": f"Service '{clean_name}' restart {verification} (final state: {final_status}).",
        },
        "error": None if start_res["success"] else start_res.get("error", {"code": "RESTART_START_FAILED", "message": f"Service failed to restart into RUNNING state (Current: {final_status})"}),
    }
