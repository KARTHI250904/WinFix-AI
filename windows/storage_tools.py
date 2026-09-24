"""Read-only Windows Storage Diagnostic Tools for WinFix AI (Phase 9).

Provides structured partition metrics, storage pressure threshold analysis, temporary directory
occupancy diagnostics, and bounded large-temporary-file analysis without altering filesystem state.
"""

from datetime import datetime
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional

import psutil

from windows.system_info import _format_bytes

logger = logging.getLogger(__name__)

# Deterministic Storage Pressure Thresholds (GB and Percentages)
CRITICAL_PERCENT = 95.0
CRITICAL_FREE_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB

HIGH_PERCENT = 85.0
HIGH_FREE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB

ELEVATED_PERCENT = 75.0
ELEVATED_FREE_BYTES = 20 * 1024 * 1024 * 1024  # 20 GB


def calculate_storage_pressure_level(percent_used: Optional[float], free_bytes: Optional[int]) -> str:
    """Calculate deterministic storage pressure classification for a volume.

    Returns one of: 'CRITICAL', 'HIGH', 'ELEVATED', 'NORMAL', or 'UNKNOWN'.
    """
    if percent_used is None or free_bytes is None:
        return "UNKNOWN"

    if percent_used >= CRITICAL_PERCENT or free_bytes <= CRITICAL_FREE_BYTES:
        return "CRITICAL"
    if percent_used >= HIGH_PERCENT or free_bytes <= HIGH_FREE_BYTES:
        return "HIGH"
    if percent_used >= ELEVATED_PERCENT or free_bytes <= ELEVATED_FREE_BYTES:
        return "ELEVATED"

    return "NORMAL"


def get_storage_diagnostics() -> Dict[str, Any]:
    """Collect read-only storage partition capacities, filesystem types, and free space."""
    tool_name = "get_storage_diagnostics"
    domain = "storage"
    try:
        drives: List[Dict[str, Any]] = []
        system_drive_letter = os.environ.get("SystemDrive", "C:").upper()
        if not system_drive_letter.endswith("\\"):
            system_drive_letter += "\\"

        partitions = psutil.disk_partitions(all=False)
        for part in partitions:
            drive_info: Dict[str, Any] = {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "is_system_drive": part.mountpoint.upper().startswith(system_drive_letter[:2]),
                "accessible": True,
                "total_bytes": None,
                "total_formatted": "Unknown",
                "used_bytes": None,
                "used_formatted": "Unknown",
                "free_bytes": None,
                "free_formatted": "Unknown",
                "percent_used": None,
                "pressure_level": "UNKNOWN",
            }
            try:
                usage = psutil.disk_usage(part.mountpoint)
                drive_info["total_bytes"] = usage.total
                drive_info["total_formatted"] = _format_bytes(usage.total)
                drive_info["used_bytes"] = usage.used
                drive_info["used_formatted"] = _format_bytes(usage.used)
                drive_info["free_bytes"] = usage.free
                drive_info["free_formatted"] = _format_bytes(usage.free)
                drive_info["percent_used"] = usage.percent
                drive_info["pressure_level"] = calculate_storage_pressure_level(usage.percent, usage.free)
            except (PermissionError, OSError) as access_exc:
                logger.debug("Could not read disk usage for %s: %s", part.mountpoint, access_exc)
                drive_info["accessible"] = False

            drives.append(drive_info)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "drives_count": len(drives),
                "drives": drives,
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
            "error": {"code": "STORAGE_QUERY_ERROR", "message": str(exc)},
        }


def get_storage_pressure_analysis() -> Dict[str, Any]:
    """Evaluate overall system storage health and partition pressure levels."""
    tool_name = "get_storage_pressure_analysis"
    domain = "storage"
    try:
        diag_res = get_storage_diagnostics()
        if not diag_res.get("success") or not diag_res.get("data"):
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": diag_res.get("error") or {"code": "STORAGE_UNAVAILABLE", "message": "Could not read disk inventory."},
            }

        drives = diag_res["data"].get("drives", [])
        overall_severity = "NORMAL"
        severity_rank = {"NORMAL": 0, "ELEVATED": 1, "HIGH": 2, "CRITICAL": 3, "UNKNOWN": -1}

        system_drive_pressure = "UNKNOWN"
        lowest_free_drive: Optional[Dict[str, Any]] = None
        min_free_bytes = float("inf")

        for d in drives:
            p_level = d.get("pressure_level", "NORMAL")
            if severity_rank.get(p_level, 0) > severity_rank.get(overall_severity, 0):
                overall_severity = p_level

            if d.get("is_system_drive"):
                system_drive_pressure = p_level

            free_b = d.get("free_bytes")
            if free_b is not None and free_b < min_free_bytes:
                min_free_bytes = free_b
                lowest_free_drive = d

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "overall_pressure_level": overall_severity,
                "system_drive_pressure": system_drive_pressure,
                "lowest_free_drive": lowest_free_drive,
                "total_monitored_volumes": len(drives),
                "thresholds": {
                    "critical": ">=95% used OR <=5GB free",
                    "high": ">=85% used OR <=10GB free",
                    "elevated": ">=75% used OR <=20GB free",
                    "normal": "<75% used AND >20GB free",
                },
                "volumes": drives,
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
            "error": {"code": "PRESSURE_ANALYSIS_ERROR", "message": str(exc)},
        }


