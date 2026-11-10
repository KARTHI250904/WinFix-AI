"""
WinFix AI — Production Logging System (Phase 22).

Provides centralized, category-specific logging with automatic privacy sanitization.
Strictly prevents logging passwords, tokens, API keys, user document paths, or raw media bytes.
"""

from enum import Enum
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import threading
from typing import Any, Dict, Optional

from production.config import ProductionConfig, prod_config

# Patterns for sensitive data matching
USER_PATH_PATTERN = re.compile(r"([a-zA-Z]:[/\\\\]Users[/\\\\])[^/\\\\]+([/\\\\].*)?", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
API_KEY_PATTERN = re.compile(r"\b(?:api_key|token|password|secret|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}['\"]?", re.IGNORECASE)

_logging_lock = threading.Lock()


def sanitize_log_text(text: Optional[str]) -> str:
    """Sanitize sensitive personal identifiers, tokens, and user paths from a log string."""
    if not text or not isinstance(text, str):
        return ""

    sanitized = text
    # 1. Mask User Profiles in Windows paths
    sanitized = USER_PATH_PATTERN.sub(r"\1<User>\2", sanitized)
    # 2. Mask Email addresses
    sanitized = EMAIL_PATTERN.sub("<email-masked>", sanitized)
    # 3. Mask Key/Token patterns
    sanitized = API_KEY_PATTERN.sub("<credential-masked>", sanitized)
    return sanitized


class LogCategory(str, Enum):
    """Categorized log channels across the WinFix AI system."""

    STARTUP = "STARTUP"
    CONFIG = "CONFIG"
    DATABASE = "DATABASE"
    AI = "AI"
    VISION = "VISION"
    VOICE = "VOICE"
    DIAGNOSTICS = "DIAGNOSTICS"
    REPAIR = "REPAIR"
    VERIFICATION = "VERIFICATION"
    SECURITY = "SECURITY"
    AUTOPILOT = "AUTOPILOT"
    UI = "UI"
    SHUTDOWN = "SHUTDOWN"


class SanitizingFormatter(logging.Formatter):
    """Custom logging formatter that strips sensitive credentials and user paths."""

    def format(self, record: logging.LogRecord) -> str:
        original_msg = super().format(record)
        return sanitize_log_text(original_msg)


def setup_production_logging(
    config: Optional[ProductionConfig] = None,
    log_file_name: str = "winfix.log",
    max_bytes: int = 5 * 1024 * 1024,  # 5MB
    backup_count: int = 3,
) -> logging.Logger:
    """Initialize rotating file and console logging with automatic sanitization.

    Idempotent and thread-safe: upgrades existing un-sanitized handlers without duplicating
    managed handlers across repeated Streamlit script reruns.
    """
    cfg = config or prod_config
    logs_dir = cfg.paths.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / log_file_name

    root_logger = logging.getLogger("winfix")
    root_logger.setLevel(logging.DEBUG if cfg.debug_mode else logging.INFO)

    default_fmt_str = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    default_datefmt = "%Y-%m-%d %H:%M:%S"

    with _logging_lock:
        # 1. Upgrade any existing pre-configured handlers to use SanitizingFormatter
        for h in list(root_logger.handlers) + list(logging.getLogger().handlers):
            if not isinstance(h.formatter, SanitizingFormatter):
                orig_fmt = getattr(h.formatter, "_fmt", default_fmt_str) if h.formatter else default_fmt_str
                orig_datefmt = getattr(h.formatter, "datefmt", default_datefmt) if h.formatter else default_datefmt
                h.setFormatter(SanitizingFormatter(orig_fmt, datefmt=orig_datefmt))

        # 2. Check if WinFix-managed file and console handlers already exist
        has_managed_file = any(
            isinstance(h, RotatingFileHandler) and getattr(h, "_winfix_managed", False)
            for h in root_logger.handlers
        )
        has_managed_console = any(
            isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
            and getattr(h, "_winfix_managed", False)
            for h in root_logger.handlers
        )

        formatter = SanitizingFormatter(default_fmt_str, datefmt=default_datefmt)

        # 3. Add managed RotatingFileHandler if not present
        if not has_managed_file:
            file_handler = RotatingFileHandler(
                filename=str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG if cfg.debug_mode else logging.INFO)
            setattr(file_handler, "_winfix_managed", True)
            root_logger.addHandler(file_handler)

        # 4. Add managed StreamHandler (Console) if not present
        if not has_managed_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.DEBUG if cfg.debug_mode else logging.INFO)
            setattr(console_handler, "_winfix_managed", True)
            root_logger.addHandler(console_handler)

    return root_logger


def get_category_logger(category: LogCategory) -> logging.Logger:
    """Retrieve a child logger bound to a specific operational category."""
    return logging.getLogger(f"winfix.{category.value}")


get_logger = get_category_logger
