import os,sys,json,subprocess,time,shutil,stat,importlib.util,signal,re
from pathlib import Path
V=json.loads(Path(sys.argv[1]).read_text())
assert V.get('new_corrected_sample_authorized')is True
assert not(Path(V['book'])/'actor-owner.json').exists();R=Path(V['book']);O=Path(V['artifact']);sdk=importlib.util.spec_from_file_location('kp',R/'shim/proc_reader.py');kp=importlib.util.module_from_spec(sdk);sdk.loader.exec_module(kp)
archive=R/('before-streaming-'+str(time.time_ns()));archive.mkdir(mode=0o700,exist_ok=True)
for n in('actor','actor-owner.json','registration.json'):
 p=R/n
 if p.exists():shutil.move(str(p),str(archive/n))
(R/'actor/proxies').mkdir(mode=0o700,parents=True)
goal='이 세션을 xsm에서 찾을 수 있게 공개해 두세요. 다른 머신 동료의 검토 담당 a1입니다. 최신 안내는 /private/tmp/native-journey-samename-book-7thlq5pg/payload/skills/xsm/SKILL.md입니다. 실제로 받은 협업 준비 확인 한 건에 역할과 준비 상태를 직접 회신하고 처리 확인을 마칠 때까지 대기하세요. 소스·프로필·권한·본문·ACK·동의 답변을 상태파일에서 보정하지 마세요.'
assert not re.search('[\u3400-\u9fff\u3040-\u30ff]',goal)and len(goal)<500
args=['/usr/bin/sandbox-exec','-f',str(R/'write-ssh-guard.sb'),str(R/'runtime/claude'),'--print','--input-format','stream-json','--output-format','stream-json','--verbose','--no-session-persistence','--include-hook-events','--permission-prompts','none','--mcp-config',str(R/'claude-mcp-observe.json'),'--strict-mcp-config','--settings',str(R/'claude-invocation-settings.json')]
assert args.count('--input-format')==1 and args[args.index('--input-format')+1]=='stream-json'
env=dict(os.environ,PATH=str(R/'payload/bin')+os.pathsep+os.environ.get('PATH',''),CLAUDE_CONFIG_DIR='/Users/jaesolshin/.claude-3',XSM_HOME=str(R/'state'),PYTHONPATH=str(R/'payload'),PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(R/'tmp'),XSM_PYTHON='/usr/bin/python3')
for k in list(env):
 if k.startswith(('CODEX_','ORCA_','XSM_WORKER'))or k in('ANTHROPIC_API_KEY','OPENAI_API_KEY','CLAUDECODE','CLAUDE_CODE_SESSION_ID','CLAUDE_SESSION_ID'):env.pop(k,None)
fifo=R/'actor/user-goals.fifo'
os.mkfifo(fifo,0o600)
input_fd=os.open(fifo,os.O_RDWR)
out=(R/'actor/native.jsonl').open('wb');err=(R/'actor/native.stderr').open('wb');p=subprocess.Popen(args,cwd=str(R/'work'),env=env,stdin=input_fd,stdout=out,stderr=err,start_new_session=True)
owner={'pid':p.pid,'lstart':kp.kernel(p.pid)['lstart'],'runtime':'claude','role':'reviewer','argv':args,'goal':goal,'stdin_user_messages_sent':1,'streaming_controller_PID':os.getpid(),'streaming_controller_start':kp.kernel(os.getpid())['lstart'],'no_added_allow_rules':True,'model_override':False};(R/'actor-owner.json').write_text(json.dumps(owner,ensure_ascii=False,indent=2)+'\n');(O/'streaming-claude-launch.json').write_text(json.dumps(owner,ensure_ascii=False,indent=2)+'\n')
os.write(input_fd,(json.dumps({'type':'user','message':{'role':'user','content':goal}},ensure_ascii=False)+'\n').encode());print(json.dumps({'native_PID':p.pid,'controller_PID':os.getpid(),'user_message_count':1}),flush=True)
registered=False;deadline=time.monotonic()+900
continuation_sent=False
try:
 while time.monotonic()<deadline and p.poll()is None:
  if not registered:
   ev=[]
   for line in(R/'actor/native.jsonl').read_text().splitlines():
    try:ev.append(json.loads(line))
    except ValueError:pass
   init=next((e for e in ev if e.get('type')=='system'and e.get('subtype')=='init'),None)
   if init:
    beacons=[]
    for f in(R/'state/mcp').glob('*.json'):
     b=json.loads(f.read_text());proc=kp.kernel(b['pid'])
     if proc and proc['ppid']==p.pid:beacons.append((b,proc))
    native=kp.kernel(p.pid);ls=subprocess.run(['/usr/sbin/lsof','-a','-p',str(p.pid),'-U','-Fn'],capture_output=True,text=True,timeout=3).stdout;paths=sorted({x[1:]for x in ls.splitlines()if x.startswith('n/')and x.endswith('/'+str(p.pid)+'.sock')})
    if len(beacons)==1 and len(paths)==1:
     sock=Path(paths[0]);st=sock.stat();assert stat.S_ISSOCK(st.st_mode)and st.st_uid==native['uid']
     os.environ['XSM_HOME']=str(R/'state');os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'payload'));from xsm import registry
     record=registry.upsert('claude','/Users/jaesolshin/.claude-3',init['session_id'],p.pid,str(R/'work'),name='a1',mcp_pid=beacons[0][0]['pid'],socket=str(sock));proof={'CID':init['session_id'],'native':native,'MCP':beacons[0],'provider_init':init,'native_owned_socket':str(sock),'socket_inode':st.st_ino,'record':record,'basis':'actual provider init + actual kernel PID/UID/start/path + native MCP parent + OS-held native socket; initial setup only'};(R/'registration.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');(O/'streaming-claude-registration.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');registered=True;print(json.dumps({'actual_CID':init['session_id'],'registered':True}),flush=True)
  trigger=R/'actor/continue-user-goal.once'
  if trigger.exists()and not continuation_sent:
   follow='같은 대화에서 도착한 실제 미처리 업무가 있는지 제품 협업 도구로 확인하고 원래 동료의 업무 한 건을 마무리하세요. 중복 회신이나 상태파일 보정은 하지 마세요.'
   assert not re.search('[\u3400-\u9fff\u3040-\u30ff]',follow)
   os.write(input_fd,(json.dumps({'type':'user','message':{'role':'user','content':follow}},ensure_ascii=False)+'\n').encode());continuation_sent=True
  time.sleep(.05 if not registered else .25)
finally:
 if p.poll()is None:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
 os.close(input_fd);out.close();err.close();(R/'stream-controller-exit.json').write_text(json.dumps({'native_exit':p.returncode,'user_message_count':1+int(continuation_sent),'body_relays':0}));print(json.dumps({'native_exit':p.returncode}),flush=True)
