"""Shared host paths against actual protocol subprocesses, without native UI or models."""
import asyncio
import importlib.util
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "clients/python"))
from xsm_client import XsmClient, TransportError
from xsm_host import XsmHost


class HostCoordinationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xsm-python-coordination-")
        self.env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR") if key in os.environ}
        self.env.update(HOME=self.temp.name, XSM_HOME=self.temp.name + "/state", PYTHONPATH=str(ROOT),
                        PYTHONDONTWRITEBYTECODE="1")
        self.command = [sys.executable, "-B", "-m", "xsm", "protocol", "serve", "--stdio"]
        self.hosts, self.clients, self.errors = [], [], []

    async def asyncTearDown(self):
        await asyncio.gather(*(host.close() for host in self.hosts))
        await asyncio.gather(*(client.close() for client in self.clients))
        self.temp.cleanup()

    async def host(self, **callbacks):
        host = await XsmHost.open(command=self.command, env=self.env, cwd=str(ROOT), runtime="python-native",
            profile="one", conversation=str(len(self.hosts)), on_error=self.errors.append, **callbacks)
        self.hosts.append(host)
        return host

    async def sender(self):
        client = await XsmClient.connect(self.command, cwd=str(ROOT), env=self.env)
        self.clients.append(client)
        session = await client.session_open(runtime="sender", profile="one", conversation="sender", cwd=str(ROOT))
        return client, session

    async def send(self, host, text, **options):
        client, session = await self.sender()
        return await client.operation_call(session["session"], "xsm_send",
            {"target": "ref:" + host.session["ref"], "text": text, "wait": 0, **options})

    async def test_pull_only_host_does_not_claim_a_native_delivery(self):
        host = await self.host()
        self.assertNotIn("events", host.session["capabilities"])
        await self.send(host, "pull original")
        packet = await host.call("xsm_inbox")
        self.assertEqual(len(packet["claims"]), 1)
        ack = await host.call("xsm_ack", {"tokens": [packet["claims"][0]["token"]]})
        self.assertEqual(len(ack["acked"]), 1)
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            await host.natural_boundary()

    async def test_one_coalesced_wake_drains_bounded_batches_without_auto_ack(self):
        packets = []
        async def deliver(packet, _options):
            packets.append(packet)
        host = await self.host(deliver=deliver, inbox_batch_size=2)
        client, session = await self.sender()
        for index in range(5):
            await client.operation_call(session['session'], 'xsm_send', {
                'target': 'ref:' + host.session['ref'], 'text': 'bounded-%s' % index,
                'wake': 'never', 'wait': 0})
        self.assertEqual(packets, [])
        host.pending_wake = True
        await host._drain()
        self.assertEqual([len(packet['messages']) for packet in packets], [2, 2, 1])
        claims = [claim for packet in packets for claim in packet['claims']]
        self.assertEqual(len({claim['id'] for claim in claims}), 5)
        ack = await host.call('xsm_ack', {'tokens': [claim['token'] for claim in claims]})
        self.assertEqual(len(ack['acked']), 5)

    async def test_full_notice_only_batch_does_not_repeat_without_progress(self):
        async def deliver(_packet, _options):
            pass
        host = await self.host(deliver=deliver, inbox_batch_size=2)
        reads = []
        async def notices(*_args):
            reads.append(True)
            if len(reads) > 2:
                raise RuntimeError('notice-only batch repeated')
            return {'messages': ['deferred first', 'deferred second'], 'claims': []}
        host.client.operation_call = notices
        host.pending_wake = True
        await host._drain()
        self.assertEqual(len(reads), 1)
        self.assertEqual(self.errors, [])

    async def test_ui_answer_is_applied_only_through_original_operation_retry(self):
        shown = []
        async def present(event, cancelled):
            shown.append(event["params"]["question"])
            self.assertFalse(cancelled.is_set())
            return {"displayed": shown[-1], "source_id": event["params"]["questionId"], "answer": "blue"}
        host = await self.host(present=present)
        result = await host.call("xsm_decide", {"question": "Choose", "options": ["blue", "green"]})
        self.assertIn("your user answered: blue", str(result))
        self.assertEqual(shown, ["Choose"])
        self.assertEqual(self.errors, [])

    async def test_last_waiter_cancellation_does_not_log_a_shielded_future_error(self):
        loop = asyncio.get_running_loop()
        prior = loop.get_exception_handler()
        logged, shown = [], asyncio.Event()
        loop.set_exception_handler(lambda _loop, context: logged.append(context))
        self.addCleanup(loop.set_exception_handler, prior)
        async def present(_event, cancelled):
            shown.set()
            await cancelled.wait()
        host = await self.host(present=present)
        task = asyncio.create_task(host.call('xsm_decide', {'question': 'Cancel fixture', 'options': ['blue', 'green']}))
        await asyncio.wait_for(shown.wait(), 3)
        while not any(state['waiters'] == 1 for state in host.questions.values()):
            await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        for _ in range(3):
            await asyncio.sleep(0)
        self.assertEqual([context.get('message') for context in logged], [])
        state = next(iter(host.questions.values()))
        self.assertTrue(state['cancelled'].is_set())
        self.assertEqual(state['waiters'], 0)

    async def test_one_cancelled_waiter_keeps_another_question_waiter(self):
        shown, reply = asyncio.Event(), asyncio.Event()
        async def present(event, cancelled):
            shown.set()
            await reply.wait()
            return {"displayed": event["params"]["question"], "source_id": event["params"]["questionId"], "answer": "blue"}
        host = await self.host(present=present)
        args = {"question": "Choose", "options": ["blue", "green"]}
        first = asyncio.create_task(host.call("xsm_decide", args))
        await asyncio.wait_for(shown.wait(), 3)
        second = asyncio.create_task(host.call("xsm_decide", args))
        async def both():
            while next(iter(host.questions.values()))["waiters"] != 2:
                await asyncio.sleep(.001)
        await asyncio.wait_for(both(), 3)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        reply.set()
        self.assertIn("your user answered: blue", str(await second))

    async def test_last_cancelled_waiter_abandons_display_without_denial(self):
        shown = asyncio.Queue()
        displays = 0
        async def present(event, cancelled):
            nonlocal displays
            displays += 1
            await shown.put(event)
            if displays == 1:
                await cancelled.wait()
            return {"displayed": event["params"]["question"], "source_id": event["params"]["questionId"], "answer": "blue"}
        host = await self.host(present=present)
        args = {"question": "Choose", "options": ["blue", "green"]}
        call = asyncio.create_task(host.call("xsm_decide", args))
        event = await asyncio.wait_for(shown.get(), 3)
        call.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await call
        status = await host.call("xsm_decision_status", {"id": event["params"]["decisionId"]})
        self.assertEqual(status["status"], "pending")
        self.assertIsNone(status["answer"])
        result = await host.call("xsm_decide", args)
        self.assertIn("your user answered: blue", str(result))
        self.assertNotEqual((await shown.get())["params"]["questionId"], event["params"]["questionId"])

    async def test_pending_rpc_waiter_is_not_lost_when_another_waiter_cancels(self):
        shown, reply, response_ready, release_response = [asyncio.Event() for _ in range(4)]
        ui_controls = []
        async def present(event, cancelled):
            ui_controls.append(cancelled)
            shown.set()
            await reply.wait()
            return {"displayed": event["params"]["question"], "source_id": event["params"]["questionId"], "answer": "blue"}
        host = await self.host(present=present)
        original, requests = host.client.operation_call, 0
        async def delayed(*args):
            nonlocal requests
            requests += 1
            number = requests
            result = await original(*args)
            if number == 2:
                response_ready.set()
                await release_response.wait()
            return result
        host.client.operation_call = delayed
        args = {"question": "Choose", "options": ["blue", "green"]}
        first = asyncio.create_task(host.call("xsm_decide", args))
        await asyncio.wait_for(shown.wait(), 3)
        second = asyncio.create_task(host.call("xsm_decide", args))
        try:
            await asyncio.wait_for(response_ready.wait(), 3)
            first.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(ui_controls[0].is_set(), "unregistered waiter was discarded")
            release_response.set()
            with self.assertRaises(asyncio.CancelledError):
                await first
            reply.set()
            self.assertIn("your user answered: blue", str(await asyncio.wait_for(second, 3)))
        finally:
            release_response.set()
            reply.set()
            for call in (first, second):
                if not call.done():
                    call.cancel()
            await asyncio.gather(first, second, return_exceptions=True)

    async def test_admission_failure_releases_claim_for_a_later_boundary(self):
        failed = asyncio.Event()
        packets = []
        async def deliver(packet, options):
            if not failed.is_set():
                failed.set()
                raise RuntimeError("queue refused")
            packets.append((packet, options))
        host = await self.host(deliver=deliver)
        await self.send(host, "keep after refusal")
        await asyncio.wait_for(failed.wait(), 3)
        await host.delivery_task
        packet = await host.natural_boundary()
        self.assertEqual(len(packet["claims"]), 1)
        self.assertFalse(packets[0][1]["wake"])
        ack = await host.call("xsm_ack", {"tokens": [packet["claims"][0]["token"]]})
        self.assertEqual(len(ack["acked"]), 1)

    async def test_fyi_enters_only_at_a_natural_boundary_and_is_not_auto_acked(self):
        packets = []
        async def deliver(packet, options):
            packets.append((packet, options))
        host = await self.host(deliver=deliver)
        await self.send(host, "fyi original", wake="never")
        await host.client.request("operations/list")
        self.assertEqual(packets, [])
        packet = await host.natural_boundary()
        self.assertEqual(len(packet["claims"]), 1)
        self.assertFalse(packets[0][1]["wake"])
        self.assertEqual(len((await host.call("xsm_ack", {"tokens": [packet["claims"][0]["token"]]}))["acked"]), 1)

    async def test_false_native_admission_never_reports_delivery_and_releases_original(self):
        async def deliver(_packet, _options):
            return False
        host = await self.host(deliver=deliver)
        reports = []
        original = host.client.delivery_report
        async def reported(*args):
            reports.append(args)
            return await original(*args)
        host.client.delivery_report = reported
        await self.send(host, "not admitted")
        async def started():
            while host.delivery_task is None:
                await asyncio.sleep(.001)
        await asyncio.wait_for(started(), 3)
        await host.delivery_task
        self.assertEqual(reports, [])
        self.assertTrue(host.delivery_suspended)
        self.assertEqual(len((await host.call("xsm_inbox"))["claims"]), 1)

    async def test_transport_death_rejects_ui_and_ignores_late_answer(self):
        shown, late = asyncio.Event(), asyncio.Event()
        async def present(event, cancelled):
            shown.set()
            await late.wait()
            return {"displayed": event["params"]["question"], "source_id": event["params"]["questionId"], "answer": "blue"}
        host = await self.host(present=present)
        call = asyncio.create_task(host.call("xsm_decide", {"question": "Choose"}))
        await asyncio.wait_for(shown.wait(), 3)
        host.client.process.kill()
        with self.assertRaises(TransportError):
            await asyncio.wait_for(call, 3)
        late.set()

    async def test_immutable_sdk_roots_keep_separate_client_and_host_modules(self):
        spec = importlib.util.spec_from_file_location("hermes_loader_fixture", ROOT / "integrations/hermes/xsm.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        second = Path(self.temp.name, "second-root")
        shutil.copytree(ROOT / "clients/python", second / "clients/python", ignore=shutil.ignore_patterns("__pycache__"))
        first_sdk, second_sdk = module._sdk(ROOT), module._sdk(second)
        self.assertIsNot(first_sdk.XsmHost, second_sdk.XsmHost)
        self.assertIsNot(first_sdk.XsmHostClient, second_sdk.XsmHostClient)
        self.assertTrue(str(second_sdk.__file__).startswith(str(second)))
        self.assertIs(module._sdk(second), second_sdk)
