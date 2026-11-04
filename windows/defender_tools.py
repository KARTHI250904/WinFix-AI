"""Read-only Microsoft Defender and Security Diagnostic Tools for WinFix AI (Phase 13).

Provides structured, safe, read-only diagnostics for Microsoft Defender:
1. get_defender_service_status (inspect 'WinDefend' state and startup type)
2. get_defender_security_health (synthesize high-level factual health assessment)
3. get_defender_realtime_protection_status (inspect real-time protection state)
4. get_defender_antivirus_status (inspect SecurityCenter2 WMI and signature versions)
5. get_defender_threat_status (inspect recent threat detections in read-only mode)
6. get_defender_recent_events (inspect recent Defender operational event logs)
7. get_defender_configuration (inspect safe Defender registry policies in read-only mode)
8. get_defender_diagnostics (comprehensive aggregator)

Adheres strictly to core security architecture:
- SAFE risk level across all diagnostics
- read_only = True, automatic_allowed = True, requires_admin = False
- Zero shell or command execution APIs
- Zero disabling of Defender, real-time protection, firewall, or notifications
- No registry writes, no exclusion modifications, no process termination
"""

import logging
import platform
from typing import Any, Dict, List, Optional

from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)

DEFENDER_SERVICE_NAME = "WinDefend"

# Core Defender and Security Center services
DEFENDER_CORE_SERVICES = [
    {"name": "WinDefend", "display_name": "Microsoft Defender Antivirus Service", "critical": True},
    {"name": "WdNisSvc", "display_name": "Microsoft Defender Network Inspection Service", "critical": False},
    {"name": "SecurityHealthService", "display_name": "Windows Security Health Service", "critical": True},
    {"name": "mpssvc", "display_name": "Windows Defender Firewall", "critical": True},
]


def get_defender_service_status() -> Dict[str, Any]:
    """Inspect the operational status and startup configuration of the Microsoft Defender service ('WinDefend').

    Returns structured status information without modifying system state.
    """
    tool_name = "get_defender_service_status"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    try:
        svc_res = get_service_status(DEFENDER_SERVICE_NAME)
        if not svc_res.get("success"):
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": svc_res.get("error", {"code": "SERVICE_QUERY_FAILED", "message": "Failed to query WinDefend status."}),
            }

        data = svc_res.get("data", {})
        status = data.get("status", "UNKNOWN")
        is_running = data.get("is_running", False)
        start_type = data.get("start_type", "UNKNOWN")
        pid = data.get("pid")
        display_name = data.get("display_name", "Microsoft Defender Antivirus Service")

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": DEFENDER_SERVICE_NAME,
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


def get_defender_realtime_protection_status() -> Dict[str, Any]:
    """Inspect whether Microsoft Defender real-time protection, behavior monitoring, and on-access scanning are active.

    Strictly read-only: does not alter or disable real-time protection.
    """
    tool_name = "get_defender_realtime_protection_status"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    try:
        import winreg

        realtime_disabled = False
        behavior_disabled = False
        on_access_disabled = False
        ioav_disabled = False
        tamper_protection = True

        # Check standard Defender Real-Time Protection registry key
        rt_path = r"SOFTWARE\Microsoft\Windows Defender\Real-Time Protection"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rt_path, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "DisableRealtimeMonitoring")
                    realtime_disabled = bool(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "DisableBehaviorMonitoring")
                    behavior_disabled = bool(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "DisableOnAccessProtection")
                    on_access_disabled = bool(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "DisableIOAVProtection")
                    ioav_disabled = bool(val)
                except OSError:
                    pass
        except OSError:
            pass

        # Check Policy Key
        policy_rt_path = r"SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, policy_rt_path, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "DisableRealtimeMonitoring")
                    if bool(val):
                        realtime_disabled = True
                except OSError:
                    pass
        except OSError:
            pass

        # Check Tamper Protection status
        features_path = r"SOFTWARE\Microsoft\Windows Defender\Features"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, features_path, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "TamperProtection")
                    tamper_protection = (val == 5) or (val == 1)
                except OSError:
                    pass
        except OSError:
            pass

        # Also cross-reference service status
        svc_res = get_service_status(DEFENDER_SERVICE_NAME)
        svc_running = svc_res.get("data", {}).get("is_running", False)

        realtime_active = (not realtime_disabled) and svc_running
        behavior_active = (not behavior_disabled) and svc_running
        on_access_active = (not on_access_disabled) and svc_running

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "realtime_protection_enabled": realtime_active,
                "behavior_monitoring_enabled": behavior_active,
                "on_access_protection_enabled": on_access_active,
                "ioav_protection_enabled": not ioav_disabled,
                "tamper_protection_active": tamper_protection,
                "service_running": svc_running,
                "method": "registry_and_service_inspection",
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
            "error": {"code": "REALTIME_QUERY_ERROR", "message": str(exc)},
        }


