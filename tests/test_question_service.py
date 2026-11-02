"""Questions and handshakes share orchestration without making waits into task cancellation."""
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from tests.test_xsm import TempState


class SharedQuestionServiceTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters, context, registry
        home = os.path.join(self.tmp, 'codex')
        os.makedirs(home)
        self.me = registry.upsert('codex', home, 'sender', os.getpid(), self.tmp, name='sender')
        self.peer = registry.upsert('codex', home, 'peer', os.getpid(), self.tmp, name='peer')
        self.call = context.of_record(self.me, context.BASIS_SESSION)
        for patch in (mock.patch.object(registry, 'me', return_value=self.me),
                      mock.patch.object(registry, 'last_identity', return_value=self.call),
                      mock.patch.object(adapters, 'to_codex', return_value=None)):
            patch.start(); self.addCleanup(patch.stop)

    def cli(self, arguments):
        from xsm import cli
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(arguments)
        return code, json.loads(out.getvalue())

    def server(self):
        from xsm import mcp
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.me
        return server

    def test_cli_and_model_ask_status_and_connect_use_common_services(self):
        from xsm import cli, question_service
        target = 'ref:' + self.peer['ref']
        server = self.server()
        with mock.patch.object(question_service, 'ask', wraps=question_service.ask) as shared:
            code, question = self.cli(['ask', target, '--text', 'cli question', '--wake', 'never', '--wait', '0'])
            value = json.loads(server.call('xsm_ask', {'target': target, 'text': 'model question', 'wake': 'never', 'wait': 0}))
            self.assertEqual(code, cli.UNCONFIRMED)
            self.assertNotEqual(question['id'], value['id'])
            self.assertEqual(shared.call_count, 2)
        with mock.patch.object(question_service, 'status', wraps=question_service.status) as shared:
            _, first = self.cli(['question-status', question['id']])
            second = json.loads(server.call('xsm_question_status', {'id': question['id']}))
            self.assertEqual(first['id'], second['id'])
            self.assertEqual(shared.call_count, 2)
        with mock.patch.object(question_service, 'connect', wraps=question_service.connect) as shared:
            _, first = self.cli(['connect', target])
            second = json.loads(server.call('xsm_connect', {'target': target}))
            self.assertEqual(first['handshake'], 'pending')
            self.assertEqual(second['handshake'], 'pending')
            self.assertEqual(shared.call_count, 2)

    def test_cancelled_wait_does_not_cancel_or_ack_the_peer_request(self):
        from xsm import handoff, question_service, questions
        value = question_service.ask(self.me, {'target': 'ref:' + self.peer['ref'], 'text': 'retain work',
            'wake': 'never', 'request_id': 'cancel-wait-only'}, call=self.call)
        result = question_service.status(self.me, value['result']['id'], wait=1, cancelled=lambda: True)['result']
        self.assertEqual(result['wait_end_reason'], 'cancelled')
        self.assertEqual(questions.status(self.me, result['id'])['status'], 'pending')
        self.assertIn(result['id'], handoff.pending_ids(self.peer))
