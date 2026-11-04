"""WinFix AI Agent and Safety Framework.

Provides centralized tool registration, strict safety policies, risk classification,
LLM planning integration, domain diagnostic orchestrators, and verified repair workflows.
"""

from agent.agent_response import (
    AgentResponse,
    FORBIDDEN_EXECUTION_KEYS,
    ToolRequest,
    extract_json_from_text,
    parse_agent_response,
)
from agent.application_crash_diagnostics import (
    ApplicationCrashDiagnosis,
    ApplicationCrashDiagnosticsOrchestrator,
    CRASH_CATEGORIES,
    default_application_crash_orchestrator,
)
from agent.bluetooth_diagnostics import (
    BLUETOOTH_CATEGORIES,
    BluetoothDiagnosis,
    BluetoothDiagnosticsOrchestrator,
)
from agent.bluetooth_repairs_orchestrator import (
    BluetoothRepairExecutionResult,
    BluetoothRepairProposal,
    BluetoothRepairsOrchestrator,
)
from agent.defender_diagnostics import (
    DEFENDER_CATEGORIES,
    DefenderDiagnosis,
    DefenderDiagnosticsOrchestrator,
)
from agent.defender_repairs_orchestrator import (
    DefenderRepairExecutionResult,
    DefenderRepairProposal,
    DefenderRepairsOrchestrator,
)
from agent.network_diagnostics import (
    NETWORK_CATEGORIES,
    NetworkDiagnosis,
    NetworkDiagnosticsOrchestrator,
    default_network_orchestrator,
    sanitize_hostname_target,
)

from agent.network_repairs_orchestrator import (
    NetworkRepairsOrchestrator,
    RepairExecutionResult,
    RepairProposal,
    default_network_repairs_orchestrator,
)
from agent.performance_diagnostics import (
    PERFORMANCE_CATEGORIES,
    PerformanceDiagnosis,
    PerformanceDiagnosticsOrchestrator,
    default_performance_orchestrator,
)
from agent.performance_repairs_orchestrator import (
    PerformanceRepairExecutionResult,
    PerformanceRepairProposal,
    PerformanceRepairsOrchestrator,
    default_performance_repairs_orchestrator,
)
from agent.planner import AgentPlanner, default_agent_planner
from agent.safety import SafetyDecision, SafetyEngine, default_safety_engine
from agent.service_diagnostics import (
    ServiceDiagnosis,
    ServiceDiagnosticsOrchestrator,
)
from agent.service_repairs_orchestrator import (
    ServiceRepairExecutionResult,
    ServiceRepairProposal,
    ServiceRepairsOrchestrator,
)
from agent.storage_diagnostics import (
    STORAGE_CATEGORIES,
    StorageDiagnosis,
    StorageDiagnosticsOrchestrator,
    default_storage_orchestrator,
)
from agent.storage_repairs_orchestrator import (
    StorageRepairExecutionResult,
    StorageRepairProposal,
    StorageRepairsOrchestrator,
    default_storage_repairs_orchestrator,
)
from agent.windows_update_diagnostics import (
    WINDOWS_UPDATE_CATEGORIES,
    WindowsUpdateDiagnosis,
    WindowsUpdateDiagnosticsOrchestrator,
)
from agent.windows_update_repairs_orchestrator import (
    WindowsUpdateRepairExecutionResult,
    WindowsUpdateRepairProposal,
    WindowsUpdateRepairsOrchestrator,
)

from agent.screenshot_diagnostics import (
    ScreenshotDiagnosticMapper,
    default_screenshot_mapper,
)
from agent.multimodal_adapter import (
    MultimodalEvidenceAdapter,
    default_multimodal_adapter,
)
from agent.evidence_models import (
    EvidenceItem,
    EvidenceNormalizer,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
    default_evidence_store,
)
from agent.diagnostic_models import (
    DiagnosticHypothesis,
    DiagnosticPlan,
    DiagnosticPlanStep,
    DiagnosticResponse,
    HypothesisStatus,
)
from agent.diagnostic_engine import (
    AIDiagnosticEngine,
    default_diagnostic_engine,
)

