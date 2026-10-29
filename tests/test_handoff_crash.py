"""Real SIGKILL at durable store/claim/ack and pre-replace boundaries."""
import json
import os
import signal
import subprocess
import sys

from tests import test_xsm


class HandoffCrashTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        self.receiver = {'runtime': 'codex', 'home': self.tmp + '/codex', 'session_id': 'r'}
        self.sender = {'runtime': 'claude', 'home': self.tmp + '/claude', 'session_id': 's'}
        self.message = {'id': 'm1', 'sender': self.sender, 'body': 'durable work', 'kind': 'task'}
        self.owner = {'type': 'native', 'id': 'crash-reader'}

    def _killed(self, action, boundary, token=None):
        marker = os.path.join(self.tmp, 'reached-' + boundary)
        script = '''
import json, os, signal
from xsm import handoff, paths
receiver, message, owner, token, marker, action, boundary = json.loads(os.environ['HANDOFF_FIXTURE'])
def kill():
    with open(marker, 'w') as stream:
        stream.write('boundary reached')
    os.kill(os.getpid(), signal.SIGKILL)
if boundary == 'before-replace':
    paths.os.replace = lambda *args, **kwargs: kill()
else:
    original = handoff._write
    def commit(filename, record):
        original(filename, record)
        if record['state'] == boundary:
            kill()
    handoff._write = commit
if action == 'store':
    handoff.store(receiver, message)
elif action == 'claim':
    handoff.claim(receiver, owner, 'crash-generation', 60)
elif action == 'ack':
    handoff.ack(receiver, token, owner, 'crash-generation')
raise SystemExit('boundary was not reached')
'''
        env = os.environ.copy()
        env['XSM_HOME'] = self.tmp
        env['HANDOFF_FIXTURE'] = json.dumps([self.receiver, self.message, self.owner, token,
                                           marker, action, boundary])
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run([sys.executable, '-c', script], cwd=repo, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr.decode())
        self.assertTrue(os.path.exists(marker))
        return result

    def test_sigkill_after_store_commit_before_return_recovers_original_id(self):
        from xsm import handoff
        self._killed('store', 'pending')
        record = handoff.status(self.receiver, 'm1')
        self.assertEqual(record['status'], 'pending')
        self.assertEqual(record['message'], self.message)
        self.assertEqual(handoff.store(self.receiver, self.message)['digest'], record['digest'])
        self.assertEqual(handoff.claim(self.receiver, self.owner, 'next-generation', 60)['id'], 'm1')

    def test_sigkill_after_claim_commit_recovers_dead_owner_and_invalidates_old_token(self):
        from xsm import handoff
        handoff.store(self.receiver, self.message)
        self._killed('claim', 'claimed')
        crashed = handoff.status(self.receiver, 'm1')
        self.assertEqual(crashed['status'], 'claimed')
        self.assertEqual(handoff.claim(self.receiver, self.owner, 'next-generation', 60)['status'], 'empty')
        recovered = handoff.recover(self.receiver, owner_alive=lambda *args: False)[0]
        self.assertEqual(recovered['recovery_reason'], 'owner-dead')
        new = handoff.claim(self.receiver, self.owner, 'next-generation', 60)
        self.assertEqual(new['id'], 'm1')
        self.assertEqual(new['digest'], crashed['digest'])
        with self.assertRaises(ValueError):
            handoff.ack(self.receiver, crashed['claim']['token'], self.owner, 'crash-generation')

    def test_sigkill_after_ack_commit_lost_response_readback_suppresses_duplicate(self):
        from xsm import handoff
        handoff.store(self.receiver, self.message)
        claimed = handoff.claim(self.receiver, self.owner, 'crash-generation', 60)
        token = claimed['claim']['token']
        self._killed('ack', 'acknowledged', token)
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'acknowledged')
        self.assertEqual(handoff.ack(self.receiver, token, self.owner, 'crash-generation')['status'],
                         'acknowledged')
        self.assertEqual(handoff.claim(self.receiver, self.owner, 'next-generation', 60)['status'], 'empty')
        self.assertEqual(handoff.status(self.receiver, 'm1')['message'], self.message)

    def test_sigkill_before_atomic_replace_never_exposes_partial_original(self):
        from xsm import handoff
        self._killed('store', 'before-replace')
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'not-found')
        # Store never returned, so no legacy/native export was authorized.
        record = handoff.store(self.receiver, self.message)
        self.assertEqual(record['message'], self.message)
        self.assertEqual(handoff.claim(self.receiver, self.owner, 'next-generation', 60)['id'], 'm1')

    def test_separate_reader_processes_compete_for_only_one_claim(self):
        from xsm import handoff
        handoff.store(self.receiver, self.message)
        env = os.environ.copy()
        env['XSM_HOME'] = self.tmp
        env['HANDOFF_ENDPOINT'] = json.dumps(self.receiver)
        script = '''
import json, os, sys
from xsm import handoff
sys.stdin.readline()
owner = {'type': 'native', 'id': 'reader-' + str(os.getpid())}
print(json.dumps(handoff.claim(json.loads(os.environ['HANDOFF_ENDPOINT']), owner,
                               'generation-' + str(os.getpid()), 60)))
'''
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        children = []
        try:
            for _ in range(4):
                child = subprocess.Popen([sys.executable, '-c', script], cwd=repo, env=env,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                children.append(child)
            for child in children:
                child.stdin.write(b'go\n')
                child.stdin.flush()
            results = []
            for child in children:
                output, error = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, error.decode())
                results.append(json.loads(output))
            self.assertEqual(sum(r['status'] == 'claimed' for r in results), 1)
            self.assertEqual(sum(r['status'] == 'empty' for r in results), 3)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate()
