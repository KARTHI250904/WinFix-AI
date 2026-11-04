"""Read-only Windows Application Crash Diagnostic Tools for WinFix AI (Phase 14).

Provides structured, safe, read-only diagnostics for Windows application crashes and errors:
1. get_recent_application_crashes (inspect recent application crash and error events)
2. get_application_crash_details (inspect detailed structured crash records and exception codes)
3. get_application_crash_summary (synthesize factual crash counts, unique apps, recurring modules)
4. get_application_crash_frequency (analyze crash recurrence over bounded time windows)
5. get_faulting_module_information (inspect modules/DLLs associated with crash events)
6. get_windows_error_reporting_status (read-only Windows Error Reporting status)
7. get_application_crash_events (bounded evidence-oriented crash event query)
8. get_application_crash_diagnostics (high-level diagnostic aggregator)

Strictly adheres to security architecture:
- SAFE risk level across all tools
- read_only = True, automatic_allowed = True, requires_admin = False
- Zero shell or command execution APIs
- Zero process termination or application killing
- Zero event log modifications or clearing
- Zero registry writes or policy changes
- Zero automatic application repairs
"""

from datetime import datetime, timedelta, timezone
import logging
import os
import platform
import re
from typing import Any, Dict, List, Optional, Tuple

from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)

ALLOWED_TIME_WINDOWS = {
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
    "7d": 604800,
    "30d": 2592000,
}

CRASH_EVENT_SOURCES = {
    "Application Error",
    "Application Hang",
    "Windows Error Reporting",
    ".NET Runtime",
}

# Known common Windows exception codes for evidence clarification
EXCEPTION_CODE_NAMES = {
    "0xc0000005": "STATUS_ACCESS_VIOLATION",
    "0xc00000fd": "STATUS_STACK_OVERFLOW",
    "0xc000001d": "STATUS_ILLEGAL_INSTRUCTION",
    "0xc0000025": "STATUS_NONCONTINUABLE_EXCEPTION",
    "0xc0000374": "STATUS_HEAP_CORRUPTION",
    "0xc0000409": "STATUS_STACK_BUFFER_OVERRUN",
    "0xc0000094": "STATUS_INTEGER_DIVIDE_BY_ZERO",
    "0xc0000008": "STATUS_INVALID_HANDLE",
    "0xe0434352": "CLR_EXCEPTION (CCR / .NET Exception)",
    "0x80000003": "STATUS_BREAKPOINT",
}


def _normalize_time_window(time_window: Optional[str]) -> Tuple[str, int]:
    """Validate, normalize to an allowed key, and return (normalized_key, seconds)."""
    if not time_window:
        return "24h", ALLOWED_TIME_WINDOWS["24h"]
    key = str(time_window).strip().lower()
    if key in ALLOWED_TIME_WINDOWS:
        return key, ALLOWED_TIME_WINDOWS[key]
    return "24h", ALLOWED_TIME_WINDOWS["24h"]


def _parse_time_window_seconds(time_window: Optional[str]) -> int:
    """Validate and convert a time window string to seconds."""
    _, seconds = _normalize_time_window(time_window)
    return seconds


def _sanitize_path_evidence(path_str: Optional[str]) -> Optional[str]:
    """Sanitize user-identifiable path components while preserving module/app name."""
    if not path_str or not isinstance(path_str, str):
        return None
    # Mask username in C:\Users\<user>\...
    sanitized = re.sub(r"([a-zA-Z]:\\Users\\)[^\\]+(\\.*)", r"\1<User>\2", path_str, flags=re.IGNORECASE)
    return sanitized[:256]


