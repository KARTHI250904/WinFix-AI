"""
WinFix AI — First-Run Idempotent Setup Runner (Phase 22).

Coordinates first-run initialization:
1. Application directory structure creation and write verification.
2. SQLite schema creation and index verification.
3. Seed knowledge initialization (idempotent, transactional).
4. System & Model readiness evaluation via HealthCheckEngine.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Dict, Optional

from production.config import ProductionConfig, prod_config
from production.health_check import ComponentStatus, HealthCheckEngine, StartupHealthReport
from production.paths import initialize_app_directories

logger = logging.getLogger("winfix.STARTUP")


@dataclass
class FirstRunResult:
    """Outcome of first-run initialization."""

    success: bool
    is_first_run: bool
    directories_created: bool
    database_initialized: bool
    knowledge_seeded: bool
    seed_count: int
    health_report: StartupHealthReport
    message: str


def is_first_run(config: Optional[ProductionConfig] = None) -> bool:
    """
    Determine if this is the first execution on the current environment.
    Checks for the presence of the SQLite database file and setup marker.
    """
    cfg = config or prod_config
    db_file = Path(cfg.paths.database_path)
    marker_file = Path(cfg.paths.config_dir) / ".initialized"

    if not db_file.exists() or not marker_file.exists():
        return True
    return False


def run_first_time_setup(
    config: Optional[ProductionConfig] = None,
    force: bool = False,
) -> FirstRunResult:
    """
    Execute idempotent first-time setup for WinFix AI.
    
    Safe to run repeatedly; never duplicates records or drops existing user audit data.
    """
    cfg = config or prod_config
    first_run = is_first_run(cfg) or force
    logger.info(f"Starting setup flow (first_run={first_run}, force={force})")

    # 1. Initialize Directories
    dir_results = initialize_app_directories(cfg.paths)
    all_dirs_ok = all(dir_results.values())
    if not all_dirs_ok:
        failed = [k for k, v in dir_results.items() if not v]
        err_msg = f"Failed to create application directories: {', '.join(failed)}"
        logger.error(err_msg)
        return FirstRunResult(
            success=False,
            is_first_run=first_run,
            directories_created=False,
            database_initialized=False,
            knowledge_seeded=False,
            seed_count=0,
            health_report=HealthCheckEngine(config=cfg).run_health_check(),
            message=err_msg,
        )

    # 2. Initialize SQLite Database Schema
    from database.db import DatabaseManager
    db_mgr = DatabaseManager(db_path=cfg.paths.database_path)
    try:
        db_mgr.init_db()
        db_initialized = True
    except Exception as e:
        err_msg = f"SQLite schema initialization error: {e}"
        logger.error(err_msg)
        return FirstRunResult(
            success=False,
            is_first_run=first_run,
            directories_created=True,
            database_initialized=False,
            knowledge_seeded=False,
            seed_count=0,
            health_report=HealthCheckEngine(config=cfg, db_manager=db_mgr).run_health_check(),
            message=err_msg,
        )

    # 3. Seed Knowledge Base (Idempotent seed_default_knowledge)
    try:
        from database.knowledge_repository import KnowledgeRepository
        from knowledge.seed_data import seed_default_knowledge
        repo = KnowledgeRepository(db_mgr)
        seed_res = seed_default_knowledge(repo)
        seed_count = seed_res.get("article_count", 0) if seed_res.get("success") else 0
        knowledge_ok = seed_res.get("success", False)
        logger.info(f"Knowledge repository seeded ({seed_count} articles verified)")
    except Exception as e:
        err_msg = f"Seed knowledge population error: {e}"
        logger.error(err_msg)
        return FirstRunResult(
            success=False,
            is_first_run=first_run,
            directories_created=True,
            database_initialized=True,
            knowledge_seeded=False,
            seed_count=0,
            health_report=HealthCheckEngine(config=cfg, db_manager=db_mgr).run_health_check(),
            message=err_msg,
        )

    # 4. Write Initialization Marker
    try:
        marker_file = Path(cfg.paths.config_dir) / ".initialized"
        marker_file.write_text(f"version={cfg.app_version}\ninitialized=true\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to write setup marker: {e}")

    # 5. Run Health Check
    health_engine = HealthCheckEngine(config=cfg, db_manager=db_mgr)
    report = health_engine.run_health_check()

    overall_success = report.is_operational()
    summary_msg = (
        "WinFix AI is ready for operation."
        if report.overall_status == ComponentStatus.READY
        else "WinFix AI is ready in DEGRADED mode (some optional AI components unavailable)."
        if report.overall_status == ComponentStatus.DEGRADED
        else "WinFix AI initialization BLOCKED. Check logs for details."
    )

    return FirstRunResult(
        success=overall_success,
        is_first_run=first_run,
        directories_created=all_dirs_ok,
        database_initialized=db_initialized,
        knowledge_seeded=knowledge_ok,
        seed_count=seed_count,
        health_report=report,
        message=summary_msg,
    )
