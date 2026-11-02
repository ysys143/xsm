"""Shared board orchestration must not turn an unrelated listing into a board read."""
import io
import json
import os
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from tests.test_xsm import TempState


class SharedBoardServiceTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, teams
        home = os.path.join(self.tmp, 'codex')
        os.makedirs(home)
        self.me = registry.upsert('codex', home, 'one', os.getpid(), self.tmp, name='one')
        self.other = registry.upsert('codex', home, 'two', os.getpid(), self.tmp, name='two')
        teams.create(self.me, 'core')
        teams.add(self.me, 'core', self.other, 'fixture user approved')

    def prepare_unread_version(self):
        from xsm import board
        board.set_item(self.me, 'core', 'plan', 'original-v1')
        board.show(self.other, 'core')
        board.set_item(self.other, 'core', 'plan', 'unseen-v2')

    def assert_unread_survives(self):
        from xsm import board
        board.set_item(self.me, 'core', 'plan', 'my-v3')
        text = board.show(self.me, 'core')
        self.assertIn('unseen-v2', text)
        self.assertIn('my-v3', text)

    def test_cli_decisions_does_not_mark_unshown_board_versions_read(self):
        from xsm import cli
        self.prepare_unread_version()
        with mock.patch.object(cli, '_unsure_caller', return_value=(self.me, None)), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_board(SimpleNamespace(action='decisions', team='core', json=True)), cli.OK)
        self.assert_unread_survives()

    def test_model_decisions_does_not_mark_unshown_board_versions_read(self):
        from xsm import mcp
        self.prepare_unread_version()
        server = mcp.Server(io.StringIO(), io.StringIO())
        with mock.patch.object(server, 'session', return_value=self.me):
            result = json.loads(server.call('xsm_board', {'action': 'decisions', 'team': 'core'}))
        self.assertEqual(result, {'decisions': [], 'inbox_pending': 0})
        self.assert_unread_survives()

    def test_cli_and_model_sync_share_membership_check_and_sync_effect(self):
        from xsm import cli, mcp, board_service
        server = mcp.Server(io.StringIO(), io.StringIO())
        with mock.patch.object(board_service, 'execute', wraps=board_service.execute) as shared, \
                mock.patch('xsm.board_sync.sync', return_value=['fixture sync note']) as sync, \
                mock.patch.object(cli, '_unsure_caller', return_value=(self.me, None)), \
                mock.patch.object(server, 'session', return_value=self.me), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_board(SimpleNamespace(action='sync', team='core')), cli.OK)
            self.assertEqual(server.call('xsm_board', {'action': 'sync', 'team': 'core'}), 'fixture sync note')
        self.assertEqual(shared.call_count, 2)
        self.assertEqual([call.args[0]['name'] for call in sync.call_args_list], ['core', 'core'])

    def test_new_actions_refuse_a_nonmember_before_read_or_publish(self):
        from xsm import board, board_service, registry
        outsider = registry.upsert('codex', self.me['home'], 'outside', os.getpid(), self.tmp, name='outside')
        with mock.patch('xsm.board_sync.sync') as sync, mock.patch.object(board, 'decisions') as decisions:
            for action in ('decisions', 'sync'):
                with self.assertRaises(board.BoardError):
                    board_service.execute(outsider, {'action': action, 'team': 'core'})
        self.assertFalse(sync.called)
        self.assertFalse(decisions.called)
