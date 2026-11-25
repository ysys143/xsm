"""Replay the two TLC paths against xsm's real code, one call per action.

A = self.lead, B = self.new, P = self.bee (HandoverTest fixture).
Run from the repository root:
  python3 -m unittest <this file's path>
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.getcwd())
from tests.test_handover import HandoverTest  # noqa: E402


def queued(home, thread, content, *a, **k):
    return 'Queued message q for thread %s.' % thread


class Replay(HandoverTest):
    def _send(self, body, **kw):
        from xsm import adapters, send
        with mock.patch.object(adapters, 'to_codex', side_effect=queued):
            return send.send('ref:%s' % self.lead['ref'], body, sender=self.bee, **kw)

    def test_held_dm_reaches_successor_through_the_letter(self):
        from xsm import handoff, ledger, receive
        sent = self._send('SECRET-HELD-BODY')                      # the DM at A
        self.assertIn(sent.status, ('delivered', 'sent-unconfirmed', 'stored', 'queued'), sent.as_dict())
        mid = sent.msg_id if hasattr(sent, 'msg_id') else sent.as_dict()['id']
        # 1. A's gate refuses the DM (the real inbox path, with check() saying block).
        with mock.patch.object(receive, 'check', return_value=('block', 'out of scope (replay)')):
            out = receive.take_inbox_claims(self.lead)
        self.assertEqual(out['claims'], [])
        self.assertEqual(ledger.receipt_of(mid)['decision'], 'held')
        self.assertNotIn(mid, handoff.pending_ids(self.lead))      # the gate keeps it from A
        print('\n[held] after gate:', handoff.status(self.lead, mid)['status'],
              handoff.status(self.lead, mid)['delivery_state'])
        # 2. the wait times out: no effect on the DM (question not involved here).
        # 3-5. the person approves the handover; unread DMs go into the letter; recorded.
        rec = self._hand_over()
        print('[held] handover messages:', rec['messages'])
        # 6. B reads the letter.
        hook = receive._with_bounces('codex', self.new, None)
        text = hook['hookSpecificOutput']['additionalContext']
        print('[held] SECRET-HELD-BODY in B letter:', 'SECRET-HELD-BODY' in text)
        self.assertIn('SECRET-HELD-BODY', text)

    def test_answer_waiting_at_A_is_never_recorded_for_B(self):
        from xsm import handoff, questions, receive
        self._question('q1', self.lead, self.bee)                  # A asked P
        # 1. P answers (real send; resolves A, stores the original at A).
        sent = self._send('ANSWER-42', kind='reply', reply_to='q1', outcome='succeeded')
        rid = sent.as_dict()['id']
        print('\n[answer] reply stored at A:', handoff.status(self.lead, rid)['status'])
        # 2. the wait times out (A's wait ends without a poll).
        waited = questions.wait_for(self.lead, 'q1', 0)
        self.assertEqual(waited['wait_end_reason'], 'timeout')
        # 3-4. handover: questions move to B, unread originals go into the letter.
        rec = self._hand_over()
        print('[answer] moved questions:', rec['questions'], 'moved messages:', rec['messages'])
        self.assertIn(rid, rec['messages'])
        # Now B is the asker. B checks its question the way question-status does.
        matched = receive.poll_replies(self.new, 'q1')
        status = questions.status(self.new, 'q1')
        print('[answer] B poll matched:', matched, 'B question status:', status['status'])
        # A's hook, if it ever sees the queued native copy, cannot claim it.
        print('[answer] original at A:', handoff.status(self.lead, rid)['status'],
              'moved_to', handoff.status(self.lead, rid).get('moved_to', {}).get('session_id'))
        letter = receive._with_bounces('codex', self.new, None)['hookSpecificOutput']['additionalContext']
        print('[answer] ANSWER-42 in B letter:', 'ANSWER-42' in letter)
        self.assertEqual(status['status'], 'pending')              # the rule breaks
        self.assertIn('ANSWER-42', letter)

    def test_answer_arriving_mid_handover_is_read_by_A_and_never_recorded(self):
        from xsm import handover, questions, receive
        self._question('q1', self.lead, self.bee)
        questions.wait_for(self.lead, 'q1', 0)                     # the wait times out
        real_letter = handover._letter
        sent = {}

        def letter_then_answer(*a, **k):
            # Between _unread (move_out done) and writing handovers/<A>.json:
            # P answers; follow(A) still resolves to A.
            sent['r'] = self._send('ANSWER-MID', kind='reply', reply_to='q1', outcome='succeeded')
            return real_letter(*a, **k)
        with mock.patch.object(handover, '_letter', side_effect=letter_then_answer):
            self._hand_over()                                      # approve .. recorded
        print('\n[mid] reply went to:', sent['r'].as_dict().get('target', {}).get('session_id'))
        out = receive.take_inbox_claims(self.lead)                 # A reads the answer
        print('[mid] A read:', any('ANSWER-MID' in m for m in out['messages']))
        receive.poll_replies(self.new, 'q1')
        status = questions.status(self.new, 'q1')
        print('[mid] B question status:', status['status'])
        self.assertTrue(any('ANSWER-MID' in m for m in out['messages']))
        self.assertEqual(status['status'], 'pending')

    def test_control_answer_recorded_when_A_polls_before_handover(self):
        from xsm import questions, receive
        self._question('q1', self.lead, self.bee)
        self._send('ANSWER-42', kind='reply', reply_to='q1', outcome='succeeded')
        self.assertGreaterEqual(receive.poll_replies(self.lead, 'q1'), 1)  # one per copy found
        self._hand_over()
        self.assertEqual(questions.status(self.lead, 'q1')['status'], 'final')


if __name__ == '__main__':
    unittest.main()
