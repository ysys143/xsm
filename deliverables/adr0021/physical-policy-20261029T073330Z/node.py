import hashlib,json,os,signal,socket,stat,subprocess,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];PAYLOAD=BASE/'payload';role=sys.argv[1];action=sys.argv[2]
if role not in('a','b','c'):raise SystemExit('invalid-role')
ROOT=BASE/role
for name in('','state','home'):(ROOT/name).mkdir(mode=0o700,parents=True,exist_ok=True)
(BASE/'t').mkdir(mode=0o700,exist_ok=True)
ENV={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'en_US.UTF-8','HOME':str(ROOT/'home'),'XSM_HOME':str(ROOT/'state'),
     'TMPDIR':str(BASE/'t'),'XSM_TEMP':str(BASE/'t'),'PYTHONPATH':str(PAYLOAD),'PYTHONDONTWRITEBYTECODE':'1',
     'XSM_NET_BINARY':str(PAYLOAD/'bin'/'xsm-net'),'POLICY_TRACE':str(ROOT/'trace.jsonl'),
     'CODEX_HOME':str(ROOT/'home'/'codex'),'CLAUDE_CONFIG_DIR':str(ROOT/'home'/'claude')}
os.environ.update(ENV);sys.path.insert(0,str(PAYLOAD))
from xsm import network
def rpc(value,timeout=12):return network.call(value,timeout=timeout)
def cli(args,stream=None):
 p=subprocess.run([sys.executable,'-B','-m','xsm','network']+args,stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=48)
 try:r=json.loads(p.stdout)
 except ValueError:r={'code':'invalid-cli-json'}
 return {'exit':p.returncode,'code':r.get('code'),'result':r,'stderr_bytes':len(p.stderr)}
def starttime(pid):return subprocess.run(['ps','-p',str(pid),'-o','lstart='],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=3).stdout.strip()
def save(p,v):p.write_text(json.dumps(v));p.chmod(0o600)
if action=='verify':
 manifest=json.loads((PAYLOAD/'file-manifest.json').read_text());actual={name:hashlib.sha256((PAYLOAD/name).read_bytes()).hexdigest()for name in manifest}
 print(json.dumps({'match':actual==manifest,'files':len(actual),'python':sys.version.split()[0],'hostname':socket.gethostname()}))
elif action=='start':
 config=cli(['configure','--relay','off','--port','0'])
 out=(ROOT/'stdout').open('ab');err=(ROOT/'stderr').open('ab')
 p=subprocess.Popen([sys.executable,'-B',str(PAYLOAD/'observe.py')],stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=str(PAYLOAD),env=ENV,start_new_session=True)
 out.close();err.close();owner={'service_pid':p.pid,'service_start':starttime(p.pid)};save(ROOT/'owner.json',owner)
 end=time.monotonic()+12
 while time.monotonic()<end:
  if p.poll()is not None:raise SystemExit('owned-start-failed')
  try:
   status=rpc({'op':'status'},1);owner.update(engine_pid=status['engine_pid'],engine_start=starttime(status['engine_pid']),bound_addresses=status['transport']['bound_addresses']);save(ROOT/'owner.json',owner)
   print(json.dumps({'status':status,'owner':owner}));break
  except Exception:time.sleep(.05)
 else:raise SystemExit('owned-start-timeout')
elif action=='rpc':
 request=json.loads(sys.stdin.buffer.read(8*1024*1024+1))
 try:print(json.dumps({'ok':True,'result':rpc(request,40)}))
 except Exception as e:print(json.dumps({'ok':False,'code':str(e)if isinstance(e,network.NetworkError)else type(e).__name__}))
elif action=='cli':print(json.dumps(cli(sys.argv[3:])))
elif action=='invite':
 before=rpc({'op':'status'});hashes={r['invite_hash']for r in(before.get('network')or{}).get('invites',[])}
 response=cli(['invite']+sys.argv[3:]);after=rpc({'op':'status'})
 fresh=[r['invite_hash']for r in after['network']['invites']if r['invite_hash']not in hashes]
 print(json.dumps({'ticket_file':response['result'].get('ticket_file'),'invite_hash':fresh[0]if len(fresh)==1 else None,'network_id':after['network']['network_id'],'exit':response['exit']}))
elif action=='ticket-stream':
 import shutil
 source=Path(sys.argv[3]);expected=(ROOT/'state'/'network'/'invites').resolve()
 if source.resolve().parent!=expected or source.is_symlink():raise SystemExit('not-owned-invitation')
 with source.open('rb')as stream:shutil.copyfileobj(stream,sys.stdout.buffer)
elif action=='join-stdin':
 if len(sys.argv)>3:
  # Controlled wrong-network ticket. Its bearer value remains only in this
  # helper/private file and is never returned or logged.
  ticket=json.loads(sys.stdin.buffer.read(8*1024*1024+1));ticket['network_id']=sys.argv[3]
  temporary=ROOT/'wrong-network-ticket.json';save(temporary,ticket)
  response=cli(['join','--ticket-file',str(temporary),'--machine-name','FILE-policy-'+role])
 else:response=cli(['join','--ticket-stdin','--machine-name','FILE-policy-'+role],sys.stdin.buffer)
 print(json.dumps(response))
elif action=='audit':
 p=ROOT/'trace.jsonl';print(json.dumps([json.loads(line)for line in p.read_text().splitlines()]if p.exists()else[]))
elif action=='stop':
 owner=json.loads((ROOT/'owner.json').read_text());response=cli(['stop']);left=[]
 for pidkey,startkey in(('service_pid','service_start'),('engine_pid','engine_start')):
  pid=owner.get(pidkey);expected=owner.get(startkey)
  if not pid:continue
  end=time.monotonic()+4
  while time.monotonic()<end and starttime(pid)==expected:time.sleep(.05)
  if starttime(pid)==expected:
   os.kill(pid,signal.SIGTERM);time.sleep(.2)
  if starttime(pid)==expected:left.append(pid)
 ports=[]
 for bound in owner.get('bound_addresses',[]):
  if bound.startswith('['):host,port=bound[1:].split(']:');family=socket.AF_INET6
  else:host,port=bound.rsplit(':',1);family=socket.AF_INET
  s=socket.socket(family,socket.SOCK_DGRAM)
  try:
   if family==socket.AF_INET6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
   s.bind((host,int(port)));ports.append({'address':bound,'free':True})
  except OSError as e:ports.append({'address':bound,'free':False,'errno':e.errno})
  finally:s.close()
 print(json.dumps({'remaining_owned_pids':left,'socket_exists':network.socket_path().exists(),'udp_rebind':ports,'stop_exit':response['exit']}))
