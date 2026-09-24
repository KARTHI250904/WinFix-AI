"""Controlled Windows Performance Repair Tools for WinFix AI (Phase 8).

Implements allowlisted, safe performance optimization actions:
1. User-space process termination with strict kernel/OS process blocklists.
2. User temporary cache cleanup with strict sandbox boundary validation.

Zero shell or command interpreter execution is used. Direct Python APIs only.
"""

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil

from windows.system_info import _format_bytes

logger = logging.getLogger(__name__)

# HARD BLOCK LIST: Critical system and desktop shell processes that must NEVER be terminated
PROTECTED_PROCESS_NAMES: Set[str] = {
    "system",
    "system idle process",
    "registry",
    "memory compression",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "winlogon.exe",
    "dwm.exe",
    "explorer.exe",
    "msmpeng.exe",
    "securityhealthservice.exe",
    "conhost.exe",
    "sihost.exe",
    "taskhostw.exe",
    "runtimebroker.exe",
    "fontdrvhost.exe",
    "spoolsv.exe",
    "ctfmon.exe",
    "searchindexer.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "antigravity.exe",
    "python.exe",  # Do not self-terminate WinFix AI runner
}

PROTECTED_ACCOUNTS: Set[str] = {
    "nt authority\\system",
    "nt authority\\local service",
    "nt authority\\network service",
    "local system",
}


