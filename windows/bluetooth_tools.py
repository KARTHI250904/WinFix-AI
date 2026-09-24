"""Read-only Windows Bluetooth Diagnostic Tools for WinFix AI (Phase 11).

Provides structured Bluetooth adapter inspection, radio state analysis, device enumeration,
and Bluetooth service readiness without modifying device pairing or system configurations.
"""

import logging
import platform
import re
from typing import Any, Dict, List, Optional

from windows.service_tools import get_service_status, normalize_service_status, normalize_startup_type

logger = logging.getLogger(__name__)

# Canonical Bluetooth Support Service identifier
BLUETOOTH_SERVICE_NAME = "bthserv"

# Related Windows Bluetooth subsystem services to inspect
RELATED_BLUETOOTH_SERVICES = [
    {"name": "bthserv", "display_name": "Bluetooth Support Service"},
    {"name": "BthA2DP", "display_name": "Bluetooth Audio Gateway Service"},
    {"name": "bthHFSrv", "display_name": "Bluetooth Handsfree Service"},
]


def _query_wmi_bluetooth_entities() -> List[Dict[str, Any]]:
    """Helper querying Win32_PnPEntity for Bluetooth devices and adapters via COM."""
    entities: List[Dict[str, Any]] = []
    if platform.system().lower() != "windows":
        return entities

    try:
        import win32com.client

        wmi = win32com.client.GetObject("winmgmts:")
        query = (
            "SELECT Name, Description, Manufacturer, DeviceID, Status, "
            "PNPClass, ConfigManagerErrorCode "
            "FROM Win32_PnPEntity "
            "WHERE PNPClass = 'Bluetooth' OR DeviceID LIKE 'BTH%' OR Service = 'BTHPORT'"
        )
        raw_items = wmi.ExecQuery(query)

        for item in raw_items:
            try:
                name = str(item.Name) if item.Name else "Unknown Bluetooth Device"
                desc = str(item.Description) if item.Description else ""
                mfg = str(item.Manufacturer) if item.Manufacturer else "Standard / Microsoft"
                dev_id = str(item.DeviceID) if item.DeviceID else ""
                status = str(item.Status) if item.Status else "UNKNOWN"
                pnp_class = str(item.PNPClass) if item.PNPClass else "Bluetooth"
                err_code = int(item.ConfigManagerErrorCode) if item.ConfigManagerErrorCode is not None else 0

                entities.append({
                    "name": name,
                    "description": desc,
                    "manufacturer": mfg,
                    "device_id": dev_id,
                    "status": status,
                    "pnp_class": pnp_class,
                    "problem_code": err_code,
                    "is_enabled": err_code == 0,
                })
            except Exception:
                continue
    except Exception as exc:
        logger.debug("WMI Bluetooth query failed or restricted: %s", exc)

    return entities


def get_bluetooth_adapters() -> Dict[str, Any]:
    """Retrieve detailed hardware adapter metrics for all detected Bluetooth radio controllers."""
    tool_name = "get_bluetooth_adapters"
    domain = "bluetooth"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Bluetooth diagnostics are only supported on Windows."},
        }

    try:
        all_entities = _query_wmi_bluetooth_entities()

        # Distinguish radio controllers / adapters from connected peripheral devices
        adapters: List[Dict[str, Any]] = []
        for ent in all_entities:
            dev_id = ent.get("device_id", "")
            name = ent.get("name", "").lower()
            # Hardware controller identifiers typically start with USB\, PCI\, ACPI\, or have Adapter/Radio in name
            is_controller = (
                dev_id.startswith("USB\\")
                or dev_id.startswith("PCI\\")
                or dev_id.startswith("ACPI\\")
                or "adapter" in name
                or "radio" in name
                or "controller" in name
                or ent.get("pnp_class") == "Bluetooth"
            ) and not dev_id.startswith("BTHENUM\\")

            if is_controller:
                adapters.append({
                    "name": ent.get("name"),
                    "description": ent.get("description"),
                    "manufacturer": ent.get("manufacturer"),
                    "device_id": ent.get("device_id"),
                    "status": ent.get("status", "OK"),
                    "pnp_status": "OK" if ent.get("problem_code") == 0 else f"Code {ent.get('problem_code')}",
                    "present": True,
                    "enabled": ent.get("is_enabled", True),
                    "problem_code": ent.get("problem_code", 0),
                })

        # Fallback check if WMI returned nothing: inspect bthserv status
        if not adapters:
            bth_svc = get_service_status(BLUETOOTH_SERVICE_NAME)
            if bth_svc.get("success") and bth_svc.get("data", {}).get("status") != "NOT_INSTALLED":
                # System has Bluetooth stack installed even if specific PnP adapter name was unqueryable
                pass

        primary = adapters[0] if adapters else None

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "adapter_count": len(adapters),
                "has_adapter": len(adapters) > 0,
                "primary_adapter": primary,
                "adapters": adapters,
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
            "error": {"code": "ADAPTER_QUERY_ERROR", "message": str(exc)},
        }


