import concurrent.futures,hashlib,importlib.util,json,os,re,shlex,signal,socket,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).parent;M=json.loads((ROOT/'manifest.json').read_text());OUT=Path(M['report'])
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no','jaesol-macmini']
def save(name,value):
 p=OUT/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
def cmd(role,action,*args):
 base=str(ROOT)if role=='a'else M['remote_root'];argv=[M['python']if role=='a'else'python3','-B',base+'/payload/node.py',role,action,*args]
 return argv if role=='a'else SSH+[shlex.join(argv)]
def node(role,action,*args,value=None,timeout=60):
 p=subprocess.run(cmd(role,action,*args),input=json.dumps(value).encode()if value is not None else None,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError('owned-node-step-failed:'+role+':'+action+':'+str(p.returncode))
 return json.loads(p.stdout)
def rpc(role,op,**kwargs):
 r=node(role,'rpc',value=dict(op=op,**kwargs))
 if not r['ok']:raise RuntimeError('owned-node-rpc:'+r.get('code','unknown'))
 return r['result']
stop_controls=threading.Event();udp_seen=[]
udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0));udp.settimeout(.2)
tcp=socket.socket();tcp.bind(('127.0.0.1',0));tcp.listen(8);tcp.settimeout(.2)
def udp_loop():
 while not stop_controls.is_set():
  try:data,addr=udp.recvfrom(128);udp_seen.append({'at':time.time(),'sha256':hashlib.sha256(data).hexdigest()})
  except socket.timeout:pass
  except OSError:return
def tcp_loop():
 while not stop_controls.is_set():
  try:connection,_=tcp.accept();connection.close()
  except socket.timeout:pass
  except OSError:return
