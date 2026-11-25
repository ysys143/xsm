"""Replay TLC's shortest paths of XsmConcurrentHandover against xsm's real code.

A = self.lead (holds the team place, asked question q1 of P), B = self.new,
C = self.out, P = self.bee (HandoverTest fixture).

Each model action is one real segment of handover.hand_over, run to the next
gate. Two real hand_over calls run in two threads; a scheduler lets exactly one
thread run at a time. The gates are the entries of the real internal functions
handover._teams, handover._questions and handover._letter (the call right
before handovers/<from>.json is written), wrapped so they wait for the
scheduler and then call the real function:

  Check      thread starts: hand_over -> _check -> (_boards loop) -> up to _teams
  Teams      real _teams runs, then hand_over goes on to the entry of _questions
  Questions  real _questions, _groups, _unread run, then the entry of _letter
  Record     real _letter, the write of handovers/<from>.json, team_sync.publish,
             _publish run to the end
  Answer     (main thread) P sends a real kind=reply message through send.send;
             the receiver then runs the real receive.poll_replies

Mocked: adapters.to_codex only (the transport that would wake a Codex thread).
No gate decision is mocked. No network service runs (network.available() is
false in a temp XSM_HOME), so _publish returns its "not sent" note.

Run from the repository root:
  python3 <this file> -v Replay.test_a_two_successors
"""
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.getcwd())
from tests.test_handover import HandoverTest  # noqa: E402

TL = threading.local()
STEP_TIMEOUT = 20


class Run:
    """One real hand_over call in a thread, paused at the gates."""

    def __init__(self, label, hand_over, me, target):
        self.label, self._hand_over, self.me, self.target = label, hand_over, me, target
        self.go, self.at = threading.Event(), threading.Event()
        self.gate, self.done, self.exc, self.result = None, False, None, None
        self.thread = threading.Thread(target=self._main, daemon=True)

    def _main(self):
        TL.run = self
        try:
            self.result = self._hand_over(self.me, self.target, 'summary of %s' % self.label, 'replay')
        except Exception as exc:  # noqa: BLE001
            self.exc = exc
        finally:
            self.done, self.gate = True, 'finished'
            self.at.set()

    def arrive(self, gate):
        self.gate = gate
        self.go.clear()
        self.at.set()
        if not self.go.wait(STEP_TIMEOUT):
            raise RuntimeError('scheduler never released %s at %s' % (self.label, gate))

    def check(self):
        self.thread.start()
        self._wait()
        return self.gate

    def release(self):
        self.at.clear()
        self.go.set()
        self._wait()
        return self.gate

    def _wait(self):
        if not self.at.wait(STEP_TIMEOUT):
            raise RuntimeError('%s did not reach a gate' % self.label)


def name(rec):
    return rec.get('name') or rec.get('session_id')


