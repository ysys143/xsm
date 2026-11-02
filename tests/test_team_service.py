"""CLI and model hosts share team effects; approval stays in the trusted frontend."""
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace
from unittest import mock

from tests.test_xsm import TempState


class SharedTeamServiceTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry
        home = os.path.join(self.tmp, 'codex')
        os.makedirs(home)
        self.me = registry.upsert('codex', home, 'lead', os.getpid(), self.tmp, name='lead')
        self.member = registry.upsert('codex', home, 'member', os.getpid(), self.tmp, name='member')

    def test_cli_and_mcp_reach_the_same_team_service(self):
        from xsm import cli, mcp, team_service, teams
        teams.create(self.me, 'core')
        server = mcp.Server(io.StringIO(), io.StringIO())
        with mock.patch.object(team_service, 'execute', wraps=team_service.execute) as shared, \
                mock.patch.object(cli, '_unsure_caller', return_value=(self.me, None)), \
                mock.patch.object(server, 'session', return_value=self.me):
            out = io.StringIO()
            with redirect_stdout(out):
                result = cli.cmd_team(SimpleNamespace(action='show', name='core', json=True))
            self.assertEqual(result, cli.OK)
            cli_view = json.loads(out.getvalue())
            mcp_view = json.loads(server.call('xsm_team', {'action': 'show', 'team': 'core'}))
            self.assertEqual(cli_view['members'][0]['member'], mcp_view['members'][0]['member'])
            self.assertEqual(shared.call_count, 2)

    def test_denied_approval_has_no_team_effect_or_publish(self):
        from xsm import team_service, teams
        teams.create(self.me, 'core')
        with mock.patch('xsm.team_sync.publish') as publish:
            with self.assertRaises(team_service.DecisionRefused):
                team_service.execute(self.me, {'action': 'add', 'team': 'core', 'member': 'codex:member'},
                    authorize=lambda *args: (_ for _ in ()).throw(team_service.DecisionRefused('denied')))
        self.assertFalse(publish.called)
        self.assertEqual(len(teams.require('core')['members']), 1)

    def test_cli_leave_publishes_the_same_changed_team_as_model_host(self):
        from xsm import cli, mcp, teams
        teams.create(self.me, 'first')
        teams.create(self.me, 'second')
        server = mcp.Server(io.StringIO(), io.StringIO())
        with mock.patch('xsm.team_sync.publish', return_value=[]) as publish, \
                mock.patch.object(cli, '_unsure_caller', return_value=(self.me, None)), \
                mock.patch.object(server, 'session', return_value=self.me), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli.cmd_team(SimpleNamespace(action='leave', name='first', json=False)), cli.OK)
            server.call('xsm_team', {'action': 'leave', 'team': 'second'})
        self.assertEqual(publish.call_count, 2)
        self.assertEqual([call.args[0]['name'] for call in publish.call_args_list], ['first', 'second'])
        self.assertTrue(all(not call.args[0]['members'] for call in publish.call_args_list))
