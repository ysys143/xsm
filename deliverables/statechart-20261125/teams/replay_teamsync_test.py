"""Replay of the XsmHandoverTeamSync.tla paths against xsm's real code, two machines.

Machine X is the HandoverTest state directory (sessions lead = A, next = B, bee).
Machine Y is a second XSM_HOME (paths.HOME is switched for each call), with its own
registry (sessions yee, zed, wyn). Machine keys: X = 'a'*64, Y = 'b'*64 (Y larger).

Mocked: only the network transport. A "send" is the two real calls the network service
makes: team_sync.to_endpoints(team, sender_machine) on the sender's state, then
team_sync.receive(sender_machine, record, receiver_machine) on the receiver's state.
network_directory.public_endpoint is replaced by a function that builds the same
{machine, runtime, home_id, session_id} endpoint from the registry record.
hand_over itself runs with no network service, so its own publish step only returns a note.

Run from the repository root:  python3 <this file> -v Replay.test_x
"""
import contextlib
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.getcwd())
from tests.test_handover import HandoverTest  # noqa: E402

MX, MY = 'a' * 64, 'b' * 64


def endpoint(rec, own):
    return {'machine': own, 'runtime': rec['runtime'], 'session_id': rec['session_id'],
            'home_id': hashlib.sha256(os.path.realpath(rec['home']).encode()).hexdigest(), 'generation': 'g'}


class Replay(HandoverTest):
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
        patcher = mock.patch('xsm.network_directory.public_endpoint', side_effect=endpoint)
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

    def ship(self, sender, receiver):
        from xsm import team_sync, teams
        smach, rmach = (MX, MY) if sender == 'X' else (MY, MX)
        with self.at(sender):
            rec = team_sync.to_endpoints(teams.require('core'), smach)
        with self.at(receiver):
            return team_sync.receive(smach, rec, rmach), rec['generation']

    def view(self, machine):
        from xsm import teams
        with self.at(machine):
            t = teams.require('core')
            return {'gen': t['generation'], 'origin': (t.get('origin') or '-')[:1],
                    'lead': teams.label(t['lead']) if t.get('lead') else None,
                    'members': [teams.label(m) for m in t['members']]}

    def make_shared_team(self):
        """X's team core (lead = A) gets a member on Y and is sent to Y: X created it, Y last received from X."""
        from xsm import teams
        yee = dict(machine=MY, runtime='codex', home_id=hashlib.sha256(os.path.realpath(self.yhome).encode()).hexdigest(),
                   session_id='yee', name='yee')
        teams.add(self.lead, 'core', yee, 'x')
        status, gen = self.ship('X', 'Y')
        self.assertEqual(status, {'status': 'updated'})
        return gen

    def test_path_HandoverStands_in_the_tlc_order(self):
        """TLC path (X created the team, Y got it from X): X hands over; Y changes the team;
        Y's record reaches X first and replaces it; X's record reaches Y and is refused."""
        from xsm import handover, teams
        self.make_shared_team()
        print('\n[1] start   X:', self.view('X'), '\n            Y:', self.view('Y'))
        self._hand_over()                                                     # X hands over (real hand_over)
        x_after = self.view('X')
        print('[2] X handed A\'s seat to B   X:', x_after)
        # X's publish is in flight: build the record now (as the service does at send time)
        from xsm import team_sync
        with self.at('X'):
            x_record = team_sync.to_endpoints(teams.require('core'), MX)
        with self.at('Y'):                                                    # Y changes the team (real teams.add)
            teams.add(self.y('yee'), 'core', self.y('zed'), 'x')
        print('[3] Y added zed   Y:', self.view('Y'))
        status_y_to_x, _ = self.ship('Y', 'X')                                # Y's record reaches X first
        print('[4] X receives Y\'s record ->', status_y_to_x, '  X:', self.view('X'))
        with self.at('Y'):                                                    # X's (older send) record reaches Y
            status_x_to_y = team_sync.receive(MX, x_record, MY)
        print('[5] Y receives X\'s record ->', status_x_to_y, '   Y:', self.view('Y'))
        with self.at('X'):
            team = teams.require('core')
            print('[6] on X now: A is lead?', teams.is_lead(team, self.lead), ' B member?', teams.is_member(team, self.new),
                  ' A member?', teams.is_member(team, self.lead))
            print('    handovers/ record still there, follow(A) ->', handover.follow(self.lead)[0]['session_id'])
            self.assertTrue(teams.is_lead(team, self.lead))                   # rule HandoverStands breaks
            self.assertFalse(teams.is_member(team, self.new))

    def test_path_SameTeamAtRest_both_machines_refuse_each_other(self):
        """TLC path (both machines have received once, so origins are Y at X and X at Y)."""
        from xsm import handover, team_sync, teams
        self.make_shared_team()                                               # Y.origin = X
        with self.at('Y'):
            teams.add(self.y('yee'), 'core', self.y('zed'), 'x')              # Y changes, then X takes it: X.origin = Y
        self.assertEqual(self.ship('Y', 'X')[0], {'status': 'updated'})
        print('\n[1] start   X:', self.view('X'), '\n            Y:', self.view('Y'))
        self._hand_over()                                                     # X hands over
        with self.at('X'):
            x_record = team_sync.to_endpoints(teams.require('core'), MX)
        with self.at('Y'):
            teams.add(self.y('yee'), 'core', self.y('wyn'), 'x')              # Y changes again
            y_record = team_sync.to_endpoints(teams.require('core'), MY)
        print('[2] X handed over   X:', self.view('X'), '\n[3] Y added wyn   Y:', self.view('Y'))
        with self.at('X'):
            sx = team_sync.receive(MY, y_record, MX)
        with self.at('Y'):
            sy = team_sync.receive(MX, x_record, MY)
        print('[4] X receives Y\'s ->', sx, '   [5] Y receives X\'s ->', sy)
        print('    X:', self.view('X'), '\n    Y:', self.view('Y'))
        self.assertEqual((sx, sy), ({'status': 'stale'}, {'status': 'stale'}))
        vx, vy = self.view('X'), self.view('Y')
        self.assertNotEqual(vx['lead'], vy['lead'])                            # rule SameTeamAtRest breaks

    def test_control_handover_alone_reaches_the_other_machine(self):
        from xsm import teams
        self.make_shared_team()
        self._hand_over()
        status, _ = self.ship('X', 'Y')
        print('\n[control] X -> Y:', status, ' Y:', self.view('Y'))
        self.assertEqual(status, {'status': 'updated'})
        with self.at('Y'):
            t = teams.require('core')
            self.assertFalse(any(m.get('session_id') == 'lead' for m in t['members']))
            self.assertEqual(t['lead']['session_id'], 'next')


if __name__ == '__main__':
    unittest.main()
