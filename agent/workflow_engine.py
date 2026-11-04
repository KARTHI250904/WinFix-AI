"""WinFix AI — Intelligent Troubleshooting Workflow Engine (Phase 28).

Coordinates bounded, deterministic, multi-step troubleshooting workflows.
Enforces strict security invariants:
  - LLM != Windows Shell
  - Diagnosis != Repair Authorization
  - Repair Candidate != Repair Authorization
  - Repair Execution != Success
  - Mandatory SafetyEngine & exact user confirmation for MEDIUM tools
  - Deterministic Before/After verification before declaring resolution
  - Immutable step limit (max 8) & no automatic retries for MEDIUM repairs
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid

from agent.agent_response import FORBIDDEN_EXECUTION_KEYS
from agent.diagnostic_models import DiagnosticHypothesis, DiagnosticResponse, HypothesisStatus
from agent.evidence_models import (
    EvidenceItem,
    EvidenceQuality,
    EvidenceSource,
    EvidenceStatus,
    EvidenceStore,
    EvidenceType,
    default_evidence_store,
)
from agent.safety import SafetyDecision, SafetyEngine, default_safety_engine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from agent.workflow_models import (
    RepairCandidate,
    ResolutionStatus,
    StepType,
    TroubleshootingWorkflow,
    VALID_WORKFLOW_TRANSITIONS,
    WorkflowStatus,
    WorkflowStep,
)
from production.performance import default_profiler

logger = logging.getLogger("winfix.WORKFLOW_ENGINE")

MAX_WORKFLOW_STEPS = 8
MAX_REPAIR_EXECUTIONS_PER_TOOL = 1
MAX_SAFE_DIAGNOSTIC_RETRIES = 1

# Known verification mappings: {repair_tool: verification_tool}
DEFAULT_VERIFICATION_MAP: Dict[str, str] = {
    "flush_dns_cache": "check_dns_resolution",
    "renew_dhcp_lease": "check_internet_connectivity",
    "restart_service": "get_service_status",
    "clean_user_temp_cache": "get_temp_storage_info",
    "restart_windows_update_service": "get_windows_update_service_status",
    "restart_bluetooth_service": "get_bluetooth_service_status",
    "restart_defender_service": "get_defender_service_status",
    "terminate_user_process": "get_cpu_diagnostics",
}


class PreconditionEngine:
    """Deterministic validation of preconditions before executing workflow steps."""

    @staticmethod
    def validate_preconditions(
        tool_name: str,
        arguments: Dict[str, Any],
        preconditions: Dict[str, Any],
        evidence_store: Optional[EvidenceStore] = None,
        session_id: str = "default_session",
    ) -> Tuple[bool, str]:
        """Verify deterministic preconditions for a candidate tool execution."""
        # 1. Check for any shell injection / forbidden keywords in arguments
        for k, v in arguments.items():
            str_v = str(v).lower()
            if any(forbidden in str_v for forbidden in ["cmd", "powershell", "subprocess", "bash", "sh", ";", "&&", "|", "`"]):
                return False, f"Prohibited injection pattern detected in argument '{k}'"

        # 2. Service restart precondition: Service name must be allowlisted alphanumeric
        if tool_name in ("restart_service", "start_service", "stop_service"):
            svc_name = arguments.get("service_name", "")
            if not svc_name or not re.match(r"^[A-Za-z0-9_\-]+$", str(svc_name)):
                return False, f"Invalid or unsafe service name '{svc_name}'"

        # 3. Temp cleanup precondition: Target must not specify arbitrary external directories
        if tool_name == "clean_user_temp_cache":
            target_path = arguments.get("target_path")
            if target_path and any(danger in str(target_path).lower() for danger in ["system32", "windows\\system", "program files"]):
                return False, "Target path touches protected operating system directories"

        # 4. Check explicit preconditions dictionary if supplied
        required_evidence_type = preconditions.get("required_evidence_type")
        if required_evidence_type and evidence_store:
            items = evidence_store.get_evidence(session_id=session_id)
            has_matching = any(i.evidence_type == required_evidence_type and i.status == EvidenceStatus.VERIFIED for i in items)
            if not has_matching:
                return False, f"Required verified evidence '{required_evidence_type}' is missing"

        return True, "Preconditions satisfied"


class RepairCandidateValidator:
    """Validates repair candidates strictly against ToolRegistry and Safety policies."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        safety_engine: Optional[SafetyEngine] = None,
    ) -> None:
        self.registry = registry or default_tool_registry
        self.safety_engine = safety_engine or default_safety_engine

    def validate(self, candidate: RepairCandidate) -> Tuple[bool, str]:
        """Strict validation of a RepairCandidate."""
        if not candidate.tool_name:
            return False, "RepairCandidate has empty tool_name"

        tool = self.registry.get(candidate.tool_name)
        if not tool:
            return False, f"Tool '{candidate.tool_name}' does not exist in approved ToolRegistry"

        if tool.risk == RiskLevel.HIGH:
            return False, "HIGH risk operations cannot be repair candidates"

        # Verify argument schema
        safety_dec = self.safety_engine.evaluate(candidate.tool_name, candidate.arguments, user_confirmed=False)
        if safety_dec.blocked:
            return False, f"SafetyEngine blocked candidate: {safety_dec.reason}"

        # Verify verification tool is registered and SAFE
        if candidate.verification_method:
            v_tool = self.registry.get(candidate.verification_method)
            if not v_tool:
                return False, f"Verification tool '{candidate.verification_method}' is not registered"
            if v_tool.risk != RiskLevel.SAFE:
                return False, f"Verification tool '{candidate.verification_method}' must have SAFE risk level"

        return True, "Candidate valid"


