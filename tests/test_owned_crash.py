"""Real process death at five owned lifecycle cuts; no subscribed model runs."""
import json
import os
import signal
import subprocess
import sys
from unittest import mock

from tests import test_xsm


class OwnedCrashTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, workers
        self.owner = registry.upsert('codex', self.tmp + '/owner-home', 'owner',
                                     os.getpid(), self.tmp, name='owner')
        with mock.patch.object(workers, '_check_installed'), \
                mock.patch.dict(os.environ, {k: '' for _, keys in workers.FRAMEWORKS for k in keys}):
            self.worker = workers.create_owned('claude', caller=self.owner, name='crash-service',
                                                home=self.tmp + '/owned-home')
        self.script = '''
import json, os, signal
from xsm import handoff, paths, workers
fixture = json.loads(os.environ['OWNED_CRASH_FIXTURE'])
owner, cut = fixture['owner'], fixture['cut']
filename = paths.path('fake-evidence.json')
def evidence():
    return paths.read_json(filename, {'models': 0, 'effects': 0, 'replies': 0, 'reply_ids': []})
def execute(worker, context, body, request):
    row = evidence()
    row['models'] += 1
    row['effects'] += 1
    result = {'body': 'effect result', 'outcome': 'succeeded',
              'native_session_id': context['native_session_id'] or context['session_seed']}
    row['result'] = result
    handoff._write(filename, row)
    return result
def reply(worker, request):
    row = evidence()
    row['replies'] += 1
    row['reply_ids'].append(request['reply_id'])
    handoff._write(filename, row)
    return {'id': request['reply_id'], 'status': 'sent-unconfirmed'}
def checkpoint(stage, request):
    if stage == cut:
        with open(paths.path('cut-reached'), 'w') as stream:
            stream.write(stage)
        os.kill(os.getpid(), signal.SIGKILL)
if fixture.get('readback'):
    result = workers.reconcile_owned('crash-service', owner, 'crash-request',
                lambda request: evidence()['result'], reply_sender=reply)
else:
    result = workers.run_owned('crash-service', owner, 'cause one effect', work_context='one-job',
                request_id='crash-request', executor=execute, reply_sender=reply, checkpoint=checkpoint)
print(json.dumps(result))
'''

    def _invoke(self, cut=None, readback=False):
        env = os.environ.copy()
        env['XSM_HOME'] = self.tmp
        env['OWNED_CRASH_FIXTURE'] = json.dumps({'owner': self.owner, 'cut': cut, 'readback': readback})
        for key in list(env):
            if key.startswith(('ORCA_', 'HERDR_')):
                env.pop(key)
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run([sys.executable, '-c', self.script], env=env, cwd=repo,
                               capture_output=True, text=True, timeout=15)

    def _assert_cut(self, cut):
        from xsm import owned_requests, paths
        killed = self._invoke(cut)
        self.assertEqual(killed.returncode, -signal.SIGKILL, killed.stderr)
        with open(paths.path('cut-reached')) as stream:
            self.assertEqual(stream.read(), cut)
        before = owned_requests.status(self.owner, 'crash-request')
        self.assertTrue(before['persisted'])
        self.assertEqual(before['body'], 'cause one effect')
        restored = owned_requests.recover(self.owner)[0]
        counters = paths.read_json(paths.path('fake-evidence.json'),
                                     {'models': 0, 'effects': 0, 'replies': 0, 'reply_ids': []})
        if cut == 'after-execution':
            self.assertEqual(restored['status'], 'unknown')
            self.assertIsNone(restored['result'])
            retried = self._invoke()
            self.assertEqual(retried.returncode, 0, retried.stderr)
            self.assertEqual(json.loads(retried.stdout)['status'], 'unknown')
            unchanged = paths.read_json(paths.path('fake-evidence.json'))
            self.assertEqual((unchanged['models'], unchanged['effects'], unchanged['replies']), (1, 1, 0))
            finished = self._invoke(readback=True)
        else:
            self.assertEqual(restored['status'], 'queued' if cut in ('request-stored', 'acknowledged')
                              else 'result-ready')
            finished = self._invoke()
        self.assertEqual(finished.returncode, 0, finished.stderr)
        result = json.loads(finished.stdout)
        self.assertEqual(result['status'], 'sent')
        self.assertFalse(result['side_effects_exactly_once'])
        final = paths.read_json(paths.path('fake-evidence.json'))
        self.assertEqual((final['models'], final['effects']), (1, 1))
        self.assertEqual(final['replies'], 2 if cut == 'reply-sent' else 1)
        self.assertEqual(len(set(final['reply_ids'])), 1)
        if cut in ('result-stored', 'reply-sent'):
            self.assertEqual(before['reply_id'], result['reply_id'])
        after = self._invoke()
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(paths.read_json(paths.path('fake-evidence.json')), final)

    def test_kill_after_request_store_before_ack(self):
        self._assert_cut('request-stored')

    def test_kill_after_ack_before_execution(self):
        self._assert_cut('acknowledged')

    def test_kill_after_effect_before_result_journal_requires_readback(self):
        self._assert_cut('after-execution')

    def test_kill_after_result_store_resends_without_model(self):
        self._assert_cut('result-stored')

    def test_kill_after_reply_before_commit_reuses_exact_reply_id(self):
        self._assert_cut('reply-sent')
