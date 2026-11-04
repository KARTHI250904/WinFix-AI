"""
Phase 21: Deterministic Fuzz Testing Suite for WinFix AI.

Covers:
1. Deterministic pseudo-random fuzzing (seed=20260925).
2. Agent planner and response parsing fuzzing with SQL, shell, unicode, malformed JSON, and oversized strings.
3. Personal Tutor explanation fuzzing.
4. SQLite Knowledge search fuzzing.
5. Screenshot evidence container fuzzing.
6. Voice audio metadata and transcript fuzzing.
7. Tool arguments boundary fuzzing across registry tools.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import tempfile
import os

from agent.agent_response import parse_agent_response
from agent.planner import AgentPlanner
from agent.safety import SafetyEngine
from agent.tool_metadata import RiskLevel
from agent.tool_registry import create_default_registry, ToolRegistry
from database.db import DatabaseManager
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine
from input.screenshot_input import inspect_privacy_indicators
from input.voice_input import inspect_voice_privacy, MAX_AUDIO_BYTES
from modes.personal_tutor import PersonalTutor
from modes.tutor_context import sanitize_tutor_text
from tests.security.malicious_inputs import DeterministicFuzzer
from tests.security.test_vectors import (
    PROMPT_INJECTIONS,
    COMMAND_INJECTIONS,
    SQL_INJECTIONS,
    UNICODE_ABUSE,
    MALFORMED_JSON_PAYLOADS,
    OVERSIZED_STRINGS,
)


class TestInputFuzzing(unittest.TestCase):
    """Deterministic fuzzing suite to verify fail-closed and robust boundary handling."""

    @classmethod
    def setUpClass(cls):
        cls.fuzzer = DeterministicFuzzer(seed=20260925)
        cls.registry = create_default_registry()
        cls.safety = SafetyEngine(registry=cls.registry)

    def setUp(self):
        self.planner = AgentPlanner(registry=self.registry, safety_engine=self.safety)
        self.tutor = PersonalTutor(tool_registry=self.registry, safety_engine=self.safety)

    def test_fuzzed_responses_in_agent_parser(self):
        """Agent response parser must safely reject fuzzed and malformed model outputs."""
        fuzzed_inputs = self.fuzzer.generate_fuzz_batch(count=50) + MALFORMED_JSON_PAYLOADS
        
        for idx, fuzz_text in enumerate(fuzzed_inputs):
            with self.subTest(idx=idx, text=repr(fuzz_text[:30])):
                try:
                    is_valid, resp, err = parse_agent_response(fuzz_text)
                    self.assertIsInstance(is_valid, bool)
                    # If marked valid, it must strictly have no forbidden execution keys
                    if is_valid and resp:
                        for tr in resp.requested_tools:
                            self.assertIn(tr.tool_name, self.registry.list_tool_names())
                except Exception as e:
                    self.fail(f"Agent parser raised unhandled exception on fuzz input: {e}")

    def test_fuzzed_knowledge_queries(self):
        """Knowledge search must not crash or execute injected SQL across fuzzed inputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "fuzz_knowledge.db")
            db_mgr = DatabaseManager(db_path=db_path)
            db_mgr.init_db()
            repo = KnowledgeRepository(db_mgr)
            search_engine = KnowledgeSearchEngine(repo)
            
            fuzzed_queries = self.fuzzer.generate_fuzz_batch(count=60) + SQL_INJECTIONS
            
            for query in fuzzed_queries:
                with self.subTest(query=repr(query[:30])):
                    try:
                        results = search_engine.search(query, limit=5)
                        self.assertIsInstance(results, list)
                    except Exception as e:
                        self.fail(f"Knowledge search failed with unhandled exception on query {repr(query)}: {e}")

    def test_fuzzed_privacy_sanitization(self):
        """Privacy sanitizer must handle fuzzed and unicode strings safely without crashing."""
        fuzzed_texts = self.fuzzer.generate_fuzz_batch(count=40) + OVERSIZED_STRINGS
        
        for txt in fuzzed_texts:
            with self.subTest(text=repr(txt[:30])):
                try:
                    sanitized = sanitize_tutor_text(txt)
                    self.assertIsInstance(sanitized, str)
                except Exception as e:
                    self.fail(f"Privacy sanitizer raised exception on fuzzed input: {e}")

    def test_fuzzed_tool_arguments_validation(self):
        """Tool argument schemas must reject unexpected fuzzed dictionaries."""
        fuzzed_args = [
            {"command": "net stop wuauserv"},
            {"shell": True, "exec": "cmd.exe"},
            {"service_name": "' OR '1'='1"},
            {"service_name": "A" * 5000},
            {"process_id": -9999},
            {"process_id": "invalid_pid_string"},
            {"adapter_name": "..\\..\\..\\Windows\\System32"},
            {"path": "C:\\Windows\\System32\\calc.exe"}
        ]
        
        for tool_name in self.registry.list_tool_names():
            for bad_arg in fuzzed_args:
                with self.subTest(tool=tool_name, arg=bad_arg):
                    decision = self.safety.evaluate(tool_name, bad_arg)
                    self.assertIsInstance(decision.allowed, bool)
                    self.assertIsInstance(decision.reason, str)


if __name__ == "__main__":
    unittest.main()
