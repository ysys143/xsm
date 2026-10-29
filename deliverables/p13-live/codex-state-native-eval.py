"""PTY-owned Codex TUI state observation; no native responses/queues injected."""
import os,sys,json,time,tempfile,subprocess,pty,fcntl,termios,struct,select,threading,hashlib,re,signal
from pathlib import Path
REPO=Path(__file__).resolve().parents[2];SOURCE=Path('/private/tmp/xsm-p13-postqa-frozen-bukwksw6');PROFILE=Path.home()/'.codex-3'
sys.path.insert(0,str(SOURCE))
ROOT=Path(tempfile.mkdtemp(prefix='p13-codex-state-native-',dir='/private/tmp'));os.chmod(ROOT,0o700)
OUT=REPO/'deliverables/p13-live/codex-state-native-results.json'
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2));os.chmod(p,0o600)
def env():
 e=dict(os.environ)
 for k in list(e):
  if k.startswith(('XSM','CODEX_')) or k in ('OPENAI_API_KEY','CODEX_API_KEY','ANTHROPIC_API_KEY','OPENAI_BASE_URL'):e.pop(k,None)
 e.update(CODEX_HOME=str(PROFILE),XSM_HOME=str(ROOT/'state'),PYTHONPATH=str(SOURCE),PYTHONDONTWRITEBYTECODE='1',TERM='xterm-256color')
 return e
def args(tui=False):
 a=['codex'] if tui else ['codex','exec','--json']
 a+=['--sandbox','workspace-write','-c','approval_policy="never"']
 if tui:a+=['--no-alt-screen']
 cfg={'mcp_servers.xsm.command':'/usr/bin/python3','mcp_servers.xsm.args':['-m','xsm','mcp'],'mcp_servers.xsm.cwd':str(SOURCE)}
 for k in ('CODEX_HOME','XSM_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE'):cfg['mcp_servers.xsm.env.'+k]=env()[k]
 for k,v in cfg.items():a+=['-c',k+'='+json.dumps(v)]
 return a

def main():
 global REPORT,MASTER,PROC
 from xsm import paths,registry,identity
 paths.HOME=str(ROOT/'state');os.environ['XSM_HOME']=paths.HOME
 REPORT={'root':str(ROOT),'source':str(SOURCE),'profile':str(PROFILE),'started_at':time.time(),'status':'setup','states':[],
 'configuration':'existing user profile + invocation-only frozen xsm MCP/env; no ignore-user-config/tool disable/instruction replacement',
 'subscription_probe':'codex login status: Logged in using ChatGPT','cli_version':subprocess.check_output(['codex','--version'],text=True).strip(),
 'setup_registrations':[],'controller_tui_prompts':0,'controller_esc_keys':0,'controller_receiver_inbox_polls':0,'manual_queue_or_response_injection':0}
 manifest=json.loads((REPO/'deliverables/p13-live/post-qa-source-manifest.json').read_text());REPORT['source_manifest_match']=all(hashlib.sha256((SOURCE/p).read_bytes()).hexdigest()==v for p,v in manifest['files'].items())
 REPORT['profile_hash_before']={p:hashlib.sha256((PROFILE/p).read_bytes()).hexdigest() if (PROFILE/p).is_file() else None for p in ('config.toml','hooks.json','settings.json')}
 save(OUT,REPORT)
 MASTER,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',45,130,0,0))
 goal='이 세션은 공개 산술 검토 담당입니다. 동료의 산술 질문이 들어오면 검토하고 원래 동료에게 회신하세요. 파일·설정·권한을 바꾸지 마세요. 초기 준비가 끝나면 P13-TUI-READY-'+ROOT.name+' 라고 짧게 보고하세요.'
 PROC=subprocess.Popen(args(True)+[goal],cwd=str(REPO),env=env(),stdin=slave,stdout=slave,stderr=slave,start_new_session=True);os.close(slave)
 REPORT['receiver_tui_pid']=PROC.pid;REPORT['receiver_tui_lstart']=identity.lstart(PROC.pid);REPORT['receiver_cwd']=str(REPO);REPORT['controller_tui_prompts']=1
 stop=threading.Event()
 def reader():
  with open(ROOT/'receiver.pty','ab',buffering=0) as f:
   while not stop.is_set():
    ready,_,_=select.select([MASTER],[],[],.2)
    if not ready:continue
    try:data=os.read(MASTER,65536)
    except OSError:break
    if not data:break
    f.write(data)
    # Terminal capability replies only, never model/user responses.
    if b'\x1b[6n' in data:os.write(MASTER,b'\x1b[1;1R')
    if b'\x1b[c' in data:os.write(MASTER,b'\x1b[?1;2c')
 t=threading.Thread(target=reader,daemon=True);t.start()
 save(ROOT/'control.json',{'root':str(ROOT),'tui_pid':PROC.pid,'argv':args(True),'goal':goal})
 save(OUT,REPORT)
 try:
  # The external operator observes raw PTY and actual rollout before state actions.
  while time.time()-REPORT['started_at']<18*60:
   command=ROOT/'command.json'
   if command.exists():
    c=json.loads(command.read_text());command.unlink()
    if c['action']=='stop':break
    if c['action']=='input':os.write(MASTER,c['text'].encode());REPORT['controller_tui_prompts']+=1
    if c['action']=='esc':os.write(MASTER,b'\x1b');REPORT['controller_esc_keys']+=1
    save(OUT,REPORT)
   if PROC.poll() is not None:break
   time.sleep(.2)
 finally:
  # Only our exact TUI process/session. Do not terminate the shared daemon.
  if PROC.poll() is None:
   PROC.terminate()
   try:PROC.wait(timeout=5)
   except subprocess.TimeoutExpired:PROC.kill();PROC.wait()
  stop.set();t.join(timeout=2);os.close(MASTER)
  REPORT['tui_exit']=PROC.returncode;REPORT['tui_alive_after']=identity.pid_alive(PROC.pid);REPORT['status']='controller-stopped';save(OUT,REPORT)
if __name__=='__main__':main()
