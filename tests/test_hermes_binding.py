"""Hermes coordinator lifecycle and isolated backend recovery, without a model."""
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


    async def test_failed_operation_is_not_replayed_when_next_invocation_recovers(self):
        calls, opens = [], []
        async def close():
            old.closed = True
        async def failed(operation, arguments):
            calls.append(operation)
            old.failure = RuntimeError("outcome unknown")
            raise old.failure
        async def successful(operation, arguments):
            calls.append(operation)
            return {"recovered": True}
        old = SimpleNamespace(failure=None, closed=False, call=failed, close=close)
        new = SimpleNamespace(failure=None, closed=False, call=successful)
        async def open_host(**kwargs):
            opens.append(kwargs)
            return new
        existing = asyncio.get_running_loop().create_future()
        existing.set_result(old)
        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_lock = {"native": ("/workspace", existing)}, None
        binding.profile, binding.command, binding.env = "isolated", [], {}
        binding.sdk = SimpleNamespace(XsmHost=SimpleNamespace(open=open_host))
        with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
            await binding._call("native", "/workspace", "xsm_send", {})
        self.assertEqual(calls, ["xsm_send"])
        self.assertEqual(opens, [])
        result = await binding._call("native", "/workspace", "xsm_inbox", {})
        self.assertEqual(result, {"recovered": True})
        self.assertEqual(calls, ["xsm_send", "xsm_inbox"])
        self.assertEqual(len(opens), 1)
        self.assertTrue(old.closed)


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

    def test_next_native_call_recovers_dead_backend_without_inheriting_claim(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.register(self.context())
        def invoke(sid, operation, arguments=None):
            return json.loads(self.tools[operation]['handler'](arguments or {}, session_id=sid))
        async def host(sid):
            return await binding.hosts[sid][1]
        async def crash(value):
            value.client.process.kill()
            await value.client.process.wait()
            for _ in range(100):
                if value.failure is not None:
                    return
                await asyncio.sleep(.01)
            raise AssertionError('SDK did not observe dead backend')
        try:
            invoke('sender', 'xsm_inbox')
            invoke('receiver', 'xsm_inbox')
            before = binding._run(host('receiver'))
            invoke('sender', 'xsm_send', {'target': 'ref:' + before.session['ref'], 'text': 'survive backend death', 'wait': 0})
            original = invoke('receiver', 'xsm_inbox')['claims'][0]
            binding._run(crash(before))
            recovered = invoke('receiver', 'xsm_inbox')
            after = binding._run(host('receiver'))
            self.assertIsNot(after, before)
            self.assertEqual(after.session['ref'], before.session['ref'])
            self.assertNotEqual(after.session['generation'], before.session['generation'])
            self.assertNotEqual(after.client.process.pid, before.client.process.pid)
            self.assertEqual(recovered['claims'][0]['id'], original['id'])
            self.assertNotEqual(recovered['claims'][0]['token'], original['token'])
            with self.assertRaises(Exception) as refused:
                invoke('receiver', 'xsm_ack', {'tokens': [original['token']]})
            self.assertEqual(refused.exception.code, -32602)
            self.assertEqual(invoke('receiver', 'xsm_ack', {'tokens': [recovered['claims'][0]['token']]})['acked'], [original['id']])
        finally:
            binding.close()
        self.assertFalse(binding.thread.is_alive())
