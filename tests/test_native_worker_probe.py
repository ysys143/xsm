"""Preflight callback admission without a model, native launcher, or messenger."""
import argparse
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class NativeWorkerProbeTest(unittest.TestCase):
    def callback(self, mode, parent='native-parent'):
        path = Path(__file__).resolve().parents[1] / 'scripts/probe-hermes-worker-lifecycle.py'
        tree = ast.parse(path.read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'native_worker')
        calls, checks = [], []
        class ReachedLaunch(Exception):
            pass
        class Unsupported(Exception):
            pass
        def launch(request):
            calls.append(request)
            if any(field in request for field in ('working_directory', 'timeout_seconds', 'blocked_tools')):
                raise Unsupported()
            raise ReachedLaunch()
        def check(name, value):
            if not value:
                raise AssertionError(name)
            checks.append(name)
        options = argparse.Namespace(mode=mode)
        namespace = dict(args=options, options=options, report={}, home=Path('/isolated'),
            nonce='fixture', context=SimpleNamespace(subagent_lifecycle=SimpleNamespace(launch=launch)),
            get_active_subagent_parent=lambda: SimpleNamespace(session_id=parent), check=check,
            SubagentLifecycleError=Unsupported)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        return namespace['native_worker'], calls, checks, ReachedLaunch

    def test_tool_dictionary_does_not_shadow_cli_mode(self):
        for mode in ('complete', 'cancel'):
            with self.subTest(mode=mode):
                callback, calls, checks, reached = self.callback(mode)
                with self.assertRaises(reached):
                    callback({'parent_session_id': 'model-selected-parent'}, session_id='native-parent')
                self.assertEqual(calls[-1]['parent_session_id'], 'native-parent')
                self.assertEqual(len(calls), 1 if mode == 'complete' else 4)
                self.assertEqual(len(checks), 1 if mode == 'complete' else 4)

    def test_wrong_native_parent_is_refused_before_launch(self):
        callback, calls, checks, reached = self.callback('complete', parent='different-parent')
        with self.assertRaisesRegex(AssertionError, 'actual active parent'):
            callback({}, session_id='native-parent')
        self.assertEqual(calls, [])
