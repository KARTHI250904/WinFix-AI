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
            if name != "root" and not is_safe_app_path(directory, paths.root_dir):
                results[name] = False
                continue
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
    """
    Verify target path does not escape allowed directory via path traversal,
    sibling directory collisions, symlinks, or cross-drive references.

    Uses path-component containment rather than string prefix matching.
    Fails closed on resolution errors, invalid paths, or unsupported forms.
    """
    if target_path is None or allowed_root is None:
        return False
    try:
        target = Path(target_path)
        root = Path(allowed_root)

        str_target = str(target).strip()
        str_root = str(root).strip()
        if not str_target or not str_root:
            return False

        # Reject UNC / network paths if root is not on the same UNC network location
        target_is_unc = str_target.startswith(r"\\") or str_target.startswith("//")
        root_is_unc = str_root.startswith(r"\\") or str_root.startswith("//")
        if target_is_unc != root_is_unc:
            return False

        # Resolve both paths to normalize traversal sequences, symlinks, and relative segments
        resolved_target = target.resolve()
        resolved_root = root.resolve()

        # Enforce drive equality on Windows
        if resolved_target.drive or resolved_root.drive:
            if not resolved_target.drive or not resolved_root.drive:
                return False
            if resolved_target.drive.lower() != resolved_root.drive.lower():
                return False

        # Primary check: Path.is_relative_to enforces strict component hierarchy
        # (rejects sibling paths like C:\root_extra against C:\root)
        if resolved_target.is_relative_to(resolved_root):
            return True

        # Secondary check: Case-normalization fallback on Windows/macOS where filesystem
        # is case-preserving but case-insensitive, in case components have mismatched casing
        if os.name == "nt":
            target_parts = [p.lower() for p in resolved_target.parts]
            root_parts = [p.lower() for p in resolved_root.parts]
            if len(target_parts) >= len(root_parts) and target_parts[:len(root_parts)] == root_parts:
                return True

        return False
    except Exception:
        return False
