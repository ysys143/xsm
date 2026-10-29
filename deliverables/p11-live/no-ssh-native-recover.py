"""Post-abort own-fixture readback/cleanup only. Never triggers native work."""
import json,os,signal,socket,subprocess,time
from pathlib import Path

def start(pid):
 return subprocess.run(['/bin/ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True,timeout=5).stdout.strip() or None

def run(root):
 root=Path(root).resolve()
 if not root.name.startswith('p11-C-no-ssh-') or root.stat().st_uid!=os.getuid():raise RuntimeError('not own fixture')
 evidence={}
 for name in ('peer-final.json','ready.json','restricted.json','native-starting.json','engine-handles.json','result.json'):
  p=root/name
  if p.exists():evidence[name]=json.loads(p.read_text())
 handles=evidence.get('engine-handles.json',[])
 helper=evidence.get('peer-final.json') or evidence.get('ready.json')
 if helper:handles=handles+[{'pid':helper['helper_pid'],'lstart':helper['helper_lstart']}]
 cleanup=[]
 for h in handles:
  pid=h['pid'];before=start(pid)
  if before is not None:
   if before!=h['lstart']:raise RuntimeError('PID generation mismatch; no signal')
   os.kill(pid,signal.SIGTERM)
   end=time.monotonic()+5
   while start(pid) is not None and time.monotonic()<end:time.sleep(.1)
   if start(pid) is not None:os.kill(pid,signal.SIGKILL)
  cleanup.append({'pid':pid,'lstart':h['lstart'],'was_live':before is not None,'remaining':start(pid) is not None})
 sock=socket.socket(socket.AF_UNIX);code=sock.connect_ex(str(root/'state/network.sock'));sock.close()
 native=list((root/'native').rglob('result.json')) if (root/'native').exists() else []
 out={'at':time.time(),'root':str(root),'evidence':evidence,'cleanup':cleanup,'remaining_count':sum(r['remaining'] for r in cleanup),'ipc_connect_after_stop':code,'native_result_files':len(native),'recovery_scope':'post-abort evidence and own PID/lstart cleanup only; state preserved'}
 (root/'post-abort-readback.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));return out
if __name__=='__main__':
 import sys
 print(json.dumps(run(sys.argv[1]),ensure_ascii=False))
