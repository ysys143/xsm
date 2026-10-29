"""P11 C fixture additions: process-only TCP:22 deny and autonomous engine pull."""
import ctypes,errno,importlib.util,json,os,socket,subprocess,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('C_fixture',BASE/'C-fixture-lib.py');C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
PROFILE='(version 1) (allow default) (deny network-outbound (remote tcp "*:22"))'
SSH_OPTIONS=['-S','none','-oControlMaster=no','-oControlPath=none','-oBatchMode=yes','-oConnectTimeout=4','-oStrictHostKeyChecking=yes','-oUpdateHostKeys=no']
class Node(C.Node):
 def start(self):
  real=subprocess.Popen
  def guarded(argv,*a,**kw):
   if argv[:2]==[str(self.binary),'daemon']:argv=['/usr/bin/sandbox-exec','-p',PROFILE]+argv
   return real(argv,*a,**kw)
  subprocess.Popen=guarded
  try:return super().start()
  finally:subprocess.Popen=real
 def process(self,phase,expected_sha):
  if self.cache:raise RuntimeError('single native turn only; no retry')
  return super().process(phase,expected_sha)
def deny_current():
 lib=ctypes.CDLL('/usr/lib/libsandbox.1.dylib');err=ctypes.c_char_p()
 lib.sandbox_init.argtypes=[ctypes.c_char_p,ctypes.c_uint64,ctypes.POINTER(ctypes.c_char_p)];lib.sandbox_init.restype=ctypes.c_int
 if lib.sandbox_init(PROFILE.encode(),0,ctypes.byref(err))!=0:raise RuntimeError('sandbox_init failed')
 return {'profile':PROFILE,'pid':os.getpid(),'lstart':C.process_start(os.getpid()),'applied':True}
def probes(ip):
 s=socket.socket();s.settimeout(3)
 try:s.connect((ip,22));kernel={'connected':True}
 except OSError as e:kernel={'connected':False,'errno':e.errno,'error_type':type(e).__name__}
 finally:s.close()
 result=subprocess.run(['/usr/bin/ssh']+SSH_OPTIONS+[ip,'true'],capture_output=True,text=True,timeout=8)
 text=result.stdout+result.stderr
 proof={'peer_ip':ip,'port':22,'kernel':kernel,'ssh_exit':result.returncode,'ssh_errno_denial':('Operation not permitted' in text or 'Permission denied' in text),'ssh_stderr_sha256':C.sha(result.stderr),'multiplex_disabled':True,'phase':'restricted preflight BEFORE measurement','ssh_probe_calls':1}
 if kernel.get('errno') not in (errno.EPERM,errno.EACCES) or result.returncode!=255 or not proof['ssh_errno_denial']:raise RuntimeError('SSH/kernel denial not proven')
 return proof
def control_message(node,label,data):return node.send('p11-c-local/qa-local',C.TASK+' '+label+' '+json.dumps(data,ensure_ascii=False))
def note(root,name,value):C.write_json(Path(root)/name,value)
