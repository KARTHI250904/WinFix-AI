"""WinFix AI — Adaptive Diagnostic Engine (Phase 30).

Provides bounded, deterministic adaptive diagnostic reasoning. Adapts diagnostic path
and hypothesis status dynamically as factual telemetry is collected, invalidated, or contradicted.
Strictly adheres to:
  LLM != Windows Shell
  Hypothesis != Authorization
  Candidate != Authorization
  Execution != Success
  Workflow Budget <= 8 Steps
  Deterministic Fail-Closed Policy
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

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
from agent.diagnostic_models import DiagnosticHypothesis, HypothesisStatus
from agent.domain_models import DomainClassification, FailureCategory, TroubleshootingDomain
from agent.domain_registry import DomainRegistry
from agent.evidence_correlator import EvidenceCorrelator
from agent.evidence_evolution import EvidenceEvolutionTracker
from agent.evidence_models import EvidenceItem, EvidenceQuality, EvidenceStore, EvidenceType
from agent.resolution_analyzer import ResolutionAnalyzer

from agent.troubleshooting_strategies import StrategyRegistry, TroubleshootingStrategy

from agent.verification_registry import VerificationRegistry
from agent.workflow_models import TroubleshootingWorkflow, WorkflowStatus


logger = logging.getLogger("winfix.ADAPTIVE_ENGINE")


class AdaptiveDiagnosticEngine:
    """Deterministic adaptive reasoning engine managing dynamic hypothesis shifts and bounded diagnostic decisions."""

    def __init__(
        self,
        evidence_store: Optional[EvidenceStore] = None,
        strategy_registry: Optional[StrategyRegistry] = None,
        verification_registry: Optional[VerificationRegistry] = None,
    ) -> None:
        self.evidence_store = evidence_store or EvidenceStore()
        self.strategy_registry = strategy_registry or StrategyRegistry()
        self.verification_registry = verification_registry or VerificationRegistry()

        self.evolution_tracker = EvidenceEvolutionTracker(self.evidence_store)
        self.correlator = EvidenceCorrelator(self.evidence_store)

    def create_session(
        self,
        session_id: str,
        initial_symptom: str,
        primary_domain: Optional[TroubleshootingDomain] = None,
    ) -> AdaptiveSessionContext:
        """Initialize a new bounded adaptive diagnostic session."""
        if primary_domain is None or primary_domain == TroubleshootingDomain.UNKNOWN:
            classification = DomainRegistry.classify_symptoms(initial_symptom)
            primary_domain = classification.domain

        ctx = AdaptiveSessionContext(
            session_id=session_id,
            current_state=AdaptiveState.INITIAL,
            primary_domain=primary_domain,
        )
        return ctx

    def evaluate_telemetry_and_adapt(
        self,
        ctx: AdaptiveSessionContext,
        current_hypothesis: Optional[DiagnosticHypothesis],
        new_evidence: EvidenceItem,
    ) -> Tuple[DiagnosticHypothesis, DiagnosticDecision]:
        """Evaluate incoming evidence against current hypothesis and decide next adaptive action."""
        if not ctx.can_execute_step():
            ctx.current_state = AdaptiveState.UNRESOLVED
            decision = DiagnosticDecision(
                decision_id=str(uuid.uuid4()),
                action_type="ABORT_UNRESOLVED",
                hypothesis_id=current_hypothesis.hypothesis_id if current_hypothesis else None,
                rationale="Workflow step budget exhausted (max 8 steps reached).",
            )
            ctx.record_decision(decision)
            return current_hypothesis or self._create_fallback_hypothesis("budget_exhausted"), decision

        # Store evidence and track change
        self.evidence_store.add_evidence(new_evidence)
        old_ev = None
        existing = self.evidence_store.get_session_evidence(ctx.session_id, include_stale=True)
        for ev in existing:
            if ev.evidence_id != new_evidence.evidence_id and ev.evidence_type == new_evidence.evidence_type:
                old_ev = ev
                break

        change = self.evolution_tracker.track_change(old_ev, new_evidence)
        ctx.evidence_changes.append(change)

        # Base hypothesis if none provided
        if current_hypothesis is None:
            current_hypothesis = DiagnosticHypothesis(
                hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
                category=ctx.primary_domain.value,
                statement=f"Suspected root cause in {ctx.primary_domain.value} domain",
                status=HypothesisStatus.POSSIBLE,
            )

        # Check for contradiction against current hypothesis
        is_contradicted, reason, adapted_domain = self._check_contradiction(ctx, current_hypothesis, new_evidence)

        if is_contradicted:
            # Transition hypothesis status to CONTRADICTED
            transition = HypothesisTransition(
                transition_id=str(uuid.uuid4()),
                hypothesis_id=current_hypothesis.hypothesis_id,
                from_status=current_hypothesis.status,
                to_status=HypothesisStatus.CONTRADICTED,
                triggering_evidence_ids=[new_evidence.evidence_id],
                reason=reason,
            )
            ctx.record_transition(transition)
            ctx.current_state = AdaptiveState.CONTRADICTED

            # Generate adapted hypothesis
            target_domain = adapted_domain or ctx.primary_domain
            adapted_hypothesis = DiagnosticHypothesis(
                hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
                category=target_domain.value,
                statement=f"Adapted hypothesis: issue shifted to {target_domain.value} ({reason})",
                supporting_evidence_ids=[new_evidence.evidence_id],
                status=HypothesisStatus.SUPPORTED,
            )
            ctx.active_hypothesis_id = adapted_hypothesis.hypothesis_id

            # Select adapted strategy
            strategy = self.strategy_registry.select_strategy(target_domain)
            ctx.active_strategy_id = strategy.strategy_id if strategy else None

            decision = DiagnosticDecision(
                decision_id=str(uuid.uuid4()),
                action_type="ADAPT_HYPOTHESIS",
                target_strategy_id=strategy.strategy_id if strategy else None,
                hypothesis_id=adapted_hypothesis.hypothesis_id,
                rationale=f"Hypothesis adapted because prior hypothesis was contradicted: {reason}",
                evidence_ids=[new_evidence.evidence_id],
            )
            ctx.record_decision(decision)
            ctx.current_state = AdaptiveState.ADAPTING
            return adapted_hypothesis, decision

        # If evidence supports hypothesis
        if self._is_supporting(current_hypothesis, new_evidence):
            transition = HypothesisTransition(
                transition_id=str(uuid.uuid4()),
                hypothesis_id=current_hypothesis.hypothesis_id,
                from_status=current_hypothesis.status,
                to_status=HypothesisStatus.SUPPORTED,
                triggering_evidence_ids=[new_evidence.evidence_id],
                reason="Evidence directly confirms failure state.",
            )
            ctx.record_transition(transition)
            ctx.current_state = AdaptiveState.EVALUATING

            updated_hyp = DiagnosticHypothesis(
                hypothesis_id=current_hypothesis.hypothesis_id,
                category=current_hypothesis.category,
                statement=current_hypothesis.statement,
                supporting_evidence_ids=list(current_hypothesis.supporting_evidence_ids) + [new_evidence.evidence_id],
                status=HypothesisStatus.SUPPORTED,
                recommended_tools=current_hypothesis.recommended_tools,
            )

            # Check if repair candidate should be proposed
            strategy = self.strategy_registry.select_strategy(ctx.primary_domain)
            repair_tool = None
            if strategy and strategy.repair_candidates:
                cand = strategy.repair_candidates[0]
                repair_tool = cand.get("tool_name") if isinstance(cand, dict) else str(cand)

            decision = DiagnosticDecision(
                decision_id=str(uuid.uuid4()),
                action_type="PROPOSE_REPAIR" if repair_tool else "CONTINUE_PLAN",
                target_strategy_id=strategy.strategy_id if strategy else None,
                target_tool_name=repair_tool,
                hypothesis_id=updated_hyp.hypothesis_id,
                rationale=f"Evidence supports hypothesis. Proposed next step: {repair_tool or 'continue diagnostic'}",
                evidence_ids=[new_evidence.evidence_id],
            )
            ctx.record_decision(decision)
            return updated_hyp, decision


        # Default continue
        decision = DiagnosticDecision(
            decision_id=str(uuid.uuid4()),
            action_type="CONTINUE_PLAN",
            hypothesis_id=current_hypothesis.hypothesis_id,
            rationale="Evidence evaluated; continuing standard diagnostic plan.",
            evidence_ids=[new_evidence.evidence_id],
        )
        ctx.record_decision(decision)
        return current_hypothesis, decision

    def _check_contradiction(
        self,
        ctx: AdaptiveSessionContext,
        hypothesis: DiagnosticHypothesis,
        evidence: EvidenceItem,
    ) -> Tuple[bool, str, Optional[TroubleshootingDomain]]:
        """Evaluate if evidence contradicts the active hypothesis."""
        data = evidence.value if isinstance(evidence.value, dict) else {}

        # 1. DNS hypothesis contradicted if DNS resolution succeeded
        if "dns" in hypothesis.statement.lower() or hypothesis.category == TroubleshootingDomain.NETWORK.value:
            if "dns" in hypothesis.statement.lower() and data.get("resolved") is True:
                # DNS is healthy -> Shift to DHCP or general Network
                return True, "DNS resolution succeeded; root cause is not DNS cache/lookup failure.", TroubleshootingDomain.NETWORK

        # 2. Service hypothesis contradicted if service is already running
        if hypothesis.category == TroubleshootingDomain.SERVICES.value or "service" in hypothesis.statement.lower():
            status = data.get("status") or data.get("state")
            if status and str(status).lower() in ("running", "active"):
                return True, f"Service reported running as expected ({status}).", TroubleshootingDomain.PERFORMANCE

        # 3. Storage hypothesis contradicted if free space is abundant (> 20GB)
        if hypothesis.category == TroubleshootingDomain.STORAGE.value:
            free_gb = data.get("free_gb") or data.get("free_space_gb")
            if isinstance(free_gb, (int, float)) and free_gb > 20:
                return True, f"Sufficient free disk space available ({free_gb} GB).", TroubleshootingDomain.PERFORMANCE

        # 4. Defender hypothesis contradicted if real-time protection is enabled and active
        if hypothesis.category == TroubleshootingDomain.WINDOWS_DEFENDER.value:
            if data.get("antivirus_enabled") is True and data.get("realtime_protection") is True:
                return True, "Defender antivirus and realtime protection are fully active.", TroubleshootingDomain.SERVICES

        return False, "", None

    def _is_supporting(self, hypothesis: DiagnosticHypothesis, evidence: EvidenceItem) -> bool:
        """Check if telemetry facts support the current hypothesis."""
        data = evidence.value if isinstance(evidence.value, dict) else {}

        # DNS failure evidence
        if "dns" in hypothesis.statement.lower():
            if data.get("resolved") is False or data.get("dns_resolved") is False:
                return True

        # Service stopped
        if "service" in hypothesis.statement.lower() or hypothesis.category == TroubleshootingDomain.SERVICES.value:
            status = data.get("status") or data.get("state")
            if status and str(status).lower() in ("stopped", "inactive", "disabled"):
                return True

        # Temp cache pressure (> 5GB or > 1000 files)
        if "temp" in hypothesis.statement.lower() or hypothesis.category == TroubleshootingDomain.STORAGE.value:
            size_mb = data.get("total_size_mb") or data.get("size_mb")
            if isinstance(size_mb, (int, float)) and size_mb > 1000:
                return True

        # CPU/Memory pressure
        if hypothesis.category == TroubleshootingDomain.PERFORMANCE.value:
            cpu = data.get("cpu_percent") or data.get("cpu_usage")
            mem = data.get("memory_percent") or data.get("memory_usage")
            if (isinstance(cpu, (int, float)) and cpu > 85) or (isinstance(mem, (int, float)) and mem > 85):
                return True

        return False


    def _create_fallback_hypothesis(self, reason: str) -> DiagnosticHypothesis:
        return DiagnosticHypothesis(
            hypothesis_id=f"hyp-fallback-{uuid.uuid4().hex[:6]}",
            category=TroubleshootingDomain.UNKNOWN.value,
            statement=f"Diagnostic inconclusive ({reason}).",
            status=HypothesisStatus.UNRESOLVED,
        )
