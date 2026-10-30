"""T8: handing a session's xsm place over to another (ADR-0025 decision 20, D27)."""
import hashlib
import io
import os
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tests import test_xsm


class HandoverTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, teams
        self.home = self.tmp + '/codex'
        os.makedirs(self.home)
        self.lead = registry.upsert('codex', self.home, 'lead', os.getpid(), self.tmp, name='lead')
        self.bee = registry.upsert('codex', self.home, 'bee', os.getpid(), self.tmp, name='bee')
        self.new = registry.upsert('codex', self.home, 'next', os.getpid(), self.tmp, name='next')
        self.out = registry.upsert('codex', self.home, 'out', os.getpid(), self.tmp, name='out')
        # What registry.me() and resolve hand over: the enriched records.
        self.lead, self.bee, self.new, self.out = (registry.by_session('codex', s)
                                                   for s in ('lead', 'bee', 'next', 'out'))
        teams.create(self.lead, 'core')
        teams.add(self.lead, 'core', self.bee, 'x')
        teams.set_lead(self.lead, 'core', teams.member_of(self.lead), 'x')
        patcher = mock.patch('xsm.workers.human_terminal', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _question(self, ident, sender, target):
        from xsm import paths, questions
        paths.write_json(questions._filename(ident), {
            'id': ident, 'sender': questions._handle(sender), 'target': questions._handle(target),
            'body': 'q', 'replies': [], 'purpose': 'question', 'created_at': 1.0})

    def _reply(self, request_id, reply_id, receiver, sender, outcome=None):
        from xsm import questions
        header = {'kind': 'reply', 'reply-to': request_id, 'id': reply_id}
        if outcome:
            header['outcome'] = outcome
        return questions.record_reply(receiver, sender, header, 'answer')

    def _hand_over(self, summary='goal: ship 0.5.1; open: T9'):
        from xsm import handover
        return handover.hand_over(self.lead, self.new, summary, 'x')

    def test_team_places_and_the_leads_seat_move(self):
        from xsm import teams
        self._hand_over()
        team = teams.require('core')
        self.assertTrue(teams.is_member(team, self.new))
        self.assertTrue(teams.is_lead(team, self.new))
        self.assertFalse(teams.is_member(team, self.lead))
        self.assertEqual(team['log'][-1]['action'], 'handover')

    def test_owned_board_items_move_and_the_board_says_so(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        board.set_item(self.lead, 'core', 'owner/lead/docs', 'README')
        board.set_item(self.lead, 'core', 'owner/bee', 'tests')
        rec = self._hand_over()
        self.assertEqual(sorted(rec['items']['core']), ['owner/lead', 'owner/lead/docs'])
        state = board.current('core')
        self.assertIn('the release plan\n\n(taken over from lead)', state['owner/next'][0]['body'])
        self.assertIn('README', state['owner/next/docs'][0]['body'])
        self.assertIn('handed over to next', state['owner/lead'][0]['body'])
        self.assertEqual(state['owner/bee'][0]['body'], 'tests')
        self.assertIn('lead handed its place in this team over to next', state['handover/lead'][0]['body'])
        self.assertIn("lead's seat moved", state['handover/lead'][0]['body'])

    def test_late_answers_to_its_questions_are_recorded_for_the_successor(self):
        from xsm import paths, questions
        self._question('q1', self.lead, self.bee)
        self._question('q2', self.lead, self.bee)
        self.assertTrue(self._reply('q2', 'r0', self.lead, self.bee, outcome='succeeded'))
        rec = self._hand_over()
        self.assertEqual(rec['questions'], ['q1'])           # answered for good: stays
        self.assertTrue(self._reply('q1', 'r1', self.new, self.bee))
        self.assertFalse(self._reply('q1', 'r2', self.lead, self.bee))
        self.assertEqual(questions.status(self.new, 'q1')['replies'][0]['id'], 'r1')
        self.assertEqual(paths.read_json(questions._filename('q2'))['sender']['session_id'], 'lead')

    def test_the_successor_answers_what_the_old_session_was_asked(self):
        from xsm import questions
        self._question('q3', self.bee, self.lead)
        self._hand_over()
        self.assertTrue(questions.expects_reply(self.bee, self.new, 'q3'))
        self.assertTrue(self._reply('q3', 'r3', self.bee, self.new))
        self.assertFalse(self._reply('q3', 'r4', self.bee, self.out))

    def test_unread_dms_go_in_the_letter_and_are_closed_as_moved(self):
        from xsm import handoff, receive
        handoff.store(self.lead, {'id': 'm1', 'sender': handoff._identity(self.bee),
                                  'target': handoff._identity(self.lead), 'body': 'tests are green',
                                  'kind': 'note', 'content': '[xsm] from bee: tests are green'})
        rec = self._hand_over()
        self.assertEqual(rec['messages'], ['m1'])
        old = handoff.status(self.lead, 'm1')
        self.assertEqual((old['status'], old['moved_to']['session_id']), ('acknowledged', 'next'))
        out = receive._with_bounces('codex', self.new, None)
        text = out['hookSpecificOutput']['additionalContext']
        self.assertIn('[xsm handover] lead@', text)
        self.assertIn('--- DM m1 ---\n[xsm] from bee: tests are green', text)
        self.assertIn('goal: ship 0.5.1; open: T9', text)
        self.assertIn('team core as its lead', text)
        again = receive._with_bounces('codex', self.new, None)
        self.assertNotIn('[xsm handover]', (again or {}).get('hookSpecificOutput', {}).get('additionalContext', ''))

    def test_dms_to_the_old_session_reach_the_successor(self):
        from xsm import handover, send
        self._hand_over()
        rec, note = handover.follow(self.lead)
        self.assertEqual(rec['session_id'], 'next')
        self.assertIn('handed its place over to next', note)
        from xsm import adapters
        with mock.patch.object(adapters, 'to_codex',
                               side_effect=lambda home, thread, content, *a, **k:
                               'Queued message q for thread %s.' % thread) as to_codex:
            result = send.send('ref:%s' % self.lead['ref'], 'report: done', sender=self.bee)
        self.assertEqual(result.target['session_id'], 'next')
        self.assertEqual(to_codex.call_args[0][1], 'next')
        self.assertEqual(handover.follow(self.bee), (self.bee, None))

    def test_a_name_only_stopped_sessions_match_follows_the_handover(self):
        from xsm import handover, registry
        self._hand_over()
        stopped = dict(registry.by_session('codex', 'lead'), state='ended')
        self.assertEqual(handover.follow_offline([stopped])['session_id'], 'next')
        self.assertIsNone(handover.follow_offline([dict(self.bee, state='ended')]))

    def test_a_p2p_handle_of_the_old_session_leads_to_the_successor(self):
        from xsm import handover, network_messages
        self._hand_over()
        home = os.path.realpath(self.home)
        handle = {'machine': 'a' * 64, 'runtime': 'codex', 'session_id': 'lead',
                  'home_id': hashlib.sha256(home.encode()).hexdigest(), 'generation': 'b' * 64}
        self.assertEqual(handover.for_handle(handle)['session_id'], 'next')
        self.assertIsNone(handover.for_handle(dict(handle, session_id='bee')))
        self.assertTrue(network_messages._handed_to(self.lead, self.new))
        self.assertFalse(network_messages._handed_to(self.bee, self.new))

    def test_refusals(self):
        from xsm import handover
        with self.assertRaises(handover.HandoverError):
            handover.hand_over(self.lead, self.lead, 's', 'x')
        with self.assertRaises(handover.HandoverError):
            handover.hand_over(self.lead, dict(self.new, state='ended'), 's', 'x')
        with self.assertRaises(handover.HandoverError):
            handover.hand_over(self.lead, dict(self.new, remote=True), 's', 'x')
        self._hand_over()
        with self.assertRaises(handover.HandoverError):
            self._hand_over()                                   # once
        with self.assertRaises(handover.HandoverError):
            handover.hand_over(self.bee, self.lead, 's', 'x')    # to one that handed over

    def test_it_is_the_users_decision(self):
        from xsm import cli, teams
        err = io.StringIO()
        with mock.patch.object(cli, '_unsure_caller', return_value=(self.lead, None)), \
                mock.patch('xsm.registry.me', return_value=self.lead):
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['handover', 'next', '--summary', 'state']), cli.REFUSED)
        self.assertIn('your user', err.getvalue())
        self.assertTrue(teams.is_lead(teams.require('core'), self.lead))   # nothing moved
        with mock.patch('xsm.workers.human_terminal', return_value=True), \
                mock.patch.object(cli, '_unsure_caller', return_value=(self.lead, None)):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(['handover', 'next', '--summary', 'state']), cli.OK)
        self.assertIn('handed over to next', out.getvalue())
        self.assertTrue(teams.is_lead(teams.require('core'), self.new))

    def test_a_summary_is_required(self):
        from xsm import cli
        with mock.patch.object(cli, '_unsure_caller', return_value=(self.lead, None)):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['handover', 'next']), cli.USAGE)

    def test_mcp_asks_with_a_form(self):
        from xsm import mcp, teams
        server = mcp.Server(io.StringIO(''), io.StringIO())
        server.ctx = None
        with mock.patch.object(server, 'session', return_value=self.lead), \
                mock.patch.object(server, 'allowed', return_value=(False, 'your user declined')):
            self.assertIn('nothing moved', server.call('xsm_handover', {'target': 'next', 'summary': 's'}))
        self.assertTrue(teams.is_lead(teams.require('core'), self.lead))
        with mock.patch.object(server, 'session', return_value=self.lead), \
                mock.patch.object(server, 'allowed', return_value=(True, None)):
            self.assertIn('handed over to next', server.call('xsm_handover', {'target': 'next', 'summary': 's'}))
        with mock.patch.object(server, 'session', return_value=self.new):
            self.assertIn('[xsm handover]', server.call('xsm_handover', {'action': 'show'}))
