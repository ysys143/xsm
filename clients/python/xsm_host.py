"""Experimental async host coordination. Native code supplies admission and UI callbacks."""
from __future__ import annotations

import asyncio
import math
from pathlib import Path
import sys

if __package__:
    from .xsm_client import XsmHostClient, TransportError
else:
    from xsm_client import XsmHostClient, TransportError


class RetryAdmission(RuntimeError):
    def __init__(self, message, delay_seconds=.25):
        if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or not 0 < delay_seconds <= 60 or not math.isfinite(delay_seconds):
            raise ValueError("retry delay must be within 0–60 seconds")
        super().__init__(message)
        self.delay_seconds = delay_seconds


class XsmHost:
    @classmethod
    async def open(cls, *, runtime, profile, conversation, cwd, deliver=None, present=None,
                   command=None, env=None, on_error=None, inbox_batch_size=None, inbox_max_bytes=None,
                   initialize_timeout=10.0):
        if inbox_max_bytes is not None and (type(inbox_max_bytes) is not int or not 1 <= inbox_max_bytes <= 1048576):
            raise ValueError("inbox_max_bytes must be an integer from 1 to 1048576")
        if inbox_batch_size is not None and (type(inbox_batch_size) is not int or not 1 <= inbox_batch_size <= 100):
            raise ValueError("inbox_batch_size must be an integer from 1 to 100")
        command = command or [str(Path(__file__).resolve().parents[2] / "bin/xsm"),
                              "protocol", "serve", "--stdio"]
        client = await XsmHostClient.connect(command, cwd=cwd, env=env, initialize_timeout=initialize_timeout)
        try:
            capabilities = ["messaging", "inbox"] + (["events"] if deliver else []) + (["user-decisions"] if present else [])
            available = client.initialization.get("capabilities", [])
            lease = client.initialization.get("limits", {}).get("claimLeaseSeconds", 0)
            try:
                valid_lease = type(lease) in (int, float) and math.isfinite(lease) and lease > 0
            except OverflowError:
                valid_lease = False
            if not isinstance(available, list) or any(value not in available for value in capabilities) or not valid_lease:
                raise TransportError("server lacks required host capabilities or a finite positive claim lease")
            session = await client.session_open(runtime=runtime, profile=profile, conversation=conversation,
                                                cwd=cwd, capabilities=capabilities)
            operations = (await client.request("operations/list"))["operations"]
            if inbox_max_bytes is not None and not any(item['name'] == 'xsm_inbox' and
                    'max_bytes' in item['inputSchema'].get('properties', {}) for item in operations):
                raise TransportError('server does not advertise inbox byte budgets')
            host = cls(client, session, operations, deliver, present, on_error)
            host.inbox_batch_size = inbox_batch_size
            host.inbox_max_bytes = inbox_max_bytes
            if deliver:
                await client.events_subscribe(session["session"])
            host.pump = asyncio.create_task(host._pump())
            return host
        except BaseException:
            try:
                await client.close()
            except Exception as cleanup_error:
                try:
                    if on_error:
                        on_error(cleanup_error)
                    else:
                        print("xsm:", str(cleanup_error), file=sys.stderr)
                except Exception:
                    pass
            raise

    def __init__(self, client, session, operations, deliver, present, on_error):
        self.client, self.session, self.operations = client, session, operations
        self.deliver, self.present, self.on_error = deliver, present, on_error
        self.questions = {}
        self.cancelled = asyncio.Event()
        self.delivery_lock = asyncio.Lock()
        self.invoke_lock = asyncio.Lock()
        self.pending_wake = False
        self.delivery_suspended = False
        self.closed = False
        self.inbox_batch_size = None
        self.inbox_max_bytes = None
        self.failure = None
        self.delivery_task = None

    def _error(self, error):
        try:
            if self.on_error:
                self.on_error(error)
            else:
                print("xsm:", str(error), file=sys.stderr)
        except Exception:
            pass

    def _question(self, ident):
        if ident not in self.questions:
            done = asyncio.get_running_loop().create_future()
            done.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
            self.questions[ident] = {"done": done, "waiters": 0, "cancelled": asyncio.Event()}
        return self.questions[ident]

    async def _abandon(self, state):
        if state.get("event") and not state.get("abandon") and not self.closed:
            state["abandon"] = asyncio.create_task(self.client.abandon_decision(state["event"]))
        if state.get("abandon"):
            await asyncio.shield(state["abandon"])

    async def _cancel_unused(self, state):
        async with self.invoke_lock:
            if state["waiters"] or state["done"].done() or self.closed:
                return
            state["cancelled"].set()
            if state.get("task"):
                state["task"].cancel()
            state["done"].cancel()
            try:
                await self._abandon(state)
            except Exception as error:
                self._error(error)

    async def _show(self, state, event):
        try:
            if state["cancelled"].is_set() or self.closed:
                await self._abandon(state)
                return
            response = await self.present(event, state["cancelled"])
            if state["cancelled"].is_set() or self.closed:
                return
            result = await self.client.respond_to_decision(event, **response)
            if not state["done"].done():
                state["done"].set_result(result)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not state["done"].done():
                state["done"].set_exception(error)
            try:
                await self._abandon(state)
            except Exception:
                pass
            self._error(error)

    async def _pump(self):
        try:
            while not self.closed:
                event = await self.client.next_notification()
                if event.get("params", {}).get("session") != self.session["session"]:
                    continue
                if event["method"] == "decision/request":
                    state = self._question(event["params"]["questionId"])
                    if not state.get("event"):
                        state["event"] = event
                        state["task"] = asyncio.create_task(self._show(state, event))
                elif event["method"] == "events/available" and not self.delivery_suspended:
                    self.pending_wake = True
                    self._schedule_delivery()
        except Exception as error:
            if not self.closed:
                self.failure = error
                self.cancelled.set()
                for state in self.questions.values():
                    state["cancelled"].set()
                    if state.get("task"):
                        state["task"].cancel()
                    if not state["done"].done():
                        state["done"].set_exception(error)
                if self.delivery_task:
                    self.delivery_task.cancel()
                self._error(error)

    async def call(self, operation, arguments=None):
        if self.closed or self.failure:
            raise self.failure or TransportError("host closed")
        arguments = {} if arguments is None else arguments
        state, cancelled_state = None, None
        try:
            # Register every nonblocking reply before cancellation can decide
            # that the last waiter left; do not coalesce ordinary operations.
            async with self.invoke_lock:
                request = asyncio.create_task(self.client.operation_call(self.session["session"], operation, arguments))
                try:
                    result = await asyncio.shield(request)
                except asyncio.CancelledError:
                    result = await asyncio.shield(request)
                    if isinstance(result, dict) and result.get("status") == "waiting-for-user":
                        cancelled_state = self._question(result["question_id"])
                    raise
                if isinstance(result, dict) and result.get("status") == "waiting-for-user":
                    if not result.get("question_id"):
                        raise TransportError("server did not identify its host question")
                    state = self._question(result["question_id"])
                    state["waiters"] += 1
        except asyncio.CancelledError:
            if cancelled_state:
                await self._cancel_unused(cancelled_state)
            raise
        if state is not None:
            try:
                await asyncio.shield(state["done"])
            finally:
                state["waiters"] -= 1
                await self._cancel_unused(state)
            if self.closed or self.failure:
                raise self.failure or TransportError("host closed")
            result = await self.client.operation_call(self.session["session"], operation, arguments)
            if isinstance(result, dict) and result.get("status") == "waiting-for-user":
                raise RuntimeError("operation still waiting; inspect its decision status")
        return result

    async def _deliver_inbox(self, wake, after_id=None):
        async with self.delivery_lock:
            args = {} if self.inbox_batch_size is None else {"limit": self.inbox_batch_size}
            if self.inbox_max_bytes is not None:
                args['max_bytes'] = self.inbox_max_bytes
            if after_id is not None:
                args['after_id'] = after_id
            packet = await self.client.operation_call(self.session["session"], "xsm_inbox", args)
            if not packet["messages"]:
                return packet
            try:
                should_wake = bool(wake and packet["claims"] and
                    any(item.get("wake") for item in packet.get("items", [])))
                admitted = await self.deliver(packet, {"wake": should_wake, "cancelled": self.cancelled,
                    "lease_seconds": self.client.initialization["limits"]["claimLeaseSeconds"]})
                if admitted is False:
                    raise RuntimeError("native admission callback refused the message")
                for claim in packet["claims"]:
                    await self.client.delivery_report(self.session["session"], claim["id"], "admitted", claim["token"])
            except BaseException:
                if not self.closed and packet["claims"]:
                    try:
                        await self.client.request("inbox.release", {"session": self.session["session"],
                            "tokens": [claim["token"] for claim in packet["claims"]]})
                    except Exception as cleanup_error:
                        self._error(cleanup_error)
                raise
            return packet

    def _schedule_delivery(self, delay=0, after_id=None):
        if self.closed or self.cancelled.is_set() or self.delivery_suspended:
            return
        if self.delivery_task and not self.delivery_task.done():
            return
        async def run():
            if delay:
                try:
                    await asyncio.wait_for(self.cancelled.wait(), delay)
                    return
                except asyncio.TimeoutError:
                    pass
            await self._drain(after_id)
        def finished(task):
            if not task.cancelled() and task.exception():
                self.delivery_suspended = True
                self._error(task.exception())
            if self.delivery_task is task and self.pending_wake:
                self._schedule_delivery()
        self.delivery_task = asyncio.create_task(run())
        self.delivery_task.add_done_callback(finished)

    async def _drain(self, after_id=None):
        while self.pending_wake and not self.closed and not self.delivery_suspended:
            self.pending_wake = False
            try:
                packet = await self._deliver_inbox(True, after_id)
                progressed = bool(packet['claims'] or (packet.get('next_after') and packet['next_after'] != after_id))
                after_id = packet.get('next_after')
                if progressed and (packet.get('batch_limited') or
                        (self.inbox_batch_size and len(packet['messages']) >= self.inbox_batch_size)):
                    self.pending_wake = True
            except asyncio.CancelledError:
                raise
            except RetryAdmission as error:
                try:
                    await asyncio.wait_for(self.cancelled.wait(), error.delay_seconds)
                except asyncio.TimeoutError:
                    self.pending_wake = True
            except Exception as error:
                self.delivery_suspended = True
                self._error(error)

    async def natural_boundary(self):
        if self.deliver is None:
            raise RuntimeError("native admission callback is not connected; use xsm_inbox")
        self.delivery_suspended = False
        try:
            packet = await self._deliver_inbox(False)
            if packet.get('batch_limited') and packet.get('next_after'):
                self.pending_wake = True
                self._schedule_delivery(after_id=packet['next_after'])
            return packet
        except RetryAdmission as error:
            self.pending_wake = True
            self._schedule_delivery(error.delay_seconds)
            raise

    async def update(self, state, name=None):
        value = {"state": state}
        if name is not None:
            value["name"] = name
        return await self.client.session_update(self.session["session"], value)

    async def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancelled.set()
        tasks = []
        for state in self.questions.values():
            state["cancelled"].set()
            if state.get("task"):
                state["task"].cancel()
                tasks.append(state["task"])
            if state.get("abandon"):
                tasks.append(state["abandon"])
            if not state["done"].done():
                state["done"].set_exception(TransportError("host closed"))
        if self.delivery_task:
            self.delivery_task.cancel()
            tasks.append(self.delivery_task)
        await self.client.close()
        await self.pump
        await asyncio.gather(*tasks, return_exceptions=True)
