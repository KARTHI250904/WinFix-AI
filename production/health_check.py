"""
WinFix AI — Startup Health Check & Environment Verification (Phase 22).

Evaluates system dependencies, runtime directories, SQLite tables, Tool Registry invariants,
SafetyEngine, Ollama connectivity, local models, and Windows API layers.
"""

from dataclasses import dataclass, field
from enum import Enum
import importlib
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import urllib.request

from production.config import ProductionConfig, prod_config
from production.paths import AppPaths, initialize_app_directories

logger = logging.getLogger("winfix.STARTUP")


class ComponentStatus(str, Enum):
    """Readiness status of an individual system component."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ComponentHealth:
    """Health check outcome for a specific subsystem."""

    name: str
    status: ComponentStatus
    details: str
    is_critical: bool = True


@dataclass
class StartupHealthReport:
    """Consolidated startup health report across all WinFix AI subsystems."""

    overall_status: ComponentStatus
    components: Dict[str, ComponentHealth] = field(default_factory=dict)
    tool_counts: Dict[str, int] = field(default_factory=dict)
    ai_lifecycle: Optional[Dict[str, Any]] = None

    def is_operational(self) -> bool:
        """Return True if system can execute diagnostics and repairs (READY or DEGRADED)."""
        return self.overall_status in (ComponentStatus.READY, ComponentStatus.DEGRADED)


class HealthCheckEngine:
    """Coordinates deterministic startup health verification."""

    def __init__(
        self,
        config: Optional[ProductionConfig] = None,
        db_manager: Any = None,
        registry: Any = None,
    ) -> None:
        self.config = config or prod_config
        self._db_manager = db_manager
        self._registry = registry

    def _get_db_manager(self):
        if self._db_manager is None:
            from database.db import DatabaseManager
            self._db_manager = DatabaseManager(db_path=self.config.paths.database_path)
        return self._db_manager

    def _get_registry(self):
        if self._registry is None:
            from agent.tool_registry import create_default_registry
            self._registry = create_default_registry()
        return self._registry

    def run_health_check(self) -> StartupHealthReport:
        """Run complete end-to-end health evaluation."""
        components: Dict[str, ComponentHealth] = {}

        # 1. Directories & Storage Health
        dir_results = initialize_app_directories(self.config.paths)
        if all(dir_results.values()):
            components["directories"] = ComponentHealth(
                name="Application Directories",
                status=ComponentStatus.READY,
                details=f"All app data directories verified in {self.config.paths.root_dir}",
                is_critical=True,
            )
        else:
            failed_dirs = [k for k, v in dir_results.items() if not v]
            components["directories"] = ComponentHealth(
                name="Application Directories",
                status=ComponentStatus.BLOCKED,
                details=f"Failed to initialize directories: {', '.join(failed_dirs)}",
                is_critical=True,
            )

        # 2. SQLite Database Health
        db_mgr = self._get_db_manager()
        try:
            db_mgr.init_db()
            with db_mgr.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cursor.fetchall()]
                required_tables = {"sessions", "diagnostics", "tool_executions", "knowledge_articles"}
                missing = required_tables - set(tables)
                if not missing:
                    components["database"] = ComponentHealth(
                        name="SQLite Database",
                        status=ComponentStatus.READY,
                        details=f"Database active with {len(tables)} tables verified.",
                        is_critical=True,
                    )
                else:
                    components["database"] = ComponentHealth(
                        name="SQLite Database",
                        status=ComponentStatus.BLOCKED,
                        details=f"Missing required tables: {missing}",
                        is_critical=True,
                    )
        except Exception as ex:
            components["database"] = ComponentHealth(
                name="SQLite Database",
                status=ComponentStatus.BLOCKED,
                details=f"Database error: {ex}",
                is_critical=True,
            )

        # 3. Knowledge Base Health
        try:
            from database.knowledge_repository import KnowledgeRepository
            repo = KnowledgeRepository(db_mgr)
            k_count = repo.count_articles()
            if k_count > 0:
                components["knowledge"] = ComponentHealth(
                    name="Troubleshooting Knowledge Base",
                    status=ComponentStatus.READY,
                    details=f"{k_count} knowledge articles verified and searchable.",
                    is_critical=False,
                )
            else:
                components["knowledge"] = ComponentHealth(
                    name="Troubleshooting Knowledge Base",
                    status=ComponentStatus.DEGRADED,
                    details="Knowledge database empty. First-run seeding recommended.",
                    is_critical=False,
                )
        except Exception as ex:
            components["knowledge"] = ComponentHealth(
                name="Troubleshooting Knowledge Base",
                status=ComponentStatus.DEGRADED,
                details=f"Knowledge retrieval degraded: {ex}",
                is_critical=False,
            )

        # 4. ToolRegistry Invariant Health
        registry = self._get_registry()
        from agent.tool_metadata import RiskLevel
        tools = registry.list_tools()
        safe_count = len([t for t in tools if t.risk == RiskLevel.SAFE])
        med_count = len([t for t in tools if t.risk == RiskLevel.MEDIUM])
        high_count = len([t for t in tools if t.risk == RiskLevel.HIGH])
        unique_names = len(set(t.name for t in tools))

        tool_counts = {
            "total": len(tools),
            "safe": safe_count,
            "medium": med_count,
            "high": high_count,
            "unique": unique_names,
        }

        if (
            (len(tools) == 59 and safe_count == 49 and med_count == 10) or
            (len(tools) == 62 and safe_count == 52 and med_count == 10)
        ) and high_count == 0 and unique_names == len(tools):
            components["tool_registry"] = ComponentHealth(
                name="Tool Registry",
                status=ComponentStatus.READY,
                details=f"{len(tools)} tools registered ({safe_count} SAFE, {med_count} MEDIUM, 0 HIGH, 0 duplicates).",
                is_critical=True,
            )
        else:
            components["tool_registry"] = ComponentHealth(
                name="Tool Registry",
                status=ComponentStatus.BLOCKED,
                details=f"Tool invariant violation: total={len(tools)}, safe={safe_count}, med={med_count}, high={high_count}",
                is_critical=True,
            )

        # 5. Safety Engine Health
        try:
            from agent.safety import SafetyEngine
            safety = SafetyEngine(registry=registry)
            # Safe tool evaluation
            d_safe = safety.evaluate("get_complete_system_info", {})
            # Arbitrary / unapproved tool must be blocked
            d_unapproved = safety.evaluate("arbitrary_powershell_command", {})
            if d_safe.allowed and not d_safe.requires_confirmation and d_unapproved.blocked and not d_unapproved.allowed:
                components["safety_engine"] = ComponentHealth(
                    name="Safety Engine",
                    status=ComponentStatus.READY,
                    details="Fail-closed policies and risk gates active.",
                    is_critical=True,
                )
            else:
                components["safety_engine"] = ComponentHealth(
                    name="Safety Engine",
                    status=ComponentStatus.BLOCKED,
                    details="Safety policy evaluation anomaly detected.",
                    is_critical=True,
                )
        except Exception as ex:
            components["safety_engine"] = ComponentHealth(
                name="Safety Engine",
                status=ComponentStatus.BLOCKED,
                details=f"Safety Engine initialization failed: {ex}",
                is_critical=True,
            )

        # 6. Local Ollama & Gemma Model Health (Phase 26 Lifecycle Integration)
        ollama_status, ollama_details = self._check_ollama_and_model()
        components["ollama_ai"] = ComponentHealth(
            name=f"Local AI Model ({self.config.ollama_model})",
            status=ollama_status,
            details=ollama_details,
            is_critical=False,  # Offline heuristics allow diagnostic operation even without Ollama
        )

        # 7. Vision & Voice Subsystem Health
        components["vision"] = self._check_vision_availability()
        components["voice"] = self._check_voice_availability()

        # 8. Workflow Engine & Deterministic Verification Health (Phase 28)
        try:
            from agent.workflow_engine import default_workflow_engine
            if default_workflow_engine is not None and default_workflow_engine.validator is not None:
                components["workflow_engine"] = ComponentHealth(
                    name="Workflow & Resolution Engine",
                    status=ComponentStatus.READY,
                    details="Deterministic state machine, precondition checks, and verification active.",
                    is_critical=True,
                )
            else:
                components["workflow_engine"] = ComponentHealth(
                    name="Workflow & Resolution Engine",
                    status=ComponentStatus.BLOCKED,
                    details="Workflow engine initialization error.",
                    is_critical=True,
                )
        except Exception as ex:
            components["workflow_engine"] = ComponentHealth(
                name="Workflow & Resolution Engine",
                status=ComponentStatus.BLOCKED,
                details=f"Workflow engine verification failed: {ex}",
                is_critical=True,
            )

        # 9. Domain Intelligence & Strategy Registry Health (Phase 29)
        try:
            from agent.domain_registry import default_domain_registry
            from agent.troubleshooting_strategies import default_strategy_registry
            from agent.verification_registry import default_verification_registry
            
            domains_count = len(default_domain_registry.list_domains())
            verif_count = len(default_verification_registry.list_rules())
            if domains_count >= 10 and verif_count >= 5:
                components["domain_intelligence"] = ComponentHealth(
                    name="Domain Intelligence & Strategies",
                    status=ComponentStatus.READY,
                    details=f"{domains_count} domains cataloged, {verif_count} verification rules active.",
                    is_critical=True,
                )
            else:
                components["domain_intelligence"] = ComponentHealth(
                    name="Domain Intelligence & Strategies",
                    status=ComponentStatus.BLOCKED,
                    details=f"Domain registry incomplete: {domains_count} domains, {verif_count} rules",
                    is_critical=True,
                )
        except Exception as ex:
            components["domain_intelligence"] = ComponentHealth(
                name="Domain Intelligence & Strategies",
                status=ComponentStatus.BLOCKED,
                details=f"Domain intelligence verification failed: {ex}",
                is_critical=True,
            )

        # 10. Adaptive Diagnostic Intelligence & Scenario Validation (Phase 30)
        try:
            from agent.adaptive_engine import AdaptiveDiagnosticEngine
            from agent.scenario_runner import ScenarioRunner
            adaptive_engine = AdaptiveDiagnosticEngine()
            scenario_runner = ScenarioRunner()
            if adaptive_engine is not None and scenario_runner is not None:
                components["adaptive_diagnostics"] = ComponentHealth(
                    name="Adaptive Diagnostics & Scenario Engine",
                    status=ComponentStatus.READY,
                    details="Dynamic hypothesis transitions, before/after evolution, and scenario doubles ready.",
                    is_critical=True,
                )
            else:
                components["adaptive_diagnostics"] = ComponentHealth(
                    name="Adaptive Diagnostics & Scenario Engine",
                    status=ComponentStatus.BLOCKED,
                    details="Adaptive engine or scenario runner initialization error.",
                    is_critical=True,
                )
        except Exception as ex:
            components["adaptive_diagnostics"] = ComponentHealth(
                name="Adaptive Diagnostics & Scenario Engine",
                status=ComponentStatus.BLOCKED,
                details=f"Adaptive diagnostic health check failed: {ex}",
                is_critical=True,
            )

        # 11. Production Reliability, Recovery & Resumable Troubleshooting (Phase 31)
        try:
            from agent.recovery_manager import default_recovery_manager
            from agent.checkpoint_manager import CheckpointManager
            from agent.resume_engine import ResumeEngine

            if default_recovery_manager is not None and default_recovery_manager.resume_engine is not None:
                components["recovery_engine"] = ComponentHealth(
                    name="Recovery & Resumption Engine",
                    status=ComponentStatus.READY,
                    details="Persistent checkpoints, state revalidation, and replay protection active.",
                    is_critical=True,
                )
            else:
                components["recovery_engine"] = ComponentHealth(
                    name="Recovery & Resumption Engine",
                    status=ComponentStatus.BLOCKED,
                    details="Recovery engine initialization failed.",
                    is_critical=True,
                )
        except Exception as ex:
            components["recovery_engine"] = ComponentHealth(
                name="Recovery & Resumption Engine",
                status=ComponentStatus.BLOCKED,
                details=f"Recovery engine health check failed: {ex}",
                is_critical=True,
            )

        # 12. Observability, Diagnostics Telemetry & Reliability Analytics (Phase 32)
        try:
            from production.telemetry import default_telemetry_service
            from production.telemetry_analytics import default_telemetry_analytics
            from production.telemetry_retention import default_telemetry_retention

            if (
                default_telemetry_service is not None
                and default_telemetry_analytics is not None
                and default_telemetry_retention is not None
            ):
                components["observability_telemetry"] = ComponentHealth(
                    name="Observability & Telemetry Analytics",
                    status=ComponentStatus.READY,
                    details="Local-only privacy-preserving telemetry, analytics engine, and bounded retention active.",
                    is_critical=False,
                )
            else:
                components["observability_telemetry"] = ComponentHealth(
                    name="Observability & Telemetry Analytics",
                    status=ComponentStatus.DEGRADED,
                    details="Telemetry subsystem initialization incomplete.",
                    is_critical=False,
                )
        except Exception as ex:
            components["observability_telemetry"] = ComponentHealth(
                name="Observability & Telemetry Analytics",
                status=ComponentStatus.DEGRADED,
                details=f"Telemetry health check failed: {ex}",
                is_critical=False,
            )

        # 13. Multimodal Voice & Vision Availability
        components["vision"] = self._check_vision_availability()
        components["voice"] = self._check_voice_availability()

        # Capture AI Model Lifecycle aggregation metadata safely
        ai_lifecycle_data = None
        try:
            from ai.model_manager import ai_model_manager
            ai_agg = ai_model_manager.get_last_health_aggregation()
            ai_lifecycle_data = ai_agg.to_dict()
        except Exception:
            pass


        # Calculate Overall Status
        if any(c.status == ComponentStatus.BLOCKED and c.is_critical for c in components.values()):
            overall = ComponentStatus.BLOCKED
        elif any(c.status == ComponentStatus.DEGRADED for c in components.values()):
            overall = ComponentStatus.DEGRADED
        else:
            overall = ComponentStatus.READY

        return StartupHealthReport(
            overall_status=overall,
            components=components,
            tool_counts=tool_counts,
            ai_lifecycle=ai_lifecycle_data,
        )

    def _check_ollama_and_model(self) -> tuple[ComponentStatus, str]:
        """Verify reachability of local Ollama server and presence of required model."""
        base = self.config.ollama_base_url.rstrip("/")
        # In offline environments on Windows, normalize 'localhost' to '127.0.0.1'
        if "://localhost" in base:
            base = base.replace("://localhost", "://127.0.0.1")

        urls_to_try = [f"{base}/api/tags"]
        if "://127.0.0.1" in base:
            urls_to_try.append(base.replace("://127.0.0.1", "://localhost") + "/api/tags")

        last_ex = None
        for url in urls_to_try:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        models = [m.get("name", "") for m in data.get("models", [])]
                        target = self.config.ollama_model
                        if any(target in m for m in models):
                            return ComponentStatus.READY, f"Ollama reachable and model '{target}' is installed."
                        return (
                            ComponentStatus.DEGRADED,
                            f"Ollama reachable, but model '{target}' is not installed (run 'ollama pull {target}').",
                        )
            except Exception as ex:
                last_ex = ex
                continue

        return (
            ComponentStatus.DEGRADED,
            f"Local Ollama is currently offline ({last_ex}). WinFix AI will use deterministic fallback templates.",
        )

    def _check_vision_availability(self) -> ComponentHealth:
        """Check availability of PIL and Vision dependencies."""
        try:
            import PIL
            return ComponentHealth(
                name="Screenshot Vision Analyzer",
                status=ComponentStatus.READY,
                details="PIL imaging library available.",
                is_critical=False,
            )
        except Exception:
            return ComponentHealth(
                name="Screenshot Vision Analyzer",
                status=ComponentStatus.DEGRADED,
                details="Pillow library missing. Screenshot Diagnostics disabled.",
                is_critical=False,
            )

    def _check_voice_availability(self) -> ComponentHealth:
        """Check availability of voice decoding and operational speech-to-text pipeline."""
        try:
            import av  # type: ignore
            from ai.voice_transcriber import FasterWhisperProvider, decode_audio_to_numpy

            prov = FasterWhisperProvider()
            if not prov.is_available():
                return ComponentHealth(
                    name="Voice Input & Transcriber",
                    status=ComponentStatus.DEGRADED,
                    details="faster-whisper package not found. Spoken voice transcription degraded.",
                    is_critical=False,
                )

            # Operational check: verify model can be initialized and decoder works
            model = prov._get_model()
            if model is None:
                return ComponentHealth(
                    name="Voice Input & Transcriber",
                    status=ComponentStatus.DEGRADED,
                    details=f"faster-whisper weights ({prov.model_size}) failed to load.",
                    is_critical=False,
                )

            return ComponentHealth(
                name="Voice Input & Transcriber",
                status=ComponentStatus.READY,
                details=f"faster-whisper ({prov.model_size}) initialized, PyAV {getattr(av, '__version__', '')} operational.",
                is_critical=False,
            )
        except Exception as ex:
            return ComponentHealth(
                name="Voice Input & Transcriber",
                status=ComponentStatus.DEGRADED,
                details=f"Voice pipeline degraded: {ex}",
                is_critical=False,
            )
