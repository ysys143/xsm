"""B05 M2 capacity recovery and synchronous submission, without model calls."""
import json
import os
import subprocess
import sys
from unittest import mock

from tests import test_xsm


class OwnedReviewFixTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, workers
        self.owner = registry.upsert('codex', self.tmp + '/owner', 'owner', os.getpid(), self.tmp, name='owner')
        for patcher in (mock.patch.object(workers, '_check_installed'),
                        mock.patch.dict(os.environ, {k: '' for _, keys in workers.FRAMEWORKS for k in keys})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.worker = workers.create_owned('claude', caller=self.owner, name='review-service',
                                            home=self.tmp + '/owned')
        self.script = self.tmp + '/fake_child.py'
        with open(self.script, 'w') as stream:
            stream.write('''
import json, os, sys
native, root = sys.argv[1:]
body = sys.stdin.read()
path = os.path.join(root, 'calls.json')
try:
    with open(path) as stream: calls = json.load(stream)
except FileNotFoundError:
    calls = {'failed': 0, 'ok': 0}
fail = body.startswith('fail')
calls['failed' if fail else 'ok'] += 1
with open(path, 'w') as stream: json.dump(calls, stream)
if fail:
    raise SystemExit(7)
print(json.dumps({'type':'result','is_error':False,'session_id':native,
                 'result':json.dumps({'body':'actual fake child answer','outcome':'succeeded'})}))
''')
        patcher = mock.patch.object(workers, '_owned_argv', side_effect=lambda worker, context:
                    [sys.executable, self.script,
                     context['native_session_id'] or context['session_seed'], self.tmp])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.replies = []

    def _reply(self, worker, request):
        self.replies.append(request['reply_id'])
        return {'id': request['reply_id'], 'status': 'sent-unconfirmed'}

    def _run(self, body, context, request_id, **kwargs):
        from xsm import workers
        return workers.run_owned('review-service', self.owner, body, work_context=context,
                                  request_id=request_id, reply_sender=self._reply, **kwargs)

    def test_max_failed_dead_children_free_slots_but_preserve_unknown_context(self):
        from xsm import owned_requests, workers
        with mock.patch.dict(os.environ, {'XSM_MAX_WORKERS': '4'}):
            failed = [self._run('fail-' + str(i), 'failed-context-' + str(i), 'failed-' + str(i))
                      for i in range(4)]
            self.assertTrue(all(r['status'] == 'unknown' and r['child']['returncode'] == 7 for r in failed))
            self.assertEqual(owned_requests.active_count(self.owner), 0)
            for row in failed:
                self.assertEqual(row['execution_state'], 'exited')
                self.assertFalse(row['slot_occupied'])
                self.assertEqual(row['context']['unknown_request'], row['id'])
                self.assertIsNone(row['result'])
            fresh = self._run('new work', 'fresh-context', 'fresh')
            self.assertEqual(fresh['status'], 'sent')
            same = self._run('do not repeat uncertain work', 'failed-context-0', 'same-context-new-id')
            self.assertEqual(same['status'], 'queued')
            self.assertEqual(same['admission'], 'context-unknown')
            again = self._run('fail-0', 'failed-context-0', 'failed-0')
            self.assertEqual(again['status'], 'unknown')
            independent = self._run('fresh independent review', 'failed-context-0', 'independent', independent=True)
            self.assertEqual(independent['status'], 'sent')
            workers.check_concurrency(self.owner)
            slot = owned_requests.reserve_worker_slot(self.owner, 'legacy-startup', 4)
            owned_requests.release_worker_slot(self.owner, slot)
            with self.assertRaises(workers.WorkerError):
                workers.stop('review-service')
        with open(self.tmp + '/calls.json') as stream:
            self.assertEqual(json.load(stream), {'failed': 4, 'ok': 2})
        self.assertEqual(len(self.replies), 2)

    def test_live_dead_and_unverified_child_are_distinct_without_clearing_unknown(self):
        from xsm import identity, owned_requests
        def running(request_id, work):
            owned_requests.submit(self.owner, self.worker, self.owner, work, 'task', request_id=request_id)
            row = owned_requests.reserve(self.owner, request_id, 4)
            token = row['reservation']['token']
            owned_requests.acknowledge(self.owner, request_id, token)
            owned_requests.begin(self.owner, request_id, token)
            return token
        missing = running('missing-child', 'missing')
        unknown = owned_requests.mark_unknown(self.owner, 'missing-child', missing, 'Popen/note gap')
        self.assertEqual(unknown['execution_state'], 'unverified')
        self.assertTrue(unknown['slot_occupied'])
        child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'], stdin=subprocess.PIPE)
        try:
            token = running('observed-child', 'observed')
            owned_requests.note_child(self.owner, 'observed-child', token, child.pid, identity.lstart(child.pid))
            live = owned_requests.mark_unknown(self.owner, 'observed-child', token, 'controller uncertain')
            self.assertEqual(live['execution_state'], 'running')
            self.assertTrue(live['slot_occupied'])
            self.assertEqual(owned_requests.active_count(self.owner), 2)
            child.kill()
            child.wait(timeout=5)
            dead = owned_requests.status(self.owner, 'observed-child')
            self.assertEqual(dead['status'], 'unknown')
            self.assertEqual(dead['execution_state'], 'exited')
            self.assertFalse(dead['slot_occupied'])
            self.assertEqual(owned_requests.active_count(self.owner), 1)
            self.assertEqual(dead['context']['unknown_request'], 'observed-child')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdin.close()

    def test_submit_stores_and_checks_content_without_reservation_model_or_recovery(self):
        from xsm import owned_requests, workers
        with mock.patch.object(workers, '_execute_owned', side_effect=AssertionError('model started')), \
                mock.patch.object(owned_requests, 'reserve', side_effect=AssertionError('slot reserved')), \
                mock.patch.object(owned_requests, 'recover', side_effect=AssertionError('not pure submission')):
            first = workers.submit_owned('review-service', self.owner, 'caf\u00e9\r\n',
                       work_context='synchronous', request_id='sync', independent=False)
            second = workers.submit_owned('review-service', self.owner, 'cafe\u0301\n',
                       work_context='synchronous', request_id='sync', independent=False)
        self.assertEqual(first['status'], 'queued')
        self.assertIsNone(first['reservation'])
        self.assertEqual(first['digest'], second['digest'])
        self.assertEqual(second['body'], 'caf\u00e9\r\n')
        completed = self._run('cafe\u0301\n', 'synchronous', 'sync')
        self.assertEqual(completed['status'], 'sent')
        with self.assertRaises(owned_requests.OwnedError):
            workers.submit_owned('review-service', self.owner, 'different body',
                                 work_context='synchronous', request_id='sync', independent=False)
        with mock.patch.object(workers, 'submit_owned', wraps=workers.submit_owned) as submit:
            self._run('cafe\u0301\n', 'synchronous', 'sync')
            submit.assert_called_once()
        with open(self.tmp + '/calls.json') as stream:
            self.assertEqual(json.load(stream), {'failed': 0, 'ok': 1})
        previous_worker_id = self.worker['id']
        workers.stop('review-service')
        recreated = workers.create_owned('claude', caller=self.owner, name='review-service',
                                           home=self.tmp + '/owned')
        self.assertNotEqual(recreated['id'], previous_worker_id)
        with self.assertRaises(owned_requests.OwnedError):
            workers.submit_owned('review-service', self.owner, 'cafe\u0301\n',
                                 work_context='synchronous', request_id='sync', independent=False)
