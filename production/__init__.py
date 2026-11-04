"""
WinFix AI — Production Package (Phase 22).

Provides production configuration, lifecycle management, first-run initialization,
health checks, production logging, crash boundaries, and packaging helpers.
"""

from production.version import (
    APP_NAME as __app_name__,
    APP_VERSION as __version__,
    AUTHOR as __author__,
    BUILD_VERSION as __build_version__,
    RELEASE_CHANNEL as __release_channel__,
    get_version_info,
)

from production.paths import AppPaths, get_default_paths, initialize_app_directories, resolve_app_paths
from production.config import ProductionConfig, prod_config
from production.logging import get_category_logger, get_logger, setup_production_logging
from production.crash_handler import SafeCrashSummary, safe_exception_boundary
from production.health_check import ComponentHealth, ComponentStatus, HealthCheckEngine, StartupHealthReport
from production.setup import FirstRunResult, is_first_run, run_first_time_setup
from production.lifecycle import (
    MigrationResult,
    RestartCheckResult,
    UninstallPolicy,
    execute_safe_uninstall,
    run_database_migration,
    verify_restart_state,
)
from production.environment import (
    CapabilityEntry,
    CapabilityMatrix,
    CapabilityStatus,
    CompatibilityValidator,
    WindowsEnvironmentInfo,
    detect_windows_environment,
    is_process_elevated,
)
from production.installation import (
    InstallationInfo,
    InstallationManager,
    InstallationState,
    IntegrityCheckResult,
    compute_file_sha256,
    default_installation_manager,
    validate_installation_path,
)
from production.telemetry_models import (
    FailureTaxonomy,
    TelemetryEvent,
    TelemetryEventType,
    TelemetrySeverity,
)
from production.telemetry import (
    TelemetryService,
    default_telemetry_service,
    sanitize_telemetry_metadata,
    sanitize_telemetry_value,
)
from production.telemetry_analytics import (
    TelemetryAnalytics,
    default_telemetry_analytics,
)
from production.telemetry_retention import (
    TelemetryRetentionManager,
    default_telemetry_retention,
)
from production.compatibility import (
    CompatibilityMatrix,
    CompatibilityStatus,
    ComponentCheck,
    EnvironmentSnapshot,
    ValidationType,
    WindowsCompatibilityValidator,
    default_compatibility_validator,
)

__all__ = [
    "__version__",
    "__app_name__",
    "__author__",
    "AppPaths",
    "get_default_paths",
    "resolve_app_paths",
    "initialize_app_directories",
    "ProductionConfig",
    "prod_config",
    "setup_production_logging",
    "get_logger",
    "get_category_logger",
    "SafeCrashSummary",
    "safe_exception_boundary",
    "ComponentStatus",
    "ComponentHealth",
    "StartupHealthReport",
    "HealthCheckEngine",
    "FirstRunResult",
    "is_first_run",
    "run_first_time_setup",
    "UninstallPolicy",
    "MigrationResult",
    "RestartCheckResult",
    "verify_restart_state",
    "run_database_migration",
    "execute_safe_uninstall",
    "CapabilityStatus",
    "CapabilityEntry",
    "CapabilityMatrix",
    "WindowsEnvironmentInfo",
    "detect_windows_environment",
    "is_process_elevated",
    "CompatibilityValidator",
    "InstallationState",
    "InstallationInfo",
    "IntegrityCheckResult",
    "InstallationManager",
    "validate_installation_path",
    "compute_file_sha256",
    "default_installation_manager",
    "TelemetryEventType",
    "FailureTaxonomy",
    "TelemetrySeverity",
    "TelemetryEvent",
    "TelemetryService",
    "default_telemetry_service",
    "sanitize_telemetry_metadata",
    "sanitize_telemetry_value",
    "TelemetryAnalytics",
    "default_telemetry_analytics",
    "TelemetryRetentionManager",
    "default_telemetry_retention",
    "CompatibilityStatus",
    "ValidationType",
    "ComponentCheck",
    "EnvironmentSnapshot",
    "CompatibilityMatrix",
    "WindowsCompatibilityValidator",
    "default_compatibility_validator",
]
