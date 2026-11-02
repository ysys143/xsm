"""Owned ordering with actual private control sockets, explicit native RPC fixture."""
import os
import tempfile
import unittest

from integrations.openclaw import worker_frontend as frontend
from integrations.openclaw.worker_session import NativeSessionError
from xsm.native_worker_control import WorkerControl, WorkerControlClient, ControlError


class OpenClawWorkerFrontendTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='xsm-openclaw-turn-order-')
        self.addCleanup(directory.cleanup)
        self.cwd = directory.name
        self.calls, self.binds = [], []
        self.waits = []
        self.control = WorkerControl(self.binds.append)
        self.client = WorkerControlClient(os.dup(self.control.child.fileno()))
        self.control.start()
        self.addCleanup(self.control.close)
        self.addCleanup(self.client.close)

    def rpc(self, method, params):
        self.calls.append((method, params))
        if method == 'sessions.create':
            return dict(ok=True, key='agent:main:dashboard:host-key', sessionId='host-id', runStarted=False,
                        entry=dict(sessionId='host-id', lifecycleRevision='host-revision', sessionRoot=self.cwd))
        if method == 'sessions.resolve':
            self.assertEqual(params, dict(sessionId='host-id', agentId='main'))
            return dict(ok=True, key='agent:main:dashboard:host-key', agentId='main')
        if method == 'sessions.list':
            return dict(sessions=[dict(key='agent:main:dashboard:host-key', sessionId='host-id',
                                       agentId='main', lifecycleRevision='host-revision')])
        if method == 'agent':
            self.assertEqual(self.binds, ['host-id'], 'no model admission before private binding ACK')
            self.assertEqual(params['expectedExistingSessionId'], 'host-id')
            self.assertEqual(params['expectedExistingSessionLifecycleRevision'], 'host-revision')
            return dict(status='accepted', runId='request-1', agentId='main', sessionKey=params['sessionKey'])
        if method == 'agent.wait':
            if self.waits:
                return self.waits.pop(0)
            return dict(status='ok', runId='request-1',
                        terminalReceipt=dict(runId='request-1', turnId='request-1', sessionId='host-id',
                                             terminalDisposition='visible'),
                        terminalReply=dict(disposition='visible', text='fixture native result'))
        raise AssertionError('unexpected native method')

    def run_turn(self, rpc=None, **kwargs):
        return frontend.run_turn(rpc or self.rpc, self.client, agent_id='main', cwd=self.cwd,
                                 message='fixture task', request_id='request-1', **kwargs)

    def test_fresh_host_id_is_acknowledged_before_native_admission(self):
        result = self.run_turn()
        self.assertEqual(result['reply']['text'], 'fixture native result')
        self.assertEqual([m for m, _ in self.calls], ['sessions.create', 'agent', 'agent.wait'])

    def test_resume_resolves_exact_id_and_revision_before_binding(self):
        self.run_turn(native_session_id='host-id')
        self.assertEqual([m for m, _ in self.calls], ['sessions.resolve', 'sessions.list', 'agent', 'agent.wait'])

    def test_binding_refusal_never_submits_a_model_turn(self):
        def refuse(_sid):
            raise ValueError('explicit owner journal refusal')
        self.control.bind = refuse
        with self.assertRaises(ControlError):
            self.run_turn()
        self.assertEqual([m for m, _ in self.calls], ['sessions.create'])

    def test_unknown_admission_is_not_replayed(self):
        def rpc(method, params):
            if method == 'agent':
                self.calls.append((method, params))
                raise ConnectionError('fixture acceptance output lost')
            return self.rpc(method, params)
        with self.assertRaises(ConnectionError):
            self.run_turn(rpc)
        self.assertEqual([m for m, _ in self.calls], ['sessions.create', 'agent'])

    def test_observation_timeout_polls_same_run_without_resubmission(self):
        self.waits = [dict(status='timeout', runId='request-1')]
        self.run_turn()
        self.assertEqual([m for m, _ in self.calls], ['sessions.create', 'agent', 'agent.wait', 'agent.wait'])

    def test_late_other_run_observation_is_refused(self):
        self.waits = [dict(status='timeout', runId='another-run')]
        with self.assertRaises(NativeSessionError):
            self.run_turn()
        self.assertEqual(sum(m == 'agent' for m, _ in self.calls), 1)
