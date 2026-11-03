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
from xsm_host import XsmHost, RetryAdmission


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

    async def test_byte_limited_batches_keep_draining_below_count_limit(self):
        packets = []
        async def deliver(packet, _options):
            packets.append(packet)
        host = await self.host(deliver=deliver, inbox_batch_size=16, inbox_max_bytes=5000)
        sender, origin = await self.sender()
        for index in range(3):
            await sender.operation_call(origin['session'], 'xsm_send', {'target': 'ref:' + host.session['ref'],
                'text': 'byte-%s ' % index + 'x' * 3000, 'wake': 'never', 'wait': 0})
        host.pending_wake = True
        await host._drain()
        self.assertEqual([len(packet['claims']) for packet in packets], [1, 1, 1])
        self.assertTrue(all(packet['rendered_bytes'] <= 5000 for packet in packets))
        tokens = [claim['token'] for packet in packets for claim in packet['claims']]
        self.assertEqual(len((await host.call('xsm_ack', {'tokens': tokens}))['acked']), 3)

    async def test_notice_cursor_reaches_later_original_in_one_drain(self):
        packets = []
        async def deliver(packet, _options):
            packets.append(packet)
        code = "import runpy;from xsm import receive;check=receive.check;receive.check=lambda p,m:('block','P2P admission temporarily unavailable: fixture') if p.body.startswith('defer-') else check(p,m);runpy.run_module('xsm',run_name='__main__')"
        normal = self.command
        self.command = [sys.executable, '-B', '-c', code, 'protocol', 'serve', '--stdio']
        try:
            host = await self.host(deliver=deliver, inbox_batch_size=2, inbox_max_bytes=10000)
        finally:
            self.command = normal
        sender, origin = await self.sender()
        for text in ('defer-one', 'defer-two', 'allowed-last'):
            await sender.operation_call(origin['session'], 'xsm_send', {'target': 'ref:' + host.session['ref'],
                'text': text, 'wake': 'never', 'wait': 0})
        host.pending_wake = True
        await host._drain()
        self.assertEqual([len(packet['claims']) for packet in packets], [0, 1])
        self.assertIn('allowed-last', str(packets[1]['messages']))
        self.assertEqual(len((await host.call('xsm_ack', {'tokens': [packets[1]['claims'][0]['token']]}))['acked']), 1)

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

    async def test_native_backpressure_reacquires_original_with_new_token(self):
        packets, attempted, admitted = [], asyncio.Event(), asyncio.Event()
        async def deliver(packet, _options):
            packets.append(packet)
            if len(packets) == 1:
                attempted.set()
                raise RetryAdmission('queue full', .05)
            admitted.set()
        host = await self.host(deliver=deliver)
        await self.send(host, 'retry original')
        await asyncio.wait_for(attempted.wait(), 3)
        self.assertTrue((await host.client.request('operations/list'))['operations'])
        await asyncio.wait_for(admitted.wait(), 3)
        await host.delivery_task
        self.assertEqual(len(packets), 2)
        first, second = [packet['claims'][0] for packet in packets]
        self.assertEqual(first['id'], second['id'])
        self.assertNotEqual(first['token'], second['token'])
        self.assertEqual(len((await host.call('xsm_ack', {'tokens': [second['token']]}))['acked']), 1)
        self.assertEqual(self.errors, [])

    async def test_close_interrupts_native_capacity_retry(self):
        attempted, attempts = asyncio.Event(), []
        async def deliver(_packet, _options):
            attempts.append(True)
            attempted.set()
            raise RetryAdmission('queue full', 5)
        host = await self.host(deliver=deliver)
        await self.send(host, 'retain on close')
        await asyncio.wait_for(attempted.wait(), 3)
        await host.close()
        self.assertTrue(host.delivery_task.done())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.errors, [])

    async def test_retry_does_not_wake_fyi_after_original_was_consumed_elsewhere(self):
        retry_read, release, admitted = asyncio.Event(), asyncio.Event(), asyncio.Event()
        packets = []
        async def deliver(packet, options):
            packets.append((packet, options['wake']))
            if len(packets) == 1:
                raise RetryAdmission('queue full', .001)
            admitted.set()
        host = await self.host(deliver=deliver)
        original = host.client.operation_call
        reads = 0
        async def invoke(session, name, args):
            nonlocal reads
            if name == 'xsm_inbox' and 'limit' not in args:
                reads += 1
                if reads == 2:
                    retry_read.set()
                    await release.wait()
            return await original(session, name, args)
        host.client.operation_call = invoke
        sender, origin = await self.sender()
        await sender.operation_call(origin['session'], 'xsm_send', {'target': 'ref:' + host.session['ref'],
            'text': 'taken directly', 'wait': 0})
        await asyncio.wait_for(retry_read.wait(), 3)
        direct = await host.call('xsm_inbox', {'limit': 1})
        self.assertIn('taken directly', str(direct['messages']))
        await host.call('xsm_ack', {'tokens': [claim['token'] for claim in direct['claims']]})
        await sender.operation_call(origin['session'], 'xsm_send', {'target': 'ref:' + host.session['ref'],
            'text': 'quiet original', 'wake': 'never', 'wait': 0})
        release.set()
        await asyncio.wait_for(admitted.wait(), 3)
        await host.delivery_task
        self.assertEqual(len(packets), 2)
        self.assertFalse(packets[1][1])
        self.assertIn('quiet original', str(packets[1][0]['messages']))

    async def test_fyi_boundary_retries_without_waking_a_turn(self):
        admitted, packets = asyncio.Event(), []
        async def deliver(packet, options):
            packets.append((packet, options['wake']))
            if len(packets) == 1:
                raise RetryAdmission('queue full', .01)
            admitted.set()
        host = await self.host(deliver=deliver)
        await self.send(host, 'deferred quiet original', wake='never')
        with self.assertRaises(RetryAdmission):
            await host.natural_boundary()
        await asyncio.wait_for(admitted.wait(), 3)
        await host.delivery_task
        self.assertEqual([wake for _packet, wake in packets], [False, False])
        first, second = [packet['claims'][0] for packet, _wake in packets]
        self.assertEqual(first['id'], second['id'])
        self.assertNotEqual(first['token'], second['token'])
        self.assertEqual(len((await host.call('xsm_ack', {'tokens': [second['token']]}))['acked']), 1)
        self.assertEqual(self.errors, [])

    async def test_close_cancels_initial_boundary_retry_delay(self):
        attempts = []
        async def deliver(_packet, _options):
            attempts.append(True)
            raise RetryAdmission('queue full', 5)
        host = await self.host(deliver=deliver)
        await self.send(host, 'retain quiet original', wake='never')
        with self.assertRaises(RetryAdmission):
            await host.natural_boundary()
        await host.close()
        self.assertTrue(host.delivery_task.done())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.errors, [])

    async def test_missing_wake_metadata_never_implies_active_wake(self):
        wakes = []
        async def deliver(_packet, options):
            wakes.append(options['wake'])
        host = await self.host(deliver=deliver)
        original = host.client.operation_call
        async def invoke(*args):
            result = await original(*args)
            if args[1] == 'xsm_inbox':
                result.pop('items', None)
            return result
        host.client.operation_call = invoke
        await self.send(host, 'unknown wake metadata', wake='never')
        await host._deliver_inbox(True)
        self.assertEqual(wakes, [False])

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

    async def test_deferred_question_returns_before_ui_and_requires_explicit_retry(self):
        shown, reply = asyncio.Queue(), asyncio.Event()
        async def present(event, _cancelled):
            await shown.put(event)
            await reply.wait()
            return {'displayed':event['params']['question'],'source_id':event['params']['questionId'],'answer':'blue'}
        host = await self.host(present=present)
        args = {'question':'Deferred choice','options':['blue','green']}
        for invalid in (0, None, 'false'):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                await host.call('xsm_decide', args, wait_for_decision=invalid)
        result = await asyncio.wait_for(host.call('xsm_decide', args, wait_for_decision=False), 3)
        event = await asyncio.wait_for(shown.get(), 3)
        self.assertEqual(result['status'], 'waiting-for-user')
        self.assertNotIn('challenge', result)
        state = host.questions[result['question_id']]
        self.assertEqual(state['waiters'], 0)
        status = await host.call('xsm_decision_status', {'id':result['decision_id']})
        self.assertEqual(status['status'], 'pending')
        reply.set()
        await asyncio.wait_for(asyncio.shield(state['done']), 3)
        status = await host.call('xsm_decision_status', {'id':result['decision_id']})
        self.assertEqual(status['status'], 'answered')
        self.assertEqual(event['params']['questionId'], result['question_id'])
        applied = await host.call('xsm_decide', args)
        self.assertIn('your user answered: blue', str(applied))

    async def test_deferred_ui_survives_normal_waiter_cancel_until_explicit_abandon(self):
        shown = asyncio.Queue()
        async def present(event, cancelled):
            await shown.put(event)
            await cancelled.wait()
        host = await self.host(present=present)
        args = {'question':'Deferred cancellation','options':['blue','green']}
        result = await host.call('xsm_decide', args, wait_for_decision=False)
        await asyncio.wait_for(shown.get(), 3)
        waiter = asyncio.create_task(host.call('xsm_decide', args))
        state = host.questions[result['question_id']]
        async def registered():
            while state['waiters'] != 1:
                await asyncio.sleep(.001)
        await asyncio.wait_for(registered(), 3)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertFalse(state['cancelled'].is_set())
        with self.assertRaises(ValueError):
            await host.abandon_deferred('foreign-question')
        self.assertTrue(await host.abandon_deferred(result['question_id']))
        self.assertFalse(await host.abandon_deferred(result['question_id']))
        self.assertTrue(state['cancelled'].is_set())
        status = await host.call('xsm_decision_status', {'id':result['decision_id']})
        self.assertEqual(status['status'], 'pending')
        self.assertIsNone(status['answer'])

    async def test_cancelled_deferred_rpc_abandons_unowned_presentation(self):
        shown, ready, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def present(_event, cancelled):
            shown.set()
            await cancelled.wait()
        host = await self.host(present=present)
        original = host.client.operation_call
        async def delayed(*args, **kwargs):
            value = await original(*args, **kwargs)
            if args[1] == 'xsm_decide':
                ready.set()
                await release.wait()
            return value
        host.client.operation_call = delayed
        task = asyncio.create_task(host.call('xsm_decide', {'question':'Cancelled deferred RPC'}, wait_for_decision=False))
        await asyncio.wait_for(ready.wait(), 3)
        await asyncio.wait_for(shown.wait(), 3)
        task.cancel(); release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(next(iter(host.questions.values()))['cancelled'].is_set())

    async def test_deferred_abandon_intent_survives_callers_cancellation(self):
        shown, entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def present(_event, cancelled):
            shown.set()
            await cancelled.wait()
        host = await self.host(present=present)
        pending = await host.call('xsm_decide', {'question':'Release cancellation'}, wait_for_decision=False)
        await asyncio.wait_for(shown.wait(), 3)
        original = host._cancel_unused
        async def paused(state):
            entered.set()
            await release.wait()
            await original(state)
        host._cancel_unused = paused
        task = asyncio.create_task(host.abandon_deferred(pending['question_id']))
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        release.set()
        state = host.questions[pending['question_id']]
        await asyncio.wait_for(state['cancelled'].wait(), 3)

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
