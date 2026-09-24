"""Read-only Windows Network Diagnostic Tools for WinFix AI.

Provides structured diagnostic observation for network adapters, DNS resolution,
and internet reachability without modifying IP configuration, firewall, or adapter state.
"""

import logging
import socket
import time
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


def get_network_adapters_diagnostics() -> Dict[str, Any]:
    """Collect read-only network adapter link state, MAC, and IP configuration."""
    tool_name = "get_network_adapters_diagnostics"
    domain = "network"
    try:
        if_addrs = psutil.net_if_addrs()
        if_stats = psutil.net_if_stats()

        adapters: List[Dict[str, Any]] = []
        for if_name, addr_list in if_addrs.items():
            stat = if_stats.get(if_name)
            is_up = stat.isup if stat else False
            speed_mbps = stat.speed if stat else 0

            ipv4_list: List[str] = []
            ipv6_list: List[str] = []
            mac: Optional[str] = None

            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    ipv4_list.append(addr.address)
                elif hasattr(socket, "AF_INET6") and addr.family == socket.AF_INET6:
                    ipv6_list.append(addr.address.split("%")[0])
                elif addr.family == -1 or getattr(addr, "address", "").count("-") == 5 or getattr(addr, "address", "").count(":") == 5:
                    mac = addr.address

            adapters.append(
                {
                    "name": if_name,
                    "is_up": is_up,
                    "speed_mbps": speed_mbps,
                    "ipv4": ipv4_list,
                    "ipv6": ipv6_list,
                    "mac": mac,
                }
            )

        active = [a for a in adapters if a["is_up"] and a["ipv4"]]

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "total_adapters": len(adapters),
                "active_adapters": len(active),
                "adapters": adapters,
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
            "error": {"code": "ADAPTER_QUERY_ERROR", "message": str(exc)},
        }


def check_dns_resolution(hostname: str = "dns.google", timeout: float = 3.0) -> Dict[str, Any]:
    """Test DNS resolution for a target hostname and measure resolution latency."""
    tool_name = "check_dns_resolution"
    domain = "network"
    start_time = time.time()
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            resolved_ips = list({res[4][0] for res in addr_info if res and len(res) > 4})
        finally:
            socket.setdefaulttimeout(old_timeout)

        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "target_host": hostname,
                "resolved": len(resolved_ips) > 0,
                "resolved_ips": resolved_ips,
                "latency_ms": latency_ms,
            },
            "error": None,
        }
    except socket.gaierror as gai_err:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        logger.debug("DNS resolution lookup failed for %s: %s", hostname, gai_err)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "target_host": hostname,
                "resolved": False,
                "resolved_ips": [],
                "latency_ms": latency_ms,
            },
            "error": {"code": "DNS_RESOLUTION_FAILED", "message": f"Could not resolve host '{hostname}': {gai_err}"},
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "DNS_CHECK_ERROR", "message": str(exc)},
        }


def check_internet_connectivity(
    target_host: str = "1.1.1.1",
    port: int = 53,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    """Test direct network connectivity to an external IP and measure socket latency."""
    tool_name = "check_internet_connectivity"
    domain = "network"
    start_time = time.time()
    sock = None
    try:
        sock = socket.create_connection((target_host, port), timeout=timeout)
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "target": f"{target_host}:{port}",
                "reachable": True,
                "latency_ms": latency_ms,
            },
            "error": None,
        }
    except (socket.timeout, TimeoutError) as t_err:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"target": f"{target_host}:{port}", "reachable": False, "latency_ms": None},
            "error": {"code": "CONNECTION_TIMEOUT", "message": f"Connection to {target_host}:{port} timed out: {t_err}"},
        }
    except (OSError, socket.error) as sock_err:
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"target": f"{target_host}:{port}", "reachable": False, "latency_ms": None},
            "error": {"code": "HOST_UNREACHABLE", "message": f"Could not connect to {target_host}:{port}: {sock_err}"},
        }
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def get_dns_client_config() -> Dict[str, Any]:
    """Collect read-only configured DNS name servers from Windows registry."""
    tool_name = "get_dns_client_config"
    domain = "network"
    try:
        import winreg

        dns_servers: List[str] = []
        tcpip_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, tcpip_path) as key:
            try:
                val, _ = winreg.QueryValueEx(key, "NameServer")
                if val:
                    dns_servers.extend([s.strip() for s in val.split(",") if s.strip()])
            except OSError:
                pass
            try:
                val, _ = winreg.QueryValueEx(key, "DhcpNameServer")
                if val:
                    dns_servers.extend([s.strip() for s in val.split(" ") if s.strip()])
            except OSError:
                pass

        # Deduplicate while preserving order
        unique_servers = list(dict.fromkeys(dns_servers))

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "dns_servers": unique_servers,
                "count": len(unique_servers),
            },
            "error": None,
        }
    except Exception as exc:
        logger.debug("DNS config query failed: %s", exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": {"dns_servers": [], "count": 0},
            "error": {"code": "REGISTRY_QUERY_ERROR", "message": str(exc)},
        }
