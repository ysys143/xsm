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

    def _call(self, me, target, summary='goal: ship; open: T9'):
        """One hand_over call. (P3 adds a `plan` argument: adapt here only.)"""
        from xsm import handover
        return handover.hand_over(me, target, summary, 'state-model test')

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

    # RED until P2 (SM-F1)
    # Today: wrong value. move_out closes the held original as moved and _letter prints its body.
    @unittest.expectedFailure
    def test_SM_F1_letter_has_no_held_body_and_counts_it(self):
        from xsm import handover
        self._held_at_lead()
        rec = self._hand_over()
        self.assertNotIn('SECRET-HELD-BODY', rec['letter'])
        self.assertIn('1 held', rec['letter'])
        shown = handover.notice(self.new)
        self.assertNotIn('SECRET-HELD-BODY', shown)
        self.assertIn('1 held', shown)

    # RED until P2 (SM-F1)
    # Today: wrong value. B has no copy of the original at all (status 'not-found'), so nothing is B's to hold.
    @unittest.expectedFailure
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

    # RED until P2 (SM-F1)
    # Today: wrong value. The held entry stays bound to A's ref (receiver_ref == A).
    @unittest.expectedFailure
    def test_SM_F1_held_entry_is_rebound_to_the_successor_with_the_same_reason(self):
        _, held_name = self._held_at_lead()
        reason = self._held_entry(held_name)['reason']
        self._hand_over()
        names = self._held_names()
        self.assertEqual(len(names), 1)
        entry = self._held_entry(names[0])
        self.assertEqual(entry['receiver_ref'], self.new['ref'])
        self.assertEqual(entry['reason'], reason)

    # RED until P2 (SM-F1)
    # Today: wrong value. `held deliver` at B is refused (exit 2: "held for another session").
    @unittest.expectedFailure
    def test_SM_F1_held_deliver_at_the_successor_shows_the_message(self):
        self._held_at_lead()
        self._hand_over()
        names = self._held_names()
        self.assertEqual(len(names), 1)
        code, out, err = self._held_deliver(self.new, names[0])
        self.assertEqual(code, 0, err)
        self.assertIn('SECRET-HELD-BODY', out)

    # ================= SM-F2a: an answer waiting at A is B's answer =================

    # RED until P2 (SM-F2a)
    # Today: wrong value. The reply sits unindexed in A's folder; B's question stays 'pending' with no replies.
    @unittest.expectedFailure
    def test_SM_F2a_unconsumed_reply_at_A_is_final_for_B(self):
        self._question('q1', self.lead, self.bee)
        self._send(self.lead, 'ANSWER-42', kind='reply', reply_to='q1', outcome='succeeded')
        self._hand_over()
        status = self.question_status(self.new)
        self.assertEqual(status['status'], 'final')
        self.assertEqual(len(status['replies']), 1)

    # RED until P2 (SM-F2a)
    # Today: wrong value ('pending', no replies). Here B is in another folder and P has no scope with B:
    # the answer must still be B's (the copy of A's connections is not what carries it).
    @unittest.expectedFailure
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

    # RED until P2 (SM-SEAM)
    # Today: wrong value. The DM goes into the letter and B's inbox is empty; the gate is never asked.
    # B shares no scope with P, so the delivered copy must pass (a marker is allowed), never hold.
    @unittest.expectedFailure
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

    # RED until P2 (SM-COMPAT)
    # Today: wrong value. Nothing is copied into B's handoffs folder (the DM goes into the letter), so there is
    # no record to carry handover_history.
    @unittest.expectedFailure
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
        with self.assertRaises(handover.HandoverError):
            self._call(self.out, self.lead)


# The inherited HandoverTest cases are not this module's: leave them to test_handover.
for _inherited in [n for n in dir(test_handover.HandoverTest) if n.startswith('test')]:
    setattr(StateModelHandover, _inherited, None)
del _inherited


if __name__ == '__main__':
    unittest.main()
