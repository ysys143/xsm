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
