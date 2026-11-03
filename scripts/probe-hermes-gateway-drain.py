#!/usr/bin/env python3
"""Actual Hermes gateway FIFO drain and installed plugin hooks; scripted provider, no real model/UI."""
import argparse
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-source',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();repo=Path(__file__).resolve().parents[1];source=args.native_source.resolve()
out=args.output.absolute();out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
root=Path(tempfile.mkdtemp(prefix='xsm-hermes-gateway-drain-')).resolve();root.chmod(0o700)
for name in ('home','hermes','state','workspace'):(root/name).mkdir(mode=0o700)
env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
env.update(HOME=str(root/'home'),HERMES_HOME=str(root/'hermes'),XSM_HOME=str(root/'state'),
    TERMINAL_CWD=str(root/'workspace'),PYTHONDONTWRITEBYTECODE='1')
os.environ.clear();os.environ.update(env);os.chdir(root/'workspace');sys.path[:0]=[str(repo),str(source),str(repo/'clients/python')]
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
assert commit==subprocess.check_output(['git','-C',str(source),'rev-parse','v0.22.5^{}'],text=True).strip()
subprocess.run(['git','-C',str(source),'diff','--quiet','HEAD'],check=True)
logging.disable(logging.CRITICAL)
nonce=os.urandom(8).hex();original='XSM_NATIVE_WAKE_'+nonce;message_id='native-wake-'+nonce
report=dict(status='starting',root=str(root),nativeSourceCommit=commit,modelCalls=0,checks=[],
    scope='actual pinned local FIFO drain, installed plugin and AIAgent hooks with scripted provider; no real inference/UI/messenger')
requests=[];phase='warmup';acked=False

