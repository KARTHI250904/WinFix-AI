"""Read-only Windows Update Diagnostic Tools for WinFix AI.

Provides structured Windows Update service and policy status diagnostics
without initiating update downloads, modifications, or reboots.
"""

import logging
from typing import Any, Dict

from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)


def get_windows_update_diagnostics() -> Dict[str, Any]:
    """Inspect read-only Windows Update service states and update configurations."""
    tool_name = "get_windows_update_diagnostics"
    domain = "windows_update"
    try:
        # Check core update-related services
        wuauserv = get_service_status("wuauserv")
        bits = get_service_status("bits")
        dosvc = get_service_status("dosvc")

        # Read Auto-Update registry configuration if accessible
        au_options = None
        last_success_time = None
        try:
            import winreg

            au_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, au_path) as key:
                try:
                    au_options, _ = winreg.QueryValueEx(key, "AUOptions")
                except OSError:
                    pass
                try:
                    last_success_time, _ = winreg.QueryValueEx(key, "LastSuccessTime")
                except OSError:
                    pass
        except Exception as reg_exc:
            logger.debug("Could not query Windows Update registry key: %s", reg_exc)

        services_summary = {
            "wuauserv": {
                "status": wuauserv.get("data", {}).get("status", "unknown"),
                "is_running": wuauserv.get("data", {}).get("is_running", False),
                "start_type": wuauserv.get("data", {}).get("start_type", "unknown"),
            },
            "bits": {
                "status": bits.get("data", {}).get("status", "unknown"),
                "is_running": bits.get("data", {}).get("is_running", False),
                "start_type": bits.get("data", {}).get("start_type", "unknown"),
            },
            "dosvc": {
                "status": dosvc.get("data", {}).get("status", "unknown"),
                "is_running": dosvc.get("data", {}).get("is_running", False),
                "start_type": dosvc.get("data", {}).get("start_type", "unknown"),
            },
        }

        # Determine overall service operational health
        update_services_ready = (
            wuauserv.get("data", {}).get("status") in ("running", "stopped")
            and bits.get("data", {}).get("status") in ("running", "stopped")
        )

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "update_services_ready": update_services_ready,
                "services": services_summary,
                "au_options": au_options,
                "last_success_time": last_success_time,
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
            "error": {"code": "WINDOWS_UPDATE_QUERY_ERROR", "message": str(exc)},
        }
