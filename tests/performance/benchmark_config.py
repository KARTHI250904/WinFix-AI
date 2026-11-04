"""WinFix AI — Performance Benchmark Configuration & Thresholds (Phase 24)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceThresholds:
    """Realistic performance target ceilings (in milliseconds or megabytes)."""

    # Startup & Initialization ceilings (ms)
    MAX_STARTUP_TIME_MS: float = 3500.0
    MAX_DB_INIT_TIME_MS: float = 800.0
    MAX_KNOWLEDGE_INIT_TIME_MS: float = 1200.0
    MAX_TOOL_REGISTRY_INIT_TIME_MS: float = 250.0
    MAX_HEALTH_CHECK_TIME_MS: float = 2500.0

    # Runtime Operations ceilings (ms)
    MAX_SQLITE_QUERY_TIME_MS: float = 50.0
    MAX_KNOWLEDGE_SEARCH_TIME_MS: float = 150.0
    MAX_DIAGNOSTIC_LOOKUP_TIME_MS: float = 15.0
    MAX_SAFE_TOOL_EXEC_TIME_MS: float = 1000.0
    MAX_SYSTEM_INFO_TIME_MS: float = 1500.0

    # Memory ceilings (MB)
    MAX_IDLE_MEMORY_MB: float = 250.0
    MAX_DIAGNOSTIC_MEMORY_MB: float = 400.0
    MAX_SCREENSHOT_MEMORY_MB: float = 450.0
    MAX_VOICE_MEMORY_MB: float = 450.0
    MAX_LONG_RUNNING_MEMORY_GROWTH_MB: float = 50.0

    # Safety limits (strict)
    MAX_SCREENSHOT_BYTES: int = 10 * 1024 * 1024
    MAX_VOICE_BYTES: int = 25 * 1024 * 1024
    MAX_VOICE_SECONDS: int = 120
    MAX_VOICE_TRANSCRIPT_CHARS: int = 12000


benchmark_config = PerformanceThresholds()
