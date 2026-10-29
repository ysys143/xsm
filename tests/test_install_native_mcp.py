"""Native MCP registration must not use a mutating Claude query as a CAS read."""
import json
import contextlib
import io
import os
from pathlib import Path
import subprocess
from unittest import mock

from tests import test_xsm


class NativeMcpInstallTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        self.home = Path(self.tmp, 'claude-clean')
        self.home.mkdir()
        self.target = self.home / '.claude.json'
        self.command = [self.tmp + '/snapshot/hooks/xsm-mcp']

    def test_clean_native_get_bootstrap_does_not_collide_with_installer(self):
        from xsm import install
        calls = []
        def native(argv, **kwargs):
            calls.append(argv[1:3])
            if argv[1:3] == ['mcp', 'get']:
                self.target.write_text(json.dumps({'firstStartTime': 'native-initialization'}))
                return subprocess.CompletedProcess(argv, 1, '', 'No MCP server found')
            if argv[1:3] == ['mcp', 'add']:
                data = json.loads(self.target.read_text()) if self.target.exists() else {'firstStartTime': 'native-initialization'}
                data['mcpServers'] = {'xsm': {'type': 'stdio', 'command': self.command[0], 'args': []}}
                self.target.write_text(json.dumps(data))
                return subprocess.CompletedProcess(argv, 0, '', '')
            raise AssertionError('unexpected native operation')
        with mock.patch.object(install, 'mcp_command', return_value=self.command), \
                mock.patch.object(install.subprocess, 'run', side_effect=native):
            self.assertEqual(install.install_mcp(str(self.home), 'claude'), 'added')
        self.assertEqual(calls, [['mcp', 'add']])
        self.assertEqual(json.loads(self.target.read_text())['firstStartTime'], 'native-initialization')

    def test_claude_existing_current_and_stale_inspection_is_readonly_and_exact(self):
        from xsm import install
        original = {'user-preference': {'keep': True}, 'mcpServers': {
                    'xsm': {'command': self.command[0], 'args': []},
                    'other': {'command': '/user-owned-server'}}}
        self.target.write_text(json.dumps(original));before = self.target.read_bytes()
        with mock.patch.object(install, 'mcp_command', return_value=self.command), \
                mock.patch.object(install.subprocess, 'run', side_effect=AssertionError('native query writes metadata')):
            self.assertEqual(install.mcp_state(str(self.home), 'claude'), 'current')
            self.assertEqual(install.install_mcp(str(self.home), 'claude'), 'current')
            self.assertEqual(self.target.read_bytes(), before)
            original['mcpServers']['xsm']['command'] += '-different'
            self.target.write_text(json.dumps(original))
            self.assertEqual(install.mcp_state(str(self.home), 'claude'), 'stale')

    def test_concurrent_user_edit_rejected_even_for_current_state(self):
        from xsm import install
        self.target.write_text('{"mcpServers":{}}')
        changed = '{"mcpServers":{},"user_late_edit":true}'
        def inspected(*args):
            self.target.write_text(changed)
            return 'current'
        with mock.patch.object(install, 'mcp_state', side_effect=inspected), \
                mock.patch.object(install.subprocess, 'run', side_effect=AssertionError('must not write')):
            with self.assertRaises(install.InstallConflictError):
                install.install_mcp(str(self.home), 'claude')
        self.assertEqual(self.target.read_text(), changed)

    def test_invalid_json_and_symlink_preserved_without_native_repair(self):
        from xsm import install
        with mock.patch.object(install.subprocess, 'run', side_effect=AssertionError('must preserve invalid state')):
            for invalid in ('{', '[]', '{"mcpServers":[]}'):
                self.target.write_text(invalid)
                with self.assertRaises(ValueError):
                    install.install_mcp(str(self.home), 'claude')
                self.assertEqual(self.target.read_text(), invalid)
            self.target.unlink()
            foreign = Path(self.tmp, 'user-config.json');foreign.write_text('{"user":"keep"}')
            self.target.symlink_to(foreign)
            with self.assertRaises(install.InstallConflictError):
                install.install_mcp(str(self.home), 'claude')
            self.assertTrue(self.target.is_symlink())
            self.assertEqual(foreign.read_text(), '{"user":"keep"}')

    def test_setup_guard_still_prevents_native_registration(self):
        from xsm import install
        def cancelled():
            raise install.InstallConflictError('setup generation cancelled')
        with mock.patch.object(install.subprocess, 'run') as native:
            with self.assertRaises(install.InstallConflictError):
                with install.setup_write_guard(cancelled):
                    install.install_mcp(str(self.home), 'claude')
            native.assert_not_called()

    def test_remove_mcp_preserves_invalid_or_linked_config_and_raises_explicitly(self):
        from xsm import install
        with mock.patch.object(install.subprocess, 'run', side_effect=AssertionError('must not remove native config')):
            self.target.write_text('{')
            with self.assertRaises(ValueError):
                install.remove_mcp(str(self.home), 'claude')
            self.assertEqual(self.target.read_text(), '{')
            self.target.unlink()
            foreign = Path(self.tmp, 'retained-config.json')
            foreign.write_text('{"mcpServers":{},"user":"preserve"}')
            self.target.symlink_to(foreign)
            with self.assertRaises(install.InstallConflictError):
                install.remove_mcp(str(self.home), 'claude')
            self.assertTrue(self.target.is_symlink())
            self.assertEqual(foreign.read_text(), '{"mcpServers":{},"user":"preserve"}')

    def _public_uninstall_preserves_bad_mcp_and_hooks(self, linked):
        from xsm import cli, install
        applied = install.apply(str(self.home), 'claude')
        self.assertTrue(applied.get('installed'), applied)
        hooks = self.home / 'settings.json'
        original_hooks = hooks.read_bytes()
        hooks_revision = install.file_revision(str(hooks))
        retained = self.home / 'user-owned.json'
        if linked:
            retained.write_text('{"mcpServers":{},"user":"keep"}')
            self.target.symlink_to(retained)
        else:
            self.target.write_text('{')
        original_mcp = self.target.read_bytes()
        mcp_revision = install.file_revision(str(self.target))
        destination = os.readlink(self.target) if linked else None
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(['uninstall', '--claude-home', str(self.home)])
        self.assertEqual(code, 4)
        self.assertNotIn('Traceback', stdout.getvalue() + stderr.getvalue())
        self.assertTrue(stderr.getvalue().strip(), 'public failure needs an explicit diagnostic')
        self.assertEqual(len(stderr.getvalue().strip().splitlines()), 1)
        self.assertNotIn('removed', stdout.getvalue())
        self.assertEqual(self.target.read_bytes(), original_mcp)
        self.assertEqual(hooks.read_bytes(), original_hooks)
        self.assertEqual(install.file_revision(str(hooks)), hooks_revision)
        self.assertEqual(install.file_revision(str(self.target)), mcp_revision)
        if linked:
            self.assertTrue(self.target.is_symlink())
            self.assertEqual(os.readlink(self.target), destination)
            self.assertEqual(retained.read_bytes(), original_mcp)

    def test_public_uninstall_invalid_json_is_exit4_without_traceback_or_partial_removal(self):
        self._public_uninstall_preserves_bad_mcp_and_hooks(False)

    def test_public_uninstall_symlink_is_exit4_without_traceback_or_partial_removal(self):
        self._public_uninstall_preserves_bad_mcp_and_hooks(True)

    def test_native_remove_failure_is_not_reported_as_absent(self):
        from xsm import install
        original = {'mcpServers': {'xsm': {'command': self.command[0], 'args': []}}}
        self.target.write_text(json.dumps(original))
        before = self.target.read_bytes()
        with mock.patch.object(install, 'mcp_command', return_value=self.command), \
                mock.patch.object(install.subprocess, 'run', return_value=
                    subprocess.CompletedProcess(['native', 'mcp', 'remove'], 7, '', 'failed')):
            with self.assertRaises(install.InstallConflictError):
                install.remove_mcp(str(self.home), 'claude')
        self.assertEqual(self.target.read_bytes(), before)

    def test_public_uninstall_normal_path_removes_owned_components(self):
        from xsm import cli, install
        install.apply(str(self.home), 'claude')
        self.target.write_text(json.dumps({'user': 'keep', 'mcpServers': {
            'xsm': {'command': self.command[0], 'args': []},
            'other': {'command': '/user/server'}}}))
        def native(argv, **kwargs):
            self.assertEqual(argv[1:3], ['mcp', 'remove'])
            data = json.loads(self.target.read_text())
            data['mcpServers'].pop('xsm')
            self.target.write_text(json.dumps(data))
            return subprocess.CompletedProcess(argv, 0, '', '')
        with mock.patch.object(install, 'mcp_command', return_value=self.command), \
                mock.patch.object(install.subprocess, 'run', side_effect=native), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(['uninstall', '--claude-home', str(self.home)])
        self.assertEqual(code, 0)
        data = json.loads(self.target.read_text())
        self.assertEqual(data['user'], 'keep')
        self.assertIn('other', data['mcpServers'])
        self.assertNotIn('xsm', data['mcpServers'])
        hooks = json.loads((self.home / 'settings.json').read_text()).get('hooks', {})
        self.assertFalse(any(install._is_ours(group) for groups in hooks.values() for group in groups))

    def test_public_native_remove_nonzero_exit_preserves_hooks_and_returns_exit4(self):
        from xsm import cli, install
        install.apply(str(self.home), 'claude')
        self.target.write_text(json.dumps({'mcpServers': {'xsm': {'command': self.command[0], 'args': []}}}))
        hooks = self.home / 'settings.json'
        before_hooks, before_mcp = hooks.read_bytes(), self.target.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(install, 'mcp_command', return_value=self.command), \
                mock.patch.object(install.subprocess, 'run', return_value=
                    subprocess.CompletedProcess(['native', 'mcp', 'remove'], 7, '', 'failed')), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(['uninstall', '--claude-home', str(self.home)])
        self.assertEqual(code, 4)
        self.assertNotIn('Traceback', stderr.getvalue())
        self.assertNotIn('removed', stdout.getvalue())
        self.assertEqual(len(stderr.getvalue().strip().splitlines()), 1)
        self.assertEqual(hooks.read_bytes(), before_hooks)
        self.assertEqual(self.target.read_bytes(), before_mcp)
