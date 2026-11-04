"""Read-only Windows Application Event Log Diagnostic Tools for WinFix AI.

Provides structured application crash and error event inspection using native Windows APIs
without clearing logs, modifying event filters, or terminating processes.
"""

from typing import Any, Dict

from windows.application_crash_tools import get_recent_application_crashes

__all__ = ["get_recent_application_crashes"]