def get_bluetooth_radio_status() -> Dict[str, Any]:
    """Inspect the current operational radio status of the primary Bluetooth controller."""
    tool_name = "get_bluetooth_radio_status"
    domain = "bluetooth"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Bluetooth diagnostics are only supported on Windows."},
        }

    try:
        adapters_res = get_bluetooth_adapters()
        if not adapters_res["success"]:
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": adapters_res.get("error", {"code": "QUERY_FAILED", "message": "Failed to query adapter."}),
            }

        adapters_data = adapters_res.get("data", {})
        has_adapter = adapters_data.get("has_adapter", False)
        adapters = adapters_data.get("adapters", [])

        # Check bthserv service state
        bth_svc = get_service_status(BLUETOOTH_SERVICE_NAME)
        svc_data = bth_svc.get("data", {})
        svc_running = svc_data.get("is_running", False)
        svc_status = svc_data.get("status", "UNKNOWN")

        radio_status = "UNKNOWN"
        details = ""

        if not has_adapter:
            radio_status = "UNAVAILABLE"
            details = "No physical or virtual Bluetooth adapter hardware controller detected."
        elif not svc_running:
            radio_status = "OFF"
            details = f"Bluetooth controller hardware is present, but '{BLUETOOTH_SERVICE_NAME}' is {svc_status}."
        else:
            # Check primary adapter error code
            primary = adapters[0] if adapters else {}
            code = primary.get("problem_code", 0)
            if code == 0 and primary.get("enabled", True):
                radio_status = "ON"
                details = f"Bluetooth radio controller '{primary.get('name')}' is active and operational."
            elif code == 22:  # Windows error code 22: Device is disabled in Device Manager
                radio_status = "OFF"
                details = f"Bluetooth adapter '{primary.get('name')}' is disabled in Windows Device Manager."
            else:
                radio_status = "UNKNOWN"
                details = f"Bluetooth controller reported PnP code {code}."

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "radio_status": radio_status,
                "is_radio_on": radio_status == "ON",
                "service_running": svc_running,
                "has_hardware": has_adapter,
                "details": details,
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
            "error": {"code": "RADIO_QUERY_ERROR", "message": str(exc)},
        }


def get_bluetooth_devices() -> Dict[str, Any]:
    """Enumerate paired, known, or connected Bluetooth peripheral devices."""
    tool_name = "get_bluetooth_devices"
    domain = "bluetooth"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Bluetooth diagnostics are only supported on Windows."},
        }

    try:
        all_entities = _query_wmi_bluetooth_entities()
        devices: List[Dict[str, Any]] = []

        for ent in all_entities:
            dev_id = ent.get("device_id", "")
            # Devices/peripherals are enumerated under BTHENUM, BTHLE, BTHHFENUM, or have peripheral names
            is_device = (
                dev_id.startswith("BTHENUM\\")
                or dev_id.startswith("BTHLE\\")
                or dev_id.startswith("BTHHFENUM\\")
            )

            if is_device:
                devices.append({
                    "name": ent.get("name", "Bluetooth Peripheral"),
                    "device_id": ent.get("device_id"),
                    "description": ent.get("description", ""),
                    "manufacturer": ent.get("manufacturer", "Unknown"),
                    "status": ent.get("status", "OK"),
                    "paired": True,
                    "connected": ent.get("status") == "OK" and ent.get("is_enabled", True),
                    "present": True,
                    "problem_code": ent.get("problem_code", 0),
                })

        connected_count = sum(1 for d in devices if d.get("connected"))

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "device_count": len(devices),
                "connected_count": connected_count,
                "devices": devices,
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
            "error": {"code": "DEVICES_QUERY_ERROR", "message": str(exc)},
        }


