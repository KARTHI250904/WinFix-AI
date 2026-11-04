"""
WinFix AI — Production Application Launcher (Phase 22).

Coordinates production startup sequence:
1. Environment and configuration loading.
2. Centralized, sanitized logging setup.
3. Idempotent first-run initialization & SQLite verification.
4. Comprehensive pre-flight health evaluation.
5. Streamlit application bootstrap within safe boundary.
"""

import argparse
import os
from pathlib import Path
import sys
import subprocess

from production import (
    __app_name__,
    __version__,
    ComponentStatus,
    HealthCheckEngine,
    prod_config,
    run_database_migration,
    run_first_time_setup,
    safe_exception_boundary,
    setup_production_logging,
)


def print_banner() -> None:
    """Display startup header."""
    print("=" * 60)
    print(f"  {__app_name__} — Production Windows Troubleshooting Agent")
    print(f"  Version: {__version__}")
    print("=" * 60)


def print_health_report(report) -> None:
    """Render formatted startup health status."""
    print("\n--- Startup Health Check ---")
    for key, comp in report.components.items():
        status_marker = "[OK]" if comp.status == ComponentStatus.READY else "[WARN]" if comp.status == ComponentStatus.DEGRADED else "[FAIL]"
        print(f"  {status_marker:<8} {comp.name:<25} : {comp.status.value:<10} ({comp.details})")
    
    print("-" * 60)
    print(f"  Overall System Readiness: {report.overall_status.value}")
    if report.tool_counts:
        print(f"  Tools Registered        : {report.tool_counts.get('total', 0)} "
              f"({report.tool_counts.get('safe', 0)} SAFE, {report.tool_counts.get('medium', 0)} MEDIUM, {report.tool_counts.get('high', 0)} HIGH)")
    print("=" * 60 + "\n")


def launch_streamlit_app(
    port: int = 8501,
    host: str = "127.0.0.1",
    headless: bool = False,
    offline: bool = True,
) -> int:
    """Launch Streamlit web UI in offline mode."""
    app_py = Path(__file__).parent / "app.py"
    if not app_py.exists():
        print(f"Error: Application file not found: {app_py}")
        return 1

    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
        if not os.environ.get("OLLAMA_BASE_URL") or "localhost" in os.environ.get("OLLAMA_BASE_URL", ""):
            os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_py),
        "--server.port",
        str(port),
        "--server.address",
        str(host),
        "--browser.gatherUsageStats",
        "false",
    ]
    if headless:
        cmd.extend(["--server.headless", "true"])

    display_host = "localhost" if host == "0.0.0.0" else host
    print(f"Starting {__app_name__} UI (Offline Mode: {'ENABLED' if offline else 'DISABLED'})...")
    print(f"  • Local URL:   http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"  • Loopback:    http://127.0.0.1:{port}")
        print(f"  • Network URL: http://<Your-PC-IP>:{port} (accessible across local offline network)")
    else:
        print(f"  • Bound Host:  http://{host}:{port}")
    try:
        proc = subprocess.run(cmd)
        return proc.returncode
    except KeyboardInterrupt:
        print(f"\n{__app_name__} stopped by user.")
        return 0
    except Exception as e:
        print(f"Error launching Streamlit UI: {e}")
        return 1


def main() -> int:
    """Main launcher entry point."""
    parser = argparse.ArgumentParser(description=f"{__app_name__} Production Launcher")
    parser.add_argument("--version", "-v", action="version", version=f"{__app_name__} v{__version__}")
    parser.add_argument("--check-only", action="store_true", help="Run health check and exit without launching UI")
    parser.add_argument("--setup-only", action="store_true", help="Run first-time initialization and exit")
    parser.add_argument("--migrate", action="store_true", help="Run transactional schema migration and exit")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind the UI server to (default: 0.0.0.0 for Local & LAN)")
    parser.add_argument("--port", type=int, default=8501, help="Port to run the UI server on (default: 8501)")
    parser.add_argument("--headless", action="store_true", help="Run Streamlit in headless mode")
    parser.add_argument("--offline", action="store_true", default=True, help="Enforce offline operation (default: True)")
    parser.add_argument("--online", dest="offline", action="store_false", help="Allow online telemetry and model lookups")

    args = parser.parse_args()

    # Enforce IPv4 loopback for Ollama to prevent offline Windows DNS resolution issues
    if "localhost" in os.environ.get("OLLAMA_BASE_URL", ""):
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
    else:
        os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    # 1. Setup production logging
    logger = setup_production_logging(prod_config)
    logger.info(f"Launcher started: {__app_name__} v{__version__}")

    print_banner()

    # 2. Migration flow
    if args.migrate:
        print("Running database schema migration...")
        mig_res = run_database_migration(target_version=__version__, config=prod_config)
        if mig_res.success:
            print(f"[OK] Migration completed: v{mig_res.from_version} -> v{mig_res.to_version}")
            print(f"     Audits preserved: {mig_res.audit_records_preserved}")
            return 0
        else:
            print(f"[FAIL] Migration failed: {mig_res.error}")
            return 1

    # 3. Setup flow
    setup_res = run_first_time_setup(config=prod_config)
    if not setup_res.success and setup_res.health_report.overall_status == ComponentStatus.BLOCKED:
        print(f"[CRITICAL ERROR] First-time setup failed: {setup_res.message}")
        print_health_report(setup_res.health_report)
        return 1

    # 4. Pre-flight health evaluation
    health_engine = HealthCheckEngine(config=prod_config)
    report = health_engine.run_health_check()
    print_health_report(report)

    if args.setup_only or args.check_only:
        return 0 if report.is_operational() else 1

    if report.overall_status == ComponentStatus.BLOCKED:
        print("\n[BLOCKED] Core dependencies or database layers failed health check.")
        print("Please review logs and ensure SQLite and required directories are accessible.")
        return 1

    # 5. Safe UI Launch
    return launch_streamlit_app(
        port=args.port,
        host=args.host,
        headless=args.headless,
        offline=args.offline,
    )


if __name__ == "__main__":
    sys.exit(main())
