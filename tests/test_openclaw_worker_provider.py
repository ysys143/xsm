"""Common owned engine and SDK subprocess fixture; not native OpenClaw certification."""
import json
import os
from pathlib import Path
import shutil
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
 if(method==='agents.list')result={defaultId:'main',agents:[{id:'main'}]};
 else if(method==='sessions.create') {
  const row={key:'agent:main:dashboard:'+randomUUID(),sessionId:randomUUID(),agentId:'main',lifecycleRevision:randomUUID(),sessionRoot:p.cwd};
  s.sessions.push(row);result={ok:true,key:row.key,sessionId:row.sessionId,entry:row,runStarted:false};
 } else if(method==='sessions.resolve') {
  const row=s.sessions.find(r=>r.sessionId===p.sessionId);
  result=row?{ok:true,key:row.key,agentId:row.agentId}:{ok:false};
 } else if(method==='sessions.list')result={sessions:s.sessions};
 else if(method==='agent') {
  const row=s.sessions.find(r=>r.sessionId===p.sessionId);
  if(!row || row.lifecycleRevision!==p.expectedExistingSessionLifecycleRevision)throw Error('fixture native identity changed');
  s.runs[p.idempotencyKey]=row.sessionId;
  result={status:'accepted',runId:p.idempotencyKey,sessionKey:row.key,agentId:row.agentId};
 } else if(method==='agent.wait')result={status:'ok',runId:p.runId,
  terminalReceipt:{runId:p.runId,turnId:p.runId,sessionId:s.runs[p.runId],terminalDisposition:'visible'},
  terminalReply:{disposition:'visible',text:'Explicit owned SDK fixture answer.'}};
 else throw Error('unexpected fixture method');
 fs.writeFileSync(path,JSON.stringify(s));return result;
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
        output = json.loads(Path(first['child']['stdout']).read_text())
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
