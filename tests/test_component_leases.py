"""Component lifetime evidence and pruning; only fixture PIDs are inspected."""
import contextlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.test_xsm import TempState


class ComponentLeaseTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import install, paths
        self.old = Path(install.runtime_dir('a' * 12))
        self.new = Path(install.runtime_dir('b' * 12))
        self.old.mkdir(parents=True)
        self.new.mkdir()
        paths.write_json(install.runtime_dir(install.CURRENT), {'id': 'b' * 12})
        self.folder = Path(paths.path('component-leases'))
        self.folder.mkdir(mode=0o700)
        self.lease = {'componentLease': 1, 'id': 'c' * 32, 'component': 'opencode-tui',
                      'pid': 123, 'lstart': 'fixture-generation', 'root': str(self.old), 'clock': 'utc-c'}
        self.filename = self.folder / ('c' * 32 + '.json')
        self.save()

    def save(self):
        self.filename.write_text(json.dumps(self.lease))
        self.filename.chmod(0o600)

    def test_live_dead_reused_and_unobservable_processes(self):
        from xsm import component_leases as leases
        with mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', return_value=SimpleNamespace(stdout='fixture-generation')) as ps:
            self.assertEqual(leases.configured_roots(), [str(self.old)])
            self.assertEqual(ps.call_args.args[0], ['ps', '-o', 'lstart=', '-p', '123'])
        with mock.patch.object(leases.identity, 'pid_alive', return_value=False):
            self.assertEqual(leases.configured_roots(), [])
        with mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', return_value=SimpleNamespace(stdout='reused-pid-generation')):
            self.assertEqual(leases.configured_roots(), [])
        with mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', side_effect=OSError('not observable')):
            self.assertEqual(leases.configured_roots(), [str(self.old)])
        self.lease.pop('clock')
        self.save()
        with mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', side_effect=AssertionError('legacy zone is unknown')):
            self.assertEqual(leases.configured_roots(), [str(self.old)])

    def test_pruning_retains_live_ui_then_reclaims_after_process_ends(self):
        from xsm import component_leases as leases, install
        with mock.patch.object(install, '_running_from', return_value=set()), \
                mock.patch.object(install, '_live_session_starts', return_value=[]), \
                mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', return_value=SimpleNamespace(stdout='fixture-generation')):
            self.assertEqual(install.prune_snapshots(), [])
            self.assertTrue(self.old.exists())
        with mock.patch.object(install, '_running_from', return_value=set()), \
                mock.patch.object(install, '_live_session_starts', return_value=[]), \
                mock.patch.object(leases.identity, 'pid_alive', return_value=False):
            self.assertIn(self.old.name, install.prune_snapshots())
        self.assertFalse(self.old.exists())
        self.assertTrue(self.new.exists())

    def test_malformed_or_foreign_leases_preserve_snapshots(self):
        from xsm import component_leases as leases, install
        for change in ({'root': str(Path(self.tmp, 'foreign'))}, {'pid': True}, {'component': 'unknown'}):
            original = dict(self.lease)
            self.lease.update(change)
            self.save()
            with self.assertRaises(ValueError):
                leases.configured_roots()
            self.assertIn(self.old.name, install._configured_for())
            self.lease = original
        self.filename.write_text('{')
        self.assertIn(self.old.name, install._configured_for())

    def test_non_private_files_and_symlinks_are_not_trusted(self):
        from xsm import component_leases as leases
        self.filename.chmod(0o644)
        with self.assertRaises(ValueError):
            leases.configured_roots()
        self.filename.unlink()
        foreign = Path(self.tmp, 'foreign.json')
        foreign.write_text(json.dumps(self.lease))
        self.filename.symlink_to(foreign)
        with self.assertRaises((OSError, ValueError)):
            leases.configured_roots()

    def test_registration_observes_parent_generation_under_the_prune_lock(self):
        from xsm import component_leases as leases, install
        held = []
        @contextlib.contextmanager
        def lock(target):
            self.assertEqual(target, install.runtime_dir(install.CURRENT))
            held.append(True)
            try:
                yield
            finally:
                held.pop()
        def ps(*args, **kwargs):
            self.assertTrue(held)
            self.assertEqual(kwargs['env']['LC_ALL'], 'C')
            self.assertEqual(kwargs['env']['TZ'], 'UTC')
            return SimpleNamespace(stdout='native-parent-generation')
        with mock.patch.object(leases, '__file__', str(self.old / 'xsm/component_leases.py')), \
                mock.patch.object(install, '_target_lock', side_effect=lock), \
                mock.patch.object(leases.os, 'getppid', return_value=456), \
                mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', side_effect=ps):
            lease = leases.hold('opencode-server')
            with self.assertRaisesRegex(ValueError, 'parent changed'):
                leases.hold('opencode-server', expected_parent=789)
        self.assertEqual(lease['pid'], 456)
        self.assertEqual(lease['root'], os.path.realpath(self.old))
        self.assertEqual(lease['component'], 'opencode-server')
        self.assertTrue((self.folder / (lease['id'] + '.json')).is_file())

    def test_registration_refuses_a_snapshot_removed_before_lock_acquisition(self):
        from xsm import component_leases as leases, install
        @contextlib.contextmanager
        def lock(_target):
            self.old.rmdir()
            yield
        before = set(self.folder.iterdir())
        with mock.patch.object(leases, '__file__', str(self.old / 'xsm/component_leases.py')), \
                mock.patch.object(install, '_target_lock', side_effect=lock):
            with self.assertRaisesRegex(ValueError, 'disappeared'):
                leases.hold()
        self.assertEqual(set(self.folder.iterdir()), before)

    def test_hermes_lease_keeps_snapshot_and_only_exact_owner_can_release(self):
        from xsm import component_leases as leases
        self.lease.update(component='hermes-plugin', pid=os.getppid())
        self.save()
        with mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', return_value=SimpleNamespace(stdout='fixture-generation')):
            self.assertIn(str(self.old), leases.configured_roots())
        with self.assertRaisesRegex(ValueError, 'owner differs'):
            leases.release(dict(self.lease, pid=123456789))
        altered = dict(self.lease, lstart='edited')
        with self.assertRaisesRegex(ValueError, 'edited component lease'):
            leases.release(altered)
        self.assertTrue(self.filename.exists())
        self.assertTrue(leases.release(self.lease, expected_parent=os.getppid()))
        self.assertFalse(self.filename.exists())
        self.assertFalse(leases.release(self.lease))

    def test_pruning_retains_loaded_hermes_without_a_session_or_installed_loader(self):
        from xsm import component_leases as leases, install
        self.lease['component'] = 'hermes-plugin'
        self.save()
        with mock.patch.object(install, '_running_from', return_value=set()), \
                mock.patch.object(install, '_live_session_starts', return_value=[]), \
                mock.patch.object(leases.identity, 'pid_alive', return_value=True), \
                mock.patch.object(leases.subprocess, 'run', return_value=SimpleNamespace(stdout='fixture-generation')):
            self.assertEqual(install.prune_snapshots(), [])
            self.assertTrue(self.old.is_dir())
