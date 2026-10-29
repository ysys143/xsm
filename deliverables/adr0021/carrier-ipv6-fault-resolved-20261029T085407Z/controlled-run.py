
import importlib.util,json,os,socket,time
from pathlib import Path
root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('existing_carrier_helper',root/'run.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
profile='(version 1)(allow default)(deny network-outbound(remote tcp "*:*"))(deny network-outbound(remote udp "*:*"))(allow network-outbound(remote udp "localhost:*"))'
control=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM);control.close()
held=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);held.bind(('0.0.0.0',0));port=held.getsockname()[1];os.environ['CARRIER_HELD_PORT']=str(port)
result={'scope':'same-host controlled AF_INET6 EAFNOSUPPORT; not actual IPv6-absent host','host_ipv6_socket_supported':True,'held_ipv4_port':port,'started_at':time.time(),'interposer_forward':'direct original socket from interposer image','nodes':[]}
nodes=[]
try:
 for role in ('a','b'):nodes.append(r.Node('v4',role,profile,launcher=root/'observe-v6-corrected.py'))
 for n in nodes:n.ready()
 result['nodes']=[{'service_pid':n.proc.pid,'engine_pid':n.engine_pid,'endpoint_id':n.info['endpoint_id'],'transport':n.info['transport']}for n in nodes]
 a,b=nodes
 a.cli('init','controlled-ipv6-unavailable','--machine-name','v4-a')
 ticket=a.cli('invite','--once','--expires','120')
 import subprocess
 with open(ticket['ticket_file'],'rb') as f:
  joined=subprocess.run([r.PYTHON,'-B','-m','xsm','network','join','--ticket-stdin','--machine-name','v4-b'],cwd=root/'src',env=b.env,stdin=f,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
 for name,raw in [('join.stdout',joined.stdout),('join.stderr',joined.stderr)]:
  fd=os.open(root/'raw'/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb')as out:out.write(raw)
 if joined.returncode:raise r.Failure('public-cli-join-failed')
 for n in nodes:n.info=n.rpc({'op':'status'},3)
 result['both_active']=all(n.info.get('active')for n in nodes)
 result['roundtrips']=[r.ping(a,b),r.ping(b,a)]
 result['fault_observations']=[]
 for n in nodes:
  events=[json.loads(x)for x in Path(str(n.trace)+'.sockets.jsonl').read_text().splitlines()]
  result['fault_observations'].append({'engine_pid':n.engine_pid,'observed_pids':sorted({e['pid']for e in events}),'loaded_in_engine':any(e['event']=='interpose-loaded'and e['pid']==n.engine_pid for e in events),'ipv6_eafnosupport_count':sum(e['event']=='ipv6-socket-denied'and e['pid']==n.engine_pid and e['errno']==47 for e in events),'ipv4_socket_success_count':sum(e['event']=='socket-passed'and e['pid']==n.engine_pid and e['family']==2 and e['result']>=0 for e in events),'direct_reentry_count':sum(e['event']=='direct-call-reentry'for e in events),'native_stderr_bytes':Path(str(n.trace)+'.native.stderr').stat().st_size})
 result['passed']=result['both_active'] and all(n['transport']['requested_port']==port and n['transport']['port_fallback'] and all(not a.startswith('[') and int(a.rsplit(':',1)[1])!=port for a in n['transport']['bound_addresses'])for n in result['nodes']) and all(o['loaded_in_engine']and o['ipv6_eafnosupport_count']>0 and o['ipv4_socket_success_count']>0 and o['direct_reentry_count']==0 for o in result['fault_observations']) and all(p['path']=='direct'and p['tls_origin_matches']and p['request_digest_matches']and p['response_digest_matches']for p in result['roundtrips'])
except Exception as e:result['passed']=False;result['failure_code']=getattr(e,'code',type(e).__name__)
finally:
 result['cleanup']=[n.close()for n in nodes];held.close();result['udp_rebind_after_cleanup']=[]
 for address in [a for n in result['nodes']for a in n['transport']['bound_addresses']]+['0.0.0.0:'+str(port)]:
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:s.bind(('0.0.0.0',int(address.rsplit(':',1)[1])));result['udp_rebind_after_cleanup'].append({'address':address,'free':True})
  except OSError as e:result['udp_rebind_after_cleanup'].append({'address':address,'free':False,'errno':e.errno})
  finally:s.close()
 result['finished_at']=time.time();r.save(r.REPORT/'result.json',result)
print(json.dumps({'report':str(r.REPORT),'passed':result['passed'],'failure_code':result.get('failure_code'),'nodes':result['nodes'],'fault_observations':result.get('fault_observations'),'roundtrips':result.get('roundtrips'),'cleanup':result['cleanup'],'udp_rebind':result['udp_rebind_after_cleanup']}),flush=True)
