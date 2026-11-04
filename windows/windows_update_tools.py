"""Read-only Windows Update Diagnostic Tools for WinFix AI (Phase 12).

Provides structured, safe, read-only diagnostics for the Windows Update subsystem:
1. get_windows_update_service_status (inspect 'wuauserv' status and start type)
2. get_windows_update_dependency_services (inspect BITS, CryptSvc, RpcSs, DcomLaunch, DoSvc)
3. get_windows_update_configuration (inspect Windows Update registry policies in read-only mode)
4. get_windows_update_history (query installed/attempted updates via COM/WMI)
5. get_windows_update_errors (query recent Windows Update failure events)
6. get_windows_update_health (synthesize high-level factual health assessment)
7. get_windows_update_diagnostics (comprehensive aggregator)

Adheres strictly to core security architecture:
- SAFE risk level across all diagnostics
- read_only = True, automatic_allowed = True, requires_admin = False
- Strictly native Windows API queries without shell or external command execution
- No registry writes, no file modifications, no component resets
"""

import logging
import platform
from typing import Any, Dict, List, Optional

from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)

WINDOWS_UPDATE_SERVICE_NAME = "wuauserv"

# Core dependencies needed for Windows Update operations
WINDOWS_UPDATE_DEPENDENCIES = [
    {"name": "bits", "display_name": "Background Intelligent Transfer Service", "critical": True},
    {"name": "cryptsvc", "display_name": "Cryptographic Services", "critical": True},
    {"name": "rpcss", "display_name": "Remote Procedure Call (RPC)", "critical": True},
    {"name": "dcomlaunch", "display_name": "DCOM Server Process Launcher", "critical": True},
    {"name": "dosvc", "display_name": "Delivery Optimization", "critical": False},
]


def get_windows_update_service_status() -> Dict[str, Any]:
    """Inspect the operational status and startup configuration of the Windows Update service ('wuauserv').

    Returns structured status information without modifying system state.
    """
    tool_name = "get_windows_update_service_status"
    domain = "windows_update"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Windows Update diagnostics are only supported on Windows."},
        }

    try:
        svc_res = get_service_status(WINDOWS_UPDATE_SERVICE_NAME)
        if not svc_res.get("success"):
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": svc_res.get("error", {"code": "SERVICE_QUERY_FAILED", "message": "Failed to query wuauserv status."}),
            }

        data = svc_res.get("data", {})
        status = data.get("status", "UNKNOWN")
        is_running = data.get("is_running", False)
        start_type = data.get("start_type", "UNKNOWN")
        pid = data.get("pid")
        display_name = data.get("display_name", "Windows Update")

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": WINDOWS_UPDATE_SERVICE_NAME,
                "display_name": display_name,
                "status": status,
                "is_running": is_running,
                "start_type": start_type,
                "pid": pid,
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
            "error": {"code": "QUERY_ERROR", "message": str(exc)},
        }


def get_windows_update_dependency_services() -> Dict[str, Any]:
    """Inspect operational state of services that Windows Update depends on (BITS, CryptSvc, RpcSs, etc.).

    Strictly read-only: does not modify or restart any dependency services.
    """
    tool_name = "get_windows_update_dependency_services"
    domain = "windows_update"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Windows Update diagnostics are only supported on Windows."},
        }

    try:
        dependency_results: List[Dict[str, Any]] = []
        all_healthy = True
        degraded: List[str] = []

        for dep in WINDOWS_UPDATE_DEPENDENCIES:
            name = dep["name"]
            display_name = dep["display_name"]
            is_critical = dep["critical"]

            svc_res = get_service_status(name)
            if svc_res.get("success") and svc_res.get("data"):
                s_data = svc_res["data"]
                status = s_data.get("status", "UNKNOWN")
                start_type = s_data.get("start_type", "UNKNOWN")
                is_running = s_data.get("is_running", False)

                # Healthy if running, or if manual/demand start (can start on-demand)
                is_healthy = is_running or (start_type in ("DEMAND_START", "AUTO_START") and status != "DISABLED")
                if not is_healthy and is_critical:
                    all_healthy = False
                    degraded.append(name)

                dependency_results.append({
                    "service_name": name,
                    "display_name": display_name,
                    "status": status,
                    "start_type": start_type,
                    "is_running": is_running,
                    "critical": is_critical,
                    "is_healthy": is_healthy,
                })
            else:
                dependency_results.append({
                    "service_name": name,
                    "display_name": display_name,
                    "status": "NOT_FOUND",
                    "start_type": "UNKNOWN",
                    "is_running": False,
                    "critical": is_critical,
                    "is_healthy": not is_critical,
                })
                if is_critical:
                    all_healthy = False
                    degraded.append(name)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "dependencies": dependency_results,
                "all_dependencies_healthy": all_healthy,
                "degraded_services": degraded,
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
            "error": {"code": "DEPENDENCY_QUERY_ERROR", "message": str(exc)},
        }


