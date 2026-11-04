"""Read-only Windows Audio Diagnostic Tools for WinFix AI.

Provides structured audio device enumeration, audio background service inspection,
and endpoint status analysis without adjusting master volumes, modifying sound schemes,
or resetting playback hardware.
"""

import ctypes
import logging
from typing import Any, Dict, List, Optional

from windows.service_tools import get_service_status

logger = logging.getLogger(__name__)


def get_audio_diagnostics() -> Dict[str, Any]:
    """Inspect Windows Audio subsystem health, core audio services, and device counts."""
    tool_name = "get_audio_diagnostics"
    domain = "audio"
    try:
        # Check core Windows audio services
        audiosrv_res = get_service_status("Audiosrv")
        audiosrv_data = audiosrv_res.get("data") or {}
        audiosrv_running = audiosrv_data.get("is_running", False)

        endpoint_res = get_service_status("AudioEndpointBuilder")
        endpoint_data = endpoint_res.get("data") or {}
        endpoint_running = endpoint_data.get("is_running", False)

        # Query wave playback and recording device count via winmm
        playback_count = 0
        recording_count = 0
        try:
            winmm = ctypes.windll.winmm
            playback_count = winmm.waveOutGetNumDevs()
            recording_count = winmm.waveInGetNumDevs()
        except Exception as mm_err:
            logger.debug("Failed to query winmm wave devices: %s", mm_err)

        healthy = audiosrv_running and endpoint_running and (playback_count > 0 or recording_count > 0)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "audio_service_status": audiosrv_data.get("status", "UNKNOWN"),
                "audio_service_running": audiosrv_running,
                "audio_endpoint_builder_status": endpoint_data.get("status", "UNKNOWN"),
                "audio_endpoint_builder_running": endpoint_running,
                "playback_devices_count": playback_count,
                "recording_devices_count": recording_count,
                "audio_subsystem_healthy": bool(healthy),
            },
            "error": None,
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "AUDIO_QUERY_ERROR", "message": str(exc)},
        }


def get_audio_endpoint_status() -> Dict[str, Any]:
    """Inspect status of audio playback and recording endpoints."""
    tool_name = "get_audio_endpoint_status"
    domain = "audio"
    try:
        diag = get_audio_diagnostics()
        if not diag.get("success"):
            return diag

        diag_data = diag.get("data", {})
        playback_available = diag_data.get("playback_devices_count", 0) > 0
        recording_available = diag_data.get("recording_devices_count", 0) > 0
        services_ok = diag_data.get("audio_service_running", False) and diag_data.get("audio_endpoint_builder_running", False)

        return {
            "success": True,
            "tool": tool_name,
            "domain": domain,
            "data": {
                "playback_endpoints_available": playback_available,
                "recording_endpoints_available": recording_available,
                "audio_services_running": services_ok,
                "audiosrv_status": diag_data.get("audio_service_status"),
                "endpoint_builder_status": diag_data.get("audio_endpoint_builder_status"),
                "total_endpoints": diag_data.get("playback_devices_count", 0) + diag_data.get("recording_devices_count", 0),
            },
            "error": None,
        }
    except Exception as exc:
        logger.error("%s failed: %s", tool_name, exc)
        return {
            "success": False,
            "tool": tool_name,
            "domain": domain,
            "data": None,
            "error": {"code": "AUDIO_ENDPOINT_QUERY_ERROR", "message": str(exc)},
        }
