"""Native OpenCode event semantics and managed provider admission, model0."""
import copy
import json
import os
from pathlib import Path
import sys
from unittest import mock
from tests.test_xsm import TempState


class OpenCodeWorkerTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import native_workers
        self.provider = native_workers._load_provider('opencode', Path(__file__).resolve().parents[1] /
                                                      'integrations/opencode/worker_provider.py')
        self.cli = sys.modules[self.provider.__package__ + '.worker_cli']

    def events(self):
        return [dict(type=kind, sessionID='ses_native', part=dict(sessionID='ses_native', **part))
                for kind, part in [('step_start', {}), ('text', {'text': 'actual answer'}),
                                   ('step_finish', {'reason': 'stop'})]]

    def parse(self, events, context=None):
        return self.cli.parse_result('\n'.join(json.dumps(event) for event in events), context or {})

    def test_only_actual_complete_native_answer_is_accepted(self):
        result = self.parse(self.events(), {'native_session_id': 'ses_native'})
        self.assertEqual(result['body'], 'actual answer')
        self.assertEqual(result['native_evidence']['finish_reason'], 'stop')

    def test_native_abort_readback_has_no_business_answer(self):
        output = json.dumps(dict(type='error', sessionID='ses_native', error={'name': 'MessageAbortedError'}))
        result = self.cli.parse_cancellation(output, {'native_session_id': 'ses_native'})
        self.assertEqual(result['native_evidence']['native_state'], 'stopped')
        self.assertNotIn('body', result)
        with self.assertRaises(self.cli.NativeCliError): self.cli.parse_result(output, {'native_session_id': 'ses_native'})

    def test_error_text_or_another_session_is_not_native_abort_proof(self):
        for error in ({'name': 'APIError', 'data': {'message': 'Aborted'}}, {'message': 'MessageAbortedError'}):
            with self.assertRaises(self.cli.NativeCliError):
                self.cli.parse_cancellation(json.dumps(dict(type='error', sessionID='ses_native', error=error)),
                                            {'native_session_id': 'ses_native'})
        output = json.dumps(dict(type='error', sessionID='ses_other', error={'name': 'MessageAbortedError'}))
        for context in ({}, {'native_session_id': 'ses_native'}):
            with self.assertRaises(self.cli.NativeCliError): self.cli.parse_cancellation(output, context)

    def test_frontend_observation_covers_native_cli_without_an_error_event(self):
        observed = dict(type='xsm_native_cancelled', source='opencode/1.19.5', sessionID='ses_native',
                        native_input_message_id='msg_input', native_assistant_message_id='msg_assistant',
                        native_error='MessageAbortedError', native_completed=123, native_idle=True)
        context = {'native_session_id': 'ses_native'}
        result = self.cli.parse_cancellation(json.dumps(observed), context)
        self.assertEqual(result['native_evidence']['terminal_event'], 'xsm_native_cancelled')
        self.assertNotIn('body', result)
        for changes in ({'native_idle': 1}, {'native_error': 'APIError'}, {'source': 'model'},
                        {'native_completed': True}, {'native_input_message_id': None}):
            with self.subTest(changes=changes), self.assertRaises(self.cli.NativeCliError):
                self.cli.parse_cancellation(json.dumps(dict(observed, **changes)), context)
        for trailing in (observed, dict(type='step_start', sessionID='ses_native'),
                         dict(type='error', sessionID='ses_native', error=[])):
            with self.subTest(trailing=trailing), self.assertRaises(self.cli.NativeCliError):
                self.cli.parse_cancellation(json.dumps(observed) + '\n' + json.dumps(trailing), context)

    def test_failed_incomplete_or_changed_native_turn_is_refused(self):
        baseline = self.events()
        variants = [baseline[:-1], baseline[1:], baseline + [baseline[1]],
                    baseline + [dict(type='error', sessionID='ses_native')]]
        for mutation in ({'reason': 'length'}, {'reason': 'tool-calls'}):
            changed = copy.deepcopy(baseline); changed[-1]['part'].update(mutation); variants.append(changed)
        changed = copy.deepcopy(baseline); changed[1]['sessionID'] = 'ses_other'; variants.append(changed)
        changed = copy.deepcopy(baseline); changed[1]['part']['sessionID'] = 'ses_other'; variants.append(changed)
        for events in variants:
            with self.subTest(events=events), self.assertRaises(self.cli.NativeCliError):
                self.parse(events)
        with self.assertRaises(self.cli.NativeCliError):
            self.parse(baseline, {'native_session_id': 'ses_different'})

    def test_intermediate_tool_step_cannot_become_final_answer(self):
        first = self.events(); first[-1]['part']['reason'] = 'tool-calls'
        self.assertEqual(self.parse(first + self.events())['body'], 'actual answer')
        with self.assertRaises(self.cli.NativeCliError):
            self.parse(first + [dict(type='step_start', sessionID='ses_native', part={'sessionID': 'ses_native'})])

    def test_non_json_and_duplicate_fields_are_refused(self):
        for output in ('noise', '[]', '{"type":"error","type":"step_finish"}',
                       '{"type":"text","part":{"text":NaN}}'):
            with self.subTest(output=output), self.assertRaises(self.cli.NativeCliError):
                self.cli.parse_result(output, {})

    def test_command_resumes_exact_id_without_permission_overrides(self):
        command = self.cli.build_command('/native/opencode', {'model': 'provider/model', 'effort': 'high'},
                                         {'native_session_id': 'ses_native'})
        self.assertEqual(command, ['/native/opencode', 'run', '--format', 'json', '--session',
                                   'ses_native', '--model=provider/model', '--variant=high'])
        with self.assertRaises(self.cli.NativeCliError):
            self.cli.build_command('/native/opencode', {}, {'native_session_id': '--continue'})

    def test_managed_profile_and_pinned_binary_are_required(self):
        from xsm import host_install, native_workers
        home = str(Path(self.tmp, 'profile'))
        with self.assertRaises(native_workers.ProviderError): self.provider.prepare(home)
        host_install.apply('opencode', home)
        binary = Path(self.tmp, 'native-opencode')
        binary.write_text('#!' + sys.executable + '\nprint("1.19.5")\n'); binary.chmod(0o700)
        with mock.patch.dict(os.environ, {'XSM_OPENCODE': str(binary)}):
            descriptor = self.provider.prepare(home)
            self.assertEqual(descriptor['version'], '1.19.5')
            worker = dict(home=home, native_provider=descriptor)
            self.assertEqual(self.provider.argv(worker, {})[:4], [str(binary.resolve()), 'run', '--format', 'json'])
            descriptor['frontend_sha256'] = 'changed'
            with self.assertRaises(native_workers.ProviderError): self.provider.argv(worker, {})
            binary.write_text('#!' + sys.executable + '\nprint("1.19.6")\n')
            with self.assertRaises(native_workers.ProviderError): self.provider.prepare(home)

    def test_environment_drops_ambient_identity_and_inline_profile_overrides(self):
        base = dict(OPENCODE_CONFIG='/other', OPENCODE_CONFIG_CONTENT='other', XSM_WORKER='other',
                    XSM_OWNED_CONTROL_FD='9', XDG_DATA_HOME='/operator/data')
        actual = self.provider.environment({'home': '/native/profile'}, base)
        self.assertEqual(actual, {'OPENCODE_CONFIG_DIR': '/native/profile', 'XDG_DATA_HOME': '/operator/data'})
        self.assertIn('XSM_WORKER', base)
