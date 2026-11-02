"""Native create/resolve identity contracts, no OpenClaw/model certification."""
import copy
import tempfile
import unittest
from integrations.openclaw import worker_session as session


class OpenClawWorkerSessionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='xsm-openclaw-session-contract-')
        self.addCleanup(self.directory.cleanup); self.cwd = self.directory.name
        self.created = dict(ok=True, key='agent:main:dashboard:native-key', sessionId='native-id', runStarted=False,
                            entry=dict(sessionId='native-id', lifecycleRevision='revision-1', sessionRoot=self.cwd))

    def test_create_has_no_adopted_key_initial_task_or_permission_override(self):
        params = session.creation_params('main', self.cwd, idempotency_key='one-create')
        self.assertEqual(params, dict(agentId='main', cwd=self.cwd, message='', idempotencyKey='one-create'))
        locator = session.created_locator(self.created, 'main', self.cwd)
        self.assertEqual(locator['native_session_id'], 'native-id')
        self.assertEqual(locator['native_lifecycle_revision'], 'revision-1')

    def test_create_refuses_started_changed_identity_or_workspace(self):
        variants = [dict(self.created, runStarted=0), dict(self.created, runStarted=True)]
        for field, value in (('sessionId', 'other'), ('lifecycleRevision', ''), ('sessionRoot', '/different'), ('execNode', 'remote')):
            changed = copy.deepcopy(self.created); changed['entry'][field] = value; variants.append(changed)
        for reply in variants:
            with self.subTest(reply=reply), self.assertRaises(session.NativeSessionError):
                session.created_locator(reply, 'main', self.cwd)

    def test_resume_resolves_only_exact_native_id_and_listing_revision(self):
        self.assertEqual(session.resolution_params('native-id', 'main'), dict(sessionId='native-id', agentId='main'))
        reply = dict(ok=True, key=self.created['key'], agentId='main')
        row = dict(key=self.created['key'], sessionId='native-id', agentId='main', lifecycleRevision='revision-2')
        locator = session.resolved_locator(reply, {'sessions': [row]}, 'native-id', 'main', self.cwd)
        self.assertEqual(locator['native_lifecycle_revision'], 'revision-2')
        for listing in ({'sessions': []}, {'sessions': [row, row]}, {'sessions': [dict(row, sessionId='other')]}):
            with self.assertRaises(session.NativeSessionError):
                session.resolved_locator(reply, listing, 'native-id', 'main', self.cwd)

    def test_agent_run_requires_existing_native_id_and_lifecycle_revision(self):
        locator = session.created_locator(self.created, 'main', self.cwd)
        params = session.agent_params(locator, 'work', 'request-1')
        self.assertEqual(params['expectedExistingSessionId'], 'native-id')
        self.assertEqual(params['expectedExistingSessionLifecycleRevision'], 'revision-1')
        self.assertFalse(params['deliver'])
        with self.assertRaises(session.NativeSessionError): session.agent_params(dict(locator, native_lifecycle_revision=None), 'work', 'request-1')

    def test_rpc_noise_duplicates_and_non_json_values_are_refused(self):
        for output in ('noise\n{}', '[]', '{"ok":false,"ok":true}', '{"n":NaN}'):
            with self.subTest(output=output), self.assertRaises(session.NativeSessionError): session.decode_reply(output)
