"""WinFix AI — Phase 26 AI Model Management & Lifecycle Unit Tests.

Validates model discovery, registry allowlists, capability detection,
configuration validation, health evaluation, switching, and cache safety.
"""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from ai.model_config import AIConfigurationManager, AIModelConfiguration
from ai.model_manager import AIModelLifecycleManager
from ai.model_models import (
    AIHealthAggregation,
    ModelCapability,
    ModelInfo,
    ModelStatus,
    ModelType,
)
from ai.model_registry import ModelRegistry, model_registry
from ai.ollama_client import OllamaClient
from production.health_check import ComponentStatus, HealthCheckEngine
from production.performance import default_profiler


class TestAIModelManagement:
    """Test suite for Phase 26 AI Model Management."""

    def test_model_registry_allowlist_and_safety(self) -> None:
        """Verify approved model allowlist and rejection of unapproved models."""
        registry = ModelRegistry()

        # Approved models
        assert registry.is_approved_model("gemma4:12b", ModelType.TEXT) is True
        assert registry.is_approved_model("gemma:7b", ModelType.TEXT) is True
        assert registry.is_approved_model("gemma:2b", ModelType.TEXT) is True
        assert registry.is_approved_model("llama3:8b", ModelType.TEXT) is True
        assert registry.is_approved_model("mistral:7b", ModelType.TEXT) is True
        assert registry.is_approved_model("minicpm-v:latest", ModelType.VISION) is True
        assert registry.is_approved_model("whisper_cpp", ModelType.STT) is True
        assert registry.is_approved_model("faster-whisper", ModelType.STT) is True

        # Unapproved models
        assert registry.is_approved_model("unapproved_model:latest") is False
        assert registry.is_approved_model("gpt-4-turbo") is False
        assert registry.is_approved_model("claude-3-opus") is False

        # Wrong type check
        assert registry.is_approved_model("gemma4:12b", ModelType.VISION) is False
        assert registry.is_approved_model("minicpm-v:latest", ModelType.TEXT) is False

    def test_model_id_security_injection_rejection(self) -> None:
        """Verify that model IDs containing shell symbols or traversal are rejected."""
        registry = ModelRegistry()

        malicious_ids = [
            "../../malicious_model",
            "..\\..\\windows\\system32",
            "gemma4:12b && calc.exe",
            "gemma4:12b; rm -rf /",
            "gemma4:12b | whoami",
            "$(whoami)",
            "`whoami`",
            "model\nname",
            "model\r\nname",
            "model with spaces",
            "gemma4:12b>output.txt",
            "<script>alert(1)</script>",
            "",
            "a" * 200,  # Exceeds max length
        ]

        for m_id in malicious_ids:
            assert registry.is_safe_model_id(m_id) is False
            assert registry.is_approved_model(m_id) is False

    def test_model_capabilities_mapping(self) -> None:
        """Verify model capabilities are accurately retrieved from registry."""
        registry = ModelRegistry()

        gemma_caps = registry.get_expected_capabilities("gemma4:12b")
        assert ModelCapability.TEXT_GENERATION in gemma_caps
        assert ModelCapability.STRUCTURED_OUTPUT in gemma_caps

        vision_caps = registry.get_expected_capabilities("minicpm-v:latest")
        assert ModelCapability.VISION in vision_caps
        assert ModelCapability.TEXT_GENERATION in vision_caps

        stt_caps = registry.get_expected_capabilities("whisper_cpp")
        assert ModelCapability.SPEECH_TO_TEXT in stt_caps

        unknown_caps = registry.get_expected_capabilities("nonexistent:model")
        assert unknown_caps == []

    def test_model_configuration_validation_and_persistence(self) -> None:
        """Test configuration loading, validation, saving, and bound checks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "ai_models.json"
            mgr = AIConfigurationManager(config_file=cfg_file)

            # Default configuration
            cfg = mgr.load_config()
            assert cfg.text_model == "gemma4:12b"
            assert cfg.vision_model in ["minicpm-v:latest", "moondream:latest"]
            assert cfg.stt_backend == "whisper_cpp"
            assert cfg.validate()["valid"] is True

            # Modify and save valid configuration
            cfg.text_model = "gemma:7b"
            cfg.health_check_timeout_seconds = 5.0
            assert mgr.save_config(cfg) is True

            # Reload from disk
            mgr_new = AIConfigurationManager(config_file=cfg_file)
            reloaded = mgr_new.load_config()
            assert reloaded.text_model == "gemma:7b"
            assert reloaded.health_check_timeout_seconds == 5.0

    def test_model_configuration_rejects_invalid_values(self) -> None:
        """Test that invalid configuration parameters fail validation."""
        cfg = AIModelConfiguration(
            text_model="unapproved_model",
            vision_model="invalid_vision",
            stt_backend="invalid_stt",
            health_check_timeout_seconds=-1.0,
            generation_timeout_seconds=500.0,
        )
        res = cfg.validate()
        assert res["valid"] is False
        assert "text_model" in res["errors"]
        assert "vision_model" in res["errors"]
        assert "stt_backend" in res["errors"]
        assert "health_check_timeout_seconds" in res["errors"]
        assert "generation_timeout_seconds" in res["errors"]

    def test_model_configuration_fail_closed_on_corrupt_file(self) -> None:
        """Test fail-closed behavior when configuration file on disk is corrupt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "ai_models.json"
            cfg_file.write_text("{corrupted_json: true", encoding="utf-8")

            mgr = AIConfigurationManager(config_file=cfg_file)
            cfg = mgr.load_config()
            # Should revert safely to defaults
            assert cfg.text_model == "gemma4:12b"
            assert cfg.vision_model in ["minicpm-v:latest", "moondream:latest"]

    def test_model_discovery_with_ollama_mock(self) -> None:
        """Test discovery of installed models and classification of supported vs unknown models."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.list_local_models.return_value = {
            "success": True,
            "raw_models": [
                {"name": "gemma4:12b", "size": 8000000000, "details": {"format": "gguf", "family": "gemma"}},
                {"name": "minicpm-v:latest", "size": 5000000000, "details": {"format": "gguf"}},
                {"name": "custom_experimental_model:v1", "size": 1000000000, "details": {}},
            ],
            "error": None,
        }

        mgr = AIModelLifecycleManager(client=mock_client)
        discovered = mgr.discover_installed_models()

        assert len(discovered) == 3
        gemma = next(m for m in discovered if m.model_id == "gemma4:12b")
        assert gemma.status == ModelStatus.READY
        assert gemma.available is True
        assert ModelCapability.TEXT_GENERATION in gemma.capabilities

        custom = next(m for m in discovered if m.model_id == "custom_experimental_model:v1")
        assert custom.status == ModelStatus.UNKNOWN
        assert custom.available is False

    def test_text_model_validation_flow(self) -> None:
        """Test text model validation in ready, missing, and offline scenarios."""
        mock_client = MagicMock(spec=OllamaClient)

        # 1. Ready scenario
        mock_client.check_model_availability.return_value = {
            "connected": True,
            "model_available": True,
            "available_models": ["gemma4:12b"],
        }
        mock_client.generate.return_value = {
            "success": True,
            "response": '{"status":"healthy"}',
            "duration_ms": 120,
        }

        mgr = AIModelLifecycleManager(client=mock_client)
        info = mgr.validate_text_model("gemma4:12b")
        assert info.status == ModelStatus.READY
        assert info.installed is True
        assert info.available is True

        # 2. Missing model scenario
        mock_client.check_model_availability.return_value = {
            "connected": True,
            "model_available": False,
            "available_models": [],
        }
        info_missing = mgr.validate_text_model("gemma4:12b")
        assert info_missing.status == ModelStatus.MISSING
        assert info_missing.installed is False

        # 3. Ollama offline scenario
        mock_client.check_model_availability.return_value = {
            "connected": False,
            "model_available": False,
        }
        info_offline = mgr.validate_text_model("gemma4:12b")
        assert info_offline.status == ModelStatus.UNAVAILABLE

    def test_vision_model_validation_flow(self) -> None:
        """Test vision model validation scenarios."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.check_model_availability.return_value = {
            "connected": True,
            "model_available": True,
            "available_models": ["minicpm-v:latest"],
        }

        mgr = AIModelLifecycleManager(client=mock_client)
        info = mgr.validate_vision_model("minicpm-v:latest")
        assert info.status == ModelStatus.READY
        assert ModelCapability.VISION in info.capabilities

    def test_stt_backend_validation(self) -> None:
        """Test speech-to-text backend validation."""
        mgr = AIModelLifecycleManager()

        info_ok = mgr.validate_stt_backend("whisper_cpp")
        assert info_ok.status == ModelStatus.READY
        assert ModelCapability.SPEECH_TO_TEXT in info_ok.capabilities

        info_bad = mgr.validate_stt_backend("unapproved_cloud_stt")
        assert info_bad.status == ModelStatus.INCOMPATIBLE

    def test_aggregate_ai_health_evaluation(self) -> None:
        """Test aggregate health assessment under ready and degraded conditions."""
        mock_client = MagicMock(spec=OllamaClient)

        # 1. Fully ready
        mock_client.check_connection.return_value = {"connected": True, "version": "0.1.30", "base_url": "http://localhost:11434"}
        mock_client.check_model_availability.return_value = {"connected": True, "model_available": True}
        mock_client.generate.return_value = {"success": True, "duration_ms": 50}

        mgr = AIModelLifecycleManager(client=mock_client)
        agg = mgr.check_aggregate_ai_health()
        assert agg.overall_status == ModelStatus.READY
        assert agg.ollama_status == ModelStatus.READY
        assert agg.is_fully_ready() is True

        # 2. Degraded: Ollama offline
        mock_client.check_connection.return_value = {"connected": False, "error": "Connection refused"}
        mock_client.check_model_availability.return_value = {"connected": False, "model_available": False}

        agg_degraded = mgr.check_aggregate_ai_health()
        assert agg_degraded.overall_status == ModelStatus.DEGRADED
        assert agg_degraded.is_degraded() is True

    def test_model_switching_and_cache_invalidation(self) -> None:
        """Test safe model switching, config updating, and cache invalidation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "ai_models.json"
            cfg_mgr = AIConfigurationManager(config_file=cfg_file)
            mock_client = MagicMock(spec=OllamaClient)

            mgr = AIModelLifecycleManager(client=mock_client, config_manager=cfg_mgr)

            # Switch to another approved text model
            success, msg = mgr.switch_model(ModelType.TEXT, "gemma:7b")
            assert success is True
            assert mgr.config.text_model == "gemma:7b"
            mock_client.clear_cache.assert_called_once()

            # Attempt switch to unapproved model
            success_bad, msg_bad = mgr.switch_model(ModelType.TEXT, "malicious_unapproved:latest")
            assert success_bad is False
            assert "not an approved" in msg_bad
            assert mgr.config.text_model == "gemma:7b"

    def test_production_health_check_incorporates_ai_lifecycle(self) -> None:
        """Verify HealthCheckEngine includes ai_lifecycle data in StartupHealthReport."""
        engine = HealthCheckEngine()
        report = engine.run_health_check()
        assert report.is_operational() is True
        assert report.ai_lifecycle is not None
        assert "overall_status" in report.ai_lifecycle
        assert "ollama_status" in report.ai_lifecycle
        assert "text_ai_status" in report.ai_lifecycle

    def test_profiler_records_model_management_metrics(self) -> None:
        """Verify that model lifecycle actions record local performance measurements."""
        default_profiler.clear()
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.list_local_models.return_value = {"success": True, "raw_models": []}

        mgr = AIModelLifecycleManager(client=mock_client)
        mgr.discover_installed_models()

        metrics = default_profiler.get_metrics("model_discovery")
        assert len(metrics) > 0
        assert metrics[0].status == "SUCCESS"
        assert metrics[0].duration_ms >= 0.0

    def test_ollama_client_timeout_and_error_handling(self) -> None:
        """Verify OllamaClient handles network timeouts and URLErrors cleanly."""
        import urllib.error
        client = OllamaClient(base_url="http://localhost:11434", timeout=1)

        with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
            res = client.generate(prompt="test timeout", use_cache=False)
            assert res["success"] is False
            assert "timed out" in res["error"].lower()

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            conn = client.check_connection()
            assert conn["connected"] is False
            assert "not running" in conn["error"]

    def test_malformed_json_ollama_response_handling(self) -> None:
        """Verify OllamaClient handles corrupted non-JSON responses without unhandled crashes."""
        client = OllamaClient(base_url="http://localhost:11434")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            res = client.generate(prompt="test json parse failure")
            assert res["success"] is False
            assert res["error"] is not None

    def test_degraded_mode_tutor_when_ai_offline(self) -> None:
        """Verify Personal Tutor generates deterministic educational guidance when Ollama is offline."""
        from modes.personal_tutor import PersonalTutor
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.is_available.return_value = False
        mock_client.generate.return_value = {"success": False, "error": "Ollama offline"}

        tutor = PersonalTutor(client=mock_client)
        resp = tutor.explain_diagnostic(
            {"status": "disconnected", "adapters": []},
            user_question="How do I fix a disconnected network adapter?",
        )
        assert resp is not None
        assert len(resp.summary) > 0 or len(resp.what_happened) > 0
        assert resp.severity in ("NORMAL", "ELEVATED", "HIGH", "CRITICAL", "UNKNOWN")



    def test_arbitrary_url_and_executable_path_rejection_in_config(self) -> None:
        """Verify that remote URLs or local executable paths cannot be configured as model IDs."""
        cfg = AIModelConfiguration(
            text_model="http://evil.com/model.bin",
            vision_model="C:\\Windows\\System32\\cmd.exe",
            stt_backend="https://cloud-api.com/stt",
        )
        val = cfg.validate()
        assert val["valid"] is False
        assert len(val["errors"]) >= 3

