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
from agent.tool_metadata import ParameterSpec, RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, create_default_registry, default_tool_registry

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
]


