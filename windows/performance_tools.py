"""Read-only Windows Performance Diagnostic Tools for WinFix AI.

Provides structured CPU, memory, process inspection, disk activity, and resource snapshots
without terminating processes or altering scheduling priorities.
"""

from datetime import datetime
import logging
import os
import time
from typing import Any, Dict, List, Optional

import psutil

from windows.system_info import _format_bytes, _format_seconds

logger = logging.getLogger(__name__)


def get_cpu_diagnostics(interval: float = 0.1) -> Dict[str, Any]:
    """Collect read-only CPU utilization percentages and core metrics."""
    tool_name = "get_cpu_diagnostics"
    domain = "performance"
    try:
        overall_percent = psutil.cpu_percent(interval=interval)
        per_cpu = psutil.cpu_percent(interval=0.0, percpu=True)
        physical_cores = psutil.cpu_count(logical=False) or 0
        logical_threads = psutil.cpu_count(logical=True) or 0

        freq_data = None
        try:
            freq = psutil.cpu_freq()
            if freq:
                freq_data = {
                    "current_mhz": round(freq.current, 2) if freq.current else None,
                    "min_mhz": round(freq.min, 2) if freq.min else None,
                    "max_mhz": round(freq.max, 2) if freq.max else None,
                }
        except Exception:
            pass

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "overall_percent": overall_percent,
                "per_cpu_percent": per_cpu,
                "physical_cores": physical_cores,
                "logical_threads": logical_threads,
                "frequency": freq_data,
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
            "error": {"code": "CPU_DIAG_ERROR", "message": str(exc)},
        }


def get_memory_diagnostics() -> Dict[str, Any]:
    """Collect read-only physical RAM and swap/pagefile memory utilization."""
    tool_name = "get_memory_diagnostics"
    domain = "performance"
    try:
        vmem = psutil.virtual_memory()
        smem = psutil.swap_memory()

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "virtual_memory": {
                    "total_bytes": vmem.total,
                    "total_formatted": _format_bytes(vmem.total),
                    "available_bytes": vmem.available,
                    "available_formatted": _format_bytes(vmem.available),
                    "used_bytes": vmem.used,
                    "used_formatted": _format_bytes(vmem.used),
                    "percent_used": vmem.percent,
                },
                "swap_memory": {
                    "total_bytes": smem.total,
                    "total_formatted": _format_bytes(smem.total),
                    "used_bytes": smem.used,
                    "used_formatted": _format_bytes(smem.used),
                    "free_bytes": smem.free,
                    "free_formatted": _format_bytes(smem.free),
                    "percent_used": smem.percent,
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
            "error": {"code": "MEM_DIAG_ERROR", "message": str(exc)},
        }


def get_top_cpu_processes(limit: int = 5) -> Dict[str, Any]:
    """Identify the top running processes consuming the highest CPU."""
    tool_name = "get_top_cpu_processes"
    domain = "performance"
    try:
        bounded_limit = max(1, min(limit, 50))
        processes: List[Dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "username", "status"]):
            try:
                info = proc.info
                if info and info.get("cpu_percent") is not None:
                    processes.append(
                        {
                            "pid": info.get("pid"),
                            "name": info.get("name") or "Unknown",
                            "cpu_percent": info.get("cpu_percent") or 0.0,
                            "username": info.get("username") or "N/A",
                            "status": info.get("status") or "unknown",
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes.sort(key=lambda p: p["cpu_percent"], reverse=True)
        top_procs = processes[:bounded_limit]

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "count": len(top_procs),
                "processes": top_procs,
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
            "error": {"code": "PROC_QUERY_ERROR", "message": str(exc)},
        }


def get_top_memory_processes(limit: int = 5) -> Dict[str, Any]:
    """Identify the top running processes consuming the highest physical RAM."""
    tool_name = "get_top_memory_processes"
    domain = "performance"
    try:
        bounded_limit = max(1, min(limit, 50))
        processes: List[Dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "memory_info", "memory_percent", "username"]):
            try:
                info = proc.info
                mem_info = info.get("memory_info")
                rss_bytes = mem_info.rss if mem_info else 0
                if rss_bytes > 0:
                    processes.append(
                        {
                            "pid": info.get("pid"),
                            "name": info.get("name") or "Unknown",
                            "memory_bytes": rss_bytes,
                            "memory_formatted": _format_bytes(rss_bytes),
                            "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                            "username": info.get("username") or "N/A",
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes.sort(key=lambda p: p["memory_bytes"], reverse=True)
        top_procs = processes[:bounded_limit]

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "count": len(top_procs),
                "processes": top_procs,
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
            "error": {"code": "MEM_PROC_QUERY_ERROR", "message": str(exc)},
        }


def get_process_details(pid: int) -> Dict[str, Any]:
    """Retrieve detailed read-only diagnostics for a specific process by PID."""
    tool_name = "get_process_details"
    domain = "performance"
    try:
        if not isinstance(pid, int) or pid < 0:
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": {"code": "INVALID_PID", "message": f"Invalid PID: {pid}"},
            }

        if not psutil.pid_exists(pid):
            return {
                "success": False,
                "tool": tool_name,
                "domain": domain,
                "data": None,
                "error": {"code": "PROCESS_NOT_FOUND", "message": f"No active process found with PID {pid}."},
            }

        proc = psutil.Process(pid)
        with proc.oneshot():
            name = proc.name()
            status = proc.status()
            create_ts = proc.create_time()
            create_str = datetime.fromtimestamp(create_ts).isoformat() if create_ts else "Unknown"

            # Safe metadata gathering
            exe_path = None
            try:
                exe_path = proc.exe()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                exe_path = "Access Denied"

            username = None
            try:
                username = proc.username()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                username = "Access Denied"

            mem_info = proc.memory_info()
            rss_bytes = mem_info.rss if mem_info else 0
            vms_bytes = mem_info.vms if mem_info else 0
            mem_pct = round(proc.memory_percent(), 2)
            cpu_pct = round(proc.cpu_percent(interval=0.0), 2)
            num_threads = proc.num_threads()

            # Parent info
            parent_info = None
            try:
                parent = proc.parent()
                if parent:
                    parent_info = {
                        "pid": parent.pid,
                        "name": parent.name(),
                    }
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            # Children info (bounded to 20)
            children_list: List[Dict[str, Any]] = []
            try:
                children = proc.children(recursive=False)
                for child in children[:20]:
                    try:
                        children_list.append({
                            "pid": child.pid,
                            "name": child.name(),
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "pid": pid,
                "name": name,
                "exe": exe_path,
                "status": status,
                "username": username,
                "created_at": create_str,
                "cpu_percent": cpu_pct,
                "memory_rss_bytes": rss_bytes,
                "memory_rss_formatted": _format_bytes(rss_bytes),
                "memory_vms_bytes": vms_bytes,
                "memory_vms_formatted": _format_bytes(vms_bytes),
                "memory_percent": mem_pct,
                "num_threads": num_threads,
                "parent": parent_info,
                "children_count": len(children_list),
                "children": children_list,
            },
            "error": None,
        }
    except psutil.NoSuchProcess:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "PROCESS_NOT_FOUND", "message": f"Process {pid} terminated during inspection."},
        }
    except psutil.AccessDenied as acc_err:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "ACCESS_DENIED", "message": f"Access denied reading process {pid}: {acc_err}"},
        }
    except Exception as exc:
        logger.error("%s failed for PID %s: %s", tool_name, pid, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "PROCESS_DETAILS_ERROR", "message": str(exc)},
        }


