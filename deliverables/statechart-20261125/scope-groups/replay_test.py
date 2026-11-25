"""Replay the TLC paths of XsmScopeGroups.tla against xsm's real code.

A = self.lead, B = self.new (or a session in another folder), P = self.bee
(and self.out as the second peer of the group). Run from the repository root:
  python3 <this file> -v Replay.test_x
Every test passes when the bug REPRODUCES (it asserts the broken behaviour,
and the print lines show what the rule would have wanted).

Mocked: adapters.to_codex only (the external Codex transport; it returns the
"Queued message" line the real adapter prints). HandoverTest.setUp also
patches workers.human_terminal -> False (the fixture's stand-in for "not a
person at a terminal"). Nothing else: ask, ask_many, send, poll_replies,
record_reply, hand_over, question_groups.status and config.scope_for are real.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.getcwd())
from tests.test_handover import HandoverTest  # noqa: E402


def queued(home, thread, content, *a, **k):
    return 'Queued message q for thread %s.' % thread


class Replay(HandoverTest):
    def _sess(self, sid, cwd=None):
        from xsm import registry
        if cwd is None:
            cwd = tempfile.mkdtemp(prefix='xsm-replay-')
            self.addCleanup(shutil.rmtree, cwd, True)
        os.makedirs(cwd, exist_ok=True)
        registry.upsert('codex', self.home, sid, os.getpid(), cwd, name=sid)
        return registry.by_session('codex', sid)

    def _answer(self, peer, to, body, request_id, outcome='succeeded'):
        from xsm import adapters, send
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            return send.send('ref:%s' % to['ref'], body, sender=peer, kind='reply',
                             reply_to=request_id, outcome=outcome)

    # ---- rules GroupShowsEveryAnswer / GroupStatusTruthful -------------------------
    def _ask_group(self):
        from xsm import adapters, question_groups
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            res = question_groups.ask_many(self.lead, ['ref:%s' % self.bee['ref'], 'ref:%s' % self.out['ref']],
                                           'what is 6*7?', wait=0)
        return res['id'], question_groups.child_ids(res['id'])

    def test_group_hides_a_final_answer_after_handover(self):
        """Path: P answers a question -> the person approves the handover."""
        from xsm import question_groups, questions, receive
        gid, kids = self._ask_group()
        print('\n[g1] group', gid, 'children', kids)
        # 1. P (bee) answers child 0 for good; A records it (poll, as the hook does).
        sent = self._answer(self.bee, self.lead, 'ANSWER-42', kids[0])
        self.assertGreaterEqual(receive.poll_replies(self.lead, kids[0]), 1)
        before = question_groups.status(self.lead, gid)
        print('[g1] A before handover: status=%s answered=%s asked=%s replies=%s waiting_on=%s'
              % (before['status'], before['answered'], before['asked'], len(before['replies']), before['waiting_on']))
        self.assertEqual((before['status'], before['answered']), ('reply_received', 1))
        # 2. the person approves the handover A -> B.
        rec = self._hand_over()
        print('[g1] handover moved questions:', rec['questions'], 'groups:', rec['groups'])
        after = question_groups.status(self.new, gid)
        print('[g1] B after handover: status=%s answered=%s asked=%s replies=%s waiting_on=%s'
              % (after['status'], after['answered'], after['asked'], len(after['replies']), after['waiting_on']))
        for row in after['recipients']:
            print('[g1]   row', row['recipient'], '->', row['status'], row.get('reason'))
        print('[g1] child 0 for A:', questions.status(self.lead, kids[0])['status'],
              '| for B:', questions.status(self.new, kids[0])['status'],
              '| group for A:', question_groups.status(self.lead, gid)['status'])
        # The rules would want: answered == 1, status reply_received, ANSWER-42 in replies.
        self.assertEqual(after['answered'], 0)                       # the rule breaks
        self.assertEqual(after['status'], 'pending')                 # the rule breaks
        self.assertFalse(any('ANSWER-42' in r['body'] for r in after['replies']))
        self.assertEqual(after['waiting_on'], [after['recipients'][1]['recipient']])
        self.assertEqual(after['recipients'][0]['status'], 'refused')

    def test_fully_answered_group_reads_refused_after_handover(self):
        """Path: P answers, P answers, the person approves the handover."""
        from xsm import question_groups, receive
        gid, kids = self._ask_group()
        self._answer(self.bee, self.lead, 'ANSWER-A', kids[0])
        self._answer(self.out, self.lead, 'ANSWER-B', kids[1])
        for k in kids:
            receive.poll_replies(self.lead, k)
        before = question_groups.status(self.lead, gid)
        print('\n[g2] A before handover: status=%s answered=%s' % (before['status'], before['answered']))
        self.assertEqual(before['status'], 'final')
        rec = self._hand_over()
        after = question_groups.status(self.new, gid)
        print('[g2] handover moved questions:', rec['questions'], 'groups:', rec['groups'])
        print('[g2] B after handover: status=%s answered=%s asked=%s replies=%s'
              % (after['status'], after['answered'], after['asked'], len(after['replies'])))
        waited = question_groups.wait_for(self.new, gid, 0)
        print('[g2] B wait_for: status=%s reason=%s' % (waited['status'], waited['wait_end_reason']))
        self.assertEqual((after['status'], after['answered'], len(after['replies'])), ('refused', 0, 0))

    def test_control_group_final_when_handed_over_before_any_answer(self):
        """Control: nothing answered before the handover; both answers come late and count."""
        from xsm import question_groups, receive
        gid, kids = self._ask_group()
        self._hand_over()
        for peer, k in ((self.bee, kids[0]), (self.out, kids[1])):
            self._answer(peer, self.lead, 'LATE', k)
            self.assertGreaterEqual(receive.poll_replies(self.new, k), 1)
        after = question_groups.status(self.new, gid)
        print('\n[g3] control: status=%s answered=%s' % (after['status'], after['answered']))
        self.assertEqual((after['status'], after['answered']), ('final', 2))

    # ---- rule LateAnswerReachesSuccessor ------------------------------------------
    def _late(self, label, setup, far=True, expect_reaches=False, peer_in_a_folder=False):
        """A asks P (real questions.ask; the scope A-P is `setup`), A hands over to B,
        P answers late (real send), B polls."""
        from xsm import adapters, config, questions, receive
        A = self.lead
        P = self._sess('peer', cwd=self.lead['cwd']) if peer_in_a_folder else self._sess('peer')   # not self.bee: it is in team core
        B = self._sess('nextfar') if far else self.new
        setup(P, A)
        scope_a = config.scope_for(P, A)[0]
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            ask = questions.ask(A, 'ref:%s' % P['ref'], 'what is 6*7?', request_id='q1')
        self.assertEqual(ask['status'], 'pending', ask)
        self._hand_over_to(A, B)
        scope_b = config.scope_for(P, B)[0]
        sent = self._answer(P, A, 'ANSWER-42', 'q1')
        matched = receive.poll_replies(B, 'q1')
        st = questions.status(B, 'q1')
        print('\n[%s] scope(P,A)=%s scope(P,B)=%s | late answer: %s | B poll=%s B status=%s'
              % (label, scope_a, scope_b, sent.status, matched, st['status']))
        print('[%s]   reason: %s' % (label, (sent.reason or '')[:150].replace('\n', ' ')))
        return sent, matched, st

    def _hand_over_to(self, A, B):
        from xsm import handover
        return handover.hand_over(A, B, 'goal: x', 'x')

    def _expect_refused(self, sent, matched, st):
        self.assertEqual(sent.status, 'refused')
        self.assertIn('out of scope', sent.reason)
        self.assertEqual(matched, 0)
        self.assertEqual(st['status'], 'pending')                    # the rule breaks

    def _expect_reaches(self, sent, matched, st):
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'))
        self.assertGreaterEqual(matched, 1)
        self.assertEqual(st['status'], 'final')

    def test_late_answer_reach_held_by_A(self):
        from xsm import config
        self._expect_refused(*self._late('reach by A', lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A)))

    def test_late_answer_P_is_a_worker_of_A(self):
        from xsm import workers
        self._expect_refused(*self._late('worker of A', lambda P, A: workers.save(
            {'name': 'h', 'ref': P['ref'], 'parent_ref': A['ref']})))

    def test_late_answer_same_folder_B_elsewhere(self):
        self._expect_refused(*self._late('same folder, B elsewhere', lambda P, A: None, peer_in_a_folder=True))

    def test_late_answer_link_B_outside(self):
        from xsm import config
        self._expect_refused(*self._late('link, B outside', lambda P, A: config.add_link(P['cwd'], A['cwd'], 't')))

    def test_control_same_folder_B_same_folder(self):
        self._expect_reaches(*self._late('same folder, B same', lambda P, A: None, far=False, peer_in_a_folder=True))

    def test_control_team(self):
        from xsm import teams
        self._expect_reaches(*self._late('team', lambda P, A: teams.add(self.lead, 'core', P, 'x')))

    def test_control_pair_team(self):
        """A pair team as `connect` makes it (two conversation members); built with the teams API."""
        from xsm import teams
        def pair(P, A):
            team = teams.create(A, 'pair-abc')
            teams.add(A, 'pair-abc', P, 'x')
        self._expect_reaches(*self._late('pair team', pair))

    def test_control_link_B_inside(self):
        from xsm import config
        self._expect_reaches(*self._late('link, B inside', lambda P, A: config.add_link(P['cwd'], A['cwd'], 't'),
                                         far=False))


if __name__ == '__main__':
    unittest.main()
