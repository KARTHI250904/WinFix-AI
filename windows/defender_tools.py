"""Read-only Windows Defender and Security Diagnostic Tools for WinFix AI.

Provides structured Microsoft Defender Antivirus and Windows Security status
diagnostics. STRICT RULE: Read-only inspection only. Never disables Defender,
alters real-time protection, or modifies security policies.
"""

import logging
from typing import Any, Dict

from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)


def get_defender_diagnostics() -> Dict[str, Any]:
    """Inspect read-only Microsoft Defender Antivirus and Security Center service status."""
    tool_name = "get_defender_diagnostics"
    domain = "defender"
    try:
        # Check core Defender and Security Health services
        windefend = get_service_status("WinDefend")
        wdnissvc = get_service_status("WdNisSvc")
        sec_health = get_service_status("SecurityHealthService")
        firewall = get_service_status("mpssvc")

        # Read signature / engine versions from registry if accessible
        signature_version = None
        engine_version = None
        product_version = None
        try:
            import winreg

            sig_path = r"SOFTWARE\Microsoft\Windows Defender\Signature Updates"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sig_path) as key:
                try:
                    signature_version, _ = winreg.QueryValueEx(key, "AVSignatureVersion")
                except OSError:
                    pass
                try:
                    engine_version, _ = winreg.QueryValueEx(key, "EngineVersion")
                except OSError:
                    pass
        except Exception as reg_exc:
            logger.debug("Could not query Defender signature registry key: %s", reg_exc)

        antivirus_running = windefend.get("data", {}).get("is_running", False)
        firewall_running = firewall.get("data", {}).get("is_running", False)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "antivirus_service_running": antivirus_running,
                "firewall_service_running": firewall_running,
                "services": {
                    "WinDefend": {
                        "status": windefend.get("data", {}).get("status", "unknown"),
                        "is_running": antivirus_running,
                    },
                    "WdNisSvc": {
                        "status": wdnissvc.get("data", {}).get("status", "unknown"),
                        "is_running": wdnissvc.get("data", {}).get("is_running", False),
                    },
                    "SecurityHealthService": {
                        "status": sec_health.get("data", {}).get("status", "unknown"),
                        "is_running": sec_health.get("data", {}).get("is_running", False),
                    },
                    "mpssvc": {
                        "status": firewall.get("data", {}).get("status", "unknown"),
                        "is_running": firewall_running,
                    },
                },
                "signature_version": signature_version,
                "engine_version": engine_version,
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
            "error": {"code": "DEFENDER_QUERY_ERROR", "message": str(exc)},
        }
