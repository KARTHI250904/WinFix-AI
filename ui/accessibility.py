"""Accessibility helpers for WinFix AI UI (Phases 20 & 35).

Ensures all states, alerts, headings, tables, and interactive controls provide
explicit textual indicators, high-contrast badges, non-color-only state cues,
and descriptive, screen-reader friendly labels.
"""

from typing import Any, Dict, List, Optional


def accessible_button_label(icon: str, action_text: str, context_hint: Optional[str] = None) -> str:
    """Generate accessible button label pairing an icon with an explicit descriptive action verb."""
    base = action_text.strip()
    if icon:
        base = f"{icon} {base}"
    if context_hint:
        base = f"{base} ({context_hint.strip()})"
    return base


def accessible_status_indicator(status_type: str, message: str) -> str:
    """Generate textual status prefix to ensure status is never conveyed by color alone."""
    st = status_type.upper().strip()
    prefix_map = {
        "SUCCESS": "[SUCCESS] ✓",
        "VERIFIED": "[VERIFIED] ✓",
        "PARTIAL_SUCCESS": "[PARTIALLY RESOLVED] ⚠️",
        "WARNING": "[WARNING] ⚠️",
        "CAUTION": "[CAUTION] ⚠️",
        "ERROR": "[ERROR] ✕",
        "FAILED": "[FAILED] ✕",
        "UNRESOLVED": "[UNRESOLVED] ⚠️",
        "NOT_VERIFIED": "[NOT VERIFIED] ⚠️",
        "TIMEOUT": "[TIMEOUT] ⚠️",
        "BLOCKED": "[BLOCKED] 🚫",
        "INFO": "[INFO] ℹ️",
        "RUNNING": "[RUNNING] ⏳",
        "LOADING": "[LOADING] ⏳",
        "ANALYZING": "[ANALYZING] 🔍",
        "EXECUTING": "[EXECUTING] ⚙️",
        "VERIFYING": "[VERIFYING] 🔍",
        "RECOVERING": "[RECOVERING] 🔄",
        "OFFLINE": "[OFFLINE] 🔌",
        "CANCELLED": "[CANCELLED] ✕",
        "IDLE": "[READY] ●",
        "WAITING_FOR_CONFIRMATION": "[CONFIRMATION REQUIRED] ⚠️",
    }
    prefix = prefix_map.get(st, f"[{st}] ●")
    return f"{prefix} {message}"


def format_accessible_table(headers: List[str], rows: List[List[str]]) -> str:
    """Format tabular data with standard markdown and clear column alignment."""
    if not headers or not rows:
        return ""
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    row_lines = ["| " + " | ".join(str(cell) for cell in r) + " |" for r in rows]
    return "\n".join([header_line, sep_line, *row_lines])


def format_accessible_diff(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    """Format before-and-after state changes as an accessible textual comparison table."""
    all_keys = sorted(set(list(before.keys()) + list(after.keys())))
    if not all_keys:
        return "No measurable state properties to compare."
    headers = ["Component / Property", "Before Repair", "After Repair", "Status Change"]
    rows = []
    for k in all_keys:
        b_val = str(before.get(k, "Not Recorded"))
        a_val = str(after.get(k, "Not Recorded"))
        change = "Unchanged" if b_val == a_val else "Changed"
        rows.append([k, b_val, a_val, change])
    return format_accessible_table(headers, rows)


def format_accessible_bullet_list(items: List[str], prefix: str = "•") -> str:
    """Format a list of strings with consistent accessible bullets."""
    if not items:
        return "None recorded."
    return "\n".join([f"{prefix} {item.strip()}" for item in items if item.strip()])
