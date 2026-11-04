"""WinFix AI — AI Decision & Diagnostic Intelligence Engine (Phase 27).

Orchestrates multi-modal evidence ingestion, contradiction detection, structured
diagnostic hypothesis generation, strict ToolRegistry recommendation validation,
bounded deterministic diagnostic plans, and degraded offline resilience.
Strictly adheres to:
  LLM != Windows Shell
  Diagnosis != Windows Command
  Evidence != Windows Command
  Hypothesis != Windows Command
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid

from agent.agent_response import FORBIDDEN_EXECUTION_KEYS, extract_json_from_text
from agent.diagnostic_models import (
    DiagnosticHypothesis,
    DiagnosticPlan,
    DiagnosticPlanStep,
    DiagnosticResponse,
    HypothesisStatus,
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
from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from production.performance import default_profiler

logger = logging.getLogger("winfix.DIAGNOSTIC_ENGINE")

DIAGNOSTIC_SYSTEM_PROMPT = """You are WinFix AI Diagnostic Intelligence Engine.
Analyze factual evidence and user symptoms to produce structured troubleshooting hypotheses.
Strictly adhere to rules:
1. Separate raw OBSERVATION from INTERPRETATION and HYPOTHESIS.
2. Never claim an issue is VERIFIED unless deterministic tool evidence directly confirms it.
3. Recommend ONLY registered tool names from the provided allowlist.
4. Output strictly valid JSON matching the schema:
{
  "summary": "Brief summary of diagnosis",
  "observations": ["Observed fact 1", "Observed fact 2"],
  "interpretations": ["Interpretation 1", "Interpretation 2"],
  "hypotheses": [
    {
      "category": "network",
      "statement": "Hypothesis statement",
      "affected_component": "DNS",
      "severity": "NORMAL",
      "status": "POSSIBLE",
      "recommended_tools": ["check_dns_resolution"],
      "explanation": "Why this might be happening",
      "uncertainty_notes": "What remains unknown"
    }
  ],
  "recommended_tools": ["check_dns_resolution"],
  "uncertainty": ["Uncertainty point 1"],
  "tutor_explanation": "Educational summary for the user"
}
"""


class AIDiagnosticEngine:
    """Core diagnostic intelligence coordinator for WinFix AI."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
        safety_engine: Optional[SafetyEngine] = None,
        evidence_store: Optional[EvidenceStore] = None,
    ) -> None:
        self.client = client or ollama_client
        self.tool_registry = tool_registry or default_tool_registry
        self.safety_engine = safety_engine or default_safety_engine
        self.evidence_store = evidence_store or default_evidence_store

    def ingest_tool_result(
        self,
        tool_name: str,
        tool_result: Dict[str, Any],
        evidence_type: EvidenceType,
        session_id: str = "default_session",
    ) -> List[EvidenceItem]:
        """Normalize and store tool execution output as verified diagnostic evidence."""
        with default_profiler.measure("ingest_tool_result"):
            items = EvidenceNormalizer.from_tool_result(
                tool_name=tool_name,
                tool_result=tool_result,
                evidence_type=evidence_type,
                session_id=session_id,
            )
            self.evidence_store.add_many(items)
            return items

    def ingest_user_symptom(
        self,
        user_text: str,
        session_id: str = "default_session",
        source: EvidenceSource = EvidenceSource.USER,
    ) -> EvidenceItem:
        """Normalize and store user symptom or voice transcript as user-reported evidence."""
        with default_profiler.measure("ingest_user_symptom"):
            item = EvidenceNormalizer.from_user_input(
                user_text=user_text,
                session_id=session_id,
                source=source,
            )
            self.evidence_store.add_evidence(item)
            return item

    def ingest_screenshot(
        self,
        observation: str,
        visual_details: Optional[Dict[str, Any]] = None,
        session_id: str = "default_session",
    ) -> EvidenceItem:
        """Normalize and store screenshot analysis as inferred visual evidence."""
        with default_profiler.measure("ingest_screenshot"):
            item = EvidenceNormalizer.from_screenshot(
                observation=observation,
                visual_details=visual_details,
                session_id=session_id,
            )
            self.evidence_store.add_evidence(item)
            return item

    def evaluate_diagnosis(
        self,
        user_problem: str,
        session_id: str = "default_session",
    ) -> DiagnosticResponse:
        """Generate structured diagnostic hypotheses, recommendations, and plans from evidence."""
        with default_profiler.measure("evaluate_diagnosis"):
            # 1. Ingest current user prompt if not already present
            self.ingest_user_symptom(user_problem, session_id=session_id)

            # 2. Retrieve session evidence & check contradictions
            evidence_items = self.evidence_store.get_session_evidence(session_id, include_stale=False)
            contradictions = self.evidence_store.detect_contradictions(session_id)

            # 3. Check if local Ollama is available
            if not self.client.is_available():
                logger.info("Local Ollama unavailable; generating deterministic diagnostic fallback.")
                return self._build_deterministic_diagnosis(user_problem, evidence_items, contradictions, session_id)

            # 4. Construct prompt for Ollama
            allowed_tools = self._get_diagnostic_allowed_tools()
            prompt = self._build_diagnostic_prompt(user_problem, evidence_items, contradictions, allowed_tools)

            # 5. Query Ollama with timeout
            raw_res = self.client.generate(
                prompt=prompt,
                system=DIAGNOSTIC_SYSTEM_PROMPT,
                format="json",
                options={"temperature": 0.1},
                use_cache=False,
            )

            if not raw_res.get("success", False):
                logger.warning("Ollama diagnostic generation failed (%s); using deterministic fallback.", raw_res.get("error"))
                return self._build_deterministic_diagnosis(user_problem, evidence_items, contradictions, session_id)

            # 6. Parse and strictly validate response
            raw_text = raw_res.get("response", "")
            return self._parse_and_validate_diagnosis(raw_text, user_problem, evidence_items, contradictions, session_id)

    def _get_diagnostic_allowed_tools(self) -> List[str]:
        """Return allowlist of SAFE diagnostic tool names."""
        tools = self.tool_registry.list_tools()
        return [t.name for t in tools if t.risk == RiskLevel.SAFE]

    def _build_diagnostic_prompt(
        self,
        user_problem: str,
        evidence: List[EvidenceItem],
        contradictions: List[Dict[str, Any]],
        allowed_tools: List[str],
    ) -> str:
        """Build structured prompt presenting verified facts and allowed tools."""
        ev_summary = []
        for it in evidence:
            ev_summary.append(f"[{it.quality.value}] ({it.category}) {it.observation} (ID: {it.evidence_id})")

        contra_summary = []
        for c in contradictions:
            contra_summary.append(f"CONFLICT: {c['description']} (Evidence: {c['evidence_ids']})")

        return f"""USER PROBLEM DESCRIPTION:
{user_problem}

CURRENT COLLECTED EVIDENCE:
{chr(10).join(ev_summary) if ev_summary else "No prior tool execution evidence yet."}

CONTRADICTIONS DETECTED:
{chr(10).join(contra_summary) if contra_summary else "None."}

ALLOWED DIAGNOSTIC TOOLS:
{json.dumps(allowed_tools)}

Analyze the evidence, formulate hypotheses, recommend allowed tools, and output strictly JSON.
"""

    def _parse_and_validate_diagnosis(
        self,
        raw_text: str,
        user_problem: str,
        evidence: List[EvidenceItem],
        contradictions: List[Dict[str, Any]],
        session_id: str,
    ) -> DiagnosticResponse:
        """Strictly parse, sanitize, and validate the LLM diagnostic response."""
        json_str = extract_json_from_text(raw_text)
        if not json_str:
            return self._build_deterministic_diagnosis(user_problem, evidence, contradictions, session_id)

        try:
            data = json.loads(json_str)
        except Exception:
            return self._build_deterministic_diagnosis(user_problem, evidence, contradictions, session_id)

        if not isinstance(data, dict):
            return self._build_deterministic_diagnosis(user_problem, evidence, contradictions, session_id)

        # Check for forbidden command injection keys
        if any(k in data for k in FORBIDDEN_EXECUTION_KEYS):
            logger.warning("Forbidden execution key detected in diagnostic response. Reverting to fallback.")
            return self._build_deterministic_diagnosis(user_problem, evidence, contradictions, session_id)

        allowed_tools_set = set(self._get_diagnostic_allowed_tools())

        # Validate and sanitize recommended tools
        raw_tools = data.get("recommended_tools", [])
        valid_tools: List[str] = []
        if isinstance(raw_tools, list):
            for t in raw_tools:
                if isinstance(t, str) and t in allowed_tools_set and t not in valid_tools:
                    valid_tools.append(t)

        # Limit to max 5 tools
        valid_tools = valid_tools[:5]

        # Validate Hypotheses (limit to max 5)
        raw_hypotheses = data.get("hypotheses", [])
        valid_hypotheses: List[DiagnosticHypothesis] = []
        if isinstance(raw_hypotheses, list):
            for h in raw_hypotheses[:5]:
                if not isinstance(h, dict):
                    continue
                # Invariant: LLM cannot set status to VERIFIED
                raw_status = str(h.get("status", "POSSIBLE")).upper()
                status = HypothesisStatus.POSSIBLE
                if raw_status in (HypothesisStatus.SUPPORTED.value, HypothesisStatus.CONTRADICTED.value, HypothesisStatus.UNRESOLVED.value):
                    status = HypothesisStatus(raw_status)

                hyp_tools = [t for t in h.get("recommended_tools", []) if isinstance(t, str) and t in allowed_tools_set][:5]

                hyp = DiagnosticHypothesis(
                    hypothesis_id=str(uuid.uuid4())[:8],
                    category=str(h.get("category", "general")),
                    statement=str(h.get("statement", "")),
                    supporting_evidence_ids=[str(x) for x in h.get("supporting_evidence_ids", [])],
                    contradicting_evidence_ids=[str(x) for x in h.get("contradicting_evidence_ids", [])],
                    affected_component=str(h.get("affected_component", "")),
                    severity=str(h.get("severity", "NORMAL")),
                    status=status,
                    recommended_tools=hyp_tools,
                    explanation=str(h.get("explanation", "")),
                    uncertainty_notes=str(h.get("uncertainty_notes", "")),
                )
                valid_hypotheses.append(hyp)

        # Build deterministic plan from validated tools
        plan = self.build_diagnostic_plan(valid_tools, session_id, problem_category=data.get("category", "general"))

        ev_ids = [it.evidence_id for it in evidence]

        return DiagnosticResponse(
            summary=str(data.get("summary", "Diagnostic analysis completed.")),
            observations=[str(o) for o in data.get("observations", []) if isinstance(o, str)][:5],
            interpretations=[str(i) for i in data.get("interpretations", []) if isinstance(i, str)][:5],
            hypotheses=valid_hypotheses,
            evidence_references=ev_ids,
            recommended_tools=valid_tools,
            diagnostic_plan=plan,
            uncertainty=[str(u) for u in data.get("uncertainty", []) if isinstance(u, str)][:5],
            tutor_explanation=data.get("tutor_explanation"),
            confidence=0.85,
            is_degraded=False,
            raw_json=data,
        )

    def _build_deterministic_diagnosis(
        self,
        user_problem: str,
        evidence: List[EvidenceItem],
        contradictions: List[Dict[str, Any]],
        session_id: str,
    ) -> DiagnosticResponse:
        """Deterministic rule-based diagnostic synthesis when AI is unavailable or fails."""
        prob_lower = user_problem.lower()
        recommended: List[str] = []
        hypotheses: List[DiagnosticHypothesis] = []
        category = "general"

        if "network" in prob_lower or "internet" in prob_lower or "dns" in prob_lower or "wifi" in prob_lower:
            category = "network"
            recommended = ["check_internet_connectivity", "check_dns_resolution", "get_network_adapters_diagnostics"]
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="hyp_net_01",
                    category="network",
                    statement="Possible network adapter disconnect or DNS resolver failure.",
                    affected_component="Network",
                    severity="NORMAL",
                    status=HypothesisStatus.POSSIBLE,
                    recommended_tools=recommended,
                    explanation="Network connectivity or DNS lookup may be degraded.",
                    uncertainty_notes="Requires executing diagnostic tools to verify adapter and gateway reachability.",
                )
            )
        elif "service" in prob_lower or "spooler" in prob_lower or "wuauserv" in prob_lower:
            category = "service"
            recommended = ["get_services_diagnostics", "list_common_services"]
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="hyp_svc_01",
                    category="service",
                    statement="Target Windows service may be stopped or in an error state.",
                    affected_component="ServiceManager",
                    severity="NORMAL",
                    status=HypothesisStatus.POSSIBLE,
                    recommended_tools=recommended,
                    explanation="Background services can stop unexpectedly due to crashes or dependencies.",
                )
            )
        elif "disk" in prob_lower or "storage" in prob_lower or "space" in prob_lower:
            category = "storage"
            recommended = ["get_storage_diagnostics", "get_temp_storage_info"]
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="hyp_str_01",
                    category="storage",
                    statement="Low disk space or large temporary file accumulation.",
                    affected_component="Storage",
                    severity="NORMAL",
                    status=HypothesisStatus.POSSIBLE,
                    recommended_tools=recommended,
                    explanation="Exhausted drive space degrades Windows system performance.",
                )
            )
        elif "slow" in prob_lower or "cpu" in prob_lower or "memory" in prob_lower or "ram" in prob_lower:
            category = "performance"
            recommended = ["get_cpu_diagnostics", "get_memory_diagnostics", "get_top_cpu_processes"]
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="hyp_perf_01",
                    category="performance",
                    statement="High resource consumption by background processes.",
                    affected_component="Performance",
                    severity="NORMAL",
                    status=HypothesisStatus.POSSIBLE,
                    recommended_tools=recommended,
                    explanation="Unresponsive tasks or memory leaks cause system sluggishness.",
                )
            )
        else:
            recommended = ["get_complete_system_info"]
            hypotheses.append(
                DiagnosticHypothesis(
                    hypothesis_id="hyp_gen_01",
                    category="system",
                    statement="General Windows diagnostic inspection required.",
                    affected_component="System",
                    severity="NORMAL",
                    status=HypothesisStatus.POSSIBLE,
                    recommended_tools=recommended,
                    explanation="Inspecting OS baseline information and active subsystems.",
                )
            )

        plan = self.build_diagnostic_plan(recommended, session_id, problem_category=category)
        ev_ids = [it.evidence_id for it in evidence]

        return DiagnosticResponse(
            summary=f"Deterministic diagnostic evaluation for {category} troubleshooting.",
            observations=[f"User reported: {user_problem}"] + [it.observation for it in evidence[:3]],
            interpretations=[f"Rule-based diagnostic pattern matched '{category}'."],
            hypotheses=hypotheses,
            evidence_references=ev_ids,
            recommended_tools=recommended,
            diagnostic_plan=plan,
            uncertainty=["Evaluation performed using deterministic fallback rules (Ollama offline/degraded)."],
            tutor_explanation=f"WinFix AI matched your inquiry to standard {category} diagnostics.",
            confidence=0.75,
            is_degraded=True,
        )

    def build_diagnostic_plan(
        self,
        tool_names: List[str],
        session_id: str,
        problem_category: str = "general",
    ) -> DiagnosticPlan:
        """Construct a bounded, loop-protected DiagnosticPlan."""
        allowed_tools_set = set(self._get_diagnostic_allowed_tools())
        steps: List[DiagnosticPlanStep] = []
        seen_tools: Set[str] = set()

        for idx, t_name in enumerate(tool_names):
            if t_name in allowed_tools_set and t_name not in seen_tools and len(steps) < 5:
                step = DiagnosticPlanStep(
                    step_id=len(steps) + 1,
                    tool_name=t_name,
                    purpose=f"Collect factual {problem_category} evidence via {t_name}",
                    arguments={},
                )
                steps.append(step)
                seen_tools.add(t_name)

        plan = DiagnosticPlan(
            plan_id=str(uuid.uuid4())[:8],
            session_id=session_id,
            problem_category=problem_category,
            steps=steps,
            max_steps=5,
        )
        return plan

    def execute_plan_step(
        self,
        plan: DiagnosticPlan,
        step_index: int,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Execute a single diagnostic plan step through registered safe tool handlers."""
        with default_profiler.measure("execute_plan_step"):
            if step_index < 0 or step_index >= len(plan.steps):
                return False, None, "Invalid step index."

            step = plan.steps[step_index]
            tool_name = step.tool_name

            # Check ToolRegistry
            tool_def = self.tool_registry.get(tool_name)
            if not tool_def:
                step.status = "FAILED"
                return False, None, f"Tool '{tool_name}' not found in registry."

            # SafetyEngine check (SAFE tools only for automated diagnostic execution)
            decision = self.safety_engine.evaluate(tool_name, step.arguments)
            if not decision.allowed or decision.requires_confirmation:
                step.status = "FAILED"
                return False, None, f"Tool '{tool_name}' blocked by SafetyEngine: {decision.reason}"

            step.status = "RUNNING"
            try:
                # Dispatch tool execution safely
                handler = tool_def.handler
                if not handler:
                    step.status = "FAILED"
                    return False, None, f"No execution handler registered for '{tool_name}'."

                result = handler(**step.arguments)
                step.status = "COMPLETED"
                step.result = result

                # Ingest result into session evidence store
                ev_type = EvidenceType.SYSTEM
                cat_lower = plan.problem_category.lower()
                for t in EvidenceType:
                    if t.value.lower() in cat_lower or t.value.lower() in tool_name.lower():
                        ev_type = t
                        break

                self.ingest_tool_result(
                    tool_name=tool_name,
                    tool_result=result,
                    evidence_type=ev_type,
                    session_id=plan.session_id,
                )

                plan.current_step_index = step_index + 1
                if plan.current_step_index >= len(plan.steps):
                    plan.status = "COMPLETED"
                else:
                    plan.status = "IN_PROGRESS"

                return True, result, f"Successfully executed step {step.step_id} ({tool_name})."
            except Exception as exc:
                step.status = "FAILED"
                step.result = {"error": str(exc)}
                return False, None, f"Execution failed for {tool_name}: {exc}"



# Global singleton diagnostic engine
default_diagnostic_engine = AIDiagnosticEngine()