class Replay(HandoverTest):
    def setUp(self):
        super().setUp()
        from xsm import handover
        self.handover = handover
        self.runs = {}
        for gate, fn in (('teams', '_teams'), ('questions', '_questions'), ('record', '_letter')):
            self._gate(gate, fn)
        self.who = {'A': self.lead, 'B': self.new, 'C': self.out}

    def _gate(self, gate, fn):
        real = getattr(self.handover, fn)

        def wrapper(*a, **k):
            run = getattr(TL, 'run', None)
            if run:
                run.arrive(gate)
            return real(*a, **k)
        p = mock.patch.object(self.handover, fn, side_effect=wrapper)
        p.start()
        self.addCleanup(p.stop)

    # ---- model actions, one real segment each ----
    def act(self, op, plan):
        src, dst = plan[0], plan[-1]
        if op == 'Check':
            run = Run(plan, self.handover.hand_over, self.who[src], self.who[dst])
            self.runs[plan] = run
            gate = run.check()
            expect = 'teams'
        else:
            run = self.runs[plan]
            gate = run.release()
            expect = {'Teams': 'questions', 'Questions': 'record', 'Record': 'finished'}[op]
        self.assertEqual(gate, expect, '%s %s stopped at %s: %r' % (op, plan, gate, run.exc))
        if run.exc:
            self.fail('%s %s raised %r' % (op, plan, run.exc))
        print('  %-9s %s -> now at gate %s' % (op, plan, gate))

    def play(self, path):
        for op, plan in path:
            self.act(op, plan)

    # ---- observations of the real stored state ----
    def team(self):
        from xsm import teams
        t = teams.require('core')
        members = sorted(m.get('name') or m.get('session_id') for m in t['members']
                         if (m.get('name') or m.get('session_id')) != 'bee')   # P (bee) is a plain member, outside the model
        return members, name(t['lead']) if t.get('lead') else None

    def question_sender(self):
        from xsm import paths, questions
        return paths.read_json(questions._filename('q1'))['sender']['session_id']

    def records(self):
        out = {}
        for key, who in (('A', self.lead), ('B', self.new), ('C', self.out)):
            rec = self.handover.load(who)
            if rec:
                out[key] = rec['to']['session_id']
        return out

    def snapshot(self, title):
        from xsm import handover
        members, lead = self.team()
        f = handover.follow(self.lead)
        print('  [%s] team members=%s lead=%s | question q1 sender=%s | handover records=%s | follow(A)=%s'
              % (title, members, lead, self.question_sender(), self.records(),
                 name(f[0]) if f[1] else 'A itself (no record)'))

    def answer(self):
        """P answers q1 as a real reply; the receiver follow() picked runs poll_replies."""
        from xsm import adapters, handoff, questions, receive, send
        with mock.patch.object(adapters, 'to_codex',
                               side_effect=lambda home, thread, content, *a, **k: 'Queued message q for thread %s.' % thread):
            sent = send.send('ref:%s' % self.lead['ref'], 'ANSWER-42', sender=self.bee,
                             kind='reply', reply_to='q1', outcome='succeeded')
        dest = sent.target
        holder = {'lead': self.lead, 'next': self.new, 'out': self.out}[self.question_sender()]
        print('  [answer] P sent the reply to', dest['session_id'], '; the record\'s sender is', holder['session_id'])
        got_dest = receive.poll_replies(dest, 'q1')
        got_holder = receive.poll_replies(holder, 'q1') if holder['session_id'] != dest['session_id'] else got_dest
        status = questions.status(holder, 'q1')
        print('  [answer] poll_replies at the destination indexed %d, at the sender %d; '
              'question status for the sender: %s, replies stored: %d'
              % (got_dest, got_holder, status['status'], len(status['replies'])))
        print('  [answer] questions.expects_reply(dest, P, q1) =', questions.expects_reply(dest, self.bee, 'q1'))
        return dest, status

    def setup_question(self):
        self._question('q1', self.lead, self.bee)

    # ===== hypothesis (a): A to B and A to C at once =====
    def test_a_two_successors(self):
        """scn_a, path to AtMostOneHandoverPerSession, AddressAndPlaceAgree,
        QuestionHolderIsAddressTarget and (with the answer) LateAnswerRecorded."""
        self.setup_question()
        print()
        self.snapshot('start')
        self.play([('Check', 'AB'), ('Check', 'AC'), ('Teams', 'AB'), ('Questions', 'AB'), ('Record', 'AB'),
                   ('Teams', 'AC'), ('Questions', 'AC'), ('Record', 'AC')])
        self.snapshot('end')
        ab, ac = self.runs['AB'], self.runs['AC']
        print('  both calls returned a record: AB ok=%s, AC ok=%s' % (ab.result is not None, ac.result is not None))
        print('  AC letter, teams/asks lines:', [l for l in ac.result['letter'].splitlines()
                                              if l.startswith('- team') or 'pending question' in l or l.startswith('- no team')])
        print('  AB letter, teams/asks lines:', [l for l in ab.result['letter'].splitlines()
                                              if l.startswith('- team') or 'pending question' in l or l.startswith('- no team')])
        members, lead = self.team()
        self.assertEqual((members, lead), (['next'], 'next'))      # the place is B's
        self.assertEqual(self.question_sender(), 'next')           # the question is B's
        self.assertEqual(self.records(), {'A': 'out'})             # but A's record names C (last write wins)
        dest, status = self.answer()
        self.assertEqual(dest['session_id'], 'out')
        self.assertEqual(status['replies'], [])                    # nothing recorded for B
        self.assertEqual(status['status'], 'pending')

    def test_a_control_other_order_is_consistent(self):
        """Same two handovers, but C records first and B records last: the sender and
        the record agree on B, so the answer is stored (the model's good order)."""
        self.setup_question()
        print()
        self.play([('Check', 'AB'), ('Check', 'AC'), ('Teams', 'AB'), ('Questions', 'AB'),
                   ('Teams', 'AC'), ('Questions', 'AC'), ('Record', 'AC'), ('Record', 'AB')])
        self.snapshot('end')
        dest, status = self.answer()
        self.assertEqual(dest['session_id'], 'next')
        self.assertEqual(status['status'], 'final')

    # ===== hypothesis (b): A to B and B to A at once =====
    def test_b_cycle(self):
        """scn_b, path to AddressLeadsAway (shortest, 8 steps)."""
        from xsm import handover, send, adapters
        self.setup_question()
        print()
        self.play([('Check', 'AB'), ('Check', 'BA'), ('Teams', 'AB'), ('Questions', 'AB'), ('Record', 'AB'),
                   ('Teams', 'BA'), ('Questions', 'BA'), ('Record', 'BA')])
        self.snapshot('end')
        self.assertEqual(self.records(), {'A': 'next', 'B': 'lead'})
        a_next = handover.successor_identity(handover._identity(self.lead))
        b_next = handover.successor_identity(handover._identity(self.new))
        print('  successor_identity(A) is A:', a_next == handover._identity(self.lead),
              '| successor_identity(B) is B:', b_next == handover._identity(self.new))
        self.assertEqual(a_next, handover._identity(self.lead))
        self.assertEqual(b_next, handover._identity(self.new))
        rec, note = handover.follow(self.lead)
        print('  follow(A) ->', rec['session_id'], '| note:', note)
        self.assertEqual(rec['session_id'], 'lead')
        self.assertTrue(note)                                      # "lead handed its place over to lead"
        print('  succeeds(B, A) =', handover.succeeds(self.new, self.lead),
              '(B holds the place by handover, per the A -> B record)')
        self.assertFalse(handover.succeeds(self.new, self.lead))
        # And the session that handed over still holds the place:
        members, lead = self.team()
        self.assertEqual((members, lead), (['lead'], 'lead'))
        # A DM to B (which also handed over) goes to A, not away either:
        with mock.patch.object(adapters, 'to_codex',
                               side_effect=lambda home, thread, content, *a, **k: 'Queued message q for thread %s.' % thread):
            r = send.send('ref:%s' % self.new['ref'], 'hello B', sender=self.bee)
        print('  a DM to B reached', r.target['session_id'])

    def test_b_cycle_and_the_late_answer(self):
        """scn_b, path to LateAnswerRecorded (9 steps): B to A writes its record first."""
        self.setup_question()
        print()
        self.play([('Check', 'AB'), ('Check', 'BA'), ('Teams', 'AB'), ('Teams', 'BA'), ('Questions', 'BA'),
                   ('Questions', 'AB'), ('Record', 'BA'), ('Record', 'AB')])
        self.snapshot('end')
        dest, status = self.answer()
        self.assertEqual(self.question_sender(), 'next')
        self.assertEqual(dest['session_id'], 'lead')
        self.assertEqual(status['status'], 'pending')

    # ===== a session that is the target while it hands over itself: A to B and B to C =====
    def test_c_target_hands_over_meanwhile(self):
        """scn_c, path to HandedOverHoldsNoPlace (8 steps): B to C moves the seat before A to B does."""
        self.setup_question()
        print()
        self.play([('Check', 'AB'), ('Check', 'BC'), ('Teams', 'BC'), ('Teams', 'AB'), ('Questions', 'AB'),
                   ('Questions', 'BC'), ('Record', 'BC'), ('Record', 'AB')])
        self.snapshot('end')
        members, lead = self.team()
        self.assertEqual((members, lead), (['next'], 'next'))      # B holds the place ...
        self.assertEqual(self.records().get('B'), 'out')           # ... though B handed over to C
        print('  B (records B -> C) holds the team seat and the lead seat; C holds nothing')
        c_letter = self.runs['BC'].result['letter']
        print('  B to C letter, teams line:', [l for l in c_letter.splitlines() if l.startswith('- team') or l.startswith('- no team')])

    def test_c_target_hands_over_meanwhile_and_the_late_answer(self):
        """scn_c, path to LateAnswerRecorded (9 steps)."""
        self.setup_question()
        print()
        self.play([('Check', 'AB'), ('Check', 'BC'), ('Teams', 'AB'), ('Teams', 'BC'), ('Questions', 'BC'),
                   ('Questions', 'AB'), ('Record', 'BC'), ('Record', 'AB')])
        self.snapshot('end')
        dest, status = self.answer()
        self.assertEqual(self.question_sender(), 'next')
        self.assertEqual(dest['session_id'], 'out')
        self.assertEqual(status['status'], 'pending')

    # ===== controls: the same pairs one after the other =====
    def test_control_sequential_is_refused_or_clean(self):
        from xsm import handover
        self.setup_question()
        print()
        # A to B, then A to C, then B to A, then A to B again: all refused after the first record.
        first = handover.hand_over(self.lead, self.new, 's', 'replay')
        for me, target, why in ((self.lead, self.out, 'A to C'), (self.new, self.lead, 'B to A')):
            with self.assertRaises(handover.HandoverError) as cm:
                handover.hand_over(me, target, 's', 'replay')
            print('  sequential %s refused: %s' % (why, cm.exception))
        # A to B, then B to C: a chain, and the place follows it.
        handover.hand_over(self.new, self.out, 's', 'replay')
        self.snapshot('chain A -> B -> C')
        members, lead = self.team()
        self.assertEqual((members, lead), (['out'], 'out'))
        self.assertEqual(self.question_sender(), 'out')
        dest, status = self.answer()
        self.assertEqual(dest['session_id'], 'out')
        self.assertEqual(status['status'], 'final')


    def test_window_length(self):
        """How long hand_over runs between its own _check and the write of the record (fixture: 1 team,
        1 question, 6 board items; no network service). Not a measure of a real machine's disk or load."""
        import time
        from xsm import board, handover
        self.setup_question()
        for i in range(5):
            board.set_item(self.lead, 'core', 'owner/lead/x%d' % i, 'item %d' % i)
        t0 = time.perf_counter()
        handover.hand_over(self.lead, self.new, 's', 'replay')
        print('\n  hand_over took %.1f ms in the fixture' % ((time.perf_counter() - t0) * 1000))


if __name__ == '__main__':
    unittest.main()
