"""T3: teams (ADR-0025 decisions 9-20, D22)."""
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from tests import test_xsm

MACHINE_A = "a" * 64
MACHINE_B = "b" * 64


class TeamTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters, registry
        self.home = self.tmp + '/codex'
        os.makedirs(self.home)
        other = self.tmp + '/elsewhere'
        os.makedirs(other)
        self.other = other
        self.me = registry.upsert('codex', self.home, 'lead', os.getpid(), self.tmp, name='lead')
        self.b = registry.upsert('codex', self.home, 'bee', os.getpid(), self.tmp, name='bee')
        self.far = registry.upsert('codex', self.home, 'far', os.getpid(), other, name='far')
        self.out = registry.upsert('codex', self.home, 'out', os.getpid(), other, name='out')
        self.bodies, self.wakes = {}, {}

        def queued(home, thread, content, *a, **k):
            self.bodies[thread] = content
            return 'Queued message q for thread %s.' % thread
        patcher = mock.patch.object(adapters, 'to_codex', side_effect=queued)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- the record ---------------------------------------------------------------
    def test_create_names_and_duplicates(self):
        from xsm import teams
        team = teams.create(self.me, 'core')
        self.assertEqual([teams.label(m) for m in team['members']], ['lead@codex'])
        self.assertIsNone(team['lead'])
        with self.assertRaises(teams.TeamError):
            teams.create(self.b, 'core')
        for bad in ('', '-x', 'a/b', 'x' * 64):
            with self.assertRaises(teams.TeamError):
                teams.create(self.me, bad)

    def test_who_may_add(self):
        from xsm import teams
        team = teams.create(self.me, 'core')
        self.assertEqual(teams.add_rule(self.me, team, self.b), 'user')     # not the lead yet
        team = teams.set_lead(self.me, 'core', teams.member_of(self.me), 'yes, lead is fine')
        self.assertEqual(teams.add_rule(self.me, team, self.b), 'lead')     # lead, same project
        self.assertEqual(teams.add_rule(self.me, team, self.far), 'user')   # outside the scope
        with self.assertRaises(teams.TeamError):
            teams.add_rule(self.b, team, self.far)                          # not a member
        team = teams.add(self.me, 'core', self.b, 'lead')
        with self.assertRaises(teams.TeamError):
            teams.add_rule(self.me, team, self.b)                           # already in

    def test_team_permission_opens_only_between_members(self):
        from xsm import config, teams
        self.assertIsNone(config.scope_for(self.me, self.far)[0])
        teams.create(self.me, 'core')
        teams.add(self.me, 'core', self.far, 'user said yes')
        self.assertEqual(config.scope_for(self.me, self.far), ('team:core', 'two sessions in team core'))
        # a session that is not in the team gains nothing
        self.assertNotEqual(config.scope_for(self.b, self.far)[0], 'team:core')
        self.assertIsNone(config.scope_for(self.me, self.out)[0])
        # without teams the scope is what it was
        self.assertIsNone(config.scope_for(self.me, self.far, team_aware=False)[0])
        ended = dict(self.far, state='ended')
        self.assertIsNone(config.scope_for(self.me, ended)[0])

    def test_remove_rules_and_lead_rules(self):
        from xsm import teams
        teams.create(self.me, 'core')
        teams.add(self.me, 'core', self.b, 'x')
        teams.add(self.me, 'core', self.far, 'x')
        with self.assertRaises(teams.TeamError):
            teams.remove(self.b, 'core', teams.member_of(self.far), None)    # not lead, no approval
        team = teams.remove(self.far, 'core', teams.member_of(self.far), None)  # leaves by itself
        self.assertEqual(len(team['members']), 2)
        with self.assertRaises(teams.TeamError):
            teams.set_lead(self.me, 'core', teams.member_of(self.b), '')      # needs the user
        with self.assertRaises(teams.TeamError):
            teams.set_lead(self.me, 'core', teams.member_of(self.far), 'ok')  # not a member any more
        team = teams.set_lead(self.me, 'core', teams.member_of(self.b), 'ok')
        team = teams.remove(self.b, 'core', teams.member_of(self.me), None)   # the lead may
        team = teams.remove(self.b, 'core', teams.member_of(self.b), None)
        self.assertIsNone(team['lead'])                                      # the lead left
        self.assertEqual([e['action'] for e in team['log']][:2], ['create', 'add'])

    def test_name_membership_follows_a_restarted_session(self):
        from xsm import registry, teams
        teams.create(self.me, 'core')
        teams.add(self.me, 'core', self.b, 'x')
        first = teams.address(teams.find_member(teams.require('core'), 'bee'))
        self.assertEqual(first, 'codex:bee')
        registry.upsert('codex', self.home, 'bee-2', os.getpid(), self.tmp, name='bee')
        with mock.patch.object(registry, 'records', return_value=[
                dict(registry.by_session('codex', 'bee-2'), state='live', updated=9e9),
                dict(registry.by_session('codex', 'bee'), state='ended')]):
            self.assertEqual(teams.address(teams.find_member(teams.require('core'), 'bee')), 'codex:bee-2')
        self.assertTrue(teams.is_member(teams.require('core'), registry.by_session('codex', 'bee-2')))

    # -- addressing ------------------------------------------------------------------
    def test_team_address_reaches_every_member_and_mute_skips_the_wake(self):
        from xsm import multisend, teams
        teams.create(self.me, 'core')
        teams.add(self.me, 'core', self.b, 'x')
        teams.add(self.me, 'core', self.far, 'x')
        teams.mute('core', self.far)
        with mock.patch('xsm.team_sync.publish', return_value=[]):
            res = multisend.send_many(['team:core'], 'freeze main', sender=self.me)
        by = {r['label'].split('@')[0]: r['result'] for r in res.rows}
        self.assertEqual(set(by), {'bee', 'far'})
        self.assertEqual(by['bee'].status, 'sent-unconfirmed')
        self.assertEqual(by['far'].status, 'stored')
        self.assertIn('muted this team', by['far'].reason)
        self.assertNotIn('far', self.bodies)                                 # no wake, no queue
        self.assertIn('(also sent to: far@', self.bodies['bee'])

    def test_team_address_refused_for_non_members_and_names_stopped_members(self):
        from xsm import multisend, teams
        teams.create(self.me, 'core')
        teams.add(self.me, 'core', self.b, 'x')
        with self.assertRaises(multisend.MultiError):
            multisend.send_many(['#core'], 'x', sender=self.out)
        with mock.patch.object(teams, 'live_session', return_value=None):
            with self.assertRaises(multisend.MultiError):
                multisend.send_many(['#core'], 'x', sender=self.me)
            out, notes = teams.expand(['#core'], self.me)
        self.assertEqual(out, [])
        self.assertIn('bee@codex in core is not running', notes[0])

    # -- the command -------------------------------------------------------------------
    def test_cli_team_flow(self):
        from xsm import cli, workers
        with mock.patch.object(cli, '_unsure_caller', return_value=(self.me, None)), \
                mock.patch('xsm.registry.me', return_value=self.me), \
                mock.patch('xsm.team_sync.publish', return_value=[]):
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(cli.main(['team', 'create', 'core']), cli.OK)
                with mock.patch.object(workers, 'human_terminal', return_value=False), \
                        mock.patch('xsm.consent.take_or_request', return_value=(None, False, True)):
                    self.assertEqual(cli.main(['team', 'add', 'core', 'codex:far']), cli.REFUSED)
            self.assertIn('your user', err.getvalue())
            with redirect_stdout(io.StringIO()), mock.patch.object(workers, 'human_terminal', return_value=True):
                self.assertEqual(cli.main(['team', 'add', 'core', 'codex:far']), cli.OK)
                self.assertEqual(cli.main(['team', 'lead', 'core', 'lead']), cli.OK)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(['team', 'show', 'core']), cli.OK)
            view = json.loads(out.getvalue())
            self.assertEqual(view['lead'], 'lead@codex')
            self.assertEqual([m['member'] for m in view['members']], ['lead@codex', 'far@codex'])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['team', 'mute', 'core']), cli.OK)
                # the sender muted the team for itself; far still gets a woken DM
                self.assertEqual(cli.main(['send', 'team:core', '--text', 'hi']), cli.UNCONFIRMED)
        from xsm import teams
        self.assertTrue(teams.muted('core', self.me))
        self.assertIn('hi', self.bodies['far'])

    def test_mcp_team_tool(self):
        from xsm import mcp
        server = mcp.Server(io.StringIO(''), io.StringIO())
        server.ctx = None
        with mock.patch.object(server, 'session', return_value=self.me), \
                mock.patch('xsm.team_sync.publish', return_value=[]), \
                mock.patch.object(server, 'allowed', return_value=(True, '')):
            self.assertIn('created team core', server.call('xsm_team', {'action': 'create', 'team': 'core'}))
            self.assertIn('added far@codex', server.call('xsm_team', {'action': 'add', 'team': 'core', 'member': 'codex:far'}))
            listed = json.loads(server.call('xsm_team', {'action': 'list'}))
        self.assertEqual(listed['teams'][0]['members'], ['lead@codex', 'far@codex'])
        with mock.patch.object(server, 'session', return_value=self.me), \
                mock.patch.object(server, 'allowed', return_value=(False, 'your user said no')):
            self.assertIn('the lead is unchanged', server.call('xsm_team', {'action': 'lead', 'team': 'core', 'member': 'far'}))


