"""Strict stopped-output readback, separate from task answers and normal exit."""
import copy
import json
import tempfile
import unittest

from integrations.openclaw import worker_cli, worker_session as session


class OpenClawWorkerCancellationTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='xsm-openclaw-cancel-contract-')
        self.addCleanup(directory.cleanup);self.cwd = directory.name
        self.context = dict(id='context',epoch='epoch',native_session_id='native-id')
        self.locator = dict(agent_id='main',native_session_id='native-id',native_session_key='agent:main:dashboard:key',
                            native_lifecycle_revision='revision',cwd=self.cwd)
        self.value = dict(type='xsm_openclaw_cancelled',cancelled=True,native_not_started=False,
            context_id='context',context_epoch='epoch',locator=self.locator,run_id='run-1',
            admission=dict(status='accepted',runId='run-1',agentId='main',sessionKey=self.locator['native_session_key']),
            abort=dict(ok=True,aborted=True,runIds=['run-1']),
            terminal=dict(status='error',stopReason='rpc',runId='run-1',startedAt=100,endedAt=200),
            stop_observation=dict(key=self.locator['native_session_key'],sessionId='native-id',agentId='main',
                lifecycleRevision='revision',lastRunId='run-1',status='killed',abortedLastRun=True,
                hasActiveRun=False,activeRunIds=[],startedAt=100,endedAt=200))

    def parse(self, value):
        return worker_cli.parse_cancellation(json.dumps(value),self.context,agent_id='main',cwd=self.cwd)

    def test_stopped_output_requires_exact_epoch_and_native_settlement(self):
        result = self.parse(self.value)
        self.assertEqual(result['native_evidence']['native_state'],'stopped')
        self.assertNotIn('body',result)
        for field in ('context_epoch','context_id','run_id'):
            with self.subTest(field=field), self.assertRaises(session.NativeSessionError):
                self.parse(dict(self.value,**{field:'other'}))
        for field, value in (('sessionId','other'), ('lifecycleRevision','other'),
                             ('lastRunId','other'), ('hasActiveRun',True), ('abortedLastRun',False)):
            changed = copy.deepcopy(self.value);changed['stop_observation'][field]=value
            with self.subTest(field=field), self.assertRaises(session.NativeSessionError):self.parse(changed)

    def test_unstarted_marker_cannot_contain_a_native_execution(self):
        value = {key:item for key,item in self.value.items() if key not in ('abort','stop_observation')}
        value.update(native_not_started=True,admission=None,terminal=None)
        self.assertTrue(self.parse(value)['native_evidence']['native_not_started'])
        for field in ('admission','terminal','abort','stop_observation'):
            with self.subTest(field=field), self.assertRaises(session.NativeSessionError):
                self.parse(dict(value,**{field:self.value[field]}))

    def test_native_error_or_completed_answer_is_not_stopped_evidence(self):
        for value in (dict(self.value,type='xsm_openclaw_result'),dict(self.value,cancelled=False),
                      dict(self.value,abort=dict(ok=True,aborted=False,runIds=[])),
                      dict(self.value,terminal=dict(status='error',stopReason='provider-error',runId='run-1'))):
            with self.subTest(value=value), self.assertRaises(session.NativeSessionError):self.parse(value)

    def test_accepted_queued_stop_is_distinct_from_never_submitted(self):
        value = copy.deepcopy(self.value)
        value['terminal'].pop('startedAt');value['terminal']['providerStarted']=False
        for field in ('lastRunId','status','abortedLastRun','startedAt','endedAt'):
            value['stop_observation'].pop(field)
        result = self.parse(value)
        self.assertTrue(result['native_evidence']['native_provider_not_started'])
        with self.assertRaises(session.NativeSessionError):
            self.parse(dict(value,native_not_started=True))

    def test_bound_record_and_final_must_share_one_execution(self):
        bound = {key:self.value[key] for key in ('context_id','context_epoch','run_id','locator')}
        bound['type']='xsm_openclaw_bound'
        output=json.dumps(bound)+'\n'+json.dumps(self.value)+'\n'
        self.assertEqual(worker_cli.parse_cancellation(output,self.context)['native_evidence']['native_state'],'stopped')
        for field in ('context_id','context_epoch','run_id'):
            changed=dict(bound,**{field:'other'})
            with self.subTest(field=field),self.assertRaises(session.NativeSessionError):
                worker_cli.parse_cancellation(json.dumps(changed)+'\n'+json.dumps(self.value),self.context)
        for text in (json.dumps(bound),json.dumps(bound)+'\n'+json.dumps(bound),
                     output+json.dumps(self.value),'noise\n'+output):
            with self.subTest(text=text),self.assertRaises(session.NativeSessionError):
                worker_cli.parse_cancellation(text,self.context)
