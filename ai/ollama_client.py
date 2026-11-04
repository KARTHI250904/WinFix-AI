"""Ollama client health, model inspection, and generation module for WinFix AI.

Provides safe, local-only communication with the Ollama runtime.
Complies strictly with safety rules: no shell execution, no arbitrary commands,
local offline execution only.
"""

import json
import logging
import os
import socket
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
        raw_url = (base_url or config.ollama_base_url).rstrip("/")
        # In offline environments on Windows, resolving 'localhost' can fail when network
        # interfaces are disconnected (WinError 11001 / getaddrinfo failure). Normalizing
        # 'localhost' to '127.0.0.1' guarantees direct IPv4 loopback routing without DNS lookup.
        if "://localhost" in raw_url:
            self.base_url = raw_url.replace("://localhost", "://127.0.0.1")
        else:
            self.base_url = raw_url
        self.default_model = default_model or config.default_model
        self.timeout = timeout or config.ollama_timeout_seconds
        self._read_only_cache: Dict[str, Dict[str, Any]] = {}
        self._max_cache_entries = 100
        self._last_conn_check: Optional[Dict[str, Any]] = None

    def _get_fallback_url(self, url: str) -> Optional[str]:
        """Return alternative loopback URL if applicable. Never fall back to 'localhost' when on 127.0.0.1 to avoid Windows offline DNS resolution delays."""
        if "://localhost" in url:
            return url.replace("://localhost", "://127.0.0.1")
        return None

    def clear_cache(self) -> None:
        """Clear the read-only generation cache."""
        self._read_only_cache.clear()
        self._last_conn_check = None

    def is_available(self) -> bool:
        """Convenience method checking if Ollama is connected and default model is available."""
        status = self.check_model_availability()
        return bool(status.get("model_available", False))

    def check_health(self) -> Dict[str, Any]:
        """Convenience method checking both connection and model availability."""
        status = self.check_model_availability()
        return {
            "connected": status.get("connected", False),
            "model_available": status.get("model_available", False),
            "model": status.get("target_model", self.default_model),
            "available_models": status.get("available_models", []),
            "error": status.get("error"),
        }

    def check_connection(self, force: bool = False) -> Dict[str, Any]:
        """Check whether the Ollama server is online and responding.

        Returns structured status without raising unhandled exceptions.
        Uses a short 1-second timeout and brief cache to avoid freezing offline interfaces.
        """
        now = time.time()
        cache_ttl = 3.0 if (self._last_conn_check and self._last_conn_check.get("result", {}).get("connected")) else 0.0
        if not force and self._last_conn_check and (now - self._last_conn_check.get("time", 0)) < cache_ttl:
            return self._last_conn_check["result"]

        urls_to_try = [f"{self.base_url}/api/version"]
        probe_timeout = min(1.0, float(self.timeout))

        last_err: Optional[Exception] = None
        for candidate_url in urls_to_try:
            try:
                req = urllib.request.Request(candidate_url, method="GET")
                with urllib.request.urlopen(req, timeout=probe_timeout) as response:
                    if response.status == 200:
                        payload = json.loads(response.read().decode("utf-8"))
                        version = payload.get("version", "unknown")
                        res = {
                            "connected": True,
                            "base_url": self.base_url,
                            "version": version,
                            "error": None,
                        }
                        self._last_conn_check = {"time": now, "result": res}
                        return res
                    res = {
                        "connected": False,
                        "base_url": self.base_url,
                        "version": None,
                        "error": f"Unexpected HTTP status: {response.status}",
                    }
                    self._last_conn_check = {"time": now, "result": res}
                    return res
            except urllib.error.URLError as err:
                last_err = err
                continue
            except Exception as exc:
                logger.debug("Ollama connection check failed: %s", exc)
                res = {
                    "connected": False,
                    "base_url": self.base_url,
                    "version": None,
                    "error": str(exc),
                }
                self._last_conn_check = {"time": now, "result": res}
                return res

        logger.debug("Ollama is not reachable at %s: %s", self.base_url, last_err)
        res = {
            "connected": False,
            "base_url": self.base_url,
            "version": None,
            "error": "Ollama service is not running or unreachable at the configured URL.",
        }
        self._last_conn_check = {"time": now, "result": res}
        return res

    def list_local_models(self) -> Dict[str, Any]:
        """Fetch list of models currently downloaded and available in local Ollama.

        Returns structured response with model names and details.
        """
        conn = self.check_connection()
        if not conn.get("connected"):
            return {
                "success": False,
                "models": [],
                "raw_models": [],
                "error": "Ollama service is offline or unreachable.",
            }

        urls_to_try = [f"{self.base_url}/api/tags"]
        probe_timeout = min(2.0, float(self.timeout))

        last_err: Optional[Exception] = None
        for candidate_url in urls_to_try:
            try:
                req = urllib.request.Request(candidate_url, method="GET")
                with urllib.request.urlopen(req, timeout=probe_timeout) as response:
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
            except urllib.error.URLError as err:
                last_err = err
                continue
            except Exception as exc:
                return {
                    "success": False,
                    "models": [],
                    "raw_models": [],
                    "error": str(exc),
                }

        return {
            "success": False,
            "models": [],
            "raw_models": [],
            "error": str(last_err) if last_err else "Ollama unreachable",
        }

    def check_model_availability(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Check whether the target model (e.g. gemma4:12b) is locally available in Ollama."""
        target_model = model_name or self.default_model

        models_res = self.list_local_models()
        if not models_res["success"]:
            # If listing failed, check general connection for specific error
            conn_status = self.check_connection()
            return {
                "connected": conn_status.get("connected", False),
                "base_url": self.base_url,
                "target_model": target_model,
                "model_available": False,
                "available_models": [],
                "error": conn_status.get("error") or models_res.get("error"),
            }

        available = models_res["models"]
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
        images: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
        use_cache: bool = False,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a generation request to the local Ollama endpoint.

        Returns structured response dictionary without throwing unhandled exceptions.
        Supports safe in-memory read-only deduplication when use_cache=True.
        """
        target_model = model or self.default_model
        req_timeout = timeout if timeout is not None else self.timeout

        # Fast-fail if Ollama service is not running or unreachable
        conn = self.check_connection()
        if not conn.get("connected"):
            conn_err = str(conn.get("error") or "")
            is_timeout = "timed out" in conn_err.lower() or "timeout" in conn_err.lower()
            return {
                "success": False,
                "timeout": is_timeout,
                "response": "",
                "model": target_model,
                "duration_ms": 0,
                "error": f"Ollama request timed out: {conn_err}" if is_timeout else "Ollama service is offline or unreachable.",
                "raw_response": None,
            }

        # Safe read-only cache check (never cache repair authorizations or security decisions)
        cache_key = None
        if use_cache:
            import hashlib
            raw_key = f"{target_model}|{format}|{system or ''}|{prompt}|{len(images) if images else 0}|{json.dumps(options or {}, sort_keys=True)}"
            cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            if cache_key in self._read_only_cache:
                cached = dict(self._read_only_cache[cache_key])
                cached["cached"] = True
                return cached

        urls_to_try = [f"{self.base_url}/api/generate"]
        fb = self._get_fallback_url(urls_to_try[0])
        if fb:
            urls_to_try.append(fb)

        start_time = time.time()

        payload: Dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = images
        if system:
            payload["system"] = system
        if format:
            payload["format"] = format
        # Performance tuning for fast multi-threaded local CPU inference
        cpu_threads = min(8, os.cpu_count() or 4)
        default_opts: Dict[str, Any] = {
            "temperature": 0.1,
            "num_predict": 512,
            "num_ctx": 4096,
            "num_thread": cpu_threads,
        }
        if options:
            default_opts.update(options)
        payload["options"] = default_opts

        req_data = json.dumps(payload).encode("utf-8")
        last_url_err = None

        for current_url in urls_to_try:
            try:
                req = urllib.request.Request(
                    current_url,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=req_timeout) as response:
                    duration_ms = int((time.time() - start_time) * 1000)
                    if response.status == 200:
                        resp_body = json.loads(response.read().decode("utf-8"))
                        raw_text = resp_body.get("response", "")
                        result = {
                            "success": True,
                            "response": raw_text,
                            "model": target_model,
                            "duration_ms": duration_ms,
                            "error": None,
                            "raw_response": resp_body,
                        }
                        if use_cache and cache_key:
                            self._read_only_cache[cache_key] = result
                            if len(self._read_only_cache) > self._max_cache_entries:
                                # Drop oldest entry
                                oldest = next(iter(self._read_only_cache))
                                del self._read_only_cache[oldest]
                        return result
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
                reason_str = str(err.reason) if hasattr(err, "reason") else str(err)
                if "timed out" in reason_str.lower() or "timeout" in reason_str.lower() or isinstance(getattr(err, "reason", None), (TimeoutError, socket.timeout)):
                    logger.warning("Ollama generate connection error (timeout=True): %s", err)
                    return {
                        "success": False,
                        "timeout": True,
                        "response": "",
                        "model": target_model,
                        "duration_ms": duration_ms,
                        "error": f"Ollama request timed out after {req_timeout}s",
                        "raw_response": None,
                    }
                last_url_err = err
                continue
            except (TimeoutError, socket.timeout):
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning("Ollama generate request timed out after %s seconds", req_timeout)
                return {
                    "success": False,
                    "timeout": True,
                    "response": "",
                    "model": target_model,
                    "duration_ms": duration_ms,
                    "error": f"Ollama request timed out after {req_timeout}s",
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

        duration_ms = int((time.time() - start_time) * 1000)
        reason_str = str(last_url_err.reason) if last_url_err and hasattr(last_url_err, "reason") else str(last_url_err)
        return {
            "success": False,
            "timeout": False,
            "response": "",
            "model": target_model,
            "duration_ms": duration_ms,
            "error": f"Ollama connection error: {reason_str}",
            "raw_response": None,
        }

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        format: Optional[str] = "json",
        options: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a chat-formatted request to the local Ollama endpoint."""
        target_model = model or self.default_model
        req_timeout = timeout if timeout is not None else self.timeout
        urls_to_try = [f"{self.base_url}/api/chat"]
        fb = self._get_fallback_url(urls_to_try[0])
        if fb:
            urls_to_try.append(fb)

        start_time = time.time()

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": False,
        }
        if format:
            payload["format"] = format
        # Performance tuning for fast multi-threaded local CPU inference
        cpu_threads = min(8, os.cpu_count() or 4)
        default_opts: Dict[str, Any] = {
            "temperature": 0.1,
            "num_predict": 512,
            "num_ctx": 4096,
            "num_thread": cpu_threads,
        }
        if options:
            default_opts.update(options)
        payload["options"] = default_opts

        req_data = json.dumps(payload).encode("utf-8")
        last_chat_err = None

        for current_url in urls_to_try:
            try:
                req = urllib.request.Request(
                    current_url,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=req_timeout) as response:
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
            except urllib.error.URLError as err:
                last_chat_err = err
                continue
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

        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "response": "",
            "model": target_model,
            "duration_ms": duration_ms,
            "error": str(last_chat_err) if last_chat_err else "Ollama unreachable",
            "raw_response": None,
        }


# Default shared client instance
ollama_client = OllamaClient()
