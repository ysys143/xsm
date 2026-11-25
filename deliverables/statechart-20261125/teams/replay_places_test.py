"""Replay of the XsmHandoverPlaces.tla paths against xsm's real code.

A = self.lead ('lead'), B = self.new ('next'), another session = self.bee ('bee').
Team 'core' (A is lead, bee member) comes from HandoverTest. Team 'ops' is made by bee.
Nothing is mocked. The outside change (teams.remove / teams.add, real calls) is made at the
point the path puts it, by a pass-through wrapper around the real function hand_over is
about to call (board.set_item, teams.teams_of, teams._locked).

Run from the repository root:  python3 <this file> -v Replay.test_x
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.getcwd())
from tests.test_handover import HandoverTest  # noqa: E402


class Replay(HandoverTest):
    def _places(self):
        from xsm import teams
        return {t['name']: {'A is member': teams.is_member(t, self.lead), 'B is member': teams.is_member(t, self.new),
                            'A is lead': teams.is_lead(t, self.lead), 'B is lead': teams.is_lead(t, self.new)}
                for t in teams.all_teams()}

    def _owner_items(self, team):
        from xsm import board
        return {k: [h['body'].split('\n')[0] for h in v] for k, v in board.current(team).items() if k.startswith('owner/')}

    def test_path_PlaceAndItemsMoveTogether_A_leaves_after_its_items_moved(self):
        """lists teams -> A's items in core are moved to B -> someone removes A from core ->
        lists teams again -> recorded."""
        from xsm import board, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        real, fired = board.set_item, []

        def removing(me, team, item, text, *a, **k):
            out = real(me, team, item, text, *a, **k)
            if item == 'handover/lead' and not fired:                          # the last board write of the team
                fired.append(1)
                teams.remove(self.bee, 'core', teams.member_of(self.lead), 'user said so')   # real removal
            return out
        with mock.patch.object(board, 'set_item', side_effect=removing):
            rec = self._hand_over()
        print('\n[remove] record teams:', rec['teams'], ' items:', rec['items'])
        print('[remove] places after:', self._places())
        print('[remove] owner items on core:', self._owner_items('core'))
        t = teams.require('core')
        self.assertFalse(teams.is_member(t, self.new))                          # B never joined core
        self.assertEqual(rec['items']['core'], ['owner/lead'])                  # yet its items are 'owner/next'
        self.assertEqual(rec['teams'], [])                                      # and the letter lists no team

    def test_path_PlaceAndItemsMoveTogether_A_joins_between_the_two_lists(self):
        """lists teams for the boards -> ... boards moved -> someone adds A to ops ->
        lists teams again -> B takes A's place in ops, whose board nobody moved."""
        from xsm import board, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        teams.create(self.bee, 'ops')
        board.set_item(self.bee, 'ops', 'owner/lead', 'ops tasks assigned to lead')    # assigned before A joined
        real, calls = teams.teams_of, []

        def adding(record):
            calls.append(1)
            if len(calls) == 2:                                                 # the call inside _teams
                teams.add(self.bee, 'ops', self.lead, 'user said so')           # real add, no teams.teams_of recursion
            return real(record)
        with mock.patch.object(teams, 'teams_of', side_effect=adding):
            rec = self._hand_over()
        print('\n[add-between] teams_of calls:', len(calls), ' record teams:', rec['teams'], ' items:', rec['items'])
        print('[add-between] places after:', self._places())
        print('[add-between] owner items on ops:', self._owner_items('ops'))
        t = teams.require('ops')
        self.assertTrue(teams.is_member(t, self.new))
        self.assertIn('owner/lead', self._owner_items('ops'))                   # still A's name on ops
        self.assertNotIn('owner/next', self._owner_items('ops'))

    def test_path_NoPlaceLeftBehind_A_joins_after_the_second_list(self):
        """lists -> items moved -> lists again -> someone adds A to ops -> B takes A's place in core -> recorded."""
        from xsm import teams
        teams.create(self.bee, 'ops')
        real, fired = teams._locked, []

        def adding(name):
            if name == 'core' and not fired:                                    # first lock taken inside _teams
                fired.append(1)
                teams.add(self.bee, 'ops', self.lead, 'user said so')
            return real(name)
        with mock.patch.object(teams, '_locked', side_effect=adding):
            rec = self._hand_over()
        print('\n[add-after] record teams:', rec['teams'])
        print('[add-after] places after:', self._places())
        t = teams.require('ops')
        self.assertTrue(teams.is_member(t, self.lead))                          # A still has a team place
        self.assertFalse(teams.is_member(t, self.new))

    def test_control_without_an_outside_change_everything_moves_together(self):
        from xsm import board, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        self._hand_over()
        self.assertTrue(teams.is_member(teams.require('core'), self.new))
        self.assertIn('owner/next', self._owner_items('core'))

    def test_observation_a_board_error_in_a_later_team_leaves_the_earlier_board_moved(self):
        """The abort branch of the model: A leaves team ops after the board list is made and before
        its board step. hand_over raises; core's items were already moved; nothing is rolled back."""
        from xsm import board, handover, teams
        teams.create(self.lead, 'ops')                                          # A in core and ops
        board.set_item(self.lead, 'core', 'owner/lead', 'core plan')
        board.set_item(self.lead, 'ops', 'owner/lead', 'ops plan')
        real, fired = board.set_item, []

        def leaving(me, team, item, text, *a, **k):
            out = real(me, team, item, text, *a, **k)
            if team == 'core' and item == 'handover/lead' and not fired:        # core finished, ops next
                fired.append(1)
                teams.remove(self.lead, 'ops', teams.member_of(self.lead), None)
            return out
        with mock.patch.object(board, 'set_item', side_effect=leaving):
            with self.assertRaises(Exception) as ctx:
                self._hand_over()
        print('\n[abort] raised:', type(ctx.exception).__name__, str(ctx.exception)[:90])
        print('[abort] places:', self._places())
        print('[abort] core owner items:', self._owner_items('core'))
        print('[abort] handovers record written:', handover.load(self.lead) is not None)
        self.assertIsNone(handover.load(self.lead))
        self.assertIn('owner/next', self._owner_items('core'))

    def test_observation_retry_after_the_abort_buries_the_moved_content(self):
        """After the abort above A is put back in ops and the person approves again: core's owner/lead now
        holds the 'handed over' note, which is moved over owner/next."""
        from xsm import board, teams
        teams.create(self.lead, 'ops')
        board.set_item(self.lead, 'core', 'owner/lead', 'core plan')
        board.set_item(self.lead, 'ops', 'owner/lead', 'ops plan')
        real, fired = board.set_item, []

        def leaving(me, team, item, text, *a, **k):
            out = real(me, team, item, text, *a, **k)
            if team == 'core' and item == 'handover/lead' and not fired:
                fired.append(1)
                teams.remove(self.lead, 'ops', teams.member_of(self.lead), None)
            return out
        with mock.patch.object(board, 'set_item', side_effect=leaving):
            with self.assertRaises(Exception):
                self._hand_over()
        print('\n[retry] owner/next after the abort:', board.current('core')['owner/next'][0]['body'])
        # A is back in ops through the lead of ops (A made ops, so bee cannot add; use A's own create path)
        t = teams.require('ops')
        t['members'].append(teams.member_of(self.lead))
        from xsm import paths
        paths.write_json(teams._file('ops'), t)
        self._hand_over()
        print('[retry] owner/next after the retry:', board.current('core')['owner/next'][0]['body'].replace(chr(10), ' | '))
        self.assertNotIn('core plan', board.current('core')['owner/next'][0]['body'].split('(taken over')[0])


if __name__ == '__main__':
    unittest.main()
