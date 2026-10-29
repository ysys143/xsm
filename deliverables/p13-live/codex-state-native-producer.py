"""Controlled real native producer; never substitutes receiver polling/replies."""
import sys,os,json,subprocess,time,hashlib
from pathlib import Path
SOURCE=Path('/private/tmp/xsm-p13-postqa-frozen-bukwksw6');BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
from xsm import identity
root=Path('/private/tmp/p13-codex-state-native-dv1ahfwm');profile=Path.home()/'.codex-3'
state=sys.argv[1];sid='01a1844f-fe38-7ce2-b466-7bb38e5a4c60'
env=dict(os.environ)
for k in list(env):
 if k.startswith(('XSM','CODEX_')) or k in ('OPENAI_API_KEY','CODEX_API_KEY','ANTHROPIC_API_KEY','OPENAI_BASE_URL'):env.pop(k,None)
env.update(CODEX_HOME=str(profile),XSM_HOME=str(root/'state'),PYTHONPATH=str(SOURCE),PYTHONDONTWRITEBYTECODE='1')
argv=['codex','exec','--json','--sandbox','workspace-write','-c','approval_policy="never"']
cfg={'mcp_servers.xsm.command':'/usr/bin/python3','mcp_servers.xsm.args':['-m','xsm','mcp'],'mcp_servers.xsm.cwd':str(SOURCE)}
for k in ('CODEX_HOME','XSM_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE'):cfg['mcp_servers.xsm.env.'+k]=env[k]
for k,v in cfg.items():argv+=['-c',k+'='+json.dumps(v)]
request='p13-tui-'+state+'-dv1ahfwm'
goal=('네이티브 TUI 동료의 산술 검토 QA입니다. 실제 동료 주소 codex:'+sid+' 에 xsm의 일반 질문 서비스로 다음 질문을 한 번만 요청하세요: '
      '"P13-TUI-'+state.upper()+': 2+2=5가 맞나요? 반례와 올바른 합을 답해주세요." '
      '질문 request_id는 '+request+', priority는 next, wait는 60을 사용하세요. 실제 회신을 기다려 결과를 보고하세요. '
      'timeout이면 같은 요청의 상태만 조회하고 새 질문·재전송·worker·권한변경은 하지 마세요. '
      '다른 세션·폴더·설정·파일을 변경하지 마세요. 수신자의 수신함을 대신 조회하지 마세요.')
argv.append(goal)
with open(root/(state+'-producer.jsonl'),'w') as out,open(root/(state+'-producer.stderr'),'w') as err:
 p=subprocess.Popen(argv,cwd=str(BASE.parents[1]),env=env,stdout=out,stderr=err,start_new_session=True)
 meta={'state':state,'producer_pid':p.pid,'producer_lstart':identity.lstart(p.pid),'started_at':time.time(),'request_id':request,'argv':argv,'goal':goal}
 (root/(state+'-producer-meta.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2))
 print(json.dumps({k:meta[k] for k in ('state','producer_pid','producer_lstart','request_id')},ensure_ascii=False),flush=True)
 try:code=p.wait(timeout=155)
 except subprocess.TimeoutExpired:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
  code=p.returncode;meta['timeout']=True
 meta['returncode']=code;meta['ended_at']=time.time();(root/(state+'-producer-meta.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2))
 print(json.dumps({'state':state,'returncode':code}),flush=True)
