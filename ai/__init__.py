"""AI module for WinFix AI (Ollama client, prompts, transcriber, vision, lifecycle management)."""

from ai.model_config import AIConfigurationManager, AIModelConfiguration, ai_config_manager
from ai.model_manager import AIModelLifecycleManager, ai_model_manager
from ai.model_models import (
    AIHealthAggregation,
    ModelCapability,
    ModelInfo,
    ModelStatus,
    ModelType,
)
from ai.model_registry import ModelRegistry, model_registry
from ai.ollama_client import OllamaClient, ollama_client
from ai.screenshot_analyzer import ScreenshotAnalyzer, default_screenshot_analyzer
from ai.screenshot_prompt import (
    SCREENSHOT_VISION_SYSTEM_INSTRUCTION,
    build_screenshot_prompt,
)
from ai.voice_prompt import VOICE_SYSTEM_INSTRUCTION, build_voice_prompt
from ai.voice_transcriber import (
    FasterWhisperProvider,
    MockLocalSTTProvider,
    SpeechToTextProvider,
    VoiceTranscriber,
    default_voice_transcriber,
    is_valid_transcript,
)

__all__ = [
    "OllamaClient",
    "ollama_client",
    "ScreenshotAnalyzer",
    "default_screenshot_analyzer",
    "SCREENSHOT_VISION_SYSTEM_INSTRUCTION",
    "build_screenshot_prompt",
    "VOICE_SYSTEM_INSTRUCTION",
    "build_voice_prompt",
    "SpeechToTextProvider",
    "FasterWhisperProvider",
    "MockLocalSTTProvider",
    "VoiceTranscriber",
    "default_voice_transcriber",
    "is_valid_transcript",
    "ModelType",
    "ModelStatus",
    "ModelCapability",
    "ModelInfo",
    "AIHealthAggregation",
    "ModelRegistry",
    "model_registry",
    "AIModelConfiguration",
    "AIConfigurationManager",
    "ai_config_manager",
    "AIModelLifecycleManager",
    "ai_model_manager",
]