for function in(udp_loop,tcp_loop):threading.Thread(target=function,daemon=True).start()
relay=socket.gethostbyname('aps1-1.relay.n0.iroh.link.')
(ROOT/'socket-probe-config.json').write_text(json.dumps({'udp_port':udp.getsockname()[1],'tcp_port':tcp.getsockname()[1],'relay_ipv4':relay}))
spec=importlib.util.spec_from_file_location('actual_actors',ROOT/'actors.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
reviewer=a.Actor('reviewer');requester=a.Actor('requester');actors=[reviewer,requester];started=set()
result={'kind':'actual Codex local workflow under owned remote/link outages','manifest':'manifest.json','phases':[],'cleanup':{},'controller_body_relay_or_ACK_or_index_repair':False,'model_override':False,'started_at':time.time()}
def checkpoint():save('results.json',result)
def refresh_all():return [actor.refresh()for actor in actors if actor.runs]
def workflow():
 records=[]
 for q in a.questions():
  if q.get('purpose')=='question' and q.get('replies'):
   records.append(q)
 return records
def wait_phase(phase,earlier,budget=180):
 end=time.monotonic()+budget;seen=False
 while time.monotonic()<end:
  state=refresh_all()
  found=[q for q in workflow()if q['id']not in earlier]
  if found:
   seen=True
   if requester.proc.poll()is not None:
    return {'phase':phase,'completed':True,'actors':state,'questions':found,'at':time.time()}
  if any(x.get('error')for x in state):raise RuntimeError('native-actor-error')
  if requester.proc.poll()is not None and not seen:raise RuntimeError('requester-ended-without-correlated-local-reply')
  time.sleep(.15)
 raise RuntimeError('phase-timeout:'+phase)
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:
  for role,answer in zip(('a','b'),pool.map(lambda r:node(r,'start'),('a','b'))):started.add(role)
 initial={r:rpc(r,'status')for r in('a','b')};save('initial-services.json',initial)
 assert node('a','cli','init','actual-local-resilience','--machine-name','a215-book')['exit']==0
 ticket=node('a','invite')
 producer=subprocess.Popen(cmd('a','ticket-stream',ticket['ticket_file']),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 joined=subprocess.run(cmd('b','join-stdin'),stdin=producer.stdout,capture_output=True,timeout=55);producer.stdout.close();producer.wait(5)
 assert json.loads(joined.stdout)['exit']==0
 health=[]
 for source,target in(('a','b'),('b','a')):
  response=rpc(source,'ping',peer=rpc(target,'status')['address']);health.append({'source':source,'target':target,'endpoint_id':response.get('endpoint_id'),'ok':response.get('ok')})
 result['initial_physical_p2p_health']=health;checkpoint();print(json.dumps({'stage':'initial-P2P-health','both_ok':all(v['ok']for v in health)}),flush=True)
 reviewer.launch('phase0');requester.launch('phase0');save('actor-launches.json',[x.runs for x in actors])
 first=wait_phase('baseline-local',set());result['phases'].append(first);checkpoint();print(json.dumps({'stage':'baseline-local','questions':len(first['questions']),'completed':True}),flush=True)
 stopped=node('b','stop');started.remove('b');result['mini_stop']=stopped;checkpoint()
 prior={q['id']for q in workflow()}
 if reviewer.proc.poll()is not None:reviewer.launch('phase1')
 requester.launch('phase1');save('actor-launches.json',[x.runs for x in actors])
 second=wait_phase('Mini-service-stopped',prior);result['phases'].append(second);checkpoint();print(json.dumps({'stage':'Mini-service-stopped','completed':True}),flush=True)
 result['book_stop_for_restart']=node('a','stop');started.remove('a')
 (ROOT/'engine-link-blocked').write_text('owned engine process only\n')
 restart=node('a','start');started.add('a');result['book_blocked_status']=restart['status']
 probes=[json.loads(line)for line in(ROOT/'engine-socket-probes.jsonl').read_text().splitlines()]
 blocked=[p for p in probes if p['blocked']][-1]
 assert blocked['pid']==restart['status']['engine_pid'],'socket probe PID must remain native engine PID across exec'
 assert blocked['checks'][0].get('errno')==1 and blocked['checks'][1].get('errno')==1 and blocked['checks'][2]['allowed']
 result['socket_probes']=probes;result['udp_control_observations']=udp_seen;checkpoint()
 prior={q['id']for q in workflow()}
 if reviewer.proc.poll()is not None:reviewer.launch('phase2')
 requester.launch('phase2');save('actor-launches.json',[x.runs for x in actors])
 third=wait_phase('Book-engine-UDP-and-TCP443-blocked',prior);result['phases'].append(third);checkpoint();print(json.dumps({'stage':'Book-engine-link-blocked','completed':True}),flush=True)
 result['completed']=True
except Exception as error:
 result['completed']=False;result['failure_code']=str(error)if isinstance(error,RuntimeError)else type(error).__name__
 print(json.dumps({'failure_code':result['failure_code']}),flush=True)
finally:
 result['actor_final_observations']=refresh_all()
 for actor in actors:result['cleanup'][actor.role]=actor.cleanup()
 for role in list(started):
  try:result['cleanup']['network-'+role]=node(role,'stop')
  except Exception as error:result['cleanup']['network-'+role]={'code':type(error).__name__}
 stop_controls.set();udp.close();tcp.close()
 auth=Path(M['auth_source_profile'])/'auth.json';st=auth.stat();after_auth={'inode':st.st_ino,'size':st.st_size,'mtime_ns':st.st_mtime_ns,'mode':st.st_mode&511}
 profiles={name:hashlib.sha256((Path(M['auth_source_profile'])/name).read_bytes()).hexdigest()if(Path(M['auth_source_profile'])/name).is_file()else None for name in M['profile_before']}
 result['source_auth_metadata_unchanged']=after_auth==M['auth_metadata_only'];result['source_profile_unchanged']=profiles==M['profile_before']
 result['actual_CIDs']={actor.role:actor.cid for actor in actors};result['finished_at']=time.time();checkpoint()
 print(json.dumps({'completed':result['completed'],'failure_code':result.get('failure_code'),'phases':len(result['phases']),'cleanup':result['cleanup'],'profile_unchanged':result['source_profile_unchanged'],'auth_metadata_unchanged':result['source_auth_metadata_unchanged']},ensure_ascii=False),flush=True)
