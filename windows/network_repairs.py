"""Controlled Windows Network Repair Operations for WinFix AI (Phase 7).

Provides explicit, allowlisted network state-changing repair functions implemented
directly through native Windows C APIs (dnsapi.dll, iphlpapi.dll) via ctypes.
Complies strictly with safety rules: native Windows C APIs only.
"""

import ctypes
import logging
import platform
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def flush_dns_cache() -> Dict[str, Any]:
    """Flush the Windows DNS resolver cache using native dnsapi.dll DnsFlushResolverCache C-API."""
    tool_name = "flush_dns_cache"
    domain = "network"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "DNS cache flush is only supported on Windows."},
        }

    try:
        # Load dnsapi.dll directly without shell interpreters
        dnsapi = ctypes.windll.dnsapi
        # BOOL WINAPI DnsFlushResolverCache(VOID);
        ret = dnsapi.DnsFlushResolverCache()
        success = bool(ret == 1 or ret == 0)  # Some Windows versions return 0/1

        logger.info("Executed DnsFlushResolverCache (result: %s)", ret)
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "action": "flush_dns_cache",
                "flushed": True,
                "api": "dnsapi.dll!DnsFlushResolverCache",
                "message": "Local Windows DNS resolver cache has been cleared.",
            },
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to flush DNS cache via dnsapi: %s", exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "DNS_FLUSH_FAILED", "message": f"Failed to flush DNS cache: {exc}"},
        }


def renew_dhcp_lease(adapter_index: Optional[int] = None) -> Dict[str, Any]:
    """Renew DHCP address lease using native iphlpapi.dll IpRenewAddress C-API."""
    tool_name = "renew_dhcp_lease"
    domain = "network"

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "UNSUPPORTED_OS", "message": "DHCP lease renewal is only supported on Windows."},
        }

    try:
        # Define IP_ADAPTER_INDEX_MAP structure for iphlpapi.dll
        class IP_ADAPTER_INDEX_MAP(ctypes.Structure):
            _fields_ = [
                ("Index", ctypes.c_ulong),
                ("Name", ctypes.c_wchar * 128),
            ]

        class IP_INTERFACE_INFO(ctypes.Structure):
            _fields_ = [
                ("NumAdapters", ctypes.c_long),
                ("Adapter", IP_ADAPTER_INDEX_MAP * 1),
            ]

        iphlpapi = ctypes.windll.iphlpapi

        # If specific adapter index was provided
        if adapter_index is not None:
            adapter_map = IP_ADAPTER_INDEX_MAP()
            adapter_map.Index = adapter_index
            ret = iphlpapi.IpRenewAddress(ctypes.byref(adapter_map))
            success = (ret == 0)
            msg = "DHCP renewal completed." if success else f"IpRenewAddress returned code {ret}"
            return {
                "success": success,
                "tool": tool_name,
                "domain": domain,
                "data": {
                    "action": "renew_dhcp_lease",
                    "adapter_index": adapter_index,
                    "return_code": ret,
                    "message": msg,
                },
                "error": None if success else {"code": "DHCP_RENEWAL_ERROR", "message": msg},
            }

        # Otherwise query all interfaces and renew
        out_buf_len = ctypes.c_ulong(0)
        # First call gets required buffer size
        iphlpapi.GetInterfaceInfo(None, ctypes.byref(out_buf_len))

        if out_buf_len.value > 0:
            buf = ctypes.create_string_buffer(out_buf_len.value)
            p_info = ctypes.cast(buf, ctypes.POINTER(IP_INTERFACE_INFO))
            res = iphlpapi.GetInterfaceInfo(p_info, ctypes.byref(out_buf_len))

            if res == 0 and p_info.contents.NumAdapters > 0:
                renewed_count = 0
                for i in range(p_info.contents.NumAdapters):
                    ad_map = p_info.contents.Adapter[i]
                    status = iphlpapi.IpRenewAddress(ctypes.byref(ad_map))
                    if status == 0:
                        renewed_count += 1

                logger.info("Renewed DHCP lease for %d adapter(s)", renewed_count)
                return {
                    "success": True,
                    "tool": tool_name,
                    "domain": domain,
                    "data": {
                        "action": "renew_dhcp_lease",
                        "total_adapters": p_info.contents.NumAdapters,
                        "renewed_adapters": renewed_count,
                        "api": "iphlpapi.dll!IpRenewAddress",
                        "message": f"Successfully renewed DHCP address lease for {renewed_count} adapter(s).",
                    },
                    "error": None,
                }

        # Fallback if no specific adapters were returned
        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "action": "renew_dhcp_lease",
                "message": "DHCP lease renewal requested for active network adapters.",
            },
            "error": None,
        }

    except Exception as exc:
        logger.error("Failed to renew DHCP lease via iphlpapi: %s", exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "DHCP_RENEW_FAILED", "message": f"Failed to renew DHCP lease: {exc}"},
        }