class DeterministicResolutionEngine:
    """Evaluates before/after diagnostic evidence to deterministically determine resolution."""

    @staticmethod
    def compare_evidence(
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
    ) -> Tuple[ResolutionStatus, str]:
        """Deterministically compare before vs after tool results."""
        if not before_state or not after_state:
            return ResolutionStatus.INCONCLUSIVE, "Insufficient before/after verification evidence"

        # Extract status / health indicators
        before_status = before_state.get("status") or before_state.get("result", {}).get("status") or "unknown"
        after_status = after_state.get("status") or after_state.get("result", {}).get("status") or "unknown"

        before_success = before_status in ["ok", "healthy", "success", "reachable", "normal"] or before_state.get("success") is True
        after_success = after_status in ["ok", "healthy", "success", "reachable", "normal"] or after_state.get("success") is True

        # Check for specific network / service indicators
        before_dns = before_state.get("dns_resolved", False)
        after_dns = after_state.get("dns_resolved", False)
        if "dns_resolved" in before_state or "dns_resolved" in after_state:
            if not before_dns and after_dns:
                return ResolutionStatus.RESOLVED, "DNS resolution restored successfully"
            if not before_dns and not after_dns:
                return ResolutionStatus.NOT_RESOLVED, "DNS resolution continues to fail after repair"

        # Service status check
        before_svc = str(before_state.get("state", "")).lower()
        after_svc = str(after_state.get("state", "")).lower()
        if before_svc and after_svc:
            if before_svc != "running" and after_svc == "running":
                return ResolutionStatus.RESOLVED, "Target service successfully restored to RUNNING state"
            if before_svc != "running" and after_svc != "running":
                return ResolutionStatus.NOT_RESOLVED, "Target service failed to start"

        # General status comparison
        if not before_success and after_success:
            return ResolutionStatus.RESOLVED, "Verification confirmed system returned to healthy state"
        elif not before_success and not after_success:
            return ResolutionStatus.NOT_RESOLVED, "Verification indicates issue persists after repair attempt"
        elif before_success and after_success:
            return ResolutionStatus.RESOLVED, "State remained verified and functional"
        else:
            return ResolutionStatus.PARTIALLY_RESOLVED, "Mixed verification signals detected"


