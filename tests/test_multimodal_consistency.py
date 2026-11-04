"""Tests for Phase 34 Multimodal Diagnostic Consistency.

Validates semantic consistency across Text, Screenshot, and Voice modalities
ensuring equivalent evidence yields consistent domain inference and tool selection.
"""

import unittest

from agent.domain_models import TroubleshootingDomain
from agent.domain_registry import default_domain_registry
from agent.evaluation_engine import EvaluationEngine
from agent.evaluation_models import (
    EvaluationOutcome,
    EvaluationScenario,
)


class TestMultimodalConsistency(unittest.TestCase):
    def test_multimodal_text_and_voice_consistency(self):
        engine = EvaluationEngine()
        
        # Text modality
        text_scenario = EvaluationScenario(
            scenario_id="MULTI-TEXT-01",
            domain=TroubleshootingDomain.NETWORK,
            symptoms="DNS resolution failure, cannot reach google.com.",
            expected_domain=TroubleshootingDomain.NETWORK,
            expected_safe_tools=["check_dns_resolution"],
        )
        # Voice modality (transcript)
        voice_scenario = EvaluationScenario(
            scenario_id="MULTI-VOICE-01",
            domain=TroubleshootingDomain.NETWORK,
            symptoms="Hey WinFix, my DNS is not resolving and I can't open websites.",
            expected_domain=TroubleshootingDomain.NETWORK,
            expected_safe_tools=["check_dns_resolution"],
        )
        
        text_res = engine.evaluate_scenario(text_scenario)
        voice_res = engine.evaluate_scenario(voice_scenario)
        
        self.assertTrue(text_res.domain_matched)
        self.assertTrue(voice_res.domain_matched)
        self.assertEqual(text_res.domain, voice_res.domain)

    def test_multimodal_screenshot_evidence_consistency(self):
        engine = EvaluationEngine()
        screenshot_scenario = EvaluationScenario(
            scenario_id="MULTI-SCREEN-01",
            domain=TroubleshootingDomain.PERFORMANCE,
            symptoms="Task Manager screenshot shows CPU at 99%.",
            initial_evidence=[{"tool": "get_cpu_diagnostics", "result": {"cpu_percent": 99.0}}],
            expected_domain=TroubleshootingDomain.PERFORMANCE,
            expected_safe_tools=["get_cpu_diagnostics"],
        )
        res = engine.evaluate_scenario(screenshot_scenario)
        self.assertTrue(res.domain_matched)
        self.assertEqual(res.outcome, EvaluationOutcome.PASS)
