"""Tests for WinFix AI Ollama client health and model inspection."""

import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from ai.ollama_client import OllamaClient


class TestOllamaClient(unittest.TestCase):
    """Test suite for OllamaClient."""

    def setUp(self) -> None:
        self.client = OllamaClient(
            base_url="http://localhost:11434",
            default_model="gemma4:12b",
            timeout=2,
        )

    def test_offline_handling_check_connection(self) -> None:
        """Verify check_connection returns structured offline status when unreachable without raising exception."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            result = self.client.check_connection()
            self.assertFalse(result["connected"])
            self.assertIsNone(result["version"])
            self.assertIsNotNone(result["error"])
            self.assertIn("Ollama service is not running", result["error"])

    def test_online_handling_check_connection(self) -> None:
        """Verify check_connection parses version payload correctly when Ollama is online."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"version": "0.34.2"}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = self.client.check_connection()
            self.assertTrue(result["connected"])
            self.assertEqual(result["version"], "0.34.2")
            self.assertIsNone(result["error"])

    def test_model_availability_when_installed(self) -> None:
        """Verify check_model_availability returns True when target model exists in local tags."""
        # Mock connection check
        with patch.object(self.client, "check_connection", return_value={"connected": True, "error": None}):
            # Mock list_local_models
            with patch.object(
                self.client,
                "list_local_models",
                return_value={
                    "success": True,
                    "models": ["gemma4:12b", "llama3:latest"],
                    "error": None,
                },
            ):
                result = self.client.check_model_availability("gemma4:12b")
                self.assertTrue(result["connected"])
                self.assertTrue(result["model_available"])
                self.assertEqual(result["target_model"], "gemma4:12b")
                self.assertIsNone(result["error"])

    def test_model_availability_when_missing(self) -> None:
        """Verify check_model_availability returns False with structured error when target model is missing."""
        with patch.object(self.client, "check_connection", return_value={"connected": True, "error": None}):
            with patch.object(
                self.client,
                "list_local_models",
                return_value={
                    "success": True,
                    "models": ["mistral:latest"],
                    "error": None,
                },
            ):
                result = self.client.check_model_availability("gemma4:12b")
                self.assertTrue(result["connected"])
                self.assertFalse(result["model_available"])
                self.assertIsNotNone(result["error"])
                self.assertIn("not installed", result["error"])


if __name__ == "__main__":
    unittest.main()
