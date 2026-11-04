"""Tests for Phase 34 Diagnostic Accuracy Across All Domains.

Validates that symptom classifications accurately map to correct Windows troubleshooting domains.
"""

import pytest
from agent.domain_models import TroubleshootingDomain
from agent.domain_registry import default_domain_registry
from agent.evaluation_dataset import get_evaluation_dataset
from agent.evaluation_engine import EvaluationEngine


@pytest.fixture
def engine():
    return EvaluationEngine()


def test_network_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.NETWORK]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0


def test_performance_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.PERFORMANCE]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0


def test_storage_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.STORAGE]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0


def test_services_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.SERVICES]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0


def test_windows_update_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.WINDOWS_UPDATE]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0


def test_defender_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.WINDOWS_DEFENDER]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0


def test_bluetooth_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.BLUETOOTH]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0


def test_application_crash_domain_diagnostic_accuracy(engine):
    dataset = [s for s in get_evaluation_dataset() if s.domain == TroubleshootingDomain.APPLICATION_CRASH]
    assert len(dataset) >= 5
    for sc in dataset:
        res = engine.evaluate_scenario(sc)
        assert res.domain_matched is True
        assert res.unregistered_tools_count == 0
