"""Actual cross-process serialization through parent aliases and mutable links."""
import os
from pathlib import Path
import select
import subprocess
import sys

from tests.test_xsm import TempState, REPO


class InstallLockAliasTest(TempState):
    def serialized(self, target, other, change=None):
        from xsm import install
        code = '''import sys
sys.path.insert(0,sys.argv[1])
from xsm import install
print('ready',flush=True)
with install._target_lock(sys.argv[2]):
 print('held',flush=True)
'''
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        env.update(HOME=self.user_home, XSM_HOME=self.tmp, PYTHONDONTWRITEBYTECODE='1')
        process = None
        try:
            with install._target_lock(str(target)):
                if change:
                    change()
                process = subprocess.Popen([sys.executable, '-B', '-c', code, str(REPO), str(other)], env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'child did not initialize')
                self.assertEqual(process.stdout.readline().strip(), b'ready')
                self.assertFalse(select.select([process.stdout], [], [], .5)[0], 'alias bypassed the held lock')
            self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'child did not acquire released lock')
            self.assertEqual(process.stdout.readline().strip(), b'held')
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

    def test_parent_directory_aliases_serialize_the_same_entry(self):
        real = Path(self.tmp, 'real')
        real.mkdir()
        alias = Path(self.user_home, 'alias')
        alias.symlink_to(real, target_is_directory=True)
        self.serialized(real / 'current.json', alias / 'current.json')

    def test_changing_a_leaf_symlink_does_not_change_its_entry_lock(self):
        folder = Path(self.tmp, 'target')
        folder.mkdir()
        first, second = folder / 'first', folder / 'second'
        first.write_text('first')
        second.write_text('second')
        target = folder / 'skill'
        target.symlink_to(first)
        def change():
            target.unlink()
            target.symlink_to(second)
        self.serialized(target, target, change)
