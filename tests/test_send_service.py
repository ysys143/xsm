"""Send orchestration is shared without moving file authority into model arguments."""
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState


class SharedSendServiceTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters, context, registry
        home = os.path.join(self.tmp, 'codex')
        os.makedirs(home)
        self.me = registry.upsert('codex', home, 'sender', os.getpid(), self.tmp, name='sender')
        self.peer = registry.upsert('codex', home, 'peer', os.getpid(), self.tmp, name='peer')
        self.third = registry.upsert('codex', home, 'third', os.getpid(), self.tmp, name='third')
        self.call = context.of_record(self.me, context.BASIS_SESSION)
        for p in (mock.patch.object(registry, 'me', return_value=self.me),
                  mock.patch.object(registry, 'last_identity', return_value=self.call),
                  mock.patch.object(adapters, 'to_codex', return_value=None)):
            p.start(); self.addCleanup(p.stop)

    def server(self):
        from xsm import mcp
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.me
        return server

    def test_cli_and_model_single_send_use_one_service(self):
        from xsm import cli, send_service, handoff
        with mock.patch.object(send_service, 'execute', wraps=send_service.execute) as execute:
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['send', 'codex:peer', '--text', 'cli body', '--wake', 'never', '--json']), cli.OK)
            result = json.loads(out.getvalue())
            text = self.server().call('xsm_send', {'target': 'codex:peer', 'text': 'model body', 'wake': 'never', 'wait': 0})
        self.assertIn('stored', text)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(execute.call_args.kwargs['caller'], self.me)
        self.assertEqual(result['status'], 'stored')
        self.assertEqual(len(handoff.pending_ids(self.peer)), 2)

    def test_cli_and_model_multi_send_use_one_service(self):
        from xsm import cli, send_service, handoff
        with mock.patch.object(send_service, 'execute', wraps=send_service.execute) as execute:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['send', 'codex:peer', 'codex:third', '--text', 'cli group', '--wake', 'never']), cli.OK)
            text = self.server().call('xsm_send', {'targets': ['codex:peer', 'codex:third'], 'text': 'model group', 'wake': 'never', 'wait': 0})
        self.assertIn('2 of 2', text)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(len(handoff.pending_ids(self.peer)), 2)
        self.assertEqual(len(handoff.pending_ids(self.third)), 2)

    def test_question_send_keeps_the_shared_material_preparation_path(self):
        from xsm import send_service
        with mock.patch.object(send_service, 'prepare_materials', wraps=send_service.prepare_materials) as prepare:
            value = json.loads(self.server().call('xsm_ask', {'target': 'ref:' + self.peer['ref'],
                'text': 'question body', 'wake': 'never', 'wait': 0, 'request_id': 'service-question'}))
        self.assertEqual(value['id'], 'service-question')
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(prepare.call_args.args[0], self.me)

    def test_changed_attachment_cannot_replace_a_frozen_request_or_send_twice(self):
        from xsm import files, registry, send, send_service
        self.assertTrue(registry.note_capabilities(self.peer, {'files': {'status': 'observed', 'version': 1}}, reader_pid=os.getpid()))
        args = {'target': 'codex:peer', 'text': 'same body', 'request_id': 'frozen-service',
            'attachments': [{'name': 'note.txt', 'text': 'first bytes'}], 'wake': 'never', 'wait': 0}
        with mock.patch.object(send, 'send', wraps=send.send) as actual:
            first = send_service.execute(args, caller=self.me, call=self.call)
            with self.assertRaisesRegex(files.FileError, 'intent-conflict'):
                send_service.execute(dict(args, attachments=[{'name': 'note.txt', 'text': 'changed bytes'}]), caller=self.me, call=self.call)
        self.assertEqual(first['result'].msg_id, 'frozen-service')
        self.assertEqual(actual.call_count, 1)

    def test_model_data_cannot_select_cli_path_read_authority(self):
        from xsm import files, registry, send, send_service
        self.assertTrue(registry.note_capabilities(self.peer, {'files': {'status': 'observed', 'version': 1}}, reader_pid=os.getpid()))
        private = Path(self.tmp, 'private-source.txt'); private.write_text('fixture bytes')
        args = {'target': 'codex:peer', 'text': 'body', 'request_id': 'path-authority',
            'attachments': [{'name': 'leak', 'path': str(private)}], 'material_source': 'cli', 'wait': 0}
        with mock.patch.object(send, 'send') as actual:
            with self.assertRaises(files.FileError):
                send_service.execute(args, caller=self.me, call=self.call)
        self.assertFalse(actual.called)
