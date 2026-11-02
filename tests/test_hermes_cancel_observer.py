"""Exact-admission observer using native contract fixtures, not a Hermes run."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('hermes_cancel_frontend',
    Path(__file__).resolve().parents[1] / 'integrations/hermes/worker_frontend.py')
frontend = importlib.util.module_from_spec(spec); spec.loader.exec_module(frontend)


class HermesCancellationObserverTest(unittest.IsolatedAsyncioTestCase):
    def fixture(self, receipts, *, stale=False):
        calls, emitted, reports = [], [], []
        async def rpc(method, **params):
            calls.append((method, params))
            self.assertEqual(params['session_id'], 'native-owned')
            if method == 'prompt.receipt':
                self.assertEqual(params['admission_id'], 'own-admission')
                return receipts.pop(0)
            if method == 'session.interrupt' and stale:
                raise RuntimeError('stale_generation')
            return {}
        control = SimpleNamespace(native_id='native-owned', cancellation_requested=lambda: True,
                                   report_stopped=lambda: reports.append(True))
        view = SimpleNamespace(session_id='native-owned', generation=999, completions={},
                               client=SimpleNamespace(rpc=rpc))
        observer = frontend.CancellationObserver(view, 'own-admission', control, self.receipt('queued', None), emit=emitted.append)
        return observer, calls, emitted, reports

    def receipt(self, status, generation=7, outcome=None, epoch=1):
        result = dict(admission_id='own-admission', ref=dict(profile_id='profile', session_id='logical-native'),
                    status=status, execution_generation=generation, authority_epoch=epoch, outcome=outcome)
        if status == 'terminal' and generation is not None and outcome in ('cancelled', 'interrupted'):
            result['result'] = {'interrupted': True}
        return result

    async def test_interrupt_uses_own_receipt_generation_not_latest_view_generation(self):
        observer, calls, emitted, reports = self.fixture([
            self.receipt('started'), self.receipt('terminal', outcome='interrupted')])
        self.assertTrue(await observer.step())
        self.assertEqual(calls[-1], ('session.interrupt', dict(session_id='native-owned', execution_generation=7)))
        self.assertEqual(reports, [])
        self.assertFalse(await observer.step())
        self.assertEqual(emitted[0]['execution_generation'], 7)
        self.assertEqual(reports, [True])

    async def test_queued_cancel_uses_admission_and_can_confirm_no_execution(self):
        observer, calls, emitted, reports = self.fixture([
            self.receipt('queued', None), self.receipt('terminal', None, 'cancelled')])
        self.assertTrue(await observer.step())
        self.assertEqual(calls[-1], ('prompt.cancel', dict(session_id='native-owned', admission_id='own-admission')))
        self.assertFalse(await observer.step())
        self.assertIsNone(emitted[0]['execution_generation']); self.assertEqual(reports, [True])

    async def test_stale_interrupt_does_not_fall_back_to_another_generation(self):
        observer, calls, emitted, reports = self.fixture([
            self.receipt('started'), self.receipt('terminal', outcome='completed')], stale=True)
        self.assertTrue(await observer.step()); self.assertFalse(await observer.step())
        self.assertEqual([params['execution_generation'] for method, params in calls if method == 'session.interrupt'], [7])
        self.assertEqual((emitted, reports), ([], []))

    async def test_changed_authority_or_execution_generation_never_confirms_stop(self):
        for terminal in (self.receipt('terminal', 8, 'interrupted'), self.receipt('terminal', 7, 'interrupted', 2)):
            observer, calls, emitted, reports = self.fixture([self.receipt('started'), terminal])
            await observer.step()
            with self.assertRaises(ValueError): await observer.step()
            self.assertEqual((emitted, reports), ([], []))

    async def test_another_admission_and_boolean_generation_are_refused(self):
        for receipt in (dict(self.receipt('started'), admission_id='foreign'), self.receipt('started', True)):
            observer, calls, emitted, reports = self.fixture([receipt])
            with self.assertRaises(ValueError): await observer.step()
            self.assertEqual([method for method, _ in calls], ['prompt.receipt'])
            self.assertEqual((emitted, reports), ([], []))

    async def test_changed_native_view_cannot_cancel_another_session(self):
        observer, calls, emitted, reports = self.fixture([self.receipt('started')])
        observer.view.session_id = 'another-session'
        self.assertFalse(await observer.step())
        self.assertEqual((calls, emitted, reports), ([], [], []))

    async def test_submission_epoch_is_pinned_before_first_cancellation_receipt(self):
        observer, calls, emitted, reports = self.fixture([self.receipt('started', epoch=2)])
        with self.assertRaises(ValueError): await observer.step()
        self.assertEqual([method for method, _ in calls], ['prompt.receipt'])
        self.assertEqual((emitted, reports), ([], []))

    async def test_view_switch_during_receipt_query_cannot_interrupt_another_session(self):
        observer, calls, emitted, reports = self.fixture([self.receipt('started')])
        original = observer.view.client.rpc
        async def changed(method, **params):
            result = await original(method, **params)
            observer.view.session_id = 'another-session'
            return result
        observer.view.client.rpc = changed
        self.assertFalse(await observer.step())
        self.assertEqual([method for method, _ in calls], ['prompt.receipt'])
        self.assertEqual((emitted, reports), ([], []))

    async def test_invalid_submission_generation_is_refused_before_observation(self):
        observer, calls, emitted, reports = self.fixture([])
        for generation in (None, True, 0):
            with self.assertRaises(ValueError):
                frontend.CancellationObserver(observer.view, 'own-admission', observer.control,
                                               self.receipt('started', generation), emit=emitted.append)

    async def test_administrative_unknown_resolution_is_not_native_quiescence(self):
        receipt = self.receipt('terminal', outcome='interrupted'); receipt.pop('result')
        observer, calls, emitted, reports = self.fixture([receipt])
        self.assertFalse(await observer.step())
        self.assertEqual((emitted, reports), ([], []))
