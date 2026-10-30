"""T5: a team's board on xsm doc (ADR-0026 decisions 1-5)."""
import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

from tests import test_xsm


class BoardTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, teams
        home = self.tmp + '/codex'
        os.makedirs(home)
        self.me = registry.upsert('codex', home, 'lead', os.getpid(), self.tmp, name='lead')
        self.b = registry.upsert('codex', home, 'bee', os.getpid(), self.tmp, name='bee')
        self.out = registry.upsert('codex', home, 'out', os.getpid(), self.tmp, name='out')
        teams.create(self.me, 'core')
        teams.add(self.me, 'core', self.b, 'x')
        patcher = mock.patch('xsm.workers.human_terminal', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _text(self):
        from xsm import board
        with open(board.path('core'), encoding='utf-8') as fh:
            return fh.read()

    def test_items_show_their_newest_version(self):
        from xsm import board
        board.set_item(self.me, 'core', 'decision: cache', 'redis')
        board.set_item(self.b, 'core', 'owner/bee', 'bee owns the importer')
        board.set_item(self.b, 'core', 'decision: cache', 'memcached after the benchmark')
        text = board.show(self.me, 'core')
        self.assertIn('## decision: cache\n\nmemcached after the benchmark', text)
        self.assertNotIn('\nredis\n', text)
        self.assertIn('## owner/bee', text)
        self.assertLess(text.index('decision: cache'), text.index('owner/bee'))
        self.assertEqual(len(board.log(self.me, 'core', 'decision: cache')), 2)

    def test_two_versions_at_once_are_both_shown_and_set_settles_them(self):
        from xsm import board, doc
        first = board.set_item(self.me, 'core', 'plan', 'v1')
        p = board.path('core')
        doc.add(p, board.author(self.me), 'mine', ['update'], [first['id']], item='plan')
        doc.add(p, board.author(self.b), 'yours', ['update'], [first['id']], item='plan')
        text = board.show(self.me, 'core')
        self.assertIn('_2 versions at once', text)
        self.assertIn('mine', text)
        self.assertIn('yours', text)
        settled = board.set_item(self.me, 'core', 'plan', 'agreed: mine')
        self.assertEqual(len(settled['parents']), 2)
        self.assertNotIn('versions at once', board.show(self.me, 'core'))

    def test_a_report_tag_does_not_take_over_the_board(self):
        from xsm import board
        board.set_item(self.me, 'core', 'a', 'first')
        board.set_item(self.b, 'core', 'b', 'short', tag='report')
        text = board.show(self.me, 'core')
        self.assertIn('## a', text)
        self.assertIn('## b', text)

    def test_members_only_and_clear_errors(self):
        from xsm import board
        with self.assertRaises(board.BoardError):
            board.show(self.out, 'core')
        with self.assertRaises(board.BoardError):
            board.set_item(self.out, 'core', 'x', 'y')
        with self.assertRaisesRegex(board.BoardError, 'pass --text'):
            board.set_item(self.me, 'core', 'x', '  ')
        with self.assertRaisesRegex(board.BoardError, 'or leave the tag out'):
            board.set_item(self.me, 'core', 'x', 'y', tag='status')
        with self.assertRaisesRegex(board.BoardError, 'short name'):
            board.set_item(self.me, 'core', '#bad\nitem', 'y')

    def test_a_direct_edit_is_taken_as_a_node_not_lost(self):
        from xsm import board
        board.set_item(self.me, 'core', 'decision: cache', 'redis')
        text = self._text().replace('\nredis\n', '\nredis, with a 5 minute TTL\n')
        text += '\n## risk\n\nthe cache can go stale\n'
        with open(board.path('core'), 'w', encoding='utf-8') as fh:
            fh.write(text)
        shown = board.show(self.b, 'core')
        self.assertIn('redis, with a 5 minute TTL', shown)
        self.assertIn('## risk', shown)
        self.assertIn('taken from a direct edit', shown)
        edits = [n for n in board.log(self.me, 'core') if n['author_kind'] == 'file-edit']
        self.assertEqual(sorted(n['item'] for n in edits), ['decision: cache', 'risk'])
        board.show(self.me, 'core')                       # nothing changed since: nothing added
        self.assertEqual(len([n for n in board.log(self.me, 'core') if n['author_kind'] == 'file-edit']), 2)

    def test_board_lives_at_the_team_path(self):
        from xsm import board, teams
        board.set_item(self.me, 'core', 'x', 'y')
        self.assertEqual(os.path.dirname(board.path('core')), teams.folder('core'))
        self.assertTrue(os.path.isdir(board.path('core') + '.nodes'))

    def test_cli_and_mcp(self):
        from xsm import cli, mcp
        with mock.patch.object(cli, '_unsure_caller', return_value=(self.me, None)):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['board', 'set', 'core', 'owner/lead', '--text', 'lead owns the plan']), cli.OK)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(['board', 'show', 'core']), cli.OK)
            self.assertIn('lead owns the plan', out.getvalue())
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(['board', 'log', 'core', '--json']), cli.OK)
            self.assertEqual(json.loads(out.getvalue())['nodes'][0]['item'], 'owner/lead')
        server = mcp.Server(io.StringIO(''), io.StringIO())
        server.ctx = None
        with mock.patch.object(server, 'session', return_value=self.b):
            self.assertIn('set progress', server.call('xsm_board', {'action': 'set', 'team': 'core',
                                                                    'item': 'progress', 'text': 'half done'}))
            self.assertIn('half done', server.call('xsm_board', {'action': 'show', 'team': 'core'}))
        with mock.patch.object(server, 'session', return_value=self.out):
            with self.assertRaises(mcp.channel.ChannelError):
                server.call('xsm_board', {'action': 'show', 'team': 'core'})


class BoardSyncTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, teams
        home = self.tmp + '/codex'
        os.makedirs(home)
        self.me = registry.upsert('codex', home, 'lead', os.getpid(), self.tmp, name='lead')
        self.team = teams.create(self.me, 'core')
        self.remote = 'a' * 64
        self.team['members'].append({'machine': self.remote, 'runtime': 'codex', 'home_id': 'c' * 64,
                                     'session_id': 'r1', 'name': 'boss'})
        from xsm import paths
        paths.write_json(teams._file('core'), self.team)
        patcher = mock.patch('xsm.workers.human_terminal', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _node(self, body='from the other machine', item='plan'):
        from xsm import doc
        node = {'t': '2026-10-30T10:00:00+0900', 'author': 'boss@codex [r1]', 'author_kind': 'agent',
                'tags': ['update'], 'parents': [], 'body': body, 'item': item}
        node['id'] = doc.node_digest(node)
        return {'id': node['id'], 'text': doc._serialize(node)}

    def test_receive_takes_valid_nodes_once_and_refuses_tampered_ones(self):
        from xsm import board, board_sync
        good = self._node()
        bad = dict(self._node('original'), text=self._node('changed')['text'])
        res = board_sync.receive(self.remote, 'core', self.team['id'], [good, bad])
        self.assertEqual(res, {'taken': 1, 'kept': 0, 'refused': 1})
        self.assertEqual(board_sync.receive(self.remote, 'core', self.team['id'], [good])['kept'], 1)
        self.assertIn('from the other machine', board.render('core'))

    def test_receive_refuses_other_teams_and_non_member_machines(self):
        from xsm import board_sync
        with self.assertRaises(ValueError):
            board_sync.receive(self.remote, 'core', 'other-id', [self._node()])
        with self.assertRaises(ValueError):
            board_sync.receive('d' * 64, 'core', self.team['id'], [self._node()])

    def test_set_publishes_to_remote_member_machines(self):
        from xsm import board, network
        calls = []
        with mock.patch.object(network, 'call', side_effect=lambda req, **k: calls.append(req) or
                               {'published': [{'machine': self.remote, 'taken': 1}], 'failed': []}):
            node = board.set_item(self.me, 'core', 'plan', 'from here')
        self.assertEqual(calls[0]['op'], 'board-publish')
        self.assertEqual(calls[0]['machines'], [self.remote])
        self.assertEqual(calls[0]['nodes'][0]['id'], node['id'])
        with mock.patch.object(network, 'call', side_effect=network.NetworkError('service-unavailable-or-response-unknown')):
            node = board.set_item(self.me, 'core', 'plan', 'again')
        self.assertIn('xsm board sync core', node['sync_notes'][0])
