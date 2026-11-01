"""Select only explicitly pinned native probe platforms; never silently emulate x64."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('opencode_platform_probe', ROOT / 'scripts/probe-opencode-protocol.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class NativeProbePlatformTest(unittest.TestCase):
    def test_pinned_platforms_select_matching_binary(self):
        for system, machine, package in (
            ('darwin', 'arm64', 'opencode-darwin-arm64'),
            ('darwin', 'x86_64', 'opencode-darwin-x64'),
            ('linux', 'aarch64', 'opencode-linux-arm64'),
            ('linux', 'arm64', 'opencode-linux-arm64'),
            ('linux', 'x86_64', 'opencode-linux-x64'),
            ('linux', 'amd64', 'opencode-linux-x64')):
            self.assertEqual(probe.native_binary('/isolated', system, machine),
                             Path('/isolated/node_modules', package, 'bin/opencode'))

    def test_unknown_platform_refuses_instead_of_falling_back(self):
        for system, machine in (('linux', 'riscv64'), ('win32', 'arm64'), ('darwin', 'unknown')):
            with self.assertRaisesRegex(ValueError, 'not pinned'):
                probe.native_binary('/isolated', system, machine)
