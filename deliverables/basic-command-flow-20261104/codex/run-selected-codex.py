import json,os,pathlib,subprocess,time,sys
sys.path.insert(0,'/Users/jaesolshin/Documents/GitHub/cross-session-messaging')
from xsm.codex_daemon import _Conn,socket_path
m=json.loads(pathlib.Path('/private/tmp/xsm-selected-codex-location.json').read_text());root=pathlib.Path(m['root'])
c=_Conn(socket_path(m['native_home']),time.monotonic()+5)
try:
 c.call('init','initialize',{'clientInfo':{'name':'xsm-selected-test','version':'dev'},'capabilities':{'experimentalApi':True}});c.send({'method':'initialized'})
 reply=c.call('status','thread/read',{'threadId':m['session_id'],'includeTurns':False})
 assert reply['result']['thread']['status']['type']=='notLoaded', 'selected thread is busy or loaded; do not start'
finally:c.close()
base='XSM_HOME='+m['state']+' /Users/jaesolshin/Documents/GitHub/cross-session-messaging/bin/xsm'
prompt=("사용자가 승인한 기존 시험 대화(ref:8e85bd)의 격리 XSM 기본 왕복 시험만 수행하세요. 코드·프로젝트 문서·설정·권한·기존 작업은 바꾸지 마세요. 이번 시험에서 CLI 버전을 맞추기 위해 아래 절대경로를 그대로 씁니다. 새 세션을 만들거나 다른 작업을 이어서 하지 마세요. "
 + '먼저 '+base+' who --table 로 실제 ref가 8e85bd인지 확인하세요. 그 다음 '+base+' inbox --json --wait 10 을 딱 한 번 실행해 basic-codex-selected-41acb7 요청만 읽으세요. 다른 것은 처리하지 마세요. 그 요청이 없으면 없다고 말하고 멈추세요. '
 + '실제로 읽은 그 요청의 claim token만 '+base+' ack TOKEN 으로 ACK하고, '+base+' send ref:92b8d2 --kind reply --reply-to basic-codex-selected-41acb7 --outcome succeeded --wake never --text XSM_CODEX_SELECTED_REPLY_41acb7 로 한 번 회신하세요. 마지막으로 XSM_CODEX_SELECTED_DONE_41acb7 만 출력하고 종료하세요. 셸 승인이나 훅 신뢰가 막으면 우회·설정 변경 없이 그대로 실패를 보고하세요. 대기 루프는 만들지 마세요.')
(root/'requested-prompt.txt').write_text(prompt)
env=os.environ.copy()
for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_THREAD_ID','CODEX_SESSION_ID'):env.pop(key,None)
env.update(CODEX_HOME=m['native_home'],XSM_HOME=m['state'],XSM_PYTHON=sys.executable)
start=time.monotonic()
try:
 with (root/'native.jsonl').open('wb') as out,(root/'native.stderr').open('wb') as err:
  p=subprocess.run(['codex','exec','resume','--json',m['session_id'],'-'],input=prompt.encode(),stdout=out,stderr=err,env=env,timeout=115)
 result={'exit_code':p.returncode,'seconds':round(time.monotonic()-start,3)}
except subprocess.TimeoutExpired:
 result={'status':'timeout','seconds':round(time.monotonic()-start,3)}
(root/'process-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
