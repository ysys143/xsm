"""Hermes coordinator interleavings with a controlled SDK, without a model."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


spec = importlib.util.spec_from_file_location(
    "xsm_hermes_binding", Path(__file__).resolve().parents[1] / "integrations/hermes/xsm.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HermesLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_waits_for_inflight_open_before_removing_participation(self):
        entered, release = asyncio.Event(), asyncio.Event()
        closed = []

        async def close():
            closed.append(True)

        host = SimpleNamespace(close=close)

        async def open_host(**kwargs):
            entered.set()
            await release.wait()
            return host

        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_lock = {}, None
        binding.profile, binding.command, binding.env = "isolated", [], {}
        binding.sdk = SimpleNamespace(XsmHost=SimpleNamespace(open=open_host))
        scheduled = []
        binding._run = lambda coroutine: scheduled.append(asyncio.create_task(coroutine))
        opening = asyncio.create_task(binding._host("native", "/workspace"))
        await entered.wait()
        binding.finalize(session_id="native")
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(opening, *scheduled, return_exceptions=True)
        self.assertIs(results[0], host, repr(results))
        self.assertIsNone(results[1], repr(results))
        self.assertEqual(closed, [True])
        self.assertEqual(binding.hosts, {})


from tests.test_xsm import TempState
from unittest import mock
import json
import os
import sys


class HermesRegistrationTest(TempState):
    def context(self):
        self.tools, self.hooks, self.unload = {}, {}, []
        return SimpleNamespace(
            on_unload=self.unload.append,
            register_tool=lambda **tool: self.tools.__setitem__(tool["name"], tool),
            register_hook=lambda name, callback: self.hooks.__setitem__(name, callback),
            session_cwd=lambda: self.user_home)

    def test_pinned_command_and_environment_reach_describe_and_tool_processes(self):
        marker = Path(self.tmp, "backend-starts")
        root = Path(__file__).resolve().parents[1]
        boot = ("import os,pathlib,runpy,sys;"
                "p=pathlib.Path(os.environ['XSM_HERMES_TEST_MARKER']);"
                "p.open('a').write('start\\n');"
                "sys.path.insert(0,sys.argv.pop(1));"
                "runpy.run_module('xsm',run_name='__main__')")
        command = [sys.executable, "-B", "-c", boot, str(root), "protocol", "serve", "--stdio"]
        env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR") if key in os.environ}
        env.update(HOME=self.user_home, XSM_HOME=self.tmp, XSM_HERMES_TEST_MARKER=str(marker))
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, "hermes"))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.register(self.context(), command=command, env=env)
        try:
            self.assertEqual(len(self.tools), 21)
            self.assertEqual(len(self.hooks), 5)
            self.assertEqual(marker.read_text().splitlines(), ["start"])
            result = json.loads(self.tools["xsm_inbox"]["handler"]({}, session_id="pinned-native"))
            self.assertIsInstance(result, dict)
            self.assertEqual(marker.read_text().splitlines(), ["start", "start"])
            self.assertEqual(binding.command, command)
            self.assertEqual(len(binding.hosts), 1)
        finally:
            binding.close()
        self.assertFalse(binding.thread.is_alive())

    def test_registration_failure_stops_coordinator(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, "hermes"))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            with self.assertRaisesRegex(Exception, "peer closed stdout"):
                module.register(self.context(), command=[sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual(len(self.unload), 1)
        binding = self.unload[0].__self__
        self.assertTrue(binding.closed)
        self.assertFalse(binding.thread.is_alive())
