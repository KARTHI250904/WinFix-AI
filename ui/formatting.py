"""Formatting utilities for WinFix AI presentation layer (Phases 20 & 35).

Provides consistent string, badge, risk level, timestamp, size, confidence,
and user-facing terminology formatters.
Enforces plain, readable, calm output for technical and non-technical users.
"""

from datetime import datetime
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Union

from agent.tool_metadata import RiskLevel


class ConfidenceLevel(str, Enum):
    """User-facing confidence levels grounded in evidence and verification semantics."""

    HIGH = "High confidence"
    MODERATE = "Moderate confidence"
    LOW = "Low confidence"
    UNKNOWN = "Not enough information"


USER_FACING_TERMINOLOGY: Dict[str, str] = {
    "diagnosis": "What we found",
    "evidence": "Why we think this",
    "hypothesis": "Possible cause",
    "tool": "Windows check / action",
    "medium_risk": "Requires your approval",
    "safe_risk": "Safe read-only check",
    "verification": "Check whether the fix worked",
    "recovery": "Safely continue",
    "telemetry": "Technical diagnostics",
    "autopilot": "Automated safe troubleshooting",
    "tutor": "Personal learning guide",
}


def map_confidence(
    evidence_count: int = 0,
    contradictions_found: bool = False,
    is_uncertain: bool = False,
    hypothesis_status: str = "CONFIRMED",
) -> str:
    """Deterministically map evidence state and contradiction flags to human confidence levels.
    
    Prevents false numerical precision (e.g. 97.384%) and adheres strictly to evidence grounding.
    """
    if contradictions_found or is_uncertain:
        return ConfidenceLevel.LOW.value if evidence_count > 0 else ConfidenceLevel.UNKNOWN.value

    status_clean = str(hypothesis_status).upper().strip()
    if evidence_count >= 3 and status_clean in ("CONFIRMED", "HIGH", "SUPPORTED"):
        return ConfidenceLevel.HIGH.value
    elif evidence_count >= 1 and status_clean not in ("REJECTED", "INVALIDATED", "CONTRADICTED"):
        return ConfidenceLevel.MODERATE.value
    elif evidence_count == 0:
        return ConfidenceLevel.UNKNOWN.value
    return ConfidenceLevel.LOW.value


def format_user_friendly_terminology(term: str) -> str:
    """Translate internal engineering terms to calm, plain English."""
    key = term.lower().strip().replace(" ", "_")
    return USER_FACING_TERMINOLOGY.get(key, term)


def format_progress_step(step_name: str) -> str:
    """Map internal workflow steps to user-facing progress descriptions."""
    step_clean = str(step_name).upper().strip()
    step_descriptions = {
        "INPUT": "Understanding your problem",
        "ANALYSIS": "Checking system information",
        "EVIDENCE": "Collecting diagnostic clues",
        "KNOWLEDGE": "Checking known Windows patterns",
        "DIAGNOSTIC": "Looking for the likely cause",
        "ACTION": "Applying approved fix",
        "VERIFICATION": "Checking whether the fix worked",
    }
    return step_descriptions.get(step_clean, f"Step: {step_name}")


def format_human_verification_status(verification_status: str) -> str:
    """Translate raw verification statuses into plain-language outcome statements."""
    st_clean = str(verification_status).lower().strip()
    if st_clean in ("verified", "success"):
        return "Fix verified — Windows is now in the expected healthy state."
    elif "partial" in st_clean:
        return "The repair improved the situation, but the original problem is not fully resolved."
    elif "timeout" in st_clean:
        return "Verification timed out before confirming healthy state recovery."
    elif st_clean in ("not_verified", "failed", "error"):
        return "The fix did not resolve the problem. Windows is not in the expected state."
    return f"Verification outcome: {verification_status}"


def format_bytes(size_bytes: Union[int, float]) -> str:
    """Format byte counts into human-readable strings (KB, MB, GB)."""
    if size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    idx = 0
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def format_timestamp(iso_timestamp: Optional[str]) -> str:
    """Convert ISO timestamp string to friendly user-readable date/time format."""
    if not iso_timestamp:
        return "Unknown time"
    try:
        # Handle trailing Z or offset if present
        clean_ts = str(iso_timestamp).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except Exception:
        return str(iso_timestamp)[:19]


def format_risk_badge(risk: Union[RiskLevel, str]) -> str:
    """Generate textual risk badge with explicit safety categorization."""
    risk_val = risk.value if isinstance(risk, RiskLevel) else str(risk).upper()
    if risk_val == "SAFE":
        return "🛡️ SAFE (Read-Only Diagnostic)"
    elif risk_val == "MEDIUM":
        return "⚠️ MEDIUM (User Confirmation Required)"
    elif risk_val == "HIGH":
        return "🚫 HIGH (Strictly Blocked by Policy)"
    return f"❓ {risk_val}"