__all__ = [
    "RiskLevel",
    "ParameterSpec",
    "ToolDefinition",
    "ToolRegistry",
    "default_tool_registry",
    "create_default_registry",
    "SafetyDecision",
    "SafetyEngine",
    "default_safety_engine",
    "ToolRequest",
    "AgentResponse",
    "FORBIDDEN_EXECUTION_KEYS",
    "extract_json_from_text",
    "parse_agent_response",
    "AgentPlanner",
    "default_agent_planner",
    "NETWORK_CATEGORIES",
    "NetworkDiagnosis",
    "NetworkDiagnosticsOrchestrator",
    "default_network_orchestrator",
    "sanitize_hostname_target",
    "RepairProposal",
    "RepairExecutionResult",
    "NetworkRepairsOrchestrator",
    "default_network_repairs_orchestrator",
    "PERFORMANCE_CATEGORIES",
    "PerformanceDiagnosis",
    "PerformanceDiagnosticsOrchestrator",
    "default_performance_orchestrator",
    "PerformanceRepairProposal",
    "PerformanceRepairExecutionResult",
    "PerformanceRepairsOrchestrator",
    "default_performance_repairs_orchestrator",
    "STORAGE_CATEGORIES",
    "StorageDiagnosis",
    "StorageDiagnosticsOrchestrator",
    "default_storage_orchestrator",
    "StorageRepairProposal",
    "StorageRepairExecutionResult",
    "StorageRepairsOrchestrator",
    "default_storage_repairs_orchestrator",
    "ServiceDiagnosis",
    "ServiceDiagnosticsOrchestrator",
    "ServiceRepairProposal",
    "ServiceRepairExecutionResult",
    "ServiceRepairsOrchestrator",
    "BLUETOOTH_CATEGORIES",
    "BluetoothDiagnosis",
    "BluetoothDiagnosticsOrchestrator",
    "BluetoothRepairProposal",
    "BluetoothRepairExecutionResult",
    "BluetoothRepairsOrchestrator",
    "WINDOWS_UPDATE_CATEGORIES",
    "WindowsUpdateDiagnosis",
    "WindowsUpdateDiagnosticsOrchestrator",
    "WindowsUpdateRepairProposal",
    "WindowsUpdateRepairExecutionResult",
    "WindowsUpdateRepairsOrchestrator",
    "DEFENDER_CATEGORIES",
    "DefenderDiagnosis",
    "DefenderDiagnosticsOrchestrator",
    "DefenderRepairProposal",
    "DefenderRepairExecutionResult",
    "DefenderRepairsOrchestrator",
    "CRASH_CATEGORIES",
    "ApplicationCrashDiagnosis",
    "ApplicationCrashDiagnosticsOrchestrator",
    "default_application_crash_orchestrator",
    "ScreenshotDiagnosticMapper",
    "default_screenshot_mapper",
    "VoiceDiagnosticMapper",
    "VoiceDiagnosticOrchestrator",
    "default_voice_orchestrator",
    "EvidenceType",
    "EvidenceStatus",
    "EvidenceSource",
    "EvidenceQuality",
    "EvidenceItem",
    "EvidenceNormalizer",
    "EvidenceStore",
    "default_evidence_store",
    "MultimodalEvidenceAdapter",
    "default_multimodal_adapter",
    "HypothesisStatus",
    "DiagnosticHypothesis",
    "DiagnosticPlanStep",
    "DiagnosticPlan",
    "DiagnosticResponse",
    "AIDiagnosticEngine",
    "default_diagnostic_engine",
    "WorkflowStatus",
    "StepType",
    "ResolutionStatus",
    "RepairCandidate",
    "WorkflowStep",
    "TroubleshootingWorkflow",
    "VALID_WORKFLOW_TRANSITIONS",
    "PreconditionEngine",
    "RepairCandidateValidator",
    "DeterministicResolutionEngine",
    "TroubleshootingWorkflowEngine",
    "default_workflow_engine",
    "TroubleshootingDomain",
    "FailureCategory",
    "DomainClassification",
    "EvidenceCorrelationResult",
    "DomainMetadata",
    "DomainRegistry",
    "default_domain_registry",
    "EvidenceCorrelator",
    "default_evidence_correlator",
    "TroubleshootingStrategy",
    "StrategyRegistry",
    "default_strategy_registry",
    "WorkflowTemplate",
    "WorkflowTemplateValidator",
    "VerificationRule",
    "VerificationRegistry",
    "default_verification_registry",
    # Phase 30 Exports
    "AdaptiveState",
    "EvidenceChangeType",
    "ResolutionOutcome",
    "EvidenceChange",
    "HypothesisTransition",
    "DiagnosticDecision",
    "BeforeAfterComparison",
    "ResolutionAnalysis",
    "AdaptiveSessionContext",
    "EvidenceEvolutionTracker",
    "ResolutionAnalyzer",
    "AdaptiveDiagnosticEngine",
    "ScenarioDefinition",
    "ScenarioExecutionResult",
    "FakeWindowsEnvironment",
    "ScenarioRunner",
    "SubsystemStatus",
    "SubsystemCheckResult",
    "RealWindowsValidator",
    # Phase 31 Exports
    "RecoveryState",
    "RecoveryEventType",
    "ResumeAction",
    "Checkpoint",
    "ExecutionRecord",
    "RecoveryEvent",
    "ResumeDecision",
    "RecoveryResult",
    "IdempotencyStatus",
    "IdempotencyEngine",
    "CheckpointManager",
    "ResumeEngine",
    "RecoveryManager",
    "default_recovery_manager",
]

