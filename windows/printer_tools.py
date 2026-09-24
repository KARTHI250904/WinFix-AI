"""Read-only Windows Printer Diagnostic Tools for WinFix AI.

Provides structured printer enumeration, default printer identification, and
Print Spooler service diagnostics without submitting print jobs, modifying drivers,
or deleting printers.
"""

import logging
from typing import Any, Dict, List, Optional

from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)


def get_printer_diagnostics() -> Dict[str, Any]:
    """Inspect read-only Print Spooler status and installed printers."""
    tool_name = "get_printer_diagnostics"
    domain = "printer"
    try:
        # Check Print Spooler service
        spooler_res = get_service_status("Spooler")
        spooler_running = spooler_res.get("data", {}).get("is_running", False)
        spooler_status = spooler_res.get("data", {}).get("status", "unknown")

        printers_list: List[Dict[str, Any]] = []
        default_printer: Optional[str] = None

        try:
            import win32print

            # Get default printer
            try:
                default_printer = win32print.GetDefaultPrinter()
            except Exception:
                default_printer = None

            # Enum all local and connection printers (flags: PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS)
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            raw_printers = win32print.EnumPrinters(flags)
            for p in raw_printers:
                # p is a tuple: (flags, description, name, comment)
                p_name = p[2] if len(p) > 2 else (p[1] if len(p) > 1 else str(p))
                printers_list.append(
                    {
                        "name": p_name,
                        "is_default": (p_name == default_printer),
                        "description": p[1] if len(p) > 1 else "",
                        "comment": p[3] if len(p) > 3 else "",
                    }
                )
        except ImportError:
            logger.debug("win32print not available, falling back to basic printer status")
        except Exception as p_err:
            logger.debug("Failed to enum printers via win32print: %s", p_err)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "spooler_service_status": spooler_status,
                "spooler_running": spooler_running,
                "total_printers": len(printers_list),
                "default_printer": default_printer,
                "printers": printers_list,
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
            "error": {"code": "PRINTER_QUERY_ERROR", "message": str(exc)},
        }