def get_windows_update_configuration() -> Dict[str, Any]:
    """Inspect Windows Update registry policies and settings in strictly read-only mode.

    Inspects AUOptions, NoAutoUpdate, WSUS policies without modifying any registry keys.
    """
    tool_name = "get_windows_update_configuration"
    domain = "windows_update"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Windows Update diagnostics are only supported on Windows."},
        }

    try:
        import winreg

        au_options = None
        au_options_desc = "Default (Automatic)"
        no_auto_update = False
        use_wu_server = False
        wu_server = None
        wu_status_server = None
        scheduled_install_day = None
        scheduled_install_time = None
        last_success_time = None
        policy_managed = False

        # 1. Check Policy Key: HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU
        policy_au_path = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, policy_au_path, 0, winreg.KEY_READ) as key:
                policy_managed = True
                try:
                    val, _ = winreg.QueryValueEx(key, "AUOptions")
                    au_options = val
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "NoAutoUpdate")
                    no_auto_update = bool(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "UseWUServer")
                    use_wu_server = bool(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "ScheduledInstallDay")
                    scheduled_install_day = val
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "ScheduledInstallTime")
                    scheduled_install_time = val
                except OSError:
                    pass
        except OSError:
            pass

        # 2. Check Policy Server Key: HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate
        policy_wu_path = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, policy_wu_path, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "WUServer")
                    wu_server = str(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "WUStatusServer")
                    wu_status_server = str(val)
                except OSError:
                    pass
        except OSError:
            pass

        # 3. Check CurrentVersion Key: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update
        std_au_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, std_au_path, 0, winreg.KEY_READ) as key:
                if au_options is None:
                    try:
                        val, _ = winreg.QueryValueEx(key, "AUOptions")
                        au_options = val
                    except OSError:
                        pass
                try:
                    val, _ = winreg.QueryValueEx(key, "LastSuccessTime")
                    last_success_time = str(val)
                except OSError:
                    pass
        except OSError:
            pass

        # Interpret AUOptions value
        au_map = {
            1: "Keep my computer up to date is disabled",
            2: "Notify for download and notify for install",
            3: "Auto download and notify for install",
            4: "Auto download and schedule the install",
            5: "Allow local admin to select settings",
        }
        if au_options in au_map:
            au_options_desc = au_map[au_options]

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "au_options": au_options,
                "au_options_description": au_options_desc,
                "no_auto_update": no_auto_update,
                "use_wu_server": use_wu_server,
                "wu_server": wu_server,
                "wu_status_server": wu_status_server,
                "scheduled_install_day": scheduled_install_day,
                "scheduled_install_time": scheduled_install_time,
                "last_success_time": last_success_time,
                "policy_managed": policy_managed,
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
            "error": {"code": "CONFIG_QUERY_ERROR", "message": str(exc)},
        }


def get_windows_update_history(limit: int = 20) -> Dict[str, Any]:
    """Query recent Windows Update installation and update history using native Windows COM/WMI APIs.

    Strictly read-only: does not modify or clear update history.
    """
    tool_name = "get_windows_update_history"
    domain = "windows_update"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Windows Update diagnostics are only supported on Windows."},
        }

    clamped_limit = max(1, min(int(limit), 50))
    updates: List[Dict[str, Any]] = []

    # Attempt 1: Query Microsoft.Update.Session COM interface
    try:
        import win32com.client

        session = win32com.client.Dispatch("Microsoft.Update.Session")
        searcher = session.CreateUpdateSearcher()
        history_coll = searcher.QueryHistory(0, clamped_limit)

        result_code_map = {
            1: "In Progress",
            2: "Succeeded",
            3: "Succeeded With Errors",
            4: "Failed",
            5: "Aborted",
        }
        operation_map = {
            1: "Installation",
            2: "Uninstallation",
            3: "Other",
        }

        for i in range(history_coll.Count):
            try:
                entry = history_coll.Item(i)
                title = getattr(entry, "Title", "Unknown Update")
                date_val = getattr(entry, "Date", None)
                date_str = str(date_val) if date_val else "Unknown"
                res_code = getattr(entry, "ResultCode", 0)
                res_str = result_code_map.get(res_code, f"Code {res_code}")
                op_code = getattr(entry, "Operation", 0)
                op_str = operation_map.get(op_code, "Unknown")
                update_id = None
                if hasattr(entry, "UpdateIdentity") and entry.UpdateIdentity:
                    update_id = getattr(entry.UpdateIdentity, "UpdateID", None)
                support_url = getattr(entry, "SupportUrl", None)

                updates.append({
                    "title": title,
                    "date": date_str,
                    "operation": op_str,
                    "result": res_str,
                    "update_id": update_id,
                    "support_url": support_url,
                })
            except Exception as item_exc:
                logger.debug("Error extracting update history item: %s", item_exc)
    except Exception as com_exc:
        logger.debug("COM Microsoft.Update.Session query failed: %s, falling back to WMI", com_exc)
        # Fallback to WMI Win32_QuickFixEngineering
        try:
            import win32com.client

            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")
            qfe_list = wmi.ExecQuery(f"SELECT HotFixID, Description, InstalledOn, InstalledBy FROM Win32_QuickFixEngineering")
            count = 0
            for item in qfe_list:
                if count >= clamped_limit:
                    break
                hotfix_id = getattr(item, "HotFixID", "Unknown")
                desc = getattr(item, "Description", "Update")
                installed_on = getattr(item, "InstalledOn", "Unknown")
                installed_by = getattr(item, "InstalledBy", "Unknown")
                updates.append({
                    "title": f"{desc} ({hotfix_id})",
                    "date": str(installed_on),
                    "operation": "Installation",
                    "result": "Succeeded",
                    "update_id": hotfix_id,
                    "support_url": None,
                })
                count += 1
        except Exception as wmi_exc:
            logger.debug("WMI QFE query failed: %s", wmi_exc)

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "updates": updates,
            "count": len(updates),
            "latest_update": updates[0] if updates else None,
        },
        "error": None,
    }


