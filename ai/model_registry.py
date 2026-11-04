"""WinFix AI — Controlled AI Model Registry (Phase 26).

Provides an immutable allowlist of approved AI models and components,
capability bindings, and strict validation.
Strictly adheres to: Model Name != Windows Command and LLM != Windows Shell.
"""

import re
from typing import Any, Dict, List, Optional, Set

from ai.model_models import ModelCapability, ModelInfo, ModelStatus, ModelType

# Safe model name pattern: alphanumeric, :, ., -, _ (no slashes, traversal, or shell characters)
_SAFE_MODEL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\:]+$")

# Approved Model Definitions
_APPROVED_MODELS: Dict[str, Dict[str, Any]] = {
    # Text Models
    "gemma4:12b": {
        "type": ModelType.TEXT,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT],
        "is_default": True,
        "description": "Primary offline troubleshooting reasoning model.",
    },
    "llama3.2:latest": {
        "type": ModelType.TEXT,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT],
        "is_default": False,
        "description": "Fast, high-efficiency local troubleshooting reasoning model.",
    },
    "llama3.2": {
        "type": ModelType.TEXT,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT],
        "is_default": False,
        "description": "Fast, high-efficiency local troubleshooting reasoning model.",
    },
    "gemma:7b": {
        "type": ModelType.TEXT,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT],
        "is_default": False,
        "description": "Lightweight fallback text generation model.",
    },
    "gemma:2b": {
        "type": ModelType.TEXT,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT],
        "is_default": False,
        "description": "Ultra-lightweight text generation model.",
    },
    "llama3:8b": {
        "type": ModelType.TEXT,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT],
        "is_default": False,
        "description": "Alternative general troubleshooting model.",
    },
    "mistral:7b": {
        "type": ModelType.TEXT,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.STRUCTURED_OUTPUT],
        "is_default": False,
        "description": "Alternative fast reasoning model.",
    },

    # Vision Models
    "moondream:latest": {
        "type": ModelType.VISION,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.VISION],
        "is_default": True,
        "description": "Fast, lightweight visual error and screenshot inspection model.",
    },
    "moondream": {
        "type": ModelType.VISION,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.VISION],
        "is_default": False,
        "description": "Fast, lightweight visual error and screenshot inspection model.",
    },
    "minicpm-v:latest": {
        "type": ModelType.VISION,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.VISION],
        "is_default": False,
        "description": "Visual error and screenshot inspection model.",
    },
    "llama3.2-vision:latest": {
        "type": ModelType.VISION,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.VISION],
        "is_default": False,
        "description": "Advanced multimodal vision-language model.",
    },
    "llama3.2-vision": {
        "type": ModelType.VISION,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.VISION],
        "is_default": False,
        "description": "Advanced multimodal vision-language model.",
    },
    "llava:latest": {
        "type": ModelType.VISION,
        "provider": "ollama",
        "capabilities": [ModelCapability.TEXT_GENERATION, ModelCapability.VISION],
        "is_default": False,
        "description": "Alternative vision-language model.",
    },

    # STT Engines
    "whisper_cpp": {
        "type": ModelType.STT,
        "provider": "local",
        "capabilities": [ModelCapability.SPEECH_TO_TEXT],
        "is_default": True,
        "description": "Offline local speech-to-text engine.",
    },
    "faster-whisper": {
        "type": ModelType.STT,
        "provider": "local",
        "capabilities": [ModelCapability.SPEECH_TO_TEXT],
        "is_default": False,
        "description": "Alternative local transformer-based STT engine.",
    },
}

DEFAULT_TEXT_MODEL = "gemma4:12b"
DEFAULT_VISION_MODEL = "moondream:latest"
DEFAULT_STT_ENGINE = "whisper_cpp"


class ModelRegistry:
    """Controlled registry managing approved AI model definitions and capabilities."""

    def __init__(self) -> None:
        self._registry = dict(_APPROVED_MODELS)

    @staticmethod
    def is_safe_model_id(model_id: str) -> bool:
        """Validate that model_id contains only safe characters and no command injection symbols."""
        if not model_id or not isinstance(model_id, str):
            return False
        if len(model_id) > 128:
            return False
        if ".." in model_id or "/" in model_id or "\\" in model_id:
            return False
        return bool(_SAFE_MODEL_NAME_PATTERN.match(model_id))

    def is_approved_model(self, model_id: str, model_type: Optional[ModelType] = None) -> bool:
        """Check whether a model ID is in the approved registry."""
        if not self.is_safe_model_id(model_id):
            return False

        matched_key = None
        if model_id in self._registry:
            matched_key = model_id
        elif f"{model_id}:latest" in self._registry:
            matched_key = f"{model_id}:latest"
        elif ":" not in model_id:
            candidates = [k for k in self._registry if k.startswith(f"{model_id}:")]
            if len(candidates) == 1:
                matched_key = candidates[0]

        if matched_key is None:
            return False

        if model_type is not None:
            return self._registry[matched_key]["type"] == model_type
        return True

    def get_model_definition(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve static definition for an approved model."""
        if not self.is_safe_model_id(model_id):
            return None
        if model_id in self._registry:
            return dict(self._registry[model_id])
        if f"{model_id}:latest" in self._registry:
            return dict(self._registry[f"{model_id}:latest"])
        if ":" not in model_id:
            candidates = [k for k in self._registry if k.startswith(f"{model_id}:")]
            if len(candidates) == 1:
                return dict(self._registry[candidates[0]])
        return None


    def get_approved_models(self, model_type: Optional[ModelType] = None) -> List[str]:
        """Return list of all approved model identifiers, optionally filtered by type."""
        if model_type is None:
            return list(self._registry.keys())
        return [k for k, v in self._registry.items() if v["type"] == model_type]

    def get_expected_capabilities(self, model_id: str) -> List[ModelCapability]:
        """Retrieve expected capabilities for a model ID. Returns empty list if unapproved."""
        defn = self.get_model_definition(model_id)
        if defn:
            return list(defn.get("capabilities", []))
        return []

    def get_default_model(self, model_type: ModelType) -> str:
        """Retrieve default approved model identifier for a given modality."""
        if model_type == ModelType.TEXT:
            return DEFAULT_TEXT_MODEL
        if model_type == ModelType.VISION:
            return DEFAULT_VISION_MODEL
        if model_type == ModelType.STT:
            return DEFAULT_STT_ENGINE
        return DEFAULT_TEXT_MODEL


# Global registry singleton
model_registry = ModelRegistry()
