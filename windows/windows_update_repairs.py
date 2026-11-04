"""Controlled Windows Update Repair Operations for WinFix AI (Phase 12).

Provides explicit, safe, allowlisted Windows Update repair operations:
1. restart_windows_update_service (controlled restart of Windows Update service 'wuauserv')

Enforces strict safety boundaries:
- Fixed service identifier (WINDOWS_UPDATE_SERVICE_NAME = 'wuauserv')
- No user-supplied service name argument accepted
- Strictly native Windows Service Control Manager APIs
- Sequential stop-then-start with mandatory STOPPED state verification before restart
- Deterministic verification using native Windows Service APIs
"""

import logging
import platform
import time
from typing import Any, Dict

from windows.service_repairs import (
    SERVICE_OPERATION_TIMEOUT_SECONDS,
    _wait_for_service_status,
    start_service,
)
from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)

WINDOWS_UPDATE_SERVICE_NAME = "wuauserv"


def _stop_wuauserv_direct() -> Dict[str, Any]:
    """Execute direct native StopService control code on 'wuauserv'.

    Internal helper providing the narrowly scoped Phase 12 exception to stop 'wuauserv'
    specifically during the controlled Windows Update restart flow.
    """
    try:
        import win32serviceutil
        import pywintypes

        try:
            win32serviceutil.StopService(WINDOWS_UPDATE_SERVICE_NAME)
        except pywintypes.error as win_err:
            # 1062 = ERROR_SERVICE_NOT_ACTIVE
            if win_err.winerror != 1062:
                return {"success": False, "error": {"code": "STOP_FAILED", "message": str(win_err)}}
        return {"success": True, "error": None}
    except ImportError:
        # Fallback to ctypes Advapi32
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
                return {"success": False, "error": {"code": "ACCESS_DENIED", "message": "Failed to open Service Control Manager."}}
            try:
                schService = advapi32.OpenServiceW(schSCManager, WINDOWS_UPDATE_SERVICE_NAME, SERVICE_STOP | SERVICE_QUERY_STATUS)
                if not schService:
                    return {"success": False, "error": {"code": "SERVICE_OPEN_FAILED", "message": f"Failed to open {WINDOWS_UPDATE_SERVICE_NAME}."}}
                try:
                    s_status = SERVICE_STATUS()
                    res = advapi32.ControlService(schService, SERVICE_CONTROL_STOP, ctypes.byref(s_status))
                    if res == 0:
                        err_code = ctypes.windll.kernel32.GetLastError()
                        if err_code != 1062:
                            return {"success": False, "error": {"code": "STOP_SERVICE_FAILED", "message": f"ControlService failed: {err_code}"}}
                    return {"success": True, "error": None}
                finally:
                    advapi32.CloseServiceHandle(schService)
            finally:
                advapi32.CloseServiceHandle(schSCManager)
        except Exception as fallback_exc:
            return {"success": False, "error": {"code": "STOP_SERVICE_FAILED", "message": str(fallback_exc)}}
    except Exception as exc:
        return {"success": False, "error": {"code": "STOP_SERVICE_FAILED", "message": str(exc)}}