def get_windows_update_errors(limit: int = 20) -> Dict[str, Any]:
    """Inspect recent Windows Update error events from the Windows Event Log in read-only mode.

    Queries System and Application event logs for events from WindowsUpdateClient with error severity.
    """
    tool_name = "get_windows_update_errors"
    domain = "windows_update"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Windows Update diagnostics are only supported on Windows."},
        }

    clamped_limit = max(1, min(int(limit), 50))
    error_records: List[Dict[str, Any]] = []

    try:
        import win32evtlog

        server = "localhost"
        log_type = "System"
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        h_log = win32evtlog.OpenEventLog(server, log_type)

        try:
            count = 0
            while count < clamped_limit:
                events = win32evtlog.ReadEventLog(h_log, flags, 0)
                if not events:
                    break
                for ev in events:
                    source = str(ev.SourceName)
                    # Check for Windows Update sources
                    if "windowsupdate" in source.lower() or "wuauserv" in source.lower():
                        ev_type = ev.EventType
                        # 1 = Error, 2 = Warning
                        if ev_type in (1, 2):
                            event_id = ev.EventID & 0xFFFF
                            time_gen = ev.TimeGenerated.Format() if hasattr(ev.TimeGenerated, "Format") else str(ev.TimeGenerated)
                            strings = ev.StringInserts or []
                            msg = " | ".join([str(s) for s in strings]) if strings else f"Event {event_id} from {source}"

                            # Extract potential hex error codes (0x80...)
                            error_code = None
                            for s in strings:
                                s_str = str(s)
                                if "0x80" in s_str or "0x8" in s_str:
                                    error_code = s_str
                                    break

                            error_records.append({
                                "timestamp": time_gen,
                                "event_id": event_id,
                                "error_code": error_code,
                                "severity": "Error" if ev_type == 1 else "Warning",
                                "source": source,
                                "message": msg[:256],
                            })
                            count += 1
                            if count >= clamped_limit:
                                break
        finally:
            win32evtlog.CloseEventLog(h_log)
    except Exception as evt_exc:
        logger.debug("Windows Event Log query for update errors: %s", evt_exc)

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "errors": error_records,
            "count": len(error_records),
            "has_recent_errors": len(error_records) > 0,
        },
        "error": None,
    }


