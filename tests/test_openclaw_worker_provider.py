"""Common owned engine and SDK subprocess fixture; not native OpenClaw certification."""
import json
import os
from pathlib import Path
import shutil
import concurrent.futures
import signal
import time
import copy
from unittest import mock

from tests.test_xsm import TempState


class OpenClawWorkerProviderTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import host_install, registry, workers
        self.workers = workers
        self.home = str(Path(self.tmp, 'openclaw-profile'))
        self.owner = registry.upsert('codex', self.tmp + '/owner', 'owner', os.getpid(), self.tmp)
        root = Path(self.tmp, 'native-package');root.mkdir()
        (root / 'package.json').write_text(json.dumps(dict(name='openclaw', version='2026.10.9', type='module',
            exports={'./plugin-sdk/gateway-runtime': './fixture.mjs'})))
        self.executable = root / 'openclaw.mjs';self.executable.write_text('// Explicit SDK fixture, no native runtime or model.\n');self.executable.chmod(0o700)
        (root / 'fixture.mjs').write_text('''
import fs from 'node:fs';import {randomUUID} from 'node:crypto';
export async function callGatewayFromCli(method,options,p,extra) {
 const path=process.env.OPENCLAW_STATE_DIR+'/fixture-memory.json';
 let s;try{s=JSON.parse(fs.readFileSync(path,'utf8'));}catch{s={sessions:[],runs:{},calls:[]};}
 s.calls.push(method);let result;
 if(method==='agent.wait' && ['ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY'].some(k=>k in process.env))throw Error('unexpected fixture billing marker');
 if(method==='agent.wait' && fs.existsSync(process.env.OPENCLAW_STATE_DIR+'/pause-wait'))await new Promise(r=>setTimeout(r,10000));
 if(method==='agents.list')result={defaultId:'main',agents:[{id:'main'}]};
 else if(method==='sessions.create') {
  const row={key:'agent:main:dashboard:'+randomUUID(),sessionId:randomUUID(),agentId:'main',lifecycleRevision:randomUUID(),sessionRoot:p.cwd};
  s.sessions.push(row);result={ok:true,key:row.key,sessionId:row.sessionId,entry:row,runStarted:false};
 } else if(method==='sessions.resolve') {
  const row=s.sessions.find(r=>r.sessionId===p.sessionId);
  result=row?{ok:true,key:row.key,agentId:row.agentId}:{ok:false};
 } else if(method==='sessions.list')result={sessions:s.sessions};
 else if(method==='sessions.describe')result={session:s.sessions.find(r=>r.key===p.key)};
 else if(method==='agent') {
  const row=s.sessions.find(r=>r.sessionId===p.sessionId);
  if(!row || row.lifecycleRevision!==p.expectedExistingSessionLifecycleRevision)throw Error('fixture native identity changed');
  s.runs[p.idempotencyKey]=row.sessionId;
  row.lastRunId=p.idempotencyKey;row.status='done';row.abortedLastRun=false;row.hasActiveRun=false;row.activeRunIds=[];row.startedAt=100;row.endedAt=200;
  s.history ||= {};s.history[row.sessionId] ||= [];const h=s.history[row.sessionId];
  h.push({role:'user',idempotencyKey:p.idempotencyKey+':user',content:'fixture task',__openclaw:{id:p.idempotencyKey+':input',idempotencyKey:p.idempotencyKey+':user',seq:h.length+1,transcriptPosition:{source:'fixture-source',rawSeq:h.length+1}}});
  h.push({role:'assistant',stopReason:'stop',content:[{type:'text',text:'Explicit owned SDK fixture answer.'}],__openclaw:{id:p.idempotencyKey+':answer',runId:p.idempotencyKey,seq:h.length+1,transcriptPosition:{source:'fixture-source',rawSeq:h.length+1}}});
  result={status:'accepted',runId:p.idempotencyKey,sessionKey:row.key,agentId:row.agentId};
 } else if(method==='agent.wait')result={status:'ok',runId:p.runId,
  terminalReceipt:{runId:p.runId,turnId:p.runId,sessionId:s.runs[p.runId],terminalDisposition:'visible'},
  terminalReply:{disposition:'visible',text:'Explicit owned SDK fixture answer.'}};
 else if(method!=='chat.history')throw Error('unexpected fixture method');
 if(method==='agent.wait' && fs.existsSync(process.env.OPENCLAW_STATE_DIR+'/terminal-error')) {
  const row=s.sessions.find(r=>r.sessionId===s.runs[p.runId]);
  row.lastRunId=p.runId;row.status='failed';row.hasActiveRun=false;row.activeRunIds=[];row.startedAt=100;row.endedAt=190;
  result={status:'error',runId:p.runId,startedAt:100,endedAt:200,error:'explicit fixture provider refusal'};
  const h=s.history[row.sessionId];s.history[row.sessionId]=h.filter(m=>m.__openclaw?.runId!==p.runId);
  const f=s.history[row.sessionId];f.push({role:'custom',customType:'run-failed-before-reply',content:'private fixture error',timestamp:195,__openclaw:{id:p.runId+':failure',runId:p.runId,seq:f.length+1,recordTimestampMs:195,transcriptPosition:{source:'fixture-source',rawSeq:f.length+1}}});
 }
 if(method==='agent.wait' && fs.existsSync(process.env.OPENCLAW_STATE_DIR+'/lost-wait-cache'))result={status:'timeout',runId:p.runId};
 if(method==='chat.history') {
  const row=s.sessions.find(r=>r.key===p.sessionKey);const h=s.history[row.sessionId];const end=h.length-(p.offset||0);
  result={sessionKey:row.key,sessionId:row.sessionId,sessionInfo:row,messages:h.slice(Math.max(0,end-1),end),hasMore:end>1,totalMessages:h.length,pendingInputs:{items:[],total:0}};
 }
 const temporary=path+'.tmp-'+process.pid;
 fs.writeFileSync(temporary,JSON.stringify(s));fs.renameSync(temporary,path);return result;
}
''')
        env = {key: '' for _, keys in workers.FRAMEWORKS for key in keys}
        env.update(XSM_OPENCLAW=str(self.executable), XSM_OPENCLAW_NODE=shutil.which('node'))
        patcher = mock.patch.dict(os.environ, env);patcher.start();self.addCleanup(patcher.stop)
        host_install.apply('openclaw', self.home)
        self.worker = workers.create_owned('openclaw', caller=self.owner, name='native-openclaw', home=self.home)

    def run_turn(self, request='one', work='same'):
        return self.workers.run_owned('native-openclaw', self.owner, 'Explicit fixture task',
            work_context=work, request_id=request,
            reply_sender=lambda worker,row:self.workers.publish_owned(worker,row,wake=False))

    def test_common_journal_binding_resume_separation_and_replay(self):
        first, second, separate = self.run_turn(), self.run_turn('two'), self.run_turn('three', 'separate')
        self.assertEqual(first['status'], 'reply-stored')
        self.assertEqual(first['result']['body'], 'Explicit owned SDK fixture answer.')
        self.assertIsNone(first['result']['outcome'])
        self.assertEqual(first['result']['native_session_id'], second['result']['native_session_id'])
        self.assertNotEqual(first['result']['native_session_id'], separate['result']['native_session_id'])
        self.assertEqual(first['native_binding']['native_session_id'], first['result']['native_session_id'])
        before = Path(self.home, 'fixture-memory.json').read_bytes()
        self.assertEqual(self.run_turn()['reply_id'], first['reply_id'])
        self.assertEqual(Path(self.home, 'fixture-memory.json').read_bytes(), before)
        self.assertNotIn('Explicit fixture task', first['child']['argv'])

    def test_retained_output_rejects_wrong_context_epoch_and_native_receipt(self):
        from integrations.openclaw.worker_cli import parse_result
        from integrations.openclaw.worker_session import NativeSessionError
        first = self.run_turn()
        from integrations.openclaw.worker_cli import final_frame
        output = final_frame(Path(first['child']['stdout']).read_text())
        for field in ('context_id', 'context_epoch'):
            changed = dict(output, **{field: 'other'})
            with self.subTest(field=field), self.assertRaises(NativeSessionError):
                parse_result(json.dumps(changed), first['context'])
        for field, value in (('agent_id', 'other'), ('native_session_key', ''),
                             ('native_lifecycle_revision', ''), ('cwd', self.home)):
            changed = dict(output, locator=dict(output['locator'], **{field: value}))
            with self.subTest(field=field), self.assertRaises(NativeSessionError):
                parse_result(json.dumps(changed), first['context'], agent_id='main', cwd=self.tmp)
        output['terminal']['terminalReceipt']['sessionId'] = 'other'
        with self.assertRaises(NativeSessionError):
            parse_result(json.dumps(output), first['context'])

    def test_missing_selected_agent_is_not_replaced_by_default(self):
        with mock.patch.dict(os.environ, {'XSM_OPENCLAW_AGENT_ID': 'missing'}):
            with self.assertRaises(self.workers.WorkerError):
                self.workers.create_owned('openclaw', caller=self.owner, name='missing-agent', home=self.home)
        self.assertIsNone(self.workers.load('missing-agent'))

    def test_changed_installed_frontend_is_not_executed(self):
        from xsm import native_workers
        path = Path(self.worker['native_provider']['runtime_root'], 'integrations/openclaw/worker_frontend.py')
        path.write_bytes(path.read_bytes() + b'\n# explicit changed installed fixture\n')
        with self.assertRaises(native_workers.ProviderError):
            native_workers.provider('openclaw').argv(self.worker, dict(id='context', epoch='generation'))

    def test_frontend_death_queries_native_result_without_replay(self):
        from xsm import identity
        pause = Path(self.home,'pause-wait');pause.touch()
        memory = Path(self.home,'fixture-memory.json')
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_turn)
            deadline = time.monotonic()+10
            while True:
                state = json.loads(memory.read_text())
                request = self.workers.owned_status('native-openclaw',self.owner,'one')
                if state.get('runs') and request.get('native_binding'):break
                if time.monotonic()>deadline:raise AssertionError('fixture native admission not observed')
                time.sleep(.02)
            child = request['child']
            self.assertTrue(identity.process_matches(child['pid'],child['lstart']))
            os.killpg(child['pid'],signal.SIGKILL)
            unknown = future.result(timeout=10)
        self.assertEqual(unknown['status'],'unknown')
        self.assertTrue(unknown['slot_occupied'])
        self.assertIsNone(unknown['result'])
        pause.unlink()
        calls = json.loads(memory.read_text())['calls'].count('agent')
        with mock.patch.dict(os.environ,{'ANTHROPIC_API_KEY':'fixture-not-real','OPENAI_API_KEY':'fixture-not-real','CODEX_API_KEY':'fixture-not-real'}):
            recovered = self.workers.reconcile_owned('native-openclaw',self.owner,'one',
                reply_sender=lambda worker,row:self.workers.publish_owned(worker,row,wake=False))
        self.assertEqual(recovered['status'],'reply-stored')
        self.assertEqual(recovered['result']['body'],'Explicit owned SDK fixture answer.')
        self.assertEqual(recovered['result']['native_session_id'],request['native_binding']['native_session_id'])
        self.assertIsNone(recovered['result']['outcome'])
        self.assertEqual(json.loads(memory.read_text())['calls'].count('agent'),calls)

    def test_recovery_guards_refuse_foreign_binding_and_live_child_before_rpc(self):
        from xsm import identity
        first=self.run_turn();memory=Path(self.home,'fixture-memory.json');before=memory.read_bytes()
        variants=[]
        for field,value in (('native_session_id','other'),('child_pid',1),('child_lstart','other')):
            changed=copy.deepcopy(first);changed['native_binding'][field]=value;variants.append(changed)
        changed=copy.deepcopy(first)
        changed['child'].update(pid=os.getpid(),lstart=identity.lstart(os.getpid()))
        changed['native_binding'].update(child_pid=os.getpid(),child_lstart=identity.lstart(os.getpid()))
        variants.append(changed)
        changed=copy.deepcopy(first);changed['child']['stdout']=self.tmp+'/wrong-output';variants.append(changed)
        changed=copy.deepcopy(first);changed['worker']['native_provider']=True;variants.append(changed)
        for pid in (None,True,-1,1.5):
            changed=copy.deepcopy(first);changed['child']['pid']=pid;changed['native_binding']['child_pid']=pid;variants.append(changed)
        for value in variants:
            with self.subTest(binding=value.get('native_binding')):
                self.assertIsNone(self.workers._readback_owned_host(value['worker'],value))
                self.assertEqual(memory.read_bytes(),before)

    def test_recovery_rejects_changed_bound_run_and_epoch_before_rpc(self):
        from xsm import native_workers
        from integrations.openclaw.worker_cli import output_records
        first=self.run_turn();memory=Path(self.home,'fixture-memory.json');before=memory.read_bytes()
        bound,_final=output_records(Path(first['child']['stdout']).read_text())
        provider=native_workers.provider('openclaw')
        for field in ('run_id','context_id','context_epoch'):
            with self.subTest(field=field),self.assertRaises(native_workers.ProviderError):
                provider.recover_result(first['worker'],first['context'],json.dumps(dict(bound,**{field:'other'})),first['child'],
                    self.workers._owned_turn_environment(first['worker'],provider))
            self.assertEqual(memory.read_bytes(),before)

    def test_native_error_settlement_releases_lease_without_task_answer(self):
        Path(self.home,'terminal-error').touch()
        unknown=self.run_turn()
        self.assertEqual(unknown['status'],'unknown')
        self.assertTrue(unknown['slot_occupied'])
        memory=Path(self.home,'fixture-memory.json');calls=json.loads(memory.read_text())['calls'].count('agent')
        settled=self.workers.reconcile_owned('native-openclaw',self.owner,'one')
        self.assertEqual(settled['status'],'unknown')
        self.assertFalse(settled['slot_occupied'])
        self.assertIsNone(settled['result']);self.assertIsNone(settled['reply_id'])
        self.assertIsNone(settled.get('cancellation'))
        self.assertEqual(settled['native_execution']['state'],'settled')
        from xsm import mcp
        import io
        server=mcp.Server(io.StringIO(),io.StringIO());server.session=lambda:self.owner
        observed=json.loads(server.call('xsm_owned',{'action':'status','name':'native-openclaw','request_id':'one'}))
        self.assertEqual(observed['native_execution']['state'],'settled')
        self.assertIsNone(observed['result']);self.assertIsNone(observed['reply_id'])
        self.assertNotIn('child',observed)
        self.assertNotIn('child_pid',observed['native_execution'])
        self.assertNotIn('evidence',observed['native_execution'])
        again=self.workers.reconcile_owned('native-openclaw',self.owner,'one')
        self.assertEqual(again['native_execution'],settled['native_execution'])
        self.assertEqual(json.loads(memory.read_text())['calls'].count('agent'),calls)

    def test_lost_native_wait_cache_uses_exact_run_history_without_replay(self):
        from xsm import identity
        Path(self.home,'pause-wait').touch();memory=Path(self.home,'fixture-memory.json')
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.run_turn)
            deadline=time.monotonic()+10
            while True:
                state=json.loads(memory.read_text());request=self.workers.owned_status('native-openclaw',self.owner,'one')
                if state.get('runs') and request.get('native_binding'):break
                if time.monotonic()>deadline:raise AssertionError('fixture admission unavailable')
                time.sleep(.02)
            child=request['child'];self.assertTrue(identity.process_matches(child['pid'],child['lstart']))
            os.killpg(child['pid'],signal.SIGKILL);unknown=future.result(timeout=10)
        Path(self.home,'pause-wait').unlink();Path(self.home,'lost-wait-cache').touch()
        calls=json.loads(memory.read_text())['calls'].count('agent')
        recovered=self.workers.reconcile_owned('native-openclaw',self.owner,'one',
            reply_sender=lambda worker,row:self.workers.publish_owned(worker,row,wake=False))
        self.assertEqual(recovered['status'],'reply-stored')
        self.assertEqual(recovered['result']['body'],'Explicit owned SDK fixture answer.')
        self.assertEqual(recovered['result']['native_evidence']['source'],'native-chat.history')
        self.assertNotIn('terminal_receipt',recovered['result']['native_evidence'])
        self.assertEqual(json.loads(memory.read_text())['calls'].count('agent'),calls)

    def test_settlement_journal_refuses_wrong_reservation_or_native_identity(self):
        from xsm import owned_requests
        Path(self.home,'terminal-error').touch();unknown=self.run_turn()
        path=Path(owned_requests._path(self.owner));before=path.read_bytes()
        token=unknown['reservation']['token'];sid=unknown['context']['native_session_id']
        for selected_token,selected_id in (('wrong',sid),(token,'other')):
            with self.subTest(native_id=selected_id),self.assertRaises(owned_requests.OwnedError):
                owned_requests.confirm_native_settlement(self.owner,'one',selected_token,selected_id,{'native_state':'settled'})
            self.assertEqual(path.read_bytes(),before)

    def test_cold_failed_run_releases_only_execution_lease(self):
        Path(self.home,'terminal-error').touch();unknown=self.run_turn()
        self.assertEqual(unknown['status'],'unknown');self.assertTrue(unknown['slot_occupied'])
        Path(self.home,'lost-wait-cache').touch()
        memory=Path(self.home,'fixture-memory.json');calls=json.loads(memory.read_text())['calls'].count('agent')
        closed=self.workers.reconcile_owned('native-openclaw',self.owner,'one')
        self.assertFalse(closed['slot_occupied']);self.assertEqual(closed['status'],'unknown')
        self.assertIsNone(closed['result']);self.assertIsNone(closed['reply_id']);self.assertIsNone(closed.get('cancellation'))
        self.assertEqual(closed['native_execution']['evidence']['source'],'native-chat.history')
        self.assertNotIn('private fixture error',json.dumps(closed['native_execution']))
        self.assertEqual(json.loads(memory.read_text())['calls'].count('agent'),calls)

    def test_cold_recovery_does_not_adopt_unlinked_restart_run(self):
        Path(self.home,'terminal-error').touch();unknown=self.run_turn()
        Path(self.home,'terminal-error').unlink()
        Path(self.home,'lost-wait-cache').touch()
        memory=Path(self.home,'fixture-memory.json');state=json.loads(memory.read_text())
        calls=state['calls'].count('agent')
        sid=unknown['context']['native_session_id']
        row=next(row for row in state['sessions'] if row['sessionId']==sid)
        # Same native conversation and revision do not prove continuation lineage.
        # Preserve the original failure occurrence to make the row fence decisive.
        row.update(lastRunId='native-restart-recovery-run',status='failed',abortedLastRun=False)
        state['history'][sid].append({'role':'assistant','stopReason':'stop',
            'content':[{'type':'text','text':'Unlinked recovery answer.'}],
            '__openclaw':{'id':'recovery-answer','runId':'native-restart-recovery-run',
                'seq':3,'transcriptPosition':{'source':'fixture-source','rawSeq':3}}})
        memory.write_text(json.dumps(state))
        observed=self.workers.reconcile_owned('native-openclaw',self.owner,'one')
        self.assertEqual(observed['status'],'unknown')
        self.assertTrue(observed['slot_occupied'])
        self.assertIsNone(observed['result']);self.assertIsNone(observed['reply_id'])
        self.assertIsNone(observed.get('native_execution'))
        self.assertEqual(json.loads(memory.read_text())['calls'].count('agent'),calls)
