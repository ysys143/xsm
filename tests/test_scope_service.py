"""Membership frontends share mutations and keep approval bound to a frozen root."""
import contextlib
import io
import os
import subprocess
from unittest import mock
from tests.test_xsm import TempState


class ScopeServiceTest(TempState):
    def setUp(self):
        super().setUp()
        self.folder = os.path.realpath(os.path.join(self.tmp, 'workspace'))
        os.makedirs(self.folder)

    def change_root(self):
        subprocess.run(['git', 'init', '-q', self.tmp], check=True, capture_output=True)

    def test_join_and_leave_use_the_same_frozen_root(self):
        from xsm import config, scope_service
        joined = scope_service.apply_membership(scope_service.prepare_membership('demo', self.folder))
        self.assertTrue(joined['added'])
        again = scope_service.apply_membership(scope_service.prepare_membership('demo', self.folder))
        self.assertFalse(again['added'])
        left = scope_service.apply_membership(scope_service.prepare_membership('demo', self.folder, leaving=True))
        self.assertTrue(left['changed'])
        self.assertFalse(any(s.get('members') for s in config.projects()))

    def test_changed_root_refuses_join_before_any_policy_write(self):
        from xsm import config, scope_service
        plan = scope_service.prepare_membership('demo', self.folder)
        self.change_root()
        with self.assertRaisesRegex(ValueError, 'root changed'):
            scope_service.apply_membership(plan)
        self.assertEqual(config.projects(), [])

    def test_changed_root_refuses_leave_and_preserves_membership(self):
        from xsm import config, scope_service
        config.join('demo', self.folder)
        plan = scope_service.prepare_membership('demo', self.folder, leaving=True)
        self.change_root()
        with self.assertRaisesRegex(ValueError, 'root changed'):
            scope_service.apply_membership(plan)
        self.assertEqual(config.projects()[0]['members'][0]['root'], self.folder)

    def test_cli_and_model_call_the_common_service(self):
        from xsm import cli, config, mcp, scope_service
        server = mcp.Server(io.StringIO(), io.StringIO())
        me = {'cwd': self.folder, 'runtime': 'codex', 'ref': 'test', 'name': 'test', 'alias': 'test'}
        with mock.patch.object(scope_service, 'apply_membership', wraps=scope_service.apply_membership) as common:
            with mock.patch.object(cli, '_unsure_caller', return_value=(me, None)), \
                    mock.patch.object(cli, '_here', return_value=self.folder), \
                    mock.patch.object(cli, '_person_or_refuse', return_value=None), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['join', 'demo']), 0)
                self.assertEqual(cli.main(['leave', 'demo']), 0)
            with mock.patch.object(server, 'typed_permission', return_value=True):
                self.assertIn('joined demo', server.join(me, {'project': 'demo'}))
                self.assertIn('left demo', server.join(me, {'project': 'demo', 'leave': True}))
            self.assertEqual(common.call_count, 4)
        self.assertFalse(any(s.get('members') for s in config.projects()))

    def test_model_approval_cannot_apply_to_a_changed_root(self):
        from xsm import config, mcp, operations
        server = mcp.Server(io.StringIO(), io.StringIO())
        def approve(*args):
            self.change_root()
            return True, ''
        with mock.patch.object(server, 'typed_permission', return_value=False), \
                mock.patch.object(server, 'allowed', side_effect=approve), \
                self.assertRaisesRegex(operations.ToolError, 'root changed'):
            server.join({'cwd': self.folder}, {'project': 'demo'})
        self.assertEqual(config.projects(), [])