def restart_windows_update_service() -> Dict[str, Any]:
    """Restart the Windows Update service ('wuauserv') using verified sequential controls.

    Flow:
    1. Verify OS is Windows.
    2. Check before-state of 'wuauserv'.
    3. If stopped, start it directly and verify RUNNING.
    4. If running, issue native stop control and poll for STOPPED state.
    5. CRITICAL: If stop verification fails or times out, ABORT and do NOT start.
    6. Start service and verify RUNNING state.
    7. Return structured verification outcome.
    """
    tool_name = "restart_windows_update_service"
    domain = "windows_update"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Windows Update repairs are only supported on Windows."},
        }

    try:
        # 1. Check before-state
        before_res = get_service_status(WINDOWS_UPDATE_SERVICE_NAME)
        if not before_res["success"]:
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": before_res.get("error", {"code": "SERVICE_QUERY_FAILED", "message": "Failed to query Windows Update service state."}),
            }

        before_data = before_res["data"]
        before_status = before_data.get("status", "UNKNOWN")

        # 2. If already stopped, simply start it
        if before_status == "STOPPED":
            start_res = start_service(WINDOWS_UPDATE_SERVICE_NAME)
            if start_res["success"]:
                return {
                    "success": True,
                    "tool": tool_name,
                    "domain": domain,
                    "data": {
                        "service_name": WINDOWS_UPDATE_SERVICE_NAME,
                        "display_name": "Windows Update",
                        "operation": "restart",
                        "before_state": before_status,
                        "after_state": start_res.get("data", {}).get("after_state", "RUNNING"),
                        "verification": "verified",
                        "message": "Windows Update service was stopped and has been started successfully.",
                    },
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "tool": tool_name,
                    "domain": domain,
                    "data": {
                        "service_name": WINDOWS_UPDATE_SERVICE_NAME,
                        "display_name": "Windows Update",
                        "operation": "restart",
                        "before_state": before_status,
                        "after_state": "STOPPED",
                        "verification": "not_verified",
                        "message": "Failed to start Windows Update service.",
                    },
                    "error": start_res.get("error", {"code": "START_FAILED", "message": "Failed to start Windows Update service."}),
                }

        # 3. Running state -> Stop service
        stop_cmd_res = _stop_wuauserv_direct()
        if not stop_cmd_res["success"]:
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": {
                    "service_name": WINDOWS_UPDATE_SERVICE_NAME,
                    "display_name": "Windows Update",
                    "operation": "restart",
                    "before_state": before_status,
                    "after_state": before_status,
                    "verification": "not_verified",
                    "message": "Failed to send stop command to Windows Update service.",
                },
                "error": stop_cmd_res.get("error", {"code": "STOP_COMMAND_FAILED", "message": "Failed to stop wuauserv."}),
            }

        # 4. Wait & Verify STOPPED state
        matched_stop, stop_status = _wait_for_service_status(WINDOWS_UPDATE_SERVICE_NAME, "STOPPED", timeout_seconds=SERVICE_OPERATION_TIMEOUT_SECONDS)
        if not matched_stop:
            # MANDATORY: DO NOT START IF STOP VERIFICATION FAILS
            logger.error("Stop verification failed for %s (current: %s). Aborting restart sequence.", WINDOWS_UPDATE_SERVICE_NAME, stop_status)
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": {
                    "service_name": WINDOWS_UPDATE_SERVICE_NAME,
                    "display_name": "Windows Update",
                    "operation": "restart",
                    "before_state": before_status,
                    "after_state": stop_status,
                    "verification": "not_verified",
                    "message": f"Service did not reach STOPPED state in time (current: {stop_status}). Start aborted.",
                },
                "error": {"code": "VERIFICATION_TIMEOUT", "message": f"Service did not reach STOPPED state within timeout. Current: {stop_status}"},
            }

        # 5. Start service
        start_res = start_service(WINDOWS_UPDATE_SERVICE_NAME)
        final_status = start_res.get("data", {}).get("after_state", "UNKNOWN") if start_res.get("data") else "UNKNOWN"
        verification = "verified" if start_res["success"] else "not_verified"

        return {
            "success": start_res["success"],
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": WINDOWS_UPDATE_SERVICE_NAME,
                "display_name": "Windows Update",
                "operation": "restart",
                "before_state": before_status,
                "after_state": final_status,
                "verification": verification,
                "message": f"Windows Update service restart {verification} (final state: {final_status}).",
            },
            "error": None if start_res["success"] else start_res.get("error", {"code": "RESTART_START_FAILED", "message": f"Service failed to reach RUNNING state (Current: {final_status})"}),
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "WINDOWS_UPDATE_REPAIR_ERROR", "message": str(exc)},
        }
