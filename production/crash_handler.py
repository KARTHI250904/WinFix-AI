"""
WinFix AI — Production Crash & Exception Boundary (Phase 22).

Intercepts unhandled exceptions at application boundaries, logs them safely without
sensitive data leakage, and provides structured, friendly error presentations.
Never triggers automatic repairs after a crash.
"""

from dataclasses import dataclass, field
import functools
import logging
import sys
import time
import traceback
from typing import Any, Callable, Dict, Optional, Tuple, Union

from production.logging import LogCategory, get_category_logger

logger = get_category_logger(LogCategory.UI)


@dataclass(frozen=True)
class SafeCrashSummary:
    """Safe, user-facing summary of an unexpected failure without internal trace leakage."""

    title: str = "WinFix AI Encountered an Unexpected Issue"
    friendly_message: str = (
        "An unexpected error occurred during processing. Your local data and system settings remain safe."
    )
    error_type: str = "GeneralApplicationError"
    actionable_guidance: str = (
        "Please retry the operation. If the issue persists, review the diagnostic logs in your application data directory."
    )
    context: str = "operation"
    user_message: str = (
        "WinFix AI encountered an unexpected error. Your data has not been deleted. "
        "Please review the application log for diagnostic information."
    )
    timestamp: float = field(default_factory=time.time)
    is_crashed: bool = True


def safe_exception_boundary(
    func: Optional[Callable[..., Any]] = None,
    *,
    context: str = "operation",
    fallback_value: Any = None,
) -> Any:
    """
    Execute or decorate a function inside a production exception boundary.

    Can be used as:
    1. Decorator:
       @safe_exception_boundary(context="worker")
       def my_func(): ...

    2. Function executor:
       success, res, crash = safe_exception_boundary(my_func, arg1, context="worker")
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Tuple[bool, Any, Optional[SafeCrashSummary]]]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Tuple[bool, Any, Optional[SafeCrashSummary]]:
            try:
                result = fn(*args, **kwargs)
                return True, result, None
            except Exception as ex:
                err_type = type(ex).__name__
                logger.error(
                    "Controlled exception boundary caught an error in %s (%s): %s",
                    context,
                    err_type,
                    str(ex),
                )
                summary = SafeCrashSummary(
                    title=f"Issue in {context.capitalize()}",
                    friendly_message=f"WinFix AI encountered an unexpected condition while running {context}.",
                    error_type=err_type,
                    context=context,
                    user_message=f"WinFix AI encountered an unexpected error during {context}.",
                    actionable_guidance="Please try the operation again or select another troubleshooting tool.",
                    is_crashed=True,
                )
                return False, fallback_value, summary
        return wrapper

    if func is not None and callable(func):
        return decorator(func)
    return decorator
