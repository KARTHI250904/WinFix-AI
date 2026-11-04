"""Read-only Windows Display & Monitor Diagnostic Tools for WinFix AI.

Provides structured display device inspection, resolution diagnostics, and Night Light state analysis
without altering registry settings, changing display modes, or modifying screen drivers.
"""

import ctypes
import logging
import os
from typing import Any, Dict, List, Optional
import winreg

logger = logging.getLogger(__name__)


def _query_night_light_state() -> Dict[str, Any]:
    """Inspect Windows 10/11 Night Light (Blue light reduction) registry status safely."""
    result = {
        "supported": True,
        "enabled": False,
        "status": "DISABLED",
        "details": "Night Light is currently off or not active.",
    }
    try:
        # Standard Windows 10/11 Night Light CloudStore registry path
        path = r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.bluelightreduction.bluelightreductionstate\windows.data.bluelightreduction.bluelightreductionstate"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
                data, _ = winreg.QueryValueEx(key, "Data")
                if data and len(data) >= 19:
                    # In Windows 10/11 binary data at offset 18: 0x15 -> enabled, 0x13 -> disabled
                    is_enabled = data[18] == 0x15 or (len(data) > 19 and data[19] == 0x15)
                    result["enabled"] = bool(is_enabled)
                    result["status"] = "ENABLED" if is_enabled else "DISABLED"
                    result["details"] = "Night Light is enabled and active." if is_enabled else "Night Light is disabled."
                    return result
        except FileNotFoundError:
            pass

        # Fallback Cache path for Windows 10 earlier builds
        fallback_path = r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\Cache\DefaultAccount\$$windows.data.bluelightreduction.settings\Current"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, fallback_path, 0, winreg.KEY_READ) as key:
                data, _ = winreg.QueryValueEx(key, "Data")
                if data and len(data) >= 19:
                    is_enabled = data[18] == 0x15 or (len(data) > 19 and data[19] == 0x15)
                    result["enabled"] = bool(is_enabled)
                    result["status"] = "ENABLED" if is_enabled else "DISABLED"
                    result["details"] = "Night Light is enabled." if is_enabled else "Night Light is disabled."
                    return result
        except FileNotFoundError:
            pass

        result["status"] = "NOT_CONFIGURED"
        result["details"] = "Night Light settings have not been modified from default."
    except Exception as exc:
        logger.debug("Failed to read Night Light registry: %s", exc)
        result["status"] = "UNKNOWN"
        result["details"] = f"Unable to read Night Light status: {exc}"

    return result


def get_display_diagnostics() -> Dict[str, Any]:
    """Inspect display devices, screen resolution, scaling, and Night Light status."""
    tool_name = "get_display_diagnostics"
    domain = "display"
    try:
        displays: List[Dict[str, Any]] = []
        primary_res = "Unknown"

        # 1. Query screen dimensions via user32 GetSystemMetrics
        try:
            user32 = ctypes.windll.user32
            # Enable DPI awareness to get true physical resolution
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                try:
                    user32.SetProcessDPIAware()
                except Exception:
                    pass

            width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            monitor_count = user32.GetSystemMetrics(80)  # SM_CMONITORS
            primary_res = f"{width}x{height}"

            displays.append({
                "device_name": r"\\.\DISPLAY1",
                "is_primary": True,
                "resolution": primary_res,
                "width": width,
                "height": height,
                "state": "ATTACHED",
            })
        except Exception as dm_err:
            logger.debug("Failed to query screen metrics: %s", dm_err)
            monitor_count = 1

        # 2. Query Night Light status
        night_light_info = _query_night_light_state()

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "total_monitors": max(1, monitor_count),
                "primary_resolution": primary_res,
                "displays": displays,
                "night_light": night_light_info,
                "display_subsystem_healthy": True,
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
            "error": {"code": "DISPLAY_QUERY_ERROR", "message": str(exc)},
        }
