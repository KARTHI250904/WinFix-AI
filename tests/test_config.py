"""Tests for WinFix AI configuration management."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from config import AppConfig, BASE_DIR


class TestAppConfig(unittest.TestCase):
    """Test suite for AppConfig class."""

    def test_default_config_values(self) -> None:
        """Verify default configuration values match project specifications."""
        cfg = AppConfig()
        self.assertEqual(cfg.app_name, "WinFix AI")
        self.assertEqual(cfg.app_tagline, "Your Offline Windows Assistant")
        self.assertEqual(cfg.default_model, "gemma4:12b")
        self.assertEqual(cfg.ollama_base_url, "http://localhost:11434")
        self.assertEqual(cfg.ollama_timeout_seconds, 10)
        self.assertEqual(cfg.database_path, BASE_DIR / "winfix.db")
        self.assertEqual(cfg.schema_path, BASE_DIR / "database" / "schema.sql")

    def test_env_var_overrides(self) -> None:
        """Verify configuration respects environment variable overrides."""
        env_overrides = {
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "OLLAMA_MODEL": "custom-gemma:latest",
            "OLLAMA_TIMEOUT_SECONDS": "20",
            "SQLITE_DB_NAME": "custom_test.db",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env_overrides, clear=False):
            cfg = AppConfig()
            self.assertEqual(cfg.ollama_base_url, "http://127.0.0.1:11434")
            self.assertEqual(cfg.default_model, "custom-gemma:latest")
            self.assertEqual(cfg.ollama_timeout_seconds, 20)
            self.assertEqual(cfg.database_path, BASE_DIR / "custom_test.db")
            self.assertEqual(cfg.log_level, "DEBUG")


if __name__ == "__main__":
    unittest.main()
