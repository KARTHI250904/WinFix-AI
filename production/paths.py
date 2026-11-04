"""
WinFix AI — Windows Application Data & Path Management (Phase 22).

Manages controlled application data directories in standard Windows user paths
(or explicit environment overrides) with directory creation, permission checks,
and strict path traversal prevention.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Dict, Optional


@dataclass(frozen=True)
class AppPaths:
    """Strongly typed container for all application directories and files."""

    root_dir: Path
    data_dir: Path
    logs_dir: Path
    config_dir: Path
    temp_dir: Path
    database_path: Path
    schema_path: Path


def get_default_app_data_dir() -> Path:
    """Determine standard Windows application data directory for WinFix AI."""
    # 1. Check explicit environment override
    env_override = os.getenv("WINFIX_APP_DATA_DIR")
    if env_override:
        return Path(env_override).resolve()

    # 2. Use Windows LOCALAPPDATA or APPDATA if available
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "WinFixAI"

    app_data = os.getenv("APPDATA")
    if app_data:
        return Path(app_data) / "WinFixAI"

    # 3. Fallback to user home directory or project directory
    return Path.home() / ".winfix_ai"


def resolve_app_paths(base_data_dir: Optional[Path] = None) -> AppPaths:
    """Resolve and build full AppPaths structure."""
    root = (base_data_dir or get_default_app_data_dir()).resolve()
    project_root = Path(__file__).resolve().parent.parent

    data_dir = root / "Data"
    logs_dir = root / "Logs"
    config_dir = root / "Config"
    temp_dir = root / "Temp"
    database_path = data_dir / "winfix.db"
    schema_path = project_root / "database" / "schema.sql"

    return AppPaths(
        root_dir=root,
        data_dir=data_dir,
        logs_dir=logs_dir,
        config_dir=config_dir,
        temp_dir=temp_dir,
        database_path=database_path,
        schema_path=schema_path,
    )


get_default_paths = resolve_app_paths


def initialize_app_directories(paths: AppPaths) -> Dict[str, bool]:
    """Create all required application directories with write verification."""
    results = {}
    dirs_to_create = [
        ("root", paths.root_dir),
        ("data", paths.data_dir),
        ("logs", paths.logs_dir),
        ("config", paths.config_dir),
        ("temp", paths.temp_dir),
    ]

    for name, directory in dirs_to_create:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # Verify write permissions using a temporary probe file
            probe = directory / ".write_probe"
            probe.write_text("probe", encoding="utf-8")
            probe.unlink(missing_ok=True)
            results[name] = True
        except Exception:
            results[name] = False

    return results


def is_safe_app_path(target_path: Path, allowed_root: Path) -> bool:
    """Verify target path does not escape allowed directory via path traversal or symlinks."""
    try:
        resolved_target = target_path.resolve()
        resolved_root = allowed_root.resolve()
        return str(resolved_target).startswith(str(resolved_root))
    except Exception:
        return False