class TroubleshootingWorkflowEngine:
    """Central coordinator for guided resolution workflows in WinFix AI."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        safety_engine: Optional[SafetyEngine] = None,
        evidence_store: Optional[EvidenceStore] = None,
    ) -> None:
        self.tool_registry = tool_registry or default_tool_registry
        self.safety_engine = safety_engine or default_safety_engine
        self.evidence_store = evidence_store or default_evidence_store
        self.validator = RepairCandidateValidator(self.tool_registry, self.safety_engine)
        self.workflows: Dict[str, TroubleshootingWorkflow] = {}

    def create_workflow_from_diagnosis(
        self,
        diagnosis: DiagnosticResponse,
        session_id: str = "default_session",
        repair_candidate: Optional[RepairCandidate] = None,
    ) -> TroubleshootingWorkflow:
        """Construct a bounded, structured TroubleshootingWorkflow from a DiagnosticResponse."""
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        
        # Determine problem category
        category = "general"
        if diagnosis.hypotheses:
            category = diagnosis.hypotheses[0].category

        steps: List[WorkflowStep] = []
        seq = 1

        # Step 1: Initial observation / verification of current state
        diagnostic_tools = diagnosis.recommended_tools or ["get_network_adapters_diagnostics"]
        for tool_name in diagnostic_tools[:2]:  # Limit initial diagnostic steps to max 2
            tool_def = self.tool_registry.get(tool_name)
            if tool_def and tool_def.risk == RiskLevel.SAFE:
                steps.append(
                    WorkflowStep(
                        step_id=seq,
                        workflow_id=workflow_id,
                        sequence=seq,
                        step_type=StepType.DIAGNOSE,
                        purpose=f"Gather verified diagnostic telemetry via {tool_name}",
                        tool_name=tool_name,
                        authorization_required=False,
                        verification_required=False,
                    )
                )
                seq += 1

        # Step 2: Precondition verification
        steps.append(
            WorkflowStep(
                step_id=seq,
                workflow_id=workflow_id,
                sequence=seq,
                step_type=StepType.VERIFY_PRECONDITION,
                purpose="Verify safety preconditions and environment stability",
                authorization_required=False,
                verification_required=False,
            )
        )
        seq += 1

        # Step 3: Repair candidate step if available
        if repair_candidate:
            valid, reason = self.validator.validate(repair_candidate)
            if valid:
                repair_candidate.workflow_id = workflow_id
                repair_candidate.session_id = session_id
                steps.append(
                    WorkflowStep(
                        step_id=seq,
                        workflow_id=workflow_id,
                        sequence=seq,
                        step_type=StepType.REPAIR,
                        purpose=repair_candidate.purpose or f"Execute approved repair {repair_candidate.tool_name}",
                        tool_name=repair_candidate.tool_name,
                        arguments=repair_candidate.arguments,
                        authorization_required=(repair_candidate.risk_level == "MEDIUM"),
                        verification_required=True,
                    )
                )
                seq += 1

                # Step 4: Verification step
                v_tool = repair_candidate.verification_method or DEFAULT_VERIFICATION_MAP.get(repair_candidate.tool_name, "")
                if v_tool and self.tool_registry.get(v_tool):
                    steps.append(
                        WorkflowStep(
                            step_id=seq,
                            workflow_id=workflow_id,
                            sequence=seq,
                            step_type=StepType.VERIFY_REPAIR,
                            purpose=f"Deterministically verify resolution via {v_tool}",
                            tool_name=v_tool,
                            authorization_required=False,
                            verification_required=False,
                        )
                    )
                    seq += 1

        # Final step: Complete
        steps.append(
            WorkflowStep(
                step_id=seq,
                workflow_id=workflow_id,
                sequence=seq,
                step_type=StepType.COMPLETE,
                purpose="Finalize resolution assessment and present explanation",
                authorization_required=False,
                verification_required=False,
            )
        )

        workflow = TroubleshootingWorkflow(
            workflow_id=workflow_id,
            session_id=session_id,
            problem_category=category,
            title=f"Troubleshooting: {diagnosis.summary or category.title()}",
            description=diagnosis.summary,
            diagnosis_id=diagnosis.plan_id if hasattr(diagnosis, "plan_id") else "",
            steps=steps[:MAX_WORKFLOW_STEPS],
            current_step=0,
            max_steps=MAX_WORKFLOW_STEPS,
            status=WorkflowStatus.CREATED,
            repair_candidate=repair_candidate,
            tutor_explanation=diagnosis.tutor_explanation,
        )

        self._audit(workflow, "WORKFLOW_CREATED", {"category": category, "steps_count": len(steps)})
        self.workflows[workflow_id] = workflow
        return workflow

    def transition_state(self, workflow: TroubleshootingWorkflow, target_status: WorkflowStatus) -> None:
        """Validate and apply a state transition via the state machine."""
        current = workflow.status
        allowed = VALID_WORKFLOW_TRANSITIONS.get(current, [])
        if target_status not in allowed:
            raise ValueError(f"Invalid workflow state transition: '{current.value}' -> '{target_status.value}'")
        
        workflow.status = target_status
        workflow.updated_at = datetime.now(timezone.utc).isoformat()
        self._audit(workflow, "STATE_TRANSITION", {"from": current.value, "to": target_status.value})

    def request_cancellation(self, workflow_id: str, session_id: str) -> bool:
        """Explicitly request workflow cancellation."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return False
        if wf.session_id != session_id:
            return False

        wf.cancellation_requested = True
        if wf.status not in [WorkflowStatus.RESOLVED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED]:
            try:
                self.transition_state(wf, WorkflowStatus.CANCELLED)
            except ValueError:
                wf.status = WorkflowStatus.CANCELLED
            self._audit(wf, "WORKFLOW_CANCELLED", {"reason": "User explicit request"})
        return True

    def execute_next_step(
        self,
        workflow_id: str,
        session_id: str,
        confirmation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Advance the workflow by executing the current step under strict boundaries."""
        with default_profiler.measure("execute_workflow_step"):
            wf = self.workflows.get(workflow_id)
            if not wf:
                return {"success": False, "error": "Workflow not found", "status": "NOT_FOUND"}

            # Session isolation validation
            if wf.session_id != session_id:
                return {"success": False, "error": "Session mismatch / unauthorized workflow access", "status": "FORBIDDEN"}

            # Cancellation check
            if wf.cancellation_requested or wf.status == WorkflowStatus.CANCELLED:
                return {"success": False, "error": "Workflow was cancelled", "status": "CANCELLED"}

            # Terminal state check
            if wf.status in [WorkflowStatus.RESOLVED, WorkflowStatus.FAILED, WorkflowStatus.UNRESOLVED]:
                return {"success": False, "error": f"Workflow is in terminal state: {wf.status.value}", "status": wf.status.value}

            # Step bounds check
            if wf.current_step >= len(wf.steps) or wf.current_step >= wf.max_steps:
                self.transition_state(wf, WorkflowStatus.UNRESOLVED)
                return {"success": False, "error": "Workflow step limit reached without complete resolution", "status": "LIMIT_REACHED"}

            step = wf.steps[wf.current_step]
            step.status = "RUNNING"
            step.started_at = datetime.now(timezone.utc).isoformat()
            self._audit(wf, "STEP_STARTED", {"step_id": step.step_id, "type": step.step_type.value})

            # Handle step by StepType
            if step.step_type == StepType.DIAGNOSE:
                if wf.status == WorkflowStatus.CREATED:
                    self.transition_state(wf, WorkflowStatus.DIAGNOSING)
                return self._execute_diagnostic_step(wf, step)

            elif step.step_type == StepType.VERIFY_PRECONDITION:
                if wf.status in [WorkflowStatus.CREATED, WorkflowStatus.DIAGNOSING]:
                    self.transition_state(wf, WorkflowStatus.VERIFY_PRECONDITION)
                return self._execute_precondition_step(wf, step)

            elif step.step_type == StepType.REPAIR:
                return self._execute_repair_step(wf, step, confirmation_token)

            elif step.step_type == StepType.VERIFY_REPAIR:
                if wf.status == WorkflowStatus.REPAIRING:
                    self.transition_state(wf, WorkflowStatus.VERIFYING)
                return self._execute_verification_step(wf, step)

            elif step.step_type == StepType.COMPLETE:
                return self._execute_complete_step(wf, step)

            return {"success": False, "error": f"Unsupported step type {step.step_type}", "status": "ERROR"}

    def _execute_diagnostic_step(self, wf: TroubleshootingWorkflow, step: WorkflowStep) -> Dict[str, Any]:
        """Execute a SAFE diagnostic tool step and capture evidence."""
        tool = self.tool_registry.get(step.tool_name)
        if not tool or tool.risk != RiskLevel.SAFE:
            step.status = "FAILED"
            step.error = "Tool is missing or not SAFE"
            return {"success": False, "error": step.error}

        decision = self.safety_engine.evaluate(step.tool_name, step.arguments, user_confirmed=False)
        if not decision.allowed:
            step.status = "FAILED"
            step.error = decision.reason
            return {"success": False, "error": decision.reason}

        try:
            result = tool.handler(**decision.validated_arguments)
            step.result = result
            step.status = "COMPLETED"
            step.completed_at = datetime.now(timezone.utc).isoformat()
            
            # Store as before_evidence if not already populated
            if not wf.before_evidence:
                wf.before_evidence = dict(result)

            wf.current_step += 1
            self._audit(wf, "STEP_COMPLETED", {"step_id": step.step_id, "tool": step.tool_name})
            return {"success": True, "step": step.to_dict(), "result": result}
        except Exception as e:
            if step.retry_count < MAX_SAFE_DIAGNOSTIC_RETRIES:
                step.retry_count += 1
                self._audit(wf, "STEP_RETRY", {"step_id": step.step_id, "tool": step.tool_name, "retry": step.retry_count})
                return self._execute_diagnostic_step(wf, step)
            step.status = "FAILED"
            step.error = str(e)
            return {"success": False, "error": str(e)}

    def _execute_precondition_step(self, wf: TroubleshootingWorkflow, step: WorkflowStep) -> Dict[str, Any]:
        """Evaluate preconditions deterministically."""
        candidate = wf.repair_candidate
        if candidate:
            ok, msg = PreconditionEngine.validate_preconditions(
                tool_name=candidate.tool_name,
                arguments=candidate.arguments,
                preconditions=candidate.preconditions,
                evidence_store=self.evidence_store,
                session_id=wf.session_id,
            )
            if not ok:
                step.status = "FAILED"
                step.error = msg
                self.transition_state(wf, WorkflowStatus.FAILED)
                return {"success": False, "error": f"Precondition failed: {msg}"}

        step.status = "COMPLETED"
        step.completed_at = datetime.now(timezone.utc).isoformat()
        wf.current_step += 1
        self._audit(wf, "STEP_COMPLETED", {"step_id": step.step_id, "type": "VERIFY_PRECONDITION"})
        return {"success": True, "message": "Preconditions satisfied"}

    def _execute_repair_step(
        self,
        wf: TroubleshootingWorkflow,
        step: WorkflowStep,
        confirmation_token: Optional[str],
    ) -> Dict[str, Any]:
        """Execute a repair action strictly guarded by confirmation and limits."""
        candidate = wf.repair_candidate
        if not candidate:
            step.status = "FAILED"
            step.error = "No RepairCandidate associated with workflow"
            return {"success": False, "error": step.error}

        # Check duplicate repair execution limit
        if step.tool_name in wf.executed_repair_tools:
            step.status = "FAILED"
            step.error = f"Duplicate execution blocked: Repair tool '{step.tool_name}' already executed in this workflow"
            self.transition_state(wf, WorkflowStatus.FAILED)
            return {"success": False, "error": step.error}

        # Check confirmation token for MEDIUM risk tools
        tool = self.tool_registry.get(step.tool_name)
        if not tool:
            step.status = "FAILED"
            step.error = f"Tool '{step.tool_name}' not found"
            return {"success": False, "error": step.error}

        if tool.risk == RiskLevel.MEDIUM:
            expected_token = candidate.generate_confirmation_token()
            if not confirmation_token or confirmation_token != expected_token:
                wf.status = WorkflowStatus.WAITING_FOR_CONFIRMATION
                self._audit(wf, "CONFIRMATION_REQUESTED", {"tool": step.tool_name, "token": expected_token})
                return {
                    "success": False,
                    "status": "WAITING_FOR_CONFIRMATION",
                    "requires_confirmation": True,
                    "confirmation_token": expected_token,
                    "message": f"Confirmation required for MEDIUM risk tool '{step.tool_name}'",
                }

        # User is confirmed
        if wf.status == WorkflowStatus.WAITING_FOR_CONFIRMATION:
            self.transition_state(wf, WorkflowStatus.REPAIRING)
        elif wf.status == WorkflowStatus.VERIFY_PRECONDITION:
            self.transition_state(wf, WorkflowStatus.REPAIRING)

        decision = self.safety_engine.evaluate(step.tool_name, step.arguments, user_confirmed=True)
        if not decision.allowed:
            step.status = "FAILED"
            step.error = decision.reason
            self.transition_state(wf, WorkflowStatus.FAILED)
            return {"success": False, "error": decision.reason}

        try:
            result = tool.handler(**decision.validated_arguments)
            step.result = result
            step.status = "COMPLETED"
            step.completed_at = datetime.now(timezone.utc).isoformat()
            wf.executed_repair_tools.append(step.tool_name)
            wf.current_step += 1
            self._audit(wf, "REPAIR_EXECUTED", {"tool": step.tool_name, "result_summary": str(result)[:100]})
            return {"success": True, "result": result, "status": "REPAIR_EXECUTED"}
        except Exception as e:
            step.status = "FAILED"
            step.error = str(e)
            wf.failure_reason = str(e)
            self.transition_state(wf, WorkflowStatus.FAILED)
            return {"success": False, "error": f"Repair execution failed: {e}", "status": "FAILED"}

    def _execute_verification_step(self, wf: TroubleshootingWorkflow, step: WorkflowStep) -> Dict[str, Any]:
        """Execute post-repair deterministic verification and compare evidence."""
        tool = self.tool_registry.get(step.tool_name)
        if not tool or tool.risk != RiskLevel.SAFE:
            step.status = "FAILED"
            step.error = "Verification tool is invalid or not SAFE"
            return {"success": False, "error": step.error}

        decision = self.safety_engine.evaluate(step.tool_name, step.arguments, user_confirmed=False)
        if not decision.allowed:
            step.status = "FAILED"
            step.error = decision.reason
            return {"success": False, "error": decision.reason}

        try:
            after_result = tool.handler(**decision.validated_arguments)
            step.result = after_result
            step.status = "COMPLETED"
            step.completed_at = datetime.now(timezone.utc).isoformat()
            wf.after_evidence = dict(after_result)

            # Compare before vs after deterministically
            res_status, explanation = DeterministicResolutionEngine.compare_evidence(
                before_state=wf.before_evidence,
                after_state=wf.after_evidence,
            )
            wf.resolution_status = res_status
            wf.current_step += 1
            self._audit(wf, "VERIFICATION_COMPLETED", {"resolution": res_status.value, "explanation": explanation})
            return {
                "success": True,
                "verification_result": after_result,
                "resolution_status": res_status.value,
                "explanation": explanation,
            }
        except Exception as e:
            step.status = "FAILED"
            step.error = str(e)
            wf.resolution_status = ResolutionStatus.INCONCLUSIVE
            return {"success": False, "error": str(e)}

    def _execute_complete_step(self, wf: TroubleshootingWorkflow, step: WorkflowStep) -> Dict[str, Any]:
        """Finalize workflow status based on deterministic verification."""
        step.status = "COMPLETED"
        step.completed_at = datetime.now(timezone.utc).isoformat()
        wf.current_step += 1

        if wf.resolution_status == ResolutionStatus.RESOLVED:
            self.transition_state(wf, WorkflowStatus.RESOLVED)
        elif wf.resolution_status == ResolutionStatus.PARTIALLY_RESOLVED:
            self.transition_state(wf, WorkflowStatus.PARTIALLY_RESOLVED)
        else:
            self.transition_state(wf, WorkflowStatus.UNRESOLVED)

        self._audit(wf, "WORKFLOW_COMPLETED", {"final_status": wf.status.value, "resolution": wf.resolution_status.value})
        return {
            "success": True,
            "status": wf.status.value,
            "resolution_status": wf.resolution_status.value,
            "tutor_explanation": wf.tutor_explanation,
        }

    def _audit(self, wf: TroubleshootingWorkflow, event: str, details: Dict[str, Any]) -> None:
        """Record a sanitized audit event."""
        # Sanitize sensitive fields
        sanitized_details = {}
        for k, v in details.items():
            if any(secret in k.lower() for secret in ["password", "secret", "token", "auth"]):
                sanitized_details[k] = "[REDACTED]"
            else:
                sanitized_details[k] = v

        wf.audit_events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": sanitized_details,
        })

        # Forward to Phase 32 Telemetry Service
        try:
            from production.telemetry import default_telemetry_service
            from production.telemetry_models import TelemetryEventType
            if event == "WORKFLOW_STARTED":
                default_telemetry_service.record_workflow_event(
                    session_id=wf.session_id,
                    event_type=TelemetryEventType.WORKFLOW_STARTED,
                    outcome=wf.status.value,
                    metadata={"workflow_id": wf.workflow_id, **sanitized_details},
                )
            elif event == "WORKFLOW_COMPLETED":
                default_telemetry_service.record_workflow_event(
                    session_id=wf.session_id,
                    event_type=TelemetryEventType.WORKFLOW_COMPLETED,
                    outcome=wf.status.value,
                    metadata={"workflow_id": wf.workflow_id, **sanitized_details},
                )
            elif event == "STEP_STARTED":
                default_telemetry_service.record_workflow_event(
                    session_id=wf.session_id,
                    event_type=TelemetryEventType.WORKFLOW_STEP_STARTED,
                    metadata={"workflow_id": wf.workflow_id, **sanitized_details},
                )
            elif event == "STEP_COMPLETED":
                default_telemetry_service.record_workflow_event(
                    session_id=wf.session_id,
                    event_type=TelemetryEventType.WORKFLOW_STEP_COMPLETED,
                    metadata={"workflow_id": wf.workflow_id, **sanitized_details},
                )
        except Exception as ex:
            logger.debug(f"Telemetry forwarding exception in workflow audit (ignored): {ex}")


default_workflow_engine = TroubleshootingWorkflowEngine()