def get_defender_antivirus_status() -> Dict[str, Any]:
    """Inspect Microsoft Defender Antivirus status, signature versions, and engine release information.

    Queries Windows SecurityCenter2 WMI and registry signature paths in read-only mode.
    """
    tool_name = "get_defender_antivirus_status"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    try:
        import winreg

        signature_version = None
        engine_version = None
        as_signature_version = None
        signatures_last_updated = None

        # 1. Read signature and engine versions from registry
        sig_path = r"SOFTWARE\Microsoft\Windows Defender\Signature Updates"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sig_path, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "AVSignatureVersion")
                    signature_version = str(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "EngineVersion")
                    engine_version = str(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "ASSignatureVersion")
                    as_signature_version = str(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "SignaturesLastUpdated")
                    signatures_last_updated = str(val)
                except OSError:
                    pass
        except OSError:
            pass

        # 2. Check SecurityCenter2 WMI for Antivirus product status
        product_name = "Microsoft Defender Antivirus"
        is_active = True
        signatures_up_to_date = True

        try:
            import win32com.client

            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\SecurityCenter2")
            av_list = wmi.ExecQuery("SELECT * FROM AntiVirusProduct")
            for av in av_list:
                name = getattr(av, "displayName", "")
                if "defender" in name.lower() or "windows" in name.lower():
                    product_name = name
                    state_val = getattr(av, "productState", 0)
                    # State bits: 0x1000 = ON, 0x10 = up to date
                    is_active = bool(state_val & 0x1000)
                    signatures_up_to_date = not bool(state_val & 0x10)
        except Exception as wmi_exc:
            logger.debug("SecurityCenter2 WMI query failed: %s", wmi_exc)

        # 3. Check service state
        svc_res = get_service_status(DEFENDER_SERVICE_NAME)
        svc_running = svc_res.get("data", {}).get("is_running", False)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "product_name": product_name,
                "is_active": is_active and svc_running,
                "antivirus_enabled": is_active and svc_running,
                "signatures_up_to_date": signatures_up_to_date,
                "signature_version": signature_version,
                "engine_version": engine_version,
                "antispyware_signature_version": as_signature_version,
                "signatures_last_updated": signatures_last_updated,
                "antivirus_service_running": svc_running,
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
            "error": {"code": "ANTIVIRUS_QUERY_ERROR", "message": str(exc)},
        }


def get_defender_threat_status() -> Dict[str, Any]:
    """Inspect recent threat detections and current threat status in read-only mode.

    Strictly read-only: does not quarantine, remove, or modify detected threats.
    """
    tool_name = "get_defender_threat_status"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    threats: List[Dict[str, Any]] = []

    try:
        import win32evtlog

        server = "localhost"
        log_type = "Microsoft-Windows-Windows Defender/Operational"
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        try:
            h_log = win32evtlog.OpenEventLog(server, log_type)
            count = 0
            while count < 20:
                events = win32evtlog.ReadEventLog(h_log, flags, 0)
                if not events:
                    break
                for ev in events:
                    event_id = ev.EventID & 0xFFFF
                    # 1116 = Threat Detected, 1117 = Action Taken, 1119 = Remediation Error
                    if event_id in (1116, 1117, 1119):
                        time_gen = ev.TimeGenerated.Format() if hasattr(ev.TimeGenerated, "Format") else str(ev.TimeGenerated)
                        strings = ev.StringInserts or []
                        threat_name = strings[0] if len(strings) > 0 else "Unknown Threat"
                        threat_severity = strings[1] if len(strings) > 1 else "Unknown"
                        threat_path = strings[2] if len(strings) > 2 else None

                        threats.append({
                            "timestamp": time_gen,
                            "event_id": event_id,
                            "threat_name": threat_name,
                            "severity": threat_severity,
                            "path": threat_path,
                            "status": "Remediated" if event_id == 1117 else ("Detected" if event_id == 1116 else "Remediation Failed"),
                        })
                        count += 1
                        if count >= 20:
                            break
            win32evtlog.CloseEventLog(h_log)
        except Exception as evt_exc:
            logger.debug("Defender threat event log query failed: %s", evt_exc)
    except Exception as exc:
        logger.debug("Threat status query error: %s", exc)

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "active_threats_count": len([t for t in threats if t["status"] == "Detected"]),
            "recent_threats": threats,
            "has_unresolved_threats": any(t["status"] in ("Detected", "Remediation Failed") for t in threats),
            "threats": threats,
            "threat_count": len(threats),
            "has_threats": any(t["status"] in ("Detected", "Remediation Failed") for t in threats),
        },
        "error": None,
    }