class TeamSyncTest(test_xsm.TempState):
    """A team that has members on another machine (D22)."""

    def setUp(self):
        super().setUp()
        from xsm import registry
        self.home = self.tmp + '/codex'
        os.makedirs(self.home)
        self.mine = registry.upsert('codex', self.home, 'mine', os.getpid(), self.tmp, name='mine')
        self.remote = {'machine': MACHINE_A, 'runtime': 'codex', 'home_id': 'c' * 64, 'session_id': 'r1'}

    def _incoming(self, generation=1, team_id='t1', members=None):
        import hashlib
        local_ep = {'machine': MACHINE_B, 'runtime': 'codex',
                    'home_id': hashlib.sha256(os.path.realpath(self.home).encode()).hexdigest(),
                    'session_id': 'mine', 'name': 'mine'}
        return {'name': 'core', 'id': team_id, 'generation': generation, 'lead': dict(self.remote, name='boss'),
                'members': members if members is not None else [dict(self.remote, name='boss'), local_ep]}

    def test_receive_turns_own_endpoints_back_into_local_members(self):
        from xsm import config, team_sync, teams
        self.assertEqual(team_sync.receive(MACHINE_A, self._incoming(), MACHINE_B), {'status': 'updated'})
        team = teams.require('core')
        self.assertEqual(team['origin'], MACHINE_A)
        self.assertTrue(teams.is_member(team, self.mine))
        self.assertTrue(teams.is_member(team, self.remote))
        self.assertEqual(config.scope_for(self.mine, dict(self.remote, home=None))[0], 'team:core')

    def test_receive_order_conflict_and_refusals(self):
        from xsm import team_sync
        team_sync.receive(MACHINE_A, self._incoming(2), MACHINE_B)
        self.assertEqual(team_sync.receive(MACHINE_A, self._incoming(1), MACHINE_B), {'status': 'stale'})
        self.assertEqual(team_sync.receive(MACHINE_A, self._incoming(3, team_id='other'), MACHINE_B)['status'],
                         'conflict')
        with self.assertRaises(ValueError):    # the sender machine has no member in it
            team_sync.receive('d' * 64, self._incoming(5), MACHINE_B)
        with self.assertRaises(ValueError):    # this machine has no member in it
            team_sync.receive(MACHINE_A, self._incoming(5, members=[dict(self.remote, name='boss')]), MACHINE_B)
        with self.assertRaises(ValueError):
            team_sync.receive(MACHINE_A, {'name': 'core'}, MACHINE_B)

    def test_to_endpoints_sends_running_members_by_session_and_others_by_name(self):
        from xsm import team_sync, teams
        team = teams.create(self.mine, 'core')
        team['members'].append(dict(self.remote, name='boss'))
        ep = {'machine': MACHINE_B, 'runtime': 'codex', 'home_id': 'e' * 64, 'session_id': 'mine', 'generation': 'g'}
        with mock.patch('xsm.network_directory.public_endpoint', return_value=ep), \
                mock.patch.object(teams, 'live_session', return_value=self.mine):
            out = team_sync.to_endpoints(team, MACHINE_B)
        self.assertEqual(out['members'][0]['session_id'], 'mine')
        self.assertEqual(out['members'][1]['machine'], MACHINE_A)
        with mock.patch.object(teams, 'live_session', return_value=None):
            out = team_sync.to_endpoints(team, MACHINE_B)
        self.assertTrue(out['members'][0]['not_running'])
        self.assertIsNone(out['members'][0]['session_id'])

    def test_network_permission_reads_the_team(self):
        from xsm import network, team_sync
        daemon = network.Daemon.__new__(network.Daemon)
        daemon.transport = mock.Mock(endpoint_id=MACHINE_B)
        daemon.repositories = lambda: mock.Mock(allows=lambda *a: False)
        daemon._grant_file = lambda *a: '/nonexistent-grant'      # no pair grant was ever sent
        sender = dict(self.remote)
        own = {'machine': MACHINE_B, 'runtime': 'codex', 'home_id': 'e' * 64, 'session_id': 'mine', 'generation': 'g'}
        with mock.patch('xsm.network_directory.public_endpoint', return_value=own), \
                mock.patch.object(network, '_read_private', side_effect=FileNotFoundError):
            self.assertFalse(daemon._permission(MACHINE_A, sender, self.mine))
            team_sync.receive(MACHINE_A, self._incoming(), MACHINE_B)
            self.assertTrue(daemon._permission(MACHINE_A, sender, self.mine))
            stranger = dict(sender, session_id='r2')
            self.assertFalse(daemon._permission(MACHINE_A, stranger, self.mine))

    def test_publish_says_when_the_service_is_not_reachable(self):
        from xsm import network, team_sync, teams
        team = teams.create(self.mine, 'core')
        self.assertEqual(team_sync.publish(team), [])            # no remote member, nothing to send
        team['members'].append(dict(self.remote, name='boss'))
        with mock.patch.object(network, 'call', side_effect=network.NetworkError('service-unavailable-or-response-unknown')):
            notes = team_sync.publish(team)
        self.assertIn('not sent to its members on other machines', notes[0])
        with mock.patch.object(network, 'call', return_value={'published': [], 'failed': [{'machine': MACHINE_A, 'code': 'peer-refused'}]}):
            self.assertIn('not updated on machine aaaaaaaa: peer-refused', team_sync.publish(team)[0])


