"""State-model fixes, P0 RED tests for the board and team criteria (docs/plan/state-model-fixes/spec.md).

SM-F6  team places and owner/A board items move together while a handover runs  (RED until P1)
SM-F7  a write to owner/A between copy and close is carried; two-head items are named  (RED until P5)
SM-F8  two machines that change the same team at the same generation end with one record  (RED until P6)

Reproductions: deliverables/statechart-20261125/teams/replay_{places,board,teamsync}_test.py.

Mocked: only the network transport (the network service is not running, so publish only returns
a note; a team "send" between machines is the two real calls the service makes, team_sync.to_endpoints
on the sender and team_sync.receive on the receiver). The outside changes (teams.remove, teams.add,
board.set_item by another member) are real calls, injected by pass-through wrappers around the real
function hand_over is about to call, at the points the replays use.

Machine X is the HandoverTest state directory (sessions lead = A, next = B, bee). Machine Y is a second
XSM_HOME (paths.HOME is switched for each call). Machine keys: X = 'a'*64, Y = 'b'*64 (Y larger).
"""
import contextlib
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import test_handover

MX, MY = 'a' * 64, 'b' * 64


class _Base(test_handover.HandoverTest):
    """HandoverTest's fixtures; load_tests below keeps its own tests out of this module's run."""

    def _head_lines(self, team, item):
        from xsm import board
        return [h['body'].split('\n')[0] for h in board.current(team).get(item, [])]


# --- SM-F6: places and items move together ----------------------------------------------------

class PlacesAndItems(_Base):
    def _places(self):
        from xsm import board, teams
        out = {}
        for t in teams.all_teams():
            out[t['name']] = {'B is member': teams.is_member(t, self.new),
                              'owner/next on board': 'owner/next' in board.current(t['name'])}
        return out

    def _assert_move_together(self, where, owned):
        """For every team where A had owner items (`owned`): B holds A's place there exactly when
        A's owner items were moved to owner/next there."""
        for name, p in self._places().items():
            if name not in owned:
                continue
            self.assertEqual(p['B is member'], p['owner/next on board'],
                             '%s: team %s has B as member=%s but owner/next on its board=%s (places %s)'
                             % (where, name, p['B is member'], p['owner/next on board'], self._places()))

    def _assert_a_has_no_place_left(self):
        from xsm import teams
        left = [t['name'] for t in teams.all_teams() if teams.is_member(t, self.lead)]
        self.assertEqual(left, [], 'A is still a member of %s after the handover finished' % left)

    # RED until P1 (SM-F6). Today: A is removed from core after its items were moved; B never joins core
    # (teams are listed twice) but owner/next exists on core's board, and the record lists no team.
    @unittest.expectedFailure
    def test_SM_F6_A_removed_from_a_team_after_its_items_moved(self):
        from xsm import board, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        real, fired = board.set_item, []

        def removing(me, team, item, text, *a, **k):
            out = real(me, team, item, text, *a, **k)
            if item == 'handover/lead' and not fired:                           # the last board write of the team
                fired.append(1)
                teams.remove(self.bee, 'core', teams.member_of(self.lead), 'user said so')   # real removal
            return out
        with mock.patch.object(board, 'set_item', side_effect=removing):
            rec = self._hand_over()
        self.assertTrue(fired, 'the injection point was never reached')
        self.assertFalse(teams.is_member(teams.require('core'), self.new))      # B is not added to a team A left
        self._assert_move_together('removed after items moved', ['core'])
        moved_teams = {t for t, items in rec['items'].items() if items}
        self.assertLessEqual(moved_teams, {t['team'] for t in rec['teams']})    # the result does not report items for a team it lists no place for

    # RED until P1 (SM-F6). Today: A is added to ops between the two team lists; B takes A's place in ops
    # but ops' board was never moved (no owner/next there, A's owner/lead item stays).
    @unittest.expectedFailure
    def test_SM_F6_A_added_to_a_second_team_between_the_two_lists(self):
        from xsm import board, teams
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        teams.create(self.bee, 'ops')
        board.set_item(self.bee, 'ops', 'owner/lead', 'ops tasks assigned to lead')
        real, calls = teams.teams_of, []

        def adding(record):
            calls.append(1)
            if len(calls) == 2:                                                 # the call inside _teams
                teams.add(self.bee, 'ops', self.lead, 'user said so')
            return real(record)
        with mock.patch.object(teams, 'teams_of', side_effect=adding):
            self._hand_over()
        self.assertGreaterEqual(len(calls), 2, 'the injection point was never reached')
        self._assert_move_together('added between the lists', ['core', 'ops'])
        self._assert_a_has_no_place_left()

    # RED until P1 (SM-F6, model rule NoPlaceLeftBehind). Today: A is added to ops after the second list
    # and keeps its place there; B never gets it. The board and the places agree, so only A's leftover place fails.
    @unittest.expectedFailure
    def test_SM_F6_A_added_to_a_second_team_after_the_second_list(self):
        from xsm import teams
        teams.create(self.bee, 'ops')
        real, fired = teams._locked, []

        def adding(name):
            if name == 'core' and not fired:                                    # first lock taken inside _teams
                fired.append(1)
                teams.add(self.bee, 'ops', self.lead, 'user said so')
            return real(name)
        with mock.patch.object(teams, '_locked', side_effect=adding):
            self._hand_over()
        self.assertTrue(fired, 'the injection point was never reached')
        self._assert_a_has_no_place_left()

    # RED until P1 (SM-F6). Today: A leaves ops after core was finished; the board step for ops raises
    # (A is no longer a member), core's items stay moved and no handover record is written: a half-moved state.
    @unittest.expectedFailure
    def test_SM_F6_A_leaves_a_later_team_and_the_handover_does_not_abort(self):
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
            rec = self._hand_over()                                             # must not raise
        self.assertTrue(fired, 'the injection point was never reached')
        self.assertIsNotNone(handover.load(self.lead))
        self.assertTrue(teams.is_member(teams.require('core'), self.new))
        self.assertFalse(teams.is_member(teams.require('ops'), self.new))       # B is not added to the team A left
        self._assert_move_together('A left a later team', ['core', 'ops'])
        self.assertIn('core', [t['team'] for t in rec['teams']])

    def test_SM_F6_control_without_an_outside_change_everything_moves_together(self):
        from xsm import board, teams
        teams.create(self.lead, 'ops')
        board.set_item(self.lead, 'core', 'owner/lead', 'the release plan')
        board.set_item(self.lead, 'ops', 'owner/lead', 'ops plan')
        self._hand_over()
        self.assertTrue(teams.is_member(teams.require('core'), self.new))
        self.assertTrue(teams.is_member(teams.require('ops'), self.new))
        self._assert_move_together('control', ['core', 'ops'])
        self._assert_a_has_no_place_left()


