"""P10 installer preparation: isolated homes and owned, disposable readers only."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from unittest import mock

from tests.test_install_runtime import _Checkout


class InstallerSafetyTest(_Checkout):
    def home(self, runtime='claude', name='profile'):
        from xsm import install
        home = Path(self.tmp, name)
        home.mkdir(exist_ok=True)
        target = Path(install._settings_file(str(home), runtime))
        original = {'model': 'user-model', 'user_key': 'private-token', 'hooks': {
            'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'user-hook'}]}]}}
        target.write_text(json.dumps(original))
        target.chmod(0o600)
        return str(home), target, original

    def test_claude_and_codex_clean_reinstall_remove_preserve_user_settings_and_mode(self):
        from xsm import install
        for runtime in ('claude', 'codex'):
            with self.subTest(runtime=runtime):
                home, target, original = self.home(runtime, runtime + '-custom')
                result = install.apply(home, runtime)
                self.assertTrue(result['installed'])
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                before = sorted(target.parent.glob(target.name + '.xsm-backup-*'))
                again = install.apply(home, runtime)
                self.assertTrue(again['unchanged'])
                self.assertEqual(sorted(target.parent.glob(target.name + '.xsm-backup-*')), before)
                current = json.loads(target.read_text())
                current['later-user-setting'] = 'keep-this'
                target.write_text(json.dumps(current))
                removed = install.remove(home, runtime)
                self.assertGreater(removed['removed'], 0)
                self.assertEqual(json.loads(target.read_text()), dict(original, **{'later-user-setting': 'keep-this'}))
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_settings_changed_after_plan_are_preserved_and_not_registered_as_installed(self):
        from xsm import config, install
        home, target, _ = self.home()
        plan = install.plan
        newer = {'user-followup': 'do-not-overwrite'}
        def changed(*args, **kwargs):
            result = plan(*args, **kwargs)
            target.write_text(json.dumps(newer))
            return result
        with mock.patch.object(install, 'plan', side_effect=changed):
            result = install.apply(home, 'claude')
        self.assertTrue(result['conflict'])
        self.assertNotIn('installed', result)
        self.assertEqual(json.loads(target.read_text()), newer)
        self.assertNotIn(home, [row['path'] for row in config.homes()])

    def test_settings_changed_during_backup_are_preserved_with_their_mode(self):
        from xsm import install
        home, target, _ = self.home()
        backup = install._backup
        def changed(filename):
            result = backup(filename)
            target.write_text('{"late-user-edit":true}')
            target.chmod(0o640)
            return result
        with mock.patch.object(install, '_backup', side_effect=changed):
            result = install.apply(home, 'claude')
        self.assertTrue(result['conflict'])
        self.assertEqual(target.read_text(), '{"late-user-edit":true}')
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)

    def test_allow_inbound_and_statusline_writers_share_final_compare_before_write(self):
        from xsm import install
        for kind in ('allow', 'inbound', 'statusline'):
            with self.subTest(kind=kind):
                home, target, _ = self.home(name=kind)
                cas = install._cas_bytes
                def late(filename, data, expected, **kwargs):
                    if filename == str(target):
                        target.write_text('{"late-user-edit":true}')
                    return cas(filename, data, expected, **kwargs)
                writer = {'allow': install.allow_form_tools, 'inbound': install.set_inbound,
                          'statusline': install.install_statusline}[kind]
                with mock.patch.object(install, '_cas_bytes', side_effect=late):
                    with self.assertRaises(install.InstallConflictError):
                        writer(home)
                self.assertEqual(target.read_text(), '{"late-user-edit":true}')

    def test_component_manifest_records_owned_values_and_modes_without_public_secrets(self):
        from xsm import install
        home, target, _ = self.home()
        install.apply(home, 'claude')
        install.allow_form_tools(home)
        install.set_inbound(home)
        install.install_statusline(home)
        install.install_skill(home)
        install.install_cli()
        native_config = Path(home, '.claude.json')
        native_config.write_text('{"user-owned":"preserve"}')
        native_config.chmod(0o600)
        with mock.patch.object(install, 'mcp_state', return_value='absent'), \
                mock.patch.object(install.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='', stderr='')):
            self.assertEqual(install.install_mcp(home, 'claude'), 'added')
        report = install.component_manifest(home, 'claude')
        for kind in ('hooks', 'allow', 'inbound', 'statusline', 'skill', 'cli', 'mcp'):
            self.assertIn(kind, report['items'])
        for kind in ('hooks', 'allow', 'inbound', 'statusline'):
            self.assertEqual(report['items'][kind]['recorded_mode'], 0o600)
            self.assertTrue(report['items'][kind]['value_matches'])
        self.assertIsNone(report['items']['mcp']['value_matches'], 'native connectivity was not observed')
        self.assertNotIn('private-token', json.dumps(report))
        target.chmod(0o640)
        changed = install.ownership_manifest(home, 'claude')
        self.assertFalse(changed['items']['hooks']['mode_matches'])

    def test_catalog_preserves_coordinator_decision_and_ack_commands(self):
        from xsm import install
        for name in ('decision-status', 'ack', 'files'):
            self.assertIn(name, install.MESSAGING_COMMANDS)
        for name in ('xsm_decision_status', 'xsm_ack', 'xsm_files'):
            self.assertIn(name, install.MESSAGING_TOOLS)

    def test_uninstall_preserves_later_edits_to_owned_hook_and_statusline(self):
        from xsm import install
        home, target, _ = self.home()
        install.apply(home, 'claude')
        install.install_statusline(home)
        data = json.loads(target.read_text())
        ours = next(group for group in data['hooks']['SessionStart'] if install._is_ours(group))
        ours['hooks'][0]['command'] += ' user-followup'
        data['statusLine']['padding'] = 17
        target.write_text(json.dumps(data))
        self.assertFalse(install.remove_statusline(home))
        result = install.remove(home, 'claude')
        self.assertEqual(result['retained_modified'], 1)
        remaining = json.loads(target.read_text())
        self.assertIn('user-followup', remaining['hooks']['SessionStart'][0]['hooks'][0]['command'])
        self.assertEqual(remaining['statusLine']['padding'], 17)

    def test_skill_copy_uninstall_preserves_added_and_modified_user_files(self):
        from xsm import install
        home, _, _ = self.home()
        folder = Path(home, 'skills', 'xsm')
        tree = install._skill_tree()
        for relative, text in tree.items():
            filename = folder / relative
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text(text + '\n# stale\n')
        self.assertEqual(install.install_skill(home, refresh=True)[0], 'copy-current')
        note = folder / 'user-note.md'
        note.write_text('user notes must survive')
        changed = folder / next(relative for relative in tree if relative != 'SKILL.md')
        changed.write_text('user edited this tracked skill reference')
        self.assertTrue(install.remove_skill(home))
        self.assertEqual(note.read_text(), 'user notes must survive')
        self.assertEqual(changed.read_text(), 'user edited this tracked skill reference')

    def test_cooperative_installers_serialize_and_leave_one_group_per_event(self):
        from xsm import install
        home, target, original = self.home()
        program = ('import json,sys; from xsm import install; '
                   'install.REPO=sys.argv[2]; r=install.apply(sys.argv[1],"claude"); '
                   'print(json.dumps({"installed":r.get("installed"),"conflict":r.get("conflict",False)}))')
        children = [subprocess.Popen([sys.executable, '-c', program, home, self.checkout],
                                    env=dict(os.environ, XSM_HOME=self.tmp),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for _ in range(2)]
        try:
            for child in children:
                output, error = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, error)
                result = json.loads(output)
                self.assertTrue(result['installed'])
                self.assertFalse(result['conflict'])
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=5)
        data = json.loads(target.read_text())
        for event in install.CLAUDE_EVENTS:
            self.assertEqual(sum(install._is_ours(group) for group in data['hooks'][event]), 1)
        self.assertEqual(data['user_key'], original['user_key'])

    def test_live_snapshot_mode_change_is_reported_without_in_place_repair(self):
        from xsm import install
        old = install.make_snapshot()
        script = Path(old['path'], 'bin', 'xsm')
        script.chmod(0o600)
        with mock.patch.object(install, '_running_from', return_value={old['id']}):
            with self.assertRaises(install.InstallConflictError):
                install.make_snapshot()
        self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o600)

    def test_supply_facts_do_not_invent_signature_checksum_or_license(self):
        from xsm import install
        report = install.supply_report(self.checkout)
        self.assertEqual(report['checksum'], 'unknown')
        self.assertEqual(report['signature'], 'unknown')
        self.assertEqual(report['license'], 'unknown')
        self.assertFalse(report['checksum_independent_authentication'])
        Path(self.checkout, 'LICENSE').write_text('MIT License\nfixture license\n')
        report = install.supply_report(self.checkout)
        self.assertEqual(report['license'], 'MIT')
        self.assertEqual(report['license_sha256'], hashlib.sha256(Path(self.checkout, 'LICENSE').read_bytes()).hexdigest())
        self.assertEqual(report['support_matrix'], 'D11-undecided')

    def test_bad_checksum_and_signature_team_leave_existing_runtime_and_settings_unchanged(self):
        from xsm import install
        old = install.make_snapshot()
        home, target, _ = self.home()
        install.apply(home, 'claude')
        original = target.read_bytes()
        metadata = Path(install.runtime_dir(install.CURRENT)).read_bytes()
        with self.assertRaises(install.SupplyError):
            install.make_snapshot(expected_digest='0' * 64)
        with self.assertRaises(install.SupplyError):
            install.make_snapshot(signature={'artifact_digest': install.runtime_digest(self.checkout, install.SNAPSHOT_FILES),
                'verified': True, 'expected_team': 'trusted-team', 'observed_team': 'other-team'})
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(Path(install.runtime_dir(install.CURRENT)).read_bytes(), metadata)
        self.assertEqual(install.runtime_current()['id'], old['id'])

    def test_interrupted_copy_preserves_old_reader_pointer_and_metadata(self):
        from xsm import install
        old = install.make_snapshot()
        original = Path(install.runtime_dir(install.CURRENT)).read_bytes()
        self._edit()
        with mock.patch.object(install.shutil, 'copy2', side_effect=OSError('interrupted copy')):
            with self.assertRaises(OSError):
                install.make_snapshot()
        self.assertEqual(Path(install.runtime_dir(install.CURRENT)).read_bytes(), original)
        self.assertTrue(Path(old['path'], 'xsm', 'install.py').exists())
        self.assertEqual(os.readlink(install.runtime_dir(install.LINK)), old['id'])

    def test_metadata_publish_failure_restores_only_our_pointer_and_retains_old_runtime(self):
        from xsm import install
        old = install.make_snapshot()
        metadata = Path(install.runtime_dir(install.CURRENT)).read_bytes()
        self._edit()
        cas = install._cas_bytes
        def failed(filename, *args, **kwargs):
            if filename == install.runtime_dir(install.CURRENT):
                raise OSError('metadata disk full')
            return cas(filename, *args, **kwargs)
        with mock.patch.object(install, '_cas_bytes', side_effect=failed):
            with self.assertRaises(OSError):
                install.make_snapshot()
        self.assertEqual(Path(install.runtime_dir(install.CURRENT)).read_bytes(), metadata)
        self.assertEqual(os.readlink(install.runtime_dir(install.LINK)), old['id'])
        self.assertTrue(Path(old['path']).is_dir())

    def test_active_corrupt_snapshot_is_preserved_instead_of_deleted_or_replaced(self):
        from xsm import install
        old = install.make_snapshot()
        filename = Path(old['path'], 'xsm', 'paths.py')
        filename.write_text('# old reader still uses this exact file\n')
        with mock.patch.object(install, '_running_from', return_value={old['id']}):
            with self.assertRaises(install.InstallConflictError):
                install.make_snapshot()
        self.assertEqual(filename.read_text(), '# old reader still uses this exact file\n')
        self.assertEqual(os.readlink(install.runtime_dir(install.LINK)), old['id'])

    def test_live_old_reader_survives_upgrade_and_prune_and_can_read_again(self):
        from xsm import install
        old = install.make_snapshot()
        filename = Path(old['path'], 'xsm', '__init__.py')
        expected = filename.read_text()
        program = 'import pathlib,sys; p=pathlib.Path(sys.argv[1]); print("ready",flush=True); sys.stdin.readline(); print(p.read_text())'
        reader = subprocess.Popen([sys.executable, '-c', program, str(filename)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(reader.stdout.readline().strip(), 'ready')
            self._edit()
            new = install.make_snapshot()
            self.assertNotEqual(new['id'], old['id'])
            with mock.patch.object(install, '_live_session_starts', return_value=[]), \
                    mock.patch.object(install, '_configured_for', return_value=set()):
                self.assertNotIn(old['id'], install.prune_snapshots())
            self.assertIsNone(reader.poll())
            output, error = reader.communicate('\n', timeout=10)
            self.assertEqual(reader.returncode, 0, error)
            self.assertEqual(output, expected + '\n')
        finally:
            if reader.poll() is None:
                reader.kill()
                reader.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
