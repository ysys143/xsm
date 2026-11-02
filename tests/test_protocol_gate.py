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
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('protocol_gate', ROOT / 'scripts/check-protocol.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ProtocolGateTest(unittest.TestCase):
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
