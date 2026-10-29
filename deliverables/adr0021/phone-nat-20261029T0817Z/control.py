from pathlib import Path
import hashlib,io,json,os,shlex,shutil,subprocess,sys,tarfile,time
BASE=Path(__file__).resolve().parent
CONFIG=json.loads((BASE/'runner.json').read_text())
MAC=Path(CONFIG['mac_root']);PHONE=CONFIG['phone_root'];REPO=Path('/Users/jaesolshin/Documents/GitHub/cross-session-messaging')
BINARY='/data/data/com.termux/files/usr/tmp/xsm-net-product-co8sb0zw/target/aarch64-linux-android/release/xsm-net'
BINARY_SHA='19c259be759a63cc149db1e846db48a3e35be5712d62c9572085250d0e31247a'
PHONE_ENV={'LD_LIBRARY_PATH':'/data/data/com.termux/files/usr/tmp/xsm-net-product-co8sb0zw/runtime-lib:/data/data/com.termux/files/usr/lib','SSL_CERT_FILE':'/data/data/com.termux/files/usr/etc/tls/cert.pem','LD_PRELOAD':'/data/data/com.termux/files/usr/lib/libtermux-exec.so'}
SSH=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/private/tmp/phone-ssh-obo10a51/known_hosts','-o','GlobalKnownHostsFile=/dev/null','-o','IdentitiesOnly=yes','-o','IdentityFile=/Users/jaesolshin/.ssh/id_ed25519','-o','ConnectTimeout=8','-p','8022','u0_a451@100.85.28.75']
def invoke(argv,data=None,timeout=85):
 r=subprocess.run(argv,input=data,capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError('owned operation exit '+str(r.returncode)+': '+r.stderr.decode(errors='replace')[:300])
 return json.loads(r.stdout)
def local(action,*args,data=None):return invoke([sys.executable,'-B',str(MAC/'payload/node.py'),action,*args],data)
def phone(action,*args,data=None):
 cmd=['env']+[k+'='+v for k,v in PHONE_ENV.items()]+['python','-B',PHONE+'/payload/node.py',action,*args]
 return invoke(SSH+[' '.join(shlex.quote(x) for x in cmd)],data)
def status(which):return which('cli','status')['result']
def write(name,value):
 p=BASE/name;p.write_text(json.dumps(value,indent=2));p.chmod(0o600)
 return p
if __name__=='__main__':
 action=sys.argv[1]
 if action=='prepare':
  for p in (REPO/'xsm').glob('*.py'):shutil.copy2(p,MAC/'payload/xsm'/p.name)
  body=io.BytesIO()
  with tarfile.open(fileobj=body,mode='w:gz') as archive:
   for p in (MAC/'payload/xsm').glob('*.py'):archive.add(p,arcname='xsm/'+p.name,recursive=False)
  script='''import hashlib,json,pathlib,shutil,sys,tarfile
root=pathlib.Path(sys.argv[1]);payload=root/'payload';source=pathlib.Path(sys.argv[2])
assert hashlib.sha256(source.read_bytes()).hexdigest()==sys.argv[3]
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
 for member in archive:
  if not member.isfile() or member.name.startswith('/') or '..' in pathlib.PurePosixPath(member.name).parts:raise SystemExit('unexpected payload')
  p=payload/member.name;p.write_bytes(archive.extractfile(member).read());p.chmod(0o600)
binary=payload/'bin/xsm-net';binary.parent.mkdir(mode=0o700,exist_ok=True);shutil.copy2(source,binary);binary.chmod(0o700)
manifest={str(p.relative_to(payload)):hashlib.sha256(p.read_bytes()).hexdigest() for p in payload.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json'}
(payload/'manifest.json').write_text(json.dumps(manifest,sort_keys=True));(payload/'manifest.json').chmod(0o600)
print(json.dumps({'files':len(manifest),'binary_sha256':manifest['bin/xsm-net']}))
'''
  cmd='python -c '+shlex.quote(script)+' '+shlex.quote(PHONE)+' '+shlex.quote(BINARY)+' '+BINARY_SHA
  result=invoke(SSH+[cmd],body.getvalue())
  manifest={str(p.relative_to(MAC/'payload')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (MAC/'payload').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json'}
  (MAC/'payload/manifest.json').write_text(json.dumps(manifest,sort_keys=True));(MAC/'payload/manifest.json').chmod(0o600)
  write('prepared-current.json',{'phone':result,'mac':{'files':len(manifest),'binary_sha256':manifest['bin/xsm-net']},'phone_environment':PHONE_ENV,'mac_process_policy':CONFIG['mac_process_policy']})
  print(json.dumps({'prepared':True,'phone':result,'mac_files':len(manifest)}))
 elif action=='start':
  result={'mac':local('start'),'phone':phone('start')};write('started.json',result);print(json.dumps(result))
 elif action=='join':
  init=local('cli','init','adr21-cellular','--machine-name','mac-public-relay')
  assert init['exit']==0,init
  invitation=local('cli','invite')
  assert invitation['exit']==0,invitation
  ticket=Path(invitation['result']['ticket_file']).read_bytes()
  joined=phone('join-stdin','phone-cellular',data=ticket)
  result={'init':init,'invitation_public_result':invitation,'join':joined,'mac_status':status(local),'phone_status':status(phone)}
  write('join-result.json',result);print(json.dumps({'init_exit':init['exit'],'join_exit':joined['exit'],'join_code':joined['result'].get('code'),'both_active':result['mac_status'].get('active') and result['phone_status'].get('active'),'network_ids_match':result['mac_status'].get('network',{}).get('network_id')==result['phone_status'].get('network',{}).get('network_id')}))
 elif action=='ping':
  a,b=status(local),status(phone)
  results={'mac_to_phone':local('ping',data=json.dumps(b['address']).encode()),'phone_to_mac':phone('ping',data=json.dumps(a['address']).encode()),'mac_status':status(local),'phone_status':status(phone)}
  write('ping-result.json',results);print(json.dumps(results))
 elif action=='collect':
  data={'mac':local('audit'),'phone':phone('audit')};write('transport-audit.json',data)
  print(json.dumps({k:len(v) for k,v in data.items()}))
 elif action=='stop':
  result={}
  for name,call in [('mac',local),('phone',phone)]:
   try:result[name]=call('stop')
   except Exception as e:result[name]={'error':str(e)}
  write('cleanup.json',result);print(json.dumps(result))
 else:raise SystemExit('unknown action')
