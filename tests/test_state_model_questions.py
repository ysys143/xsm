"""State-model fixes, questions and scope (docs/plan/state-model-fixes/spec.md, P0).

Criteria SM-F3 (question groups across a handover) and SM-F4 (late answers
across a handover when the answerer has no scope with the successor). The
fixtures follow deliverables/statechart-20261125/scope-groups/replay_test.py:
A = self.lead, B = self.new (or a session in another folder), P = a peer.

Mocked: adapters.to_codex only (the external Codex transport) and, through
HandoverTest.setUp, the person at a terminal. Nothing else: ask, ask_many,
send, poll_replies, hand_over, question_groups.status, questions.status and
config.scope_for are the real code.

RED tests assert the TARGET behavior and are marked expectedFailure until the
fix lands (P3). Controls pass today.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import test_handover


def queued(home, thread, content, *a, **k):
    return 'Queued message q for thread %s.' % thread


class StateModelQuestionsTest(test_handover.HandoverTest):
    # ---- fixtures ------------------------------------------------------------------
    def _sess(self, sid, cwd=None):
        from xsm import registry
        if cwd is None:
            cwd = tempfile.mkdtemp(prefix='xsm-sm-')
            self.addCleanup(shutil.rmtree, cwd, True)
        os.makedirs(cwd, exist_ok=True)
        registry.upsert('codex', self.home, sid, os.getpid(), cwd, name=sid)
        return registry.by_session('codex', sid)

    def _answer(self, peer, to, body, request_id, outcome='succeeded'):
        from xsm import adapters, send
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            return send.send('ref:%s' % to['ref'], body, sender=peer, kind='reply',
                             reply_to=request_id, outcome=outcome)

    def _ask_group(self):
        from xsm import adapters, question_groups
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            res = question_groups.ask_many(
                self.lead, ['ref:%s' % self.bee['ref'], 'ref:%s' % self.out['ref']],
                'what is 6*7?', wait=0)
        return res['id'], question_groups.child_ids(res['id'])

    # ---- SM-F3: question groups across a handover ---------------------------------
    # RED until P3 (SM-F3)
    # Today: _groups moves the group but _questions leaves the child that has a final
    # answer at A, and questions.status reads only the exact sender, so B sees 0 answers
    # and status "pending" instead of "reply_received" with 1 reply.
    @unittest.expectedFailure
    def test_SM_F3_one_answer_before_handover_group_is_reply_received_for_B(self):
        from xsm import question_groups, receive
        gid, kids = self._ask_group()
        self._answer(self.bee, self.lead, 'ANSWER-42', kids[0])
        self.assertGreaterEqual(receive.poll_replies(self.lead, kids[0]), 1)
        before = question_groups.status(self.lead, gid)
        self.assertEqual((before['status'], before['answered']), ('reply_received', 1))
        self._hand_over()
        after = question_groups.status(self.new, gid)
        self.assertEqual(after['status'], 'reply_received')
        self.assertEqual(after['answered'], 1)
        self.assertEqual(len(after['replies']), 1)
        self.assertTrue(any('ANSWER-42' in r['body'] for r in after['replies']))

    # RED until P3 (SM-F3)
    # Today: same cause; both children are answered for good, stay with A, and the group
    # reads "refused" with 0 replies for B instead of "final" with 2.
    @unittest.expectedFailure
    def test_SM_F3_fully_answered_group_is_final_for_B(self):
        from xsm import question_groups, receive
        gid, kids = self._ask_group()
        self._answer(self.bee, self.lead, 'ANSWER-A', kids[0])
        self._answer(self.out, self.lead, 'ANSWER-B', kids[1])
        for k in kids:
            receive.poll_replies(self.lead, k)
        self.assertEqual(question_groups.status(self.lead, gid)['status'], 'final')
        self._hand_over()
        after = question_groups.status(self.new, gid)
        self.assertEqual(after['status'], 'final')
        self.assertEqual(after['answered'], 2)
        self.assertEqual(len(after['replies']), 2)

    # Control (spec 3.4 / SM-F3 third sentence): a question A asks after the handover stays
    # A's; B must not read it, so questions.status(B, id) is "refused". Passes today.
    def test_control_SM_F3_new_question_stays_As(self):
        from xsm import adapters, questions
        self._hand_over()
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            ask = questions.ask(self.lead, 'ref:%s' % self.bee['ref'], 'what is 6*7?', request_id='q-after')
        self.assertEqual(ask['status'], 'pending', ask)
        self.assertEqual(questions.status(self.new, 'q-after')['status'], 'refused')

    # ---- SM-F4: late answers to a handed-over question ------------------------------
    def _late(self, setup, far=True, peer_in_a_folder=False, before=None):
        """A asks P (real questions.ask; the P-A scope is whatever `setup` builds),
        A hands over to B, P answers late (real send), B polls.
        Returns (handover record, send result, replies matched for B, B's question status)."""
        from xsm import adapters, config, handover, questions, receive
        A = self.lead
        P = self._sess('peer', cwd=A['cwd']) if peer_in_a_folder else self._sess('peer')
        B = self._sess('nextfar') if far else self.new
        setup(P, A)
        self.assertIsNotNone(config.scope_for(P, A)[0])
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            ask = questions.ask(A, 'ref:%s' % P['ref'], 'what is 6*7?', request_id='q1')
        self.assertEqual(ask['status'], 'pending', ask)
        if before:
            before(P, A)
        rec = handover.hand_over(A, B, 'goal: x', 'x')
        sent = self._answer(P, A, 'ANSWER-42', 'q1')
        matched = receive.poll_replies(B, 'q1')
        return rec, sent, matched, questions.status(B, 'q1'), (P, A, B)

    def _expect_reaches(self, result):
        _rec, sent, matched, st, _who = result
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'), sent.reason)
        self.assertGreaterEqual(matched, 1)
        self.assertEqual(st['status'], 'final')

    # The four bases below: today scope_for(P, B) is None, so the late answer is refused
    # ("out of scope") at send and B's question record stays pending (spec F4). Target:
    # the handover copies A's connection, so the answer lands in B's record, status final.
    # RED until P3 (SM-F4)
    @unittest.expectedFailure
    def test_SM_F4_reach_held_by_A_late_answer_reaches_B(self):
        from xsm import config
        self._expect_reaches(self._late(lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A)))

    # RED until P3 (SM-F4)
    @unittest.expectedFailure
    def test_SM_F4_P_is_a_worker_of_A_late_answer_reaches_B(self):
        from xsm import workers
        self._expect_reaches(self._late(lambda P, A: workers.save(
            {'name': 'h', 'ref': P['ref'], 'parent_ref': A['ref']})))

    # RED until P3 (SM-F4)
    @unittest.expectedFailure
    def test_SM_F4_same_folder_B_elsewhere_late_answer_reaches_B(self):
        self._expect_reaches(self._late(lambda P, A: None, peer_in_a_folder=True))

    # RED until P3 (SM-F4)
    @unittest.expectedFailure
    def test_SM_F4_link_B_outside_late_answer_reaches_B(self):
        from xsm import config
        self._expect_reaches(self._late(lambda P, A: config.add_link(P['cwd'], A['cwd'], 't')))

    # RED until P3 (SM-F4)
    # Today: hand_over returns no "links" key (planned API, spec 3.2 step "links").
    @unittest.expectedFailure
    def test_SM_F4_handover_result_lists_the_copied_reach(self):
        from xsm import config
        rec, _sent, _matched, _st, (P, _A, _B) = self._late(
            lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A))
        self.assertIn('links', rec)
        self.assertTrue(rec['links'])
        self.assertIn(os.path.realpath(P['cwd']), json.dumps(rec['links'], default=str)
                      .replace(P['cwd'], os.path.realpath(P['cwd'])))

    # RED until P3 (SM-F4)
    # Today: no "links" key, and nothing is copied, so the worker pair is not listed.
    @unittest.expectedFailure
    def test_SM_F4_handover_result_lists_the_copied_worker_pair(self):
        from xsm import workers
        rec, _sent, _matched, _st, (P, _A, _B) = self._late(lambda P, A: workers.save(
            {'name': 'h', 'ref': P['ref'], 'parent_ref': A['ref']}))
        self.assertIn('links', rec)
        self.assertIn(P['ref'], json.dumps(rec['links'], default=str))

    # RED until P3 (SM-F4, spec 6: one failing copy is skipped and listed, the rest go on)
    # Today: no "links" key and no copy at all (the good reach is not carried to B either).
    @unittest.expectedFailure
    def test_SM_F4_failed_copy_is_skipped_and_listed_and_handover_completes(self):
        from xsm import config, teams
        gone = tempfile.mkdtemp(prefix='xsm-sm-gone-')
        self.addCleanup(shutil.rmtree, gone, True)
        config.add_reach(self.lead['ref'], gone, 't', self.lead)
        shutil.rmtree(gone)                       # the folder is missing when the copy runs
        result = self._late(lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A))
        rec, B = result[0], result[4][2]
        self.assertTrue(teams.is_lead(teams.require('core'), B))     # the handover completed
        self.assertIn('links', rec)
        self.assertIn(os.path.basename(gone), json.dumps(rec['links'], default=str))   # skipped, listed
        self._expect_reaches(result)                                 # the other copy still worked

    # RED until P3 (SM-F4, "B gets no more scope than A had")
    # Today: fails at the first assertion, because nothing is copied (scope P-B is None).
    # Once copying exists, the same test pins that Q (no scope with A) gets none with B.
    @unittest.expectedFailure
    def test_SM_F4_a_session_with_no_scope_with_A_has_none_with_B(self):
        from xsm import config
        Q = self._sess('stranger')                # its own unrelated folder
        result = self._late(lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A))
        P, A, B = result[4]
        self.assertIsNone(config.scope_for(Q, A)[0])
        self.assertIsNotNone(config.scope_for(P, B)[0])             # the copy happened
        self.assertIsNone(config.scope_for(Q, B)[0])                # and went no further

    # ---- controls: these reach B today (a scope P-B exists or carries over) ---------
    def test_control_SM_F4_team(self):
        from xsm import teams
        self._expect_reaches(self._late(lambda P, A: teams.add(self.lead, 'core', P, 'x')))

    def test_control_SM_F4_pair_team(self):
        from xsm import teams

        def pair(P, A):
            teams.create(A, 'pair-abc')
            teams.add(A, 'pair-abc', P, 'x')
        self._expect_reaches(self._late(pair))

    def test_control_SM_F4_same_folder_B_same_folder(self):
        self._expect_reaches(self._late(lambda P, A: None, far=False, peer_in_a_folder=True))

    def test_control_SM_F4_link_B_inside(self):
        from xsm import config
        self._expect_reaches(self._late(lambda P, A: config.add_link(P['cwd'], A['cwd'], 't'), far=False))


# The fixture's own tests stay in test_handover; only this file's tests run here.
for _name in dir(test_handover.HandoverTest):
    if _name.startswith('test_'):
        setattr(StateModelQuestionsTest, _name, None)


if __name__ == '__main__':
    unittest.main()
