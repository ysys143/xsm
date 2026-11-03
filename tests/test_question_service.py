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

    def test_foreign_group_status_refuses_through_service_cli_and_model(self):
        from xsm import cli, mcp, question_groups, question_service, receive
        group = question_service.ask(self.me, {'targets': ['ref:' + self.peer['ref']],
            'text': 'retained owner question', 'wake': 'never'}, call=self.call)['result']
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.peer
        poll = mock.Mock(side_effect=AssertionError('foreign group child was polled'))
        with mock.patch.object(receive, 'poll_replies', poll):
            for frontend in ('service', 'cli', 'model'):
                with self.subTest(frontend=frontend):
                    if frontend == 'service':
                        result = question_service.status(self.peer, group['id'], poll=poll)['result']
                    elif frontend == 'cli':
                        with mock.patch.object(cli, '_unsure_caller', return_value=(self.peer, None)):
                            code, result = self.cli(['question-status', group['id']])
                        self.assertEqual(code, cli.REFUSED)
                    else:
                        result = json.loads(server.call('xsm_question_status', {'id': group['id']}))
                    self.assertEqual(result['status'], 'refused')
                    self.assertEqual(result['replies'], [])
                    self.assertEqual(result['recipients'], [])
        poll.assert_not_called()
        self.assertEqual(question_groups.status(self.me, group['id'])['status'], 'pending')

    def test_model_group_reply_claims_survive_common_result_projection(self):
        from xsm import send
        server = self.server()
        group = json.loads(server.call('xsm_ask', {'targets': ['ref:' + self.peer['ref']],
            'text': 'group claim projection', 'wake': 'never'}))
        child = group['recipients'][0]['id']
        reply = send.send('ref:' + self.me['ref'], 'selected reply', sender=self.peer,
            kind='reply', reply_to=child, msg_id='model-group-claim-reply', wake=False)
        self.assertEqual(reply.status, 'stored')
        answer = json.loads(server.call('xsm_question_status', {'id': group['id']}))
        self.assertEqual([claim['id'] for claim in answer['claims']], ['model-group-claim-reply'])
        self.assertEqual(answer['claims'], answer['recipients'][0]['claims'])
        server.call('xsm_ack', {'tokens': [claim['token'] for claim in answer['claims']]})
        retained = json.loads(server.call('xsm_question_status', {'id': group['id']}))
        self.assertEqual(retained['replies'][0]['body'], 'selected reply')
        self.assertEqual(retained['claims'], [])

    def test_cancelled_wait_does_not_cancel_or_ack_the_peer_request(self):
        from xsm import handoff, question_service, questions
        value = question_service.ask(self.me, {'target': 'ref:' + self.peer['ref'], 'text': 'retain work',
            'wake': 'never', 'request_id': 'cancel-wait-only'}, call=self.call)
        result = question_service.status(self.me, value['result']['id'], wait=1, cancelled=lambda: True)['result']
        self.assertEqual(result['wait_end_reason'], 'cancelled')
        self.assertEqual(questions.status(self.me, result['id'])['status'], 'pending')
        self.assertIn(result['id'], handoff.pending_ids(self.peer))

    def test_selected_handshake_does_not_follow_a_reassigned_name(self):
        from xsm import connect, handoff, question_service, registry
        select = connect.select
        replacement = []
        def move_name(me, target, **kwargs):
            result = select(me, target, **kwargs)
            registry.upsert('codex', self.peer['home'], 'peer', os.getpid(), self.tmp, name='renamed')
            replacement.append(registry.upsert('codex', self.peer['home'], 'replacement',
                                               os.getpid(), self.tmp, name='peer'))
            return result
        with mock.patch.object(connect, 'select', side_effect=move_name):
            value = question_service.connect(self.me, {'target': 'peer'}, call=self.call)['result']
        self.assertIn(value['id'], handoff.pending_ids(self.peer))
        self.assertNotIn(value['id'], handoff.pending_ids(replacement[0]))
