"""Read-only Windows Application Event Log Diagnostic Tools for WinFix AI.

Provides structured application crash and error event inspection using win32evtlog
without clearing logs, modifying event filters, or terminating processes.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def get_recent_application_crashes(limit: int = 10, max_scan: int = 200) -> Dict[str, Any]:
    """Inspect recent application crash and error events from the Windows Application log."""
    tool_name = "get_recent_application_crashes"
    domain = "applications"
    try:
        import win32evtlog

        hand = win32evtlog.OpenEventLog(None, "Application")
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        events: List[Dict[str, Any]] = []
        scanned = 0

        # Event type constants
        EVENTLOG_ERROR_TYPE = 0x0001
        EVENTLOG_WARNING_TYPE = 0x0002

        try:
            while scanned < max_scan and len(events) < limit:
                batch = win32evtlog.ReadEventLog(hand, flags, 0)
                if not batch:
                    break

                for event in batch:
                    scanned += 1
                    event_type = event.EventType
                    # Target Errors (1) or Warnings (2), especially Application Error (1000) or Windows Error Reporting (1001)
                    is_error = event_type == EVENTLOG_ERROR_TYPE
                    is_crash_source = event.SourceName in (
                        "Application Error",
                        "Application Hang",
                        "Windows Error Reporting",
                    )

                    if is_error or is_crash_source:
                        time_generated = event.TimeGenerated.Format("%Y-%m-%d %H:%M:%S") if hasattr(event.TimeGenerated, "Format") else str(event.TimeGenerated)
                        strings = event.StringInserts or []
                        desc = " ".join([str(s) for s in strings if s]) if strings else "No description available"

                        # Keep description concise
                        if len(desc) > 300:
                            desc = desc[:300] + "..."

                        event_id_clean = event.EventID & 0xFFFF  # Mask out facility bits

                        events.append(
                            {
                                "timestamp": time_generated,
                                "source": event.SourceName,
                                "event_id": event_id_clean,
                                "event_type": "Error" if is_error else "Warning",
                                "message_summary": desc,
                            }
                        )

                        if len(events) >= limit:
                            break
        finally:
            win32evtlog.CloseEventLog(hand)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "events_count": len(events),
                "events_scanned": scanned,
                "crashes": events,
            },
            "error": None,
        }
    except ImportError:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"events_count": 0, "crashes": []},
            "error": {"code": "PYWIN32_NOT_FOUND", "message": "win32evtlog library is not available."},
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "EVENTLOG_QUERY_ERROR", "message": str(exc)},
        }
