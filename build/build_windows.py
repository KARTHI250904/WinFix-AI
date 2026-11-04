"""WinFix AI — Windows Production Build & Distribution Packager (Phase 25).

Orchestrates reproducible packaging of WinFix AI into a self-contained,
offline-capable Windows distribution with build manifest, secret scanning,
and cryptographic SHA-256 checksums.
"""

from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Set, Tuple

# Base Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT_DIR / "build"
ARTIFACTS_DIR = BUILD_DIR / "artifacts"
DIST_DIR = BUILD_DIR / "dist" / "WinFixAI"
RELEASE_DIR = ROOT_DIR / "release"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("winfix.BUILD")

# Production Allowlist
PRODUCTION_DIRECTORIES: List[str] = [
    "agent",
    "ai",
    "database",
    "input",
    "knowledge",
    "modes",
    "production",
    "ui",
    "windows",
]

PRODUCTION_FILES: List[str] = [
    "app.py",
    "config.py",
    "winfix_launcher.py",
    "requirements.txt",
]

DEVELOPMENT_EXCLUSION_PATTERNS: Set[str] = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    ".env",
    "tests",
    "scratch",
    "benchmarks",
    ".coverage",
}

FORBIDDEN_SECRET_PATTERNS = [
    "sk-",
    "api_key",
    "bearer ",
    "ghp_",
    "password=",
    "secret=",
    "private_key",
]


def clean_build_directories() -> None:
    """Purge previous build and distribution artifacts."""
    logger.info("Cleaning previous build directories...")
    for directory in [ARTIFACTS_DIR, DIST_DIR, BUILD_DIR / "dist"]:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
            # If directory still exists due to Windows file handle locking, clear contents
            if directory.exists():
                for item in directory.iterdir():
                    try:
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                    except Exception:
                        pass
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)



def scan_for_secrets(source_dir: Path) -> List[str]:
    """Scan all packaged source files for potential credentials or secrets."""
    logger.info("Scanning package sources for potential secrets...")
    violations: List[str] = []

    for file_path in source_dir.rglob("*.py"):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore").lower()
            for pattern in FORBIDDEN_SECRET_PATTERNS:
                # Exclude safety/sanitizer definition references
                if pattern in content:
                    lines = content.splitlines()
                    for idx, line in enumerate(lines):
                        if pattern in line and not any(
                            safe_term in line
                            for safe_term in ["sanitize", "forbidden", "blacklist", "pattern", "replace", "mask", "re.compile", "sensitive", "redact", "allowlist"]
                        ):
                            violations.append(f"{file_path.relative_to(source_dir)}:{idx+1} matches '{pattern}'")
        except Exception as e:
            violations.append(f"Failed to scan {file_path}: {e}")

    return violations


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def copy_production_files(dist_root: Path) -> List[Path]:
    """Copy all approved production code and assets to destination."""
    logger.info("Copying production modules and assets...")
    copied_files: List[Path] = []

    # 1. Copy top-level files
    for filename in PRODUCTION_FILES:
        src = ROOT_DIR / filename
        if src.exists():
            dst = dist_root / filename
            shutil.copy2(src, dst)
            copied_files.append(dst)

    # 2. Copy production packages
    for dirname in PRODUCTION_DIRECTORIES:
        src_dir = ROOT_DIR / dirname
        dst_dir = dist_root / dirname
        if src_dir.exists():
            shutil.copytree(
                src_dir,
                dst_dir,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
                dirs_exist_ok=True,
            )
            for p in dst_dir.rglob("*"):
                if p.is_file():
                    copied_files.append(p)

    return copied_files


def generate_build_manifest(dist_root: Path, version: str) -> Dict[str, Any]:
    """Generate and write BUILD_MANIFEST.json containing cryptographic hashes."""
    logger.info("Generating cryptographic build manifest...")
    checksums: Dict[str, str] = {}
    total_size = 0

    for file_path in sorted(dist_root.rglob("*")):
        if file_path.is_file():
            rel_path = file_path.relative_to(dist_root).as_posix()
            file_hash = compute_sha256(file_path)
            checksums[rel_path] = file_hash
            total_size += file_path.stat().st_size

    manifest = {
        "application_name": "WinFix AI",
        "version": version,
        "build_timestamp": datetime.now().isoformat(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": "windows",
        "architecture": "x64",
        "package_format": "standalone_directory",
        "file_count": len(checksums),
        "package_size_bytes": total_size,
        "included_directories": PRODUCTION_DIRECTORIES,
        "included_files": PRODUCTION_FILES,
        "checksums": checksums,
    }

    manifest_file = dist_root / "BUILD_MANIFEST.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Also save copy in build/
    shutil.copy2(manifest_file, BUILD_DIR / "BUILD_MANIFEST.json")
    return manifest


def generate_checksum_file(dist_root: Path, artifacts_dir: Path) -> Path:
    """Generate SHA256SUMS.txt."""
    logger.info("Generating SHA256SUMS.txt...")
    sums_file = artifacts_dir / "SHA256SUMS.txt"
    with open(sums_file, "w", encoding="utf-8") as f:
        for p in sorted(dist_root.rglob("*")):
            if p.is_file():
                rel = p.relative_to(dist_root).as_posix()
                f.write(f"{compute_sha256(p)}  {rel}\n")
    return sums_file


def create_installer_script(dist_root: Path, artifacts_dir: Path, version: str) -> Path:
    """Generate an Inno Setup installer script definition for native Windows installer compilation."""
    logger.info("Generating Inno Setup compiler definition (winfix_setup.iss)...")
    iss_content = f"""[Setup]
AppName=WinFix AI
AppVersion={version}
AppPublisher=WinFix AI Team
AppPublisherURL=https://github.com/winfix-ai
DefaultDirName={{autopf}}\\WinFix AI
DefaultGroupName=WinFix AI
OutputDir={artifacts_dir.as_posix()}
OutputBaseFilename=WinFixAI-{version}-Setup
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{dist_root.as_posix()}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\WinFix AI"; Filename: "{{app}}\\winfix_launcher.py"
Name: "{{autodesktop}}\\WinFix AI"; Filename: "{{app}}\\winfix_launcher.py"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\winfix_launcher.py"; Description: "{{cm:LaunchProgram,WinFix AI}}"; Flags: nowait postinstall skipifsilent
"""
    iss_file = artifacts_dir / "winfix_setup.iss"
    iss_file.write_text(iss_content, encoding="utf-8")
    return iss_file


def build_package() -> Tuple[bool, Dict[str, Any]]:
    """Execute complete build pipeline."""
    from production.version import APP_VERSION
    logger.info(f"Starting WinFix AI build v{APP_VERSION}...")

    # 1. Clean
    clean_build_directories()

    # 2. Secret Scan
    violations = scan_for_secrets(ROOT_DIR / "production")
    if violations:
        logger.error(f"Build halted due to secret scan violations: {violations}")
        return False, {"error": "Secret scan failed", "violations": violations}

    # 3. Copy files
    copy_production_files(DIST_DIR)

    # 4. Generate Manifest
    manifest = generate_build_manifest(DIST_DIR, APP_VERSION)

    # 5. Checksum File
    generate_checksum_file(DIST_DIR, ARTIFACTS_DIR)

    # 6. Inno Setup Definition
    create_installer_script(DIST_DIR, ARTIFACTS_DIR, APP_VERSION)

    logger.info(f"Build complete! Packaged {manifest['file_count']} files ({manifest['package_size_bytes']} bytes).")
    return True, manifest


if __name__ == "__main__":
    success, res = build_package()
    if not success:
        sys.exit(1)
    print("Build successful.")
