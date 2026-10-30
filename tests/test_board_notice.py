"""T7: a line at the next prompt when a team's board changed (D23)."""
import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

from tests import test_xsm


class BoardNoticeTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, teams
        home = self.tmp + '/codex'
        os.makedirs(home)
        self.lead = registry.upsert('codex', home, 'lead', os.getpid(), self.tmp, name='lead')
        self.bee = registry.upsert('codex', home, 'bee', os.getpid(), self.tmp, name='bee')
        teams.create(self.lead, 'core')
        teams.add(self.lead, 'core', self.bee, 'x')
        patcher = mock.patch('xsm.workers.human_terminal', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _set(self, item, text, team='core', who=None):
        from xsm import board
        board.set_item(who or self.lead, team, item, text)

    def test_a_change_is_told_once_and_counts_what_is_unread(self):
        from xsm import board, board_notice
        self._set('decision: cache', 'redis')
        self._set('owner/api', 'bee')
        line = board_notice.notice(self.bee)
        self.assertEqual(line, "[xsm] board core: 2 items changed (decision: cache, owner/api). "
                               "Read it with `xsm board show core` (xsm_board).")
        self.assertIsNone(board_notice.notice(self.bee))          # not again every turn
        self._set('progress', 'half')
        self.assertIn('3 items changed', board_notice.notice(self.bee))   # still unread: counted
        board.show(self.bee, 'core')
        self.assertIsNone(board_notice.notice(self.bee))
        self._set('progress', 'done')
        self.assertIn('1 item changed (progress)', board_notice.notice(self.bee))

    def test_what_a_member_wrote_itself_is_not_told_back(self):
        from xsm import board_notice
        self._set('decision: cache', 'redis')
        self.assertIsNone(board_notice.notice(self.lead))
        self._set('owner/api', 'lead', who=self.bee)
        self.assertIn('(owner/api)', board_notice.notice(self.lead))

    def test_a_session_in_several_teams_gets_a_line_per_team(self):
        from xsm import board_notice, teams
        teams.create(self.lead, 'docs')
        teams.add(self.lead, 'docs', self.bee, 'x')
        self._set('decision: cache', 'redis')
        self._set('owner/readme', 'bee', team='docs')
        lines = board_notice.notice(self.bee).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith('[xsm] board core: 1 item changed'))
        self.assertTrue(lines[1].startswith('[xsm] board docs: 1 item changed'))

    def test_mute_turns_a_teams_lines_off_for_this_session(self):
        from xsm import board_notice, cli, mcp
        with redirect_stdout(io.StringIO()):
            with mock.patch.object(cli, '_unsure_caller', return_value=(self.bee, None)):
                self.assertEqual(cli.main(['board', 'mute', 'core']), cli.OK)
        self._set('decision: cache', 'redis')
        self.assertIsNone(board_notice.notice(self.bee))
        server = mcp.Server(io.StringIO(''), io.StringIO())
        server.ctx = None
        with mock.patch.object(server, 'session', return_value=self.bee):
            self.assertIn('unmuted', server.call('xsm_board', {'action': 'unmute', 'team': 'core'}))
        self.assertIn('(decision: cache)', board_notice.notice(self.bee))   # what came while muted
        with mock.patch.object(server, 'session', return_value=self.bee):
            server.call('xsm_board', {'action': 'mute', 'team': 'core'})
        self._set('progress', 'half')
        self.assertIsNone(board_notice.notice(self.bee))

    def test_a_decision_is_counted(self):
        from xsm import board, board_notice
        board.record_decision(self.lead, 'core', 'Which cache?', 'redis', via='terminal', item='decision: cache')
        line = board_notice.notice(self.bee)
        self.assertIn('1 item changed (decision: cache); 1 decision recorded', line)
        self.assertIsNone(board_notice.notice(self.lead))         # its own decision

    def test_limits_keep_the_lines_short(self):
        from xsm import board_notice, teams
        for i in range(7):
            teams.create(self.lead, 't%d' % i)
            teams.add(self.lead, 't%d' % i, self.bee, 'x')
            self._set('item %d' % i, 'x', team='t%d' % i)
        lines = board_notice.notice(self.bee).splitlines()
        self.assertEqual(len(lines), board_notice.TEAM_LIMIT + 1)
        self.assertEqual(lines[-1], '[xsm] and 2 more team boards changed (`xsm team list`).')
        # The two left out are told at the next prompt.
        self.assertEqual(len(board_notice.notice(self.bee).splitlines()), 2)
        for i in range(5):
            self._set('item %d' % i, 'x')
        self.assertIn('(item 0, item 1, item 2, +2 more)', board_notice.notice(self.bee))
        for i in range(3):
            self._set('a long item name number %d ' % i + 'x' * 50, 'x')     # 76 characters
        line = board_notice.notice(self.bee)
        self.assertEqual(len(line) - len('[xsm] '), board_notice.LINE_LIMIT)
        self.assertTrue(line.endswith('…'))

    def test_unread_nodes_past_the_parse_limit_are_counted_not_read(self):
        from xsm import board_notice
        for i in range(4):
            self._set('item %d' % i, 'x')
        with mock.patch.object(board_notice, 'PARSE_LIMIT', 2):
            line = board_notice.notice(self.bee)
        self.assertIn('2+ items changed', line)

    def test_the_prompt_hook_carries_the_line(self):
        from xsm import receive
        self._set('decision: cache', 'redis')
        out = receive._with_bounces('codex', self.bee, None)
        self.assertIn('[xsm] board core: 1 item changed', out['hookSpecificOutput']['additionalContext'])
        self.assertIsNone(receive._with_bounces('codex', self.bee, None))

    def test_a_broken_board_state_does_not_cost_the_prompt(self):
        from xsm import board_notice, receive
        self._set('decision: cache', 'redis')
        with mock.patch.object(board_notice, 'notice', side_effect=OSError('disk')):
            self.assertIsNone(receive._with_bounces('codex', self.bee, None))