from agent.workflow_models import (
    RepairCandidate,
    ResolutionStatus,
    StepType,
    TroubleshootingWorkflow,
    VALID_WORKFLOW_TRANSITIONS,
    WorkflowStatus,
    WorkflowStep,
)
from agent.workflow_engine import (
    DeterministicResolutionEngine,
    PreconditionEngine,
    RepairCandidateValidator,
    TroubleshootingWorkflowEngine,
    default_workflow_engine,
)
from agent.domain_models import (
    DomainClassification,
    EvidenceCorrelationResult,
    FailureCategory,
    TroubleshootingDomain,
)
from agent.domain_registry import (
    DomainMetadata,
    DomainRegistry,
    default_domain_registry,
)
from agent.evidence_correlator import (
    EvidenceCorrelator,
    default_evidence_correlator,
)
from agent.troubleshooting_strategies import (
    StrategyRegistry,
    TroubleshootingStrategy,
    default_strategy_registry,
)
from agent.workflow_templates import (
    WorkflowTemplate,
    WorkflowTemplateRegistry,
    WorkflowTemplateValidator,
    default_template_registry,
)
from agent.verification_registry import (
    VerificationRegistry,
    VerificationRule,
    default_verification_registry,
)
from agent.adaptive_models import (
    AdaptiveSessionContext,
    AdaptiveState,
    BeforeAfterComparison,
    DiagnosticDecision,
    EvidenceChange,
    EvidenceChangeType,
    HypothesisTransition,
    ResolutionAnalysis,
    ResolutionOutcome,
)
from agent.evidence_evolution import EvidenceEvolutionTracker
from agent.resolution_analyzer import ResolutionAnalyzer
from agent.adaptive_engine import AdaptiveDiagnosticEngine
from agent.scenario_models import (
    ScenarioDefinition,
    ScenarioExecutionResult,
)
from agent.scenario_runner import (
    FakeWindowsEnvironment,
    ScenarioRunner,
)
from agent.real_windows_validator import (
    RealWindowsValidator,
    SubsystemCheckResult,
    SubsystemStatus,
)
from agent.recovery_models import (
    Checkpoint,
    ExecutionRecord,
    RecoveryEvent,
    RecoveryEventType,
    RecoveryResult,
    RecoveryState,
    ResumeAction,
    ResumeDecision,
)
from agent.idempotency import (
    IdempotencyEngine,
    IdempotencyStatus,
)
from agent.checkpoint_manager import CheckpointManager
from agent.resume_engine import ResumeEngine
from agent.recovery_manager import (
    RecoveryManager,
    default_recovery_manager,
)
from agent.evaluation_models import (
    EvaluationOutcome,
    EvaluationScenario,
    ScenarioEvaluationResult,
    EvaluationSummary,
)
from agent.evaluation_dataset import get_evaluation_dataset
from agent.evaluation_engine import EvaluationEngine
from agent.evaluation_runner import EvaluationRunner
from agent.evaluation_report import EvaluationReportGenerator
from agent.multimodal_adapter import (
    MultimodalEvidenceAdapter,
    default_multimodal_adapter,
)
from modes.tutor_models import (
    ProblemInput,
    StructuredProblem,
    TutorStep,
    TroubleshootingResponse,
)

