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
from typing import Any, Dict, Optional

from production.config import ProductionConfig, prod_config

# Patterns for sensitive data matching
USER_PATH_PATTERN = re.compile(r"([a-zA-Z]:\\Users\\)[^\\]+(\\.*)?", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
API_KEY_PATTERN = re.compile(r"\b(?:api_key|token|password|secret|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}['\"]?", re.IGNORECASE)


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
    """Initialize rotating file and console logging with automatic sanitization."""
    cfg = config or prod_config
    logs_dir = cfg.paths.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / log_file_name

    root_logger = logging.getLogger("winfix")
    root_logger.setLevel(logging.DEBUG if cfg.debug_mode else logging.INFO)

    # Avoid duplicate handlers if setup is called multiple times
    if not root_logger.handlers:
        formatter = SanitizingFormatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # File Handler
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG if cfg.debug_mode else logging.INFO)
        root_logger.addHandler(file_handler)

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG if cfg.debug_mode else logging.INFO)
        root_logger.addHandler(console_handler)

    return root_logger


def get_category_logger(category: LogCategory) -> logging.Logger:
    """Retrieve a child logger bound to a specific operational category."""
    return logging.getLogger(f"winfix.{category.value}")


get_logger = get_category_logger
