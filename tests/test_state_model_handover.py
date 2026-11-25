"""State-model fixes, handover core (docs/plan/state-model-fixes/spec.md, P0).

RED regression tests for SM-F1, SM-F2a, SM-F2b, SM-F5, SM-F5r, SM-SEAM and
SM-COMPAT. They assert the TARGET behavior of the spec (section 5), not the
behavior of 0.6.1, so each one is marked `expectedFailure` until the phase
named in its comment lands. The phase implementer removes the decorator.

Each RED test says in a comment why it fails on 0.6.1 ("wrong value": the
defect itself; "missing API": a planned name from spec section 3.2). Tests
named `test_control_*` pass today and must keep passing.

Fixtures and interleaving tricks come from the reproductions in
deliverables/statechart-20261125/{round1,concurrent,migration}/replay_test.py.
Mocked: adapters.to_codex (transport), receive.check where a gate decision is
the point (a hold), and the person's yes for `held deliver`. Nothing else.

A = lead, B = next, C = out, P = bee (the HandoverTest fixture). Where B must
be outside A's and P's scope, a2/p2 share one folder and `far` sits in another
folder with no team.
"""
import io
import json
import os
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tests import test_handover

RACE_STEP = 10          # seconds a parked thread waits before the test gives up


class _Crash(BaseException):
    """A process that dies: not an Exception, so no step may swallow it."""


def queued(home, thread, content, *a, **k):
    return 'Queued message q for thread %s.' % thread


def name(rec):
    return rec.get('name') or rec.get('session_id')