def check(name,condition):
    if not condition:
        report['failedCheck']=name
        if threading.current_thread() is not threading.main_thread():
            os.kill(os.getpid(),signal.SIGINT)
        raise AssertionError(name)
    report['checks'].append(name)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        global acked
        if len(requests)>=16:
            report['fixtureFailure']='scripted provider exceeded sixteen requests'
            os.kill(os.getpid(),signal.SIGINT)
            return
        value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        available={tool.get('function',{}).get('name') for tool in value.get('tools',[])}
        requests.append(dict(phase=phase,tools=sorted(name for name in available if name),
            originalObserved=original in json.dumps(value,ensure_ascii=False)))
        (out/('request-%d.json'%len(requests))).write_text(json.dumps(value,indent=2)+'\n')
        # Only a primary tool-enabled call drives this fixture; auxiliaries stay separate.
        text='Explicit auxiliary fixture';name=None;arguments=None
        if available:
            messages=value.get('messages',[])
            wire=json.dumps(messages,ensure_ascii=False)
            if phase=='warmup':text='XSM_CONTEXT_WARMUP'
            else:
                check('actual provider request contains complete original as user content',
                    any(message.get('role')=='user' and original in json.dumps(message.get('content','')) for message in messages))
                if phase=='fyi':
                    check('quiet original reaches actual natural-turn context marker','[XSM peer context ' in wire)
                def find_acked(item):
                    if isinstance(item,dict):
                        if message_id in item.get('acked',[]):return True
                        return any(find_acked(value) for value in item.values())
                    if isinstance(item,list):return any(find_acked(value) for value in item)
                    if isinstance(item,str):
                        try:decoded=json.loads(item)
                        except (ValueError,TypeError):return False
                        return find_acked(decoded) if not isinstance(decoded,str) else False
                    return False
                results=[message.get('content','') for message in messages if message.get('role')=='tool']
                acked=any(find_acked(result) for result in results)
                found_ack=any('xsm_ack' in result and 'queries is required' not in result for result in results)
                if acked:text='XSM_CONTEXT_COMPLETE'
                elif not found_ack:name='tool_search';arguments={'queries':['xsm ack'],'limit':5}
                else:
                    tokens=None
                    for message in messages:
                        content=message.get('content')
                        if message.get('role')=='user' and isinstance(content,str):
                            found=re.search(r'After reading, call xsm_ack with tokens: (\[[^\n]+?\])',content)
                            if found:tokens=json.loads(found.group(1))
                    check('scripted model read exact ACK instructions in native user context',bool(tokens))
                    if 'xsm_ack' in available:name='xsm_ack';arguments={'tokens':tokens}
                    else:name='tool_call';arguments={'calls':[{'name':'xsm_ack','arguments':{'tokens':tokens}}]}
        delta={'content':text};reason='stop'
        if name:delta={'tool_calls':[{'index':0,'id':'context-fixture-'+str(len(requests)),'type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]};reason='tool_calls'
        packets=[dict(id='fixture',object='chat.completion.chunk',created=int(time.time()),model='explicit-fixture',
            choices=[dict(index=0,delta=delta,finish_reason=None)]),dict(id='fixture',object='chat.completion.chunk',
            created=int(time.time()),model='explicit-fixture',choices=[dict(index=0,delta={},finish_reason=reason)])]
        body=(''.join('data: '+json.dumps(packet)+'\n\n' for packet in packets)+'data: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
settings={'model':{'default':'fixture','provider':'custom','base_url':'http://127.0.0.1:'+str(server.server_port)+'/v1',
    'api_key':'explicit-fixture','api_mode':'chat_completions'},'fallback_providers':[],
    'agent':{'max_turns':6,'skip_context_files':True},'memory':{'enabled':False},
    'plugins':{'enabled':['xsm'],'entries':{'xsm':{'settings':{'native_context':True}}}},'toolsets':['xsm'],
    'terminal':{'cwd':str(root/'workspace')}}
settings['plugins']['entries']['xsm']['allow_gateway_injection']=True
settings['plugins']['entries']['xsm']['settings']['native_wake']=True
(root/'hermes/config.yaml').write_text(json.dumps(settings));binding=None

async def scenario():
    global binding, phase, original, message_id, acked
    import asyncio
    from xsm import host_install
    installation=host_install.apply('hermes',str(root/'hermes'));report['runtimeRoot']=installation['runtime_root']
    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from gateway.session_authority import initialize_session_authority
    from gateway.session_contract import Principal, Submission
    from gateway.session_local import create_local_session
    from hermes_state import SessionDB
    from hermes_state_runtime import list_session_admissions
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    runner=GatewayRunner(GatewayConfig(sessions_dir=root/'hermes/sessions'))
    db=SessionDB(root/'hermes/state.db');runner.session_store._db=db;runner._session_db=db
    runner._gateway_loop=asyncio.get_running_loop();runner._running=True
    runner._install_plugin_message_injector()
    manager=get_plugin_manager();manager.discover_and_load()
    entry=registry.get_entry('xsm_inbox',scope=manager.scope_key)
    check('actual plugin loads with native permission at entry root',entry is not None)
    for cell in getattr(entry.handler,'__closure__',()) or ():
        candidate=cell.cell_contents
        if type(candidate).__name__=='HermesBinding':binding=candidate;break
    check('installed binding opted into native wake',binding is not None and binding.native_wake)
    authority=await initialize_session_authority(runner,profile_id='default',instance_id='drain-probe',db=db)
    try:
        actor=Principal('drain-probe','default',frozenset({'session:create','session:submit','session:read'}),'fixture')
        ref=create_local_session(authority,actor,dict(request_id='drain-local',source='cli',cwd=str(root/'workspace'),
            model='fixture',provider='custom',base_url=settings['model']['base_url'],api_key='explicit-fixture',toolsets=['xsm']))
        live=authority.sessions[ref.session_id]
        async def terminal(predicate):
            deadline=asyncio.get_running_loop().time()+60
            while asyncio.get_running_loop().time()<deadline:
                rows=list_session_admissions(db,session_id=ref.session_id,pending_only=False)
                found=next((row for row in rows if predicate(row) and row['status']=='terminal'),None)
                if found:return found
                await asyncio.sleep(.02)
            report['pendingRows']=rows
            raise TimeoutError('actual native FIFO did not reach terminal')
        receipt=await authority.submit(actor,Submission('warmup',ref,{'text':'Warm up the explicit native hook fixture; do not call tools.'},'queue'))
        warm=await terminal(lambda row:row['admission_id']==receipt.admission_id)
        check('actual gateway warmup FIFO completes',warm['outcome']=='completed')
        entry=runner.session_store.lookup_by_session_key(live.route);sid=entry.session_id
        async def host_description():return (await binding.hosts[sid][1]).session
        recipient=await asyncio.to_thread(binding._run,host_description())
        check('native hook opened exact gateway host with events','events' in recipient['capabilities'])
        from xsm_client import XsmClient
        command=[sys.executable,'-B','-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",str(repo),'protocol','serve','--stdio']
        async with await XsmClient.connect(command,cwd=str(root/'workspace'),env=env) as sender:
            origin=await sender.session_open(runtime='gateway-drain-sender',profile='isolated',conversation='sender',cwd=str(root/'workspace'))
            phase='awake'
            await sender.operation_call(origin['session'],'xsm_send',dict(target='ref:'+recipient['ref'],text=original,wake='auto',request_id=message_id))
            row=await terminal(lambda row:original in row['payload'].get('text',''))
            check('XSM alone drives native FIFO turn to completion',row['outcome']=='completed')
            check('actual native tool acknowledges exact original',acked)
            async def inbox():return await (await binding.hosts[sid][1]).call('xsm_inbox',{'message_ids':[message_id]})
            packet=await asyncio.to_thread(binding._run,inbox())
            check('native ACK suppresses canonical redelivery',packet['claims']==[])
            check('actual native turns leave no pending staged context',not binding.native_context.pending)
            phase='fyi';original='XSM_NATIVE_QUIET_'+nonce;message_id='native-quiet-'+nonce;acked=False
            before_requests=len(requests)
            before_rows=len(list_session_admissions(db,session_id=ref.session_id,pending_only=False))
            sent=await sender.operation_call(origin['session'],'xsm_send',dict(target='ref:'+recipient['ref'],
                text=original,wake='never',request_id=message_id))
            check('strict FYI is stored without native reach claim',sent['send']['status']=='stored' and
                sent['send']['runtime_reached'] is False)
            await asyncio.sleep(.3)
            check('FYI creates no FIFO turn or provider call in observed idle window',len(requests)==before_requests and
                len(list_session_admissions(db,session_id=ref.session_id,pending_only=False))==before_rows)
            natural=await authority.submit(actor,Submission('natural-fyi',ref,
                {'text':'Read the peer FYI context in this next natural turn.'},'queue'))
            quiet=await terminal(lambda row:row['admission_id']==natural.admission_id)
            check('actual natural FIFO turn consumes quiet context and completes',quiet['outcome']=='completed' and acked)
            packet=await asyncio.to_thread(binding._run,inbox())
            check('actual FYI native ACK suppresses canonical redelivery',packet['claims']==[])
            report.update(nativeSessionId=sid,nativeAdmissionId=row['admission_id'],providerRequests=len(requests),requests=requests)
    finally:
        runner._running=False;runner._clear_plugin_message_injector()
        await asyncio.to_thread(manager.unload,'xsm');report['pluginUnloaded']=True
        db.close()

try:
    import asyncio
    def deadline(*_):raise TimeoutError('gateway drain probe exceeded outer deadline')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(100)
    asyncio.run(scenario());report['status']='passed'
except BaseException as error:
    report.update(status='failed',failureType=type(error).__name__,failure=str(error));raise
finally:
    signal.alarm(0)
    if binding is not None and not binding.closed:
        try:
            from hermes_cli.plugins import get_plugin_manager
            get_plugin_manager().unload('xsm');report['pluginUnloaded']=True
        except Exception as error:
            report.update(status='failed',unloadFailure=type(error).__name__)
    server.shutdown();server.server_close();thread.join(timeout=2)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report.get(key) for key in ('status','checks','failure','pluginUnloaded')}))