def get_defender_recent_events(limit: int = 20, max_scan: int = 200) -> Dict[str, Any]:
    """Inspect recent Microsoft Defender operational events (scans, signature updates, engine notices).

    Strictly read-only: does not modify or clear Windows event logs.
    """
    tool_name = "get_defender_recent_events"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    clamped_limit = max(1, min(int(limit), 50))
    clamped_scan = max(10, min(int(max_scan), 1000))
    event_records: List[Dict[str, Any]] = []

    try:
        import win32evtlog

        server = "localhost"
        log_type = "Microsoft-Windows-Windows Defender/Operational"
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        try:
            h_log = win32evtlog.OpenEventLog(server, log_type)
            count = 0
            scanned = 0
            while count < clamped_limit and scanned < clamped_scan:
                events = win32evtlog.ReadEventLog(h_log, flags, 0)
                if not events:
                    break
                for ev in events:
                    scanned += 1
                    event_id = ev.EventID & 0xFFFF
                    time_gen = ev.TimeGenerated.Format() if hasattr(ev.TimeGenerated, "Format") else str(ev.TimeGenerated)
                    strings = ev.StringInserts or []
                    msg = " | ".join([str(s) for s in strings]) if strings else f"Defender Event {event_id}"

                    level_map = {1: "Error", 2: "Warning", 3: "Information", 4: "Information"}
                    level_str = level_map.get(ev.EventType, "Information")

                    event_records.append({
                        "timestamp": time_gen,
                        "event_id": event_id,
                        "source": str(ev.SourceName),
                        "level": level_str,
                        "message": msg[:256],
                    })
                    count += 1
                    if count >= clamped_limit or scanned >= clamped_scan:
                        break
            win32evtlog.CloseEventLog(h_log)
        except Exception as evt_exc:
            logger.debug("Defender operational log query failed: %s, falling back to System log", evt_exc)
            # Fallback to System log filtering by WinDefend
            try:
                h_log = win32evtlog.OpenEventLog(server, "System")
                count = 0
                scanned = 0
                while count < clamped_limit and scanned < clamped_scan:
                    events = win32evtlog.ReadEventLog(h_log, flags, 0)
                    if not events:
                        break
                    for ev in events:
                        scanned += 1
                        source = str(ev.SourceName)
                        if "windefend" in source.lower() or "defender" in source.lower():
                            event_id = ev.EventID & 0xFFFF
                            time_gen = ev.TimeGenerated.Format() if hasattr(ev.TimeGenerated, "Format") else str(ev.TimeGenerated)
                            strings = ev.StringInserts or []
                            msg = " | ".join([str(s) for s in strings]) if strings else f"Event {event_id} from {source}"

                            event_records.append({
                                "timestamp": time_gen,
                                "event_id": event_id,
                                "source": source,
                                "level": "Information" if ev.EventType == 4 else "Warning",
                                "message": msg[:256],
                            })
                            count += 1
                            if count >= clamped_limit or scanned >= clamped_scan:
                                break
                win32evtlog.CloseEventLog(h_log)
            except Exception:
                pass
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "events": event_records,
            "count": len(event_records),
            "has_errors": any(e.get("level") in ("Error", "Warning") for e in event_records),
        },
        "error": None,
    }


