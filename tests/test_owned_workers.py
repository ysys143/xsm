"""Real owned service lifecycle with fake model/reply boundaries, no LLM costs."""
import concurrent.futures
import json
import os
import sys
import threading
from unittest import mock

from tests import test_xsm


class OwnedWorkerTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, workers
        self.a = registry.upsert('codex', self.tmp + '/home', 'a', os.getpid(), self.tmp, name='a')
        self.b = registry.upsert('codex', self.tmp + '/home', 'b', os.getpid(), self.tmp, name='b')
        for patcher in (mock.patch.object(workers, '_check_installed'),
                        mock.patch.dict(os.environ, {k: '' for _, keys in workers.FRAMEWORKS for k in keys})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.worker = workers.create_owned('claude', caller=self.a, name='service', home=self.tmp + '/owned')
        self.calls, self.effects, self.replies = [], [], []
        self.memory = {}
        self.mutex = threading.Lock()

    def _execute(self, worker, context, body, request):
        native_id = context['native_session_id'] or context['session_seed']
        with self.mutex:
            self.calls.append((request['id'], native_id))
            self.effects.append(request['id'])
            previous = list(self.memory.get(native_id, []))
            self.memory.setdefault(native_id, []).append(body)
        return {'body': json.dumps(previous + [body]), 'outcome': 'succeeded',
                'native_session_id': native_id}

    def _reply(self, worker, request):
        with self.mutex:
            self.replies.append((request['id'], request['reply_id'], request['result']['body']))
        return {'status': 'sent-unconfirmed', 'id': request['reply_id']}

    def _run(self, body='task', sender=None, context='job', request_id='r1', **kwargs):
        from xsm import workers
        return workers.run_owned('service', sender or self.a, body, work_context=context,
                    request_id=request_id, executor=kwargs.pop('executor', self._execute),
                    reply_sender=kwargs.pop('reply_sender', self._reply), **kwargs)

    def test_same_sender_work_resumes_two_senders_jobs_and_review_stay_isolated(self):
        first = self._run('remember red')
        follow = self._run('recall', request_id='r2')
        other = self._run('remember blue', sender=self.b, request_id='r3')
        work = self._run('another work', context='other-job', request_id='r4')
        review = self._run('independent review', request_id='r5', independent=True)
        self.assertEqual(first['context']['native_session_id'], follow['context']['native_session_id'])
        self.assertIn('remember red', follow['result']['body'])
        self.assertNotIn('remember red', other['result']['body'])
        self.assertEqual(len({first['context_id'], other['context_id'], work['context_id'], review['context_id']}), 4)
        self.assertEqual(len(self.calls), 5)

    def test_failed_reply_reuses_saved_answer_and_same_reply_id_after_plan_change(self):
        from xsm import workers
        def fail(worker, request):
            self._reply(worker, request)
            raise OSError('reply link unavailable')
        pending = self._run(reply_sender=fail)
        self.assertEqual(pending['status'], 'result-ready')
        worker = workers.load('service')
        worker['model'] = 'changed-only-for-next-request'
        workers.save(worker)
        recovered = workers.resend_owned('service', self.a, 'r1', reply_sender=self._reply)
        self.assertEqual(recovered['status'], 'sent')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.effects, ['r1'])
        self.assertEqual(self.replies[0][1:], self.replies[1][1:])
        self.assertEqual(recovered['reply_id'], pending['reply_id'])

    def test_same_context_serial_other_context_parallel_capacity_plus_one_queued(self):
        entered = [threading.Event(), threading.Event()]
        finish = threading.Event()
        def blocked(worker, context, body, request):
            entered[0 if request['id'] == 'r1' else 1].set()
            if not finish.wait(5):
                raise AssertionError('test run not released')
            return self._execute(worker, context, body, request)
        with mock.patch.dict(os.environ, {'XSM_MAX_WORKERS': '2'}), \
                concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self._run, executor=blocked)
            self.assertTrue(entered[0].wait(5))
            serial = self._run('follow', request_id='same-context')
            self.assertEqual(serial['status'], 'queued')
            self.assertEqual(serial['admission'], 'context-busy')
            second = pool.submit(self._run, sender=self.b, request_id='r2', executor=blocked)
            try:
                self.assertTrue(entered[1].wait(5))
                extra = self._run('third', context='third', request_id='r3')
                self.assertEqual(extra['status'], 'queued')
                self.assertEqual(extra['admission'], 'overloaded')
                self.assertEqual(extra['capacity'], {'limit': 2, 'busy': 2, 'available': 0})
                self.assertTrue(extra['persisted'])
                self.assertFalse(extra['accepted'])
            finally:
                finish.set()
            self.assertEqual(first.result(timeout=5)['status'], 'sent')
            self.assertEqual(second.result(timeout=5)['status'], 'sent')
        resumed = self._run('third', context='third', request_id='r3')
        self.assertEqual(resumed['status'], 'sent')
        self.assertEqual(len(self.calls), 3)

    def test_duplicate_request_concurrency_has_one_model_call(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(lambda _: self._run(), range(12)))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(any(r['status'] == 'sent' for r in rows))
        self.assertEqual(len(self.replies), 1)

    def test_existing_general_session_is_not_converted_and_framework_refusal_stays(self):
        from xsm import workers
        workers.save({'name': 'ordinary', 'mode': 'pane', 'runtime': 'claude', 'session_id': 'user-native'})
        with self.assertRaises(workers.WorkerError):
            workers.run_owned('ordinary', self.a, 'task', work_context='job')
        with mock.patch.dict(os.environ, {'ORCA_TERMINAL_HANDLE': 'framework-owned'}):
            with self.assertRaises(workers.WorkerError):
                workers.create_owned('claude', caller=self.a, name='not-created')
            with self.assertRaises(workers.WorkerError):
                self._run()
        self.assertEqual(self.calls, [])
        self.assertEqual(workers.load('ordinary')['session_id'], 'user-native')

    def test_unknown_execution_does_not_auto_repeat_side_effect_or_report_success(self):
        from xsm import workers
        def uncertain(worker, context, body, request):
            self.effects.append(request['id'])
            raise RuntimeError('effect happened; result missing')
        row = self._run(executor=uncertain)
        self.assertEqual(row['status'], 'unknown')
        self.assertIsNone(row['result'])
        retry = self._run()
        self.assertEqual(retry['status'], 'unknown')
        self.assertEqual(self.effects, ['r1'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.replies, [])
        with self.assertRaises(workers.WorkerError):
            workers.stop('service')

    def test_native_id_cannot_be_an_ordinary_session_and_error_text_is_not_answer(self):
        from xsm import workers
        def wrong(worker, context, body, request):
            return {'body': 'pretend', 'native_session_id': self.a['session_id'], 'outcome': 'succeeded'}
        row = self._run(executor=wrong)
        self.assertEqual(row['status'], 'unknown')
        self.assertIsNone(row['result'])
        self.assertEqual(self.replies, [])
        launch = self._run(request_id='launch', context='other',
                           executor=lambda *a: (_ for _ in ()).throw(workers.OwnedLaunchError('not started')))
        self.assertEqual(launch['status'], 'error')
        self.assertIsNone(launch['result'])
        self.assertEqual(self.replies, [])

    def test_idle_context_retirement_fresh_session_and_worker_removal_keeps_journal(self):
        from xsm import owned_requests, workers
        original = self._run('remember')
        workers.retire_owned_context('service', self.a, original['context_id'])
        fresh = self._run('new memory', request_id='new')
        self.assertNotEqual(fresh['context_id'], original['context_id'])
        self.assertNotIn('remember', fresh['result']['body'])
        self.assertEqual(owned_requests.status(self.a, 'r1')['result'], original['result'])
        workers.stop('service')
        self.assertIsNone(workers.load('service'))
        self.assertEqual(owned_requests.status(self.a, 'r1')['result'], original['result'])

    def test_native_baseline_flags_and_permission_errors_not_corrected_silently(self):
        from xsm import workers
        context = {'native_session_id': None, 'session_seed': '12345678-1234-4234-8234-123456789abc'}
        argv = workers._owned_argv(self.worker, context)
        self.assertIn('--session-id', argv)
        self.assertNotIn('--allowedTools', argv)
        self.assertNotIn('--dangerously-skip-permissions', argv)
        with self.assertRaises(workers.WorkerError):
            workers._owned_native_result(self.worker, context, json.dumps({
                'type': 'result', 'is_error': True, 'result': 'cannot use tool',
                'session_id': '12345678-1234-4234-8234-123456789abc',
                'permission_denials': [{'tool_name': 'Read'}]}))
        with self.assertRaises(workers.WorkerError):
            workers._owned_native_result(dict(self.worker, runtime='codex'), context,
                '{"type":"thread.started","thread_id":"x"}\n{"type":"turn.failed"}')

    def test_controller_cancel_releases_pre_run_and_preserves_post_run_result(self):
        from xsm import owned_requests, workers
        def cancel_ack(stage, request):
            if stage == 'acknowledged':
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self._run(checkpoint=cancel_ack)
        self.assertEqual(owned_requests.status(self.a, 'r1')['status'], 'queued')
        self.assertEqual(self.calls, [])
        self.assertEqual(self._run()['status'], 'sent')
        def cancel_publish(stage, request):
            if stage == 'reply-sent':
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self._run('second', context='second', request_id='r2', checkpoint=cancel_publish)
        pending = owned_requests.status(self.a, 'r2')
        self.assertEqual(pending['status'], 'result-ready')
        self.assertEqual(pending['send_evidence']['status'], 'unknown')
        calls_before = len(self.calls)
        resumed = workers.resend_owned('service', self.a, 'r2', reply_sender=self._reply)
        self.assertEqual(resumed['status'], 'sent')
        self.assertEqual(len(self.calls), calls_before)
        self.assertEqual(self.replies[-1][1], self.replies[-2][1])

    def test_execution_interrupt_in_live_controller_is_unknown_not_permanently_running(self):
        from xsm import owned_requests
        def interrupt(stage, request):
            if stage == 'after-execution':
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self._run(checkpoint=interrupt)
        request = owned_requests.status(self.a, 'r1')
        self.assertEqual(request['status'], 'unknown')
        self.assertIsNone(request['result'])
        self.assertEqual(self._run()['status'], 'unknown')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.effects, ['r1'])

    def test_lost_auto_id_after_cancel_is_listed_only_for_original_native_sender(self):
        from xsm import owned_requests, workers
        def cancel(stage, request):
            if stage == 'acknowledged':
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            workers.run_owned('service', self.a, 'auto-id private task', work_context='auto',
                               executor=self._execute, reply_sender=self._reply, checkpoint=cancel)
        with open(owned_requests._path(self.a), 'rb') as stream:
            before = stream.read()
        rows = workers.list_owned('service', self.a)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'queued')
        self.assertNotIn('result', rows[0])
        self.assertEqual(workers.list_owned('service', self.b), [])
        self.assertEqual(workers.list_owned('service', dict(self.a, home='/other-home')), [])
        with open(owned_requests._path(self.a), 'rb') as stream:
            self.assertEqual(stream.read(), before)
        self.assertEqual(self.calls, [])
        resumed = self._run('auto-id private task', context='auto', request_id=rows[0]['id'])
        self.assertEqual(resumed['status'], 'sent')
        self.assertEqual(len(self.calls), 1)

    def test_parallel_publications_keep_both_owned_native_identities(self):
        from xsm import identity, send, workers
        barrier = threading.Barrier(2)
        original_save = workers.save
        start = identity.lstart(os.getpid())
        def delayed_save(record):
            if (record.get('mode') == 'owned' and len(record.get('owned_sessions', [])) == 1
                    and threading.current_thread().name.startswith('publish-race')):
                try:
                    barrier.wait(timeout=0.5)
                except threading.BrokenBarrierError:
                    pass
            return original_save(record)
        def model(worker, context, body, request):
            result = self._execute(worker, context, body, request)
            result['execution'] = {'pid': os.getpid(), 'lstart': start, 'provider': 'fake-only'}
            return result
        def queued(spec, body, **kwargs):
            return send.SendResult('sent-unconfirmed', msg_id=kwargs['msg_id'])
        with mock.patch.object(workers, 'save', side_effect=delayed_save), \
                mock.patch.object(send, 'send', side_effect=queued), \
                concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='publish-race') as pool:
            first = pool.submit(self._run, executor=model, reply_sender=workers.publish_owned)
            second = pool.submit(self._run, sender=self.b, request_id='r2', context='second',
                                 executor=model, reply_sender=workers.publish_owned)
            results = [first.result(timeout=10), second.result(timeout=10)]
        self.assertTrue(all(r['status'] == 'sent' for r in results),
                        [r.get('send_evidence') for r in results])
        native_ids = {r['result']['native_session_id'] for r in results}
        self.assertEqual(set(workers.load('service')['owned_sessions']), native_ids)
