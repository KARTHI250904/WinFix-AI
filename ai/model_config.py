"""WinFix AI — AI Model Configuration Management (Phase 26).

Provides validated, centralized configuration for local AI models,
timeouts, caching flags, and degraded mode settings.
Strictly adheres to: Model Configuration != Windows Command.
"""

from dataclasses import asdict, dataclass, field
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ai.model_models import ModelType
from ai.model_registry import (
    DEFAULT_STT_ENGINE,
    DEFAULT_TEXT_MODEL,
    DEFAULT_VISION_MODEL,
    model_registry,
)
from production.paths import resolve_app_paths

logger = logging.getLogger("winfix.AI_CONFIG")


@dataclass
class AIModelConfiguration:
    """Validated configuration for local AI execution."""

    text_model: str = DEFAULT_TEXT_MODEL
    vision_model: str = DEFAULT_VISION_MODEL
    stt_backend: str = DEFAULT_STT_ENGINE
    health_check_timeout_seconds: float = 3.0
    generation_timeout_seconds: float = 30.0
    enable_ai_cache: bool = True
    degraded_mode_enabled: bool = True

    def validate(self) -> Dict[str, Any]:
        """Validate all configuration attributes against the model registry and safe bounds."""
        errors: Dict[str, str] = {}

        # 1. Text Model Validation
        if not model_registry.is_safe_model_id(self.text_model):
            errors["text_model"] = f"Invalid model identifier syntax: {self.text_model}"
        elif not model_registry.is_approved_model(self.text_model, ModelType.TEXT):
            errors["text_model"] = f"Model '{self.text_model}' is not an approved text model."

        # 2. Vision Model Validation
        if not model_registry.is_safe_model_id(self.vision_model):
            errors["vision_model"] = f"Invalid model identifier syntax: {self.vision_model}"
        elif not model_registry.is_approved_model(self.vision_model, ModelType.VISION):
            errors["vision_model"] = f"Model '{self.vision_model}' is not an approved vision model."

        # 3. STT Backend Validation
        if not model_registry.is_safe_model_id(self.stt_backend):
            errors["stt_backend"] = f"Invalid STT backend identifier: {self.stt_backend}"
        elif not model_registry.is_approved_model(self.stt_backend, ModelType.STT):
            errors["stt_backend"] = f"STT backend '{self.stt_backend}' is not approved."

        # 4. Numeric Bounds Validation
        if self.health_check_timeout_seconds <= 0.0 or self.health_check_timeout_seconds > 60.0:
            errors["health_check_timeout_seconds"] = "Timeout must be between 0.1 and 60.0 seconds."

        if self.generation_timeout_seconds <= 0.0 or self.generation_timeout_seconds > 300.0:
            errors["generation_timeout_seconds"] = "Generation timeout must be between 1.0 and 300.0 seconds."

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIModelConfiguration":
        """Instantiate configuration from dictionary with fail-closed default fallback."""
        if not isinstance(data, dict):
            logger.warning("Invalid configuration data type, falling back to defaults.")
            return cls()

        instance = cls(
            text_model=str(data.get("text_model", DEFAULT_TEXT_MODEL)),
            vision_model=str(data.get("vision_model", DEFAULT_VISION_MODEL)),
            stt_backend=str(data.get("stt_backend", DEFAULT_STT_ENGINE)),
            health_check_timeout_seconds=float(data.get("health_check_timeout_seconds", 3.0)),
            generation_timeout_seconds=float(data.get("generation_timeout_seconds", 30.0)),
            enable_ai_cache=bool(data.get("enable_ai_cache", True)),
            degraded_mode_enabled=bool(data.get("degraded_mode_enabled", True)),
        )

        validation = instance.validate()
        if not validation["valid"]:
            logger.warning("Loaded configuration failed validation: %s. Reverting invalid fields.", validation["errors"])
            # Reset invalid fields to defaults
            if "text_model" in validation["errors"]:
                instance.text_model = DEFAULT_TEXT_MODEL
            if "vision_model" in validation["errors"]:
                instance.vision_model = DEFAULT_VISION_MODEL
            if "stt_backend" in validation["errors"]:
                instance.stt_backend = DEFAULT_STT_ENGINE
            if "health_check_timeout_seconds" in validation["errors"]:
                instance.health_check_timeout_seconds = 3.0
            if "generation_timeout_seconds" in validation["errors"]:
                instance.generation_timeout_seconds = 30.0

        return instance


class AIConfigurationManager:
    """Manages persistence and retrieval of local AI model settings."""

    def __init__(self, config_file: Optional[Path] = None) -> None:
        if config_file:
            self.config_path = config_file
        else:
            paths = resolve_app_paths()
            self.config_path = paths.config_dir / "ai_models.json"

        self._cached_config: Optional[AIModelConfiguration] = None

    def load_config(self) -> AIModelConfiguration:
        """Load and validate AI configuration from disk or return default."""
        if self._cached_config is not None:
            return self._cached_config

        if not self.config_path.exists():
            self._cached_config = AIModelConfiguration()
            return self._cached_config

        try:
            content = self.config_path.read_text(encoding="utf-8")
            data = json.loads(content)
            self._cached_config = AIModelConfiguration.from_dict(data)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s. Using default AI configuration.", self.config_path, exc)
            self._cached_config = AIModelConfiguration()

        return self._cached_config

    def save_config(self, config: AIModelConfiguration) -> bool:
        """Save validated AI configuration to disk safely."""
        validation = config.validate()
        if not validation["valid"]:
            logger.error("Refusing to save invalid AI configuration: %s", validation["errors"])
            return False

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps(config.to_dict(), indent=2),
                encoding="utf-8",
            )
            self._cached_config = config
            return True
        except Exception as exc:
            logger.error("Failed to write AI configuration to %s: %s", self.config_path, exc)
            return False

    def reset_to_defaults(self) -> AIModelConfiguration:
        """Reset configuration to standard default values."""
        cfg = AIModelConfiguration()
        self.save_config(cfg)
        return cfg


# Global singleton instance
ai_config_manager = AIConfigurationManager()
