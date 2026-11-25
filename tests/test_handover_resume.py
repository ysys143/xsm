"""P1 of the state-model fixes: what a begun (moving) handover does besides the SM-F5/F6 tests.

D9: a session with a begun or finished handover is not added to a team, its successor is.
D4: `xsm doctor` lists a handover that did not finish, with the command to finish it.
A new request to another target first finishes the begun one, then is refused as a double handover.
The lock: a second handover waits for the first, and gives up with a next action after the timeout.
"""
import threading
import unittest

from tests import test_handover


class MovingHandover(test_handover.HandoverTest):
    def test_adding_a_session_that_began_a_handover_adds_its_successor(self):
        from xsm import handover, teams
        teams.create(self.bee, 'ops')
        self.assertEqual(handover._begin(self.lead, self.new, 'goal', 'x')['state'], 'moving')
        teams.add(self.bee, 'ops', self.lead, 'x')
        ops = teams.require('ops')
        self.assertTrue(teams.is_member(ops, self.new))
        self.assertFalse(teams.is_member(ops, self.lead))

    def test_doctor_lists_an_unfinished_handover_with_the_command_to_finish_it(self):
        from xsm import cli, handover
        self.assertEqual(cli._unfinished_handovers(), [])
        handover._begin(self.lead, self.new, 'goal', 'x')
        rows = cli._unfinished_handovers()
        self.assertEqual(len(rows), 1)
        self.assertIn('xsm handover ref:%s' % self.new['ref'], rows[0]['note'])
        self.assertEqual(rows[0]['left'], list(handover.STEPS))
        self._hand_over()
        self.assertEqual(cli._unfinished_handovers(), [])

    def test_a_request_to_another_target_finishes_the_begun_one_then_is_refused(self):
        from xsm import handover, teams
        handover._begin(self.lead, self.new, 'goal: the first target', 'x')
        with self.assertRaises(handover.HandoverError) as refused:
            handover.hand_over(self.lead, self.out, 'second', 'x')
        self.assertIn('next', str(refused.exception))
        self.assertIn('xsm handover', str(refused.exception))
        self.assertEqual(handover.load(self.lead)['state'], 'done')
        self.assertTrue(teams.is_member(teams.require('core'), self.new))
        self.assertIn('goal: the first target', handover.notice(self.new))

    def test_a_handover_waits_for_the_lock_and_gives_up_with_a_next_action(self):
        from xsm import handover
        held, release = threading.Event(), threading.Event()

        def holder():
            with handover._handover_lock():
                held.set()
                release.wait(10)
        thread = threading.Thread(target=holder, daemon=True)
        thread.start()
        self.assertTrue(held.wait(5))
        try:
            with self.assertRaises(handover.HandoverError) as refused:
                with handover._handover_lock(timeout=0.3):
                    pass
            self.assertIn('try again', str(refused.exception))
        finally:
            release.set()
            thread.join(5)
        with handover._handover_lock(timeout=1):
            pass


for _inherited in [n for n in dir(test_handover.HandoverTest) if n.startswith('test')]:
    setattr(MovingHandover, _inherited, None)
del _inherited


if __name__ == '__main__':
    unittest.main()
