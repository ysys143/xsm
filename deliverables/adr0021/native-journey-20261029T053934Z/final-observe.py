import os,json,subprocess,sys,hashlib,time
from pathlib import Path
r=Path(sys.argv[1]);os.umask(0o077)
os.environ.update(XSM_HOME=str(r/'state'),TMPDIR=str(r/'tmp'),PYTHONDONTWRITEBYTECODE='1');sys.dont_write_bytecode=True;sys.path.insert(0,str(r/'payload'))
from xsm import network
def load(p):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return None
def start(pid):return subprocess.run(['ps','-p',str(pid),'-o','lstart='],capture_output=True,text=True).stdout.strip()or None
known={}
for f in r.glob('**/actor-owner.json'):
 v=load(f)
 if v:known[(v['pid'],v['lstart'])]={'kind':'actor','path':str(f),'pid':v['pid'],'lstart':v['lstart']}
for f in r.glob('**/handles.json'):
 h=load(f)
 if h:
  for v in [h['proxy'],h['server']]+[v for v in h['native_ancestor_chain']if Path(v['comm']).name=='codex']:
   known[(v['pid'],v['lstart'])]=dict(v,path=str(f))
result={'at':time.time(),'all_attempt_owned_processes':[dict(v,same_generation_alive=start(v['pid'])==v['lstart'])for v in known.values()], 'network_status':network.call({'op':'status'},timeout=4),'key_metadata':[],'payload_verification':{}}
for name,v in load(r/'payload/source-manifest.json')['files'].items():result['payload_verification'][name]=hashlib.sha256((r/'payload'/name).read_bytes()).hexdigest()==v['sha256']
for p in (r/'state/network').rglob('node.secret'):
 s=p.stat();result['key_metadata'].append({'path':str(p),'mode':oct(s.st_mode&511),'size':s.st_size,'inode':s.st_ino,'root_mode':oct(p.parent.stat().st_mode&511),'key_value_read':False})
for key in ('service_pid','engine_pid'):
 pid=result['network_status'].get(key);result[key+'_lstart']=start(pid)if pid else None
(r/'final-observation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