class ConnectPairTest(test_xsm.TempState):
    """T4: a connect makes a team of two; leaving it drops the selection."""

    def setUp(self):
        super().setUp()
        from xsm import registry
        home = self.tmp + '/codex'
        os.makedirs(home)
        other = self.tmp + '/elsewhere'
        os.makedirs(other)
        self.a = registry.upsert('codex', home, 'a-thread', os.getpid(), self.tmp, name='alpha')
        self.b = registry.upsert('codex', home, 'b-thread', os.getpid(), other, name=None)

    def test_pair_team_follows_the_selection_and_leaving_revokes_it(self):
        from xsm import collaboration, config, teams
        record = collaboration.create(self.a, self.b, 'work with b')
        team = teams.make_pair(self.a, self.b, record)
        self.assertEqual(team['name'], 'pair-' + record['id'][:10])
        self.assertEqual([m.get('session_id') for m in team['members']], ['a-thread', 'b-thread'])
        self.assertEqual(teams.make_pair(self.a, self.b, record)['id'], team['id'])   # idempotent
        self.assertEqual(config.scope_for(self.a, self.b)[0], 'team:' + team['name'])
        # a renamed or restarted session with the same name is not the selected conversation
        from xsm import registry
        same_name = registry.upsert('codex', self.a['home'], 'a2', os.getpid(), self.tmp, name='alpha')
        self.assertFalse(teams.is_member(team, same_name))
        teams.remove(self.b, team['name'], teams.member_of(self.b, by_conversation=True), None)
        self.assertIsNone(collaboration.scope_for(self.a, self.b))
        self.assertIsNone(config.scope_for(self.a, self.b)[0])

    def test_selections_made_before_are_listed_as_pairs(self):
        from xsm import collaboration, teams
        record = collaboration.create(self.a, self.b, 'yes')
        self.assertEqual(teams.adopt_pairs(), 1)
        self.assertEqual(teams.adopt_pairs(), 0)
        self.assertIsNotNone(teams.load('pair-' + record['id'][:10]))
        collaboration.drop(self.a, self.b)
        self.assertEqual(teams.adopt_pairs(), 0)

    def test_unnamed_sessions_are_held_by_conversation(self):
        from xsm import teams
        self.assertEqual(teams.member_of(self.b), {'runtime': 'codex', 'home': os.path.realpath(self.b['home']),
                                                  'session_id': 'b-thread', 'name': None})
        self.assertEqual(teams.label(teams.member_of(self.b)), 'codex:b-thread')
