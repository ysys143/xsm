from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,time
root=Path(__file__).resolve().parent
label=sys.argv[1]; interpreter=sys.argv[2]
record=root/(label+'.json')
if record.exists():raise SystemExit('preserve prior suite result')
env=dict(os.environ,PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1',XSM_NET_BINARY=str(root/'native/xsm-net/target/release/xsm-net'),XSM_TEST_NET_BINARY=str(root/'native/xsm-net/target/release/xsm-net'),XSM_TEST_RELAY_BINARY='/private/tmp/xsm-selfrelay-4qh_rrfo/target/debug/iroh-relay')
for k in ['ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY']:env.pop(k,None)
args=[interpreter,'-B','-m','unittest','discover','-s','tests','-q']
meta={'label':label,'argv':args,'frozen_source':str(root),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
started=time.monotonic()
with (root/(label+'.stdout')).open('wb') as out,(root/(label+'.stderr')).open('wb') as err:
 proc=subprocess.Popen(args,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
 meta['pid']=proc.pid;record.write_text(json.dumps(meta));print(json.dumps({'label':label,'pid':proc.pid,'root':str(root)}),flush=True)
 proc.wait()
meta.update(exit_code=proc.returncode,elapsed_seconds=round(time.monotonic()-started,3),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
meta['stderr_sha256']=hashlib.sha256((root/(label+'.stderr')).read_bytes()).hexdigest();record.write_text(json.dumps(meta,indent=2))
print(json.dumps(meta),flush=True)
print('\n'.join((root/(label+'.stderr')).read_text(errors='replace').splitlines()[-24:]),flush=True)
raise SystemExit(proc.returncode)
