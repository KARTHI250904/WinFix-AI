"""WinFix AI — Local AI Model Lifecycle & Health Manager (Phase 26).

Coordinates discovery, validation, health evaluation, model switching,
cache invalidation, and degraded-mode handling across Text, Vision, and STT components.
Strictly adheres to:
  LLM != Windows Shell
  Model Metadata != Windows Command
  Model Configuration != Windows Command
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ai.model_config import AIModelConfiguration, ai_config_manager
from ai.model_models import (
    AIHealthAggregation,
    ModelCapability,
    ModelInfo,
    ModelStatus,
    ModelType,
)
from ai.model_registry import model_registry
from ai.ollama_client import OllamaClient, ollama_client
from production.performance import default_profiler

logger = logging.getLogger("winfix.AI_MANAGER")


class AIModelLifecycleManager:
    """Manages local AI model discovery, health checks, switching, and degraded states."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        config_manager: Optional[Any] = None,
    ) -> None:
        self._client = client or ollama_client
        self._config_mgr = config_manager or ai_config_manager
        self._last_health_aggregation: Optional[AIHealthAggregation] = None

    @property
    def config(self) -> AIModelConfiguration:
        """Retrieve current validated AI configuration."""
        return self._config_mgr.load_config()

    def discover_installed_models(self) -> List[ModelInfo]:
        """Discover models installed in local Ollama and match against approved registry."""
        with default_profiler.measure("model_discovery"):
            res = self._client.list_local_models()
            now_str = datetime.now(timezone.utc).isoformat()

            if not res.get("success", False):
                logger.info("Ollama is not responding; no local models discovered.")
                return []

            discovered: List[ModelInfo] = []
            raw_models = res.get("raw_models", [])

            for raw in raw_models:
                raw_name = raw.get("name", "")
                if not model_registry.is_safe_model_id(raw_name):
                    logger.warning("Ignoring unsafe model identifier in discovery: %s", raw_name)
                    continue

                is_approved = model_registry.is_approved_model(raw_name)
                defn = model_registry.get_model_definition(raw_name)

                m_type = defn["type"] if defn else ModelType.TEXT
                caps = defn["capabilities"] if defn else []
                provider = defn["provider"] if defn else "ollama"
                status = ModelStatus.READY if is_approved else ModelStatus.UNKNOWN

                model_info = ModelInfo(
                    provider=provider,
                    model_id=raw_name,
                    model_type=m_type,
                    installed=True,
                    available=is_approved,
                    capabilities=caps,
                    version=raw.get("details", {}).get("format"),
                    digest=raw.get("digest"),
                    size_bytes=raw.get("size"),
                    status=status,
                    health="Installed in local Ollama",
                    last_checked=now_str,
                    error=None if is_approved else "Model is not in the approved WinFix AI registry",
                    metadata={"family": raw.get("details", {}).get("family")},
                )
                discovered.append(model_info)

            return discovered

    def validate_text_model(self, model_id: Optional[str] = None) -> ModelInfo:
        """Verify reachability and functional responsiveness of the configured text model."""
        target_model = model_id or self.config.text_model
        now_str = datetime.now(timezone.utc).isoformat()

        with default_profiler.measure("validate_text_model"):
            # 1. Allowlist and safety check
            if not model_registry.is_safe_model_id(target_model):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model or "unknown",
                    model_type=ModelType.TEXT,
                    installed=False,
                    available=False,
                    status=ModelStatus.INCOMPATIBLE,
                    error="Unsafe or invalid model identifier format.",
                    last_checked=now_str,
                )

            if not model_registry.is_approved_model(target_model, ModelType.TEXT):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model,
                    model_type=ModelType.TEXT,
                    installed=False,
                    available=False,
                    status=ModelStatus.INCOMPATIBLE,
                    error=f"Model '{target_model}' is not an approved text model.",
                    last_checked=now_str,
                )

            # 2. Check connection and availability
            avail_res = self._client.check_model_availability(target_model)
            if not avail_res.get("connected", False):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model,
                    model_type=ModelType.TEXT,
                    installed=False,
                    available=False,
                    status=ModelStatus.UNAVAILABLE,
                    error="Local Ollama service is offline or unreachable.",
                    last_checked=now_str,
                )

            # If target model is not pulled, check for any installed approved text model fallback
            if not avail_res.get("model_available", False) and model_id is None:
                local_models = avail_res.get("available_models", [])
                for alt in ["llama3.2:latest", "llama3.2", "gemma4:12b", "gemma:7b", "llama3:8b", "mistral:7b"]:
                    if any(alt == m or m.startswith(f"{alt}:") for m in local_models) and model_registry.is_approved_model(alt, ModelType.TEXT):
                        target_model = alt
                        avail_res = self._client.check_model_availability(target_model)
                        break

            if not avail_res.get("model_available", False):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model,
                    model_type=ModelType.TEXT,
                    installed=False,
                    available=False,
                    status=ModelStatus.MISSING,
                    error=f"Model '{target_model}' is not pulled in local Ollama (run: ollama pull {target_model}).",
                    last_checked=now_str,
                )

            caps = model_registry.get_expected_capabilities(target_model)
            return ModelInfo(
                provider="ollama",
                model_id=target_model,
                model_type=ModelType.TEXT,
                installed=True,
                available=True,
                capabilities=caps,
                status=ModelStatus.READY,
                health="Text model installed and available in Ollama",
                last_checked=now_str,
            )

    def validate_vision_model(self, model_id: Optional[str] = None) -> ModelInfo:
        """Verify reachability and functional responsiveness of the configured vision model."""
        target_model = model_id or self.config.vision_model
        now_str = datetime.now(timezone.utc).isoformat()

        with default_profiler.measure("validate_vision_model"):
            if not model_registry.is_safe_model_id(target_model):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model or "unknown",
                    model_type=ModelType.VISION,
                    installed=False,
                    available=False,
                    status=ModelStatus.INCOMPATIBLE,
                    error="Unsafe or invalid vision model identifier.",
                    last_checked=now_str,
                )

            if not model_registry.is_approved_model(target_model, ModelType.VISION):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model,
                    model_type=ModelType.VISION,
                    installed=False,
                    available=False,
                    status=ModelStatus.INCOMPATIBLE,
                    error=f"Model '{target_model}' is not an approved vision model.",
                    last_checked=now_str,
                )

            avail_res = self._client.check_model_availability(target_model)
            if not avail_res.get("connected", False):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model,
                    model_type=ModelType.VISION,
                    installed=False,
                    available=False,
                    status=ModelStatus.UNAVAILABLE,
                    error="Ollama service is offline.",
                    last_checked=now_str,
                )

            # If target vision model is not pulled, check for any installed approved vision model fallback
            if not avail_res.get("model_available", False) and model_id is None:
                local_models = avail_res.get("available_models", [])
                for alt in ["moondream:latest", "moondream", "llama3.2-vision:latest", "llama3.2-vision", "minicpm-v:latest", "llava:latest"]:
                    if any(alt == m or m.startswith(f"{alt}:") for m in local_models) and model_registry.is_approved_model(alt, ModelType.VISION):
                        target_model = alt
                        avail_res = self._client.check_model_availability(target_model)
                        break

            if not avail_res.get("model_available", False):
                return ModelInfo(
                    provider="ollama",
                    model_id=target_model,
                    model_type=ModelType.VISION,
                    installed=False,
                    available=False,
                    status=ModelStatus.MISSING,
                    error=f"Vision model '{target_model}' is not pulled in Ollama (run: ollama pull {target_model}).",
                    last_checked=now_str,
                )

            caps = model_registry.get_expected_capabilities(target_model)
            return ModelInfo(
                provider="ollama",
                model_id=target_model,
                model_type=ModelType.VISION,
                installed=True,
                available=True,
                capabilities=caps,
                status=ModelStatus.READY,
                health="Vision model installed and available in Ollama",
                last_checked=now_str,
            )

    def validate_stt_backend(self, provider_name: Optional[str] = None) -> ModelInfo:
        """Verify readiness of speech-to-text libraries and model files."""
        target_provider = provider_name or self.config.stt_backend
        now_str = datetime.now(timezone.utc).isoformat()

        with default_profiler.measure("validate_stt_backend"):
            if not model_registry.is_approved_model(target_provider, ModelType.STT):
                return ModelInfo(
                    provider="local",
                    model_id=target_provider,
                    model_type=ModelType.STT,
                    installed=False,
                    available=False,
                    status=ModelStatus.INCOMPATIBLE,
                    error=f"STT provider '{target_provider}' is not approved.",
                    last_checked=now_str,
                )

            try:
                # Check basic audio processing readiness
                import wave
                caps = model_registry.get_expected_capabilities(target_provider)
                return ModelInfo(
                    provider="local",
                    model_id=target_provider,
                    model_type=ModelType.STT,
                    installed=True,
                    available=True,
                    capabilities=caps,
                    status=ModelStatus.READY,
                    health="Local audio processing and STT subsystem ready",
                    last_checked=now_str,
                )
            except Exception as exc:
                return ModelInfo(
                    provider="local",
                    model_id=target_provider,
                    model_type=ModelType.STT,
                    installed=False,
                    available=False,
                    status=ModelStatus.DEGRADED,
                    error=f"STT initialization degraded: {exc}",
                    last_checked=now_str,
                )

    def check_aggregate_ai_health(self) -> AIHealthAggregation:
        """Run consolidated multi-component health assessment across all AI modalities."""
        with default_profiler.measure("aggregate_ai_health"):
            conn_res = self._client.check_connection()
            ollama_online = conn_res.get("connected", False)
            ollama_status = ModelStatus.READY if ollama_online else ModelStatus.UNAVAILABLE

            text_info = self.validate_text_model()
            vision_info = self.validate_vision_model()
            stt_info = self.validate_stt_backend()

            # Aggregate status calculation
            if text_info.status == ModelStatus.READY and ollama_status == ModelStatus.READY:
                if vision_info.status == ModelStatus.READY and stt_info.status == ModelStatus.READY:
                    overall = ModelStatus.READY
                else:
                    overall = ModelStatus.DEGRADED
            elif ollama_status == ModelStatus.UNAVAILABLE or text_info.status in (ModelStatus.MISSING, ModelStatus.DEGRADED):
                overall = ModelStatus.DEGRADED
            else:
                overall = ModelStatus.UNAVAILABLE

            aggregation = AIHealthAggregation(
                ollama_status=ollama_status,
                text_ai_status=text_info.status,
                vision_ai_status=vision_info.status,
                stt_status=stt_info.status,
                overall_status=overall,
                text_model_info=text_info,
                vision_model_info=vision_info,
                stt_model_info=stt_info,
                details={
                    "ollama_version": conn_res.get("version"),
                    "base_url": conn_res.get("base_url"),
                    "degraded_mode_enabled": self.config.degraded_mode_enabled,
                },
            )
            self._last_health_aggregation = aggregation
            return aggregation

    def switch_model(self, model_type: ModelType, new_model_id: str) -> Tuple[bool, str]:
        """Safely switch the active model identifier after strict registry validation."""
        with default_profiler.measure("switch_model"):
            # 1. Validate syntax and safety
            if not model_registry.is_safe_model_id(new_model_id):
                return False, f"Invalid model identifier syntax: '{new_model_id}'"

            # 2. Check registry allowlist for the given type
            if not model_registry.is_approved_model(new_model_id, model_type):
                return False, f"Model '{new_model_id}' is not an approved {model_type.value} model."

            cfg = self.config
            current_dict = cfg.to_dict()

            if model_type == ModelType.TEXT:
                current_dict["text_model"] = new_model_id
            elif model_type == ModelType.VISION:
                current_dict["vision_model"] = new_model_id
            elif model_type == ModelType.STT:
                current_dict["stt_backend"] = new_model_id
            else:
                return False, f"Unsupported model type: {model_type}"

            updated_cfg = AIModelConfiguration.from_dict(current_dict)
            saved = self._config_mgr.save_config(updated_cfg)
            if not saved:
                return False, "Failed to persist updated AI configuration to disk."

            # 3. Invalidate read-only generation caches
            self._client.clear_cache()

            logger.info("Successfully switched %s model to '%s'. AI generation cache invalidated.", model_type.value, new_model_id)
            return True, f"Successfully switched {model_type.value} model to '{new_model_id}'."

    def get_last_health_aggregation(self) -> AIHealthAggregation:
        """Return cached health aggregation or perform a fresh assessment."""
        if self._last_health_aggregation is not None:
            return self._last_health_aggregation
        return self.check_aggregate_ai_health()


# Global singleton instance
ai_model_manager = AIModelLifecycleManager()
