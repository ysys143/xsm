"""Private two-node Reason Network fixture. No ambient Reason IPC or team access."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import threading
import time

ENGINE_SHA='6ac4bb4837469867edc2dba3cbbd6e4dd9fb18ad0389db69ff6ef21683317a44'
TASK='P11-QA-40c1afc34bbd43c4'
PHASES=('first','followup','after-reconnect')


def sha(value):
    return hashlib.sha256(value if isinstance(value,bytes) else str(value).encode()).hexdigest()


def write_json(path,value):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.new')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,path)


def process_start(pid):
    return subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True,timeout=5).stdout.strip() or None


def safe_error(value):
    text=str(value).lower()
    terms=[name for name in ('permission denied','operation not permitted','tcc','login','sign in','unauthorized','timed out','unreachable','refused','not connected') if name in text]
    return {'error_type':type(value).__name__,'error_sha256':sha(str(value)),'safe_error_terms':terms}


class FixtureError(Exception):
    def __init__(self,operation,detail):
        self.operation=operation;self.detail=safe_error(detail)
        super().__init__('private fixture operation failed: '+operation)


class IPC:
    def __init__(self,path):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(100)
        self.sock.connect(str(path));self.reader=self.sock.makefile('rb');self.seq=0
    def call(self,op,**args):
        self.seq+=1;self.sock.sendall((json.dumps(dict(id=self.seq,op=op,**args))+'\n').encode())
        while True:
            line=self.reader.readline()
            if not line:raise FixtureError(op,RuntimeError('private IPC closed'))
            reply=json.loads(line)
            if reply.get('id')!=self.seq:continue
            if not reply.get('ok'):raise FixtureError(op,RuntimeError(reply.get('error','IPC refused')))
            return reply.get('result')
    def close(self):
        try:self.reader.close()
        finally:self.sock.close()


class Node:
    def __init__(self,root,role,native_home):
        self.root=Path(root).resolve();self.role=role;self.native_home=native_home
        if not self.root.name.startswith('p11-C-') or self.root.stat().st_uid!=os.getuid():raise ValueError('not an owned fixture root')
        self.root.chmod(0o700);self.state=self.root/'state';self.sock=self.state/'network.sock';self.home=self.root/'home'
        if len(str(self.sock).encode())>=100:raise ValueError('private socket would escape into fallback directory')
        self.binary=self.root/'reason-network';self.proc=None;self.client=None;self.handles=[];self.model_handles=[];self.log_threads=[]
        self.key='fixture:p11-c-'+role;self.person='p11-c-'+role;self.name='qa-'+role;self.address=self.person+'/'+self.name
        self.events=[];self.cache={};self.permission_failure=False
        for name in ('state','home','tmp','project','engine-codex','engine-claude','xdg-config','xdg-state','xdg-data'):
            (self.root/name).mkdir(mode=0o700,exist_ok=True)
        self.config=self.state/'config.toml'
        if not self.config.exists():
            self.config.write_text('person = "'+self.person+'"\nlan = false\ntray = false\nreason = false\nauto_update = false\nshare_unmanaged = false\nshare_paths = false\n')
            self.config.chmod(0o600)
        self.env=dict(os.environ)
        for key in list(self.env):
            if key.startswith(('REASON','TINCAN','CLAUDE','CODEX','XSM')) or key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN'):
                self.env.pop(key,None)
        self.env.update(HOME=str(self.home),REASON_NETWORK_HOME=str(self.state),REASON_NETWORK_NO_SERVICE='1',
                        REASON_NETWORK_NO_TRAY='1',REASON_NETWORK_NO_MDNS='1',CODEX_HOME=str(self.root/'engine-codex'),
                        CLAUDE_CONFIG_DIR=str(self.root/'engine-claude'),XDG_CONFIG_HOME=str(self.root/'xdg-config'),
                        XDG_DATA_HOME=str(self.root/'xdg-data'),XDG_STATE_HOME=str(self.root/'xdg-state'),TMPDIR=str(self.root/'tmp'))
        write_json(self.root/'fixture-ownership.json',{'uid':os.getuid(),'role':role,'scope':'private controlled fixture only'})
    def log_hashes(self,stream,pid):
        target=self.root/('engine-'+str(pid)+'-log-hashes.jsonl')
        with target.open('w') as out:
            target.chmod(0o600)
            for line in stream:
                category='permission' if any(t in line.lower() for t in ('permission denied','operation not permitted')) or re.search(r'\btcc\b',line.lower()) else 'engine-status'
                if category=='permission':self.permission_failure=True
                out.write(json.dumps({'line_sha256':sha(line),'bytes':len(line.encode()),'category':category})+'\n');out.flush()
    def start(self):
        if self.proc and self.proc.poll() is None:raise ValueError('owned engine already alive')
        if sha(self.binary.read_bytes())!=ENGINE_SHA:raise ValueError('engine checksum mismatch')
        self.proc=subprocess.Popen([str(self.binary),'daemon'],cwd=str(self.root/'project'),env=self.env,
                                   stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        handle={'pid':self.proc.pid,'lstart':process_start(self.proc.pid),'binary_sha256':ENGINE_SHA,
                'alive_after_start':self.proc.poll() is None,'role':self.role,'socket':str(self.sock)}
        self.handles.append(handle);write_json(self.root/'engine-handles.json',self.handles)
        thread=threading.Thread(target=self.log_hashes,args=(self.proc.stdout,self.proc.pid),daemon=True);thread.start();self.log_threads.append(thread)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if self.proc.poll() is not None:raise FixtureError('engine-start',RuntimeError('private engine exited '+str(self.proc.returncode)))
            if self.sock.exists():
                try:
                    c=IPC(self.sock);c.close();return handle
                except OSError:pass
            time.sleep(.05)
        raise FixtureError('engine-start',TimeoutError('private IPC readiness timed out'))
    def check_permissions(self):
        if self.permission_failure:raise FixtureError('OS-permission',PermissionError('permission denied'))
    def call(self,op,**args):
        self.check_permissions()
        client=IPC(self.sock)
        try:return client.call(op,**args)
        finally:client.close()
    def after_native_restart(self):
        if self.client:
            self.client.close();self.client=None
        try:self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:raise FixtureError('native-team-restart',TimeoutError('engine did not finish its expected restart'))
        self.handles[-1]['exit_code']=self.proc.returncode
        if self.proc.returncode!=0:raise FixtureError('native-team-restart',RuntimeError('private engine restart nonzero'))
        return self.start()
    def endpoint_hash(self):
        result=subprocess.run([str(self.binary),'endpoint'],cwd=str(self.root/'project'),env=self.env,capture_output=True,text=True,timeout=10)
        if result.returncode:raise FixtureError('private-endpoint',RuntimeError(result.stderr))
        return {'endpoint_sha256':sha(result.stdout.strip()),'exit_code':result.returncode}
    def create(self):
        result=self.call('create_team',name='P11-C-private-fixture',person=self.person)
        team_id=result.get('team_id');self.after_native_restart()
        return {'created':True,'team_id_sha256':sha(team_id),'proof_used':False}
    def capability(self):
        result=self.call('link',new=False)
        ticket=result.get('ticket')
        if not isinstance(ticket,str) or not ticket:raise FixtureError('link',RuntimeError('no join capability'))
        # ticket/url never go to files, logs or an argv. The caller sends the
        # ticket through the existing SSH stdin directly into the peer's IPC.
        return ticket
    def join(self,ticket):
        result=self.call('join',ticket=ticket,person=self.person)
        team_id=result.get('team_id');self.after_native_restart()
        return {'joined':True,'team_id_sha256':sha(team_id),'capability_sha256':sha(ticket),'proof_used':False}
    def register(self):
        self.check_permissions()
        if self.client:self.client.close()
        self.client=IPC(self.sock)
        result=self.client.call('register',session={'key':self.key,'agent':'p11-controlled-native-adapter','cwd':str(self.root/'project'),
                                                  'agent_session_id':'P11-C-'+self.role,'tier':'pull','name':self.name})
        self.name=result['name'];self.address=self.person+'/'+self.name
        return {'registered':True,'session_key_sha256':sha(self.key),'address_sha256':sha(self.address),'tier':'pull'}
    def team(self):
        result=self.call('team')
        machines=result.get('machines',[])
        return {'team_id_sha256':sha(result.get('team_id')),'member_count':len(machines),
                'relay_connected':result.get('relay_connected'),'relay_url_sha256':sha(result['relay']) if result.get('relay') else None,
                'machines':[{'endpoint_sha256':sha(m.get('endpoint')),'is_me':m.get('is_me'),'online':m.get('online'),
                             'link':m.get('link'),'rtt_ms':m.get('rtt_ms'),'verified':m.get('verified'),'has_proof':m.get('has_proof')} for m in machines]}
    def who(self):
        result=self.client.call('who',me=self.key)
        rows=result.get('sessions',[])
        return {'session_count':len(rows),'sessions':[{'person':r.get('person'),'name':r.get('name'),'is_me':r.get('is_me')} for r in rows]}
    def send(self,to,body,reply_to=None):
        self.check_permissions()
        if not (to in ('p11-c-local/qa-local','p11-c-peer/qa-peer')):raise ValueError('outside controlled recipients')
        if TASK not in body:raise ValueError('non-math fixture task rejected')
        result=self.client.call('send',**{'from':self.key,'to':to,'body':body,'reply_to':reply_to,'wake':False,'notify':False})
        return result
    def inbox(self):
        self.check_permissions()
        return self.client.call('inbox',key=self.key,peek=True,wait_secs=0).get('messages',[])
    def ack(self,ids):return self.client.call('delivered',key=self.key,ids=ids)
    def process(self,phase,expected_sha):
        self.check_permissions()
        if phase not in PHASES:raise ValueError('outside controlled task phases')
        candidates=[m for m in self.inbox() if sha(m.get('body',''))==expected_sha]
        if not candidates:raise FixtureError('native-receive',RuntimeError('expected math request absent'))
        message=candidates[0]
        if message.get('from')!='p11-c-local/qa-local':raise ValueError('unexpected sender')
        if TASK not in message['body'] or '2+2=5' not in message['body']:raise ValueError('outside math fixture body')
        cache_key=sha(message['body'])
        if cache_key in self.cache:
            result=self.cache[cache_key];ran=False
        else:
            module_path=self.root/'code'/'C-native-base.py'
            spec=importlib.util.spec_from_file_location('C_native_base',module_path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.PROFILE=str(self.native_home)
            result=module.native({'id':TASK,'phase':phase,'body':message['body']},self.root/'native'/phase)
            self.model_handles.append(result['native_handle'])
            if result.get('status')!='succeeded':raise FixtureError('native-codex',RuntimeError('native JSON/CLI validation failed'))
            self.cache[cache_key]=result;ran=True
        answer=result['actual_json_answer'];body=json.dumps(answer,ensure_ascii=False)
        sent=self.send('p11-c-local/qa-local',body,reply_to=message['id'])
        self.ack([message['id']])
        return {'actual_native_call':ran,'native_conversation_sha256':sha(result['native_conversation']),
                'native_cli_version':result['native_cli_version'],'native_elapsed_ms':result['native_elapsed_ms'],
                'native_handle':{k:v for k,v in result['native_handle'].items() if k not in ('argv','profile')},
                'native_process_exited':result['native_process_exited'],'tool_events':result['tool_events'],
                'request_engine_id_sha256':sha(message['id']),'reply_engine_ids_sha256':[sha(v) for v in sent.get('ids',[])],
                'received_body_sha256':sha(message['body']),'answer_sha256':sha(body),
                'phase':phase,'model_call_count':len(self.cache)}
    def stop(self):
        if self.client:
            try:self.client.close()
            except OSError:pass
            self.client=None
        if self.proc:
            if self.proc.poll() is None:
                current=process_start(self.proc.pid)
                if current!=self.handles[-1]['lstart']:raise RuntimeError('owned PID start mismatch; refusal to signal')
                self.proc.terminate()
                try:self.proc.wait(timeout=8)
                except subprocess.TimeoutExpired:os.killpg(self.proc.pid,signal.SIGKILL);self.proc.wait(timeout=5)
            self.handles[-1]['exit_code']=self.proc.returncode
        write_json(self.root/'engine-handles.json',self.handles)
        return {'stopped':self.proc is None or self.proc.poll() is not None,'handles':self.handles}
    def restart(self):
        self.stop();return self.start()
    def cleanup(self):
        status=self.stop()
        sock=socket.socket(socket.AF_UNIX);code=sock.connect_ex(str(self.sock));sock.close()
        if code==0:raise RuntimeError('private IPC still answers after owned stop')
        for name in ('state','home','engine-codex','engine-claude','xdg-config','xdg-state','xdg-data','tmp'):
            p=self.root/name
            if p.exists() and not p.is_symlink():shutil.rmtree(p)
        if self.binary.exists():self.binary.unlink()
        status.update(ipc_connect_after_stop=code,private_state_removed=not self.state.exists(),engine_copy_removed=not self.binary.exists())
        write_json(self.root/'cleanup.json',status)
        return status
