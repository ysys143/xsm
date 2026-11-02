"""Trusted catalog discovery is inert and isolates providers by installation root."""
import json
import concurrent.futures
from pathlib import Path
import sys
import threading
import types
from unittest import mock
from tests.test_xsm import TempState


class NativeWorkerCatalogTest(TempState):
    def fixture(self, name, marker='one'):
        root=Path(self.tmp,name).resolve();folder=root/'integrations/fixture';folder.mkdir(parents=True)
        (root/'integrations/worker-providers.json').write_text(json.dumps({'fixture':'integrations/fixture/worker_provider.py'}))
        (folder/'helper.py').write_text('MARKER='+repr(marker)+'\n')
        body='from .helper import MARKER\nRUNTIME="fixture"\nCONTROL_PROTOCOL=1\n'
        for method in ('default_home','prepare','environment','argv','result'):
            body+='def '+method+'(*args): return None\n'
        (folder/'worker_provider.py').write_text(body)
        return root

    def test_catalog_listing_and_unknown_selection_execute_no_provider(self):
        from xsm import native_workers
        root=self.fixture('inert');module=root/'integrations/fixture/worker_provider.py';marker=root/'imported'
        module.write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n'+module.read_text())
        with mock.patch.object(native_workers,'ROOT',root):
            self.assertEqual(native_workers.runtimes(),['claude','codex','fixture'])
            with self.assertRaises(native_workers.ProviderError):native_workers.provider('unknown')
            self.assertFalse(marker.exists())
            native_workers.provider('fixture')
            self.assertTrue(marker.exists())

    def test_relative_imports_from_different_installations_cannot_share_a_provider(self):
        from xsm import native_workers
        first=self.fixture('first','first');second=self.fixture('second','second')
        with mock.patch.object(native_workers,'ROOT',first):a=native_workers.provider('fixture')
        with mock.patch.object(native_workers,'ROOT',second):b=native_workers.provider('fixture')
        self.assertEqual((a.MARKER,b.MARKER),('first','second'))
        self.assertIsNot(a,b)

    def test_concurrent_selection_waits_for_one_complete_module_initialization(self):
        from xsm import native_workers
        root=self.fixture('concurrent');module=root/'integrations/fixture/worker_provider.py'
        module.write_text('import _xsm_provider_test_barrier as barrier\n'
            'barrier.entered.set()\nbarrier.release.wait(3)\n'+module.read_text())
        barrier=types.ModuleType('_xsm_provider_test_barrier')
        barrier.entered,barrier.release=threading.Event(),threading.Event()
        with mock.patch.object(native_workers,'ROOT',root),mock.patch.dict(sys.modules,{barrier.__name__:barrier}), \
                concurrent.futures.ThreadPoolExecutor(2) as pool:
            first=pool.submit(native_workers.provider,'fixture')
            self.assertTrue(barrier.entered.wait(2))
            second=pool.submit(native_workers.provider,'fixture')
            try:
                with self.assertRaises(concurrent.futures.TimeoutError):second.result(timeout=.05)
            finally:barrier.release.set()
            self.assertIs(first.result(timeout=2),second.result(timeout=2))

    def test_runtime_cannot_select_an_arbitrary_module_or_override_legacy(self):
        from xsm import native_workers
        root=self.fixture('invalid');filename=root/'integrations/worker-providers.json'
        for catalog in ({'fixture':'../../arbitrary.py'},{'claude':'integrations/claude/worker_provider.py'},
                        {'../fixture':'integrations/fixture/worker_provider.py'}):
            filename.write_text(json.dumps(catalog))
            with self.subTest(catalog=catalog),mock.patch.object(native_workers,'ROOT',root),self.assertRaises(native_workers.ProviderError):
                native_workers.runtimes()

    def test_symlink_and_duplicate_catalog_entries_are_refused(self):
        from xsm import native_workers
        root=self.fixture('symlink');filename=root/'integrations/worker-providers.json'
        original=filename.read_text();target=root/'catalog.json';target.write_text(original);filename.unlink();filename.symlink_to(target)
        with mock.patch.object(native_workers,'ROOT',root),self.assertRaises(native_workers.ProviderError):native_workers.runtimes()
        filename.unlink();filename.write_text('{"fixture":"x","fixture":"y"}')
        with mock.patch.object(native_workers,'ROOT',root),self.assertRaises(native_workers.ProviderError):native_workers.runtimes()
        filename.write_text(original);module=root/'integrations/fixture/worker_provider.py';data=module.read_text();module.unlink();target.write_text(data);module.symlink_to(target)
        with mock.patch.object(native_workers,'ROOT',root),self.assertRaises(native_workers.ProviderError):native_workers.runtimes()
