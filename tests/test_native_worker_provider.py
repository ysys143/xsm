"""Provider selection and owned native process/journal interoperability, model0."""
import io
import json
import os
from pathlib import Path
import sys
from unittest import mock
from tests.test_xsm import TempState


class NativeWorkerProviderTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import host_install, native_workers, registry, workers
        self.owner = registry.upsert('codex', self.tmp+'/owner', 'native-owner', os.getpid(), self.tmp)
        self.home = str(Path(self.tmp, 'hermes').resolve())
        host_install.apply('hermes', self.home)
        self.binary = Path(self.tmp, 'native-hermes')
        self.binary.write_text('#!'+sys.executable+'\n'+'''import json,os,sys,uuid
if '--version' in sys.argv:
 print('Hermes v0.22.5')
 raise SystemExit(0)
prompt=sys.stdin.read()
args=sys.argv[1:]
sid=args[args.index('--resume')+1] if '--resume' in args else 'local-'+uuid.uuid4().hex+uuid.uuid4().hex
path=os.path.join(os.environ['HERMES_HOME'],'native-memory.json')
try:
 with open(path) as f:state=json.load(f)
except FileNotFoundError:state={'calls':0,'memory':{}}
state['calls']+=1
if prompt.startswith('remember:'):state['memory'][sid]=prompt.partition(':')[2]
with open(path,'w') as f:json.dump(state,f)
body=state['memory'].get(sid,'no prior memory')
print(json.dumps({'type':'system','subtype':'init','session_id':''}))
print(json.dumps({'type':'result','session_id':sid,'exit_code':0,'text':json.dumps({'body':body,'outcome':'succeeded'}),
 'native_environment':{'home':os.environ.get('HERMES_HOME'),'cwd':os.environ.get('TERMINAL_CWD'),
 'parent_session_present':any(k.startswith(('HERMES_SESSION_','HERMES_TUI_')) for k in os.environ),
 'billing_keys_present':any(k in os.environ for k in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY','HERMES_API_KEY','CUSTOM_API_KEY'))}}))
''')
        self.binary.chmod(0o700)
        fake=self.fixture_native_package()
        environment = {key: '' for _, keys in workers.FRAMEWORKS for key in keys}
        environment['XSM_HERMES'] = str(self.binary)
        environment['PYTHONPATH'] = str(fake)
        patcher = mock.patch.dict(os.environ, environment);patcher.start();self.addCleanup(patcher.stop)
        self.worker = workers.create_owned('hermes', caller=self.owner, name='native-hermes', home=self.home)

    def fixture_native_package(self):
        """Stub native API, actual controlled frontend/process/socket; never an LLM."""
        root=Path(self.tmp,'native-api');package=root/'hermes_cli';package.mkdir(parents=True)
        (package/'__init__.py').write_text('')
        (package/'gateway_client.py').write_text('class GatewayClientError(Exception): pass\n')
        (package/'stream_json.py').write_text('''import json
class StreamJsonEmitter:
 def __init__(self):
  self.sid=''
  print(json.dumps({'type':'system','subtype':'init','session_id':''}),flush=True)
 def bind_session(self,sid):self.sid=sid
 def emit_result(self,text,environment):
  print(json.dumps({'type':'result','session_id':self.sid,'exit_code':0,'text':text,'native_environment':environment}),flush=True)
''')
        (package/'main.py').write_text('''import json,os,sys,uuid
from . import stream_json
def main():
 args=sys.argv[1:];prompt=sys.stdin.read()
 sid=args[args.index('--resume')+1] if '--resume' in args else 'local-'+uuid.uuid4().hex+uuid.uuid4().hex
 emitter=stream_json.StreamJsonEmitter();emitter.bind_session(sid)
 path=os.path.join(os.environ['HERMES_HOME'],'native-memory.json')
 try:
  with open(path) as f:state=json.load(f)
 except FileNotFoundError:state={'calls':0,'memory':{}}
 state['calls']+=1
 if prompt.startswith('remember:'):state['memory'][sid]=prompt.partition(':')[2]
 with open(path,'w') as f:json.dump(state,f)
 body=state['memory'].get(sid,'no prior memory')
 emitter.emit_result(json.dumps({'body':body,'outcome':'succeeded'}),{'home':os.environ.get('HERMES_HOME'),
  'cwd':os.environ.get('TERMINAL_CWD'),'parent_session_present':any(k.startswith(('HERMES_SESSION_','HERMES_TUI_')) for k in os.environ),
  'worker_label_present':'XSM_WORKER' in os.environ,'control_hint_present':'XSM_OWNED_CONTROL_FD' in os.environ,
  'billing_keys_present':any(k in os.environ for k in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY','HERMES_API_KEY','CUSTOM_API_KEY'))})
if __name__=='__main__':
 if '--version' in sys.argv:print('Hermes v0.22.5')
 else:main()
''')
        return root

    def run_turn(self, prompt, request='one', work='work', **kwargs):
        from xsm import workers
        return workers.run_owned('native-hermes', self.owner, prompt, work_context=work, request_id=request,
            reply_sender=lambda worker, row: workers.publish_owned(worker, row, wake=False), **kwargs)

    def test_native_opaque_context_reuse_and_actual_stored_reply(self):
        from xsm import workers
        first = self.run_turn('remember:retained native body')
        second = self.run_turn('recall', request='two')
        separate = self.run_turn('recall', request='three', work='separate')
        self.assertEqual(first['status'], 'reply-stored')
        self.assertEqual(second['result']['body'], 'retained native body')
        self.assertEqual(second['result']['native_session_id'], first['result']['native_session_id'])
        self.assertEqual(len(first['result']['native_session_id']), 70)
        self.assertNotEqual(separate['result']['native_session_id'], first['result']['native_session_id'])
        self.assertEqual(separate['result']['body'], 'no prior memory')
        repeated = self.run_turn('remember:retained native body')
        self.assertEqual(repeated['reply_id'], first['reply_id'])
        self.assertEqual(json.loads(Path(self.home,'native-memory.json').read_text())['calls'], 3)
        self.assertEqual(workers.owned_status('native-hermes', self.owner, 'one')['result'], first['result'])

    def test_native_environment_does_not_inherit_parent_session_or_billing_keys(self):
        with mock.patch.dict(os.environ, {'HERMES_SESSION_ID':'parent','HERMES_TUI_GATEWAY_URL':'ws://parent',
              'ANTHROPIC_API_KEY':'fixture','OPENAI_API_KEY':'fixture','CODEX_API_KEY':'fixture',
              'HERMES_API_KEY':'fixture','CUSTOM_API_KEY':'fixture'}):
            result = self.run_turn('remember:environment')
        with open(result['result']['execution']['stdout']) as f:
            rows=[json.loads(line) for line in f if line.strip()]
        environment=rows[-1]['native_environment']
        self.assertEqual(environment['home'], self.home)
        self.assertEqual(environment['cwd'], self.worker['cwd'])
        self.assertFalse(environment['parent_session_present'])
        self.assertFalse(environment['billing_keys_present'])
        self.assertFalse(environment['worker_label_present'])
        self.assertFalse(environment['control_hint_present'])

    def test_preflight_failure_is_known_not_started_and_does_not_lock_context_unknown(self):
        from xsm import workers
        self.binary.write_text('#!'+sys.executable+'\nprint("Hermes v0.22.5.1")\n')
        result = self.run_turn('must not execute')
        self.assertEqual(result['status'], 'error')
        self.assertIsNone(result['result'])
        self.assertFalse(Path(self.home,'native-memory.json').exists())
        self.assertIsNone(result['context'].get('unknown_request'))

    def test_changed_python_runtime_is_refused_even_when_console_version_still_matches(self):
        package=Path(self.tmp,'native-api/hermes_cli/main.py')
        package.write_text(package.read_text().replace("print('Hermes v0.22.5')","print('Hermes v0.23.1')"))
        result=self.run_turn('must not switch the admitted runtime')
        self.assertEqual(result['status'],'error')
        self.assertIsNone(result['result'])
        self.assertFalse(Path(self.home,'native-memory.json').exists())

    def test_real_output_readback_after_controller_failure_never_runs_again(self):
        from xsm import workers
        def crash(stage, request):
            if stage=='after-execution':raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_turn('remember:readback', checkpoint=crash)
        recovered=workers.reconcile_owned('native-hermes', self.owner, 'one',
            reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
        self.assertEqual(recovered['status'], 'reply-stored')
        self.assertEqual(recovered['result']['body'], 'readback')
        self.assertEqual(json.loads(Path(self.home,'native-memory.json').read_text())['calls'], 1)

    def test_profile_is_required_and_cannot_supply_its_own_executable(self):
        from xsm import workers
        with self.assertRaisesRegex(workers.WorkerError, 'owned xsm binding'):
            workers.create_owned('hermes', caller=self.owner, name='unmanaged', home=self.tmp+'/unmanaged')
        with mock.patch.dict(os.environ, {'XSM_HERMES':'relative-hermes'}), \
                self.assertRaisesRegex(workers.WorkerError, 'operator PATH'):
            workers.create_owned('hermes', caller=self.owner, name='bad-executable', home=self.home)

    def test_native_catalog_selection_is_separate_from_classic_spawn(self):
        from xsm import cli, native_workers, operation_schema
        self.assertIn('hermes',native_workers.runtimes())
        owned=next(tool for tool in operation_schema.TOOLS if tool['name']=='xsm_owned')
        self.assertIn('hermes',owned['inputSchema']['properties']['runtime']['enum'])
        self.assertEqual(cli.build_parser().parse_args(['owned','create','x','--runtime','hermes']).runtime,'hermes')

    def test_native_provider_reply_is_read_and_acked_by_generic_parent(self):
        from xsm import protocol, registry, workers
        connection=protocol.Connection();self.addCleanup(connection.close)
        connection.dispatch('initialize',{'protocolVersion':'1'})
        opened=connection.dispatch('session.open',{'runtime':'fixture','profile':'native-parent',
            'conversation':'generic','cwd':self.tmp,'capabilities':['messaging','inbox']})
        parent=connection.sessions[opened['session']].record
        workers.create_owned('hermes',caller=parent,name='hermes-generic',home=self.home)
        result=workers.run_owned('hermes-generic',parent,'remember:Hermes generic reply',
            work_context='generic',request_id='generic',
            reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
        self.assertEqual(result['status'],'reply-stored',result.get('send_evidence'))
        packet=connection.dispatch('operation.call',{'session':opened['session'],
            'operation':'xsm_inbox','arguments':{}})
        self.assertEqual(len(packet['claims']),1,packet)
        self.assertIn('Hermes generic reply',packet['messages'][0])
        self.assertEqual(registry.by_session('hermes',result['result']['native_session_id'])['state'],'ended')
        ack=connection.dispatch('operation.call',{'session':opened['session'],'operation':'xsm_ack',
            'arguments':{'tokens':[packet['claims'][0]['token']]}})
        self.assertEqual(ack['acked'],[result['reply_id']])

    def test_fresh_runner_cannot_adopt_an_existing_protocol_conversation(self):
        from xsm import protocol, workers
        connection=protocol.Connection();self.addCleanup(connection.close)
        connection.dispatch('initialize',{'protocolVersion':'1'})
        ordinary='ordinary-native-conversation'
        connection.dispatch('session.open',{'runtime':'hermes','profile':self.home,
            'conversation':ordinary,'cwd':self.tmp,'capabilities':['messaging','inbox']})
        result=self.run_turn('must not adopt',executor=lambda *args:{'body':'not owned',
            'outcome':'succeeded','native_session_id':ordinary})
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['result'])
        self.assertIn('existing ordinary conversation',result.get('error') or result.get('unknown_reason') or str(result))

    def test_binding_records_worker_budget_before_the_native_task_starts(self):
        from xsm import protocol, workers
        bind=workers._bind_owned_native
        observed=[]
        connections=[]
        def inspect_binding(worker, request, native_id, before):
            result=bind(worker,request,native_id,before)
            self.assertFalse(Path(self.home,'native-memory.json').exists())
            connection=protocol.Connection();connections.append(connection)
            connection.dispatch('initialize',{'protocolVersion':'1'})
            opened=connection.dispatch('session.open',{'runtime':'hermes','profile':self.home,
                'conversation':native_id,'cwd':self.tmp,'capabilities':['messaging','inbox']})
            actor=connection.sessions[opened['session']].record
            with self.assertRaisesRegex(workers.WorkerError,'max_depth'):
                workers.depth_budget(actor)
            self.assertEqual(workers.for_record(actor)['id'],worker['id'])
            other=connection.dispatch('session.open',{'runtime':'hermes','profile':self.home+'-other',
                'conversation':native_id,'cwd':self.tmp,'capabilities':['messaging','inbox']})
            self.assertEqual(workers.depth_budget(connection.sessions[other['session']].record),(1,1))
            observed.append(native_id)
            return result
        try:
            with mock.patch.object(workers,'_bind_owned_native',side_effect=inspect_binding):
                result=self.run_turn('remember:bound before model')
        finally:
            for connection in connections:connection.close()
        self.assertEqual(result['status'],'reply-stored',result)
        self.assertEqual(observed,[result['result']['native_session_id']])

    def test_valid_looking_native_output_without_pre_turn_binding_is_not_accepted(self):
        package=Path(self.tmp,'native-api/hermes_cli/main.py')
        package.write_text(package.read_text().replace('emitter.bind_session(sid)','emitter.sid=sid'))
        result=self.run_turn('must not accept an unbound result')
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['result'])

    def test_ordinary_native_identity_is_refused_before_the_task_body_runs(self):
        from xsm import protocol
        connection=protocol.Connection();self.addCleanup(connection.close)
        connection.dispatch('initialize',{'protocolVersion':'1'})
        native_id='existing-native-user-conversation'
        connection.dispatch('session.open',{'runtime':'hermes','profile':self.home,
            'conversation':native_id,'cwd':self.tmp,'capabilities':['messaging','inbox']})
        package=Path(self.tmp,'native-api/hermes_cli/main.py')
        text=package.read_text();start=text.index(' sid=args[');end=text.index('\n emitter=',start)
        package.write_text(text[:start]+' sid='+repr(native_id)+text[end:])
        result=self.run_turn('must never execute in an ordinary session')
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['result'])
        self.assertFalse(Path(self.home,'native-memory.json').exists())

    def test_admitted_executable_metadata_is_part_of_the_frozen_request(self):
        from xsm import owned_requests, workers
        first=self.run_turn('remember:frozen provider')
        current=workers.load('native-hermes');current['native_provider']['python']='/changed/python'
        workers.save(current)
        with self.assertRaisesRegex(owned_requests.OwnedError,'worker plan'):
            self.run_turn('remember:frozen provider')
        self.assertEqual(workers.owned_status('native-hermes',self.owner,'one')['result'],first['result'])
        self.assertEqual(json.loads(Path(self.home,'native-memory.json').read_text())['calls'],1)
