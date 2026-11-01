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
