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
        self.assertNotIn('cwd', params, 'operator runs retain their native-created workspace')
        with self.assertRaises(session.NativeSessionError): session.agent_params(dict(locator, native_lifecycle_revision=None), 'work', 'request-1')

    def test_rpc_noise_duplicates_and_non_json_values_are_refused(self):
        for output in ('noise\n{}', '[]', '{"ok":false,"ok":true}', '{"n":NaN}'):
            with self.subTest(output=output), self.assertRaises(session.NativeSessionError): session.decode_reply(output)

    def test_admission_is_bound_to_request_agent_and_native_key(self):
        locator = session.created_locator(self.created, 'main', self.cwd)
        reply = dict(status='accepted', runId='request-1', agentId='main', sessionKey=self.created['key'])
        self.assertEqual(session.accepted_run(reply, locator, 'request-1'), 'request-1')
        for field in ('status', 'runId', 'agentId', 'sessionKey'):
            with self.subTest(field=field), self.assertRaises(session.NativeSessionError):
                session.accepted_run(dict(reply, **{field: 'other'}), locator, 'request-1')

    def test_terminal_requires_matching_run_turn_session_and_reply(self):
        locator = session.created_locator(self.created, 'main', self.cwd)
        receipt = dict(runId='request-1', turnId='request-1', sessionId='native-id', terminalDisposition='visible')
        reply = dict(status='ok', runId='request-1', terminalReceipt=receipt,
                     terminalReply=dict(disposition='visible', text='native result'))
        self.assertEqual(session.completed_run(reply, locator, 'request-1'), reply['terminalReply'])
        variants = [dict(reply, status='timeout'), dict(reply, runId='other'),
                    dict(reply, stopReason='rpc'), dict(reply, stopReason='aborted'),
                    dict(reply, terminalReceipt=None), dict(reply, terminalReply=None),
                    dict(reply, terminalReply=dict(disposition='visible', text=1)),
                    dict(reply, terminalReply=dict(disposition='silent'))]
        for field in ('runId', 'turnId', 'sessionId', 'terminalDisposition'):
            variants.append(dict(reply, terminalReceipt=dict(receipt, **{field: 'other'})))
        for variant in variants:
            with self.subTest(reply=variant), self.assertRaises(session.NativeSessionError):
                session.completed_run(variant, locator, 'request-1')

    def test_native_stop_requires_exact_settled_run_and_unchanged_session(self):
        locator = session.created_locator(self.created, 'main', self.cwd)
        terminal = dict(runId='run-1', status='error', stopReason='rpc', startedAt=100, endedAt=200)
        abort = dict(ok=True, aborted=True, runIds=['run-1'])
        row = dict(key=locator['native_session_key'], sessionId='native-id', agentId='main',
                   lifecycleRevision='revision-1', lastRunId='run-1', status='killed',
                   abortedLastRun=True, hasActiveRun=False, activeRunIds=[], startedAt=100, endedAt=200,
                   unrelatedPrivateData='must not be retained')
        proof = session.stopped_run(terminal, dict(sessions=[row]), locator, 'run-1', abort)
        self.assertNotIn('unrelatedPrivateData', proof)
        for field, value in (('sessionId','other'), ('agentId','other'), ('lifecycleRevision','other'),
                             ('lastRunId','other'), ('status','idle'), ('abortedLastRun',False),
                             ('hasActiveRun',True), ('activeRunIds',['other']), ('endedAt',201)):
            with self.subTest(field=field), self.assertRaises(session.NativeSessionError):
                session.stopped_run(terminal, dict(sessions=[dict(row, **{field:value})]), locator, 'run-1', abort)
        for changed in (dict(terminal,status='ok'), dict(terminal,stopReason='error'),
                        dict(terminal,runId='other'), dict(terminal,endedAt=None), dict(terminal,endedAt=True)):
            with self.subTest(terminal=changed), self.assertRaises(session.NativeSessionError):
                session.stopped_run(changed, dict(sessions=[row]), locator, 'run-1', abort)
        with self.assertRaises(session.NativeSessionError):
            session.stopped_run(terminal, dict(sessions=[row]), locator, 'run-1', dict(abort,aborted=False))

    def test_queued_stop_requires_explicit_native_nonexecution_and_stable_identity(self):
        locator = session.created_locator(self.created, 'main', self.cwd)
        terminal = dict(runId='run-1',status='error',stopReason='rpc',endedAt=200,providerStarted=False)
        abort = dict(ok=True,aborted=True,runIds=['run-1'])
        row = dict(key=locator['native_session_key'],sessionId='native-id',agentId='main',
                   lifecycleRevision='revision-1',hasActiveRun=False,activeRunIds=[],abortedLastRun=False)
        proof = session.stopped_run(terminal,dict(sessions=[row]),locator,'run-1',abort)
        self.assertTrue(proof['native_provider_not_started'])
        self.assertNotIn('lastRunId',proof)
        for changed in (dict(terminal,providerStarted=True),dict(terminal,providerStarted=0),
                        dict(terminal,startedAt=100),dict(terminal,runId='other'),dict(terminal,endedAt=None)):
            with self.subTest(terminal=changed), self.assertRaises(session.NativeSessionError):
                session.stopped_run(changed,dict(sessions=[row]),locator,'run-1',abort)
        for field,value in (('sessionId','other'),('lifecycleRevision','other'),('hasActiveRun',True),('activeRunIds',['other'])):
            with self.subTest(field=field), self.assertRaises(session.NativeSessionError):
                session.stopped_run(terminal,dict(sessions=[dict(row,**{field:value})]),locator,'run-1',abort)