def _parse_crash_event_details(
    source: str,
    event_id: int,
    strings: List[str],
    time_str: str,
    timestamp_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Extract structured fields from Windows Application crash event string inserts."""
    app_name = None
    app_version = None
    faulting_module = None
    module_version = None
    exception_code = None
    exception_name = None
    fault_offset = None
    process_id = None
    app_path = None
    module_path = None
    report_id = None

    if source == "Application Error" and event_id == 1000 and len(strings) >= 7:
        app_name = strings[0] if len(strings) > 0 else None
        app_version = strings[1] if len(strings) > 1 and strings[1] != "0.0.0.0" else None
        faulting_module = strings[3] if len(strings) > 3 else None
        module_version = strings[4] if len(strings) > 4 and strings[4] != "0.0.0.0" else None
        exception_code = strings[6] if len(strings) > 6 else None
        fault_offset = strings[7] if len(strings) > 7 else None
        process_id = strings[8] if len(strings) > 8 else None
        app_path = _sanitize_path_evidence(strings[10]) if len(strings) > 10 else None
        module_path = _sanitize_path_evidence(strings[11]) if len(strings) > 11 else None
        report_id = strings[12] if len(strings) > 12 else None
    elif source == "Application Hang" and event_id == 1002 and len(strings) >= 1:
        app_name = strings[0] if len(strings) > 0 else None
        app_version = strings[1] if len(strings) > 1 else None
        process_id = strings[2] if len(strings) > 2 else None
        faulting_module = "Hung / Unresponsive"
        exception_code = "APP_HANG"
    elif source == "Windows Error Reporting" and event_id == 1001 and strings:
        # Extract from WER event message or strings
        for s in strings:
            if "P1:" in s or "Application Name:" in s:
                parts = s.split()
                if len(parts) >= 2:
                    app_name = parts[1]
            if "P4:" in s or "Module Name:" in s:
                parts = s.split()
                if len(parts) >= 2:
                    faulting_module = parts[1]
            if "P7:" in s or "Exception Code:" in s:
                parts = s.split()
                if len(parts) >= 2:
                    exception_code = parts[1]
    elif source == ".NET Runtime" and strings:
        desc = " ".join(strings)
        app_match = re.search(r"Application:\s*([^\s,]+)", desc, re.IGNORECASE)
        if app_match:
            app_name = app_match.group(1)
        exc_match = re.search(r"Exception Code:\s*([^\s,]+)", desc, re.IGNORECASE)
        if exc_match:
            exception_code = exc_match.group(1)
        faulting_module = ".NET Runtime CLR"

    # Fallback app name if still None
    if not app_name and strings:
        app_name = strings[0] if strings else "Unknown"

    if exception_code:
        exc_clean = exception_code.strip().lower()
        if not exc_clean.startswith("0x") and len(exc_clean) == 8:
            exc_clean = f"0x{exc_clean}"
        exception_name = EXCEPTION_CODE_NAMES.get(exc_clean)

    # Concise description
    desc_parts = []
    if app_name:
        desc_parts.append(f"Application: {app_name}")
    if faulting_module:
        desc_parts.append(f"Module: {faulting_module}")
    if exception_code:
        exc_desc = f"Exception: {exception_code}"
        if exception_name:
            exc_desc += f" ({exception_name})"
        desc_parts.append(exc_desc)

    summary_desc = " | ".join(desc_parts) if desc_parts else f"Crash event {event_id} from {source}"

    return {
        "timestamp": time_str,
        "source": source,
        "event_id": event_id,
        "application_name": app_name,
        "application_version": app_version,
        "faulting_module": faulting_module,
        "faulting_module_version": module_version,
        "exception_code": exception_code,
        "exception_name": exception_name,
        "fault_offset": fault_offset,
        "process_id": str(process_id) if process_id else None,
        "application_path": app_path,
        "module_path": module_path,
        "report_id": report_id,
        "message_summary": summary_desc,
    }


def _read_application_crash_records(
    limit: int = 50,
    max_scan: int = 500,
    time_window_seconds: Optional[int] = None,
    filter_app: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int, bool]:
    """Internal helper to read and parse Application event logs with bounded limits."""
    clamped_limit = max(1, min(int(limit), 100))
    clamped_scan = max(10, min(int(max_scan), 2000))
    events: List[Dict[str, Any]] = []
    scanned = 0
    scan_limited = False

    cutoff_time = None
    if time_window_seconds and time_window_seconds > 0:
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=time_window_seconds)

    try:
        import win32evtlog

        hand = win32evtlog.OpenEventLog(None, "Application")
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        try:
            while scanned < clamped_scan and len(events) < clamped_limit:
                batch = win32evtlog.ReadEventLog(hand, flags, 0)
                if not batch:
                    break

                for event in batch:
                    scanned += 1
                    event_type = event.EventType
                    # Target Errors (1) or Warnings (2), or known crash sources
                    is_error = event_type == 1  # EVENTLOG_ERROR_TYPE
                    is_crash_source = event.SourceName in CRASH_EVENT_SOURCES

                    if is_error or is_crash_source:
                        time_gen = event.TimeGenerated
                        time_str = time_gen.Format("%Y-%m-%d %H:%M:%S") if hasattr(time_gen, "Format") else str(time_gen)

                        # Parse Python datetime for time-window comparison
                        if cutoff_time:
                            try:
                                if hasattr(time_gen, "year"):
                                    event_dt = datetime(
                                        time_gen.year,
                                        time_gen.month,
                                        time_gen.day,
                                        time_gen.hour,
                                        time_gen.minute,
                                        time_gen.second,
                                        tzinfo=timezone.utc,
                                    )
                                    if event_dt < cutoff_time:
                                        # Past the time window, stop scanning backwards
                                        return events, scanned, False
                            except Exception:
                                pass

                        strings = [str(s) for s in (event.StringInserts or []) if s is not None]
                        event_id_clean = event.EventID & 0xFFFF

                        details = _parse_crash_event_details(
                            source=str(event.SourceName),
                            event_id=event_id_clean,
                            strings=strings,
                            time_str=time_str,
                        )

                        # Filter by application name if requested
                        if filter_app:
                            app = (details.get("application_name") or "").lower()
                            if filter_app.lower() not in app:
                                continue

                        events.append(details)

                        if len(events) >= clamped_limit:
                            break

                if scanned >= clamped_scan:
                    scan_limited = True
                    break
        finally:
            win32evtlog.CloseEventLog(hand)
    except ImportError:
        logger.debug("win32evtlog is not available on this platform.")
    except Exception as exc:
        logger.debug("Error reading Application event log: %s", exc)

    return events, scanned, scan_limited


def get_recent_application_crashes(limit: int = 10, max_scan: int = 200) -> Dict[str, Any]:
    """Inspect recent application crash and error events from the Windows Application log.

    Preserves full backward compatibility with Phase 3 baseline contract.
    """
    tool_name = "get_recent_application_crashes"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"status": "not_available", "events_count": 0, "crashes_found": 0, "crashes": []},
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    events, scanned, scan_limited = _read_application_crash_records(limit=limit, max_scan=max_scan)

    # Convert to standard crashes list with legacy fields
    legacy_crashes = []
    for ev in events:
        legacy_crashes.append({
            "timestamp": ev.get("timestamp"),
            "source": ev.get("source"),
            "event_id": ev.get("event_id"),
            "event_type": "Error",
            "message_summary": ev.get("message_summary"),
            "application_name": ev.get("application_name"),
            "faulting_module": ev.get("faulting_module"),
            "exception_code": ev.get("exception_code"),
            "exception_name": ev.get("exception_name"),
        })

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "status": "available",
            "events_count": len(legacy_crashes),
            "crashes_found": len(legacy_crashes),
            "events_scanned": scanned,
            "scan_limited": scan_limited,
            "crashes": legacy_crashes,
        },
        "error": None,
    }


def get_application_crash_details(
    application_name: Optional[str] = None,
    limit: int = 5,
    max_scan: int = 200,
) -> Dict[str, Any]:
    """Retrieve detailed, structured crash records, fault offsets, and exception codes for an application."""
    tool_name = "get_application_crash_details"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"status": "not_available", "count": 0, "records": []},
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    events, scanned, scan_limited = _read_application_crash_records(
        limit=limit,
        max_scan=max_scan,
        filter_app=application_name,
    )

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "status": "available",
            "application_filter": application_name,
            "count": len(events),
            "matched_records_count": len(events),
            "events_scanned": scanned,
            "scan_limited": scan_limited,
            "records": events,
        },
        "error": None,
    }


def get_application_crash_summary(
    time_window: str = "24h",
    limit: int = 50,
    max_scan: int = 500,
) -> Dict[str, Any]:
    """Synthesize high-level factual summary of recent crashes, unique applications, and recurring modules."""
    tool_name = "get_application_crash_summary"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"status": "not_available", "total_crashes": 0},
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    norm_window, sec = _normalize_time_window(time_window)
    events, scanned, scan_limited = _read_application_crash_records(
        limit=limit,
        max_scan=max_scan,
        time_window_seconds=sec,
    )

    app_counts: Dict[str, int] = {}
    mod_counts: Dict[str, int] = {}

    for ev in events:
        app = ev.get("application_name") or "Unknown"
        mod = ev.get("faulting_module") or "Unknown"
        app_counts[app] = app_counts.get(app, 0) + 1
        mod_counts[mod] = mod_counts.get(mod, 0) + 1

    recurring_apps = [app for app, cnt in app_counts.items() if cnt > 1]
    recurring_mods = [mod for mod, cnt in mod_counts.items() if cnt > 1]

    most_recent = events[0] if events else None

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "status": "available",
            "time_window": norm_window,
            "total_crashes": len(events),
            "unique_applications": len(app_counts),
            "unique_applications_count": len(app_counts),
            "unique_faulting_modules": len(mod_counts),
            "unique_faulting_modules_count": len(mod_counts),
            "crashes_by_application": app_counts,
            "applications_breakdown": app_counts,
            "modules_breakdown": mod_counts,
            "recurring_applications": recurring_apps,
            "recurring_modules": recurring_mods,
            "has_recurring_crashes": bool(recurring_apps or recurring_mods),
            "most_recent_crash": most_recent,
            "events_scanned": scanned,
            "scan_limited": scan_limited,
        },
        "error": None,
    }


def get_application_crash_frequency(
    time_window: str = "24h",
    limit: int = 50,
    max_scan: int = 500,
) -> Dict[str, Any]:
    """Analyze crash recurrence and frequency over bounded time windows (1h, 6h, 24h, 7d, 30d)."""
    tool_name = "get_application_crash_frequency"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"status": "not_available", "total_crashes": 0},
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    norm_window, sec = _normalize_time_window(time_window)
    events, scanned, scan_limited = _read_application_crash_records(
        limit=limit,
        max_scan=max_scan,
        time_window_seconds=sec,
    )

    crashes_by_app: Dict[str, int] = {}
    crashes_by_mod: Dict[str, int] = {}
    crashes_by_exception: Dict[str, int] = {}

    for ev in events:
        app = ev.get("application_name") or "Unknown"
        mod = ev.get("faulting_module") or "Unknown"
        exc = ev.get("exception_code") or "Unknown"
        crashes_by_app[app] = crashes_by_app.get(app, 0) + 1
        crashes_by_mod[mod] = crashes_by_mod.get(mod, 0) + 1
        crashes_by_exception[exc] = crashes_by_exception.get(exc, 0) + 1

    recurring = {app: count for app, count in crashes_by_app.items() if count >= 2}
    recurring_list = [{"application_name": app, "crash_count": count} for app, count in recurring.items()]

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "status": "available",
            "time_window": norm_window,
            "total_crashes": len(events),
            "crashes_by_application": crashes_by_app,
            "crashes_by_module": crashes_by_mod,
            "crashes_by_exception": crashes_by_exception,
            "recurring_crashes": recurring_list,
            "is_frequent": len(events) >= 3 or bool(recurring),
            "events_scanned": scanned,
            "scan_limited": scan_limited,
        },
        "error": None,
    }


def get_faulting_module_information(
    module_name: Optional[str] = None,
    limit: int = 20,
    max_scan: int = 300,
) -> Dict[str, Any]:
    """Inspect modules and dynamic libraries associated with application crashes in read-only mode."""
    tool_name = "get_faulting_module_information"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"status": "not_available", "count": 0, "modules": []},
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    events, scanned, scan_limited = _read_application_crash_records(limit=limit, max_scan=max_scan)

    modules_observed: Dict[str, Dict[str, Any]] = {}

    for ev in events:
        mod = ev.get("faulting_module")
        if not mod:
            continue
        if module_name and module_name.lower() not in mod.lower():
            continue

        if mod not in modules_observed:
            modules_observed[mod] = {
                "module_name": mod,
                "module_version": ev.get("faulting_module_version"),
                "module_path": ev.get("module_path"),
                "associated_applications": set(),
                "crash_count": 0,
                "exception_codes": set(),
                "latest_timestamp": ev.get("timestamp"),
                "observed_faulting_module": True,
                "confirmed_root_cause": False,
            }

        modules_observed[mod]["crash_count"] += 1
        if ev.get("application_name"):
            modules_observed[mod]["associated_applications"].add(ev["application_name"])
        if ev.get("exception_code"):
            modules_observed[mod]["exception_codes"].add(ev["exception_code"])

    # Format sets into JSON serializable lists
    formatted_modules = []
    for mod_info in modules_observed.values():
        formatted_modules.append({
            "module_name": mod_info["module_name"],
            "module_version": mod_info["module_version"],
            "module_path": mod_info["module_path"],
            "associated_applications": sorted(list(mod_info["associated_applications"])),
            "crash_count": mod_info["crash_count"],
            "exception_codes": sorted(list(mod_info["exception_codes"])),
            "latest_timestamp": mod_info["latest_timestamp"],
            "observed_faulting_module": True,
            "confirmed_root_cause": False,
        })

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "status": "available",
            "module_filter": module_name,
            "count": len(formatted_modules),
            "unique_modules_count": len(formatted_modules),
            "modules": formatted_modules,
            "events_scanned": scanned,
            "scan_limited": scan_limited,
        },
        "error": None,
    }


def get_windows_error_reporting_status() -> Dict[str, Any]:
    """Inspect Windows Error Reporting (WER) service and registry configuration in read-only mode."""
    tool_name = "get_windows_error_reporting_status"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"status": "not_available"},
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    wer_enabled = True
    disabled_by_policy = False
    dont_show_ui = False
    logging_disabled = False
    queue_count = 0

    try:
        import winreg

        # 1. Read Machine WER Policy: HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Error Reporting
        policy_path = r"SOFTWARE\Policies\Microsoft\Windows\Windows Error Reporting"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, policy_path, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "Disabled")
                    if bool(val):
                        disabled_by_policy = True
                        wer_enabled = False
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "DontShowUI")
                    dont_show_ui = bool(val)
                except OSError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "LoggingDisabled")
                    logging_disabled = bool(val)
                except OSError:
                    pass
        except OSError:
            pass

        # 2. Read Machine WER Standard settings: HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting
        main_path = r"SOFTWARE\Microsoft\Windows\Windows Error Reporting"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, main_path, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "Disabled")
                    if bool(val):
                        wer_enabled = False
                except OSError:
                    pass
        except OSError:
            pass

        # 3. Check WER service state via Windows Service API
        wer_svc_running = False
        try:
            svc_res = get_service_status("WerSvc")
            if svc_res.get("success"):
                wer_svc_running = svc_res.get("data", {}).get("is_running", False)
        except Exception:
            pass

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "service_name": "WerSvc",
                "service_running": wer_svc_running,
                "wer_service_running": wer_svc_running,
                "wer_enabled": wer_enabled and not disabled_by_policy,
                "disabled": disabled_by_policy or not wer_enabled,
                "disabled_by_policy": disabled_by_policy,
                "ui_suppressed": dont_show_ui,
                "logging_disabled": logging_disabled,
                "error_reporting_ready": wer_enabled and not disabled_by_policy and wer_svc_running,
                "status": "OPERATIONAL" if (wer_enabled and not disabled_by_policy) else "DISABLED",
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
            "error": {"code": "WER_QUERY_ERROR", "message": str(exc)},
        }


def get_application_crash_events(
    time_window: str = "24h",
    limit: int = 20,
    max_scan: int = 300,
    application_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve bounded application crash event records filtered by time window and application name."""
    tool_name = "get_application_crash_events"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    sec = _parse_time_window_seconds(time_window)
    events, scanned, scan_limited = _read_application_crash_records(
        limit=limit,
        max_scan=max_scan,
        time_window_seconds=sec,
        filter_app=application_name,
    )

    return {
        "success": True,
        "tool": tool_name,
        "domain": domain,
        "data": {
            "time_window": time_window,
            "application_filter": application_name,
            "events_count": len(events),
            "events_scanned": scanned,
            "scan_limited": scan_limited,
            "events": events,
        },
        "error": None,
    }


def get_application_crash_diagnostics(
    time_window: str = "24h",
    limit: int = 20,
) -> Dict[str, Any]:
    """Comprehensive high-level Application Crash diagnostic orchestrator aggregating all crash evidence."""
    tool_name = "get_application_crash_diagnostics"
    domain = "applications"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "Application crash diagnostics are only supported on Windows."},
        }

    try:
        summary_res = get_application_crash_summary(time_window=time_window, limit=limit)
        frequency_res = get_application_crash_frequency(time_window=time_window, limit=limit)
        modules_res = get_faulting_module_information(limit=limit)
        wer_res = get_windows_error_reporting_status()
        events_res = get_application_crash_events(time_window=time_window, limit=limit)

        summary_data = summary_res.get("data") or {}
        frequency_data = frequency_res.get("data") or {}
        modules_data = modules_res.get("data") or {}
        wer_data = wer_res.get("data") or {}
        events_data = events_res.get("data") or {}

        total_crashes = summary_data.get("total_crashes", 0)
        recurring_apps = summary_data.get("recurring_applications", [])
        recurring_mods = summary_data.get("recurring_modules", [])
        modules_list = modules_data.get("modules", [])

        # Determine conservative classification
        if total_crashes == 0:
            overall_status = "NO_RECENT_CRASH_EVIDENCE"
        elif recurring_apps or len(recurring_mods) > 0 or total_crashes >= 3:
            overall_status = "RECURRING_APPLICATION_CRASH"
        elif modules_list:
            overall_status = "FAULTING_MODULE_OBSERVED"
        else:
            overall_status = "RECENT_APPLICATION_CRASH"

        # Evidence accumulation
        evidence: List[str] = []
        if total_crashes == 0:
            evidence.append(f"No application crash events detected in Windows Event Log within {time_window}.")
        else:
            evidence.append(f"Detected {total_crashes} application crash/error event(s) within {time_window}.")
            if recurring_apps:
                evidence.append(f"Recurring crashes observed for application(s): {', '.join(recurring_apps)}.")
            if recurring_mods:
                evidence.append(f"Frequently observed faulting module(s): {', '.join(recurring_mods)}.")

        # Recommendations (Diagnostic only)
        recommendations: List[str] = []
        if recurring_apps:
            for app in recurring_apps:
                recommendations.append(f"Check for pending updates or patches for '{app}'.")
                recommendations.append(f"Inspect '{app}' internal error logs or reinstall if crashes persist.")
        elif total_crashes > 0:
            recommendations.append("Review application version compatibility and pending software updates.")
        else:
            recommendations.append("No immediate application troubleshooting required.")

        # Limitations
        limitations: List[str] = [
            "Diagnostic analysis is based on available local Windows Application Event logs.",
            "A faulting module is observable evidence and not automatic proof of software defect.",
            "Crash diagnostics are read-only; no automatic process termination or modification is performed.",
        ]

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "overall_status": overall_status,
                "time_window": time_window,
                "total_crashes": total_crashes,
                "summary": summary_data,
                "frequency": frequency_data,
                "faulting_modules": modules_list,
                "wer_status": wer_data,
                "events": events_data.get("events", []),
                "evidence": evidence,
                "limitations": limitations,
                "recommendations": recommendations,
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
            "error": {"code": "APPLICATION_CRASH_DIAGNOSTICS_ERROR", "message": str(exc)},
        }
