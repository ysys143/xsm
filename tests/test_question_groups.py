"""T2: one question to several recipients (ADR-0025 decision 6)."""
import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

from tests import test_xsm


class QuestionGroupTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters, registry
        home = self.tmp + '/codex'
        os.makedirs(home)
        other = self.tmp + '/elsewhere'
        os.makedirs(other)
        self.me = registry.upsert('codex', home, 'lead', os.getpid(), self.tmp, name='lead')
        self.b = registry.upsert('codex', home, 'bee', os.getpid(), self.tmp, name='bee')
        self.c = registry.upsert('codex', home, 'cee', os.getpid(), self.tmp, name='cee')
        self.far = registry.upsert('codex', home, 'far', os.getpid(), other, name='far')
        self.bodies = {}

        def queued(home, thread, content, *a, **k):
            self.bodies[thread] = content
            return 'Queued message q for thread %s.' % thread
        patcher = mock.patch.object(adapters, 'to_codex', side_effect=queued)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ask(self, specs=('codex:bee', 'codex:cee', 'codex:far'), **kw):
        from xsm import question_groups
        return question_groups.ask_many(self.me, list(specs), 'which cache?', **kw)

    def _reply(self, peer, request_id, reply_id, body, outcome=None):
        from xsm import questions
        header = {'kind': 'reply', 'reply-to': request_id, 'id': reply_id}
        if outcome:
            header['outcome'] = outcome
        return questions.record_reply(self.me, peer, header, body)

    def _child(self, result, label_part):
        return next(r for r in result['recipients'] if label_part in r['recipient'])

    def test_each_in_scope_recipient_gets_its_own_question_and_far_is_skipped(self):
        res = self._ask()
        self.assertTrue(res['group'])
        self.assertEqual((res['asked'], res['skipped']), (2, 1))
        far = self._child(res, 'far')
        self.assertEqual(far['status'], 'skipped')
        self.assertIn('out of scope', far['reason'])
        bee, cee = self._child(res, 'bee@'), self._child(res, 'cee@')
        self.assertTrue(bee['id'].startswith(res['id'] + '-'))
        self.assertNotEqual(bee['id'], cee['id'])
        self.assertIn('(also sent to: cee@', self.bodies['bee'])
        self.assertNotIn('far', self.bodies)
        self.assertEqual(res['status'], 'pending')
        self.assertEqual(sorted(res['waiting_on'])[0].split('@')[0], 'bee')

    def test_replies_are_kept_per_recipient_and_the_status_follows(self):
        from xsm import question_groups
        res = self._ask()
        bee, cee = self._child(res, 'bee@')['id'], self._child(res, 'cee@')['id']
        self.assertTrue(self._reply(self.b, bee, 'rb1', 'redis'))
        self.assertFalse(self._reply(self.b, cee, 'rb2', 'not my question'))   # wrong peer
        st = question_groups.status(self.me, res['id'])
        self.assertEqual(st['status'], 'reply_received')
        self.assertEqual(st['answered'], 1)
        self.assertEqual([r['recipient'].split('@')[0] for r in st['replies']], ['bee'])
        self.assertEqual(st['replies'][0]['request_id'], bee)
        self._reply(self.b, bee, 'rb3', 'final: redis', 'succeeded')
        self._reply(self.c, cee, 'rc1', 'memcached', 'succeeded')
        st = question_groups.status(self.me, res['id'])
        self.assertEqual(st['status'], 'final')
        self.assertEqual(st['waiting_on'], [])

    def test_wait_ends_when_all_answer_or_at_the_deadline(self):
        from xsm import question_groups
        res = self._ask(('codex:bee', 'codex:cee'))
        timed = question_groups.wait_for(self.me, res['id'], wait=0.2)
        self.assertEqual(timed['wait_end_reason'], 'timeout')
        self._reply(self.b, self._child(res, 'bee@')['id'], 'r1', 'a')
        self._reply(self.c, self._child(res, 'cee@')['id'], 'r2', 'b')
        done = question_groups.wait_for(self.me, res['id'], wait=5)
        self.assertEqual(done['wait_end_reason'], 'all-answered-or-ended')
        self.assertEqual(done['status'], 'replied')
        polled = []
        question_groups.wait_for(self.me, res['id'], wait=0, poll=polled.append)
        self.assertEqual(sorted(polled), sorted(question_groups.child_ids(res['id'])))
        self.assertEqual(question_groups.wait_for(self.me, res['id'], wait=5,
                                                  cancelled=lambda: True)['wait_end_reason'],
                         'all-answered-or-ended')

    def test_another_conversation_cannot_read_the_group_and_bad_ids_are_not_groups(self):
        from xsm import question_groups
        res = self._ask(('codex:bee', 'codex:cee'))
        self.assertEqual(question_groups.status(self.b, res['id'])['status'], 'refused')
        self.assertEqual(question_groups.status(self.me, 'nope')['status'], 'not-found')
        self.assertFalse(question_groups.is_group('../x'))
        with self.assertRaises(question_groups.GroupError):
            self._ask(())

    def test_cli_group_ask_and_question_status(self):
        from xsm import cli
        with mock.patch.object(cli, '_unsure_caller', return_value=(self.me, None)):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(['ask', 'codex:bee', 'codex:cee', '--text', 'which cache?'])
            self.assertEqual(code, cli.UNCONFIRMED)
            res = json.loads(out.getvalue())
            self._reply(self.b, self._child(res, 'bee@')['id'], 'r1', 'redis')
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(['question-status', res['id']])
            self.assertEqual(code, cli.OK)
            st = json.loads(out.getvalue())
        self.assertEqual(st['answered'], 1)
        self.assertIn('claims', st)

    def test_mcp_targets_and_group_status(self):
        from xsm import mcp
        server = mcp.Server(io.StringIO(''), io.StringIO())
        with mock.patch.object(server, 'session', return_value=self.me):
            server.ctx = None
            res = json.loads(server.call('xsm_ask', {'targets': ['codex:bee', 'codex:cee'], 'text': 'q?'}))
            self.assertTrue(res['group'])
            self._reply(self.c, self._child(res, 'cee@')['id'], 'r9', 'ok', 'succeeded')
            st = json.loads(server.call('xsm_question_status', {'id': res['id']}))
            self.assertEqual(st['answered'], 1)
            with self.assertRaises(mcp.channel.ChannelError):
                server.call('xsm_ask', {'targets': ['codex:bee'], 'target': 'codex:cee', 'text': 'q'})
            with self.assertRaises(mcp.channel.ChannelError):
                server.call('xsm_ask', {'text': 'q'})
