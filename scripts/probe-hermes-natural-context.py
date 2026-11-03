#!/usr/bin/env python3
"""Actual Hermes v0.22.5 hooks/context/tool ACK; scripted provider, no real model/UI."""
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
root=Path(tempfile.mkdtemp(prefix='xsm-hermes-natural-context-')).resolve();root.chmod(0o700)
for name in ('home','hermes','state','workspace'):(root/name).mkdir(mode=0o700)
env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
env.update(HOME=str(root/'home'),HERMES_HOME=str(root/'hermes'),XSM_HOME=str(root/'state'),
    TERMINAL_CWD=str(root/'workspace'),PYTHONDONTWRITEBYTECODE='1')
os.environ.clear();os.environ.update(env);os.chdir(root/'workspace');sys.path[:0]=[str(repo),str(source),str(repo/'clients/python')]
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
assert commit==subprocess.check_output(['git','-C',str(source),'rev-parse','v0.22.5^{}'],text=True).strip()
subprocess.run(['git','-C',str(source),'diff','--quiet','HEAD'],check=True)
logging.disable(logging.CRITICAL)
nonce=os.urandom(8).hex();original='XSM_NATIVE_FYI_'+nonce;message_id='native-fyi-'+nonce
report=dict(status='starting',root=str(root),nativeSourceCommit=commit,modelCalls=0,checks=[],
    scope='actual pinned Hermes AIAgent pre_llm/pre_api hooks and tool registry; scripted provider; no native UI, idle wake or real inference')
requests=[];phase='warmup';acked=False

def check(name,condition):
    if not condition:raise AssertionError(name)
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
        # Only a primary tool-enabled call drives this fixture; auxiliaries stay separate.
        text='Explicit auxiliary fixture';name=None;arguments=None
        if available:
            messages=value.get('messages',[])
            wire=json.dumps(messages,ensure_ascii=False)
            if phase=='warmup':text='XSM_CONTEXT_WARMUP'
            else:
                check('actual provider request contains complete original and context marker',original in wire and '[XSM peer context ' in wire)
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
        requests.append(dict(phase=phase,tools=sorted(name for name in available if name),originalObserved=original in json.dumps(value,ensure_ascii=False)))
        (out/('request-%d.json'%len(requests))).write_text(json.dumps(value,indent=2)+'\n')
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
(root/'hermes/config.yaml').write_text(json.dumps(settings));binding=None
try:
    from xsm import host_install
    installation=host_install.apply('hermes',str(root/'hermes'));report['runtimeRoot']=installation['runtime_root']
    from run_agent import AIAgent
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    agent=AIAgent(model='fixture',provider='custom',base_url=settings['model']['base_url'],api_key='explicit-fixture',
        api_mode='chat_completions',quiet_mode=True,enabled_toolsets=['xsm'],run_budget_seconds=60,max_iterations=6)
    warm=agent.run_conversation('Warm up the explicit native hook fixture; do not call tools.')
    check('actual native warmup completes',str(warm.get('final_response','')).strip()=='XSM_CONTEXT_WARMUP')
    entry=registry.get_entry('xsm_inbox',scope=get_plugin_manager().scope_key)
    for cell in getattr(entry.handler,'__closure__',()) or ():
        candidate=cell.cell_contents
        if type(candidate).__name__=='HermesBinding':binding=candidate;break
    check('native plugin opted into natural context',binding is not None and binding.native_context is not None)
    async def describe():return (await binding._host(agent.session_id,str(root/'workspace'))).session
    recipient=binding._run(describe())
    check('context-only native host does not advertise background events','events' not in recipient['capabilities'])
    async def send_and_close():
        from xsm_client import XsmClient
        command=[sys.executable,'-B','-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",str(repo),'protocol','serve','--stdio']
        async with await XsmClient.connect(command,cwd=str(root/'workspace'),env=env) as sender:
            origin=await sender.session_open(runtime='natural-context-sender',profile='isolated',conversation='sender',cwd=str(root/'workspace'))
            value=await sender.operation_call(origin['session'],'xsm_send',dict(target='ref:'+recipient['ref'],text=original,wake='never',request_id=message_id))
            check('FYI is stored without native wake',value['send']['status']=='stored' and value['send']['runtime_reached'] is False)
    asyncio.run(send_and_close());before=len(requests);time.sleep(.35)
    check('idle FYI causes no provider request',len(requests)==before)
    phase='natural'
    result=agent.run_conversation('Perform the next natural-turn fixture; read any peer context and acknowledge only after reading it.')
    check('actual native natural turn completes',str(result.get('final_response','')).strip()=='XSM_CONTEXT_COMPLETE')
    check('actual native tool acknowledges the exact original',acked)
    packet=json.loads(binding.handler('xsm_inbox')({'message_ids':[message_id]},session_id=agent.session_id))
    check('explicit ACK suppresses another canonical delivery',packet['claims']==[])
    check('context staging left no pending admission',not binding.native_context.pending)
    report.update(status='passed',nativeSessionId=agent.session_id,providerRequests=len(requests),requests=requests)
except BaseException as error:
    report.update(status='failed',failureType=type(error).__name__,failure=str(error));raise
finally:
    try:
        from hermes_cli.plugins import get_plugin_manager
        get_plugin_manager().unload('xsm');report['pluginUnloaded']=True
    except Exception as error:report.update(status='failed',unloadFailure=type(error).__name__)
    server.shutdown();server.server_close();thread.join(timeout=2)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report.get(key) for key in ('status','checks','failure','pluginUnloaded')}))
