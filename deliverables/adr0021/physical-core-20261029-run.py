"""Physical core experiment; provisioning/observation SSH only, no repo install."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
PEER = "jaesol-macmini"
TAIL = {"book": "100.123.30.11", "mini": "100.77.24.16"}
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
       "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no", PEER]
OUT = Path(__file__).with_name("physical-core-20261029-results.json")

OBSERVER = r'''
import hashlib,json,os,runpy,sys,time
from pathlib import Path
root=Path(sys.argv[1]); audit=root/'raw'/'transport.jsonl'
def write(value):
    value['observed_at']=time.time(); value['observer_pid']=os.getpid()
    fd=os.open(audit,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    with os.fdopen(fd,'a') as stream: stream.write(json.dumps(value,separators=(',',':'))+'\n')
def digest(body):
    return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
from xsm.network_transport import Sidecar
dispatch=Sidecar._dispatch; request=Sidecar.request
def observed_dispatch(self,event):
    dispatch(self,event)
    kind=event.get('event')
    if kind not in ('ready','request','response','path'): return
    record={k:event[k] for k in ('event','id','request_id','origin','endpoint_id','bound_addresses','requested_port','port_fallback','relay_mode','relay_online') if k in event}
    record['native_pid']=self._process.pid
    if 'body' in event:
        record['body_sha256']=digest(event['body'])
        if isinstance(event['body'],dict) and event['body'].get('op') in ('join','join-status','ping','sync'):
            record['application_op']=event['body']['op']
    record['last_transport']=self.last_transport
    write(record)
def observed_request(self,peer,body,timeout=30):
    write({'event':'outbound-body','target_endpoint_id':peer.get('id'),'application_op':body.get('op'),'body_sha256':digest(body)})
    return request(self,peer,body,timeout=timeout)
Sidecar._dispatch=observed_dispatch; Sidecar.request=observed_request
sys.argv=['xsm.network','serve']
runpy.run_module('xsm.network',run_name='__main__')
'''

HELPER = r'''
import hashlib,json,os,socket,stat,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]; payload=root/'payload'
for name in ('raw','tmp','state','os-home'):
    (root/name).mkdir(mode=0o700,exist_ok=True)
for key in list(os.environ):
    if key.startswith(('XSM_','CLAUDE_','CODEX_','ORCA_','OTEL_')) or key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY'):
        os.environ.pop(key,None)
os.environ.update(HOME=str(root/'os-home'),XSM_HOME=str(root/'state'),XSM_TEMP=str(root),TMPDIR=str(root/'tmp'),PYTHONPATH=str(payload),PYTHONDONTWRITEBYTECODE='1',XSM_NET_BINARY=str(payload/'bin'/'xsm-net'))
sys.path.insert(0,str(payload))
from xsm import network
def save(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream: json.dump(value,stream)
def cli(args,stream=None):
    result=subprocess.run([sys.executable,'-B','-m','xsm','network']+args,stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ,timeout=65)
    stamp=str(time.monotonic_ns())
    for suffix,raw in (('stdout',result.stdout),('stderr',result.stderr)):
        fd=os.open(root/'raw'/(stamp+'.'+suffix),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f: f.write(raw)
    try: value=json.loads(result.stdout)
    except Exception: value={'code':'invalid-cli-output'}
    return {'exit':result.returncode,'stderr_bytes':len(result.stderr),'result':value}
def alive(pid):
    result=subprocess.run(['ps','-p',str(pid),'-o','pid='],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    return bool(result.stdout.strip())
action=sys.argv[1]
if action=='verify':
    expected=json.loads((payload/'manifest.json').read_text()); actual={}
    for name in expected: actual[name]=hashlib.sha256((payload/name).read_bytes()).hexdigest()
    print(json.dumps({'sha_match':expected==actual,'files':len(actual),'manifest_sha256':hashlib.sha256((payload/'manifest.json').read_bytes()).hexdigest(),'binary_sha256':actual['bin/xsm-net'],'python':sys.version.split()[0],'generation':root.name}))
elif action=='start':
    out=os.open(root/'raw'/'service.stdout',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    err=os.open(root/'raw'/'service.stderr',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    child=subprocess.Popen([sys.executable,'-B',str(payload/'observer.py'),str(root)],stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=os.environ,start_new_session=True)
    os.close(out);os.close(err)
    save(root/'service-owner.json',{'pid':child.pid,'generation':root.name})
    for _ in range(400):
        if child.poll() is not None: print(json.dumps({'start':'failed','exit':child.returncode}));break
        try:
            value=network.call({'op':'status'},timeout=.2)
            print(json.dumps({'start':'ready','service_pid':child.pid,'status':value}));break
        except Exception: time.sleep(.025)
    else: print(json.dumps({'start':'timeout','service_pid':child.pid}))
elif action=='cli': print(json.dumps(cli(sys.argv[2:])))
elif action=='join-stdin': print(json.dumps(cli(['join','--ticket-stdin','--machine-name',sys.argv[2]],sys.stdin.buffer)))
elif action=='ping':
    peer=json.loads(sys.stdin.buffer.read())
    try:
        value=network.call({'op':'ping','peer':peer},timeout=40)
        state=value.get('state',{})
        print(json.dumps({'ok':True,'endpoint_id':value.get('endpoint_id'),'network_id':value.get('network_id'),'record_count':len(state.get('records',[])),'signed_body_sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()}))
    except Exception as exc: print(json.dumps({'ok':False,'code':str(exc) if isinstance(exc,network.NetworkError) else 'operation-failed'}))
elif action=='audit':
    values=[]
    for line in (root/'raw'/'transport.jsonl').read_text().splitlines(): values.append(json.loads(line))
    print(json.dumps(values))
elif action=='stop':
    owner=json.loads((root/'service-owner.json').read_text())
    audits=[json.loads(line) for line in (root/'raw'/'transport.jsonl').read_text().splitlines()]
    native=next((r['native_pid'] for r in reversed(audits) if r.get('event')=='ready'),None)
    response=cli(['stop'])
    pids=[owner['pid']]+([native] if native else [])
    for _ in range(160):
        remaining=[p for p in pids if alive(p)]
        if not remaining: break
        time.sleep(.025)
    print(json.dumps({'cli':response,'remaining_owned_pids':remaining,'control_socket_exists':network.socket_path().exists(),'generation':root.name,'user_session_signals':0}))
elif action=='key-metadata':
    key=root/'state'/'network'/'transport'/'node.secret'
    print(json.dumps({'key_mode':oct(stat.S_IMODE(key.stat().st_mode)),'key_root_mode':oct(stat.S_IMODE(key.parent.stat().st_mode)),'private_key_read':False,'public_status':network.call({'op':'status'},timeout=5)}))
'''


def invoke(command, data=None, stream=None, timeout=100):
    result = subprocess.run(command, input=data, stdin=stream, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError("owned-step-failed:%d" % result.returncode)
    return json.loads(result.stdout)


def remote_command(args):
    return SSH + [shlex.join(args)]


def main():
    if OUT.exists():
        raise SystemExit("physical-core result already exists; preserve this experiment record")
    local = Path(tempfile.mkdtemp(prefix="xpc-", dir="/private/tmp"))
    remote = invoke(remote_command(["python3", "-c", "import tempfile,json;print(json.dumps(tempfile.mkdtemp(prefix='xpc-',dir='/private/tmp')))" ]))
    payload = local / "payload"
    payload.mkdir(mode=0o700)
    (payload / "xsm").mkdir(mode=0o700)
    (payload / "bin").mkdir(mode=0o700)
    for source in (REPO / "xsm").glob("*.py"):
        destination = payload / "xsm" / source.name
        destination.write_bytes(source.read_bytes())
        destination.chmod(0o600)
    binary = payload / "bin" / "xsm-net"
    shutil.copyfile(REPO / "native/xsm-net/target/debug/xsm-net", binary)
    binary.chmod(0o700)
    for name, text in (("observer.py", OBSERVER), ("node.py", HELPER)):
        (payload / name).write_text(text)
        (payload / name).chmod(0o600)
    manifest = {str(path.relative_to(payload)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in payload.rglob("*") if path.is_file()}
    (payload / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    (payload / "manifest.json").chmod(0o600)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as packed:
        packed.add(payload, arcname="payload")
    extract = "import sys,tarfile;tarfile.open(fileobj=sys.stdin.buffer,mode='r|').extractall(sys.argv[1]);print('{}')"
    invoke(remote_command(["python3", "-c", extract, remote]), data=archive.getvalue())
    roots = {"book": str(local), "mini": remote}
    result = {"label": "physical-core-not-agent-workflow", "roots": roots,
              "ssh_role": "provisioning-and-local-control-observation-only", "steps": [],
              "started": time.time(), "tailscale_ipv4_reobserved": TAIL}
    def save():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    def call(host, action, *args, data=None, stream=None):
        command = ([sys.executable, "-B", roots[host]+"/payload/node.py", action, *args]
                   if host == "book" else remote_command(["python3", "-B", roots[host]+"/payload/node.py", action, *args]))
        value = invoke(command, data=data, stream=stream)
        result["steps"].append({"host":host,"action":action,"args":list(args),"result":value})
        save()
        return value
    started = set()
    try:
        verified = {host: call(host,"verify") for host in roots}
        assert all(v["sha_match"] for v in verified.values())
        assert verified["book"]["manifest_sha256"] == verified["mini"]["manifest_sha256"]
        ready = {}
        for host in roots:
            ready[host] = call(host,"start");started.add(host)
            assert ready[host].get("start") == "ready"
        assert call("book","cli","init","physical-core-20261029","--machine-name","jaesol-macbookpro")["exit"] == 0
        invitation = call("book","cli","invite")
        ticket = Path(invitation["result"]["ticket_file"])
        with ticket.open("rb") as invitation_stream:
            joined = call("mini","join-stdin","jaesol-macmini",stream=invitation_stream)
        assert joined["exit"] == 0
        for host in roots: assert call(host,"cli","members")["exit"] == 0
        for sender, receiver in (("book","mini"),("mini","book")):
            ping = call(sender,"ping",data=json.dumps(ready[receiver]["status"]["address"]).encode())
            assert ping["ok"] and ping["endpoint_id"] == ready[receiver]["status"]["endpoint_id"]
        result["baseline_physical_rpc"] = True
        result["baseline_audits"] = {host:call(host,"audit") for host in roots}
        save()
        print(json.dumps({"first_physical_result":True,"results":str(OUT),"private_roots":roots}),flush=True)
        identities = {host:ready[host]["status"]["endpoint_id"] for host in roots}
        for host in roots:
            stopped = call(host,"stop");started.discard(host)
            assert not stopped["remaining_owned_pids"] and not stopped["control_socket_exists"]
        # Fresh startup with the SAME host-local key and signed membership.
        for host in roots:
            assert call(host,"cli","configure","--relay","off","--direct-address",TAIL[host]+":0")["exit"] == 0
            ready[host] = call(host,"start");started.add(host)
            assert ready[host]["status"]["endpoint_id"] == identities[host]
            metadata = call(host,"key-metadata")
            assert metadata["key_mode"] == "0o600" and metadata["key_root_mode"] == "0o700"
            assert metadata["public_status"]["active"]
        for sender,receiver in (("book","mini"),("mini","book")):
            assert call(sender,"ping",data=json.dumps(ready[receiver]["status"]["address"]).encode())["ok"]
        result["tailscale_candidate_physical_rpc"] = True
        result["final_audits"] = {host:call(host,"audit") for host in roots}
    except Exception as exc:
        result["failure"] = {"type":type(exc).__name__,"code":str(exc) if isinstance(exc,AssertionError) else "owned-step-failed"}
        print(json.dumps({"physical_core_failure":result["failure"],"results":str(OUT)}),flush=True)
    finally:
        result["cleanup"] = {}
        for host in list(started):
            try: result["cleanup"][host] = call(host,"stop")
            except Exception: result["cleanup"][host] = {"code":"owned-stop-failed"}
        result["finished"] = time.time()
        save()
    print(json.dumps({"baseline":result.get("baseline_physical_rpc",False),"tailscale_candidate":result.get("tailscale_candidate_physical_rpc",False),"failure":result.get("failure"),"results":str(OUT)}),flush=True)


if __name__ == "__main__":
    main()
