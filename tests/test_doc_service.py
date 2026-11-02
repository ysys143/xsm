"""All hosts contribute immutable document nodes as their actual session."""
import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock
from tests.test_xsm import TempState


class DocServiceTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry
        self.me = registry.upsert('fixture', self.tmp + '/profile', 'author', os.getpid(), self.tmp, name='writer')

    def test_cli_and_model_use_common_document_service(self):
        from xsm import cli, doc_service, mcp, registry
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.me
        target = self.tmp + '/BOARD.md'
        with mock.patch.object(doc_service, 'execute', wraps=doc_service.execute) as common:
            with mock.patch.object(registry, 'me', return_value=self.me), redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['doc', 'add', target, '--text', 'cli report', '--tag', 'report']), 0)
            result = json.loads(server.call('xsm_doc', {'action': 'add', 'doc': target, 'text': 'model report', 'tags': ['report']}))
            self.assertEqual(common.call_count, 2)
            self.assertEqual(result['node']['author_kind'], 'agent')
            self.assertIn('writer', result['node']['author'])

    def test_host_protocol_add_read_render_and_invalid_parent(self):
        from xsm.protocol import Connection
        from xsm import doc
        connection = Connection(); self.addCleanup(connection.close)
        connection.dispatch('initialize', {'protocolVersion': '1'})
        opened = connection.dispatch('session.open', {'runtime': 'doc-fixture', 'profile': 'private',
            'conversation': 'document', 'cwd': self.tmp})
        def call(**arguments):
            return connection.dispatch('operation.call', {'session': opened['session'], 'operation': 'xsm_doc', 'arguments': arguments})
        first = call(action='add', doc='BOARD.md', text='first report', tags=['report'])['node']
        self.assertEqual(first['author_kind'], 'agent')
        second = call(action='add', doc='BOARD.md', text='revised report', parents=[first['id']], tags=['report'])['node']
        self.assertEqual(call(action='show', doc='BOARD.md', node=second['id'])['node'], second)
        self.assertEqual(len(call(action='log', doc='BOARD.md')['nodes']), 2)
        self.assertEqual(call(action='leaves', doc='BOARD.md')['nodes'][0]['id'], second['id'])
        self.assertEqual(call(action='next', doc='BOARD.md')['order'], 'created')
        self.assertIn('revised report', call(action='render', doc='BOARD.md')['text'])
        with self.assertRaises(doc.DocError):
            from xsm import doc_service
            doc_service.execute(self.me, {'action': 'add', 'doc': self.tmp + '/BOARD.md', 'text': 'orphan', 'parents': ['missing']})
        self.assertEqual(len(doc.read(self.tmp + '/BOARD.md')), 2)

    def test_model_cannot_claim_human_endorsement(self):
        from xsm import doc, doc_service, workers
        with mock.patch.object(workers, 'human_terminal', return_value=True), self.assertRaises(doc.DocError):
            doc_service.execute(self.me, {'action': 'add', 'doc': 'BOARD.md', 'text': 'forged yes', 'tags': ['endorsed']})
        self.assertEqual(doc.read(self.tmp + '/BOARD.md'), [])

    def test_guessed_caller_cannot_read_or_write_document_nodes(self):
        from xsm import context, doc, mcp
        from xsm.operation_schema import ToolError
        server = mcp.Server(io.StringIO(), io.StringIO())
        def guessed():
            server.ctx = context.of_record(self.me, context.BASIS_NEIGHBOR)
            return self.me
        server.session = guessed
        for action in ('add', 'render', 'log', 'next', 'leaves', 'show'):
            with self.subTest(action=action), self.assertRaises(ToolError):
                server.call('xsm_doc', {'action': action, 'doc': 'BOARD.md', 'text': 'unbound'})
        self.assertEqual(doc.read(self.tmp + '/BOARD.md'), [])
        self.assertFalse(os.path.exists(self.tmp + '/BOARD.md'))
