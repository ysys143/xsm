"""Durable cancellation intent versus native process birth; no runtime/model stubs claimed native."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest import mock
from tests.test_xsm import TempState


class OwnedCancellationTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import workers
        self.owner = dict(runtime='codex', home=self.tmp + '/owner', session_id='owner', cwd=self.tmp)
        self.worker = dict(id='a' * 32, name='service', mode='owned', owned=True, owner=self.owner,
                           runtime='claude', home=self.tmp + '/worker', cwd=self.tmp)
        workers.save(self.worker)
        patcher = mock.patch.dict(os.environ, {key: '' for _, keys in workers.FRAMEWORKS for key in keys})
        patcher.start(); self.addCleanup(patcher.stop)

    def submit(self):
        from xsm import owned_requests
        return owned_requests.submit(self.owner, self.worker, self.owner, 'work', 'body', request_id='request')

    def running(self):
        from xsm import owned_requests
        self.submit(); row = owned_requests.reserve(self.owner, 'request', 1)
        token = row['reservation']['token']
        owned_requests.acknowledge(self.owner, 'request', token)
        return owned_requests.begin(self.owner, 'request', token)

    def cancel(self):
        from xsm import owned_requests
        return owned_requests.request_cancellation(self.owner, 'request', self.owner, self.worker['id'])

    def command(self, row):
        code = ('import sys,json;sys.stdin.read();print(json.dumps(' + repr(dict(
            type='result', subtype='success', session_id=row['context']['session_seed'], result='fixture answer')) + '))')
        return [sys.executable, '-B', '-c', code]

    def test_queued_cancel_is_durable_unaccepted_and_cannot_reserve_or_replay(self):
        from xsm import owned_requests
        self.submit(); cancelled = self.cancel()
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertFalse(cancelled['accepted'])
        self.assertFalse(cancelled['slot_occupied'])
        self.assertFalse(owned_requests.reserve(self.owner, 'request', 1)['reservation_acquired'])
        self.assertEqual(self.submit()['status'], 'cancelled')
        self.assertEqual(self.cancel()['cancellation'], cancelled['cancellation'])

    def test_sender_and_service_identity_are_required_before_recording_intent(self):
        from xsm import owned_requests
        self.submit()
        for sender, worker_id in ((dict(self.owner, home=self.tmp + '/other'), self.worker['id']),
                                  (self.owner, 'another-service')):
            with self.assertRaises(owned_requests.OwnedError):
                owned_requests.request_cancellation(self.owner, 'request', sender, worker_id)
        self.assertNotIn('cancellation', owned_requests.status(self.owner, 'request'))

    def test_cancel_after_ack_is_not_requeued_or_relabelled_unknown(self):
        from xsm import workers
        calls = []
        result = workers.run_owned('service', self.owner, 'body', work_context='work', request_id='request',
            checkpoint=lambda stage, row: self.cancel() if stage == 'acknowledged' else None,
            executor=lambda *args: calls.append(True))
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(calls, [])

    def test_running_intent_is_not_a_stop_claim_and_prevents_actual_process_birth(self):
        from xsm import workers, owned_requests
        row = self.running()
        pending = self.cancel()
        self.assertEqual(pending['status'], 'running')
        self.assertEqual(pending['cancellation']['native_state'], 'unverified')
        with mock.patch.object(workers, '_owned_argv', return_value=self.command(row)), \
                mock.patch.object(workers.subprocess, 'Popen', side_effect=AssertionError('must not create child')):
            with self.assertRaises(workers.OwnedLaunchError):
                workers._execute_owned(self.worker, row['context'], 'body', row)
        saved = owned_requests.status(self.owner, 'request')
        self.assertEqual(saved['status'], 'cancelled')
        self.assertEqual(saved['cancellation']['native_state'], 'not-started')

    def test_cancellation_cannot_pass_between_actual_spawn_and_durable_child_record(self):
        from xsm import workers
        row = self.running(); original = subprocess.Popen
        spawned, release, attempting = threading.Event(), threading.Event(), threading.Event()
        children = []
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs)
            if args[0][0] != sys.executable:
                return child
            children.append(child); spawned.set()
            if not release.wait(3): raise RuntimeError('test launch release deadline')
            return child
        def cancel():
            attempting.set(); return self.cancel()
        with mock.patch.object(workers, '_owned_argv', return_value=self.command(row)), \
                mock.patch.object(workers.subprocess, 'Popen', side_effect=spawn), \
                concurrent.futures.ThreadPoolExecutor(2) as pool:
            execution = pool.submit(workers._execute_owned, self.worker, row['context'], 'body', row)
            try:
                self.assertTrue(spawned.wait(3))
                cancellation = pool.submit(cancel); self.assertTrue(attempting.wait(3))
                self.assertFalse(cancellation.done())
            finally: release.set()
            saved = cancellation.result(5); answer = execution.result(5)
        self.assertEqual(saved['child']['pid'], children[0].pid)
        self.assertEqual(saved['cancellation']['status'], 'requested')
        self.assertEqual(saved['cancellation']['native_state'], 'unverified')
        self.assertEqual(answer['body'], 'fixture answer')
        self.assertIsNotNone(children[0].poll())

    def test_birth_record_write_failure_stops_the_new_child_and_remains_unknown(self):
        from xsm import workers, owned_requests
        original_spawn, original_write = subprocess.Popen, owned_requests.handoff._write
        children, failures = [], []
        def spawn(*args, **kwargs):
            child = original_spawn(*args, **kwargs)
            if args[0][0] == sys.executable: children.append(child)
            return child
        def write(path, value):
            row = value.get('requests', {}).get('request', {})
            if row.get('child') and not failures:
                failures.append(True); raise OSError('explicit child-record write failure')
            return original_write(path, value)
        with mock.patch.object(workers, '_owned_argv', side_effect=lambda worker, context: self.command({'context': context})), \
                mock.patch.object(workers.subprocess, 'Popen', side_effect=spawn), \
                mock.patch.object(owned_requests.handoff, '_write', side_effect=write):
            result = workers.run_owned('service', self.owner, 'body', work_context='work', request_id='request')
        self.assertEqual(failures, [True])
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNotNone(children[0].poll())
        with mock.patch.object(workers, '_execute_owned', side_effect=AssertionError('must not rerun')):
            self.assertEqual(workers.run_owned('service', self.owner, 'body', work_context='work',
                                              request_id='request')['status'], 'unknown')

    def test_cancellation_after_birth_refuses_native_model_binding(self):
        from xsm import owned_requests, identity
        row = self.running()
        child = subprocess.Popen([sys.executable, '-B', '-c', 'import sys;sys.stdin.read()'], stdin=subprocess.PIPE)
        try:
            owned_requests.note_child(self.owner, 'request', row['reservation']['token'],
                                      child.pid, identity.lstart(child.pid))
            self.cancel()
            with self.assertRaisesRegex(owned_requests.OwnedError, 'cancellation requested'):
                owned_requests.bind_native_context(self.owner, 'request', row['reservation']['token'], 'observed-native')
        finally:
            child.stdin.close(); child.wait(timeout=3)