def is_process_termination_blocked(
    pid: int,
    process_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """Evaluate whether a process target is strictly protected from termination.

    Returns:
        (is_blocked: bool, reason: str)
    """
    if not isinstance(pid, int):
        return True, f"Invalid PID type: {type(pid).__name__}"

    if pid <= 4:
        return True, f"PID {pid} is a protected Windows Kernel or System Idle process."

    # Direct process name check if supplied
    if process_name:
        p_clean = process_name.strip().lower()
        if p_clean in PROTECTED_PROCESS_NAMES or f"{p_clean}.exe" in PROTECTED_PROCESS_NAMES:
            return True, f"Process '{process_name}' is in the critical Windows system protection blocklist."

    # Inspect the live process if running
    if not psutil.pid_exists(pid):
        return True, f"Process with PID {pid} does not exist."

    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            live_name = proc.name().lower()

            # Check for name mismatch if caller provided an expected name
            if process_name:
                exp_name = process_name.strip().lower()
                if live_name != exp_name and live_name != f"{exp_name}.exe":
                    return True, f"Process name mismatch: PID {pid} is '{live_name}', not '{process_name}'."

            if live_name in PROTECTED_PROCESS_NAMES or f"{live_name}.exe" in PROTECTED_PROCESS_NAMES:
                return True, f"Process '{live_name}' (PID {pid}) is in the critical system blocklist."

            # Check username / ownership
            try:
                username = (proc.username() or "").lower()
                if username in PROTECTED_ACCOUNTS:
                    return True, f"Process PID {pid} is owned by system account '{username}'."
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            # Check executable path for system directories
            try:
                exe_path = proc.exe()
                if exe_path:
                    exe_lower = exe_path.lower()
                    sys_root = os.environ.get("SystemRoot", r"C:\Windows").lower()
                    sys32 = os.path.join(sys_root, "system32").lower()
                    syswow = os.path.join(sys_root, "syswow64").lower()
                    winsxs = os.path.join(sys_root, "winsxs").lower()

                    if (
                        exe_lower.startswith(sys32)
                        or exe_lower.startswith(syswow)
                        or exe_lower.startswith(winsxs)
                    ):
                        return True, f"Executable located in protected Windows system directory: {exe_path}"
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

    except psutil.NoSuchProcess:
        return True, f"Process PID {pid} terminated during safety evaluation."
    except psutil.AccessDenied:
        return True, f"Access denied inspecting PID {pid}; process is system-protected."

    return False, "Target process is permissible for termination."


def terminate_user_process(
    pid: int,
    process_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Safely terminate a validated, non-critical user-space process using direct Python APIs."""
    tool_name = "terminate_user_process"
    domain = "performance"

    # Step 1: Safety blocklist verification
    blocked, reason = is_process_termination_blocked(pid, process_name)
    if blocked:
        logger.warning("Process termination blocked for PID %s: %s", pid, reason)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "pid": pid,
                "process_name": process_name,
                "terminated": False,
                "reason": reason,
            },
            "error": {"code": "BLOCKED_PROCESS_TARGET", "message": reason},
        }

    # Step 2: Termination attempt
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()

        # Initiate graceful termination
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except psutil.TimeoutExpired:
            logger.info("Process PID %s (%s) did not exit within timeout.", pid, proc_name)

        # Check if PID is still alive
        is_alive = psutil.pid_exists(pid)
        if is_alive:
            try:
                # Verify if it's the exact same process or PID was reused
                alive_proc = psutil.Process(pid)
                if alive_proc.create_time() == proc.create_time():
                    return {
                        "success": False,
                        "tool": tool_name,
                        "domain": domain,
                        "data": {
                            "pid": pid,
                            "process_name": proc_name,
                            "terminated": False,
                        },
                        "error": {"code": "TERMINATION_FAILED", "message": f"Process {proc_name} (PID {pid}) could not be terminated."},
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        logger.info("Successfully terminated process %s (PID %s)", proc_name, pid)
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "pid": pid,
                "process_name": proc_name,
                "terminated": True,
            },
            "error": None,
        }

    except psutil.NoSuchProcess:
        # Already exited
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "pid": pid,
                "process_name": process_name or "Unknown",
                "terminated": True,
                "note": "Process already exited before termination call.",
            },
            "error": None,
        }
    except psutil.AccessDenied as acc_err:
        logger.error("Access denied terminating PID %s: %s", pid, acc_err)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "pid": pid,
                "process_name": process_name,
                "terminated": False,
            },
            "error": {"code": "ACCESS_DENIED", "message": f"Insufficient permissions to terminate PID {pid}: {acc_err}"},
        }
    except Exception as exc:
        logger.error("Error terminating PID %s: %s", pid, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "pid": pid,
                "process_name": process_name,
                "terminated": False,
            },
            "error": {"code": "TERMINATE_EXCEPTION", "message": str(exc)},
        }


def clean_user_temp_cache(
    max_file_age_hours: float = 0.0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Safely purge obsolete files from the current user's temporary cache directory.

    Strictly bound to %TEMP% / tempfile.gettempdir(). Never accepts custom or arbitrary paths.
    """
    tool_name = "clean_user_temp_cache"
    domain = "performance"

    # Step 1: Discover and validate the approved User Temp path
    raw_user_temp = os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()
    user_temp_path = Path(raw_user_temp).resolve()

    # Safety Guard: Ensure target is an existing directory and not a drive root or system folder
    if not user_temp_path.exists() or not user_temp_path.is_dir():
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "INVALID_TEMP_PATH", "message": f"User temp path '{user_temp_path}' does not exist or is not a directory."},
        }

    # Reject if temp path resolves to root of any drive (e.g. C:\) or Windows System directory
    if user_temp_path.parent == user_temp_path:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSAFE_TEMP_PATH", "message": "Temp directory cannot be a drive root."},
        }

    sys_root = Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()
    if user_temp_path == sys_root or sys_root in user_temp_path.parents:
        # User temp should not be C:\Windows
        if user_temp_path == sys_root:
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": {"code": "UNSAFE_TEMP_PATH", "message": "System directory cannot be cleaned via user cache tool."},
            }

    scanned_count = 0
    deleted_count = 0
    failed_count = 0
    freed_bytes = 0
    cutoff_time = time.time() - (max_file_age_hours * 3600.0) if max_file_age_hours > 0 else float("inf")

    # Step 2: Iterate and clean user temp entries
    try:
        with os.scandir(str(user_temp_path)) as it:
            for entry in it:
                scanned_count += 1
                try:
                    entry_path = Path(entry.path)
                    resolved_entry = entry_path.resolve()

                    # Symlink / reparse escape protection: MUST be strictly within user_temp_path
                    if not resolved_entry.is_relative_to(user_temp_path):
                        logger.warning("Skipping entry pointing outside temp sandbox: %s", entry.path)
                        continue

                    if entry.is_file(follow_symlinks=False):
                        stat = entry.stat()
                        # Check file age if specified
                        if max_file_age_hours > 0 and stat.st_mtime > cutoff_time:
                            continue

                        file_size = stat.st_size
                        if not dry_run:
                            try:
                                os.remove(entry.path)
                                deleted_count += 1
                                freed_bytes += file_size
                            except (PermissionError, OSError) as del_err:
                                logger.debug("Skipping locked/in-use file %s: %s", entry.path, del_err)
                                failed_count += 1
                        else:
                            deleted_count += 1
                            freed_bytes += file_size

                    elif entry.is_dir(follow_symlinks=False):
                        # Empty subdirectories only
                        if not dry_run:
                            try:
                                os.rmdir(entry.path)
                                deleted_count += 1
                            except (PermissionError, OSError):
                                pass

                except (PermissionError, OSError) as item_err:
                    logger.debug("Could not inspect item %s: %s", entry.path, item_err)
                    failed_count += 1

        logger.info(
            "User temp cache clean completed: %s scanned, %s removed, %s failed, %s freed",
            scanned_count,
            deleted_count,
            failed_count,
            _format_bytes(freed_bytes),
        )

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "target_directory": str(user_temp_path),
                "dry_run": dry_run,
                "scanned_files_count": scanned_count,
                "deleted_files_count": deleted_count,
                "failed_files_count": failed_count,
                "freed_bytes": freed_bytes,
                "freed_formatted": _format_bytes(freed_bytes),
            },
            "error": None,
        }

    except Exception as exc:
        logger.error("Error cleaning user temp directory %s: %s", user_temp_path, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "target_directory": str(user_temp_path),
                "scanned_files_count": scanned_count,
                "deleted_files_count": deleted_count,
                "failed_files_count": failed_count,
                "freed_bytes": freed_bytes,
            },
            "error": {"code": "CLEAN_CACHE_ERROR", "message": str(exc)},
        }
