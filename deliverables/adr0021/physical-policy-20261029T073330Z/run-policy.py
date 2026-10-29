import concurrent.futures,hashlib,json,os,shlex,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).parent;M=json.loads((ROOT/'manifest.json').read_text());OUT=Path(M['report']);PEER=M['peer']
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no',PEER]
roles={'a':('book',str(ROOT)),'b':('mini',M['remote_root']),'c':('book',str(ROOT))}
result={'kind':'two physical Macs, operator/directRPC and FILE actors, no LLM calls','manifest':'manifest.json','steps':[],'cleanup':{},'phone_touched':False,'started_at':time.time()};started=set();cache={}
def save():
 p=OUT/'results.json';t=p.with_suffix('.new');t.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');t.chmod(0o600);os.replace(t,p)
def command(role,action,*args):
 host,root=roles[role];argv=[sys.executable if host=='book'else'python3','-B',root+'/payload/node.py',role,action,*args]
 return argv if host=='book'else SSH+[shlex.join(argv)]
def call(role,action,*args,value=None,timeout=60):
 p=subprocess.run(command(role,action,*args),input=json.dumps(value).encode()if value is not None else None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if p.returncode:raise RuntimeError('helper-failed-'+role+'-'+action+'-'+str(p.returncode))
 return json.loads(p.stdout)
def rpc(role,op,**fields):return call(role,'rpc',value=dict(op=op,**fields))
def ok(answer):
 if not answer.get('ok'):raise RuntimeError('rpc-failed-'+answer.get('code','unknown'))
 return answer['result']
def status(role):return ok(rpc(role,'status'))
def state(role):return ok(rpc(role,'evaluation-state'))
def step(name,observed):
 result['steps'].append({'name':name,'at':time.time(),**observed});save();print(json.dumps({'step':name,**observed},ensure_ascii=False),flush=True)
def transfer(source,ticket,target,wrong=None):
 producer=subprocess.Popen(command(source,'ticket-stream',ticket['ticket_file']),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 try:
  response=subprocess.run(command(target,'join-stdin',*([wrong]if wrong else[])),stdin=producer.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=55)
  producer.stdout.close();producer.wait(timeout=5)
  if response.returncode or producer.returncode:raise RuntimeError('private-ticket-pipeline-failed')
  return json.loads(response.stdout)
 finally:
  if producer.poll()is None:producer.terminate();producer.wait(3)
def invite(role,*args):return call(role,'invite',*args)
def snapshot(role):
 s=state(role);return {k:s.get(k)for k in('network_id','state_sha256','active_pointer_sha256','active')}
def rejected_join(name,ticket,wrong=None):
 before=snapshot('c');answer=transfer('b',ticket,'c',wrong);after=snapshot('c')
 step(name,{'physical_boundary':'Mac mini B -> MacBook C','exit':answer['exit'],'code':answer['code'],
  'rejected':answer['exit']!=0,'prior_affiliation_preserved':before==after})
 if answer['exit']==0 or before!=after:raise RuntimeError('join-rejection-or-preservation-failed')
try:
 for role in('a','b'):step('verify-'+role,call(role,'verify'))
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:
  for role,answer in zip(('a','b','c'),pool.map(lambda r:call(r,'start'),('a','b','c'))):cache[role]=answer['status'];started.add(role)
 step('three-services-ready',{'physical_hosts':2,'same_host_third_node':'C on MacBook with A','endpoints':{r:v['endpoint_id']for r,v in cache.items()}})
 ainit=call('a','cli','init','physical-policy-A','--machine-name','policy-founder-A');cinit=call('c','cli','init','physical-policy-retained-C','--machine-name','policy-retained-C')
 network=status('a')['network']['network_id'];retained=status('c')['network']['network_id']
 afiles=ok(rpc('a','evaluation-files',labels=['published','unpublished','excluded']));bfiles=ok(rpc('b','evaluation-files',labels=['caller']))
 caller=bfiles['actors']['caller'];caller_public=bfiles['public']['caller']
 def raw(source,target,body):return ok(rpc(source,'evaluation-raw',peer=status(target)['address'],body=body))
 before=raw('b','a',{'op':'directory','network_id':network,'caller':caller_public,'repository_id':None})
 step('before-join-directory',{'physical_boundary':'B mini -> A book','rejected':not before['body'].get('ok'),'code':before['body'].get('code'),'candidate_count':len(before['body'].get('candidates',[]))})
 ticket=invite('a');joined=transfer('a',ticket,'b')
 step('B-joins-A',{'exit':joined['exit'],'same_network':status('b')['network']['network_id']==network,'active':status('b')['active']})
 stranger=raw('c','b',{'op':'ping','network_id':network})
 step('stranger-rejected',{'physical_boundary':'C book -> B mini','rejected':not stranger['body'].get('ok'),'code':stranger['body'].get('code'),'tls_origin_matches_B':stranger['origin']==cache['b']['endpoint_id']})
 discovered=ok(rpc('b','discover',caller=caller));rows=discovered['candidates'];ids=[r['handle']['session_id']for r in rows]
 astate=state('a')
 step('after-join-publication',{'physical_boundary':'B mini -> A book','candidate_ids':ids,'only_published':ids==['file-published'],
  'private_paths_absent':all(root not in json.dumps(rows)for root in(str(ROOT),M['remote_root'])),
  'native_read_counts':astate['native_reads'],'hidden_unread':astate['native_reads'].get('file-unpublished',0)==0 and astate['native_reads'].get('file-excluded',0)==0})
 forged=dict(caller_public,machine=cache['c']['endpoint_id'])
 bad=raw('b','a',{'op':'directory','network_id':network,'caller':forged,'repository_id':None})
 step('forged-sender-rejected',{'physical_boundary':'B mini -> A book','rejected':not bad['body'].get('ok'),'code':bad['body'].get('code')})
 target='net:'+':'.join(afiles['public']['published'][k]for k in('machine','runtime','home_id','session_id'))
 denied=rpc('b','send',caller=caller,target=target,id='policy-no-work',body='operator FILE fixture: publication grants no work',kind='task',wake=False)
 canonical=ok(rpc('a','evaluation-canonical',actor='published',id='policy-no-work'))
 step('publication-not-work-authority',{'rejected':not denied['ok'],'code':denied.get('code'),'target_canonical_status':canonical['status'],'no_model_called':True})
 stop=call('a','stop');started.remove('a');result['cleanup']['a']=stop
 step('founder-offline',{'remaining_owned_pids':stop['remaining_owned_pids'],'control_socket_exists':stop['socket_exists'],'B_active':status('b')['active']})
 wrong=invite('b');rejected_join('wrong-network-preserves-current',wrong,retained)
 expired=invite('b','--once','--expires','1');time.sleep(2);rejected_join('expired-invite-preserves-current',expired)
 revoked=invite('b');ok(rpc('b','revoke-invite',invite_hash=revoked['invite_hash']));rejected_join('revoked-invite-preserves-current',revoked)
 valid=invite('b');new=transfer('b',valid,'c');cstatus=status('c');bstatus=status('b')
 step('nonfounder-invites-adds-C',{'physical_boundary':'B mini -> C book','founder_offline':True,'exit':new['exit'],'C_active':cstatus['active'],'C_network_matches':cstatus['network']['network_id']==network,'B_member_status':{r['endpoint_id']:r['status']for r in bstatus['network']['members']}})
 pings=[]
 for source,targetrole in(('b','c'),('c','b')):
  answer=rpc(source,'ping',peer=status(targetrole)['address']);pings.append({'source':source,'target':targetrole,'ok':answer['ok'],'returned_endpoint':answer.get('result',{}).get('endpoint_id')})
 step('nonfounders-physical-ping',{'founder_offline':True,'roundtrips':pings})
 original_c_id=cstatus['endpoint_id'];cstop=call('c','stop');started.remove('c');result['cleanup']['c-before-removal']=cstop
 removed=call('b','cli','remove',original_c_id)
 step('nonfounder-removes-offline-C',{'founder_offline':True,'exit':removed['exit'],'C_status':next(r['status']for r in status('b')['network']['members']if r['endpoint_id']==original_c_id)})
 restarted=call('c','start');started.add('c')
 ordinary=rpc('c','ping',peer=status('b')['address'])
 end=time.monotonic()+6
 while time.monotonic()<end and status('c')['active']:time.sleep(.25)
 cnow=status('c');wire=raw('c','b',{'op':'ping','network_id':network})
 step('removed-reconnect-policy',{'same_machine_key':restarted['status']['endpoint_id']==original_c_id,'current_network_preserved':cnow['network']['network_id']==network,
  'C_active':cnow['active'],'C_self_status':next(r['status']for r in cnow['network']['members']if r['endpoint_id']==original_c_id),
  'ordinary_ping_rejected':not ordinary['ok'],'wire_ping_rejected':not wire['body'].get('ok'),'wire_code':wire['body'].get('code')})
 before=snapshot('c');again=transfer('b',valid,'c');after=snapshot('c')
 step('old-link-cannot-reactivate-removed-C',{'rejected':again['exit']!=0,'code':again['code'],'removed_affiliation_preserved':before==after})
 result['completed']=True
except Exception as error:
 result['completed']=False;result['failure_code']=str(error)if isinstance(error,RuntimeError)else type(error).__name__
 print(json.dumps({'failure_code':result['failure_code']}),flush=True)
finally:
 for role in list(started):
  try:result['cleanup'][role]=call(role,'stop');started.remove(role)
  except Exception as error:result['cleanup'][role]={'code':type(error).__name__}
 for role in('a','b','c'):
  try:result.setdefault('transport_observations',{})[role]=call(role,'audit')
  except Exception:pass
 result['finished_at']=time.time();save()
 print(json.dumps({'completed':result['completed'],'failure_code':result.get('failure_code'),'cleanup':result['cleanup']}),flush=True)
