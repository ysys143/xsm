"""Pre-exec metadata/kernel check in actual eventual native PID; no model injection."""
import importlib.util,json,os,socket,sys,time
from pathlib import Path
p=Path(__file__).resolve().parent/'no-ssh-v2-proc.py';spec=importlib.util.spec_from_file_location('ownedproc',p);P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
s=socket.socket();s.settimeout(3)
try:s.connect(('100.123.30.11',22));proof={'connected':True}
except OSError as e:proof={'connected':False,'errno':e.errno,'type':type(e).__name__}
finally:s.close()
metadata={'observed_at':time.time(),'own_process':P.info(os.getpid()),'cwd':os.getcwd(),'kernel_peer_tcp22':proof,'inherited_profile':'(version 1) (allow default) (deny network-outbound (remote tcp "*:22"))','source':'nonprivileged native pre-exec probe; exec preserves PID/start; not model-generated metadata','requested_native_executable':sys.argv[1]}
Path('native-root-metadata.json').write_text(json.dumps(metadata,indent=2));os.chmod('native-root-metadata.json',0o600)
if proof.get('errno') not in (1,13):raise RuntimeError('native launch lacks required inherited SSH denial')
os.execv(sys.argv[1],sys.argv[1:])