def get_defender_configuration() -> Dict[str, Any]:
    """Inspect safe, read-only Microsoft Defender policy settings from the Windows registry.

    Strictly read-only: does not write, delete, or alter any registry values.
    """
    tool_name = "get_defender_configuration"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    try:
        import winreg

        disable_antivirus_policy = False
        passive_mode = False
        pua_protection = None
        policy_managed = False

        # 1. Policy path: HKLM\SOFTWARE\Policies\Microsoft\Windows Defender
        policy_path = r"SOFTWARE\Policies\Microsoft\Windows Defender"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, policy_path, 0, winreg.KEY_READ) as key:
                policy_managed = True
                try:
                    val, _ = winreg.QueryValueEx(key, "DisableAntiSpyware")
                    if bool(val):
                        disable_antivirus_policy = True
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "DisableAntiVirus")
                    if bool(val):
                        disable_antivirus_policy = True
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "PUAProtection")
                    pua_protection = val
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "PassiveMode")
                    passive_mode = bool(val)
                except OSError:
                    pass
        except OSError:
            pass

        # 2. Main path: HKLM\SOFTWARE\Microsoft\Windows Defender
        main_path = r"SOFTWARE\Microsoft\Windows Defender"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, main_path, 0, winreg.KEY_READ) as key:
                if pua_protection is None:
                    try:
                        val, _ = winreg.QueryValueEx(key, "PUAProtection")
                        pua_protection = val
                    except OSError:
                        pass
                if not passive_mode:
                    try:
                        val, _ = winreg.QueryValueEx(key, "PassiveMode")
                        passive_mode = bool(val)
                    except OSError:
                        pass
        except OSError:
            pass

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "disable_antivirus_policy": disable_antivirus_policy,
                "passive_mode": passive_mode,
                "pua_protection": pua_protection,
                "policy_managed": policy_managed,
                "realtime_protection": not disable_antivirus_policy,
                "tamper_protection": True,
                "cloud_protection": True,
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
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "CONFIG_QUERY_ERROR", "message": str(exc)},
        }


def get_defender_security_health() -> Dict[str, Any]:
    """Synthesize a factual, high-level health assessment of Microsoft Defender based on observable evidence."""
    tool_name = "get_defender_security_health"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    try:
        signals: List[str] = []
        problems: List[str] = []
        recommendations: List[str] = []
        overall_status = "HEALTHY"

        # 1. Evaluate WinDefend service status
        svc_res = get_defender_service_status()
        svc_data = svc_res.get("data") if svc_res.get("success") else None

        if svc_data:
            status = svc_data.get("status", "UNKNOWN")
            is_running = svc_data.get("is_running", False)

            if status == "RUNNING":
                signals.append("Microsoft Defender Antivirus Service (WinDefend) is RUNNING.")
            elif status == "STOPPED":
                overall_status = "CRITICAL"
                signals.append("Microsoft Defender Antivirus Service (WinDefend) is STOPPED.")
                problems.append("The core antivirus service is not currently running.")
                recommendations.append("Restart the Microsoft Defender Antivirus Service (WinDefend).")
            else:
                overall_status = "DEGRADED"
                signals.append(f"WinDefend service status is {status}.")
                problems.append(f"WinDefend is in non-standard state: {status}.")
        else:
            overall_status = "CRITICAL"
            problems.append("Could not query WinDefend service status.")

        # 2. Evaluate Real-Time Protection
        rt_res = get_defender_realtime_protection_status()
        rt_data = rt_res.get("data") if rt_res.get("success") else None

        if rt_data:
            if rt_data.get("realtime_protection_enabled"):
                signals.append("Real-Time Protection is ENABLED and active.")
            else:
                if overall_status != "CRITICAL":
                    overall_status = "DEGRADED"
                signals.append("Real-Time Protection is DISABLED or inactive.")
                problems.append("Real-Time Protection is currently inactive.")
                recommendations.append("Verify Defender service operational state.")

            if rt_data.get("tamper_protection_active"):
                signals.append("Tamper Protection is ACTIVE.")
            else:
                signals.append("Tamper Protection state could not be verified.")

        # 3. Evaluate Antivirus Product & Signatures
        av_res = get_defender_antivirus_status()
        av_data = av_res.get("data") if av_res.get("success") else None

        if av_data:
            sig_ver = av_data.get("signature_version")
            if sig_ver:
                signals.append(f"Security Intelligence Version: {sig_ver}.")
            if not av_data.get("signatures_up_to_date", True):
                if overall_status == "HEALTHY":
                    overall_status = "DEGRADED"
                signals.append("Antivirus definitions may be outdated.")
                problems.append("Antivirus definitions require updating.")
                recommendations.append("Check Windows Update for latest Defender definition updates.")

        # 4. Evaluate Threats
        threat_res = get_defender_threat_status()
        threat_data = threat_res.get("data") if threat_res.get("success") else None

        if threat_data and threat_data.get("has_unresolved_threats"):
            overall_status = "CRITICAL"
            unres_count = threat_data.get("active_threats_count", 0)
            signals.append(f"Found {unres_count} unresolved threat detections.")
            problems.append(f"Unresolved malware or threat detections exist on the system.")
            recommendations.append("Open Windows Security to review and remediate detected threats.")

        # 5. Evaluate Firewall Service
        fw_res = get_service_status("mpssvc")
        if fw_res.get("success") and fw_res.get("data"):
            fw_running = fw_res["data"].get("is_running", False)
            if fw_running:
                signals.append("Windows Defender Firewall (mpssvc) is RUNNING.")
            else:
                if overall_status == "HEALTHY":
                    overall_status = "DEGRADED"
                signals.append("Windows Defender Firewall (mpssvc) is STOPPED.")
                problems.append("Windows Firewall service is not running.")

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
                    "service_status": svc_data,
                    "realtime_protection": rt_data,
                    "antivirus": av_data,
                    "threats": threat_data,
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


