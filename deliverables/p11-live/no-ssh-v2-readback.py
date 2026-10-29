"""After-window own-root retrieval and nonprivileged process-generation audit."""
import base64,hashlib,importlib.util,json,os,socket,subprocess,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=Path('/private/tmp/p11-C-no-ssh-v2-local-51bqm_cj');PEER='/private/tmp/p11-C-no-ssh-v2-peer-iorbhq2p'
s=importlib.util.spec_from_file_location('ownedproc',BASE/'no-ssh-v2-proc.py');P=importlib.util.module_from_spec(s);s.loader.exec_module(P)
def run_peer(root):
 # This body is also used as SSH stdin; no task/trigger/reply injection.
 import base64,hashlib,importlib.util,json,os,socket,sys,time
 from pathlib import Path
 root=Path(root).resolve()
 if not root.name.startswith('p11-C-no-ssh-v2-') or root.stat().st_uid!=os.getuid():raise RuntimeError('outside own fixture')
 sp=importlib.util.spec_from_file_location('readbackproc',root/'code/no-ssh-v2-proc.py');p=importlib.util.module_from_spec(sp);sp.loader.exec_module(p)
 final=json.loads((root/'peer-final.json').read_text());handles=final.get('cleanup',{}).get('handles',[])+[{'pid':final['helper_pid'],'lstart':final['helper_lstart']}]
 if final.get('native'):handles.append(final['native']['native_handle'])
 status=[]
 for h in handles:
  p.ALLOWED.add(h['pid']);i=p.info(h['pid']);status.append({'pid':h['pid'],'expected_generation':h['lstart'],'observed':i,'remaining_matching_generation':bool(i and i['generation']==h['lstart'])})
 sock=socket.socket(socket.AF_UNIX);ipc=sock.connect_ex(str(root/'state/network.sock'));sock.close()
 files={}
 for name in ('peer-final.json','ready.json','restricted.json','native-starting.json','engine-handles.json','cleanup.json','helper.stdout','helper.stderr','native/first/result.json','native/first/stdout.jsonl','native/first/stderr.txt','native/first/handle.json','native/first/native-root-metadata.json'):
  q=root/name
  if q.exists():data=q.read_bytes();files[name]={'sha256':hashlib.sha256(data).hexdigest(),'base64':base64.b64encode(data).decode()}
 return {'root':str(root),'readback_at':time.time(),'processes':status,'remaining_count':sum(x['remaining_matching_generation'] for x in status),'ipc_connect_after_stop':ipc,'files':files}
if __name__=='__main__':
 result=json.loads((ROOT/'result.json').read_text())
 # Extract only the known function and standard imports into the remote stdin.
 import inspect
 code=inspect.getsource(run_peer)+'\nprint(json.dumps(run_peer('+repr(PEER)+'),ensure_ascii=False))\n'
 code='import json\n'+code
 args=['ssh','-S','none','-oControlMaster=no','-oControlPath=none','-oBatchMode=yes','-oConnectTimeout=5','-oStrictHostKeyChecking=yes','-oUpdateHostKeys=no','jaesol-macmini','/usr/bin/python3 -']
 before=time.time()
 if before<=result['measurement_end_at']:raise RuntimeError('readback before measurement end')
 with open(ROOT/'post-window-peer.stdout','w') as out,open(ROOT/'post-window-peer.stderr','w') as err:
  child=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True);handle=P.info(child.pid);child.communicate(code,timeout=45)
 if child.returncode:raise RuntimeError('post-window SSH failure')
 peer=json.loads((ROOT/'post-window-peer.stdout').read_text());dest=ROOT/'peer-raw';dest.mkdir(mode=0o700)
 for name,row in peer['files'].items():
  raw=base64.b64decode(row.pop('base64'));assert hashlib.sha256(raw).hexdigest()==row['sha256'];q=dest/name;q.parent.mkdir(parents=True,exist_ok=True,mode=0o700);q.write_bytes(raw);q.chmod(0o600)
 handles=result.get('cleanup',{}).get('local',{}).get('handles',[])+[{'pid':result['controller_pid'],'lstart':result['controller_generation']}]
 local=[]
 for h in handles:
  P.ALLOWED.add(h['pid']);i=P.info(h['pid']);local.append({'pid':h['pid'],'expected_generation':h['lstart'],'observed':i,'remaining_matching_generation':bool(i and i['generation']==h['lstart'])})
 audit={'post_window_ssh_start':before,'post_window_ssh_exit':child.returncode,'post_window_ssh_handle':handle,'local_processes':local,'peer':peer,'local_remaining':sum(x['remaining_matching_generation'] for x in local),'peer_remaining':peer['remaining_count']}
 (ROOT/'post-window-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
 print(json.dumps({'ssh_exit':child.returncode,'local_remaining':audit['local_remaining'],'peer_remaining':audit['peer_remaining'],'raw_files':len(peer['files'])},ensure_ascii=False))
