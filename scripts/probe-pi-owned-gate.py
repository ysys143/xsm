#!/usr/bin/env python3
"""Exercise native Pi input gating over the actual private worker descriptor."""
import json,os,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from xsm.native_worker_control import WorkerControl
import argparse
parser=argparse.ArgumentParser(description='Pinned native Pi pre-model binding; no real provider or credentials.')
parser.add_argument('--native-package',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
results=[]
for mode in ('accept','refuse'):
 callbacks=[]
 def bind(sid):
  callbacks.append(sid)
  if mode=='refuse':raise ValueError('explicit fixture refusal')
 control=WorkerControl(bind)
 env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ};env['XSM_OWNED_CONTROL_FD']=str(control.child.fileno())
 with (out/(mode+'.log')).open('w') as log:
  p=subprocess.Popen(['node',str(repo/'scripts/probe-pi-owned-gate.mjs'),str(args.native_package.resolve()),str(repo),str(out/(mode+'.json')),mode],env=env,pass_fds=(control.child.fileno(),),stdout=log,stderr=log)
  control.start()
  try:code=p.wait(timeout=40)
  finally:
   if p.poll() is None:p.kill();p.wait()
   control.close()
 data=json.loads((out/(mode+'.json')).read_text()) if (out/(mode+'.json')).exists() else {}
 result=dict(mode=mode,exit=code,callbacks=callbacks,bound=control.native_id,report=data)
 results.append(result)
(out/'result.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
assert all(r['exit']==0 and r['report']['passed'] and r['callbacks']==[r['report']['nativeID']]*(2 if r['mode']=='accept' else 1) for r in results)