def get_bluetooth_service_status() -> Dict[str, Any]:
    """Inspect the operational readiness and startup configuration of the Bluetooth Support Service."""
    tool_name = "get_bluetooth_service_status"
    domain = "bluetooth"

    try:
        main_svc_res = get_service_status(BLUETOOTH_SERVICE_NAME)
        main_svc_data = main_svc_res.get("data", {}) if main_svc_res["success"] else {}

        service_installed = main_svc_data.get("status") != "NOT_INSTALLED"
        service_running = main_svc_data.get("is_running", False)
        status = main_svc_data.get("status", "UNKNOWN")
        start_type = main_svc_data.get("start_type", "UNKNOWN")

        # Query auxiliary related services
        related_statuses: List[Dict[str, Any]] = []
        for rel in RELATED_BLUETOOTH_SERVICES:
            res = get_service_status(rel["name"])
            if res["success"] and res.get("data"):
                d = res["data"]
                related_statuses.append({
                    "name": rel["name"],
                    "display_name": rel["display_name"],
                    "status": d.get("status", "UNKNOWN"),
                    "is_running": d.get("is_running", False),
                    "start_type": d.get("start_type", "UNKNOWN"),
                })

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": BLUETOOTH_SERVICE_NAME,
                "display_name": "Bluetooth Support Service",
                "service_installed": service_installed,
                "service_running": service_running,
                "status": status,
                "start_type": start_type,
                "is_disabled": start_type == "DISABLED",
                "related_services": related_statuses,
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
            "error": {"code": "SERVICE_QUERY_ERROR", "message": str(exc)},
        }


def get_bluetooth_diagnostics() -> Dict[str, Any]:
    """Unified high-level Bluetooth diagnostic aggregator combining adapters, radio, devices, and services."""
    tool_name = "get_bluetooth_diagnostics"
    domain = "bluetooth"

    try:
        adapters_res = get_bluetooth_adapters()
        radio_res = get_bluetooth_radio_status()
        devices_res = get_bluetooth_devices()
        service_res = get_bluetooth_service_status()

        adapters_data = adapters_res.get("data", {}) if adapters_res["success"] else {}
        radio_data = radio_res.get("data", {}) if radio_res["success"] else {}
        devices_data = devices_res.get("data", {}) if devices_res["success"] else {}
        service_data = service_res.get("data", {}) if service_res["success"] else {}

        issues: List[str] = []

        has_adapter = adapters_data.get("has_adapter", False)
        if not has_adapter:
            issues.append("No Bluetooth adapter hardware detected on this machine.")

        svc_running = service_data.get("service_running", False)
        if not svc_running:
            svc_status = service_data.get("status", "STOPPED")
            issues.append(f"Bluetooth Support Service ({BLUETOOTH_SERVICE_NAME}) is currently {svc_status}.")

        if service_data.get("is_disabled", False):
            issues.append(f"Bluetooth Support Service is configured with startup type DISABLED.")

        radio_status = radio_data.get("radio_status", "UNKNOWN")
        if radio_status == "OFF":
            issues.append("Bluetooth radio is currently OFF or disabled.")

        # Determine overall health status
        if not has_adapter:
            health = "UNAVAILABLE"
            summary = "Bluetooth hardware is not present or detected on this system."
        elif not svc_running or radio_status == "OFF":
            health = "ERROR" if not svc_running else "WARNING"
            summary = f"Bluetooth subsystem requires attention: {'; '.join(issues)}."
        else:
            health = "HEALTHY"
            dev_cnt = devices_data.get("device_count", 0)
            conn_cnt = devices_data.get("connected_count", 0)
            summary = f"Bluetooth adapter is active (Radio: ON, Service: RUNNING). {dev_cnt} paired device(s) ({conn_cnt} active)."

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "health": health,
                "summary": summary,
                "issues": issues,
                "adapters": adapters_data.get("adapters", []),
                "adapter_detected": has_adapter,
                "radio": radio_data,
                "devices": devices_data.get("devices", []),
                "paired_devices_count": devices_data.get("device_count", 0),
                "service": service_data,
                "service_running": svc_running,
                "service_installed": service_data.get("service_installed", True),
                "service_startup": service_data.get("start_type", "UNKNOWN"),
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
            "error": {"code": "BLUETOOTH_DIAG_ERROR", "message": str(exc)},
        }