def get_disk_performance_diagnostics() -> Dict[str, Any]:
    """Collect storage partition occupancy and disk I/O performance metrics."""
    tool_name = "get_disk_performance_diagnostics"
    domain = "performance"
    try:
        partitions_data: List[Dict[str, Any]] = []
        partitions = psutil.disk_partitions(all=False)
        for part in partitions:
            usage_dict = {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_bytes": None,
                "total_formatted": "Unknown",
                "used_bytes": None,
                "used_formatted": "Unknown",
                "free_bytes": None,
                "free_formatted": "Unknown",
                "percent_used": None,
            }
            try:
                usage = psutil.disk_usage(part.mountpoint)
                usage_dict.update({
                    "total_bytes": usage.total,
                    "total_formatted": _format_bytes(usage.total),
                    "used_bytes": usage.used,
                    "used_formatted": _format_bytes(usage.used),
                    "free_bytes": usage.free,
                    "free_formatted": _format_bytes(usage.free),
                    "percent_used": usage.percent,
                })
            except (PermissionError, OSError):
                pass
            partitions_data.append(usage_dict)

        io_data = None
        try:
            io_counters = psutil.disk_io_counters()
            if io_counters:
                io_data = {
                    "read_count": io_counters.read_count,
                    "write_count": io_counters.write_count,
                    "read_bytes": io_counters.read_bytes,
                    "read_formatted": _format_bytes(io_counters.read_bytes),
                    "write_bytes": io_counters.write_bytes,
                    "write_formatted": _format_bytes(io_counters.write_bytes),
                    "read_time_ms": io_counters.read_time,
                    "write_time_ms": io_counters.write_time,
                }
        except Exception:
            pass

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "partitions_count": len(partitions_data),
                "partitions": partitions_data,
                "disk_io": io_data,
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
            "error": {"code": "DISK_PERF_ERROR", "message": str(exc)},
        }


def get_resource_snapshot() -> Dict[str, Any]:
    """Capture a lightweight point-in-time system resource health snapshot."""
    tool_name = "get_resource_snapshot"
    domain = "performance"
    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        vmem = psutil.virtual_memory()
        smem = psutil.swap_memory()
        boot_ts = psutil.boot_time()
        uptime_sec = max(0, int(time.time() - boot_ts))

        # Check system drive
        sys_drive = os.environ.get("SystemDrive", "C:")
        if not sys_drive.endswith("\\"):
            sys_drive += "\\"
        sys_disk_pct = None
        try:
            usage = psutil.disk_usage(sys_drive)
            sys_disk_pct = usage.percent
        except Exception:
            pass

        # Top 3 CPU and Memory consumers
        top_cpu_res = get_top_cpu_processes(limit=3)
        top_cpu = top_cpu_res.get("data", {}).get("processes", []) if top_cpu_res.get("success") else []

        top_mem_res = get_top_memory_processes(limit=3)
        top_mem = top_mem_res.get("data", {}).get("processes", []) if top_mem_res.get("success") else []

        # Total process count
        total_pids = len(psutil.pids())

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "cpu_percent": cpu_pct,
                "memory_percent": vmem.percent,
                "memory_available_formatted": _format_bytes(vmem.available),
                "swap_percent": smem.percent,
                "system_drive_percent_used": sys_disk_pct,
                "total_processes_running": total_pids,
                "uptime_seconds": uptime_sec,
                "uptime_formatted": _format_seconds(uptime_sec),
                "top_cpu_consumers": top_cpu,
                "top_memory_consumers": top_mem,
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
            "error": {"code": "SNAPSHOT_ERROR", "message": str(exc)},
        }