class StateModelHandover(test_handover.HandoverTest):
    """HandoverTest's fixture without re-running its tests."""

    # ---- fixture helpers ----
    def _send(self, to, body, sender=None, **kw):
        from xsm import adapters, send
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            return send.send('ref:%s' % to['ref'], body, sender=sender or self.bee, **kw)

    def _hold(self, me, reason='out of scope (test)'):
        """The real inbox path with the gate saying block: the DM is held."""
        from xsm import receive
        with mock.patch.object(receive, 'check', return_value=('block', reason)):
            return receive.take_inbox_claims(me)

    def _session(self, session_id, cwd):
        from xsm import registry
        os.makedirs(cwd, exist_ok=True)
        registry.upsert('codex', self.home, session_id, os.getpid(), cwd, name=session_id)
        return registry.by_session('codex', session_id)

    def _outside(self):
        """a2 and p2 share a folder (a scope); far is in another folder, in no team."""
        proj = self.tmp + '/proj'
        self.a2 = self._session('a2', proj)
        self.p2 = self._session('p2', proj)
        self.far = self._session('far', self.tmp + '/elsewhere')
        from xsm import config
        self.assertIsNotNone(config.scope_for(self.p2, self.a2)[0], 'fixture: P and A must share a scope')
        self.assertIsNone(config.scope_for(self.p2, self.far)[0], 'fixture: P and B must share none')

    def _held_names(self):
        from xsm import paths
        folder = paths.path(paths.HELD)
        return sorted(n[:-5] for n in os.listdir(folder) if n.endswith('.json')) if os.path.isdir(folder) else []

    def _held_entry(self, held_name):
        from xsm import paths
        return paths.read_json(paths.path(paths.HELD, held_name + '.json'))

    def _held_deliver(self, me, held_name):
        """cli._held_deliver with the person's yes, as migration/replay_test.py drives it."""
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli.registry, 'me', return_value=me), \
                mock.patch.object(cli, '_person_or_refuse', return_value=None), \
                mock.patch.object(cli, '_verdict', 'yes', create=True), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli._held_deliver(mock.Mock(id=held_name))
        return code, out.getvalue(), err.getvalue()

    def _call(self, me, target, summary='goal: ship; open: T9', plan=None):
        """One hand_over call. `plan` is the connections to copy (P3); without one it is made inside."""
        from xsm import handover
        return handover.hand_over(me, target, summary, 'state-model test', plan)

    def _no_links(self, me, target):
        """A plan that copies nothing: the person's approval listed no connection."""
        from xsm import handover
        return dict(handover.plan_links(me, target), links=[])

    # ---- observations of the real stored state ----
    def team(self):
        from xsm import teams
        t = teams.require('core')
        members = sorted(name(m) for m in t['members'] if name(m) != 'bee')   # bee is a plain member
        return members, name(t['lead']) if t.get('lead') else None

    def question_sender(self, request_id='q1'):
        from xsm import paths, questions
        return paths.read_json(questions._filename(request_id))['sender']['session_id']

    def question_status(self, holder, request_id='q1'):
        """What question-status does: index the replies the holder has, then read."""
        from xsm import questions, receive
        receive.poll_replies(holder, request_id)
        return questions.status(holder, request_id)

    def assert_names_next_action(self, message, successor):
        """A refusal names who the place went to and what to do instead."""
        text = message.lower()
        self.assertIn(successor.lower(), text, 'the refusal must name the session to go to: %r' % message)
        self.assertTrue(any(w in text for w in ('instead', 'run ', 'from ', 'try ', 'ask ', 'hand over', 'xsm handover')),
                        'the refusal must say what to do next: %r' % message)

    # ================= SM-F1: a held DM goes to B held, with no body in the letter =================

    def _held_at_lead(self, body='SECRET-HELD-BODY'):
        from xsm import ledger
        mid = self._send(self.lead, body).msg_id
        self._hold(self.lead)
        self.assertEqual(ledger.receipt_of(mid)['decision'], 'held')
        names = self._held_names()
        self.assertEqual(len(names), 1)
        return mid, names[0]

    # Fixed in P2 (SM-F1)
    # Today: wrong value. move_out closes the held original as moved and _letter prints its body.
    def test_SM_F1_letter_has_no_held_body_and_counts_it(self):
        from xsm import handover
        self._held_at_lead()
        rec = self._hand_over()
        self.assertNotIn('SECRET-HELD-BODY', rec['letter'])
        self.assertIn('1 held', rec['letter'])
        shown = handover.notice(self.new)
        self.assertNotIn('SECRET-HELD-BODY', shown)
        self.assertIn('1 held', shown)

    # Fixed in P2 (SM-F1)
    # Today: wrong value. B has no copy of the original at all (status 'not-found'), so nothing is B's to hold.
    def test_SM_F1_successor_owns_the_held_original_and_its_inbox_hides_it(self):
        from xsm import handoff, ledger, receive
        mid, _ = self._held_at_lead()
        self._hand_over()
        self.assertEqual(handoff.status(self.new, mid)['status'], 'pending')
        self.assertEqual(ledger.receipt_of(mid)['decision'], 'held')
        out = receive.take_inbox_claims(self.new)
        self.assertEqual(out['claims'], [])
        self.assertFalse(any('SECRET-HELD-BODY' in m for m in out['messages']))
        self.assertEqual(handoff.status(self.lead, mid)['moved_to']['session_id'], 'next')

    # Fixed in P2 (SM-F1)
    # Today: wrong value. The held entry stays bound to A's ref (receiver_ref == A).
    def test_SM_F1_held_entry_is_rebound_to_the_successor_with_the_same_reason(self):
        _, held_name = self._held_at_lead()
        reason = self._held_entry(held_name)['reason']
        self._hand_over()
        names = self._held_names()
        self.assertEqual(len(names), 1)
        entry = self._held_entry(names[0])
        self.assertEqual(entry['receiver_ref'], self.new['ref'])
        self.assertEqual(entry['reason'], reason)

    # Fixed in P2 (SM-F1)
    # Today: wrong value. `held deliver` at B is refused (exit 2: "held for another session").
    def test_SM_F1_held_deliver_at_the_successor_shows_the_message(self):
        self._held_at_lead()
        self._hand_over()
        names = self._held_names()
        self.assertEqual(len(names), 1)
        code, out, err = self._held_deliver(self.new, names[0])
        self.assertEqual(code, 0, err)
        self.assertIn('SECRET-HELD-BODY', out)

    # ================= SM-F2a: an answer waiting at A is B's answer =================

    # Fixed in P2 (SM-F2a)
    # Today: wrong value. The reply sits unindexed in A's folder; B's question stays 'pending' with no replies.
    def test_SM_F2a_unconsumed_reply_at_A_is_final_for_B(self):
        self._question('q1', self.lead, self.bee)
        self._send(self.lead, 'ANSWER-42', kind='reply', reply_to='q1', outcome='succeeded')
        self._hand_over()
        status = self.question_status(self.new)
        self.assertEqual(status['status'], 'final')
        self.assertEqual(len(status['replies']), 1)

    # Fixed in P2 (SM-F2a)
    # Today: wrong value ('pending', no replies). Here B is in another folder and P has no scope with B:
    # the answer must still be B's (the copy of A's connections is not what carries it).
    def test_SM_F2a_final_for_B_registered_in_another_folder(self):
        self._outside()
        self._question('q1', self.a2, self.p2)
        self._send(self.a2, 'ANSWER-42', sender=self.p2, kind='reply', reply_to='q1', outcome='succeeded')
        self._call(self.a2, self.far)
        status = self.question_status(self.far)
        self.assertEqual(status['status'], 'final')
        self.assertEqual(len(status['replies']), 1)

    # ================= SM-F2b: an answer arriving while the handover runs goes to B =================

    def test_SM_F2b_reply_arriving_after_the_questions_step_goes_to_B_and_is_recorded(self):
        from xsm import handover
        self._question('q1', self.lead, self.bee)
        real = handover._questions
        sent = {}

        def questions_then_answer(*a, **k):
            moved = real(*a, **k)
            sent['r'] = self._send(self.lead, 'ANSWER-MID', kind='reply', reply_to='q1', outcome='succeeded')
            return moved
        with mock.patch.object(handover, '_questions', side_effect=questions_then_answer):
            self._hand_over()
        self.assertEqual(sent['r'].target['session_id'], 'next')
        status = self.question_status(self.new)
        self.assertEqual(status['status'], 'final')
        self.assertEqual([r.get('id') for r in status['replies']], [sent['r'].msg_id])

    # ================= SM-F14: an answer B reads inside the handover window is B's at once =================

    # Today: wrong value. Between _begin (follow(A) == B) and the questions step the question's
    # sender is still A, so record_reply refuses B as the receiver: B reads the answer and its
    # question record stays 'pending' until B polls (scratchpad/probe_gaps.py gap 1).
    def test_SM_F14_answer_read_by_B_before_the_questions_step_is_final_without_polling(self):
        from xsm import handover, questions, receive
        self._question('q1', self.lead, self.bee)
        real = handover._questions
        seen = {}

        def answer_then_questions(me, target):
            seen['r'] = self._send(self.lead, 'ANSWER-WINDOW', kind='reply', reply_to='q1', outcome='succeeded')
            seen['taken'] = receive.take_inbox_claims(self.new)          # B reads it now, mid-handover
            return real(me, target)
        with mock.patch.object(handover, '_questions', side_effect=answer_then_questions):
            self._hand_over()
        self.assertEqual(seen['r'].target['session_id'], 'next')
        self.assertTrue(any('ANSWER-WINDOW' in m for m in seen['taken']['messages']), seen['taken'])
        status = questions.status(self.new, 'q1')                        # no poll_replies
        self.assertEqual(status['status'], 'final')
        self.assertEqual([r.get('id') for r in status['replies']], [seen['r'].msg_id])

    # Today: wrong value, too. The unit: while the record is `moving`, B is the receiver of A's question.
    def test_SM_F14_record_reply_takes_the_successor_of_the_record_sender_while_moving(self):
        from xsm import handover, questions
        self._question('q1', self.lead, self.bee)
        seen = {}
        real = handover._questions

        def probing(me, target):
            seen['b'] = self._reply('q1', 'rB', self.new, self.bee, outcome='succeeded')
            seen['out'] = self._reply('q1', 'rO', self.out, self.bee)
            return real(me, target)
        with mock.patch.object(handover, '_questions', side_effect=probing):
            self._hand_over()
        self.assertTrue(seen['b'])
        self.assertFalse(seen['out'], 'a session that is not the successor must not be taken as the asker')
        self.assertEqual([r['id'] for r in questions.status(self.new, 'q1')['replies']], ['rB'])

    def test_control_SM_F14_the_read_rule_is_not_widened(self):
        # A new question A asks after the handover is not visible to B (spec 3.4).
        from xsm import questions
        self._hand_over()
        self._question('q-after', self.lead, self.bee)
        self.assertEqual(questions.status(self.new, 'q-after')['status'], 'refused')

    # ================= SM-F16: a team A left between the board step and the team step =================

    def _leave_before_the_teams_step(self, team_name='core'):
        """A leaves `team_name` itself after the boards step moved its items and before _teams runs."""
        from xsm import handover, teams
        real = handover._teams

        def left_first(me, target, places, approval):
            teams.remove(self.lead, team_name, teams.member_of(self.lead), None)
            return real(me, target, places, approval)
        return mock.patch.object(handover, '_teams', side_effect=left_first)

    def _heads(self, team_name, item):
        from xsm import board
        return [h['body'] for h in board.current(team_name).get(item, [])]

    # Today: wrong value. owner/next keeps the moved text in a team next is not in (probe_gaps.py gap 3).
    def test_SM_F16_a_team_A_left_meanwhile_keeps_no_owner_B_item_and_A_has_its_content_back(self):
        from xsm import board, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        with self._leave_before_the_teams_step():
            rec = self._hand_over()
        team = teams.require('core')
        self.assertFalse(teams.is_member(team, self.new), 'B must not be seated in a team A had left')
        self.assertFalse(teams.is_member(team, self.lead))
        mine = self._heads('core', 'owner/lead')
        self.assertEqual(len(mine), 1)
        self.assertTrue(mine[0].startswith('the release plan'), mine)
        self.assertIn('returned', mine[0])
        theirs = self._heads('core', 'owner/next')
        self.assertEqual(len(theirs), 1)
        self.assertTrue(theirs[0].startswith('returned'), theirs)
        self.assertIn('lead left', theirs[0])
        self.assertIn('core', rec['skipped']['teams'])
        self.assertNotIn('release plan', theirs[0])

    def test_SM_F16_the_result_and_the_letter_name_the_team_as_skipped_and_list_no_moved_items(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        board.set_item(self.lead, 'core', 'owner/lead/docs', 'README')
        with self._leave_before_the_teams_step():
            rec = self._hand_over()
        self.assertIn('core', rec['skipped']['teams'])
        self.assertEqual(rec['items'].get('core') or [], [])
        self.assertEqual([t['team'] for t in rec['teams']], [])
        self.assertIn('core', rec['letter'])
        self.assertIn('not moved', rec['letter'])
        self.assertNotIn('board items owner', rec['letter'])

    def test_SM_F16_a_team_A_stayed_in_still_moves_as_one_unit(self):
        from xsm import board, teams
        teams.create(self.lead, 'ops')
        board.set_item(self.lead, 'core', 'owner/lead', 'core plan')
        board.set_item(self.lead, 'ops', 'owner/lead', 'ops plan')
        with self._leave_before_the_teams_step('core'):
            rec = self._hand_over()
        self.assertTrue(teams.is_member(teams.require('ops'), self.new))
        self.assertEqual(rec['items']['ops'], ['owner/lead'])
        self.assertIn('ops plan', self._heads('ops', 'owner/next')[0])
        self.assertFalse(teams.is_member(teams.require('core'), self.new))
        self.assertTrue(self._heads('core', 'owner/lead')[0].startswith('core plan'))

    def test_SM_F16_the_revert_runs_again_without_writing_twice(self):
        from xsm import board, handover
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        with self._leave_before_the_teams_step():
            rec = self._hand_over()
        before = (self._heads('core', 'owner/lead'), self._heads('core', 'owner/next'),
                  len(board.doc.read(board.path('core'))))
        handover._teams(self.lead, self.new, rec['places'], 'x')          # a resumed run: the same team is left
        after = (self._heads('core', 'owner/lead'), self._heads('core', 'owner/next'),
                 len(board.doc.read(board.path('core'))))
        self.assertEqual(before, after)

    def test_SM_F16_a_process_that_dies_inside_the_revert_is_finished_by_running_it_again(self):
        from xsm import board, doc, handover, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        real_teams, real_add, calls = handover._teams, doc.add, {'n': 0}

        def dies_on_the_second_write(*a, **k):
            calls['n'] += 1
            if calls['n'] == 2:
                raise _Crash()
            return real_add(*a, **k)

        def leave_then_die_inside_the_revert(me, target, places, approval):
            teams.remove(self.lead, 'core', teams.member_of(self.lead), None)
            with mock.patch.object(doc, 'add', side_effect=dies_on_the_second_write):
                return real_teams(me, target, places, approval)
        with mock.patch.object(handover, '_teams', side_effect=leave_then_die_inside_the_revert):
            with self.assertRaises(_Crash):
                self._hand_over()
        self.assertEqual(calls['n'], 2, 'the process must die inside the revert, on its second write')
        self.assertEqual(handover.load(self.lead)['state'], 'moving')
        rec = self._hand_over()                                      # the same target: finishes it
        self.assertEqual(rec['state'], 'done')
        self.assertIn('core', rec['skipped']['teams'])
        self.assertEqual(len(self._heads('core', 'owner/lead')), 1)
        self.assertTrue(self._heads('core', 'owner/lead')[0].startswith('the release plan'))
        self.assertEqual(len(self._heads('core', 'owner/next')), 1)
        self.assertTrue(self._heads('core', 'owner/next')[0].startswith('returned'))
        self.assertFalse(teams.is_member(teams.require('core'), self.new))

    def test_control_SM_F16_a_team_A_never_left_moves_with_its_items(self):
        from xsm import board, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        rec = self._hand_over()
        self.assertTrue(teams.is_member(teams.require('core'), self.new))
        self.assertEqual(rec['items']['core'], ['owner/lead'])
        self.assertNotIn('core', rec['skipped']['teams'])

    # ================= SM-F5: concurrent handovers on one machine =================

    def _race(self, first, second):
        """Two real hand_over calls in two threads, overlapped on purpose.

        Both threads park at the entry of handover._teams (the step before the
        places move). Today nothing excludes them: the second thread arrives
        there while the first is parked, and the test lets it run to the end
        first, then the first. With the planned machine-wide lock the second
        thread cannot arrive (it waits for the lock), so the test lets the
        first one go after a short wait and the second runs after it.
        Returns {1: outcome, 2: outcome}; an outcome has 'result' or 'exc'.
        """
        from xsm import handover
        real = handover._teams
        local = threading.local()
        outcomes = {1: {}, 2: {}}
        parked = {1: threading.Event(), 2: threading.Event()}
        release = {1: threading.Event(), 2: threading.Event()}

        def teams_gate(*a, **k):
            label = getattr(local, 'label', None)
            if label and not release[label].is_set():
                parked[label].set()
                release[label].wait(RACE_STEP)
            return real(*a, **k)

        def body(label, me, target):
            local.label = label
            try:
                outcomes[label]['result'] = self._call(me, target, 'summary %d' % label)
            except BaseException as exc:    # noqa: BLE001 - the outcome is what is observed
                outcomes[label]['exc'] = exc

        threads = {1: threading.Thread(target=body, args=(1,) + first, daemon=True),
                   2: threading.Thread(target=body, args=(2,) + second, daemon=True)}
        with mock.patch.object(handover, '_teams', side_effect=teams_gate):
            threads[1].start()
            self.assertTrue(parked[1].wait(RACE_STEP), 'the first handover never reached its teams step')
            threads[2].start()
            if parked[2].wait(1.5):                     # no lock: the second overtakes the first
                release[2].set()
                threads[2].join(RACE_STEP)
            release[1].set()
            threads[1].join(RACE_STEP)
            release[2].set()
            threads[2].join(RACE_STEP)
        for label, thread in threads.items():
            self.assertFalse(thread.is_alive(), 'handover %d did not finish' % label)
        return outcomes

    def _late_answer(self):
        """P answers q1 to A's old address; whoever follow() picks records it."""
        sent = self._send(self.lead, 'ANSWER-42', kind='reply', reply_to='q1', outcome='succeeded')
        holder = {'lead': self.lead, 'next': self.new, 'out': self.out}[self.question_sender()]
        dest = sent.target
        self.assertEqual(dest['session_id'], holder['session_id'], 'the reply went to a session that is not the asker')
        return self.question_status(holder)

    def test_SM_F5_A_to_B_with_A_to_C_leaves_one_successor_and_refuses_the_other(self):
        from xsm import handover
        self._question('q1', self.lead, self.bee)
        out = self._race((self.lead, self.new), (self.lead, self.out))
        self.assertIn('result', out[1], out[1])
        self.assertIsInstance(out[2].get('exc'), handover.HandoverError, out[2])
        self.assert_names_next_action(str(out[2]['exc']), 'next')
        self.assertEqual(self.team(), (['next'], 'next'))
        self.assertEqual(self.question_sender(), 'next')
        self.assertEqual(handover.follow(self.lead)[0]['session_id'], 'next')
        self.assertEqual(handover.load(self.lead)['to']['session_id'], 'next')
        self.assertEqual(self._late_answer()['status'], 'final')

    def test_SM_F5_A_to_B_with_B_to_A_refuses_the_cycle(self):
        from xsm import handover
        self._question('q1', self.lead, self.bee)
        out = self._race((self.lead, self.new), (self.new, self.lead))
        self.assertIn('result', out[1], out[1])
        self.assertIsInstance(out[2].get('exc'), handover.HandoverError, out[2])
        self.assert_names_next_action(str(out[2]['exc']), 'next')
        self.assertIsNone(handover.load(self.new))
        self.assertEqual(handover.follow(self.new), (self.new, None))
        self.assertEqual(handover.follow(self.lead)[0]['session_id'], 'next')
        self.assertEqual(self.team(), (['next'], 'next'))
        self.assertEqual(self.question_sender(), 'next')

    def test_SM_F5_A_to_B_with_B_to_C_is_a_chain_and_the_seat_follows_it(self):
        from xsm import handover
        self._question('q1', self.lead, self.bee)
        out = self._race((self.lead, self.new), (self.new, self.out))
        self.assertIn('result', out[1], out[1])
        self.assertIn('result', out[2], out[2])
        self.assertEqual(self.team(), (['out'], 'out'))
        self.assertEqual(self.question_sender(), 'out')
        self.assertEqual(handover.load(self.lead)['to']['session_id'], 'next')
        self.assertEqual(handover.load(self.new)['to']['session_id'], 'out')
        self.assertEqual(handover.follow(self.lead)[0]['session_id'], 'out')
        self.assertEqual(self._late_answer()['status'], 'final')

    def test_SM_F5_a_refusal_names_the_next_action(self):
        from xsm import handover
        self._hand_over()
        with self.assertRaises(handover.HandoverError) as double:
            self._call(self.lead, self.out)                 # A again, to C
        self.assert_names_next_action(str(double.exception), 'next')
        with self.assertRaises(handover.HandoverError) as cycle:
            self._call(self.new, self.lead)                 # B back to A
        self.assert_names_next_action(str(cycle.exception), 'lead')

    def test_control_sequential_double_handover_and_cycle_are_refused_and_a_chain_is_not(self):
        from xsm import handover
        self._question('q1', self.lead, self.bee)
        self._hand_over()
        with self.assertRaises(handover.HandoverError):
            self._call(self.lead, self.out)
        with self.assertRaises(handover.HandoverError):
            self._call(self.new, self.lead)
        self._call(self.new, self.out)                      # B -> C: a chain
        self.assertEqual(self.team(), (['out'], 'out'))
        self.assertEqual(self.question_sender(), 'out')
        self.assertEqual(handover.follow(self.lead)[0]['session_id'], 'out')

    # ================= SM-F5r: a crash after the record was begun =================

    def _crash_in_teams(self):
        from xsm import handover
        with mock.patch.object(handover, '_teams', side_effect=_Crash('simulated process death')):
            with self.assertRaises(_Crash):
                self._hand_over()

    def test_SM_F5r_interrupted_handover_is_moving_then_the_same_target_finishes_it(self):
        from xsm import handover
        self._question('q1', self.lead, self.bee)
        self._crash_in_teams()
        rec = handover.load(self.lead)
        self.assertIsNotNone(rec, 'the handover was begun: a record must say so')
        self.assertEqual(rec['state'], 'moving')
        self.assertEqual(handover.follow(self.lead)[0]['session_id'], 'next')       # F2b: from `begin` on
        self.assertIsNone(handover.notice(self.new))                                # letters only when done
        done = self._hand_over()                                                    # same target: resume
        self.assertIn('letter', done)
        self.assertEqual(handover.load(self.lead)['state'], 'done')
        self.assertEqual(self.team(), (['next'], 'next'))
        self.assertEqual(self.question_sender(), 'next')
        self.assertIn('[xsm handover]', handover.notice(self.new) or '')           # the letter, once done

    def test_SM_F5r_resume_keeps_the_successors_board_item_original(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        self._crash_in_teams()
        self._hand_over()
        body = board.current('core')['owner/next'][0]['body']
        self.assertIn('the release plan', body)
        self.assertNotIn('handed over to', body)

    # ================= SM-SEAM: handover asks the person nothing but its approval =================

    def _asked(self):
        from xsm import paths
        folder = paths.path('asked')
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    # Fixed in P2 (SM-SEAM)
    # Today: wrong value. The DM goes into the letter and B's inbox is empty; the gate is never asked.
    # B shares no scope with P, so the delivered copy must pass (a marker is allowed), never hold.
    def test_SM_SEAM_unread_dm_without_scope_with_B_is_delivered_and_nothing_is_asked(self):
        from xsm import ledger, receive
        self._outside()
        mid = self._send(self.a2, 'SEAM-BODY', sender=self.p2).msg_id
        self._call(self.a2, self.far)
        out = receive.take_inbox_claims(self.far)                  # real gate decision, nothing mocked
        self.assertTrue(any('SEAM-BODY' in m for m in out['messages']), out['messages'])
        receipt = ledger.receipt_of(mid)
        self.assertNotIn((receipt or {}).get('decision'), ('held', 'blocked'))
        self.assertEqual(self._held_names(), [])
        self.assertEqual(self._asked(), [])

    # ================= SM-COMPAT =================

    def _folder_records(self, me):
        from xsm import handoff
        folder = handoff._folder(me)
        try:
            names = sorted(n for n in os.listdir(folder) if n.endswith('.json'))
        except OSError:
            return {}
        out = {}
        for n in names:
            with open(os.path.join(folder, n), encoding='utf-8') as fh:
                out[n[:-5]] = json.load(fh)
        return out

    # Fixed in P2 (SM-COMPAT)
    # Today: wrong value. Nothing is copied into B's handoffs folder (the DM goes into the letter), so there is
    # no record to carry handover_history.
    def test_SM_COMPAT_moved_records_carry_handover_history_and_not_migration_history(self):
        from xsm import handoff
        mid = self._send(self.lead, 'COMPAT-BODY').msg_id
        self._hand_over()
        records = self._folder_records(self.new)
        self.assertIn(mid, records)
        moved = records[mid]
        hop = (moved.get('handover_history') or [None])[-1]
        self.assertIsNotNone(hop, 'the copy must say it came by handover')
        self.assertEqual(hop['source'], handoff._identity(self.lead))
        self.assertEqual(hop['target'], handoff._identity(self.new))
        for rid, rec in records.items():
            self.assertFalse(rec.get('migration_history'), '0.6.1 readers check only this field: %s' % rid)
        self.assertIn(mid, [r['id'] for r in handoff.records(self.new)])    # raises if B's folder is unreadable

    def test_control_SM_COMPAT_a_record_without_state_reads_as_done(self):
        """A handovers/<A>.json written by 0.6.1 has no `state`, `id` or step marks."""
        from xsm import handover, paths
        done = self._hand_over()
        legacy_keys = ('t', 'from', 'from_identity', 'to', 'to_identity', 'approval', 'teams', 'items',
                       'questions', 'groups', 'messages', 'letter')
        legacy = {k: done[k] for k in legacy_keys}
        legacy['shown'] = False
        paths.write_json(handover._file(handover._identity(self.lead)), legacy)
        rec, note = handover.follow(self.lead)
        self.assertEqual(rec['session_id'], 'next')
        self.assertIn('handed its place over to next', note)
        self.assertIn('[xsm handover]', handover.notice(self.new))
        with self.assertRaises(handover.HandoverError):
            self._call(self.lead, self.out)                         # still counts as handed over
        # P3 (spec 0): a target that handed over is followed to the end of its chain, not refused.
        with self.assertRaises(handover.HandoverError):
            self._call(self.new, self.lead)                         # B back to A is still a loop
        rec = self._call(self.out, self.lead)
        self.assertEqual(rec['to']['session_id'], 'next')
        self.assertTrue(any('handed its place over' in n for n in rec['notes']), rec['notes'])


    # ================= P2: hand_to, the gate rule and the proofs (written with the fix) =================

    def test_P2_a_digest_conflict_keeps_that_one_at_A_and_the_rest_moves(self):
        from xsm import handoff
        m1 = self._send(self.lead, 'FIRST').msg_id
        m2 = self._send(self.lead, 'SECOND').msg_id
        # B already holds a different request under m1's id
        handoff.store(self.new, {'id': m1, 'sender': handoff._identity(self.bee),
                                 'target': handoff._identity(self.new), 'body': 'OTHER', 'kind': 'note',
                                 'content': '[xsm] other'})
        rec = self._hand_over()
        self.assertEqual(rec['messages'], [m2])
        self.assertEqual([k['id'] for k in rec['kept_messages']], [m1])
        self.assertIsNone(handoff.status(self.lead, m1).get('moved_to'))     # still A's
        self.assertEqual(handoff.status(self.lead, m1)['status'], 'pending')
        self.assertEqual(handoff.status(self.lead, m2)['moved_to']['session_id'], 'next')
        self.assertIn(m1, rec['letter'])
        self.assertNotIn('FIRST', rec['letter'])

    def test_P2_hand_to_is_idempotent_per_handover_id(self):
        from xsm import handoff, handover
        mid = self._send(self.lead, 'ONCE').msg_id
        hid = handover._begin(self.lead, self.new, 'summary', 'x')['id']     # the record that stands for the hop
        first = handoff.hand_to(self.lead, self.new, hid)
        stored = handoff.status(self.new, mid)
        second = handoff.hand_to(self.lead, self.new, hid)
        self.assertEqual((first['moved'], first['kept']), ([mid], []))
        self.assertEqual((second['moved'], second['kept']), ([mid], []))
        self.assertEqual(handoff.status(self.new, mid)['handover_history'], stored['handover_history'])
        self.assertEqual(len(stored['handover_history']), 1)

    def test_P2_acknowledged_originals_stay_and_do_not_move(self):
        from xsm import handoff
        mid = self._send(self.lead, 'READ').msg_id
        claim = handoff.claim(self.lead, {'type': 'native', 'id': 'p'}, 'g')
        handoff.ack(self.lead, claim['claim']['token'], {'type': 'native', 'id': 'p'}, 'g')
        rec = self._hand_over()
        self.assertEqual(rec['messages'], [])
        self.assertEqual(handoff.status(self.new, mid)['status'], 'not-found')

    def test_P2_a_forged_handover_hop_is_not_read(self):
        from xsm import handoff, handover, paths
        mid = self._send(self.lead, 'PROOF').msg_id
        self._hand_over()
        self.assertEqual(handoff.status(self.new, mid)['status'], 'pending')
        os_remove = __import__('os').remove
        os_remove(handover._file(handover._identity(self.lead)))           # nothing stands for the hop
        with self.assertRaises(ValueError):
            handoff.status(self.new, mid)

    def test_P2_the_copy_says_what_state_A_left_it_in_and_B_is_told(self):
        from xsm import handoff, receive
        mid = self._send(self.lead, 'SHOWN-AT-A').msg_id
        claim = handoff.claim(self.lead, {'type': 'native', 'id': 'p'}, 'g')
        handoff.handoff(self.lead, claim['claim']['token'], {'type': 'native', 'id': 'p'}, 'g')
        self._hand_over()
        self.assertEqual(handoff.status(self.new, mid)['handover_history'][-1]['previous_state'], 'handoff-recorded')
        out = receive.take_inbox_claims(self.new)
        text = '\n'.join(out['messages'])
        self.assertIn('SHOWN-AT-A', text)
        self.assertIn('prior processing state: handoff-recorded', text)

    def test_P2_without_scope_the_message_comes_with_a_marker_not_a_hold(self):
        from xsm import receive
        self._outside()
        self._send(self.a2, 'MARKED', sender=self.p2)
        # P3 copies A's folder to B as a reach, which would give B a scope with P; this test is about
        # B having none, so it hands over with a plan that copies nothing.
        self._call(self.a2, self.far, plan=self._no_links(self.a2, self.far))
        out = receive.take_inbox_claims(self.far)
        text = '\n'.join(out['messages'])
        self.assertIn('MARKED', text)
        self.assertIn('share no scope with its sender', text)
        self.assertEqual(self._held_names(), [])

    def test_P2_a_blocked_sender_stays_blocked_after_the_handover(self):
        from xsm import config, ledger, receive
        mid = self._send(self.lead, 'FROM-BLOCKED').msg_id
        self._hand_over()
        with mock.patch.object(config, 'blocked', return_value=[self.bee['ref']]):
            out = receive.take_inbox_claims(self.new)
        self.assertFalse(any('FROM-BLOCKED' in m for m in out['messages']))
        self.assertIn(ledger.receipt_of(mid)['decision'], ('held', 'blocked'))

    def test_P2_a_hold_for_scope_is_lifted_when_B_has_a_scope_with_the_sender(self):
        from xsm import ledger, receive
        mid = self._send(self.lead, 'WAS-OUT-OF-SCOPE').msg_id
        from xsm import receive as r
        with mock.patch.object(r, 'check', return_value=('block', 'out of scope: test')):
            receive.take_inbox_claims(self.lead)
        self.assertEqual(len(self._held_names()), 1)
        self._hand_over()                                                  # bee shares team core with next
        out = receive.take_inbox_claims(self.new)
        self.assertTrue(any('WAS-OUT-OF-SCOPE' in m for m in out['messages']), out['messages'])
        self.assertEqual(self._held_names(), [])
        self.assertEqual(ledger.receipt_of(mid)['decision'], 'delivered')

    def test_P2_the_letter_counts_held_and_unread_apart_and_never_prints_a_body(self):
        self._held_at_lead('HELD-BODY')
        self._send(self.lead, 'UNREAD-BODY')
        rec = self._hand_over()
        self.assertIn('1 unread DM moved to you', rec['letter'])
        self.assertIn('1 held DM moved to you', rec['letter'])
        self.assertNotIn('HELD-BODY', rec['letter'])
        self.assertNotIn('UNREAD-BODY', rec['letter'])
        self.assertEqual(len(rec['messages']), 2)
        self.assertEqual(len(rec['held_messages']), 1)

    def test_P2_the_copy_is_proved_by_its_hop_and_by_nobody_else(self):
        """Any migration history of the original rides inside the hop, where a 0.6.1
        reader does not look; handover.proves_copy walks it, then the handover."""
        from xsm import handoff
        mid = self._send(self.lead, 'CHAIN').msg_id
        self._hand_over()
        copy = handoff.status(self.new, mid)
        self.assertIsNone(copy.get('migration_history'))
        self.assertEqual(copy['handover_history'][-1]['migrations'], [])
        self.assertTrue(handoff.proves_ownership(copy, self.new))
        self.assertFalse(handoff.proves_ownership(copy, self.out))

    def test_P2_a_native_copy_at_A_after_the_handover_is_not_shown_or_held_at_A(self):
        # Q1 is measured by tests/test_state_model_held.py (SM_F12). Here the hook's answer.
        from xsm import adapters, receive, send
        with mock.patch.object(adapters, 'to_codex', return_value='Queued message q for thread lead.') as transport:
            sent = send.send('ref:' + self.lead['ref'], 'NATIVE-AT-A', sender=self.bee)
        wire = transport.call_args.args[2]
        self._hand_over()
        with mock.patch.object(receive, 'register', return_value=self.lead):
            out = receive.handle({'hook_event_name': 'UserPromptSubmit', 'session_id': 'lead', 'turn_id': 't',
                                  'cwd': self.tmp, 'prompt': wire})
        self.assertEqual((out or {}).get('decision'), 'block')
        self.assertIn('next', json.dumps(out))
        self.assertEqual(self._held_names(), [])
        got = receive.take_inbox_claims(self.new)
        self.assertTrue(any('NATIVE-AT-A' in m for m in got['messages']))


# The inherited HandoverTest cases are not this module's: leave them to test_handover.
for _inherited in [n for n in dir(test_handover.HandoverTest) if n.startswith('test')]:
    setattr(StateModelHandover, _inherited, None)
del _inherited


if __name__ == '__main__':
    unittest.main()
