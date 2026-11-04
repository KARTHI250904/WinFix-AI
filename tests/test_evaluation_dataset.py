"""Tests for Phase 34 Evaluation Dataset.

Validates domain coverage, scenario count (>=50), schema conformance, and privacy compliance.
"""

from agent.domain_models import TroubleshootingDomain
from agent.evaluation_dataset import get_evaluation_dataset
from agent.evaluation_models import EvaluationScenario


def test_dataset_scenario_count():
    dataset = get_evaluation_dataset()
    assert len(dataset) >= 50, f"Dataset must contain at least 50 scenarios, found {len(dataset)}"


def test_dataset_covers_all_11_domains():
    dataset = get_evaluation_dataset()
    domains_present = {sc.domain for sc in dataset}
    all_domains = set(TroubleshootingDomain)
    
    assert len(domains_present) == 11
    assert domains_present.issubset(all_domains)


def test_dataset_scenario_schema_conformance():
    dataset = get_evaluation_dataset()
    for sc in dataset:
        assert isinstance(sc, EvaluationScenario)
        assert sc.scenario_id and len(sc.scenario_id) > 0
        assert sc.symptoms and len(sc.symptoms) > 0
        assert isinstance(sc.domain, TroubleshootingDomain)
        assert isinstance(sc.expected_safe_tools, list)
        assert isinstance(sc.forbidden_tools, list)


def test_dataset_privacy_no_cleartext_credentials():
    dataset = get_evaluation_dataset()
    forbidden_terms = ["password=", "api_key=", "bearer ", "secret_key", "BEGIN RSA PRIVATE KEY"]
    
    for sc in dataset:
        for term in forbidden_terms:
            assert term not in sc.symptoms.lower()
            assert term not in str(sc.initial_evidence).lower()
            assert term not in str(sc.contradictory_evidence).lower()


def test_dataset_forbidden_tools_prohibit_arbitrary_exec():
    dataset = get_evaluation_dataset()
    allowed_forbidden = {
        "powershell", "cmd", "unregistered_tool", "invoke_secret_repair_tool",
        "clean_temp_files", "stop_service", "disable_defender", "restart_windows_service"
    }
    for sc in dataset:
        for forbidden in sc.forbidden_tools:
            assert forbidden in allowed_forbidden
