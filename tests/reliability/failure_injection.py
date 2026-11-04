"""WinFix AI — Failure Injection Simulator (Phase 33)."""

from enum import Enum
from typing import Any, Callable, Dict, Optional


class FaultType(str, Enum):
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED_JSON = "MALFORMED_JSON"
    ACCESS_DENIED = "ACCESS_DENIED"
    CONTRADICTORY_DATA = "CONTRADICTORY_DATA"
    DATABASE_LOCK = "DATABASE_LOCK"


class FailureInjector:
    """Provides controlled, mockable faults for testing resilience and fail-closed behaviors."""

    @staticmethod
    def mock_ollama_failure(fault_type: FaultType) -> Dict[str, Any]:
        """Simulate specific Ollama server and generation failure modes."""
        if fault_type == FaultType.TIMEOUT:
            raise TimeoutError("Local Ollama generate timed out after 10.0s")
        elif fault_type == FaultType.UNAVAILABLE:
            raise ConnectionError("Failed to connect to local Ollama on 127.0.0.1:11434")
        elif fault_type == FaultType.MALFORMED_JSON:
            return {"raw_text": "{ malformed_json: true, unterminated }"}
        elif fault_type == FaultType.CONTRADICTORY_DATA:
            return {
                "hypotheses": [{"name": "Hypothesis A", "status": "CONTRADICTED"}],
                "recommended_tools": ["non_existent_tool_xyz"],
            }
        return {}

    @staticmethod
    def mock_windows_api_failure(fault_type: FaultType) -> Dict[str, Any]:
        """Simulate native Windows diagnostic API faults."""
        if fault_type == FaultType.ACCESS_DENIED:
            raise PermissionError("[WinError 5] Access is denied")
        elif fault_type == FaultType.TIMEOUT:
            raise TimeoutError("Windows API query timed out")
        elif fault_type == FaultType.UNAVAILABLE:
            raise RuntimeError("Windows subsystem WMI/ServiceControlManager unavailable")
        return {"status": "error", "error_code": 0x80070005}
