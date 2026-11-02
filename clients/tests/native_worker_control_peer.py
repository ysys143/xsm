"""Real inherited descriptor interoperability; no runtime/profile/model calls."""
import json,os,socket,subprocess,sys,tempfile,threading
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
mode,node=sys.argv[1:];temp=tempfile.TemporaryDirectory(prefix='xsm-node-worker-control-')
env={key:os.environ[key] for key in ('PATH','LANG','TMPDIR') if key in os.environ};env.update(HOME=temp.name,XSM_HOME=temp.name+'/state',PYTHONDONTWRITEBYTECODE='1')
os.environ.clear();os.environ.update(env)
from xsm.native_worker_control import WorkerControl
calls=[];control=None;thread=None
if mode in ('normal','refuse'):
 def bind(native_id):
  if mode=='refuse':raise ValueError('fixture refusal')
  calls.append(native_id)
 control=WorkerControl(bind);parent,child=control.parent,control.child
else:parent,child=socket.socketpair()
env['XSM_OWNED_CONTROL_FD']=str(child.fileno())
process=subprocess.Popen([node,str(root/'clients/tests/native_worker_control_peer.mjs'),mode],env=env,pass_fds=(child.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
if control:control.start()
else:
 child.close()
 def reply():
  with parent.makefile('rwb',buffering=0) as stream:
   request=json.loads(stream.readline())
   if mode=='bad-duplicate':wire='{"jsonrpc":"2.0","id":'+str(request['id'])+',"result":{"bound":false,"bound":true}}\n'
   elif mode=='bad-bool-id':wire=json.dumps({'jsonrpc':'2.0','id':True,'result':{'bound':True}})+'\n'
   elif mode=='bad-int-confirmation':wire=json.dumps({'jsonrpc':'2.0','id':request['id'],'result':{'bound':1}})+'\n'
   else:wire='{"jsonrpc":"2.0","id":1,"result":{"bound":true}}\n'
   try:stream.write(wire.encode())
   except OSError:pass
 thread=threading.Thread(target=reply);thread.start()
try:
 stdout,stderr=process.communicate(timeout=5)
 result={'exit':process.returncode,'node':json.loads(stdout),'bindings':calls}
 if process.returncode:raise RuntimeError('Node fixture failed: '+stderr)
 print(json.dumps(result,ensure_ascii=False))
finally:
 if process.poll() is None:process.kill();process.wait()
 if control:control.close()
 else:
  parent.close();thread.join(timeout=2)
 temp.cleanup()
