"""Network Diagnostic Orchestrator for WinFix AI (Phase 6).

Coordinates evidence collection across approved read-only network diagnostic tools,
enforces evidence-based diagnosis (distinguishing observations from interpretations),
and integrates with SafetyEngine and AgentPlanner.

Strictly read-only: NO network repair or state-modifying actions are performed in this phase.
"""

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any, Dict, List, Optional

from agent.agent_response import AgentResponse, ToolRequest, parse_agent_response
from agent.safety import SafetyEngine, default_safety_engine
from agent.tool_registry import ToolRegistry, default_tool_registry
from ai.ollama_client import OllamaClient, ollama_client
from database.db import DatabaseManager, db_manager as default_db_manager
from database.repositories import DiagnosticRepository, SessionRepository

logger = logging.getLogger(__name__)

# Valid network problem categories
NETWORK_CATEGORIES = {
    "adapter",
    "ip_configuration",
    "dns",
    "connectivity",
    "host_reachability",
    "unknown",
}


@dataclass
class NetworkDiagnosis:
    """Structured, evidence-based network diagnosis result."""

    problem_category: str
    summary: str
    observed_evidence: List[str] = field(default_factory=list)
    interpretation: List[str] = field(default_factory=list)
    confidence: float = 0.8
    recommended_next_steps: List[str] = field(default_factory=list)
    repair_available: bool = False
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize diagnosis result to dictionary."""
        return {
            "problem_category": self.problem_category,
            "summary": self.summary,
            "observed_evidence": self.observed_evidence,
            "interpretation": self.interpretation,
            "confidence": self.confidence,
            "recommended_next_steps": self.recommended_next_steps,
            "repair_available": self.repair_available,
            "tool_results": self.tool_results,
        }


def sanitize_hostname_target(target: Optional[str]) -> tuple[bool, str, Optional[str]]:
    """Validate and sanitize a network target hostname or IP address.

    Rejects shell metacharacters, spaces, paths, and invalid formatting.
    """
    if not target or not isinstance(target, str):
        return True, "dns.google", None

    cleaned = target.strip()
    if not cleaned:
        return True, "dns.google", None

    # Length boundary
    if len(cleaned) > 253:
        return False, "", "Hostname exceeds maximum length of 253 characters."

    # Forbidden shell metacharacters and control tokens
    forbidden_tokens = [";", "&", "|", "`", "$", "\n", "\r", "<", ">", "\\", "/", " ", "\t", '"', "'"]
    for tok in forbidden_tokens:
        if tok in cleaned:
            return False, "", f"Target hostname contains forbidden character '{tok}'."

    # Basic hostname / IP regex pattern check
    hostname_regex = r"^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$|^([0-9]{1,3}\.){3}[0-9]{1,3}$|^localhost$"
    if not re.match(hostname_regex, cleaned, re.IGNORECASE):
        # Also allow simple single-word intranet hostnames like 'router' or 'gateway'
        if not re.match(r"^[a-zA-Z0-9\-]{1,63}$", cleaned):
            return False, "", f"Invalid hostname or IP format: '{cleaned}'."

    return True, cleaned, None


class NetworkDiagnosticsOrchestrator:
    """Coordinates read-only network diagnostics, evidence collection, and synthesis."""

    def __init__(
        self,
        safety_engine: Optional[SafetyEngine] = None,
        registry: Optional[ToolRegistry] = None,
        client: Optional[OllamaClient] = None,
        db_mgr: Optional[DatabaseManager] = None,
    ) -> None:
        self.safety_engine = safety_engine or default_safety_engine
        self.registry = registry or default_tool_registry
        self.client = client or ollama_client
        self.db_manager = db_mgr or default_db_manager

        self.session_repo = SessionRepository(self.db_manager)
        self.diag_repo = DiagnosticRepository(self.db_manager)

    def classify_network_problem(self, problem_description: str) -> str:
        """Rule-based problem categorizer for network issues."""
        text = problem_description.lower()
        if any(w in text for w in ["wifi", "wi-fi", "adapter", "ethernet", "nic", "unplugged", "cable"]):
            return "adapter"
        if any(w in text for w in ["dns", "lookup", "resolve", "domain", "nameserver"]):
            return "dns"
        if any(w in text for w in ["ip", "dhcp", "subnet", "169.254", "apipa", "gateway", "address"]):
            return "ip_configuration"
        if any(w in text for w in ["reach", "ping", "website", "server", "host", "timeout", "port"]):
            return "host_reachability"
        if any(w in text for w in ["internet", "offline", "disconnect", "web", "slow", "connection"]):
            return "connectivity"
        return "unknown"

    def select_diagnostic_tools(
        self,
        category: str,
        custom_target: Optional[str] = None,
    ) -> List[ToolRequest]:
        """Select appropriate read-only network diagnostic tools based on categorized scenario."""
        valid, target_host, _ = sanitize_hostname_target(custom_target)
        if not valid:
            target_host = "dns.google"

        tools: List[ToolRequest] = []

        # Standard baseline network checks
        tools.append(
            ToolRequest(
                tool_name="get_network_adapters_diagnostics",
                arguments={},
                purpose="Inspect physical and wireless network interface link status and assigned IPs",
            )
        )

        if category in ("dns", "connectivity", "unknown"):
            tools.append(
                ToolRequest(
                    tool_name="get_dns_client_config",
                    arguments={},
                    purpose="Inspect configured DNS name servers from the Windows registry",
                )
            )
            tools.append(
                ToolRequest(
                    tool_name="check_dns_resolution",
                    arguments={"hostname": target_host, "timeout": 3.0},
                    purpose=f"Test DNS resolution latency for target '{target_host}'",
                )
            )
            tools.append(
                ToolRequest(
                    tool_name="check_internet_connectivity",
                    arguments={"target_host": "1.1.1.1", "port": 53, "timeout": 3.0},
                    purpose="Verify socket connectivity to public gateway (1.1.1.1:53)",
                )
            )
        elif category == "host_reachability":
            tools.append(
                ToolRequest(
                    tool_name="check_dns_resolution",
                    arguments={"hostname": target_host, "timeout": 3.0},
                    purpose=f"Resolve IP address for target host '{target_host}'",
                )
            )
            tools.append(
                ToolRequest(
                    tool_name="check_internet_connectivity",
                    arguments={"target_host": target_host, "port": 80, "timeout": 3.0},
                    purpose=f"Test TCP socket reachability for target '{target_host}:80'",
                )
            )
        elif category in ("adapter", "ip_configuration"):
            tools.append(
                ToolRequest(
                    tool_name="check_internet_connectivity",
                    arguments={"target_host": "1.1.1.1", "port": 53, "timeout": 3.0},
                    purpose="Check if local adapter can reach external network gateway",
                )
            )

        return tools

    def run_network_diagnostics(
        self,
        problem_description: str,
        custom_target: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> NetworkDiagnosis:
        """Execute structured network diagnostics through SafetyEngine and synthesize evidence."""
        category = self.classify_network_problem(problem_description)
        tool_requests = self.select_diagnostic_tools(category, custom_target)

        # 1. Execute each diagnostic tool strictly through SafetyEngine
        tool_results: List[Dict[str, Any]] = []
        for req in tool_requests:
            res = self.safety_engine.execute(
                tool_name=req.tool_name,
                arguments=req.arguments,
                session_id=session_id,
            )
            tool_results.append(
                {
                    "tool_name": req.tool_name,
                    "purpose": req.purpose,
                    "arguments": req.arguments,
                    "result": res,
                }
            )

        # 2. Extract structured observations directly from tool data
        observed_facts: List[str] = []
        interpretations: List[str] = []
        recommendations: List[str] = []
        repair_available = False

        adapters_ok = False
        ip_assigned = False
        dns_working = False
        internet_reachable = False

        for tr in tool_results:
            t_name = tr["tool_name"]
            res = tr["result"]
            success = res.get("success", False)
            data = res.get("data") or {}

            if t_name == "get_network_adapters_diagnostics":
                if success:
                    active_count = data.get("active_adapters", 0)
                    total_count = data.get("total_adapters", 0)
                    observed_facts.append(
                        f"Detected {total_count} total network adapter(s); {active_count} currently active with IP addresses."
                    )
                    adapters_list = data.get("adapters", [])
                    up_adapters = [a for a in adapters_list if a.get("is_up") and a.get("ipv4")]
                    if up_adapters:
                        adapters_ok = True
                        ip_assigned = True
                        for a in up_adapters:
                            ips = ", ".join(a.get("ipv4", []))
                            observed_facts.append(f"Adapter '{a.get('name')}' is connected with IPv4: {ips}")
                    else:
                        observed_facts.append("No active network adapters currently have an assigned IPv4 address.")
                        interpretations.append("Network adapter is either disconnected, disabled, or not receiving an IP address.")
                        repair_available = True
                else:
                    observed_facts.append("Failed to query network adapter hardware status.")

            elif t_name == "get_dns_client_config":
                if success:
                    servers = data.get("dns_servers", [])
                    if servers:
                        observed_facts.append(f"Configured DNS server(s) in Windows registry: {', '.join(servers)}")
                    else:
                        observed_facts.append("No static DNS servers explicitly configured in Windows registry (DHCP default).")

            elif t_name == "check_dns_resolution":
                target = tr.get("arguments", {}).get("hostname", "host")
                if success and data.get("resolved"):
                    dns_working = True
                    ips = ", ".join(data.get("resolved_ips", []))
                    latency = data.get("latency_ms", 0)
                    observed_facts.append(
                        f"DNS lookup for '{target}' succeeded ({latency} ms). Resolved IPs: {ips}"
                    )
                else:
                    observed_facts.append(f"DNS lookup for '{target}' failed to resolve any IP addresses.")
                    interpretations.append(f"DNS resolution failure: Host '{target}' cannot be translated to an IP address.")
                    repair_available = True

            elif t_name == "check_internet_connectivity":
                tgt = data.get("target") or tr.get("arguments", {}).get("target_host", "gateway")
                if success and data.get("reachable"):
                    internet_reachable = True
                    latency = data.get("latency_ms", 0)
                    observed_facts.append(f"Socket connection to {tgt} succeeded ({latency} ms).")
                else:
                    observed_facts.append(f"Socket connection to {tgt} failed or timed out.")
                    interpretations.append("Outbound internet connectivity is blocked or the default gateway is unreachable.")
                    repair_available = True

        # 3. Formulate Evidence-Based Interpretations and Recommendations
        if adapters_ok and ip_assigned and dns_working and internet_reachable:
            summary = "Local network configuration, DNS resolution, and outbound internet connectivity are fully operational."
            interpretations.append("The physical adapter, IP stack, DNS, and external gateway reachability are functioning normally.")
            recommendations.append("If a specific website fails to open, verify the web address or check if the destination server is down.")
        elif not adapters_ok or not ip_assigned:
            summary = "Network adapter is disconnected or missing an assigned IP address."
            recommendations.append("Check physical Ethernet cable connection or ensure Wi-Fi is toggled on and connected to your router.")
            recommendations.append("Verify router DHCP status to ensure IP addresses are being assigned.")
        elif adapters_ok and ip_assigned and not dns_working and internet_reachable:
            summary = "Internet connection is active, but DNS name resolution is failing."
            interpretations.append("Your computer can communicate via IP address, but cannot translate domain names into IP addresses.")
            recommendations.append("Verify DNS server settings or test public DNS providers (e.g. 1.1.1.1 or 8.8.8.8).")
        elif adapters_ok and ip_assigned and not internet_reachable:
            summary = "Connected to local network, but no internet access."
            interpretations.append("Local adapter has an IP address, but traffic cannot pass through the gateway to the wider internet.")
            recommendations.append("Check modem / router internet uplink status.")
            recommendations.append("Restart your router or verify ISP connectivity.")
        else:
            summary = "Network diagnostics completed. Several connectivity checks failed."
            interpretations.append("Evidence indicates an issue with network routing, adapter status, or DNS reachability.")
            recommendations.append("Review detailed tool observations below to isolate the failing component.")

        # 4. Optional Gemma LLM Synthesis if available
        if self.client and self.client.is_available():
            try:
                gemma_synth = self._synthesize_with_gemma(
                    problem_description=problem_description,
                    category=category,
                    observed_facts=observed_facts,
                    interpretations=interpretations,
                )
                if gemma_synth:
                    summary = gemma_synth.get("summary", summary)
                    if gemma_synth.get("observed_evidence"):
                        observed_facts = gemma_synth["observed_evidence"]
                    if gemma_synth.get("interpretation"):
                        interpretations = gemma_synth["interpretation"]
                    if gemma_synth.get("recommended_next_steps"):
                        recommendations = gemma_synth["recommended_next_steps"]
            except Exception as llm_err:
                logger.debug("Gemma synthesis fallback note: %s", llm_err)

        diagnosis = NetworkDiagnosis(
            problem_category=category,
            summary=summary,
            observed_evidence=observed_facts,
            interpretation=interpretations,
            confidence=0.9 if tool_results else 0.5,
            recommended_next_steps=recommendations,
            repair_available=repair_available,
            tool_results=tool_results,
        )

        # 5. Persist to SQLite repository if session_id is provided
        if session_id:
            try:
                self.diag_repo.create(
                    session_id=session_id,
                    tool_name="network_diagnostics",
                    status="completed",
                    evidence_json=json.dumps(diagnosis.to_dict(), default=str),
                )
            except Exception as db_err:
                logger.debug("Network diagnosis DB persist note: %s", db_err)

        return diagnosis

    def _synthesize_with_gemma(
        self,
        problem_description: str,
        category: str,
        observed_facts: List[str],
        interpretations: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Ask Gemma to refine the diagnostic explanation while strictly preserving observed facts."""
        prompt_payload = {
            "problem": problem_description,
            "category": category,
            "observed_facts": observed_facts,
            "technical_interpretations": interpretations,
        }

        system_prompt = """You are WinFix AI Network Diagnostics Assistant.
Synthesize the verified network diagnostic facts into an accurate, user-friendly explanation.

CRITICAL RULES:
1. Do NOT invent observations that are not in observed_facts.
2. Clearly separate observed facts from interpretations.
3. Suggest only safe next steps for the user. Do NOT suggest executing shell commands.

Return valid JSON conforming to:
{
  "summary": "<plain English summary>",
  "observed_evidence": ["<fact 1>", "<fact 2>"],
  "interpretation": ["<what facts indicate>"],
  "recommended_next_steps": ["<safe advice 1>", "<safe advice 2>"]
}
"""
        res = self.client.generate(
            prompt=json.dumps(prompt_payload),
            system=system_prompt,
            format="json",
        )
        if res["success"]:
            ok, parsed, _ = parse_agent_response(res["response"])
            if ok and parsed and parsed.raw_json:
                return parsed.raw_json
        return None


# Default shared network diagnostic orchestrator
default_network_orchestrator = NetworkDiagnosticsOrchestrator()
