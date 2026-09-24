"""Controlled Windows Bluetooth Repair Operations for WinFix AI (Phase 11).

Provides explicit, safe, allowlisted Bluetooth repair operations:
1. restart_bluetooth_service (controlled restart of Windows Bluetooth Support Service 'bthserv')

Enforces strict safety boundaries:
- Fixed service identifier (BLUETOOTH_SERVICE_NAME = 'bthserv')
- Zero subprocess / os.system / powershell / cmd / devcon / pnputil / sc.exe
- Sequential stop-then-start with mandatory STOPPED state verification before restart
- Deterministic verification using native Windows Service APIs
"""

import logging
import platform
from typing import Any, Dict

from windows.service_repairs import restart_service, start_service
from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)

# Fixed constant for Bluetooth Support Service
BLUETOOTH_SERVICE_NAME = "bthserv"


def restart_bluetooth_service() -> Dict[str, Any]:
    """Restart the Windows Bluetooth Support Service ('bthserv') using verified sequential controls.

    Flow:
    1. Verify OS is Windows.
    2. Check before-state of 'bthserv'.
    3. If stopped, start it directly and verify RUNNING.
    4. If running, stop it and verify STOPPED.
    5. If stop verification fails, ABORT and do NOT start.
    6. Start service and verify RUNNING state.
    7. Return structured verification outcome.
    """
    tool_name = "restart_bluetooth_service"
    domain = "bluetooth"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Bluetooth repairs are only supported on Windows."},
        }

    try:
        # Check before-state
        before_res = get_service_status(BLUETOOTH_SERVICE_NAME)
        if not before_res["success"]:
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": before_res.get("error", {"code": "SERVICE_QUERY_FAILED", "message": "Failed to query Bluetooth service state."}),
            }

        before_data = before_res["data"]
        before_status = before_data.get("status", "UNKNOWN")

        # Delegate to proven Phase 10 verified restart implementation
        repair_res = restart_service(BLUETOOTH_SERVICE_NAME)

        after_state = repair_res.get("data", {}).get("after_state", "UNKNOWN") if repair_res.get("data") else "UNKNOWN"
        verification = repair_res.get("data", {}).get("verification", "not_verified") if repair_res.get("data") else "not_verified"

        return {
            "success": repair_res["success"],
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": BLUETOOTH_SERVICE_NAME,
                "display_name": "Bluetooth Support Service",
                "operation": "restart",
                "before_state": before_status,
                "after_state": after_state,
                "verification": verification,
                "message": f"Bluetooth Support Service restart {verification} (final state: {after_state}).",
            },
            "error": repair_res.get("error"),
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "BLUETOOTH_REPAIR_ERROR", "message": str(exc)},
        }
