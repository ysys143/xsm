"""Pi settled-result and exact-session contracts, without a model."""
import copy
import json
import os
from pathlib import Path
import sys
from unittest import mock
from tests.test_xsm import TempState

SID = '12345678-1234-4234-8234-123456789abc'


class PiWorkerTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import native_workers
        self.provider = native_workers._load_provider('pi', Path(__file__).resolve().parents[1] /
                                                     'integrations/pi/worker_provider.py')
        self.cli = sys.modules[self.provider.__package__ + '.worker_cli']

    def events(self):
        return [dict(type='session', id=SID, cwd=self.tmp),
                dict(type='agent_end', willRetry=False, messages=[dict(role='assistant', stopReason='stop',
                     content=[dict(type='text', text='native answer')])]),
                dict(type='agent_settled', aborted=False)]

    def parse(self, events, context=None):
        return self.cli.parse_result('\n'.join(json.dumps(row) for row in events),
                                     context or {'session_seed': SID}, self.tmp)

    def test_settled_answer_matches_exact_native_session(self):
        result = self.parse(self.events())
        self.assertEqual((result['body'], result['native_session_id']), ('native answer', SID))
        self.assertEqual(result['native_evidence']['terminal_event'], 'agent_settled')

    def test_abort_retry_truncation_or_changed_identity_never_becomes_success(self):
        original = self.events()
        variants = [original[:-1], original[1:], original + [dict(type='agent_start')]]
        for slot, key, value in ((0, 'id', '22345678-1234-4234-8234-123456789abc'),
                                  (0, 'cwd', self.tmp + '/other'), (1, 'willRetry', True),
                                  (2, 'aborted', True), (2, 'aborted', 0)):
            changed = copy.deepcopy(original); changed[slot][key] = value; variants.append(changed)
        for reason in ('length', 'error', 'aborted', 'toolUse'):
            changed = copy.deepcopy(original); changed[1]['messages'][-1]['stopReason'] = reason; variants.append(changed)
        for events in variants:
            with self.subTest(events=events), self.assertRaises(self.cli.NativeCliError): self.parse(events)

    def test_previous_assistant_or_empty_text_does_not_substitute_for_final_answer(self):
        events = self.events(); events[1]['messages'].append(dict(role='toolResult', content='done'))
        with self.assertRaises(self.cli.NativeCliError): self.parse(events)
        events = self.events(); events[1]['messages'][-1]['content'] = [dict(type='text', text='')]
        with self.assertRaises(self.cli.NativeCliError): self.parse(events)

    def test_non_json_and_duplicate_fields_are_refused(self):
        for output in ('noise', '[]', '{"type":"session","type":"agent_settled"}', '{"value":NaN}'):
            with self.subTest(output=output), self.assertRaises(self.cli.NativeCliError):
                self.cli.parse_result(output, {'session_seed': SID})

    def test_exact_uuid_and_private_worker_storage_without_trust_overrides(self):
        worker = dict(id='a' * 32, home='/native/profile', model='provider/model', effort='high')
        command = self.cli.build_command('/native/pi', worker, {'session_seed': SID})
        self.assertEqual(command, ['/native/pi', '--print', '--mode', 'json', '--session-id', SID,
             '--session-dir', '/native/profile/owned-sessions/' + 'a' * 32, '--model', 'provider/model', '--thinking', 'high'])
        with self.assertRaises(self.cli.NativeCliError):
            self.cli.build_command('/native/pi', worker, {'native_session_id': 'partial-id'})

    def test_managed_profile_version_and_frontend_are_required(self):
        from xsm import host_install, native_workers
        home = str(Path(self.tmp, 'profile'))
        with self.assertRaises(native_workers.ProviderError): self.provider.prepare(home)
        host_install.apply('pi', home)
        binary = Path(self.tmp, 'native-pi')
        binary.write_text('#!' + sys.executable + '\nprint("1.4.0")\n'); binary.chmod(0o700)
        with mock.patch.dict(os.environ, {'XSM_PI': str(binary)}):
            descriptor = self.provider.prepare(home)
            worker = dict(id='a' * 32, home=home, native_provider=descriptor)
            self.assertEqual(self.provider.argv(worker, {'session_seed': SID})[0], str(binary.resolve()))
            descriptor['frontend_sha256'] = 'changed'
            with self.assertRaises(native_workers.ProviderError): self.provider.argv(worker, {'session_seed': SID})
            binary.write_text('#!' + sys.executable + '\nprint("0.58.1")\n')
            with self.assertRaises(native_workers.ProviderError): self.provider.prepare(home)

    def test_environment_does_not_borrow_another_session_storage_or_package(self):
        source = dict(PI_CODING_AGENT_SESSION_DIR='/other', PI_PACKAGE_DIR='/other',
                      XSM_WORKER='other', XSM_OWNED_CONTROL_FD='9', HOME='/operator')
        self.assertEqual(self.provider.environment({'home': '/native/profile'}, source),
                         {'HOME': '/operator', 'PI_CODING_AGENT_DIR': '/native/profile'})
        self.assertIn('XSM_WORKER', source)
