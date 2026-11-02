import asyncio
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python"))
from xsm_client import RpcError, TransportError, XsmClient

PEER = str(pathlib.Path(__file__).with_name("echo_peer.py"))


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def connect(self, mode="normal", **options):
        client = await asyncio.wait_for(XsmClient.connect(
            [sys.executable, "-u", PEER, mode], close_timeout=0.1, **options
        ), 5)
        self.addAsyncCleanup(client.close)
        return client

    async def test_default_command(self):
        self.assertEqual(XsmClient.DEFAULT_COMMAND,
                         ("python3", "-m", "xsm", "protocol", "serve", "--stdio"))

    async def test_native_parent_is_refused_before_registration_on_old_server(self):
        client = await self.connect()
        with self.assertRaisesRegex(TransportError, 'native parent lineage'):
            await client.session_open(runtime='test', profile='local', conversation='child',
                                      cwd='/tmp', parent_conversation='native-parent')
        self.assertEqual(await client.request('echo', {'alive': True}), {'alive': True})

    async def test_negotiated_native_parent_is_sent_without_mutating_capabilities(self):
        client = await self.connect('lineage')
        capabilities = ['messaging']
        opened = await client.session_open(runtime='test', profile='local', conversation='child',
            cwd='/tmp', capabilities=capabilities, parent_conversation='native-parent')
        self.assertEqual(opened['generation'], 7)
        self.assertEqual(capabilities, ['messaging'])

    async def test_concurrent_reversed_responses(self):
        client = await self.connect()
        results = await asyncio.wait_for(asyncio.gather(
            client.request("test.pair", {"text": "first 세션"}),
            client.request("test.pair", {"text": "second 세션"}),
        ), 5)
        self.assertEqual(results, [{"text": "first 세션"}, {"text": "second 세션"}])

    async def test_session_contract_and_notifications(self):
        client = await self.connect()
        opened = await client.session_open(runtime="test", profile="local", conversation="a", cwd="/tmp")
        self.assertEqual(opened["generation"], 7)
        self.assertEqual(opened["extra"], "preserved")
        session = opened["session"]
        # The echo fixture checks transport only; real server validation is separate.
        self.assertEqual((await client.session_update(session, {"state": "busy"}))["session"], session)
        self.assertEqual(await client.operation_call(session, "echo", {"value": "한글"}),
                         {"session": session, "operation": "echo", "arguments": {"value": "한글"}})
        await client.events_subscribe(session)
        notification = await asyncio.wait_for(client.next_notification(), 2)
        self.assertEqual(notification, {"jsonrpc": "2.0", "method": "events/available",
                                      "params": {"session": session, "ids": ["delivery-세"]}})
        self.assertEqual(await client.delivery_report(session, "delivery-세", "queued"),
                         {"session": session, "id": "delivery-세", "state": "queued"})
        self.assertEqual(await client.session_close(session), {"session": session})

    async def test_rpc_error_does_not_poison_transport(self):
        client = await self.connect()
        with self.assertRaises(RpcError) as caught:
            await client.request("test.error")
        self.assertEqual((caught.exception.code, str(caught.exception), caught.exception.data),
                         (-32042, "expected failure", {"detail": "세부"}))
        self.assertEqual(await client.request("echo", {"ok": True}), {"ok": True})

    async def test_stderr_separate(self):
        chunks = []
        client = await self.connect(on_stderr=chunks.append)
        self.assertEqual(await client.request("test.stderr"), "stdout only")
        await client.close()
        self.assertIn('"id":"fake"', "".join(chunks))
        self.assertEqual("".join(chunks).count("진단"), 50_000)

    async def test_large_frame(self):
        client = await self.connect()
        self.assertEqual(await client.request("test.large"), "세" * 100_000)

    async def test_stderr_consumer_error_still_drains_and_reaps(self):
        def broken_consumer(text):
            raise RuntimeError("consumer failed")
        client = await self.connect(on_stderr=broken_consumer)
        with self.assertRaises(TransportError):
            await client.request("test.stderr")
        await asyncio.wait_for(client.close(), 3)
        self.assertIsNotNone(client.process.returncode)

    async def test_all_pending_rejected_on_bad_peer(self):
        for mode in ("eof", "malformed", "malformed-noisy", "truncated", "utf8", "bad-response", "bad-error", "peer-request"):
            with self.subTest(mode=mode):
                client = await self.connect(mode)
                results = await asyncio.wait_for(asyncio.gather(
                    client.request("test.pair"), client.request("test.pair"),
                    client.next_notification(), return_exceptions=True,
                ), 3)
                self.assertTrue(all(isinstance(item, TransportError) for item in results), results)
                with self.assertRaises(TransportError):
                    await client.request("echo")
                await asyncio.wait_for(client.close(), 3)
                self.assertIsNotNone(client.process.returncode)

    async def test_close_rejects_pending_and_kills_stubborn_peer(self):
        client = await self.connect("stubborn")
        pending = asyncio.create_task(client.request("test.hold"))
        await asyncio.sleep(0)
        await asyncio.wait_for(client.close(), 3)
        with self.assertRaises(TransportError):
            await pending
        self.assertIsNotNone(client.process.returncode)
        await client.close()

    async def test_cancelled_request_late_response(self):
        client = await self.connect()
        first = asyncio.create_task(client.request("test.pair", {"n": 1}))
        await asyncio.sleep(0.02)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        self.assertEqual(await client.request("test.pair", {"n": 2}), {"n": 2})
        self.assertEqual(await client.request("echo", {"ok": True}), {"ok": True})

    async def test_local_guards_and_serialization(self):
        client = await self.connect()
        with self.assertRaises(PermissionError):
            await client.request("decision.response", {"session": "forged"})
        for method in ("session.update", "session.close", "operation.call", "events.subscribe", "delivery.report"):
            with self.assertRaises(ValueError):
                await client.request(method)
        with self.assertRaises(ValueError):
            await client.session_update("handle", {"session": "forged"})
        with self.assertRaises(TypeError):
            await client.request("echo", {"not_json": object()})
        self.assertEqual(await client.request("echo", {}), {})

    async def test_initialization_failures_and_spawn_error(self):
        for mode, error in (("init-error", RpcError), ("init-eof", TransportError)):
            with self.subTest(mode=mode), self.assertRaises(error):
                await self.connect(mode)
        with self.assertRaises(OSError):
            await XsmClient.connect(["/does-not-exist/xsm"])

    async def test_context_manager_reaps_process(self):
        client = await self.connect()
        async with client:
            self.assertEqual(client.initialization, {"protocolVersion": "1"})
        self.assertEqual(client.process.returncode, 0)

    async def test_response_immediately_before_exit_is_delivered(self):
        client = await self.connect()
        self.assertEqual(await client.request("test.final"), {"final": True})
        with self.assertRaises(TransportError):
            await asyncio.wait_for(client.next_notification(), 2)
        await client.close()
        self.assertEqual(client.process.returncode, 0)



    async def test_initialize_deadline_rejects_invalid_values(self):
        for value in (False, 0, -1, float('inf'), float('nan'), '1', 10 ** 400):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, 'initialize_timeout'):
                    await XsmClient.connect(['must-not-spawn'], initialize_timeout=value)

    async def test_host_forwards_initialize_deadline(self):
        from xsm_host import XsmHost
        with self.assertRaisesRegex(TransportError, 'initialize.*timed out'):
            await asyncio.wait_for(XsmHost.open(runtime='fixture', profile='p', conversation='c',
                cwd=str(pathlib.Path.cwd()), command=[sys.executable, '-u', PEER, 'init-silent'],
                initialize_timeout=.05), 3)

    async def test_silent_initialize_times_out_and_reaps_peer(self):
        seen = []
        class Observed(XsmClient):
            def __init__(self, *args):
                super().__init__(*args)
                seen.append(self)
        try:
            with self.assertRaisesRegex(TransportError, 'initialize.*timed out'):
                await asyncio.wait_for(Observed.connect(
                    [sys.executable, '-u', PEER, 'init-silent'],
                    initialize_timeout=.05, close_timeout=.05), 2)
            self.assertIsNotNone(seen[0].process.returncode)
        finally:
            for client in seen:
                await client.close()

    async def test_version_negotiation_rejects_invalid_results_and_reaps_peer(self):
        for mode in ('init-wrong-version', 'init-missing-version', 'init-nonobject'):
            seen = []
            class Observed(XsmClient):
                def __init__(self, *args):
                    super().__init__(*args)
                    seen.append(self)
            try:
                with self.assertRaisesRegex(TransportError, 'version negotiation'):
                    await Observed.connect([sys.executable, '-u', PEER, mode], close_timeout=.1)
                self.assertIsNotNone(seen[0].process.returncode)
            finally:
                for client in seen:
                    await client.close()

    async def test_negotiation_error_survives_cleanup_error_after_reaping(self):
        seen, diagnostics = [], []
        class CleanupFails(XsmClient):
            def __init__(self, *args):
                super().__init__(*args)
                seen.append(self)
            async def close(self):
                await super().close()
                raise RuntimeError('fixture cleanup failure')
        try:
            with self.assertRaisesRegex(TransportError, 'version negotiation'):
                await CleanupFails.connect([sys.executable, '-u', PEER, 'init-wrong-version'],
                                           close_timeout=.1, on_stderr=diagnostics.append)
            self.assertIsNotNone(seen[0].process.returncode)
            self.assertTrue(any('fixture cleanup failure' in item for item in diagnostics))
        finally:
            for client in seen:
                try:
                    await client.close()
                except RuntimeError:
                    pass


if __name__ == "__main__":
    unittest.main()
