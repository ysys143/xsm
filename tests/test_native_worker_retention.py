"""An idle logical service still needs its native frontend snapshot after upgrades."""
import os
from pathlib import Path
from unittest import mock
from tests.test_xsm import TempState


class NativeWorkerRetentionTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import install, paths, registry, workers
        self.old=Path(install.runtime_dir('a'*12));self.new=Path(install.runtime_dir('b'*12))
        self.old.mkdir(parents=True);self.new.mkdir()
        paths.write_json(install.runtime_dir(install.CURRENT),{'id':self.new.name})
        owner=registry.upsert('codex',self.tmp+'/owner','owner',os.getpid(),self.tmp)
        self.worker={'id':'fixture-owned','name':'retained-native','mode':'owned','owned':True,
            'runtime':'hermes','home':self.tmp+'/profile','cwd':self.tmp,'owner':owner,'owned_sessions':[],
            'native_provider':{'control_protocol':1,'runtime_root':str(self.old),
                'frontend':str(self.old/'integrations/hermes/worker_frontend.py')}}
        workers.save(self.worker)

    def test_idle_service_retains_frontend_until_service_is_removed(self):
        from xsm import component_leases,host_install,install,workers
        with mock.patch.object(install,'_running_from',return_value=set()), \
                mock.patch.object(install,'_live_session_starts',return_value=[]), \
                mock.patch.object(component_leases,'configured_roots',return_value=[]), \
                mock.patch.object(host_install,'configured_roots',return_value=[]):
            self.assertEqual(install.prune_snapshots(),[])
            self.assertTrue(self.old.exists())
            workers.stop('retained-native')
            self.assertIn(self.old.name,install.prune_snapshots())
        self.assertFalse(self.old.exists())
        self.assertTrue(self.new.exists())

    def test_uncertain_frontend_reference_preserves_all_snapshots(self):
        from xsm import install,native_workers,workers
        for descriptor in ({'control_protocol':1},{'frontend':'relative.py'},
                           {'frontend':str(self.old/'integrations/hermes/worker_frontend.py'),'runtime_root':'/different'}):
            self.worker['native_provider']=descriptor;workers.save(self.worker)
            with self.subTest(descriptor=descriptor),self.assertRaises(native_workers.ProviderError):
                native_workers.configured_roots()
            self.assertIn(self.old.name,install._configured_for())

    def test_corrupt_or_symlink_worker_pointer_does_not_erase_dependency_evidence(self):
        from xsm import install,native_workers,workers
        pointer=Path(workers._record_path(self.worker['name']))
        original=pointer.read_text();pointer.write_text('not JSON')
        with self.assertRaises(native_workers.ProviderError):native_workers.configured_roots()
        self.assertIn(self.old.name,install._configured_for())
        target=Path(self.tmp,'pointer-copy.json');target.write_text(original)
        pointer.unlink();pointer.symlink_to(target)
        with self.assertRaises(native_workers.ProviderError):native_workers.configured_roots()
        self.assertIn(self.old.name,install._configured_for())
