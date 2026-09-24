"""Central configuration management for WinFix AI.

Provides strongly-typed, environment-aware configuration settings for
Ollama connection, model identifiers, database paths, and logging.
"""

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path


# Project Root Directory
BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class AppConfig:
    """Application configuration container."""

    # Project metadata
    app_name: str = "WinFix AI"
    app_version: str = "0.1.0"
    app_tagline: str = "Your Offline Windows Assistant"

    # Ollama runtime settings
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    default_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:12b")
    )
    ollama_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "10"))
    )

    # Database settings
    database_path: Path = field(
        default_factory=lambda: BASE_DIR / os.getenv("SQLITE_DB_NAME", "winfix.db")
    )
    schema_path: Path = field(
        default_factory=lambda: BASE_DIR / "database" / "schema.sql"
    )

    # Logging settings
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


# Default global configuration instance
config = AppConfig()


def setup_logging(cfg: AppConfig = config) -> None:
    """Configure standard logging for the application."""
    level = getattr(logging, cfg.log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format=cfg.log_format,
        force=True,
    )
