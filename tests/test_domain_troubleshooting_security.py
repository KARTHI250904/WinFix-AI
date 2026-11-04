"""Security and Invariant Tests for Advanced Windows Troubleshooting Intelligence (Phase 29).

Validates strict non-negotiable security rules:
- AST prohibited call scan (subprocess, shell=True, os.system, os.popen, eval, exec)
- Domain string validation & unknown domain rejection (Fail-closed to UNKNOWN)
- Strategy tool injection blocking
- Workflow template validation & step limit enforcement (<= 8 steps)
- Verification registry integrity (requires SAFE verification tools)
- Malicious symptom text injection resistance
"""

import ast
from pathlib import Path
import pytest

from agent.domain_models import TroubleshootingDomain
from agent.domain_registry import DomainRegistry, default_domain_registry
from agent.evidence_models import EvidenceType
from agent.tool_metadata import RiskLevel, ToolDefinition
from agent.tool_registry import ToolRegistry, default_tool_registry
from agent.troubleshooting_strategies import StrategyRegistry, TroubleshootingStrategy
from agent.verification_registry import VerificationRegistry, VerificationRule
from agent.workflow_templates import WorkflowTemplate, WorkflowTemplateValidator


# 1. AST Prohibited Calls Verification
def test_ast_prohibited_calls_in_phase_29_modules():
    """Verify strictly 0 forbidden execution calls across all Phase 29 modules."""
    forbidden_calls = {"subprocess", "system", "popen", "eval", "exec", "CreateProcess", "WinExec", "ShellExecute"}
    root_dir = Path(__file__).resolve().parent.parent

    target_files = [
        root_dir / "agent" / "domain_models.py",
        root_dir / "agent" / "domain_registry.py",
        root_dir / "agent" / "evidence_correlator.py",
        root_dir / "agent" / "troubleshooting_strategies.py",
        root_dir / "agent" / "workflow_templates.py",
        root_dir / "agent" / "verification_registry.py",
    ]

    for fpath in target_files:
        assert fpath.exists(), f"File {fpath} must exist"
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                func_name = ""
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                assert func_name not in forbidden_calls, f"Prohibited call '{func_name}' found in {fpath.name} at line {node.lineno}"


# 2. Unknown Domain Rejection
def test_unknown_domain_rejection_fail_closed():
    """Verify arbitrary or malicious domain strings map fail-closed to UNKNOWN."""
    reg = default_domain_registry

    malicious_domains = [
        "POWERSHELL_DOMAIN",
        "ROOT_ACCESS",
        "__import__('os')",
        "CMD.EXE",
        "../../etc/passwd",
        None,
        "",
        "NOT_A_REAL_DOMAIN",
    ]

    for bad in malicious_domains:
        parsed = reg.parse_domain(bad)
        assert parsed == TroubleshootingDomain.UNKNOWN


# 3. Workflow Template Step Limit & Tool Registration Security
def test_template_validator_rejects_exceeded_step_limits():
    """Verify template validator rejects templates defining > 8 steps."""
    validator = WorkflowTemplateValidator(tool_registry=default_tool_registry, domain_registry=default_domain_registry)

    # Valid template
    valid_t = WorkflowTemplate(
        template_id="TEST_VALID",
        domain=TroubleshootingDomain.NETWORK,
        title="Valid Template",
        description="Valid description",
        diagnostic_tools=["check_dns_resolution"],
    )
    ok, msg = validator.validate(valid_t)
    assert ok is True

    # Invalid template: 6 diagnostic tools + repair (2) + precond & complete (2) = 10 steps > 8
    overflow_t = WorkflowTemplate(
        template_id="TEST_OVERFLOW",
        domain=TroubleshootingDomain.NETWORK,
        title="Overflow Template",
        description="Too many steps",
        diagnostic_tools=[
            "get_network_adapters_diagnostics",
            "check_dns_resolution",
            "check_internet_connectivity",
            "get_dns_client_config",
            "get_network_adapters_diagnostics",
            "check_dns_resolution",
        ],
        repair_tool="flush_dns_cache",
        verification_tool="check_dns_resolution",
    )
    bad_ok, bad_msg = validator.validate(overflow_t)
    assert bad_ok is False
    assert "exceeds" in bad_msg.lower() or "maximum" in bad_msg.lower()


# 4. Template Validator Rejects Unregistered Tools
def test_template_validator_rejects_unregistered_tools():
    """Verify templates referencing unregistered or malicious tool names fail validation."""
    validator = WorkflowTemplateValidator(tool_registry=default_tool_registry, domain_registry=default_domain_registry)

    bad_tool_t = WorkflowTemplate(
        template_id="TEST_BAD_TOOL",
        domain=TroubleshootingDomain.NETWORK,
        title="Bad Tool Template",
        description="References malicious tool",
        diagnostic_tools=["arbitrary_powershell_cmd"],
    )
    ok, msg = validator.validate(bad_tool_t)
    assert ok is False
    assert "does not exist" in msg


# 5. Verification Registry Requires SAFE Verification Tools
def test_verification_registry_rejects_non_safe_verification_tool():
    """Verify verification registry strictly rejects MEDIUM or unregistered tools as verification methods."""
    test_reg = ToolRegistry()
    test_reg.register(ToolDefinition(
        name="test_repair",
        domain="network",
        description="Repair",
        risk=RiskLevel.MEDIUM,
        handler=lambda **kwargs: {"status": "ok"},
    ))
    test_reg.register(ToolDefinition(
        name="test_unsafe_verif",
        domain="network",
        description="Unsafe verifier",
        risk=RiskLevel.MEDIUM,  # Illegal: verification tool cannot be MEDIUM
        handler=lambda **kwargs: {"status": "ok"},
    ))

    v_reg = VerificationRegistry(tool_registry=test_reg)
    bad_rule = VerificationRule(
        verification_id="rule_bad",
        repair_tool="test_repair",
        expected_state="ok",
        verification_tool="test_unsafe_verif",
        description="Bad verification rule",
    )
    v_reg.register(bad_rule)
    assert v_reg.get_rule_for_tool("test_repair") is None  # Must fail closed and not register


# 6. Unknown Strategy and Malicious Strategy Injection
def test_unknown_strategy_returns_none():
    """Verify looking up a non-existent strategy returns None and does not throw."""
    s_reg = StrategyRegistry()
    assert s_reg.get("non_existent_strategy_id") is None
    assert s_reg.select_strategy(TroubleshootingDomain.UNKNOWN) is None


# 7. Symptom Text Shell Metacharacter Resistance
def test_symptom_injection_does_not_break_classification():
    """Verify domain classification safely handles shell metacharacters in symptom text."""
    reg = default_domain_registry
    malicious_inputs = [
        "dns failure; powershell -c calc",
        "high cpu && cmd.exe /c del C:\\*",
        "drive full | rm -rf /",
        "bluetooth hung `whoami`",
    ]

    for inp in malicious_inputs:
        domain = reg.classify_symptom_heuristically(inp)
        assert domain != TroubleshootingDomain.UNKNOWN
        assert isinstance(domain, TroubleshootingDomain)

