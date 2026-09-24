"""Read-only Windows System Information Module for WinFix AI.

Provides structured, safe diagnostic collection of operating system, CPU,
memory, disk drives, network adapters, and uptime information without executing
arbitrary commands or modifying system state.
"""

from datetime import datetime
import logging
import os
import platform
import socket
import time
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


def _format_bytes(bytes_num: Optional[int]) -> str:
    """Format bytes into human-readable representation (e.g. GB, MB)."""
    if bytes_num is None:
        return "Unknown"
    if bytes_num < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if bytes_num < 1024.0:
            return f"{bytes_num:.2f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.2f} PB"


def _format_seconds(seconds: Optional[int]) -> str:
    """Format total seconds into human-readable duration (e.g. '3 days, 4 hours, 12 minutes')."""
    if seconds is None or seconds < 0:
        return "Unknown"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: List[str] = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0 or days > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return ", ".join(parts)


def get_os_info() -> Dict[str, Any]:
    """Collect read-only operating system version, edition, and build numbers."""
    try:
        os_name = platform.system()
        os_release = platform.release()
        os_version = platform.version()
        architecture = platform.machine()
        edition = "Unknown"
        display_version = "Unknown"
        build_number = "Unknown"
        ubr = None

        if os_name == "Windows":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
                ) as key:
                    try:
                        edition, _ = winreg.QueryValueEx(key, "ProductName")
                    except OSError:
                        pass
                    try:
                        display_version, _ = winreg.QueryValueEx(key, "DisplayVersion")
                    except OSError:
                        pass
                    try:
                        build_number, _ = winreg.QueryValueEx(key, "CurrentBuildNumber")
                    except OSError:
                        pass
                    try:
                        ubr, _ = winreg.QueryValueEx(key, "UBR")
                    except OSError:
                        pass
            except Exception as reg_exc:
                logger.debug("Could not query Windows registry for OS details: %s", reg_exc)

            if edition == "Unknown":
                try:
                    edition = platform.win32_edition()
                except Exception:
                    edition = f"Windows {os_release}"

        full_build = f"{build_number}.{ubr}" if (build_number != "Unknown" and ubr is not None) else (build_number if build_number != "Unknown" else os_version)

        return {
            "status": "available",
            "name": os_name,
            "release": os_release,
            "edition": edition,
            "display_version": display_version,
            "build_number": full_build,
            "raw_version": os_version,
            "architecture": architecture,
            "is_windows": os_name == "Windows",
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to collect OS information: %s", exc)
        return {
            "status": "unavailable",
            "name": "Unknown",
            "release": "Unknown",
            "edition": "Unknown",
            "display_version": "Unknown",
            "build_number": "Unknown",
            "raw_version": "Unknown",
            "architecture": "Unknown",
            "is_windows": False,
            "error": str(exc),
        }


def get_computer_info() -> Dict[str, Any]:
    """Collect read-only computer and environment identity."""
    try:
        hostname = platform.node() or socket.gethostname() or os.environ.get("COMPUTERNAME", "Unknown")
        username = os.environ.get("USERNAME") or os.environ.get("USER", "Unknown")
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        system_drive = os.environ.get("SystemDrive", "C:")

        return {
            "status": "available",
            "computer_name": hostname,
            "username": username,
            "system_root": system_root,
            "system_drive": system_drive,
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to collect computer info: %s", exc)
        return {
            "status": "unavailable",
            "computer_name": "Unknown",
            "username": "Unknown",
            "system_root": "Unknown",
            "system_drive": "Unknown",
            "error": str(exc),
        }


def get_cpu_info() -> Dict[str, Any]:
    """Collect read-only processor architecture, model name, and core/thread counts."""
    try:
        processor_name = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "Unknown")
        
        # On Windows, try querying clean processor name from registry
        if platform.system() == "Windows":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                ) as key:
                    val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                    if val and val.strip():
                        processor_name = val.strip()
            except Exception as reg_exc:
                logger.debug("Could not query registry for CPU processor name: %s", reg_exc)

        physical_cores = psutil.cpu_count(logical=False) or 0
        logical_threads = psutil.cpu_count(logical=True) or 0

        # Frequency information
        freq_info = None
        try:
            freq = psutil.cpu_freq()
            if freq:
                freq_info = {
                    "current_mhz": round(freq.current, 2) if freq.current else None,
                    "min_mhz": round(freq.min, 2) if freq.min else None,
                    "max_mhz": round(freq.max, 2) if freq.max else None,
                }
        except Exception:
            pass

        return {
            "status": "available",
            "model": processor_name,
            "architecture": platform.machine(),
            "physical_cores": physical_cores,
            "logical_threads": logical_threads,
            "frequency": freq_info,
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to collect CPU information: %s", exc)
        return {
            "status": "unavailable",
            "model": "Unknown",
            "architecture": "Unknown",
            "physical_cores": 0,
            "logical_threads": 0,
            "frequency": None,
            "error": str(exc),
        }


def get_memory_info() -> Dict[str, Any]:
    """Collect read-only physical RAM capacity and availability."""
    try:
        vmem = psutil.virtual_memory()
        total_bytes = vmem.total
        available_bytes = vmem.available
        used_bytes = vmem.used
        percent_used = vmem.percent

        return {
            "status": "available",
            "total_bytes": total_bytes,
            "total_formatted": _format_bytes(total_bytes),
            "available_bytes": available_bytes,
            "available_formatted": _format_bytes(available_bytes),
            "used_bytes": used_bytes,
            "used_formatted": _format_bytes(used_bytes),
            "percent_used": percent_used,
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to collect memory information: %s", exc)
        return {
            "status": "unavailable",
            "total_bytes": 0,
            "total_formatted": "Unknown",
            "available_bytes": 0,
            "available_formatted": "Unknown",
            "used_bytes": 0,
            "used_formatted": "Unknown",
            "percent_used": 0.0,
            "error": str(exc),
        }


def get_disk_info() -> Dict[str, Any]:
    """Collect read-only disk partition, drive health, and free space information."""
    try:
        drives: List[Dict[str, Any]] = []
        system_drive_letter = os.environ.get("SystemDrive", "C:").upper()
        if not system_drive_letter.endswith("\\"):
            system_drive_letter += "\\"

        system_drive_info: Optional[Dict[str, Any]] = None

        partitions = psutil.disk_partitions(all=False)
        for part in partitions:
            drive_data: Dict[str, Any] = {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "opts": part.opts,
                "total_bytes": None,
                "total_formatted": "Unknown",
                "used_bytes": None,
                "used_formatted": "Unknown",
                "free_bytes": None,
                "free_formatted": "Unknown",
                "percent_used": None,
                "is_system_drive": part.mountpoint.upper().startswith(system_drive_letter[:2]),
                "accessible": True,
            }

            try:
                usage = psutil.disk_usage(part.mountpoint)
                drive_data["total_bytes"] = usage.total
                drive_data["total_formatted"] = _format_bytes(usage.total)
                drive_data["used_bytes"] = usage.used
                drive_data["used_formatted"] = _format_bytes(usage.used)
                drive_data["free_bytes"] = usage.free
                drive_data["free_formatted"] = _format_bytes(usage.free)
                drive_data["percent_used"] = usage.percent
            except (PermissionError, OSError) as access_exc:
                logger.debug("Could not read disk usage for %s: %s", part.mountpoint, access_exc)
                drive_data["accessible"] = False

            drives.append(drive_data)
            if drive_data["is_system_drive"]:
                system_drive_info = drive_data

        return {
            "status": "available",
            "drives_count": len(drives),
            "drives": drives,
            "system_drive": system_drive_info,
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to collect disk information: %s", exc)
        return {
            "status": "unavailable",
            "drives_count": 0,
            "drives": [],
            "system_drive": None,
            "error": str(exc),
        }


def get_network_adapters_info() -> Dict[str, Any]:
    """Collect read-only network interface information, connection status, and IP addresses."""
    try:
        adapters: List[Dict[str, Any]] = []
        if_addrs = psutil.net_if_addrs()
        if_stats = psutil.net_if_stats()

        for if_name, addr_list in if_addrs.items():
            stat = if_stats.get(if_name)
            is_up = stat.isup if stat else False
            speed_mbps = stat.speed if stat else 0

            ipv4_addresses: List[str] = []
            ipv6_addresses: List[str] = []
            mac_address: Optional[str] = None

            for addr in addr_list:
                # AF_INET is IPv4 (usually family 2)
                if addr.family == socket.AF_INET:
                    ipv4_addresses.append(addr.address)
                # AF_INET6 is IPv6 (usually family 23 on Windows, 10 on Linux)
                elif hasattr(socket, "AF_INET6") and addr.family == socket.AF_INET6:
                    ipv6_addresses.append(addr.address.split("%")[0])
                # AF_LINK / MAC (usually family -1 on Windows in psutil)
                elif hasattr(psutil, "AF_LINK") and addr.family == psutil.AF_LINK:
                    mac_address = addr.address
                elif addr.family == -1 or getattr(addr, "address", "").count("-") == 5 or getattr(addr, "address", "").count(":") == 5:
                    mac_address = addr.address

            adapters.append(
                {
                    "name": if_name,
                    "is_up": is_up,
                    "speed_mbps": speed_mbps,
                    "ipv4": ipv4_addresses,
                    "ipv6": ipv6_addresses,
                    "mac": mac_address,
                }
            )

        active_adapters = [a for a in adapters if a["is_up"] and a["ipv4"]]

        return {
            "status": "available",
            "total_adapters_count": len(adapters),
            "active_adapters_count": len(active_adapters),
            "adapters": adapters,
            "active_adapters": active_adapters,
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to collect network adapter information: %s", exc)
        return {
            "status": "unavailable",
            "total_adapters_count": 0,
            "active_adapters_count": 0,
            "adapters": [],
            "active_adapters": [],
            "error": str(exc),
        }


def get_uptime_info() -> Dict[str, Any]:
    """Collect read-only system boot time and uptime duration."""
    try:
        boot_timestamp = psutil.boot_time()
        boot_dt = datetime.fromtimestamp(boot_timestamp)
        now_ts = time.time()
        uptime_seconds = int(max(0, now_ts - boot_timestamp))

        return {
            "status": "available",
            "boot_timestamp": boot_timestamp,
            "boot_time_formatted": boot_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": _format_seconds(uptime_seconds),
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to collect uptime information: %s", exc)
        return {
            "status": "unavailable",
            "boot_timestamp": 0.0,
            "boot_time_formatted": "Unknown",
            "uptime_seconds": 0,
            "uptime_formatted": "Unknown",
            "error": str(exc),
        }


def _safe_collect(collector_func, name: str) -> Dict[str, Any]:
    """Execute a collector function with full exception safety."""
    try:
        return collector_func()
    except Exception as exc:
        logger.error("Collector %s encountered an unhandled exception: %s", name, exc)
        return {
            "status": "unavailable",
            "error": str(exc),
        }


def get_complete_system_info() -> Dict[str, Any]:
    """Collect and aggregate complete Windows system diagnostic information safely.

    Isolated try-except blocks ensure a failure in any single subsystem
    does not prevent the remaining information from being returned.
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "os": _safe_collect(get_os_info, "os"),
        "computer": _safe_collect(get_computer_info, "computer"),
        "cpu": _safe_collect(get_cpu_info, "cpu"),
        "memory": _safe_collect(get_memory_info, "memory"),
        "disk": _safe_collect(get_disk_info, "disk"),
        "network": _safe_collect(get_network_adapters_info, "network"),
        "uptime": _safe_collect(get_uptime_info, "uptime"),
    }