# --- SM-F7: nothing written to owner/A is left behind; two-head items are named -----------------

class OwnerItems(_Base):
    def _closed_with_note_only(self, team='core'):
        from xsm import board
        heads = board.current(team)['owner/lead']
        self.assertEqual(len(heads), 1, 'owner/lead ends with %d heads: %s'
                         % (len(heads), [h['body'].split('\n')[0] for h in heads]))
        self.assertIn('handed over to next', heads[0]['body'])

    # RED until P5 (SM-F7a). Today: a member writes owner/lead after the copy and before A's closing write;
    # owner/next never gets it and owner/lead ends with two heads (the note and the late write).
    @unittest.expectedFailure
    def test_SM_F7a_a_write_between_copy_and_close_reaches_the_successor(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')
        real, done = board.set_item, []

        def racing(me, team, item, text, *a, **k):
            if me['name'] == 'lead' and item == 'owner/lead' and not done:       # A's closing write is next
                done.append(1)
                real(self.bee, team, 'owner/lead', 'bee LATE EDIT')              # a member's real write
            return real(me, team, item, text, *a, **k)
        with mock.patch.object(board, 'set_item', side_effect=racing):
            self._hand_over()
        self.assertTrue(done, 'the injection point was never reached')
        new = board.current('core')['owner/next']
        self.assertTrue(any('bee LATE EDIT' in h['body'] for h in new),
                        'owner/next heads do not include the late write: %s' % [h['body'][:30] for h in new])
        self._closed_with_note_only()

    # RED until P5 (SM-F7a, earlier window). Today: the write lands between A's read and A's list. owner/next
    # carries it, but A never read it, so its closing write leaves owner/lead with two heads.
    @unittest.expectedFailure
    def test_SM_F7a_a_write_between_reading_and_listing_leaves_only_the_note(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')
        board.show(self.bee, 'core')                                            # bee has read node 1
        real_show, real_current = board.show, board.current
        state = {'shown': False, 'done': False}

        def show(*a, **k):
            out = real_show(*a, **k)
            if a[0]['name'] == 'lead':
                state['shown'] = True
            return out

        def current(*a, **k):
            if state['shown'] and not state['done']:
                state['done'] = True
                board.set_item(self.bee, 'core', 'owner/lead', 'bee MID EDIT')   # a member's real write
            return real_current(*a, **k)
        with mock.patch.object(board, 'show', side_effect=show), mock.patch.object(board, 'current', side_effect=current):
            self._hand_over()
        self.assertTrue(state['done'], 'the injection point was never reached')
        new = board.current('core')['owner/next']
        self.assertTrue(any('bee MID EDIT' in h['body'] for h in new))
        self._closed_with_note_only()

    def _two_head_item(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')
        board.set_item(self.bee, 'core', 'owner/lead', 'bee notes')             # bee never read it: a second head
        self.assertEqual(len(board.current('core')['owner/lead']), 2)

    # RED until P5 (SM-F7b). Today: the result has no `skipped` key at all.
    @unittest.expectedFailure
    def test_SM_F7b_a_two_head_item_is_listed_under_skipped_in_the_result(self):
        self._two_head_item()
        rec = self._hand_over()
        self.assertIn('skipped', rec)
        self.assertIn('owner/lead', json.dumps(rec['skipped']))

    # RED until P5 (SM-F7b). Today: the letter says nothing about the skipped item.
    @unittest.expectedFailure
    def test_SM_F7b_a_two_head_item_is_named_in_the_letter(self):
        self._two_head_item()
        rec = self._hand_over()
        self.assertIn('owner/lead', rec['letter'])

    # RED until P5 (SM-F7b). Today: the handover/lead board item says nothing about the skipped item.
    @unittest.expectedFailure
    def test_SM_F7b_a_two_head_item_is_named_in_the_handover_board_item(self):
        from xsm import board
        self._two_head_item()
        self._hand_over()
        self.assertIn('owner/lead', board.current('core')['handover/lead'][0]['body'])

    def test_SM_F7_control_when_nobody_writes_owner_A_ends_with_the_note_only(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')
        self._hand_over()
        self._closed_with_note_only()
        self.assertEqual(board.current('core')['owner/next'][0]['body'].split('\n')[0], 'plan v1')


# --- SM-F8: two machines, one team record -------------------------------------------------------

def _endpoint(rec, own):
    return {'machine': own, 'runtime': rec['runtime'], 'session_id': rec['session_id'],
            'home_id': hashlib.sha256(os.path.realpath(rec['home']).encode()).hexdigest(), 'generation': 'g'}


class TwoMachines(_Base):
    def setUp(self):
        super().setUp()
        from xsm import paths, registry
        self.xroot = self.tmp
        self.yroot = tempfile.mkdtemp(prefix='xsm-test-y-')
        self.addCleanup(shutil.rmtree, self.yroot, ignore_errors=True)
        self.yhome = self.yroot + '/codex'
        os.makedirs(self.yhome)
        with self.at('Y'):
            paths.ensure_home()
            for n in ('yee', 'zed', 'wyn'):
                registry.upsert('codex', self.yhome, n, os.getpid(), self.yroot, name=n)
        patcher = mock.patch('xsm.network_directory.public_endpoint', side_effect=_endpoint)
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextlib.contextmanager
    def at(self, machine):
        from xsm import paths
        old = paths.HOME
        paths.HOME = self.xroot if machine == 'X' else self.yroot
        try:
            yield
        finally:
            paths.HOME = old

    def y(self, name):
        from xsm import registry
        with self.at('Y'):
            return registry.by_session('codex', name)

    @staticmethod
    def _keys(machine):
        return (MX, MY)[machine == 'Y'], (MX, MY)[machine == 'X']

    def record_of(self, machine):
        """The team record as the other machine would read it (to_endpoints on this machine's state)."""
        from xsm import team_sync, teams
        own, _ = self._keys(machine)
        with self.at(machine):
            return team_sync.to_endpoints(teams.require('core'), own)

    def deliver(self, sender, receiver, record=None):
        """The two real calls the network service makes: the sender's record, then receive on the receiver."""
        from xsm import team_sync
        smach, rmach = self._keys(sender)[0], self._keys(receiver)[0]
        record = record or self.record_of(sender)
        with self.at(receiver):
            return team_sync.receive(smach, record, rmach)

    @staticmethod
    def _who(m):
        return (m['machine'], m.get('name') or m.get('session_id')) if m else None

    def shape(self, machine):
        rec = self.record_of(machine)
        return {'generation': rec['generation'], 'lead': self._who(rec['lead']),
                'members': sorted(self._who(m) for m in rec['members'])}

    def make_shared_team(self):
        """X's team core (lead = A) gets a member on Y and is sent to Y: X created it, Y last received from X."""
        from xsm import teams
        yee = dict(machine=MY, runtime='codex', home_id=hashlib.sha256(os.path.realpath(self.yhome).encode()).hexdigest(),
                   session_id='yee', name='yee')
        teams.add(self.lead, 'core', yee, 'x')
        self.assertEqual(self.deliver('X', 'Y'), {'status': 'updated'})

    def settle(self, rounds=5):
        """What the network service does when each machine publishes after taking or making a change:
        alternate the two machines' records until neither changes (only the transport is emulated)."""
        for _ in range(rounds):
            before = (self.shape('X'), self.shape('Y'))
            self.deliver('X', 'Y')
            self.deliver('Y', 'X')
            if (self.shape('X'), self.shape('Y')) == before:
                return

    def assert_one_record_without_A(self, y_member):
        self.settle()
        sx, sy = self.shape('X'), self.shape('Y')
        self.assertEqual(sx, sy, 'the two machines hold different records after exchanging them')
        self.assertNotEqual(sx['lead'], (MX, 'lead'), 'A came back as the lead')
        self.assertNotIn((MX, 'lead'), sx['members'], 'A came back as a member')
        self.assertEqual(sx['lead'], (MX, 'next'), "B did not take A's seat")
        self.assertIn((MX, 'next'), sx['members'])
        self.assertIn((MY, y_member), sx['members'], "Y's change was lost")
        with self.at('X'):
            from xsm import teams
            team = teams.require('core')
            self.assertFalse(teams.is_lead(team, self.lead))
            self.assertFalse(teams.is_member(team, self.lead))
        self.assert_echo_is_quiet()

    def assert_echo_is_quiet(self):
        """Sending an identical record again changes no generation, on either machine."""
        before = (self.shape('X')['generation'], self.shape('Y')['generation'])
        self.deliver('X', 'Y')
        self.deliver('Y', 'X')
        self.deliver('X', 'Y')
        self.assertEqual((self.shape('X')['generation'], self.shape('Y')['generation']), before,
                         'an echo of an identical record changed a generation')

    def _y_adds(self, name):
        from xsm import teams
        with self.at('Y'):
            teams.add(self.y('yee'), 'core', self.y(name), 'x')

    # RED until P6 (SM-F8). Today: Y's record reaches X first and replaces X's (X's local record has no
    # origin, so the tie goes to the incoming one); A is lead again on X, B is not a member, and the handover
    # is silently undone.
    @unittest.expectedFailure
    def test_SM_F8_Y_record_first_then_the_older_handover_record(self):
        self.make_shared_team()
        self._hand_over()                                                       # X hands A's seat to B
        x_record = self.record_of('X')                                          # X's publish in flight
        self._y_adds('zed')                                                     # Y changes at the same generation
        self.deliver('Y', 'X')                                                  # Y's record reaches X first
        self.deliver('X', 'Y', x_record)                                        # X's older record reaches Y
        self.assert_one_record_without_A('zed')

    # RED until P6 (SM-F8). Today: X's record reaches Y first; Y refuses it (tie, same origin) and keeps
    # its own record with A as lead; then Y's record replaces X's. The machines end alike but A is back.
    @unittest.expectedFailure
    def test_SM_F8_handover_record_first_then_Y_record(self):
        self.make_shared_team()
        self._hand_over()
        x_record = self.record_of('X')
        self._y_adds('zed')
        y_record = self.record_of('Y')
        self.deliver('X', 'Y', x_record)
        self.deliver('Y', 'X', y_record)
        self.assert_one_record_without_A('zed')

    # RED until P6 (SM-F8). Today (both machines have an origin): both records are refused as stale, in both
    # directions, and the machines stay different for good: X has B as lead, Y has A.
    @unittest.expectedFailure
    def test_SM_F8_both_machines_refuse_each_other(self):
        self.make_shared_team()
        self._y_adds('zed')                                                     # Y changes, then X takes it: X.origin = Y
        self.assertEqual(self.deliver('Y', 'X'), {'status': 'updated'})
        self._hand_over()                                                       # X hands over
        x_record = self.record_of('X')
        self._y_adds('wyn')                                                     # Y changes again, same generation
        y_record = self.record_of('Y')
        self.deliver('Y', 'X', y_record)                                        # both records cross: each side refuses
        self.deliver('X', 'Y', x_record)
        self.assert_one_record_without_A('wyn')

    def test_SM_F8_control_handover_alone_reaches_the_other_machine(self):
        self.make_shared_team()
        self._hand_over()
        self.assertEqual(self.deliver('X', 'Y'), {'status': 'updated'})
        sx, sy = self.shape('X'), self.shape('Y')
        self.assertEqual(sx, sy)
        self.assertEqual(sy['lead'], (MX, 'next'))
        self.assertNotIn((MX, 'lead'), sy['members'])
        self.assert_echo_is_quiet()


def load_tests(loader, standard_tests, pattern):
    """The classes inherit HandoverTest's fixtures and with them its tests; run only this file's SM tests."""
    suite = unittest.TestSuite()
    for case in (PlacesAndItems, OwnerItems, TwoMachines):
        suite.addTests(t for t in loader.loadTestsFromTestCase(case) if t._testMethodName.startswith('test_SM_'))
    return suite


if __name__ == '__main__':
    unittest.main()
