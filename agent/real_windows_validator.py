"""WinFix AI — Real Windows Read-Only Compatibility & Environment Validator (Phase 30).

Performs non-destructive, read-only feature detection across Windows subsystems.
Identifies whether diagnostic layers can run in the active host environment.
Strictly adheres to:
  Read-Only Invariants Enforced
  No Destructive Mutations
  AST 0 Prohibited Calls
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
import os
import platform
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger("winfix.REAL_WINDOWS_VALIDATOR")


class SubsystemStatus(str, Enum):
    """Availability status for Windows diagnostic subsystems."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SubsystemCheckResult:
    """Diagnostic check result for a discrete Windows subsystem."""

    subsystem_name: str
    status: SubsystemStatus
    details: str
    is_windows_native: bool = True
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subsystem_name": self.subsystem_name,
            "status": self.status.value,
            "details": self.details,
            "is_windows_native": self.is_windows_native,
            "checked_at": self.checked_at,
        }


class RealWindowsValidator:
    """Non-destructive compatibility validator for live Windows environments."""

    @classmethod
    def validate_host_environment(cls) -> Dict[str, SubsystemCheckResult]:
        """Inspect host operating system capabilities safely and non-destructively."""
        results: Dict[str, SubsystemCheckResult] = {}
        is_windows = sys.platform.startswith("win")

        # 1. OS & Architecture Check
        if is_windows:
            results["os_platform"] = SubsystemCheckResult(
                subsystem_name="os_platform",
                status=SubsystemStatus.READY,
                details=f"Running on Windows {platform.release()} ({platform.version()}, {platform.machine()})",
                is_windows_native=True,
            )
        else:
            results["os_platform"] = SubsystemCheckResult(
                subsystem_name="os_platform",
                status=SubsystemStatus.DEGRADED,
                details=f"Running on non-Windows host: {sys.platform} (Simulation & heuristic modes active)",
                is_windows_native=False,
            )

        # 2. Python Win32 / Ctypes Subsystem Read Readiness
        try:
            import ctypes
            if is_windows and hasattr(ctypes, "windll"):
                results["ctypes_win32"] = SubsystemCheckResult(
                    subsystem_name="ctypes_win32",
                    status=SubsystemStatus.READY,
                    details="Win32 Ctypes API bridge available.",
                    is_windows_native=True,
                )
            else:
                results["ctypes_win32"] = SubsystemCheckResult(
                    subsystem_name="ctypes_win32",
                    status=SubsystemStatus.DEGRADED if not is_windows else SubsystemStatus.READY,
                    details="Ctypes standard library available.",
                    is_windows_native=is_windows,
                )
        except Exception as exc:
            results["ctypes_win32"] = SubsystemCheckResult(
                subsystem_name="ctypes_win32",
                status=SubsystemStatus.UNAVAILABLE,
                details=f"Ctypes unavailable: {exc}",
                is_windows_native=is_windows,
            )

        # 3. Registry Read Subsystem
        try:
            import winreg
            results["winreg"] = SubsystemCheckResult(
                subsystem_name="winreg",
                status=SubsystemStatus.READY,
                details="Windows Registry read-only API available.",
                is_windows_native=True,
            )
        except ImportError:
            results["winreg"] = SubsystemCheckResult(
                subsystem_name="winreg",
                status=SubsystemStatus.UNAVAILABLE if is_windows else SubsystemStatus.DEGRADED,
                details="winreg module not available on this platform.",
                is_windows_native=False,
            )

        # 4. Storage Diagnostic Paths Read Check
        local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP")
        if local_app_data and os.path.exists(local_app_data):
            results["storage_telemetry"] = SubsystemCheckResult(
                subsystem_name="storage_telemetry",
                status=SubsystemStatus.READY,
                details=f"Local storage diagnostic path accessible: {local_app_data}",
                is_windows_native=is_windows,
            )
        else:
            results["storage_telemetry"] = SubsystemCheckResult(
                subsystem_name="storage_telemetry",
                status=SubsystemStatus.DEGRADED,
                details="Default local app data storage paths not detected.",
                is_windows_native=is_windows,
            )

        return results