def format_status_badge(status: str) -> str:
    """Format execution or verification status into an unambiguous textual indicator."""
    st_clean = status.upper().strip()
    if st_clean in ("VERIFIED", "SUCCESS", "RUNNING", "HEALTHY", "ACTIVE"):
        return f"✓ {st_clean}"
    elif st_clean in ("NOT_VERIFIED", "WARNING", "ELEVATED", "TIMEOUT", "VERIFICATION_TIMEOUT"):
        return f"⚠ {st_clean}"
    elif st_clean in ("FAILED", "BLOCKED", "ERROR", "CRITICAL", "STOPPED"):
        return f"✕ {st_clean}"
    return f"● {st_clean}"


def format_severity_badge(severity: str) -> str:
    """Format severity classification for diagnostics and knowledge articles."""
    sev = str(severity).upper().strip()
    if sev in ("LOW", "INFO", "NORMAL"):
        return f"🟢 {sev}"
    elif sev in ("MEDIUM", "ELEVATED"):
        return f"🟡 {sev}"
    elif sev in ("HIGH", "CRITICAL"):
        return f"🔴 {sev}"
    return f"⚪ {sev}"


def format_tool_name(tool_id: str) -> str:
    """Convert snake_case tool ID to capitalized title words."""
    if not tool_id or not isinstance(tool_id, str):
        return "Unknown Tool"
    words = tool_id.replace("_", " ").split()
    return " ".join(w.capitalize() for w in words)


