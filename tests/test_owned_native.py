"""Default runner/publisher with a real fake CLI process, never a model API."""
import json
import os
import sys
from unittest import mock

from tests import test_xsm


class OwnedNativeTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, workers
        self.owner = registry.upsert('codex', self.tmp + '/owner', 'ordinary-owner',
                                     os.getpid(), self.tmp, name='ordinary-owner')
        self.script = self.tmp + '/fake_native.py'
        with open(self.script, 'w') as stream:
            stream.write('''
import json, os, sys
native_id, root = sys.argv[1:]
prompt = sys.stdin.read()
filename = os.path.join(root, 'native-memory.json')
try:
    with open(filename) as stream:
        state = json.load(stream)
except FileNotFoundError:
    state = {'calls': 0, 'memory': {}}
state['calls'] += 1
if prompt.startswith('remember:'):
    state['memory'][native_id] = prompt.split(':', 1)[1]
body = state['memory'].get(native_id, 'no prior memory')
with open(filename, 'w') as stream:
    json.dump(state, stream)
print(json.dumps({'type': 'result', 'is_error': False,
      'result': json.dumps({'body': body, 'outcome': 'succeeded'}), 'session_id': native_id,
      'billing_keys_present': any(k in os.environ for k in
          ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY'))}))
''')
        for patcher in (mock.patch.object(workers, '_check_installed'),
                        mock.patch.dict(os.environ, {k: '' for _, keys in workers.FRAMEWORKS for k in keys})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.worker = workers.create_owned('claude', caller=self.owner, name='native-service',
                                            home=self.tmp + '/owned')
        patcher = mock.patch.object(workers, '_owned_argv', side_effect=lambda worker, context:
                    [sys.executable, self.script,
                     context['native_session_id'] or context['session_seed'], self.tmp])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_real_process_runner_memory_identity_and_default_reply_sender(self):
        from xsm import registry, send, workers
        published = []
        def queue(spec, body, **kwargs):
            published.append((spec, body, kwargs))
            return send.SendResult('sent-unconfirmed', msg_id=kwargs['msg_id'])
        with mock.patch.object(send, 'send', side_effect=queue):
            first = workers.run_owned('native-service', self.owner, 'remember:secret-a',
                                       work_context='job-a', request_id='r1')
            follow = workers.run_owned('native-service', self.owner, 'recall',
                                        work_context='job-a', request_id='r2')
            separate = workers.run_owned('native-service', self.owner, 'recall',
                                          work_context='job-b', request_id='r3')
        self.assertEqual(first['status'], 'sent')
        self.assertEqual(follow['result']['body'], 'secret-a')
        self.assertEqual(separate['result']['body'], 'no prior memory')
        self.assertEqual(first['result']['native_session_id'], follow['result']['native_session_id'])
        self.assertNotEqual(first['result']['native_session_id'], self.owner['session_id'])
        self.assertEqual(len(published), 3)
        native_id = first['result']['native_session_id']
        self.assertEqual(published[0][2]['sender']['session_id'], native_id)
        self.assertEqual(published[0][2]['reply_to'], 'r1')
        self.assertEqual(published[0][2]['outcome'], 'succeeded')
        self.assertEqual(workers.for_session(native_id)['id'], self.worker['id'])
        owned_pointer = registry.by_session('claude', native_id)
        self.assertEqual(owned_pointer['state'], 'ended')
        self.assertNotIn('ended_at', registry.by_session('codex', self.owner['session_id']))
        workers.stop('native-service')
        self.assertNotIn('ended_at', registry.by_session('codex', self.owner['session_id']))

    def test_subscription_child_does_not_inherit_api_billing_keys_or_parent_native_id(self):
        from xsm import workers
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'dummy', 'OPENAI_API_KEY': 'dummy',
                                          'CODEX_API_KEY': 'dummy', 'CODEX_THREAD_ID': 'parent'}):
            row = workers.run_owned('native-service', self.owner, 'recall', work_context='job',
                request_id='r1', reply_sender=lambda worker, request:
                    {'id': request['reply_id'], 'status': 'sent-unconfirmed'})
        self.assertEqual(row['status'], 'sent')
        with open(row['result']['execution']['stdout']) as stream:
            output = json.load(stream)
        self.assertFalse(output['billing_keys_present'])
        self.assertNotEqual(row['result']['native_session_id'], self.owner['session_id'])
        self.assertTrue(row['result']['execution']['pid'])
        self.assertTrue(row['result']['execution']['lstart'])

    def test_unknown_after_native_result_is_reconciled_from_log_without_model_rerun(self):
        from xsm import workers
        def crash_before_journal(stage, request):
            if stage == 'after-execution':
                raise RuntimeError('controller lost after native output')
        def reply(worker, request):
            return {'id': request['reply_id'], 'status': 'sent-unconfirmed'}
        first = workers.run_owned('native-service', self.owner, 'remember:from-native-output',
                  work_context='job', request_id='r1', reply_sender=reply, checkpoint=crash_before_journal)
        self.assertEqual(first['status'], 'unknown')
        self.assertIsNone(first['result'])
        row = workers.reconcile_owned('native-service', self.owner, 'r1', reply_sender=reply)
        self.assertEqual(row['status'], 'sent')
        self.assertEqual(row['result']['body'], 'from-native-output')
        self.assertEqual(row['result']['execution']['recovered_from'], 'completed-native-output')
        self.assertEqual(row['result']['execution']['returncode'], 0)
        with open(self.tmp + '/native-memory.json') as stream:
            self.assertEqual(json.load(stream)['calls'], 1)

    def test_actual_owned_identity_can_publish_quietly_without_native_queue(self):
        from xsm import adapters, handoff, registry, workers
        with mock.patch.object(adapters, 'to_codex', side_effect=AssertionError('native queue forbidden')), \
                mock.patch.object(adapters, 'to_claude', side_effect=AssertionError('native socket forbidden')):
            row = workers.run_owned('native-service', self.owner, 'remember:quiet-answer',
                    work_context='quiet', request_id='quiet-request',
                    reply_sender=lambda worker, request: workers.publish_owned(worker, request, wake=False))
            self.assertEqual(row['status'], 'reply-stored', row.get('send_evidence'))
            self.assertEqual(row['send_evidence']['status'], 'stored')
            stored = handoff.status(self.owner, row['reply_id'])
            self.assertEqual(stored['message']['body'], 'quiet-answer')
            self.assertEqual(stored['message']['sender']['session_id'], row['result']['native_session_id'])
            self.assertNotEqual(stored['message']['sender']['session_id'], self.owner['session_id'])
            repeated = workers.run_owned('native-service', self.owner, 'remember:quiet-answer',
                    work_context='quiet', request_id='quiet-request',
                    reply_sender=lambda *args: (_ for _ in ()).throw(AssertionError('already persisted')))
            self.assertEqual(repeated['reply_id'], row['reply_id'])
            self.assertEqual(repeated['status'], 'reply-stored')
        with open(self.tmp + '/native-memory.json') as stream:
            self.assertEqual(json.load(stream)['calls'], 1)

    def test_publisher_rejects_forged_result_before_touching_an_ordinary_pointer(self):
        import copy
        from xsm import owned_requests, registry, workers
        row = workers.run_owned('native-service', self.owner, 'remember:real-result',
                work_context='job', request_id='r1', reply_sender=lambda worker, request:
                    {'id': request['reply_id'], 'status': 'error'})
        self.assertEqual(row['status'], 'result-ready')
        sending = owned_requests.claim_send(self.owner, 'r1')
        forged = copy.deepcopy(sending)
        forged['result']['native_session_id'] = self.owner['session_id']
        forged['result']['execution']['pid'] = self.owner['pid']
        forged['result']['execution']['lstart'] = self.owner['lstart']
        with self.assertRaises(workers.WorkerError):
            workers.publish_owned(self.worker, forged, wake=False)
        self.assertNotIn('ended_at', registry.by_session('codex', self.owner['session_id']))

    def test_background_reply_scope_revocation_refuses_without_consent_offer(self):
        from xsm import config, connect, workers
        with mock.patch.object(connect, 'offer', side_effect=AssertionError('must not widen scope')):
            with mock.patch.object(config, 'scope_for', return_value=(None, 'scope revoked')):
                row = workers.run_owned('native-service', self.owner, 'remember:keep result',
                          work_context='scope', request_id='scope-request',
                          reply_sender=lambda worker, request: workers.publish_owned(worker, request, wake=False))
            self.assertEqual(row['status'], 'result-ready')
            self.assertEqual(row['send_evidence']['status'], 'refused')
            self.assertIn('no connection offered', row['send_evidence']['reason'])
            recovered = workers.resend_owned('native-service', self.owner, 'scope-request',
                          reply_sender=lambda worker, request: workers.publish_owned(worker, request, wake=False))
            self.assertEqual(recovered['status'], 'reply-stored')
            self.assertEqual(recovered['reply_id'], row['reply_id'])
        with open(self.tmp + '/native-memory.json') as stream:
            self.assertEqual(json.load(stream)['calls'], 1)

    def test_scope_revoked_between_guard_and_dispatch_never_offers_connection(self):
        from xsm import adapters, config, connect, workers
        with mock.patch.object(connect, 'offer', side_effect=AssertionError('consent globals touched')), \
                mock.patch.object(adapters, 'to_codex', side_effect=AssertionError('queue forbidden')), \
                mock.patch.object(config, 'scope_for', side_effect=[('temporary-scope', 'allowed'),
                                                                  (None, 'revoked during publication')]):
            row = workers.run_owned('native-service', self.owner, 'recall', work_context='race',
                                      request_id='race-request')
        self.assertEqual(row['status'], 'result-ready')
        self.assertEqual(row['send_evidence']['status'], 'refused')
        self.assertIsNotNone(row['result'])

    def test_known_failed_exit_cannot_be_reconciled_as_successful_completed_output(self):
        from xsm import workers
        script = self.tmp + '/failed_codex.py'
        with open(script, 'w') as stream:
            stream.write('''
import json, sys
sys.stdin.read()
print(json.dumps({'type':'thread.started','thread_id':sys.argv[1]}))
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'must not publish'}}))
print(json.dumps({'type':'turn.completed'}))
sys.exit(7)
''')
        worker = workers.create_owned('codex', caller=self.owner, name='failed-exit', home=self.tmp + '/failed')
        with mock.patch.object(workers, '_owned_argv', side_effect=lambda worker, context:
                [sys.executable, script, context['session_seed']]):
            result = workers.run_owned('failed-exit', self.owner, 'task', work_context='exit',
                    request_id='exit-request', reply_sender=lambda *args:
                    (_ for _ in ()).throw(AssertionError('must not publish failed CLI output')))
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['child']['returncode'], 7)
        recovered = workers.reconcile_owned('failed-exit', self.owner, 'exit-request',
                    reply_sender=lambda *args: (_ for _ in ()).throw(AssertionError('failed exit')))
        self.assertEqual(recovered['status'], 'unknown')
        self.assertIsNone(recovered['result'])
        readback = mock.Mock(side_effect=AssertionError('failed native exit is not a result'))
        again = workers.reconcile_owned('failed-exit', self.owner, 'exit-request', readback=readback)
        self.assertEqual(again['status'], 'unknown')
        readback.assert_not_called()
