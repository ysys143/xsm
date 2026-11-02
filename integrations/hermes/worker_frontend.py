"""Native CLI entrypoint with a private pre-turn identity observer.

The original CLI parses flags, checks startup consent, creates/resumes the native
session and runs the gateway turn. StreamJsonEmitter.bind_session is observed;
its synchronous return waits for the owned journal before the CLI starts the turn.
Cancellation uses only the submitted admission's authoritative receipt/generation.
No model reply, native permission, route, session ID or tool list is synthesized.
"""
from pathlib import Path
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from xsm.native_worker_control import WorkerControlClient, ControlError

logger = logging.getLogger(__name__)


class CancellationObserver:
    def __init__(self, view, admission_id, control, initial_receipt, emit=None):
        self.view, self.admission_id, self.control = view, admission_id, control
        self.session_id = view.session_id
        if (not isinstance(initial_receipt, dict) or initial_receipt.get('admission_id') != admission_id
                or type(initial_receipt.get('authority_epoch')) is not int
                or initial_receipt['authority_epoch'] < 0
                or not isinstance(initial_receipt.get('ref'), dict)
                or any(not isinstance(initial_receipt['ref'].get(key), str) or not initial_receipt['ref'][key]
                       for key in ('profile_id', 'session_id'))):
            raise ValueError('native submission receipt is unavailable')
        self.epoch = initial_receipt['authority_epoch']
        self.ref = dict(initial_receipt['ref'])
        self.generation = initial_receipt.get('execution_generation') if initial_receipt.get('status') == 'started' else None
        if initial_receipt.get('status') == 'started' and (type(self.generation) is not int or self.generation <= 0):
            raise ValueError('invalid submitted native generation')
        self.requested = self.interrupted = self.closed = False
        self.task = None
        self.emit = emit or self._emit

    @staticmethod
    def _emit(value):
        sys.stdout.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        sys.stdout.flush()

    def current(self):
        return not self.closed and self.view.session_id == self.session_id == self.control.native_id

    async def step(self):
        if not self.current():
            return False
        pending = await asyncio.to_thread(self.control.cancellation_requested)
        if not self.current():
            return False
        if not pending:
            return self.admission_id not in self.view.completions
        self.requested = True
        receipt = await self.view.client.rpc('prompt.receipt', session_id=self.session_id,
                                              admission_id=self.admission_id, include_result=True)
        if not self.current():
            return False
        if (not isinstance(receipt, dict) or receipt.get('admission_id') != self.admission_id
                or type(receipt.get('authority_epoch')) is not int or receipt['authority_epoch'] < 0
                or not isinstance(receipt.get('ref'), dict)):
            raise ValueError('native cancellation receipt identity is unavailable')
        if receipt['authority_epoch'] != self.epoch or receipt['ref'] != self.ref:
            raise ValueError('native cancellation authority changed')
        status, generation = receipt.get('status'), receipt.get('execution_generation')
        if status == 'terminal':
            if receipt.get('outcome') not in ('cancelled', 'interrupted'):
                return False  # Completion won; preserve the actual native result.
            if generation is not None and (type(generation) is not int or generation <= 0):
                raise ValueError('invalid stopped native generation')
            if self.generation is not None and generation != self.generation:
                raise ValueError('stopped native generation changed')
            if receipt['outcome'] == 'interrupted' and generation is None:
                raise ValueError('interrupted native execution has no generation')
            not_started = generation is None and receipt['outcome'] == 'cancelled'
            interrupted = isinstance(receipt.get('result'), dict) and receipt['result'].get('interrupted') is True
            if not not_started and not interrupted:
                return False  # Administrative unknown resolution is not a native stop observation.
            self.emit({'type': 'xsm_native_cancelled', 'source': 'hermes/0.22.5',
                       'session_id': self.session_id, 'admission_id': self.admission_id,
                       'authority_epoch': self.epoch, 'execution_generation': generation,
                       'native_status': 'terminal', 'native_outcome': receipt['outcome'],
                       'native_interrupted': interrupted, 'native_not_started': not_started})
            await asyncio.to_thread(self.control.report_stopped)
            return False
        if status == 'queued':
            # Native prompt.cancel fences a queued->started race itself.
            await self.view.client.rpc('prompt.cancel', session_id=self.session_id, admission_id=self.admission_id)
        elif status == 'started':
            if type(generation) is not int or generation <= 0:
                raise ValueError('running native admission has no exact generation')
            if self.generation is None:
                self.generation = generation
            if generation != self.generation:
                raise ValueError('running native admission generation changed')
            if not self.interrupted:
                try:
                    await self.view.client.rpc('session.interrupt', session_id=self.session_id,
                                               execution_generation=self.generation)
                except Exception:
                    # A newer generation must not be targeted. Read this exact
                    # admission again instead of substituting the current one.
                    return True
                self.interrupted = True
        else:
            return False  # Unknown is not native quiescence.
        return True

    async def run(self):
        try:
            while await self.step():
                await asyncio.sleep(.2)
        except Exception as error:
            logger.warning('Owned native cancellation observation failed: %s', type(error).__name__)

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        if self.task is None:
            return
        if self.requested:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 2)
            except asyncio.TimeoutError:
                pass
        self.closed = True
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass


def observed_view(original, control):
    class OwnedView(original):
        async def submit(self, text):
            if self.session_id != control.native_id:
                raise ControlError('owned native context changed before submission')
            receipt = await super().submit(text)
            admission = receipt.get('admission_id') if isinstance(receipt, dict) else None
            if isinstance(admission, str) and admission:
                self._xsm_cancellation = CancellationObserver(self, admission, control, receipt)
                self._xsm_cancellation.start()
            return receipt

        async def run(self, *args, **kwargs):
            try:
                return await super().run(*args, **kwargs)
            finally:
                observer = getattr(self, '_xsm_cancellation', None)
                if observer is not None:
                    await observer.close()
    return OwnedView


def main():
    control = WorkerControlClient.from_environment()
    # A shared gateway never inherits one client's worker label as global state.
    os.environ.pop('XSM_WORKER', None)
    from hermes_cli import stream_json, gateway_chat_view
    from hermes_cli.gateway_client import GatewayClientError
    original = stream_json.StreamJsonEmitter
    original_view = gateway_chat_view.GatewayChatView

    class OwnedEmitter(original):
        def bind_session(self, session_id):
            try:
                control.bind(session_id)
            except ControlError:
                raise GatewayClientError('owned native context binding was refused') from None
            super().bind_session(session_id)

    stream_json.StreamJsonEmitter = OwnedEmitter
    gateway_chat_view.GatewayChatView = observed_view(original_view, control)
    try:
        from hermes_cli.main import main as native_main
        return native_main()
    finally:
        stream_json.StreamJsonEmitter = original
        gateway_chat_view.GatewayChatView = original_view
        control.close()


if __name__ == '__main__':
    raise SystemExit(main())
