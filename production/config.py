"""
WinFix AI — Production Configuration (Phase 22).

Provides strongly-typed, environment-aware production configuration settings
with debug disabled by default, centralized model identifiers, and path resolution.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, Optional

from production.paths import AppPaths, resolve_app_paths
from production.version import APP_NAME, APP_VERSION, BUILD_VERSION, RELEASE_CHANNEL


@dataclass(frozen=True)
class ProductionConfig:
    """Production configuration container for WinFix AI."""

    # Application Metadata
    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    environment: str = field(
        default_factory=lambda: os.getenv("WINFIX_ENV", "production").lower()
    )
    debug_mode: bool = field(
        default_factory=lambda: os.getenv("WINFIX_DEBUG", "false").lower() in ("true", "1", "yes")
    )

    # Runtime Paths
    paths: AppPaths = field(default_factory=resolve_app_paths)

    # Ollama Local AI Inference
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:12b")
    )
    ollama_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120.0"))
    )

    # Vision Analysis
    vision_model: str = field(
        default_factory=lambda: os.getenv("WINFIX_VISION_MODEL", "moondream:latest")
    )
    vision_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("WINFIX_VISION_TIMEOUT_SECONDS", "60.0"))
    )
    vision_enabled: bool = True

    # Voice / STT Processing
    stt_provider: str = field(
        default_factory=lambda: os.getenv("WINFIX_STT_PROVIDER", "whisper_cpp")
    )
    stt_model: str = field(
        default_factory=lambda: os.getenv("WINFIX_STT_MODEL", "tiny.en")
    )
    voice_enabled: bool = True

    # Database Settings
    sqlite_busy_timeout_ms: int = 5000
    sqlite_wal_mode: bool = True

    # Logging Settings
    log_level: str = field(
        default_factory=lambda: "DEBUG" if os.getenv("WINFIX_DEBUG", "false").lower() in ("true", "1", "yes") else "INFO"
    )
    log_max_bytes: int = 10 * 1024 * 1024  # 10 MB per rotating log file
    log_backup_count: int = 5

    # Safe Bounds
    max_tool_execution_timeout_seconds: int = 60
    max_autopilot_steps: int = 10
    max_knowledge_search_results: int = 5


def get_production_config() -> ProductionConfig:
    """Instantiate and return the standard production configuration."""
    return ProductionConfig()


# Singleton instance
prod_config = get_production_config()