def get_defender_diagnostics() -> Dict[str, Any]:
    """Comprehensive Microsoft Defender diagnostic aggregator combining all read-only inspection tools."""
    tool_name = "get_defender_diagnostics"
    domain = "defender"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Defender diagnostics are only supported on Windows."},
        }

    try:
        service_status = get_defender_service_status()
        health = get_defender_security_health()
        realtime = get_defender_realtime_protection_status()
        antivirus = get_defender_antivirus_status()
        threats = get_defender_threat_status()
        events = get_defender_recent_events(limit=10)
        config = get_defender_configuration()

        # Backward compatible fields for Phase 3 baseline
        windefend = get_service_status("WinDefend")
        wdnissvc = get_service_status("WdNisSvc")
        sec_health = get_service_status("SecurityHealthService")
        firewall = get_service_status("mpssvc")

        antivirus_running = windefend.get("data", {}).get("is_running", False)
        firewall_running = firewall.get("data", {}).get("is_running", False)

        sig_ver = antivirus.get("data", {}).get("signature_version") if antivirus.get("success") else None
        eng_ver = antivirus.get("data", {}).get("engine_version") if antivirus.get("success") else None

        summary_parts = []
        if health.get("success") and health.get("data"):
            h_data = health["data"]
            summary_parts.append(f"Defender Security Health: {h_data.get('overall_status', 'UNKNOWN')}.")
            if h_data.get("problems"):
                summary_parts.append(f"Issues: {'; '.join(h_data['problems'])}.")
            else:
                summary_parts.append("Antivirus and Security Health services are operating normally.")

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "antivirus_service_running": antivirus_running,
                "firewall_service_running": firewall_running,
                "services": {
                    "WinDefend": {
                        "status": windefend.get("data", {}).get("status", "unknown"),
                        "is_running": antivirus_running,
                    },
                    "WdNisSvc": {
                        "status": wdnissvc.get("data", {}).get("status", "unknown"),
                        "is_running": wdnissvc.get("data", {}).get("is_running", False),
                    },
                    "SecurityHealthService": {
                        "status": sec_health.get("data", {}).get("status", "unknown"),
                        "is_running": sec_health.get("data", {}).get("is_running", False),
                    },
                    "mpssvc": {
                        "status": firewall.get("data", {}).get("status", "unknown"),
                        "is_running": firewall_running,
                    },
                },
                "signature_version": sig_ver,
                "engine_version": eng_ver,
                "service_status": service_status.get("data"),
                "security_health": health.get("data"),
                "realtime_protection": realtime.get("data"),
                "antivirus_status": antivirus.get("data"),
                "threat_status": threats.get("data"),
                "recent_events": events.get("data"),
                "configuration": config.get("data"),
                "summary": " ".join(summary_parts) if summary_parts else "Defender diagnostics complete.",
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
            "error": {"code": "DEFENDER_DIAGNOSTICS_ERROR", "message": str(exc)},
        }
