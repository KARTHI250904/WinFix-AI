"""WinFix AI — Workflow Templates & Template Validation (Phase 29).

Provides validated, structured workflow templates for known Windows issue categories.
Strictly adheres to:
  Templates != Authorization
  No executable shell commands in templates
  All referenced tools must exist in approved ToolRegistry
  Step limit bounded to <= 8 steps
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from agent.domain_models import TroubleshootingDomain
from agent.domain_registry import DomainRegistry, default_domain_registry
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from agent.workflow_models import (
    RepairCandidate,
    StepType,
    TroubleshootingWorkflow,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger("winfix.WORKFLOW_TEMPLATES")


@dataclass(frozen=True)
class WorkflowTemplate:
    """Pre-validated, deterministic workflow template."""

    template_id: str
    domain: TroubleshootingDomain
    title: str
    description: str
    diagnostic_tools: List[str]
    repair_tool: Optional[str] = None
    repair_arguments: Dict[str, Any] = field(default_factory=dict)
    repair_purpose: str = ""
    verification_tool: str = ""
    max_steps: int = 8

    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary."""
        return {
            "template_id": self.template_id,
            "domain": self.domain.value if isinstance(self.domain, TroubleshootingDomain) else str(self.domain),
            "title": self.title,
            "description": self.description,
            "diagnostic_tools": list(self.diagnostic_tools),
            "repair_tool": self.repair_tool,
            "repair_arguments": dict(self.repair_arguments),
            "repair_purpose": self.repair_purpose,
            "verification_tool": self.verification_tool,
            "max_steps": self.max_steps,
        }


