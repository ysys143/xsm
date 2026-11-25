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
    # Fixed in P3 (SM-F3)
    # Today: _groups moves the group but _questions leaves the child that has a final
    # answer at A, and questions.status reads only the exact sender, so B sees 0 answers
    # and status "pending" instead of "reply_received" with 1 reply.
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

    # Fixed in P3 (SM-F3)
    # Today: same cause; both children are answered for good, stay with A, and the group
    # reads "refused" with 0 replies for B instead of "final" with 2.
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
    # Fixed in P3 (SM-F4)
    def test_SM_F4_reach_held_by_A_late_answer_reaches_B(self):
        from xsm import config
        self._expect_reaches(self._late(lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A)))

    # Fixed in P3 (SM-F4)
    def test_SM_F4_P_is_a_worker_of_A_late_answer_reaches_B(self):
        from xsm import workers
        self._expect_reaches(self._late(lambda P, A: workers.save(
            {'name': 'h', 'ref': P['ref'], 'parent_ref': A['ref']})))

    # Fixed in P3 (SM-F4)
    def test_SM_F4_same_folder_B_elsewhere_late_answer_reaches_B(self):
        self._expect_reaches(self._late(lambda P, A: None, peer_in_a_folder=True))

    # Fixed in P3 (SM-F4)
    def test_SM_F4_link_B_outside_late_answer_reaches_B(self):
        from xsm import config
        self._expect_reaches(self._late(lambda P, A: config.add_link(P['cwd'], A['cwd'], 't')))

    # Fixed in P3 (SM-F4)
    # Today: hand_over returns no "links" key (planned API, spec 3.2 step "links").
    def test_SM_F4_handover_result_lists_the_copied_reach(self):
        from xsm import config
        rec, _sent, _matched, _st, (P, _A, _B) = self._late(
            lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A))
        self.assertIn('links', rec)
        self.assertTrue(rec['links'])
        self.assertIn(os.path.realpath(P['cwd']), json.dumps(rec['links'], default=str)
                      .replace(P['cwd'], os.path.realpath(P['cwd'])))

    # Fixed in P3 (SM-F4)
    # Today: no "links" key, and nothing is copied, so the worker pair is not listed.
    def test_SM_F4_handover_result_lists_the_copied_worker_pair(self):
        from xsm import workers
        rec, _sent, _matched, _st, (P, _A, _B) = self._late(lambda P, A: workers.save(
            {'name': 'h', 'ref': P['ref'], 'parent_ref': A['ref']}))
        self.assertIn('links', rec)
        self.assertIn(P['ref'], json.dumps(rec['links'], default=str))

    # Fixed in P3 (SM-F4, spec 6: one failing copy is skipped and listed, the rest go on)
    # Today: no "links" key and no copy at all (the good reach is not carried to B either).
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

    # Fixed in P3 (SM-F4, "B gets no more scope than A had")
    # Today: fails at the first assertion, because nothing is copied (scope P-B is None).
    # Once copying exists, the same test pins that Q (no scope with A) gets none with B.
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


    # ---- SM-F15: a late answer to a handed-over question passes on A's scope --------------------
    # P asked by A answers late, and between A and B the copy of A's connections failed (the person's
    # approved list was empty, or one copy failed), or has not been made yet. P had a scope with A.
    # Today send checks scope_for(P, B) only, finds none and refuses ("out of scope"): the
    # conversation A started is cut. Target (spec 0, F15): a reply to a question that is B's by the
    # handover passes on the scope P had with A; a new conversation keeps the present rule.
    def _late_uncopied(self, setup, window=False, peer_in_a_folder=False):
        """A asks P (scope from `setup`), hands over to B in another folder with NO link copy
        (`window`: the copy has not run yet when P answers), P answers late. Returns
        (send result, matched replies for B, B's question status, (P, A, B))."""
        from xsm import adapters, config, handover, questions, receive
        A = self.lead
        P = self._sess('peer', cwd=A['cwd']) if peer_in_a_folder else self._sess('peer')
        B = self._sess('nextfar')
        setup(P, A)
        self.assertIsNotNone(config.scope_for(P, A)[0], 'fixture: P and A must share a scope')
        self.assertIsNone(config.scope_for(P, B)[0], 'fixture: P and B must share none')
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            ask = questions.ask(A, 'ref:%s' % P['ref'], 'what is 6*7?', request_id='q1')
        self.assertEqual(ask['status'], 'pending', ask)
        box = {}
        if window:
            real = handover._copy_links

            def answer_first(*a, **k):
                box['sent'] = self._answer(P, A, 'ANSWER-42', 'q1')
                return real(*a, **k)
            with mock.patch.object(handover, '_copy_links', side_effect=answer_first):
                handover.hand_over(A, B, 'goal: x', 'x')
        else:
            plan = dict(handover.plan_links(A, B), links=[])        # the copy failed / was not approved
            handover.hand_over(A, B, 'goal: x', 'x', plan)
            box['sent'] = self._answer(P, A, 'ANSWER-42', 'q1')
        matched = receive.poll_replies(B, 'q1')
        return box['sent'], matched, questions.status(B, 'q1'), (P, A, B)

    def _expect_passes(self, result):
        from xsm import paths
        sent, matched, st, (_P, _A, B) = result
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'), sent.reason)
        self.assertGreaterEqual(matched, 1, 'the answer was not recorded for B')
        self.assertEqual(st['status'], 'final')
        held = paths.path(paths.HELD)
        self.assertEqual([n for n in os.listdir(held) if n.endswith('.json')] if os.path.isdir(held) else [], [],
                         'B\'s gate must not hold the answer')

    def test_SM_F15_reach_copy_failed_late_answer_reaches_B(self):
        from xsm import config
        self._expect_passes(self._late_uncopied(lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A)))

    def test_SM_F15_answer_before_the_link_copy_ran_reaches_B(self):
        from xsm import config
        self._expect_passes(self._late_uncopied(
            lambda P, A: config.add_reach(A['ref'], P['cwd'], 't', A), window=True))

    def test_SM_F15_same_folder_scope_copy_failed_late_answer_reaches_B(self):
        self._expect_passes(self._late_uncopied(lambda P, A: None, peer_in_a_folder=True))

    def test_SM_F15_named_project_scope_late_answer_reaches_B(self):
        from xsm import config

        def joined(P, A):
            config.join('proj', A['cwd'])
            config.join('proj', P['cwd'])
        self._expect_passes(self._late_uncopied(joined))

    def test_SM_F15_link_scope_copy_failed_late_answer_reaches_B(self):
        from xsm import config
        self._expect_passes(self._late_uncopied(lambda P, A: config.add_link(P['cwd'], A['cwd'], 't')))

    def test_SM_F15_worker_scope_copy_failed_late_answer_reaches_B(self):
        from xsm import workers
        self._expect_passes(self._late_uncopied(lambda P, A: workers.save(
            {'name': 'h', 'ref': P['ref'], 'parent_ref': A['ref']})))

    def test_SM_F15_the_marker_says_the_answer_came_on_the_handover(self):
        sent, _m, _st, _who = self._late_uncopied(
            lambda P, A: __import__('xsm.config', fromlist=['x']).add_reach(A['ref'], P['cwd'], 't', A))
        from xsm import ledger
        self.assertTrue(str(ledger.status(sent.msg_id).get('scope') or '').startswith('handover:'),
                        ledger.status(sent.msg_id).get('scope'))

    # The other direction (spec 2.1 F15, "whose original target was A"): P asked A, A handed over, and the
    # copy did not carry P's scope to B. B's answer to P is the same conversation; it must not be refused.
    def test_SM_F15_the_successor_answers_a_question_put_to_A_without_a_scope_with_P(self):
        from xsm import adapters, config, handover, questions, receive
        A, P, B = self.lead, self._sess('peer'), self._sess('nextfar')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            ask = questions.ask(P, 'ref:%s' % A['ref'], 'what is 6*7?', request_id='qp')
        self.assertEqual(ask['status'], 'pending', ask)
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        self.assertIsNone(config.scope_for(B, P)[0], 'fixture: B and P must share none')
        sent = self._answer(B, P, 'ANSWER-42', 'qp')
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'), sent.reason)
        self.assertGreaterEqual(receive.poll_replies(P, 'qp'), 1)
        self.assertEqual(questions.status(P, 'qp')['status'], 'final')

    # A chain A -> B -> C (spec 2.1 F15): the question record keeps every earlier asker, not only the last one.
    # P had a scope with A alone; neither handover copied it. P's late answer to the question A asked reaches C.
    def test_SM_F15_chain_a_late_answer_to_the_question_A_asked_reaches_C_after_A_B_C(self):
        from xsm import adapters, config, handover, questions, receive
        A, P, B, C = self.lead, self._sess('peer'), self._sess('nextfar'), self._sess('lastfar')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            ask = questions.ask(A, 'ref:%s' % P['ref'], 'what is 6*7?', request_id='qc')
        self.assertEqual(ask['status'], 'pending', ask)
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        handover.hand_over(B, C, 'goal: y', 'y', dict(handover.plan_links(B, C), links=[]))
        self.assertIsNone(config.scope_for(P, B)[0], 'fixture: P and B must share none')
        self.assertIsNone(config.scope_for(P, C)[0], 'fixture: P and C must share none')
        sent = self._answer(P, C, 'ANSWER-42', 'qc')
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'), sent.reason)
        self.assertGreaterEqual(receive.poll_replies(C, 'qc'), 1)
        self.assertEqual(questions.status(C, 'qc')['status'], 'final')

    def test_SM_F15_chain_the_question_record_keeps_every_earlier_asker(self):
        from xsm import adapters, config, handover, paths, questions
        A, P, B, C = self.lead, self._sess('peer'), self._sess('nextfar'), self._sess('lastfar')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            questions.ask(A, 'ref:%s' % P['ref'], 'what is 6*7?', request_id='qc')
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        handover.hand_over(B, C, 'goal: y', 'y', dict(handover.plan_links(B, C), links=[]))
        record = paths.read_json(questions._filename('qc'))
        self.assertEqual([h['session_id'] for h in record['handed_over_chain']], [A['session_id'], B['session_id']])
        self.assertEqual(record['handed_over_from']['session_id'], B['session_id'])

    def test_SM_F15_chain_the_successor_answers_a_question_put_to_A_after_A_B_C(self):
        from xsm import adapters, config, handover, questions, receive
        A, P, B, C = self.lead, self._sess('peer'), self._sess('nextfar'), self._sess('lastfar')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            ask = questions.ask(P, 'ref:%s' % A['ref'], 'what is 6*7?', request_id='qp')
        self.assertEqual(ask['status'], 'pending', ask)
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        handover.hand_over(B, C, 'goal: y', 'y', dict(handover.plan_links(B, C), links=[]))
        self.assertIsNone(config.scope_for(C, P)[0], 'fixture: C and P must share none')
        sent = self._answer(C, P, 'ANSWER-42', 'qp')
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'), sent.reason)
        self.assertGreaterEqual(receive.poll_replies(P, 'qp'), 1)
        self.assertEqual(questions.status(P, 'qp')['status'], 'final')

    def test_SM_F15_chain_both_sides_moved_the_answer_of_C_reaches_the_successor_of_the_asker(self):
        # P asked A, then P handed over to Q and A to B to C, none of the copies made: only P and A shared a scope.
        from xsm import adapters, config, handover, questions, receive
        A, P, B, C = self.lead, self._sess('peer'), self._sess('nextfar'), self._sess('lastfar')
        Q = self._sess('peernext')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            questions.ask(P, 'ref:%s' % A['ref'], 'what is 6*7?', request_id='qm')
        handover.hand_over(P, Q, 'goal: p', 'p', dict(handover.plan_links(P, Q), links=[]))
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        handover.hand_over(B, C, 'goal: y', 'y', dict(handover.plan_links(B, C), links=[]))
        self.assertIsNone(config.scope_for(C, Q)[0], 'fixture: C and Q must share none')
        sent = self._answer(C, Q, 'ANSWER-42', 'qm')
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'), sent.reason)
        self.assertGreaterEqual(receive.poll_replies(Q, 'qm'), 1)
        self.assertEqual(questions.status(Q, 'qm')['status'], 'final')

    def test_control_SM_F15_chain_a_stranger_cannot_answer_a_question_of_the_chain(self):
        from xsm import adapters, config, handover, questions, send
        A, P, B, C = self.lead, self._sess('peer'), self._sess('nextfar'), self._sess('lastfar')
        Q = self._sess('stranger')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            questions.ask(A, 'ref:%s' % P['ref'], 'what is 6*7?', request_id='qc')
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        handover.hand_over(B, C, 'goal: y', 'y', dict(handover.plan_links(B, C), links=[]))
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            res = send.send('ref:%s' % C['ref'], 'late', sender=Q, kind='reply', reply_to='qc', outcome='succeeded')
        self.assertEqual(res.status, 'refused', res.reason)

    # A new conversation is not a reply to a handed-over question: it keeps today's rule.
    def test_control_SM_F15_a_new_dm_from_P_to_A_after_the_handover_is_refused(self):
        from xsm import adapters, config, handover, send
        A, P, B = self.lead, self._sess('peer'), self._sess('nextfar')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            res = send.send('ref:%s' % A['ref'], 'hello again', sender=P)
        self.assertEqual(res.status, 'refused', res.reason)
        self.assertIn('scope', res.reason)

    def test_control_SM_F15_a_reply_to_a_question_nobody_of_B_asked_is_refused(self):
        from xsm import adapters, config, handover, send
        A, P, B = self.lead, self._sess('peer'), self._sess('nextfar')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            res = send.send('ref:%s' % A['ref'], 'late', sender=P, kind='reply', reply_to='nope', outcome='succeeded')
        self.assertEqual(res.status, 'refused', res.reason)

    def test_control_SM_F15_a_stranger_cannot_answer_for_the_one_asked(self):
        from xsm import adapters, config, handover, questions, send
        A, P, B = self.lead, self._sess('peer'), self._sess('nextfar')
        Q = self._sess('stranger')
        config.add_reach(A['ref'], P['cwd'], 't', A)
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            questions.ask(A, 'ref:%s' % P['ref'], 'what is 6*7?', request_id='q1')
        handover.hand_over(A, B, 'goal: x', 'x', dict(handover.plan_links(A, B), links=[]))
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            res = send.send('ref:%s' % A['ref'], 'late', sender=Q, kind='reply', reply_to='q1', outcome='succeeded')
        self.assertEqual(res.status, 'refused', res.reason)

    # ---- SM-F15 (join scopes are connections too; spec D1 detail) -------------------------------
    # Today the copy covers a reach, the folder, links and workers, not a named project A joined
    # with `xsm join`: P in the project reaches A and, after the handover, nobody.
    def test_SM_F15_a_named_project_A_joined_is_copied_to_B_and_listed(self):
        from xsm import adapters, config, handover, questions
        A, P, B = self.lead, self._sess('peer'), self._sess('nextfar')
        Q = self._sess('stranger')
        config.join('proj', A['cwd'])
        config.join('proj', P['cwd'])
        self.assertIsNone(config.scope_for(P, B)[0])
        rec = handover.hand_over(A, B, 'goal: x', 'x')
        self.assertIsNotNone(config.scope_for(P, B)[0], 'B has no scope with the project A joined')
        self.assertIsNone(config.scope_for(Q, B)[0], 'B must not get more than A had')
        self.assertIn(os.path.realpath(P['cwd']), json.dumps(rec['links'], default=str)
                      .replace(P['cwd'], os.path.realpath(P['cwd'])))
        self.assertTrue(any('proj' in str(row) for row in rec['links']), rec['links'])

    def test_SM_F15_a_project_copy_that_fails_is_skipped_and_listed(self):
        from xsm import config, handover, teams
        A, P, B = self.lead, self._sess('peer'), self._sess('nextfar')
        config.join('proj', A['cwd'])
        config.join('proj', P['cwd'])
        plan = handover.plan_links(A, B)
        gone = P['cwd']
        shutil.rmtree(gone)                                    # the folder is missing when the copy runs
        rec = handover.hand_over(A, B, 'goal: x', 'x', plan)
        self.assertTrue(teams.is_lead(teams.require('core'), B))
        bad = [row for row in rec['links'] if not row['ok']]
        self.assertTrue(any(os.path.basename(gone) in json.dumps(row) for row in bad), rec['links'])


# The fixture's own tests stay in test_handover; only this file's tests run here.
for _name in dir(test_handover.HandoverTest):
    if _name.startswith('test_'):
        setattr(StateModelQuestionsTest, _name, None)


if __name__ == '__main__':
    unittest.main()
