
import hashlib,json,os,socket,stat,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]; payload=root/'payload'
for name in ('raw','tmp','state','os-home'):
    (root/name).mkdir(mode=0o700,exist_ok=True)
for key in list(os.environ):
    if key.startswith(('XSM_','CLAUDE_','CODEX_','ORCA_','OTEL_')) or key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY'):
        os.environ.pop(key,None)
os.environ.update(XSM_HOME=str(root/'state'),XSM_TEMP=str(root),TMPDIR=str(root/'tmp'),PYTHONPATH=str(payload),PYTHONDONTWRITEBYTECODE='1',XSM_NET_BINARY=str(root/'engine-wrapper') if (root/'engine-wrapper').is_file() else str(payload/'bin'/'xsm-net'))
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
    if Path('/proc/self/stat').exists():
        try: return Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].strip().split()[0]!='Z'
        except FileNotFoundError:return False
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
