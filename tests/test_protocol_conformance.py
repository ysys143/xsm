"""Verify the external checker with an independent fixture and deliberate faults."""
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("blackbox_conformance", ROOT / "scripts/conform-host-protocol.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ExternalConformanceTest(unittest.TestCase):
    def test_peer_rejects_non_utf8_duplicate_keys_and_non_json_constants(self):
        frame = '{"jsonrpc":"2.0","id":1,"result":{}}\n'
        invalid = [frame.encode('utf-16-be'), frame.encode('utf-32-be'),
                   b'{"jsonrpc":"2.0","id":1,"result":{},"result":{}}\n',
                   b'{"jsonrpc":"2.0","id":1,"result":{"value":NaN}}\n']
        with tempfile.TemporaryDirectory(prefix='xsm-checker-wire-') as folder:
            env = {'HOME': folder, 'XSM_HOME': folder + '/state'}
            for wire in invalid:
                with self.subTest(wire=wire[:30]):
                    process = mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO(wire))
                    with mock.patch.object(checker.subprocess, 'Popen', return_value=process):
                        peer = checker.Peer(['fixture-only'], folder, env)
                    try:
                        with self.assertRaises((ValueError, RuntimeError)):
                            peer.call('initialize', {'protocolVersion': '1'})
                    finally:
                        peer.close()

    def test_peer_rejects_unisolated_environment_before_starting_candidate(self):
        with tempfile.TemporaryDirectory(prefix='xsm-conformance-guard-') as folder:
            variants = ({}, {'HOME': folder}, {'XSM_HOME': folder + '/state'},
                        {'HOME': str(Path.home()), 'XSM_HOME': folder + '/state'},
                        {'HOME': folder, 'XSM_HOME': str(Path.home() / '.xsm')})
            with mock.patch.object(checker.subprocess, 'Popen', side_effect=AssertionError('unsafe process launch reached')) as spawn:
                for environment in variants:
                    with self.subTest(keys=sorted(environment)):
                        with self.assertRaisesRegex(ValueError, 'isolated HOME and XSM_HOME'):
                            checker.Peer(['must-not-start'], folder, environment)
                self.assertFalse(spawn.called)

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
        if fault == 'none':
            return [sys.executable, '-B', '-c',
                "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
                str(ROOT), 'protocol', 'serve', '--stdio']
        return [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_delivery_fault.py'), fault]

    def test_actual_server_delivery_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='messaging')
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 33)

    def test_actual_server_discovery_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='discovery', capture=True)
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 24)
        discovered = [row['frame']['result'] for row in result['observations']
                      if row.get('operation') == 'xsm_discover' and 'result' in row['frame']]
        self.assertEqual(len(discovered), 4)

    def test_discovery_private_home_leak_is_detected(self):
        result = checker.run(self.delivery_candidate('discovery-private-home'), suite='discovery')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'discovery exposes no local home or process identity')

    def test_discovery_missing_observation_source_is_detected(self):
        result = checker.run(self.delivery_candidate('discovery-missing-source'), suite='discovery')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'discovery observations retain source and freshness')

    def test_ignored_targeted_inbox_filter_is_detected(self):
        result = checker.run(self.delivery_candidate('ignore-inbox-filter'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'targeted inbox returns current owned token')

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

    def test_actual_notification_is_captured_and_preserves_original(self):
        result = checker.run(self.delivery_candidate('none'), suite='events', capture=True)
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 36)
        events = [entry['frame'] for entry in result['observations'] if 'method' in entry['frame']]
        self.assertTrue(events, result)
        self.assertEqual(events[0]['method'], 'events/available')

    def test_actual_host_decision_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='decisions', capture=True)
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 35)
        methods = {e.get('method') for e in result['observations'] if 'result' in e['frame']}
        self.assertIn('decision.response', methods)
        self.assertIn('decision.abandon', methods)
        self.assertTrue(any(e['frame'].get('method') == 'decision/request' for e in result['observations']))

    def test_changed_display_acceptance_is_detected(self):
        command = [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_decision_fault.py'), 'ignore-display']
        result = checker.run(command, suite='decisions')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'changed display cannot answer')

    def test_automatic_decision_application_is_detected(self):
        command = [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_decision_fault.py'), 'auto-apply']
        result = checker.run(command, suite='decisions')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'stored answer has host source and no applied effect')
