"""P08 journal ownership/reservation tests, using temporary state only."""
import concurrent.futures
import os
from unittest import mock

from tests import test_xsm


class OwnedRequestsTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        self.owner = {'runtime': 'codex', 'home': self.tmp + '/owner', 'session_id': 'owner'}
        self.sender = dict(self.owner, session_id='sender')
        self.worker = {'id': 'service-id', 'name': 'service', 'mode': 'owned', 'owned': True,
                       'owner': self.owner, 'runtime': 'claude', 'home': self.tmp + '/worker',
                       'cwd': self.tmp, 'model': None, 'effort': None}

    def _submit(self, request_id='r1', **kwargs):
        from xsm import owned_requests
        return owned_requests.submit(self.owner, self.worker, kwargs.get('sender', self.sender),
                    kwargs.get('work_context', 'job'), kwargs.get('body', 'task'), request_id=request_id,
                    independent=kwargs.get('independent', False))

    def _running(self, request_id='r1'):
        from xsm import owned_requests
        self._submit(request_id)
        row = owned_requests.reserve(self.owner, request_id, 2)
        token = row['reservation']['token']
        owned_requests.acknowledge(self.owner, request_id, token)
        return owned_requests.begin(self.owner, request_id, token)

    def test_raw_body_preserved_canonical_digest_and_identity_conflicts(self):
        from xsm import owned_requests
        first = self._submit(body='caf\u00e9\r\n')
        second = self._submit(body='cafe\u0301\n')
        self.assertEqual(first['digest'], second['digest'])
        self.assertEqual(second['body'], 'caf\u00e9\r\n')
        for change in ({'body': 'different'}, {'work_context': 'different'},
                       {'sender': dict(self.sender, home='/other')}, {'independent': True}):
            with self.assertRaises(owned_requests.OwnedError):
                self._submit(**change)
        self.assertEqual(owned_requests.status(dict(self.owner, home='/other'), 'r1')['status'], 'not-found')
        self.assertEqual(owned_requests.status(self.owner, 'r1', sender=self.owner)['status'], 'refused')

    def test_atomic_reservation_context_serial_and_capacity_queue(self):
        from xsm import owned_requests
        self._submit('r1')
        self._submit('r2')
        self._submit('r3', sender=dict(self.sender, session_id='other'))
        first = owned_requests.reserve(self.owner, 'r1', 2)
        self.assertTrue(first['reservation_acquired'])
        same = owned_requests.reserve(self.owner, 'r2', 2)
        self.assertEqual(same['status'], 'queued')
        self.assertEqual(same['admission'], 'context-busy')
        other = owned_requests.reserve(self.owner, 'r3', 2)
        self.assertTrue(other['reservation_acquired'])
        self._submit('r4', work_context='third')
        full = owned_requests.reserve(self.owner, 'r4', 2)
        self.assertEqual(full['status'], 'queued')
        self.assertEqual(full['admission'], 'overloaded')
        self.assertEqual(full['capacity'], {'limit': 2, 'busy': 2, 'available': 0})
        self.assertTrue(full['persisted'])
        self.assertFalse(full['accepted'])
        self.assertEqual(owned_requests.status(self.owner, 'r4')['body'], 'task')
        self.assertFalse(owned_requests.reserve(self.owner, 'r1', 2)['reservation_acquired'])

    def test_concurrent_same_request_one_reservation(self):
        from xsm import owned_requests
        self._submit()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: owned_requests.reserve(self.owner, 'r1', 4), range(24)))
        self.assertEqual(sum(r.get('reservation_acquired', False) for r in results), 1)
        self.assertEqual(owned_requests.active_count(self.owner), 1)

    def test_result_immutable_send_retry_same_reply_and_no_extra_execution(self):
        from xsm import owned_requests
        running = self._running()
        token = running['reservation']['token']
        result = {'body': 'answer', 'outcome': 'succeeded', 'native_session_id': 'actual-native'}
        ready = owned_requests.save_result(self.owner, 'r1', token, result)
        self.assertEqual(owned_requests.active_count(self.owner), 0)
        self.assertEqual(owned_requests.save_result(self.owner, 'r1', token, result)['reply_id'], ready['reply_id'])
        with self.assertRaises(owned_requests.OwnedError):
            owned_requests.save_result(self.owner, 'r1', token, dict(result, body='changed'))
        sending = owned_requests.claim_send(self.owner, 'r1')
        self.assertTrue(sending['send_acquired'])
        self.assertFalse(owned_requests.claim_send(self.owner, 'r1')['send_acquired'])
        failed = owned_requests.finish_send(self.owner, 'r1', sending['send_token'],
                                             {'status': 'error', 'id': ready['reply_id']})
        self.assertEqual(failed['status'], 'result-ready')
        retry = owned_requests.claim_send(self.owner, 'r1')
        done = owned_requests.finish_send(self.owner, 'r1', retry['send_token'],
                                           {'status': 'sent-unconfirmed', 'id': ready['reply_id']})
        self.assertEqual(done['status'], 'sent')
        self.assertEqual(done['reply_id'], ready['reply_id'])
        self.assertEqual(done['run_attempts'], 1)
        self.assertFalse(done['side_effects_exactly_once'])

    def test_explicit_context_retirement_keeps_old_request_and_fresh_native_identity(self):
        from xsm import owned_requests
        running = self._running()
        with self.assertRaises(owned_requests.OwnedError):
            owned_requests.retire_context(self.owner, running['context_id'])
        token = running['reservation']['token']
        ready = owned_requests.save_result(self.owner, 'r1', token,
                    {'body': 'stored', 'outcome': None, 'native_session_id': 'old-native'})
        owned_requests.retire_context(self.owner, ready['context_id'])
        fresh = self._submit('r2')
        self.assertNotEqual(fresh['context_id'], ready['context_id'])
        self.assertIsNone(fresh['context']['native_session_id'])
        self.assertEqual(owned_requests.status(self.owner, 'r1')['context']['native_session_id'], 'old-native')
        self.assertEqual(owned_requests.status(self.owner, 'r1')['result']['body'], 'stored')

    def test_unknown_execution_is_not_rerun_or_idle_evicted(self):
        from xsm import owned_requests
        running = self._running()
        unknown = owned_requests.mark_unknown(self.owner, 'r1', running['reservation']['token'], 'effect uncertain')
        self.assertEqual(unknown['status'], 'unknown')
        self._submit('r2')
        blocked = owned_requests.reserve(self.owner, 'r2', 2)
        self.assertEqual(blocked['admission'], 'context-unknown')
        self.assertFalse(blocked['accepted'])
        self.assertIsNone(unknown['result'])
        with self.assertRaises(owned_requests.OwnedError):
            owned_requests.retire_context(self.owner, running['context_id'])

    def test_legacy_spawn_ticket_uses_same_budget_without_double_count(self):
        from xsm import owned_requests
        slot = owned_requests.reserve_worker_slot(self.owner, 'legacy', 1)
        self._submit()
        queued = owned_requests.reserve(self.owner, 'r1', 1,
                                        extra_busy=lambda names: 0 if 'legacy' in names else 1)
        self.assertEqual(queued['capacity']['busy'], 1)
        self.assertEqual(queued['admission'], 'overloaded')
        owned_requests.release_worker_slot(self.owner, slot)
        self.assertTrue(owned_requests.reserve(self.owner, 'r1', 1)['reservation_acquired'])

    def test_invalid_or_corrupt_state_is_never_replaced_by_empty(self):
        from xsm import owned_requests
        with self.assertRaises(owned_requests.OwnedError):
            owned_requests.submit(self.owner, dict(self.worker, mode='pane'), self.sender, 'job', 'task')
        for work in ('', None):
            with self.assertRaises(owned_requests.OwnedError):
                self._submit(work_context=work)
        self._submit()
        filename = owned_requests._path(self.owner)
        with open(filename, 'w') as stream:
            stream.write('{')
        with self.assertRaises(owned_requests.OwnedError):
            self._submit('new')
        with open(filename) as stream:
            self.assertEqual(stream.read(), '{')

    def test_work_queue_order_is_durable_sequence_not_wall_clock(self):
        from xsm import owned_requests
        with mock.patch.object(owned_requests.time, 'time', return_value=200):
            first = self._submit('first')
        with mock.patch.object(owned_requests.time, 'time', return_value=100):
            second = self._submit('second')
        self.assertLess(first['sequence'], second['sequence'])
        blocked = owned_requests.reserve(self.owner, 'second', 2)
        self.assertEqual(blocked['admission'], 'context-order')
        self.assertTrue(owned_requests.reserve(self.owner, 'first', 2)['reservation_acquired'])