def get_temp_storage_info() -> Dict[str, Any]:
    """Inspect standard temporary storage directory occupancy safely in read-only mode."""
    tool_name = "get_temp_storage_info"
    domain = "storage"
    try:
        temp_paths: List[Path] = []

        # User %TEMP%
        user_temp = os.environ.get("TEMP") or os.environ.get("TMP")
        if user_temp and Path(user_temp).exists():
            temp_paths.append(Path(user_temp))

        # Windows Temp
        win_temp = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
        if win_temp.exists() and win_temp not in temp_paths:
            temp_paths.append(win_temp)

        locations: List[Dict[str, Any]] = []
        total_temp_bytes = 0
        total_temp_files = 0
        locked_files_count = 0

        for path in temp_paths:
            dir_bytes = 0
            dir_files = 0
            try:
                # Read-only directory traversal
                with os.scandir(str(path)) as it:
                    for entry in it:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                stat = entry.stat()
                                dir_bytes += stat.st_size
                                dir_files += 1
                        except (PermissionError, OSError):
                            locked_files_count += 1
                            continue
            except (PermissionError, OSError) as scan_err:
                logger.debug("Could not scan directory %s: %s", path, scan_err)

            locations.append(
                {
                    "path": str(path),
                    "size_bytes": dir_bytes,
                    "size_formatted": _format_bytes(dir_bytes),
                    "file_count": dir_files,
                }
            )
            total_temp_bytes += dir_bytes
            total_temp_files += dir_files

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "total_temp_bytes": total_temp_bytes,
                "total_temp_formatted": _format_bytes(total_temp_bytes),
                "total_temp_files": total_temp_files,
                "locked_or_inaccessible_files": locked_files_count,
                "locations": locations,
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
            "error": {"code": "TEMP_STORAGE_QUERY_ERROR", "message": str(exc)},
        }


def analyze_large_temporary_files(
    min_size_mb: float = 50.0,
    limit: int = 20,
) -> Dict[str, Any]:
    """Scan the approved user temporary directory for large files in read-only mode.

    Strictly bound to %TEMP% / tempfile.gettempdir(). Never scans arbitrary locations.
    """
    tool_name = "analyze_large_temporary_files"
    domain = "storage"
    try:
        raw_user_temp = os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()
        user_temp_path = Path(raw_user_temp).resolve()

        if not user_temp_path.exists() or not user_temp_path.is_dir():
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": {"code": "INVALID_TEMP_PATH", "message": "User temporary directory is not accessible."},
            }

        # Safety constraints: bounded limits
        bounded_limit = max(1, min(limit, 50))
        min_bytes = max(1.0, min_size_mb) * 1024 * 1024
        max_scan_items = 2000
        scan_limited = False
        scanned_count = 0

        large_files: List[Dict[str, Any]] = []

        with os.scandir(str(user_temp_path)) as it:
            for entry in it:
                scanned_count += 1
                if scanned_count > max_scan_items:
                    scan_limited = True
                    break

                try:
                    entry_path = Path(entry.path)
                    resolved_entry = entry_path.resolve()

                    # Symlink / reparse boundary check
                    if not resolved_entry.is_relative_to(user_temp_path):
                        continue

                    if entry.is_file(follow_symlinks=False):
                        stat = entry.stat()
                        if stat.st_size >= min_bytes:
                            mtime_str = datetime.fromtimestamp(stat.st_mtime).isoformat() if stat.st_mtime else "Unknown"
                            large_files.append({
                                "filename": entry.name,
                                "path": entry.path,
                                "size_bytes": stat.st_size,
                                "size_formatted": _format_bytes(stat.st_size),
                                "modified_at": mtime_str,
                            })
                except (PermissionError, OSError):
                    continue

        large_files.sort(key=lambda f: f["size_bytes"], reverse=True)
        top_large = large_files[:bounded_limit]

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "target_directory": str(user_temp_path),
                "min_size_threshold_mb": min_size_mb,
                "scanned_items_count": scanned_count,
                "scan_limited": scan_limited,
                "large_files_found_count": len(large_files),
                "returned_count": len(top_large),
                "large_files": top_large,
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
            "error": {"code": "LARGE_FILES_SCAN_ERROR", "message": str(exc)},
        }
