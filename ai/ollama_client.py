"""Ollama client health, model inspection, and generation module for WinFix AI.

Provides safe, local-only communication with the Ollama runtime.
Complies strictly with safety rules: no shell execution, no arbitrary commands,
local offline execution only.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from config import config

logger = logging.getLogger(__name__)


class OllamaClient:
    """Safe local client for Ollama runtime status, model inspection, and text generation."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or config.ollama_base_url).rstrip("/")
        self.default_model = default_model or config.default_model
        self.timeout = timeout or config.ollama_timeout_seconds

    def is_available(self) -> bool:
        """Convenience method checking if Ollama is connected and default model is available."""
        status = self.check_model_availability()
        return bool(status.get("model_available", False))

    def check_connection(self) -> Dict[str, Any]:
        """Check whether the Ollama server is online and responding.

        Returns structured status without raising unhandled exceptions.
        """
        url = f"{self.base_url}/api/version"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode("utf-8"))
                    version = payload.get("version", "unknown")
                    return {
                        "connected": True,
                        "base_url": self.base_url,
                        "version": version,
                        "error": None,
                    }
                return {
                    "connected": False,
                    "base_url": self.base_url,
                    "version": None,
                    "error": f"Unexpected HTTP status: {response.status}",
                }
        except urllib.error.URLError as err:
            logger.debug("Ollama is not reachable at %s: %s", self.base_url, err)
            return {
                "connected": False,
                "base_url": self.base_url,
                "version": None,
                "error": "Ollama service is not running or unreachable at the configured URL.",
            }
        except Exception as exc:
            logger.debug("Ollama connection check failed: %s", exc)
            return {
                "connected": False,
                "base_url": self.base_url,
                "version": None,
                "error": str(exc),
            }

    def list_local_models(self) -> Dict[str, Any]:
        """Fetch list of models currently downloaded and available in local Ollama.

        Returns structured response with model names and details.
        """
        url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode("utf-8"))
                    raw_models = payload.get("models", [])
                    model_names = [m.get("name", "") for m in raw_models if "name" in m]
                    return {
                        "success": True,
                        "models": model_names,
                        "raw_models": raw_models,
                        "error": None,
                    }
                return {
                    "success": False,
                    "models": [],
                    "raw_models": [],
                    "error": f"Failed to list models (HTTP {response.status})",
                }
        except Exception as exc:
            return {
                "success": False,
                "models": [],
                "raw_models": [],
                "error": str(exc),
            }

    def check_model_availability(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Check whether the target model (e.g. gemma4:12b) is locally available in Ollama."""
        target_model = model_name or self.default_model

        # Check general connection first
        conn_status = self.check_connection()
        if not conn_status["connected"]:
            return {
                "connected": False,
                "base_url": self.base_url,
                "target_model": target_model,
                "model_available": False,
                "available_models": [],
                "error": conn_status["error"],
            }

        models_res = self.list_local_models()
        if not models_res["success"]:
            return {
                "connected": True,
                "base_url": self.base_url,
                "target_model": target_model,
                "model_available": False,
                "available_models": [],
                "error": models_res["error"],
            }

        available = models_res["models"]
        # Match exact tag or base tag (e.g. 'gemma4:12b' or 'gemma4:12b:latest')
        is_available = any(
            m == target_model or m.startswith(f"{target_model}:") or target_model.startswith(f"{m}:")
            for m in available
        )

        return {
            "connected": True,
            "base_url": self.base_url,
            "target_model": target_model,
            "model_available": is_available,
            "available_models": available,
            "error": None if is_available else f"Model '{target_model}' is not installed in local Ollama.",
        }

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        format: Optional[str] = "json",
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a generation request to the local Ollama endpoint.

        Returns structured response dictionary without throwing unhandled exceptions.
        """
        target_model = model or self.default_model
        url = f"{self.base_url}/api/generate"
        start_time = time.time()

        payload: Dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if format:
            payload["format"] = format
        if options:
            payload["options"] = options
        else:
            payload["options"] = {"temperature": 0.1}

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                duration_ms = int((time.time() - start_time) * 1000)
                if response.status == 200:
                    resp_body = json.loads(response.read().decode("utf-8"))
                    raw_text = resp_body.get("response", "")
                    return {
                        "success": True,
                        "response": raw_text,
                        "model": target_model,
                        "duration_ms": duration_ms,
                        "error": None,
                        "raw_response": resp_body,
                    }
                return {
                    "success": False,
                    "response": "",
                    "model": target_model,
                    "duration_ms": duration_ms,
                    "error": f"Ollama HTTP error {response.status}",
                    "raw_response": None,
                }
        except urllib.error.URLError as err:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning("Ollama generate connection error: %s", err)
            return {
                "success": False,
                "response": "",
                "model": target_model,
                "duration_ms": duration_ms,
                "error": f"Ollama connection error: {err.reason if hasattr(err, 'reason') else str(err)}",
                "raw_response": None,
            }
        except TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning("Ollama generate request timed out after %s seconds", self.timeout)
            return {
                "success": False,
                "response": "",
                "model": target_model,
                "duration_ms": duration_ms,
                "error": f"Ollama request timed out after {self.timeout}s",
                "raw_response": None,
            }
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning("Ollama generate unexpected exception: %s", exc)
            return {
                "success": False,
                "response": "",
                "model": target_model,
                "duration_ms": duration_ms,
                "error": str(exc),
                "raw_response": None,
            }

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        format: Optional[str] = "json",
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a chat-formatted request to the local Ollama endpoint."""
        target_model = model or self.default_model
        url = f"{self.base_url}/api/chat"
        start_time = time.time()

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": False,
        }
        if format:
            payload["format"] = format
        if options:
            payload["options"] = options
        else:
            payload["options"] = {"temperature": 0.1}

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                duration_ms = int((time.time() - start_time) * 1000)
                if response.status == 200:
                    resp_body = json.loads(response.read().decode("utf-8"))
                    msg = resp_body.get("message", {})
                    content = msg.get("content", "")
                    return {
                        "success": True,
                        "response": content,
                        "model": target_model,
                        "duration_ms": duration_ms,
                        "error": None,
                        "raw_response": resp_body,
                    }
                return {
                    "success": False,
                    "response": "",
                    "model": target_model,
                    "duration_ms": duration_ms,
                    "error": f"Ollama HTTP error {response.status}",
                    "raw_response": None,
                }
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "response": "",
                "model": target_model,
                "duration_ms": duration_ms,
                "error": str(exc),
                "raw_response": None,
            }


# Default shared client instance
ollama_client = OllamaClient()
