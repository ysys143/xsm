"""The bounded gate runs independent groups concurrently in separate private homes."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('protocol_gate', ROOT / 'scripts/check-protocol.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ProtocolGateTest(unittest.TestCase):
    def test_main_separates_conformance_without_omitting_any_gate(self):
        calls = []
        def run_phase(commands, env, root, deadline, offset):
            calls.append((commands, deadline, offset))
            return None
        with mock.patch.object(gate, 'run_phase', side_effect=run_phase), \
                mock.patch.object(gate.shutil, 'which', return_value='/fixture/node'), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(), 0)
        commands = [command for phase, _, _ in calls for command in phase]
        modules = [command[4:-1] for command in commands
                   if command[1:4] == ['-B', '-m', 'unittest'] and command[4] != 'discover']
        self.assertCountEqual([name for group in modules for name in group], gate.MODULES + gate.NATIVE_MODULES)
        self.assertIn(['tests.test_protocol_conformance'], modules)
        core = set(gate.MODULES) - set(gate.CONFORMANCE_MODULES)
        core_groups = [set(group) for group in modules if set(group) & core]
        self.assertGreaterEqual(len(core_groups), 2)
        self.assertEqual(set.union(*core_groups), core)
        for index, group in enumerate(core_groups):
            for other in core_groups[index + 1:]:
                self.assertFalse(group & other)
        self.assertEqual(sum(command[1:5] == ['-B', '-m', 'unittest', 'discover'] for command in commands), 1)
        self.assertEqual(sum(command[:2] == ['node', '--test'] for command in commands), 1)
        for script in ('scripts/check-protocol-schema.py', 'scripts/check-independent-v7.py'):
            self.assertEqual(sum(script in command for command in commands), 1)
        for version in (3, 5, 6):
            path = 'examples/independent-participant/local_v%d_fixtures.py' % version
            self.assertEqual(sum(path in command for command in commands), 1)
        self.assertEqual(calls[1][2], len(calls[0][0]))
        self.assertEqual(calls[0][1], calls[1][1])

    def test_validator_dependency_is_scoped_without_forwarding_parent_credentials(self):
        commands, environments = [], []
        def phase(items, env, root, deadline, offset):
            commands.extend(items); environments.append(set(env))
            return None
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY':'fixture-only', 'OPENAI_API_KEY':'fixture-only',
                                          'PYTHONPATH':'/fixture/ambient-libraries'}),                 mock.patch.object(gate, 'run_phase', side_effect=phase),                 mock.patch.object(gate.shutil, 'which', return_value='/fixture/node'),                 redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(validator_path=Path('/fixture/validator')),0)
        for keys in environments:
            self.assertFalse({'ANTHROPIC_API_KEY','OPENAI_API_KEY','PYTHONPATH'} & keys,
                             'ambient credentials or Python paths were forwarded')
        scoped = [item for item in commands if '/fixture/validator' in item]
        self.assertEqual(len(scoped),2)
        self.assertTrue(all(any(script in item for script in ('scripts/check-protocol-schema.py',
            'scripts/check-independent-v7.py')) for item in scoped))

    def test_groups_reach_a_barrier_with_distinct_private_homes(self):
        with tempfile.TemporaryDirectory(prefix='xsm-gate-barrier-') as folder:
            code = '''import json,os,pathlib,sys,time
own,other=map(pathlib.Path,sys.argv[1:])
own.write_text(json.dumps({key:os.environ[key] for key in ('HOME','XSM_HOME','CODEX_HOME','CLAUDE_CONFIG_DIR')}))
deadline=time.monotonic()+3
while not other.exists() and time.monotonic()<deadline: time.sleep(.01)
if not other.exists(): raise SystemExit(9)
print('barrier reached')
'''
            a, b = Path(folder)/'a.json', Path(folder)/'b.json'
            commands = [[sys.executable, '-B', '-c', code, str(a), str(b)],
                        [sys.executable, '-B', '-c', code, str(b), str(a)]]
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertIsNone(gate.run_phase(commands, {'PATH': os.defpath}, folder, time.monotonic()+10, 0))
            first, second = json.loads(a.read_text()), json.loads(b.read_text())
            for key in first:
                self.assertNotEqual(first[key], second[key])
                self.assertTrue(Path(first[key]).is_relative_to(folder))
                self.assertTrue(Path(second[key]).is_relative_to(folder))
            self.assertEqual(out.getvalue().count('barrier reached'), 2)

    def test_deadline_reaps_running_group_and_preserves_partial_output(self):
        with tempfile.TemporaryDirectory(prefix='xsm-gate-deadline-') as folder:
            marker = Path(folder)/'pid'
            code = "import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); print('started',flush=True); time.sleep(60)"
            out = io.StringIO()
            with redirect_stdout(out), self.assertRaises(subprocess.TimeoutExpired):
                gate.run_phase([[sys.executable, '-B', '-c', code, str(marker)]],
                               {'PATH': os.defpath}, folder, time.monotonic()+.5, 0)
            self.assertIn('started', out.getvalue())
            with self.assertRaises(ProcessLookupError):
                os.kill(int(marker.read_text()), 0)

    def test_failed_group_reports_failure_and_preserves_its_output(self):
        with tempfile.TemporaryDirectory(prefix='xsm-gate-failure-') as folder:
            command = [sys.executable, '-B', '-c', "print('failure evidence',flush=True); raise SystemExit(7)"]
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(gate.run_phase([command], {'PATH': os.defpath}, folder, time.monotonic()+10, 0), command)
            self.assertIn('failure evidence', out.getvalue())
