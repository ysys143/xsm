"""T1: one DM to several recipients (ADR-0025 decisions 2-8)."""
import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

from tests import test_xsm


class MultiSendTest(test_xsm.TempState):
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
        self.transport = patcher.start()
        self.addCleanup(patcher.stop)

    def _send(self, specs, **kw):
        from xsm import multisend
        return multisend.send_many(specs, 'please review', sender=self.me, **kw)

    def test_in_scope_recipients_get_it_out_of_scope_is_skipped_and_named(self):
        res = self._send(['codex:bee', 'codex:cee', 'codex:far'])
        by = {r['spec']: r['result'] for r in res.rows}
        self.assertEqual(by['codex:bee'].status, 'sent-unconfirmed')
        self.assertEqual(by['codex:cee'].status, 'sent-unconfirmed')
        self.assertEqual(by['codex:far'].status, 'refused')
        self.assertIn('out of scope, so not sent (the other recipients were)', by['codex:far'].reason)
        self.assertNotEqual(by['codex:bee'].msg_id, by['codex:cee'].msg_id)
        self.assertNotIn('far', self.bodies)           # no connect offer, nothing queued
        self.assertEqual(res.worst, 'sent-unconfirmed')
        self.assertIn('2 of 3 recipients sent', res.lines()[0])

    def test_each_recipient_is_told_the_others_that_got_it(self):
        self._send(['codex:bee', 'codex:cee', 'codex:far'])
        self.assertIn('(also sent to: cee@', self.bodies['bee'])
        self.assertIn('(also sent to: bee@', self.bodies['cee'])
        self.assertNotIn('far@', self.bodies['bee'])   # a skipped one is not named as a recipient
        self.assertIn('please review', self.bodies['bee'])

    def test_one_recipient_left_gets_no_note(self):
        self._send(['codex:bee', 'codex:far'])
        self.assertNotIn('also sent to', self.bodies['bee'])

    def test_duplicates_collapse_and_self_is_refused(self):
        res = self._send(['codex:bee', 'codex:bee', 'codex:lead'])
        self.assertEqual([r['spec'] for r in res.rows], ['codex:bee', 'codex:lead'])
        self.assertEqual(res.rows[1]['result'].reason, 'refusing to send to yourself')

    def test_limit_and_empty(self):
        from xsm import multisend
        with self.assertRaises(multisend.MultiError):
            self._send(['codex:bee'] * (multisend.LIMIT + 1))
        with self.assertRaises(multisend.MultiError):
            self._send(['  '])

    def test_one_wait_marks_the_receipts_that_land(self):
        from xsm import ledger, multisend
        real = multisend.ledger.status

        def landed(msg_id):
            state = dict(real(msg_id))
            if state.get('to', {}).get('session_id') == 'bee' or (state.get('to') or {}).get('name') == 'bee':
                state['status'] = 'delivered'
            return state
        with mock.patch.object(multisend.ledger, 'status', side_effect=landed):
            res = self._send(['codex:bee', 'codex:cee'], wait=0.5)
        by = {r['spec']: r['result'].status for r in res.rows}
        self.assertEqual(by['codex:bee'], 'delivered')
        self.assertEqual(by['codex:cee'], 'sent-unconfirmed')

    def test_failed_recipient_is_resent_under_its_own_id_and_others_are_not(self):
        from xsm import adapters, multisend
        def flaky(home, thread, content, *a, **k):
            if thread == 'cee':
                raise adapters.DeliveryError('queue-failed', 'daemon down')
            self.bodies[thread] = content
            return 'Queued message q for thread %s.' % thread
        self.transport.side_effect = flaky
        res = self._send(['codex:bee', 'codex:cee'])
        by = {r['spec']: r['result'] for r in res.rows}
        self.assertEqual(by['codex:cee'].status, 'error')
        first_id = by['codex:cee'].msg_id
        from xsm import ledger
        ledger.receipt(by['codex:bee'].msg_id, 'delivered', self.b)   # bee already has it
        self.bodies.clear()
        self.transport.side_effect = lambda home, thread, content, *a, **k: (
            self.bodies.__setitem__(thread, content) or 'Queued message q for thread %s.' % thread)
        again = multisend.resend_group(res.group_id, sender=self.me)
        by2 = {r['spec']: r['result'] for r in again.rows}
        self.assertEqual(by2['codex:cee'].msg_id, first_id)
        self.assertEqual(by2['codex:cee'].status, 'sent-unconfirmed')
        self.assertEqual(by2['codex:bee'].reason, 'not resent')
        self.assertEqual(list(self.bodies), ['cee'])
        self.assertIn('(also sent to: bee@', self.bodies['cee'])

    def test_resend_of_another_sessions_group_is_refused(self):
        from xsm import multisend
        res = self._send(['codex:bee', 'codex:cee'])
        with self.assertRaises(multisend.MultiError):
            multisend.resend_group(res.group_id, sender=self.b)
        with self.assertRaises(multisend.MultiError):
            multisend.resend_group('../etc', sender=self.me)

    def test_cli_exit_code_is_the_worst_and_json_lists_each(self):
        from xsm import cli, registry
        with mock.patch.object(registry, 'me', return_value=self.me):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(['send', 'codex:bee', 'codex:far', '--text', 'hi', '--json'])
        self.assertEqual(code, 3)                     # sent-unconfirmed beats refused
        data = json.loads(out.getvalue())
        self.assertEqual([r['status'] for r in data['recipients']], ['sent-unconfirmed', 'refused'])

    def test_cli_single_target_keeps_the_old_path(self):
        from xsm import cli, registry
        with mock.patch.object(registry, 'me', return_value=self.me):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(['send', 'codex:bee', '--text', 'hi'])
        self.assertEqual(code, 3)
        self.assertNotIn('group', out.getvalue())
        self.assertNotIn('also sent to', self.bodies['bee'])

    def test_mcp_targets_list(self):
        from xsm import mcp
        server = mcp.Server(io.StringIO(''), io.StringIO())
        with mock.patch.object(server, 'session', return_value=self.me):
            server.ctx = None
            text = server.call('xsm_send', {'targets': ['codex:bee', 'codex:cee'], 'text': 'x', 'wait': 0})
        self.assertIn('2 of 2 recipients sent', text)
        with mock.patch.object(server, 'session', return_value=self.me):
            with self.assertRaises(mcp.ToolError):
                server.call('xsm_send', {'targets': ['codex:bee'], 'target': 'codex:cee', 'text': 'x'})
