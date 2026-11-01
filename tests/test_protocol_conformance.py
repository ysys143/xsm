"""Verify the external checker with an independent fixture and deliberate faults."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("blackbox_conformance", ROOT / "scripts/conform-host-protocol.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ExternalConformanceTest(unittest.TestCase):
    def candidate(self, fault=""):
        return [sys.executable, "-B", str(ROOT / "tests/fixtures/minimal_protocol_host.py"), fault]

    def test_independent_lifecycle_fixture_passes_without_user_environment(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-inherit"}):
            result = checker.run(self.candidate())
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(len(result["checks"]), 16)

    def test_constant_generation_is_detected(self):
        result = checker.run(self.candidate("constant-generation"))
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["activeCheck"], "stable address new generation")

    def test_cross_connection_handle_is_detected(self):
        result = checker.run(self.candidate("shared-handles"))
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["activeCheck"], "connection-local handles")

    def test_missing_lifetime_lock_is_detected(self):
        result = checker.run(self.candidate("skip-lock"))
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["activeCheck"], "single live conversation owner")

    def delivery_candidate(self, fault):
        return [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_delivery_fault.py'), fault]

    def test_actual_server_delivery_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='messaging')
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['checks']), 29)

    def test_automatic_consumption_on_admission_is_detected(self):
        result = checker.run(self.delivery_candidate('auto-consume-admitted'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'admitted original survives generation change')

    def test_reused_claim_token_is_detected(self):
        result = checker.run(self.delivery_candidate('reuse-token'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'retry rotates claim token')

    def test_successful_foreign_ack_response_is_detected(self):
        result = checker.run(self.delivery_candidate('accept-foreign-ack'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'foreign consumer cannot acknowledge')
