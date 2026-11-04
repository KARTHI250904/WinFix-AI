"""WinFix AI — Authoritative Version Management (Phase 25).

Single authoritative source of application identity, release metadata,
and semantic versioning for all UI, launcher, installer, and health check subsystems.
"""

from typing import Any, Dict

APP_NAME: str = "WinFix AI"
APP_VERSION: str = "1.0.0"
BUILD_VERSION: str = "1.0.0.0"
RELEASE_CHANNEL: str = "stable"
AUTHOR: str = "WinFix AI Team"
COPYRIGHT: str = "Copyright (c) 2026 WinFix AI"
PLATFORM_TARGET: str = "Windows 10 / Windows 11 (x64)"


def get_version_info() -> Dict[str, Any]:
    """Return structured version dictionary."""
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "build_version": BUILD_VERSION,
        "release_channel": RELEASE_CHANNEL,
        "author": AUTHOR,
        "copyright": COPYRIGHT,
        "platform_target": PLATFORM_TARGET,
    }
