"""Native CLI framing and frozen resume selection; no model or native process."""
import json
import unittest
from integrations.hermes import worker_cli as cli


NATIVE = 'local-' + 'a' * 64


class HermesWorkerCliTest(unittest.TestCase):
    def wire(self, **changes):
        final = dict(type='result', session_id=NATIVE, exit_code=0, text='actual answer')
        final.update(changes)
        return '\n'.join(json.dumps(event) for event in [dict(type='system', subtype='init', session_id=''), final])

    def test_first_launch_uses_stdin_and_admitted_workspace_without_permission_overrides(self):
        command = cli.build_command('/native/hermes', {'cwd': '/owned/work', 'model': 'catalog/model',
                                    'effort': 'high'}, {'native_session_id': None})
        self.assertEqual(command[:6], ['/native/hermes', 'chat', '--format', 'stream-json', '--query-file', '-'])
        self.assertIn('/owned/work', command)
        self.assertIn('--model=catalog/model', command)
        self.assertIn('--reasoning=high', command)
        self.assertFalse(any(flag in command for flag in ('--yolo', '--safe-mode', '--api-key', '--ignore-user-config')))

    def test_resume_preserves_opaque_native_id_and_its_frozen_launch_policy(self):
        command = cli.build_command('/native/hermes', {'cwd': '/different', 'model': 'different'},
                                    {'native_session_id': NATIVE})
        self.assertEqual(command[-2:], ['--resume', NATIVE])
        self.assertNotIn('--in', command)
        self.assertFalse(any(value.startswith('--model') for value in command))
        self.assertEqual(cli.parse_result(self.wire(), {'native_session_id': NATIVE})['native_session_id'], NATIVE)

    def test_invalid_resume_id_never_turns_into_a_new_conversation(self):
        for value in ('', '../other', '--new', 'line\n', True):
            with self.subTest(value=value), self.assertRaises(cli.NativeCliError):
                cli.build_command('/native/hermes', {'cwd': '/owned'}, {'native_session_id': value})

    def test_changed_native_conversation_is_refused(self):
        with self.assertRaisesRegex(cli.NativeCliError, 'selected owned conversation'):
            cli.parse_result(self.wire(), {'native_session_id': 'different'})

    def test_native_error_and_incomplete_output_are_not_answers(self):
        for changes in ({'exit_code': True}, {'exit_code': 1}, {'error': 'failed'}, {'text': ''},
                        {'text': 123}, {'session_id': ''}):
            with self.subTest(changes=changes), self.assertRaises(cli.NativeCliError):
                cli.parse_result(self.wire(**changes), {})
        for output in (self.wire() + '\n{}', self.wire() + '\n' + self.wire(), '{}', '[]'):
            with self.subTest(output=output[:20]), self.assertRaises(cli.NativeCliError):
                cli.parse_result(output, {})

    def test_duplicate_keys_non_json_numbers_and_wrong_init_are_refused(self):
        invalid = ('{"type":"system","type":"result"}',
                   '{"type":"result","exit_code":NaN}',
                   '{"type":"result","session_id":"x","exit_code":0,"text":"answer"}')
        for output in invalid:
            with self.subTest(output=output), self.assertRaises(cli.NativeCliError):
                cli.parse_result(output, {})

    def test_model_text_remains_body_not_native_execution_metadata(self):
        body = json.dumps({'native_session_id': 'other', 'outcome': 'succeeded', 'body': 'model claim'})
        parsed = cli.parse_result(self.wire(text=body), {})
        self.assertEqual(parsed['native_session_id'], NATIVE)
        self.assertEqual(parsed['body'], body)
        self.assertNotIn('outcome', parsed)