class WorkflowTemplateValidator:
    """Strict security and invariant validator for workflow templates."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        domain_registry: Optional[DomainRegistry] = None,
    ) -> None:
        self.tool_registry = tool_registry or default_tool_registry
        self.domain_registry = domain_registry or default_domain_registry

    def validate(self, template: WorkflowTemplate) -> Tuple[bool, str]:
        """Validate template against all safety rules and tool registries."""
        # 1. Domain existence
        if template.domain not in self.domain_registry.list_domains():
            return False, f"Domain '{template.domain}' is not registered in DomainRegistry"

        # 2. Diagnostic tools must exist and be SAFE
        if not template.diagnostic_tools:
            return False, "Template must define at least one diagnostic tool"

        for tool_name in template.diagnostic_tools:
            tool_def = self.tool_registry.get(tool_name)
            if not tool_def:
                return False, f"Diagnostic tool '{tool_name}' does not exist in ToolRegistry"
            if tool_def.risk != RiskLevel.SAFE:
                return False, f"Diagnostic tool '{tool_name}' must be SAFE"

        # 3. Repair tool validation if present
        if template.repair_tool:
            repair_def = self.tool_registry.get(template.repair_tool)
            if not repair_def:
                return False, f"Repair tool '{template.repair_tool}' does not exist in ToolRegistry"
            if repair_def.risk == RiskLevel.HIGH:
                return False, "HIGH risk tools cannot be referenced in workflow templates"

            # Must have a valid SAFE verification tool
            if not template.verification_tool:
                return False, f"Repair tool '{template.repair_tool}' requires a designated verification tool"
            
            v_def = self.tool_registry.get(template.verification_tool)
            if not v_def:
                return False, f"Verification tool '{template.verification_tool}' does not exist in ToolRegistry"
            if v_def.risk != RiskLevel.SAFE:
                return False, f"Verification tool '{template.verification_tool}' must be SAFE"

        # 4. Step limit check
        total_steps = len(template.diagnostic_tools) + (2 if template.repair_tool else 0) + 2  # precond + complete
        if total_steps > template.max_steps or total_steps > 8:
            return False, f"Total step count ({total_steps}) exceeds maximum bound of 8"

        return True, "Template valid"


class WorkflowTemplateRegistry:
    """Registry of pre-approved workflow templates."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        domain_registry: Optional[DomainRegistry] = None,
    ) -> None:
        self.tool_registry = tool_registry or default_tool_registry
        self.domain_registry = domain_registry or default_domain_registry
        self.validator = WorkflowTemplateValidator(self.tool_registry, self.domain_registry)
        self._templates: Dict[str, WorkflowTemplate] = {}
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Register built-in workflow templates for standard Windows troubleshooting paths."""
        templates = [
            WorkflowTemplate(
                template_id="DNS_FAILURE",
                domain=TroubleshootingDomain.NETWORK,
                title="DNS Resolution Troubleshooting",
                description="Diagnoses DNS failure and provides verified DNS resolver cache clearing.",
                diagnostic_tools=["get_network_adapters_diagnostics", "check_dns_resolution"],
                repair_tool="flush_dns_cache",
                repair_purpose="Flush stale DNS resolver cache",
                verification_tool="check_dns_resolution",
            ),
            WorkflowTemplate(
                template_id="DHCP_FAILURE",
                domain=TroubleshootingDomain.NETWORK,
                title="DHCP Configuration & Gateway Troubleshooting",
                description="Diagnoses missing IP configuration and renews DHCP lease.",
                diagnostic_tools=["get_network_adapters_diagnostics", "check_internet_connectivity"],
                repair_tool="renew_dhcp_lease",
                repair_purpose="Renew local DHCP IP lease",
                verification_tool="check_internet_connectivity",
            ),
            WorkflowTemplate(
                template_id="SERVICE_FAILURE",
                domain=TroubleshootingDomain.SERVICES,
                title="Windows Service Recovery",
                description="Inspects service status and executes verified service restart.",
                diagnostic_tools=["get_service_status", "get_services_diagnostics"],
                repair_tool="restart_service",
                repair_arguments={"service_name": "wuauserv"},
                repair_purpose="Restart stalled Windows service",
                verification_tool="get_service_status",
            ),
            WorkflowTemplate(
                template_id="STORAGE_CLEANUP",
                domain=TroubleshootingDomain.STORAGE,
                title="Disk Cleanup & Temporary Files",
                description="Inspects volume free space and cleans obsolete temporary files.",
                diagnostic_tools=["get_storage_diagnostics", "get_temp_storage_info"],
                repair_tool="clean_user_temp_cache",
                repair_purpose="Purge temporary files from user temp directory",
                verification_tool="get_storage_diagnostics",
            ),
            WorkflowTemplate(
                template_id="WINDOWS_UPDATE",
                domain=TroubleshootingDomain.WINDOWS_UPDATE,
                title="Windows Update Recovery",
                description="Diagnoses failed updates and restarts Windows Update service.",
                diagnostic_tools=["get_windows_update_diagnostics", "get_windows_update_history"],
                repair_tool="restart_windows_update_service",
                repair_purpose="Restart Windows Update background service",
                verification_tool="get_windows_update_diagnostics",
            ),
            WorkflowTemplate(
                template_id="WINDOWS_DEFENDER",
                domain=TroubleshootingDomain.WINDOWS_DEFENDER,
                title="Windows Defender Status & Service Recovery",
                description="Checks antivirus state and restarts Defender background service if stalled.",
                diagnostic_tools=["get_defender_diagnostics", "get_defender_antivirus_status"],
                repair_tool="restart_defender_service",
                repair_purpose="Restart Windows Defender background service",
                verification_tool="get_defender_diagnostics",
            ),
            WorkflowTemplate(
                template_id="BLUETOOTH",
                domain=TroubleshootingDomain.BLUETOOTH,
                title="Bluetooth Peripheral Recovery",
                description="Diagnoses Bluetooth radio presence and restarts Bluetooth service.",
                diagnostic_tools=["get_bluetooth_diagnostics", "get_bluetooth_devices"],
                repair_tool="restart_bluetooth_service",
                repair_purpose="Restart Windows Bluetooth Support Service",
                verification_tool="get_bluetooth_diagnostics",
            ),
            WorkflowTemplate(
                template_id="PERFORMANCE",
                domain=TroubleshootingDomain.PERFORMANCE,
                title="Performance & Resource Analysis",
                description="Read-only analysis of CPU, memory, and disk consumption bottlenecks.",
                diagnostic_tools=["get_top_cpu_processes", "get_top_memory_processes"],
            ),
            WorkflowTemplate(
                template_id="APPLICATION_CRASH",
                domain=TroubleshootingDomain.APPLICATION_CRASH,
                title="Application Fault Diagnostics",
                description="Read-only extraction and analysis of application crash logs and Event Log errors.",
                diagnostic_tools=["get_application_crash_diagnostics", "get_recent_application_crashes"],
            ),
            WorkflowTemplate(
                template_id="SYSTEM",
                domain=TroubleshootingDomain.SYSTEM,
                title="System OS Telemetry & Diagnostics",
                description="Read-only inspection of Windows OS build, uptime, and system status.",
                diagnostic_tools=["get_complete_system_info", "get_resource_snapshot"],
            ),
        ]

        for t in templates:
            ok, msg = self.validator.validate(t)
            if ok:
                self.register(t)
            else:
                logger.warning(f"Failed to register template '{t.template_id}': {msg}")

    def register(self, template: WorkflowTemplate) -> None:
        """Register a pre-validated template."""
        self._templates[template.template_id] = template

    def get(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Retrieve a template by ID."""
        return self._templates.get(template_id)

    def instantiate_workflow(
        self,
        template_id: str,
        session_id: str = "default_session",
    ) -> Optional[TroubleshootingWorkflow]:
        """Instantiate a bounded Phase 28 TroubleshootingWorkflow from a template."""
        template = self.get(template_id)
        if not template:
            return None

        workflow_id = f"wf_tmpl_{uuid.uuid4().hex[:8]}"
        steps: List[WorkflowStep] = []
        seq = 1

        # Diagnostic steps
        for dt in template.diagnostic_tools:
            steps.append(
                WorkflowStep(
                    step_id=seq,
                    workflow_id=workflow_id,
                    sequence=seq,
                    step_type=StepType.DIAGNOSE,
                    purpose=f"Execute diagnostic {dt}",
                    tool_name=dt,
                    authorization_required=False,
                )
            )
            seq += 1

        # Precondition step
        steps.append(
            WorkflowStep(
                step_id=seq,
                workflow_id=workflow_id,
                sequence=seq,
                step_type=StepType.VERIFY_PRECONDITION,
                purpose="Verify safety preconditions and environment stability",
            )
        )
        seq += 1

        repair_candidate = None
        if template.repair_tool:
            repair_def = self.tool_registry.get(template.repair_tool)
            risk = repair_def.risk.value if repair_def else "MEDIUM"
            repair_candidate = RepairCandidate(
                candidate_id=f"cand_{uuid.uuid4().hex[:8]}",
                diagnosis_id="",
                tool_name=template.repair_tool,
                purpose=template.repair_purpose,
                verification_method=template.verification_tool,
                risk_level=risk,
                authorization_required=(risk == "MEDIUM"),
                arguments=dict(template.repair_arguments),
                session_id=session_id,
                workflow_id=workflow_id,
            )
            steps.append(
                WorkflowStep(
                    step_id=seq,
                    workflow_id=workflow_id,
                    sequence=seq,
                    step_type=StepType.REPAIR,
                    purpose=template.repair_purpose,
                    tool_name=template.repair_tool,
                    arguments=dict(template.repair_arguments),
                    authorization_required=(risk == "MEDIUM"),
                    verification_required=True,
                )
            )
            seq += 1

            if template.verification_tool:
                steps.append(
                    WorkflowStep(
                        step_id=seq,
                        workflow_id=workflow_id,
                        sequence=seq,
                        step_type=StepType.VERIFY_REPAIR,
                        purpose=f"Deterministically verify resolution via {template.verification_tool}",
                        tool_name=template.verification_tool,
                    )
                )
                seq += 1

        # Complete step
        steps.append(
            WorkflowStep(
                step_id=seq,
                workflow_id=workflow_id,
                sequence=seq,
                step_type=StepType.COMPLETE,
                purpose="Finalize resolution assessment",
            )
        )

        return TroubleshootingWorkflow(
            workflow_id=workflow_id,
            session_id=session_id,
            problem_category=template.domain.value,
            title=template.title,
            description=template.description,
            steps=steps[:8],
            current_step=0,
            max_steps=8,
            status=WorkflowStatus.CREATED,
            repair_candidate=repair_candidate,
        )


default_template_registry = WorkflowTemplateRegistry()
