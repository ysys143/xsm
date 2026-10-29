"""P09 policy recovery, corruption and concurrent-writer fixtures.

Only temporary XSM_HOME directories are used. These test config's service API;
MCP/worker/new-pair gate adoption is owned by the coordinator.
"""
import importlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import unittest
from unittest import mock

from tests.test_xsm import TempState


class PolicyRecoveryTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import config, paths
        self.config, self.paths = config, paths
        self.source = Path(paths.path(config.CONFIG))
        self.snapshot = Path(paths.path(config.POLICY_SNAPSHOT))
        self.a, self.b, self.c = [Path(self.tmp, name) for name in ('a', 'b', 'c')]
        for folder in (self.a, self.b, self.c):
            folder.mkdir()

    def write(self, value):
        self.source.write_text(json.dumps(value), encoding='utf-8')

    def seed(self):
        value = {'same_repo_scope': False, 'strict_peers': True, 'deny': ['blocked'],
                 'fail_open': False, 'remote_native': 'hold', 'stale_sender': 'hold',
                 'links': [{'a': str(self.a), 'b': str(self.b)}],
                 'custom': {'keep': ['untouched']}}
        self.write(value)
        loaded = self.config.load()
        self.assertEqual(self.config.policy_health()['health'], 'healthy')
        return loaded

    def test_first_absence_uses_normal_defaults_and_records_absence_not_prior_file(self):
        cfg = self.config
        loaded = cfg.load()
        self.assertIs(type(loaded), dict)
        self.assertEqual(loaded, cfg.DEFAULT_CONFIG)
        health = cfg.policy_health()
        self.assertEqual((health['health'], health['source'], health['error']),
                         ('healthy', 'defaults', None))
        self.assertFalse(health['source_exists'])
        self.assertFalse(health['cached_source_exists'])
        self.assertTrue(health['can_grant'])
        self.assertEqual(cfg.require_valid_policy(), loaded)
        self.assertFalse(self.source.exists(), 'a read must not manufacture config.json')
        importlib.reload(cfg)
        self.assertEqual(cfg.load(), cfg.DEFAULT_CONFIG)
        self.assertEqual(cfg.policy_health()['source'], 'defaults')

    def test_invalid_json_without_prior_valid_file_does_not_open_same_directory(self):
        cfg = self.config
        self.source.write_bytes(b'{"same_repo_scope": false,')
        before = self.source.read_bytes()
        loaded = cfg.load()
        self.assertFalse(loaded['same_repo_scope'])
        self.assertEqual(loaded['scopes'], [])
        self.assertIsNone(cfg.scope_for({'cwd': str(self.a)}, {'cwd': str(self.a)})[0])
        health = cfg.policy_health()
        self.assertEqual(health['source'], 'unavailable')
        self.assertFalse(health['can_grant'])
        self.assertIn('JSONDecodeError', health['error'])
        with self.assertRaises(cfg.PolicyError):
            cfg.require_valid_policy()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(cfg.policy('fail_open'), 'native error policy is independent')
        self.assertFalse(loaded['strict_peers'], 'do not turn on a new native strict policy')

    def test_cached_initial_absence_cannot_validate_a_new_broken_file(self):
        self.config.load()
        self.source.write_text('not JSON')
        self.assertFalse(self.config.load()['same_repo_scope'])
        self.assertFalse(self.config.policy_health()['can_grant'])
        importlib.reload(self.config)
        self.assertFalse(self.config.load()['same_repo_scope'])

    def test_nonobjects_and_duplicate_or_nonfinite_json_never_become_defaults(self):
        for contents in ('null', '[]', 'false', '5', '"config"',
                         '{"same_repo_scope":false,"same_repo_scope":true}',
                         '{"max_workers":NaN}', '{"deny":Infinity}', '\udcff'):
            with self.subTest(contents=repr(contents)):
                self.source.write_bytes(contents.encode('utf-8', 'surrogatepass'))
                self.assertFalse(self.config.load()['same_repo_scope'])
                self.assertFalse(self.config.policy_health()['can_grant'])

    def test_known_permission_field_types_are_validated_recursively(self):
        invalid = [
            {'same_repo_scope': 'false'}, {'strict_peers': 0}, {'deny': 'blocked'},
            {'deny': [None]}, {'scopes': {}}, {'scopes': [True]},
            {'scopes': [{'members': '*'}]}, {'scopes': [{'members': ['*']}]},
            {'scopes': [{'members': [{'root': []}]}]},
            {'scopes': [{'members': [{'runtime': None}]}]},
            {'links': {}}, {'links': [{'a': str(self.a), 'b': []}]},
            {'reaches': [{'ref': 'x', 'root': None}]},
            {'reaches': [{'ref': 'x', 'root': '/', 'pid': '1'}]},
            {'remotes': [{'peer': 'a', 'host': '*'}]},
            {'ignore_frameworks': 'all'}, {'directory_excluded_paths': '*'},
            {'max_workers': True}, {'max_depth': -1}, {'max_workers': '100'},
            {'fail_open': []}, {'remote_native': 'allow-all'},
            {'allow_messaging': {}}, {'human_send_connects': []},
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.write(value)
                self.assertFalse(self.config.load()['same_repo_scope'])
                self.assertIn('invalid permission field', self.config.policy_health()['error'])
                with self.assertRaises(self.config.PolicyError):
                    self.config._raw()

    def test_last_valid_snapshot_preserves_existing_link_deny_and_native_policy(self):
        expected = self.seed()
        for bad in ('{broken', '[]', '{"same_repo_scope":"false"}'):
            with self.subTest(bad=bad):
                self.source.write_text(bad)
                self.assertEqual(self.config.load(), expected)
                health = self.config.policy_health()
                self.assertEqual(health['source'], 'last-valid')
                self.assertFalse(health['can_grant'])
                self.assertIn('policy source invalid', health['error'])
                self.assertIsNotNone(self.config.scope_for({'cwd': str(self.a)}, {'cwd': str(self.b)})[0])
                self.assertIsNone(self.config.scope_for({'cwd': str(self.a)}, {'cwd': str(self.c)})[0])
                self.assertEqual(self.config.blocked(), {'blocked'})
                self.assertFalse(self.config.policy('fail_open'))
                self.assertEqual(self.config.policy('remote_native'), 'hold')
                self.assertEqual(self.source.read_text(), bad)

    def test_snapshot_recovers_in_a_fresh_python_process(self):
        expected = self.seed()
        self.source.write_text('{broken')
        program = ('from xsm import config; import json; '
                   'print(json.dumps({"config":config.load(),"health":config.policy_health()}))')
        result = subprocess.run([sys.executable, '-c', program],
                                env=dict(os.environ, XSM_HOME=self.tmp),
                                capture_output=True, text=True, timeout=10, check=True)
        result = json.loads(result.stdout)
        self.assertEqual(result['config'], expected)
        self.assertEqual(result['health']['source'], 'last-valid')
        self.assertFalse(result['health']['can_grant'])

    def test_file_deletion_is_an_error_after_a_valid_file_even_after_restart(self):
        expected = self.seed()
        self.source.unlink()  # Deliberate deletion fault, confined to this fixture.
        importlib.reload(self.config)
        self.assertEqual(self.config.load(), expected)
        health = self.config.policy_health()
        self.assertFalse(health['source_exists'])
        self.assertTrue(health['cached_source_exists'])
        self.assertIn('deleted', health['error'])
        with self.assertRaises(self.config.PolicyError):
            self.config.set_value('same_repo_scope', True)
        self.assertFalse(self.source.exists())

    def test_deleting_a_first_invalid_file_does_not_turn_it_into_first_setup(self):
        self.source.write_text('[]')
        self.config.load()
        self.source.unlink()
        importlib.reload(self.config)
        self.assertFalse(self.config.load()['same_repo_scope'])
        self.assertIn('deleted', self.config.policy_health()['error'])

    def test_user_repair_and_revocation_replace_old_snapshot(self):
        self.seed()
        self.source.write_text('{broken')
        self.assertEqual(self.config.policy_health()['source'], 'last-valid')
        self.write({'same_repo_scope': False, 'deny': ['new-deny']})
        repaired = self.config.require_valid_policy()
        self.assertEqual(self.config.policy_health()['source'], 'config')
        self.assertNotIn('links', repaired)
        self.source.write_text('{broken-again')
        self.assertEqual(self.config.load(), repaired)
        self.assertIsNone(self.config.scope_for({'cwd': str(self.a)}, {'cwd': str(self.b)})[0])

    def test_empty_valid_object_and_unknown_extensions_remain_compatible(self):
        self.write({})
        self.assertEqual(self.config.load(), self.config.DEFAULT_CONFIG)
        self.write({'unrelated': {'nested': [1, 2]}, 'max_workers': 0, 'max_depth': 0})
        self.assertTrue(self.config.policy_health()['can_grant'])
        loaded = self.config.load()
        loaded['deny'].append('must-not-mutate-defaults')
        self.assertEqual(self.config.DEFAULT_CONFIG['deny'], [])
        self.assertEqual(self.config.load()['unrelated'], {'nested': [1, 2]})

    def test_partially_invalid_object_keeps_well_typed_native_switches_separate(self):
        self.write({'links': 'invalid', 'fail_open': False, 'strict_peers': True,
                    'remote_native': 'hold', 'deny': ['blocked']})
        loaded = self.config.load()
        self.assertFalse(loaded['same_repo_scope'])
        self.assertFalse(self.config.policy('fail_open'))
        self.assertTrue(loaded['strict_peers'])
        self.assertEqual(self.config.policy('remote_native'), 'hold')
        self.assertEqual(self.config.blocked(), {'blocked'})

    def test_explicit_environment_policy_does_not_hide_unhealthy_grant_state(self):
        self.source.write_text('{broken')
        with mock.patch.dict(os.environ, {'XSM_FAIL_OPEN': 'yes', 'XSM_REMOTE_NATIVE': 'pass'}):
            self.assertTrue(self.config.policy('fail_open'))
            self.assertEqual(self.config.policy('remote_native'), 'pass')
            with self.assertRaises(self.config.PolicyError):
                self.config.require_valid_policy()

    def test_snapshot_is_uid_private_and_not_bound_to_another_home(self):
        self.seed()
        info = self.snapshot.stat()
        self.assertEqual(info.st_uid, os.getuid())
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        saved = json.loads(self.snapshot.read_text())
        self.assertTrue(saved['source_exists'])
        self.assertEqual(saved['source_path'], str(self.source))
        other = Path(self.tmp, 'other-state')
        other.mkdir()
        copied = other / self.config.POLICY_SNAPSHOT
        copied.write_bytes(self.snapshot.read_bytes())
        copied.chmod(0o600)
        with mock.patch.object(self.paths, 'HOME', str(other)):
            self.assertFalse(self.config.load()['same_repo_scope'])
            self.assertFalse(self.config.policy_health()['can_grant'])

    def test_invalid_or_unsafe_snapshot_cannot_supply_permissions(self):
        self.seed()
        self.source.write_text('{broken')
        original = self.snapshot.read_text()
        changes = ({'uid': os.getuid() + 1}, {'digest': 'wrong'}, {'version': True},
                   {'config': {'same_repo_scope': 'false'}}, {'source_path': '/other/config.json'})
        for change in changes:
            saved = json.loads(original)
            saved.update(change)
            self.snapshot.write_text(json.dumps(saved))
            self.snapshot.chmod(0o600)
            importlib.reload(self.config)
            self.assertFalse(self.config.load()['same_repo_scope'])
            self.assertFalse(self.config.policy_health()['can_grant'])
        self.snapshot.write_text(original)
        self.snapshot.chmod(0o644)
        importlib.reload(self.config)
        self.assertFalse(self.config.load()['same_repo_scope'])
        self.assertIn('snapshot', self.config.policy_health()['error'])

    def test_snapshot_symlink_is_not_followed_or_overwritten(self):
        victim = Path(self.tmp, 'private-other-file')
        victim.write_text('must survive')
        self.snapshot.symlink_to(victim)
        self.source.write_text('{broken')
        self.assertFalse(self.config.load()['same_repo_scope'])
        self.assertFalse(self.config.policy_health()['can_grant'])
        self.assertEqual(victim.read_text(), 'must survive')
        self.assertTrue(self.snapshot.is_symlink())

    def test_read_and_snapshot_write_failures_preserve_policy_and_report_errors(self):
        expected = self.seed()
        real_source = self.config._source
        with mock.patch.object(self.config, '_source', return_value=(None, 'unreadable', True, 'policy source read failed: PermissionError')):
            self.assertEqual(self.config.load(), expected)
            with self.assertRaises(self.config.PolicyError):
                self.config._raw()
        self.assertEqual(self.config._source(), real_source())
        # A newer valid source whose snapshot write fails is still usable for
        # existing traffic, but cannot authorize a new grant.
        newer = {'same_repo_scope': False, 'deny': ['newer']}
        self.write(newer)
        with mock.patch.object(self.paths, 'write_json', side_effect=OSError('disk full')):
            self.assertEqual(self.config.load()['deny'], ['newer'])
            self.assertIn('snapshot write failed', self.config.policy_health()['error'])
            with self.assertRaises(self.config.PolicyError):
                self.config.require_valid_policy()
            self.source.write_text('{broken')
            self.assertEqual(self.config.load()['deny'], ['newer'], 'memory must retain the latest validated source')

    def test_lock_failure_preserves_existing_policy_without_confirming_new_grants(self):
        expected = self.seed()
        with mock.patch.object(self.config, '_policy_lock', side_effect=PermissionError('read only')):
            self.assertEqual(self.config.load(), expected)
            self.assertIn('policy lock failed', self.config.policy_health()['error'])
            with self.assertRaises(self.config.PolicyError):
                self.config.require_valid_policy()

    def test_external_revocation_snapshot_wins_over_failed_write_memory_even_after_clock_rollback(self):
        self.seed()
        self.write({'same_repo_scope': False, 'deny': ['in-memory']})
        with mock.patch.object(self.paths, 'write_json', side_effect=OSError('disk full')):
            self.assertEqual(self.config.load()['deny'], ['in-memory'])
        self.write({'same_repo_scope': False, 'deny': ['external-revocation']})
        subprocess.run([sys.executable, '-c', 'from xsm import config; config.load()'],
                       env=dict(os.environ, XSM_HOME=self.tmp), check=True, timeout=10)
        # This is a legitimate snapshot at an earlier wall-clock timestamp.
        saved = json.loads(self.snapshot.read_text())
        saved['updated_at_ns'] = 1
        saved['digest'] = self.config._snapshot_digest(saved)
        self.snapshot.write_text(json.dumps(saved))
        self.source.write_text('{broken')
        self.assertEqual(self.config.load()['deny'], ['external-revocation'])

    def test_snapshot_commit_failure_reports_partial_write_instead_of_success(self):
        self.seed()
        replace = os.replace
        def fail_snapshot_commit(source, target):
            if target == str(self.snapshot):
                raise OSError('snapshot rename failed')
            return replace(source, target)
        with mock.patch.object(os, 'replace', side_effect=fail_snapshot_commit):
            with self.assertRaisesRegex(self.config.PolicyError, 'source committed but snapshot commit failed'):
                self.config.set_value('max_workers', 8)
        self.assertEqual(json.loads(self.source.read_text())['max_workers'], 8)
        # A later successful read repairs the recovery evidence explicitly.
        self.assertEqual(self.config.load()['max_workers'], 8)
        self.assertEqual(self.config.policy_health()['health'], 'healthy')

    def test_all_config_writers_refuse_corruption_without_overwriting_source(self):
        self.seed()
        self.source.write_bytes(b'{unclosed policy')
        before = self.source.read_bytes()
        cfg = self.config
        session = {'runtime': 'codex', 'home': self.tmp, 'session_id': 's',
                   'pid': 1, 'lstart': 'fixture', 'state': 'live'}
        writers = [lambda: cfg._raw(), lambda: cfg._data(), lambda: cfg._save({}),
                   lambda: cfg.set_value('same_repo_scope', True),
                   lambda: cfg.add_link(str(self.a), str(self.c), 'fixture'),
                   lambda: cfg.join('project', str(self.a)),
                   lambda: cfg.add_reach('aaaaaa', str(self.c), 'fixture', session=session),
                   lambda: cfg.unblock('blocked'), lambda: cfg.block('another'),
                   lambda: cfg.drop_link(str(self.a), str(self.b)),
                   lambda: cfg.leave('project', str(self.a)),
                   lambda: cfg.drop_reaches([]),
                   lambda: cfg.set_framework_ignored('orca', True),
                   lambda: cfg.add_home(str(self.c), 'codex')]
        for i, writer in enumerate(writers):
            with self.subTest(writer=i), self.assertRaises(cfg.PolicyError):
                writer()
            self.assertEqual(self.source.read_bytes(), before)

    def test_invalid_candidate_is_rejected_before_any_source_change(self):
        self.seed()
        before = self.source.read_bytes()
        with self.assertRaises(self.config.PolicyError):
            self.config._save({'deny': 'invalid'})
        self.assertEqual(self.source.read_bytes(), before)

    def test_stale_raw_and_data_writers_refuse_user_followup_edits(self):
        self.seed()
        for getter in (self.config._raw, self.config._data):
            raw = getter()
            self.write({'same_repo_scope': False, 'deny': ['user-followup']})
            # Make each source revision distinct even when the JSON is equal.
            before = self.source.read_bytes()
            raw['deny'] = []
            with self.assertRaises(self.config.PolicyConflictError):
                self.config._save(raw)
            self.assertEqual(self.source.read_bytes(), before)

    def test_explicit_revision_protects_plain_dict_copies(self):
        raw = dict(self.config._raw())
        revision = self.config.policy_health()['revision']
        self.write({'same_repo_scope': False})
        with self.assertRaises(self.config.PolicyConflictError):
            self.config._save(raw, expected_revision=revision)

    def test_cas_rechecks_after_staging_against_noncooperating_editor(self):
        self.seed()
        raw = self.config._raw()
        raw['deny'] = []
        stage = self.config._stage_policy
        def edit_after_staging(filename, value, mode):
            result = stage(filename, value, mode)
            if filename == str(self.source):
                self.write({'same_repo_scope': False, 'deny': ['late-user-edit']})
            return result
        with mock.patch.object(self.config, '_stage_policy', side_effect=edit_after_staging):
            with self.assertRaises(self.config.PolicyConflictError):
                self.config._save(raw)
        self.assertEqual(json.loads(self.source.read_text())['deny'], ['late-user-edit'])
        self.assertEqual(list(Path(self.tmp).glob('.xsm-policy-*')), [])

    def test_snapshot_staging_failure_leaves_original_source_unchanged(self):
        self.seed()
        before = self.source.read_bytes()
        with mock.patch.object(self.config, '_stage_policy', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.config.set_value('same_repo_scope', True)
        self.assertEqual(self.source.read_bytes(), before)

    def test_normal_writer_preserves_extensions_and_source_mode(self):
        self.seed()
        self.source.chmod(0o600)
        self.assertTrue(self.config.set_value('max_workers', 8))
        self.assertFalse(self.config.set_value('max_workers', 8))
        self.assertEqual(self.config.load()['custom'], {'keep': ['untouched']})
        self.assertEqual(stat.S_IMODE(self.source.stat().st_mode), 0o600)
        self.assertEqual(self.config.policy_health()['health'], 'healthy')
        self.assertEqual(json.loads(self.snapshot.read_text())['config']['max_workers'], 8)

    def test_two_process_writers_share_lock_and_one_stale_revision_is_rejected(self):
        self.seed()
        program = '''
import json, pathlib, sys, time
from xsm import config
root, name = pathlib.Path(sys.argv[1]), sys.argv[2]
raw = config._raw()
raw['writer'] = name
(root / ('ready-' + name)).touch()
deadline = time.monotonic() + 8
while not (root / 'go').exists():
    if time.monotonic() > deadline:
        raise RuntimeError('barrier timeout')
    time.sleep(.01)
try:
    config._save(raw)
    status = 'saved'
except config.PolicyConflictError:
    status = 'conflict'
print(json.dumps({'writer': name, 'status': status}))
'''
        children = [subprocess.Popen([sys.executable, '-c', program, self.tmp, name],
                                     env=dict(os.environ, XSM_HOME=self.tmp),
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for name in ('a', 'b')]
        try:
            deadline = time.monotonic() + 8
            while not all(Path(self.tmp, 'ready-' + name).exists() for name in ('a', 'b')):
                self.assertLess(time.monotonic(), deadline, 'workers did not reach fixture barrier')
                time.sleep(.01)
            Path(self.tmp, 'go').touch()
            results = []
            for child in children:
                output, error = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, error)
                results.append(json.loads(output))
            self.assertEqual(sorted(row['status'] for row in results), ['conflict', 'saved'])
            winner = next(row['writer'] for row in results if row['status'] == 'saved')
            self.assertEqual(self.config.load()['writer'], winner)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