def get_windows_update_health() -> Dict[str, Any]:
    """Synthesize a factual, high-level health assessment of the Windows Update subsystem based on observed state.

    Evaluates wuauserv state, critical dependencies, recent update failures, and configuration.
    """
    tool_name = "get_windows_update_health"
    domain = "windows_update"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Windows Update diagnostics are only supported on Windows."},
        }

    try:
        signals: List[str] = []
        problems: List[str] = []
        recommendations: List[str] = []
        overall_status = "HEALTHY"

        # 1. Evaluate wuauserv
        svc_res = get_windows_update_service_status()
        wuauserv_data = svc_res.get("data") if svc_res.get("success") else None

        if wuauserv_data:
            status = wuauserv_data.get("status", "UNKNOWN")
            start_type = wuauserv_data.get("start_type", "UNKNOWN")
            is_running = wuauserv_data.get("is_running", False)

            if status == "RUNNING":
                signals.append("Windows Update service (wuauserv) is RUNNING.")
            elif status == "STOPPED":
                if start_type == "DISABLED":
                    overall_status = "CRITICAL"
                    signals.append("Windows Update service (wuauserv) is DISABLED.")
                    problems.append("The Windows Update service is disabled in service configuration.")
                    recommendations.append("Windows Update service startup type must be set to Manual or Automatic.")
                else:
                    if overall_status != "CRITICAL":
                        overall_status = "DEGRADED"
                    signals.append(f"Windows Update service (wuauserv) is STOPPED (Startup: {start_type}).")
                    problems.append("Windows Update service is not currently running.")
                    recommendations.append("Restart the Windows Update service (wuauserv).")
            else:
                signals.append(f"Windows Update service status is {status}.")
        else:
            overall_status = "CRITICAL"
            problems.append("Could not query Windows Update service state.")

        # 2. Evaluate dependencies
        dep_res = get_windows_update_dependency_services()
        dep_data = dep_res.get("data") if dep_res.get("success") else None

        if dep_data:
            if not dep_data.get("all_dependencies_healthy", True):
                degraded = dep_data.get("degraded_services", [])
                signals.append(f"Windows Update dependency service(s) degraded: {', '.join(degraded)}.")
                problems.append(f"Critical dependencies {degraded} are stopped or disabled.")
                if overall_status != "CRITICAL":
                    overall_status = "DEGRADED"
            else:
                signals.append("All core Windows Update dependency services are healthy.")

        # 3. Evaluate recent errors
        err_res = get_windows_update_errors(limit=5)
        err_data = err_res.get("data") if err_res.get("success") else None

        if err_data and err_data.get("has_recent_errors", False):
            err_count = err_data.get("count", 0)
            signals.append(f"Detected {err_count} recent Windows Update error events.")
            if overall_status == "HEALTHY":
                overall_status = "DEGRADED"

        # 4. Evaluate configuration
        cfg_res = get_windows_update_configuration()
        cfg_data = cfg_res.get("data") if cfg_res.get("success") else None

        if cfg_data:
            if cfg_data.get("no_auto_update"):
                signals.append("Automatic Updates are disabled by group policy.")
                problems.append("Group Policy 'NoAutoUpdate' is enabled.")
            if cfg_data.get("use_wu_server"):
                signals.append(f"System is configured to use WSUS server: {cfg_data.get('wu_server')}.")

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "overall_status": overall_status,
                "signals": signals,
                "problems": problems,
                "recommendations": recommendations,
                "evidence": {
                    "wuauserv": wuauserv_data,
                    "dependencies": dep_data,
                    "configuration": cfg_data,
                    "error_summary": err_data,
                },
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
            "error": {"code": "HEALTH_EVALUATION_ERROR", "message": str(exc)},
        }


def get_windows_update_diagnostics() -> Dict[str, Any]:
    """High-level Windows Update diagnostic aggregator combining service status, dependencies, configuration, history, errors, and health."""
    tool_name = "get_windows_update_diagnostics"
    domain = "windows_update"

    try:
        service_status = get_windows_update_service_status()
        dependencies = get_windows_update_dependency_services()
        configuration = get_windows_update_configuration()
        history = get_windows_update_history(limit=10)
        errors = get_windows_update_errors(limit=10)
        health = get_windows_update_health()

        summary_parts = []
        if health.get("success") and health.get("data"):
            h_data = health["data"]
            summary_parts.append(f"Windows Update Health: {h_data.get('overall_status', 'UNKNOWN')}.")
            if h_data.get("problems"):
                summary_parts.append(f"Issues: {'; '.join(h_data['problems'])}.")
            else:
                summary_parts.append("No critical issues detected.")

        # Build backward-compatible services dictionary
        svc_data = service_status.get("data") or {}
        dep_data = dependencies.get("data") or {}
        dep_list = dep_data.get("dependencies", [])

        services_dict = {
            "wuauserv": {
                "status": svc_data.get("status", "unknown"),
                "is_running": svc_data.get("is_running", False),
                "start_type": svc_data.get("start_type", "unknown"),
            }
        }
        for d in dep_list:
            services_dict[d.get("service_name", "unknown")] = {
                "status": d.get("status", "unknown"),
                "is_running": d.get("is_running", False),
                "start_type": d.get("start_type", "unknown"),
            }

        update_ready = (
            health.get("data", {}).get("overall_status") != "CRITICAL"
            if health.get("success") and health.get("data")
            else False
        )

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "update_services_ready": update_ready,
                "services": services_dict,
                "service_status": service_status.get("data"),
                "dependencies": dependencies.get("data"),
                "configuration": configuration.get("data"),
                "history": history.get("data"),
                "errors": errors.get("data"),
                "health": health.get("data"),
                "summary": " ".join(summary_parts) if summary_parts else "Windows Update diagnostics complete.",
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
            "error": {"code": "WINDOWS_UPDATE_DIAGNOSTICS_ERROR", "message": str(exc)},
        }