def truncate_text_safely(text: str, max_len: int = 120) -> str:
    """Truncate long string gracefully with an ellipsis if length exceeds bound."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3].rstrip() + "..."


def format_tutor_tool_description(tool_item: Any) -> str:
    """Format a tool identifier, name, or dictionary into a calm, human-friendly descriptive sentence."""
    if not tool_item:
        return "Windows diagnostic inspection."

    tool_name = ""
    tool_desc = ""

    if isinstance(tool_item, str):
        tool_clean = tool_item.strip().strip("'\"`")
        if tool_clean.startswith("{") and tool_clean.endswith("}"):
            try:
                import json
                parsed = json.loads(tool_clean)
                if isinstance(parsed, dict):
                    tool_item = parsed
            except Exception:
                pass

    if isinstance(tool_item, dict):
        tool_name = str(tool_item.get("tool_name") or tool_item.get("name") or tool_item.get("tool") or "").strip()
        tool_desc = str(tool_item.get("description") or tool_item.get("purpose") or tool_item.get("summary") or "").strip()
    elif isinstance(tool_item, str):
        tool_name = tool_item.strip()
    elif hasattr(tool_item, "name"):
        tool_name = getattr(tool_item, "name", "")
        tool_desc = getattr(tool_item, "description", "")

    if not tool_name:
        return tool_desc or "Windows diagnostic check."

    title = format_tool_name(tool_name)
    if not tool_desc:
        try:
            from agent.tool_registry import default_tool_registry
            tool_def = default_tool_registry.get(tool_name)
            if tool_def and tool_def.description:
                tool_desc = tool_def.description
        except Exception:
            pass

    if tool_desc:
        desc_clean = tool_desc.rstrip(".")
        return f"{title} — {desc_clean}."
    else:
        return f"{title} — safely checks {title.lower()} without modifying the system."


def _clean_single_tutor_string(text: str) -> Optional[str]:
    """Clean and unwrap a single string from raw Python/JSON representations."""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if not s or s.lower() in ("none", "[]", "{}", "null", "undefined", "''", '""'):
        return None

    # Strip list index prefixes like '0: "..."' or '1: ...'
    s = re.sub(r"^\d+:\s*", "", s).strip()

    # Strip leading/trailing outer quotes if present
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()

    # Strip bullet indicators
    s = re.sub(r"^[\s•\-\*]+\s*", "", s).strip()

    if not s or s.lower() in ("none", "[]", "{}", "null", "''", '""'):
        return None
    return s


def format_tutor_text_list(value: Any, fallback: Optional[str] = None) -> List[str]:
    """Convert structured tutor fields into a clean list of normal human-readable sentences.

    Safely handles:
    - str (normal sentence, bulleted list, JSON list/dict string)
    - list / tuple / set of strings or nested objects
    - dict (extracts message/summary/details/values or tool descriptions)
    - Pydantic / dataclass / model objects
    - None / empty collections
    """
    if value is None:
        return [fallback] if fallback else []

    items: List[str] = []

    # 1. String handling
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in ("none", "[]", "{}", "null", "''", '""'):
            return [fallback] if fallback else []

        # If the string appears to be a JSON list or dict, parse safely
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            try:
                import json
                parsed = json.loads(s)
                return format_tutor_text_list(parsed, fallback=fallback)
            except Exception:
                lines = s.strip("[]{}").split("\n")
                for line in lines:
                    cleaned = _clean_single_tutor_string(line)
                    if cleaned:
                        items.append(cleaned)
                if items:
                    return items

        # Check if multiline
        if "\n" in s:
            for line in s.split("\n"):
                cleaned = _clean_single_tutor_string(line)
                if cleaned:
                    items.append(cleaned)
            if items:
                return items

        cleaned = _clean_single_tutor_string(s)
        if cleaned:
            return [cleaned]
        return [fallback] if fallback else []

    # 2. List / Tuple / Set handling
    elif isinstance(value, (list, tuple, set)):
        for elem in value:
            sub_items = format_tutor_text_list(elem)
            for sub in sub_items:
                if sub and sub.lower() not in ("none", "[]", "{}"):
                    items.append(sub)

    # 3. Dict handling
    elif isinstance(value, dict):
        if not value:
            return [fallback] if fallback else []
        if "tool_name" in value or "tool" in value:
            return [format_tutor_tool_description(value)]
        found_key = False
        for k in ("explanation", "summary", "message", "text", "description", "details", "note", "title", "what_happened", "what_this_means"):
            if k in value and value[k]:
                sub_items = format_tutor_text_list(value[k])
                if sub_items:
                    items.extend(sub_items)
                    found_key = True
        if not found_key:
            for k, v in value.items():
                if v and str(v).lower() not in ("none", "[]", "{}"):
                    clean_v = format_tutor_prose(v)
                    if clean_v:
                        items.append(f"{format_user_friendly_terminology(str(k))}: {clean_v}")

    # 4. Dataclass / Model-like object handling
    elif hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        return format_tutor_text_list(value.to_dict(), fallback=fallback)
    elif hasattr(value, "__dict__"):
        return format_tutor_text_list(vars(value), fallback=fallback)
    else:
        cleaned = _clean_single_tutor_string(str(value))
        if cleaned:
            items.append(cleaned)

    # Filter empty / duplicate consecutive items
    final_items: List[str] = []
    for it in items:
        cleaned = _clean_single_tutor_string(it)
        if cleaned and cleaned not in final_items:
            final_items.append(cleaned)

    if not final_items and fallback:
        return [fallback]
    return final_items


def format_tutor_prose(value: Any, fallback: Optional[str] = None) -> Optional[str]:
    """Convert structured tutor field into a single coherent human-readable prose string."""
    items = format_tutor_text_list(value, fallback=fallback)
    if not items:
        return fallback
    if len(items) == 1:
        return items[0]
    return " ".join(items)


DIAGNOSTIC_KEY_LABELS: Dict[str, str] = {
    "target_host": "Target Host",
    "target": "Target Address",
    "resolved": "Resolution Status",
    "resolved_ips": "Resolved IP Addresses",
    "latency_ms": "Latency",
    "reachable": "Reachability",
    "requires_admin": "Requires Admin",
    "read_only": "Read Only",
    "automatic_allowed": "Automatic Execution Allowed",
    "verification_tool": "Verification Tool",
    "speed_mbps": "Link Speed",
    "ipv4": "IPv4 Addresses",
    "ipv6": "IPv6 Addresses",
    "mac_address": "MAC Address",
    "is_up": "Interface Status",
    "is_running": "Service Status",
    "antivirus_service_running": "Antivirus Protection",
    "firewall_service_running": "Windows Firewall",
    "signature_version": "Signature Version",
    "update_services_ready": "Update Subsystem Ready",
    "last_success_time": "Last Successful Update",
    "spooler_running": "Print Spooler Status",
    "default_printer": "Default Printer",
    "total_printers": "Installed Printers Count",
    "service_running": "Service Status",
    "adapter_detected": "Hardware Detected",
    "percent_used": "Usage Percentage",
    "free_formatted": "Free Space",
    "total_formatted": "Total Capacity",
    "used_formatted": "Used Space",
    "tool": "Diagnostic Tool",
    "domain": "Domain",
    "success": "Outcome",
    "error": "Error Details",
    "pid": "Process ID",
    "cpu_percent": "CPU Usage",
    "memory_percent": "Memory Usage",
    "memory_formatted": "Memory Footprint",
}


def format_key_label(key: str) -> str:
    """Intelligently translate snake_case or technical keys into human-readable labels."""
    k_clean = str(key).lower().strip()
    if k_clean in DIAGNOSTIC_KEY_LABELS:
        return DIAGNOSTIC_KEY_LABELS[k_clean]
    words = k_clean.replace("_", " ").split()
    return " ".join(w.capitalize() for w in words)


def format_diagnostic_value(key: str, value: Any) -> str:
    """Format diagnostic parameter values into calm, plain-language text."""
    if value is None:
        if str(key).lower() == "error":
            return "No error reported"
        return "Not available"

    k_lower = str(key).lower()

    # Boolean handling with domain context
    if isinstance(value, bool):
        if k_lower in ("resolved", "is_resolved"):
            return "Successful" if value else "Failed"
        elif k_lower in ("reachable", "is_reachable"):
            return "Target is reachable" if value else "Target is unreachable"
        elif k_lower in ("success", "is_success"):
            return "PASS" if value else "FAILED"
        elif k_lower in ("is_running", "running", "service_running", "spooler_running"):
            return "Running" if value else "Stopped"
        elif k_lower in ("is_up", "up"):
            return "Active" if value else "Inactive"
        elif k_lower in ("adapter_detected", "detected"):
            return "Detected" if value else "Not detected"
        elif k_lower in ("requires_admin", "admin_required"):
            return "Yes" if value else "No"
        elif k_lower in ("read_only", "readonly"):
            return "Yes" if value else "No"
        elif k_lower in ("automatic_allowed",):
            return "Yes" if value else "No"
        return "Yes" if value else "No"

    # List handling
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "None reported"
        if all(isinstance(x, (str, int, float)) for x in value):
            return ", ".join(str(x) for x in value)
        return f"{len(value)} items"

    # Numeric unit handling
    if isinstance(value, (int, float)):
        if "latency" in k_lower or "duration" in k_lower or "ms" in k_lower:
            return f"{value:.1f} ms" if isinstance(value, float) else f"{value} ms"
        elif "percent" in k_lower or "pct" in k_lower:
            return f"{value:.1f}%" if isinstance(value, float) else f"{value}%"
        elif "mbps" in k_lower or "speed" in k_lower:
            return f"{value} Mbps"
        elif "bytes" in k_lower:
            return format_bytes(value)

    return str(value)


def format_diagnostic_status(success: Any) -> str:
    """Format success indicator into standard PASS/FAILED badge."""
    if success is True or str(success).upper() in ("TRUE", "PASS", "SUCCESS", "VERIFIED"):
        return "✓ PASS"
    elif success is False or str(success).upper() in ("FALSE", "FAIL", "FAILED", "ERROR"):
        return "✕ FAILED"
    return str(success)


def render_structured_diagnostic_card(tool_name: str, payload: Any, st_module: Any = None) -> None:
    """Render a clean, human-readable diagnostic card in Streamlit with zero raw JSON in normal view."""
    import streamlit as st_ctx
    st_ui = st_module or st_ctx

    if not isinstance(payload, dict):
        st_ui.info(format_tutor_prose(payload, fallback="Diagnostic completed."))
        return

    # Extract metadata fields
    tool_id = payload.get("tool") or tool_name or "Windows Diagnostic"
    title = format_tool_name(tool_id)
    success = payload.get("success", True)
    domain = format_user_friendly_terminology(str(payload.get("domain") or "System"))
    data_dict = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    err = payload.get("error")

    status_badge = format_diagnostic_status(success)
    st_ui.markdown(f"#### 🔍 {title}")
    
    # Summary header
    try:
        cols = st_ui.columns([2, 2, 2])
        if isinstance(cols, (list, tuple)) and len(cols) >= 3:
            with cols[0]:
                st_ui.write(f"**Status:** `{status_badge}`")
            with cols[1]:
                st_ui.write(f"**Domain:** {domain.capitalize()}")
            with cols[2]:
                st_ui.write(f"**Tool:** `{tool_id}`")
        else:
            st_ui.write(f"**Status:** `{status_badge}` | **Domain:** {domain.capitalize()} | **Tool:** `{tool_id}`")
    except Exception:
        st_ui.write(f"**Status:** `{status_badge}` | **Domain:** {domain.capitalize()} | **Tool:** `{tool_id}`")

    # Data elements in human-readable presentation
    if data_dict:
        items_to_render = []
        lists_to_render = []

        for k, v in data_dict.items():
            lbl = format_key_label(k)
            if isinstance(v, (list, tuple, set)) and len(v) > 0 and not isinstance(v, (str, bytes)):
                lists_to_render.append((lbl, v))
            elif isinstance(v, dict):
                # Flatten nested dict
                for sub_k, sub_v in v.items():
                    sub_lbl = f"{lbl} — {format_key_label(sub_k)}"
                    items_to_render.append((sub_lbl, format_diagnostic_value(sub_k, sub_v)))
            else:
                items_to_render.append((lbl, format_diagnostic_value(k, v)))

        if items_to_render:
            rows_md = [f"| **{lbl}** | {val} |" for lbl, val in items_to_render]
            table_md = "| Property | Value |\n| :--- | :--- |\n" + "\n".join(rows_md)
            st_ui.markdown(table_md)

        if lists_to_render:
            for l_title, l_items in lists_to_render:
                st_ui.markdown(f"**{l_title}:**")
                for it in l_items:
                    st_ui.write(f"• `{it}`" if isinstance(it, str) and ("." in it or ":" in it) else f"• {it}")

    # Error handling
    if err:
        st_ui.error(f"**Error Details:** {err}")
    else:
        st_ui.caption("✓ No error reported by diagnostic handler.")

    # Developer view with clean table view and raw payload
    with st_ui.expander(f"🔍 Raw Payload — Developer View ({tool_id})", expanded=False):
        st_ui.markdown("##### 📊 Diagnostic Properties Table")
        render_json_as_table(payload, st_ui)
        st_ui.markdown("---")
        st_ui.markdown("##### 📋 Raw JSON Payload")
        st_ui.json(payload)


def render_json_as_table(data: Any, st_module: Any = None, title: Optional[str] = None) -> None:
    """Render any JSON-like dictionary or list as a clean, human-readable Streamlit table."""
    import streamlit as st_ctx
    st_ui = st_module or st_ctx

    if not isinstance(data, (dict, list)):
        st_ui.write(f"**Value:** `{data}`")
        return

    def _flatten_data(obj: Any, prefix: str = "") -> List[Any]:
        rows = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_label = f"{prefix}.{k}" if prefix else str(k)
                if isinstance(v, dict):
                    rows.extend(_flatten_data(v, k_label))
                elif isinstance(v, list):
                    if not v:
                        rows.append((k_label, "None / Empty"))
                    elif all(not isinstance(item, (dict, list)) for item in v):
                        rows.append((k_label, ", ".join(str(item) for item in v)))
                    else:
                        for idx, item in enumerate(v):
                            rows.extend(_flatten_data(item, f"{k_label}[{idx}]"))
                else:
                    rows.append((k_label, format_diagnostic_value(k, v)))
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                rows.extend(_flatten_data(item, f"{prefix}[{idx}]" if prefix else f"[{idx}]"))
        else:
            rows.append((prefix or "value", str(obj)))
        return rows

    rows = _flatten_data(data)
    if rows:
        table_rows = [f"| `{k}` | {v} |" for k, v in rows]
        table_md = "| Diagnostic Property | Value |\n| :--- | :--- |\n" + "\n".join(table_rows)
        st_ui.markdown(table_md)
    else:
        st_ui.caption("No data to display in table.")


def extract_diagnostic_summary_text(tool_id: str, payload: Any) -> str:
    """Extract a concise, human-readable summary finding from a diagnostic payload."""
    if not isinstance(payload, dict):
        return str(payload) if payload is not None else "Diagnostic completed."

    data = payload.get("data")
    err = payload.get("error")
    success = payload.get("success", True)
    t_clean = str(payload.get("tool") or tool_id).lower().strip()

    if err and not success:
        return f"Error: {err}"

    if isinstance(data, dict):
        # 1. DNS Resolution
        if "dns" in t_clean or "resolved" in data:
            host = data.get("target_host", "DNS")
            res = data.get("resolved", True)
            lat = data.get("latency_ms")
            ips = data.get("resolved_ips", [])
            lat_str = f" ({lat:.1f} ms)" if isinstance(lat, (int, float)) else ""
            ip_str = f", {len(ips)} IP(s)" if isinstance(ips, list) and ips else ""
            return f"Target '{host}' {'resolved' if res else 'resolution failed'}{lat_str}{ip_str}"

        # 2. Internet Connectivity
        if "internet" in t_clean or "reachable" in data:
            tgt = data.get("target", "Internet Gateway")
            reach = data.get("reachable", True)
            lat = data.get("latency_ms")
            lat_str = f" ({lat:.1f} ms)" if isinstance(lat, (int, float)) else ""
            return f"Target '{tgt}' {'reachable' if reach else 'unreachable'}{lat_str}"

        # 3. Network Adapters
        if "adapter" in t_clean:
            adapters = data.get("adapters", [])
            active = data.get("active_adapters", [])
            if adapters or active:
                tot = len(adapters) if isinstance(adapters, list) else 1
                act = len(active) if isinstance(active, list) else 1
                return f"{tot} adapter(s) detected ({act} active)"
            return "Network adapter interfaces inspected"

        # 4. CPU Processes
        if "cpu" in t_clean and "processes" in data:
            procs = data.get("processes", [])
            if procs and isinstance(procs, list):
                top_p = procs[0] if isinstance(procs[0], dict) else {}
                p_name = top_p.get("name", "process")
                p_cpu = top_p.get("cpu_percent", 0.0)
                return f"{len(procs)} processes monitored (Top: {p_name} @ {p_cpu}%)"
            return "CPU process utilization monitored"

        # 5. Memory Processes
        if "memory" in t_clean and "processes" in data:
            procs = data.get("processes", [])
            if procs and isinstance(procs, list):
                top_p = procs[0] if isinstance(procs[0], dict) else {}
                p_name = top_p.get("name", "process")
                p_mem = top_p.get("memory_formatted") or f"{top_p.get('memory_percent', 0.0)}%"
                return f"{len(procs)} processes monitored (Top: {p_name} @ {p_mem})"
            return "Memory process utilization monitored"

        # 6. Storage Diagnostics
        if "storage" in t_clean and "temp" not in t_clean:
            drives = data.get("drives", [])
            low_warn = data.get("low_space_warning", False)
            if isinstance(drives, list) and drives:
                warn_str = " (Low space alert)" if low_warn else " (Healthy)"
                return f"{len(drives)} drive(s) evaluated{warn_str}"
            return "Drives and partitions evaluated"

        # 7. Temp Storage
        if "temp" in t_clean or "temp_size_bytes" in data:
            sz = data.get("temp_size_formatted") or format_bytes(data.get("temp_size_bytes", 0))
            return f"Temporary storage cache: {sz}"

        # 8. Windows Services
        if "service" in t_clean:
            svcs = data.get("services", [])
            if isinstance(svcs, list) and svcs:
                return f"{len(svcs)} common service states inspected"
            run = data.get("service_running") or data.get("is_running")
            if run is not None:
                return f"Service status: {'Running' if run else 'Stopped'}"
            return "Windows service states checked"

        # 9. Defender Diagnostics
        if "defender" in t_clean:
            rtp = data.get("real_time_protection")
            av = data.get("antivirus_enabled")
            status_txt = "Active" if (rtp or av) else "Inactive/Standby"
            return f"Real-time protection: {status_txt}"

        # 10. Windows Update Diagnostics
        if "update" in t_clean:
            pending = data.get("pending_updates", 0)
            ready = data.get("update_services_ready", True)
            if pending:
                return f"{pending} update(s) pending"
            return f"Update services {'ready' if ready else 'need attention'}"

        # 11. Printer Diagnostics
        if "printer" in t_clean:
            spooler = data.get("spooler_running", True)
            tot_p = data.get("total_printers", 0)
            return f"Spooler {'running' if spooler else 'stopped'} ({tot_p} printer(s))"

        # 12. Bluetooth Diagnostics
        if "bluetooth" in t_clean:
            svc = data.get("service_running", True)
            det = data.get("adapter_detected", True)
            return f"Service {'running' if svc else 'stopped'} ({'Adapter detected' if det else 'No adapter'})"

        # 13. Application Crash & Events
        if "crash" in t_clean or "event" in t_clean:
            crashes = data.get("crashes", [])
            tot = data.get("total_crashes", len(crashes) if isinstance(crashes, list) else 0)
            return f"{tot} application crash event(s) recorded"

        # 14. Windows Error Reporting (WER)
        if "wer" in t_clean or "error_reporting" in t_clean:
            en = data.get("enabled", True)
            return f"Windows Error Reporting is {'enabled' if en else 'disabled'}"

        # Generic dict summary (extract up to 2 key-value pairs)
        parts = []
        for k, v in list(data.items())[:2]:
            if not isinstance(v, (dict, list)):
                parts.append(f"{format_key_label(k)}: {format_diagnostic_value(k, v)}")
        if parts:
            return ", ".join(parts)

    return "Diagnostic completed successfully" if success else (err or "Check completed")


def render_diagnostic_results_table(diag_data: Dict[str, Any], st_module: Any = None) -> None:
    """Render complete diagnostics payload in clean, professional Markdown tables matching Approved Tool Registry style."""
    import streamlit as st_ctx
    st_ui = st_module or st_ctx

    if not isinstance(diag_data, dict) or not diag_data:
        st_ui.info("No diagnostic checks executed yet.")
        return

    table_rows = []
    detail_blocks = []

    for diag_key, payload in diag_data.items():
        if isinstance(payload, dict):
            tool_id = str(payload.get("tool") or diag_key)
            domain_raw = str(payload.get("domain") or "System")
            success = payload.get("success", True)
            data = payload.get("data")
            error = payload.get("error")
        else:
            tool_id = str(diag_key)
            domain_raw = "System"
            success = True
            data = payload
            error = None

        domain = format_user_friendly_terminology(domain_raw).capitalize()
        status_badge = format_diagnostic_status(success)
        findings = extract_diagnostic_summary_text(tool_id, payload)

        table_rows.append(
            f"| `{tool_id}` | {domain} | `{status_badge}` | {findings} |"
        )

        # Build structured parameter-value table for each diagnostic result
        if isinstance(data, dict) and data:
            item_rows = []
            for k, v in data.items():
                k_label = format_key_label(k)
                if isinstance(v, list):
                    v_str = ", ".join(str(x) for x in v) if v else "(empty)"
                elif isinstance(v, dict):
                    v_str = ", ".join(f"{dk}: {dv}" for dk, dv in v.items())
                elif v is None:
                    v_str = "None"
                elif isinstance(v, bool):
                    v_str = "True" if v else "False"
                elif isinstance(v, float):
                    v_str = f"{v:.2f} ms" if "latency" in k.lower() else f"{v:.2f}"
                else:
                    v_str = str(v)
                item_rows.append(f"| {k_label} | `{v_str}` |")

            if error:
                item_rows.append(f"| Error Details | `{error}` |")

            if item_rows:
                detail_blocks.append(
                    f"###### `{tool_id}` Diagnostic Findings\n"
                    f"| Parameter | Value |\n| --- | --- |\n"
                    + "\n".join(item_rows)
                )

    main_table = "| Tool | Domain | Status | Key Findings |\n| --- | --- | --- | --- |\n" + "\n".join(table_rows)

    if detail_blocks:
        full_md = main_table + "\n\n##### Diagnostic Parameters & Measured Values\n" + "\n\n".join(detail_blocks)
    else:
        full_md = main_table

    st_ui.markdown(full_md)


def render_system_info_table(sys_info: Dict[str, Any], st_module: Any = None) -> None:
    """Render complete system information payload in clean, structured Markdown tables."""
    import streamlit as st_ctx
    st_ui = st_module or st_ctx

    if not isinstance(sys_info, dict) or not sys_info:
        st_ui.info("System information not available.")
        return

    os_data = sys_info.get("os", {}) if isinstance(sys_info.get("os"), dict) else {}
    comp_data = sys_info.get("computer", {}) if isinstance(sys_info.get("computer"), dict) else {}
    cpu_data = sys_info.get("cpu", {}) if isinstance(sys_info.get("cpu"), dict) else {}
    mem_data = sys_info.get("memory", {}) if isinstance(sys_info.get("memory"), dict) else {}
    disk_data = sys_info.get("disk", {}) if isinstance(sys_info.get("disk"), dict) else {}
    net_data = sys_info.get("network", {}) if isinstance(sys_info.get("network"), dict) else {}
    uptime_data = sys_info.get("uptime", {}) if isinstance(sys_info.get("uptime"), dict) else {}

    # 1. High-Level System Overview Table
    rows = []
    # OS
    os_name = os_data.get("os_name") or os_data.get("name") or "Windows"
    os_ver = os_data.get("os_version") or os_data.get("raw_version") or ""
    os_build = os_data.get("build_number", "")
    os_val = f"{os_name} {os_ver} (Build {os_build})" if os_build else f"{os_name} {os_ver}"
    rows.append(f"| Operating System | {os_val.strip()} | System | `Available` |")

    # Computer Name
    hostname = comp_data.get("hostname") or comp_data.get("computer_name") or "Local PC"
    username = comp_data.get("username", "")
    comp_val = f"{hostname} (User: {username})" if username else hostname
    rows.append(f"| Computer Name | {comp_val} | System | `Available` |")

    # CPU
    cpu_model = cpu_data.get("model") or cpu_data.get("brand") or "Windows Processor"
    cores = cpu_data.get("physical_cores", "")
    threads = cpu_data.get("logical_threads") or cpu_data.get("logical_cores", "")
    cpu_detail = f"{cpu_model} ({cores}C / {threads}T)" if cores and threads else cpu_model
    rows.append(f"| CPU Processor | {cpu_detail} | Performance | `Available` |")

    # Memory
    mem_total = mem_data.get("total_formatted") or format_bytes(mem_data.get("total_bytes", 0))
    mem_pct = mem_data.get("percent_used")
    mem_detail = f"{mem_total} Total ({mem_pct}% used)" if mem_pct is not None else f"{mem_total} Total"
    rows.append(f"| System Memory (RAM) | {mem_detail} | Performance | `Available` |")

    # Disk
    drives = disk_data.get("drives", [])
    drive_count = len(drives) if isinstance(drives, list) else 1
    rows.append(f"| Storage Drives | {drive_count} drive(s) detected and healthy | Storage | `Available` |")

    # Network
    adapters = net_data.get("adapters", [])
    adapter_count = len(adapters) if isinstance(adapters, list) else 1
    rows.append(f"| Network Adapters | {adapter_count} interface(s) monitored | Network | `Available` |")

    # Uptime
    uptime_str = uptime_data.get("uptime_formatted") or "Available"
    rows.append(f"| System Uptime | {uptime_str} | System | `Available` |")

    overview_table = "| Component | Specification | Domain | Status |\n| --- | --- | --- | --- |\n" + "\n".join(rows)
    md_blocks = [overview_table]

    # 2. Detailed Hardware & Environment Properties Table
    detail_rows = []
    if os_data:
        for k in ["name", "edition", "release", "display_version", "build_number", "raw_version", "architecture"]:
            if k in os_data and os_data[k] is not None:
                detail_rows.append(f"| OS {format_key_label(k)} | `{os_data[k]}` | Operating System |")
    if comp_data:
        for k in ["computer_name", "username", "system_root", "system_drive"]:
            if k in comp_data and comp_data[k] is not None:
                detail_rows.append(f"| Computer {format_key_label(k)} | `{comp_data[k]}` | Environment |")
    if cpu_data:
        for k in ["model", "architecture", "physical_cores", "logical_threads", "frequency_mhz"]:
            if k in cpu_data and cpu_data[k] is not None:
                detail_rows.append(f"| CPU {format_key_label(k)} | `{cpu_data[k]}` | Hardware |")
    if mem_data:
        for k in ["total_formatted", "available_formatted", "percent_used"]:
            if k in mem_data and mem_data[k] is not None:
                detail_rows.append(f"| Memory {format_key_label(k)} | `{mem_data[k]}` | Hardware |")

    if detail_rows:
        md_blocks.append(
            "##### Detailed Hardware & Environment Properties\n"
            + "| Property | Value | Category |\n| --- | --- | --- |\n"
            + "\n".join(detail_rows)
        )

    # 3. Storage Drives Table (if list of dicts)
    if isinstance(drives, list) and drives and isinstance(drives[0], dict):
        drive_rows = []
        for d in drives:
            dev = d.get("device") or d.get("mountpoint") or "Drive"
            fstype = d.get("fstype", "NTFS")
            tot = d.get("total_formatted") or format_bytes(d.get("total_bytes", 0))
            free = d.get("free_formatted") or format_bytes(d.get("free_bytes", 0))
            usage = f"{d.get('percent_used', 0.0)}%"
            drive_rows.append(f"| `{dev}` | {fstype} | {tot} | {free} | {usage} |")
        if drive_rows:
            md_blocks.append(
                "##### Storage Drives & Partitions\n"
                + "| Drive | File System | Total Capacity | Free Space | Usage |\n| --- | --- | --- | --- | --- |\n"
                + "\n".join(drive_rows)
            )

    # 4. Network Adapters Table (if list of dicts)
    if isinstance(adapters, list) and adapters and isinstance(adapters[0], dict):
        adapter_rows = []
        for a in adapters:
            name = a.get("name") or a.get("interface_name") or "Adapter"
            status = "Up / Connected" if a.get("is_up", True) else "Down"
            ips = a.get("ip_addresses", [])
            ip_str = ", ".join(ips) if isinstance(ips, list) and ips else (a.get("ipv4_address") or "N/A")
            speed = f"{a.get('speed_mbps')} Mbps" if a.get("speed_mbps") else "Auto"
            adapter_rows.append(f"| `{name}` | `{status}` | {ip_str} | {speed} |")
        if adapter_rows:
            md_blocks.append(
                "##### Network Interfaces & IP Configuration\n"
                + "| Interface Name | Status | IP Addresses | Speed |\n| --- | --- | --- | --- |\n"
                + "\n".join(adapter_rows)
            )

    full_md = "\n\n".join(md_blocks)
    st_ui.markdown(full_md)


def render_runtime_health_tables(ollama_status: Dict[str, Any], db_health: Dict[str, Any], st_module: Any = None) -> None:
    """Render runtime health (Ollama and SQLite) in a clean Markdown table."""
    import streamlit as st_ctx
    st_ui = st_module or st_ctx

    rows = []
    # Ollama
    if isinstance(ollama_status, dict):
        ollama_avail = ollama_status.get("available", False)
        ollama_model = ollama_status.get("model", "N/A")
        ollama_status_badge = "✓ Ready" if ollama_avail else "⚠ Degraded / Offline"
        rows.append(f"| Local AI (Ollama) | Model: `{ollama_model}` | `{ollama_status_badge}` |")

    # SQLite
    if isinstance(db_health, dict):
        db_conn = db_health.get("connected", False)
        tbl_cnt = db_health.get("tables_count", 0)
        db_badge = "✓ Connected" if db_conn else "✕ Disconnected"
        rows.append(f"| SQLite Database | Tables initialized: {tbl_cnt} | `{db_badge}` |")

    if rows:
        table_md = "| Subsystem | Details | Status |\n| --- | --- | --- |\n" + "\n".join(rows)
        st_ui.markdown(table_md)
    else:
        st_ui.info("Runtime status details not available.")



