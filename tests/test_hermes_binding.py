"""Hermes coordinator lifecycle and isolated backend recovery, without a model."""
import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest


spec = importlib.util.spec_from_file_location(
    "xsm_hermes_binding", Path(__file__).resolve().parents[1] / "integrations/hermes/xsm.py")
module = importlib.util.module_from_spec(spec)
if os.environ.get('XSM_HERMES_MONITOR_MUTANT') == 'disabled':
    code = Path(spec.origin).read_text()
    changed = code.replace('    async def _monitor(self, sid, cwd):', '    async def _monitor(self, sid, cwd):\n        return')
    if changed == code:
        raise RuntimeError('monitor entry moved; update intentional mutation')
    exec(compile(changed, spec.origin, 'exec'), module.__dict__)
else:
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
        binding.hosts, binding.host_locks = {}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors, binding.states = False, False, set(), {}, {}
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
        self.assertIsInstance(results[0], RuntimeError, repr(results))
        self.assertIn("closing", str(results[0]))
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
        binding.hosts, binding.host_locks = {"native": ("/workspace", existing)}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors, binding.states = False, False, set(), {}, {}
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


    async def test_monitor_backs_off_transient_failures_and_restores_activity(self):
        attempts, ready = [], asyncio.Event()
        async def close():
            pass
        async def update(state):
            self.assertEqual(state, "busy")
            ready.set()
        old = SimpleNamespace(failure=RuntimeError("lost transport"), closed=False, close=close)
        new = SimpleNamespace(failure=None, closed=False, update=update, close=close)
        async def open_host(**kwargs):
            attempts.append(asyncio.get_running_loop().time())
            if len(attempts) < 3:
                raise RuntimeError("temporary transport failure")
            return new
        pending = asyncio.get_running_loop().create_future()
        pending.set_result(old)
        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_locks = {"native": ("/workspace", pending)}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors = False, False, set(), {}
        binding.states = {"native": "busy"}
        binding.profile, binding.command, binding.env = "isolated", [], {}
        binding.sdk = SimpleNamespace(TransportError=RuntimeError, XsmHost=SimpleNamespace(open=open_host))
        task = asyncio.create_task(binding._monitor("native", "/workspace"))
        binding.monitors["native"] = task
        try:
            await asyncio.wait_for(ready.wait(), 4)
            self.assertEqual(len(attempts), 3)
            self.assertGreaterEqual(attempts[1] - attempts[0], .45)
            self.assertGreaterEqual(attempts[2] - attempts[1], .95)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


    async def test_slow_registration_does_not_block_another_native_conversation(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def close():
            pass
        async def open_host(**kwargs):
            if kwargs['conversation'] == 'slow':
                entered.set()
                await release.wait()
            return SimpleNamespace(close=close)
        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_locks = {}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors, binding.states = False, False, set(), {}, {}
        binding.profile, binding.command, binding.env = 'isolated', [], {}
        binding.sdk = SimpleNamespace(XsmHost=SimpleNamespace(open=open_host))
        existing = await binding._host('fast', '/workspace')
        slow = asyncio.create_task(binding._host('slow', '/workspace'))
        await entered.wait()
        fast = asyncio.create_task(binding._host('fast', '/workspace'))
        try:
            self.assertIs(await asyncio.wait_for(asyncio.shield(fast), .2), existing)
            await asyncio.wait_for(binding._host('another', '/workspace'), .2)
            self.assertFalse(slow.done())
        finally:
            release.set()
            await asyncio.gather(slow, fast, return_exceptions=True)
            tasks = list(binding.monitors.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


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
            self.assertEqual(len(self.tools), 22)
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

    def test_registered_backend_reconnects_without_native_call_and_restores_state(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.register(self.context())
        async def crash_and_wait():
            before = await binding.hosts['automatic'][1]
            before.client.process.kill()
            await before.client.process.wait()
            for _ in range(300):
                pair = binding.hosts.get('automatic')
                if pair and pair[1].done():
                    current = pair[1].result()
                    rows = [json.loads(path.read_text()) for path in Path(self.tmp, 'sessions').glob('*.json')]
                    busy = any(row.get('pid') == current.client.process.pid and row.get('activity') == 'busy' for row in rows)
                    if current is not before and busy:
                        return before, current
                await asyncio.sleep(.01)
            raise AssertionError('no automatic registration')
        try:
            binding.start(session_id='automatic')
            before, after = binding._run(crash_and_wait())
            self.assertEqual(before.session['ref'], after.session['ref'])
            self.assertNotEqual(before.session['generation'], after.session['generation'])
            self.assertNotEqual(before.client.process.pid, after.client.process.pid)
            binding.finalize(session_id='automatic')
            async def wait():
                await asyncio.sleep(.4)
                return list(binding.hosts), list(binding.monitors)
            self.assertEqual(binding._run(wait()), ([], []))
        finally:
            binding.close()
        self.assertFalse(binding.thread.is_alive())


    def test_unload_cancels_backend_open_before_stopping_loop(self):
        import concurrent.futures
        import threading
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.HermesBinding(self.context())
        entered = threading.Event()
        release = binding._run(self.make_event())
        async def close():
            pass
        async def blocked(**kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(close=close)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        stopping = None
        try:
            with mock.patch.object(binding.sdk.XsmHost, 'open', new=blocked):
                opening = asyncio.run_coroutine_threadsafe(binding._host('pending', self.user_home), binding.loop)
                self.assertTrue(entered.wait(2))
                stopping = pool.submit(binding.close)
                try:
                    stopping.result(timeout=2)
                finally:
                    if not binding.loop.is_closed():
                        binding.loop.call_soon_threadsafe(release.set)
                    stopping.result(timeout=3)
                self.assertTrue(opening.cancelled())
                self.assertFalse(binding.thread.is_alive())
        finally:
            if not binding.loop.is_closed():
                binding.loop.call_soon_threadsafe(release.set)
                binding.close()
            pool.shutdown(wait=True)

    async def make_event(self):
        return asyncio.Event()
