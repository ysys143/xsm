"""Run only the explicitly owned two-Mac C fixture. Secret control stays in SSH stdin."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import shlex
import socket
import subprocess
import sys
import threading
import time

LOCAL=Path('/private/tmp/p11-C-av3sz_4j')
PEER=Path('/private/tmp/p11-C-_n_rujrd')
ARTIFACT=Path('/Users/jaesolshin/Documents/GitHub/cross-session-messaging/deliverables/p11-live')
SSH=['ssh','-oBatchMode=yes','-oConnectTimeout=5','-oStrictHostKeyChecking=yes','-oUpdateHostKeys=no','jaesol-macmini']
REAL_CODEX_HOME='/Users/jaesolshin/.codex-3'
TASK='P11-QA-40c1afc34bbd43c4'


def load_lib():
    spec=importlib.util.spec_from_file_location('C_fixture_lib',LOCAL/'code/C-fixture-lib.py')
    lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib);return lib


def read_line(proc,timeout=120):
    box=queue.Queue()
    def read():
        try:box.put(proc.stdout.readline())
        except BaseException as error:box.put(error)
    threading.Thread(target=read,daemon=True).start();value=box.get(timeout=timeout)
    if isinstance(value,BaseException):raise value
    if not value:raise RuntimeError('private peer control EOF')
    return json.loads(value)


def stage_peer(lib):
    files={name:(LOCAL/'code'/name).read_text() for name in ('C-fixture-lib.py','C-peer-agent.py','C-native-base.py')}
    binary=(LOCAL/'reason-network').read_bytes();assert lib.sha(binary)==lib.ENGINE_SHA
    code=r'''
import hashlib,json,os,pathlib,sys
root=pathlib.Path('/private/tmp/p11-C-_n_rujrd').resolve();assert root.is_dir() and root.stat().st_uid==os.getuid()
header=json.loads(sys.stdin.buffer.readline());data=sys.stdin.buffer.read();assert hashlib.sha256(data).hexdigest()==header['sha256']
(root/'code').mkdir(mode=0o700,exist_ok=True)
for name,text in header['files'].items():
 assert name in ('C-fixture-lib.py','C-peer-agent.py','C-native-base.py')
 p=root/'code'/name;p.write_text(text);p.chmod(0o600)
p=root/'reason-network';p.write_bytes(data);p.chmod(0o700)
print(json.dumps({'staged':True,'binary_sha256':hashlib.sha256(data).hexdigest(),'root':str(root),'role':'controlled-peer'}))
'''
    payload=(json.dumps({'files':files,'sha256':lib.ENGINE_SHA})+'\n').encode()+binary
    stage=subprocess.run(SSH+['/usr/bin/python3 -c '+shlex.quote(code)],input=payload,capture_output=True,timeout=30)
    if stage.returncode:raise RuntimeError('private stage failed, exit '+str(stage.returncode))
    return json.loads(stage.stdout)


class Remote:
    def __init__(self,lib):
        self.lib=lib;self.seq=0
        self.proc=subprocess.Popen(SSH+['PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u '+shlex.quote(str(PEER/'code/C-peer-agent.py'))+' '+shlex.quote(str(PEER))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.ready=read_line(self.proc,15)
        self.handle={'local_ssh_pid':self.proc.pid,'alive_after_ready':self.proc.poll() is None,'peer_control_pid':self.ready['pid']}
    def call(self,op,**args):
        self.seq+=1;request=dict(id=self.seq,op=op,**args)
        self.proc.stdin.write(json.dumps(request)+'\n');self.proc.stdin.flush();request.clear()
        reply=read_line(self.proc,160)
        if not reply.get('ok'):
            error=RuntimeError('private peer operation '+op+' failed')
            error.private_error=reply.get('error');error.private_operation=reply.get('fixture_operation');raise error
        return reply['result']
    def cleanup(self):
        result=self.call('cleanup')
        self.proc.stdin.close();self.proc.wait(timeout=10)
        if self.proc.returncode!=0:raise RuntimeError('owned SSH control exit nonzero')
        self.proc.stdout.close();self.proc.stderr.close()
        return dict(result,ssh_exit_code=self.proc.returncode,control_handle=self.handle)


def request(phase,previous=None):
    body=('Request marker: '+TASK+'; phase: '+phase+'. Review the claim 2+2=5. '
          'Return JSON with request_id, phase, claim_valid, corrected_sum, and a counterexample in one short sentence. '
          'Compute honestly; do not use any tools.')
    if previous:body+=' Previous native answer: '+json.dumps({'claim_valid':previous['claim_valid'],'corrected_sum':previous['corrected_sum']})+'. Recheck it independently.'
    return body


def wait_reply(node,request_id,timeout=25):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        for message in node.inbox():
            if message.get('reply_to')==request_id:
                answer=json.loads(message['body'])
                if message.get('from')!='p11-c-peer/qa-peer':raise RuntimeError('reply sender outside controlled fixture')
                if answer.get('request_id')!=TASK or answer.get('claim_valid') is not False or answer.get('corrected_sum')!=4:
                    raise RuntimeError('native math/request validation failed')
                return message,answer
        time.sleep(.1)
    raise TimeoutError('native reply absent from local C engine inbox')


def wait_request(peer,phase,digest,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:return peer.call('process',phase=phase,body_sha256=digest)
        except RuntimeError as exc:
            data=getattr(exc,'private_error',{}) or {}
            if data.get('safe_error_terms') and any(v in data['safe_error_terms'] for v in ('permission denied','operation not permitted','tcc','login','sign in')):raise
            # Only the transient inbox-not-yet-arrived condition can be polled.
            if getattr(exc,'private_operation',None)!='native-receive':raise
            time.sleep(.2)
    raise TimeoutError('private peer did not receive expected request')


def run():
    os.umask(0o077)
    lib=load_lib();peer=None;local=None
    out={'scope':'C private two-controlled-node carrier fixture; not D12 product choice',
         'task_marker':TASK,'local_root':str(LOCAL),'peer_root':str(PEER),'binary_sha256':lib.ENGINE_SHA,
         'network_team_created':False,'production_team_used':False,'native_model_calls':0,'passed':False,
         'phases':[],'private_plan_sha256':json.loads((LOCAL/'plan-sha256.json').read_text())['sha256']}
    def save():lib.write_json(LOCAL/'C-result.json',out)
    try:
        out['stage_peer']=stage_peer(lib);save()
        os.environ['HOME']=str(LOCAL/'home')
        local=lib.Node(LOCAL,'local',REAL_CODEX_HOME)
        out['local_initial_handle']=local.start();out['local_endpoint']=local.endpoint_hash()
        peer=Remote(lib);out['peer_control_handle']=peer.handle
        started=peer.call('start');out['peer_initial_handle']=started['handle'];out['peer_endpoint']=started['endpoint'];save()
        out['private_create']=local.create();out['network_team_created']=True;save()
        capability=local.capability()
        cap_hash=lib.sha(capability)
        out['private_join']=peer.call('join',ticket=capability)
        capability=None
        if out['private_join']['capability_sha256']!=cap_hash:raise RuntimeError('capability transfer hash mismatch')
        if out['private_join']['team_id_sha256']!=out['private_create']['team_id_sha256']:raise RuntimeError('private team hash mismatch')
        out['capability_handling']={'sha256':cap_hash,'channel':'Python memory -> existing SSH stdin -> peer explicit private IPC','raw_stored_or_logged':False};save()
        expected={out['local_endpoint']['endpoint_sha256'],out['peer_endpoint']['endpoint_sha256']}
        deadline=time.monotonic()+60
        while True:
            left,right=local.team(),peer.call('team')
            if left['member_count']>2 or right['member_count']>2:raise RuntimeError('membership outside controlled nodes')
            left_ids={m['endpoint_sha256'] for m in left['machines']};right_ids={m['endpoint_sha256'] for m in right['machines']}
            if left_ids==right_ids==expected and all(m['online'] for m in left['machines']+right['machines']):break
            if time.monotonic()>deadline:raise TimeoutError('two private members did not become online')
            time.sleep(.5)
        out['membership_before']={'local':left,'peer':right,'only_controlled_endpoints':True}
        out['private_clients']={'local':local.register(),'peer':peer.call('register')};save()
        previous=None;cached=None;native_call_counts=[]
        for phase in ('first','followup'):
            body=request(phase,previous);start=time.perf_counter();sent=local.send('p11-c-peer/qa-peer',body)
            message_id=sent['ids'][0]
            native=wait_request(peer,phase,lib.sha(body))
            message,answer=wait_reply(local,message_id)
            if lib.sha(message['body'])!=native['answer_sha256']:raise RuntimeError('native/transport answer hash mismatch')
            out['phases'].append({'phase':phase,'roundtrip_ms':round((time.perf_counter()-start)*1000,3),
                'request_engine_id_sha256':lib.sha(message_id),'reply_engine_id_sha256':lib.sha(message['id']),
                'request_body_sha256':lib.sha(body),'answer_body_sha256':lib.sha(message['body']),
                'actual_json_answer':answer,'native':native,'readback':{'local':local.team(),'peer':peer.call('team')}})
            out['native_model_calls']+=int(native['actual_native_call']);previous=answer;save()
            if phase=='first':local.ack([message['id']])
            else:cached=(message,answer)
        before_counts=peer.call('counts')['native_model_calls'];before_endpoint=local.endpoint_hash()
        start=time.perf_counter();old_handle=local.handles[-1].copy();local.restart();local.register()
        message,answer=wait_reply(local,cached[0]['reply_to'])
        after_counts=peer.call('counts')['native_model_calls'];after_endpoint=local.endpoint_hash()
        if message['id']!=cached[0]['id'] or message['body']!=cached[0]['body']:raise RuntimeError('cached engine reply changed across restart')
        if before_counts!=after_counts or before_endpoint!=after_endpoint:raise RuntimeError('cached readback reran model or changed endpoint')
        out['phases'].append({'phase':'reconnect-cached-readback','roundtrip_ms':round((time.perf_counter()-start)*1000,3),
           'reply_engine_id_sha256':lib.sha(message['id']),'answer_body_sha256':lib.sha(message['body']),
           'original_reply_id_unchanged':True,'original_body_unchanged':True,'model_rerun':False,
           'endpoint_unchanged':True,'old_private_handle':old_handle,'new_private_handle':local.handles[-1],
           'readback':{'local':local.team(),'peer':peer.call('team')}});local.ack([message['id']]);save()
        body=request('after-reconnect',answer);start=time.perf_counter();sent=local.send('p11-c-peer/qa-peer',body)
        native=wait_request(peer,'after-reconnect',lib.sha(body));message,answer=wait_reply(local,sent['ids'][0]);local.ack([message['id']])
        out['phases'].append({'phase':'after-reconnect','roundtrip_ms':round((time.perf_counter()-start)*1000,3),
            'request_engine_id_sha256':lib.sha(sent['ids'][0]),'reply_engine_id_sha256':lib.sha(message['id']),
            'actual_json_answer':answer,'native':native,'readback':{'local':local.team(),'peer':peer.call('team')}})
        out['native_model_calls']+=int(native['actual_native_call'])
        out['passed']=out['native_model_calls']==3 and all(m['member_count']==2 for m in out['phases'][-1]['readback'].values())
        save()
    except BaseException as exc:
        out['failure']={'operation':getattr(exc,'operation','controller'),'error':getattr(exc,'detail',getattr(exc,'private_error',lib.safe_error(exc)))};save()
    finally:
        out['cleanup']={}
        if peer:
            try:out['cleanup']['peer']=peer.cleanup()
            except BaseException as exc:
                out['cleanup']['peer_error']=lib.safe_error(exc)
                if peer.proc.poll() is None:peer.proc.terminate();peer.proc.wait(timeout=8)
        if local:
            try:out['cleanup']['local']=local.cleanup()
            except BaseException as exc:out['cleanup']['local_error']=lib.safe_error(exc)
        save()
    print(json.dumps({'passed':out['passed'],'native_model_calls':out['native_model_calls'],
                      'failure':out.get('failure'),'cleanup_roles':list(out['cleanup']),'result':str(LOCAL/'C-result.json')}),flush=True)


if __name__=='__main__':run()
