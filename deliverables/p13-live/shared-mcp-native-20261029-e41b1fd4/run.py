"""One factory native subagent evaluation, with real setup registration only."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

ROOT = Path('/private/tmp/shared-mcp-native-yjfl3mjl')
SOURCE = Path('/private/tmp/xsm-p13-postqa-frozen-bukwksw6')
PROFILE = Path('/Users/jaesolshin/.codex-3')
STOP_AT = 1793213910  # replaced below with an explicit UTC parse
from datetime import datetime, timezone
STOP_AT = datetime.fromisoformat('2026-10-28T20:58:30+00:00').timestamp()
GOAL = ('이 작업공간에서 native 하위 에이전트 검토자 두 명과 협업해 주세요. '
        '한 명은 2+2=5 주장을 독립 검토하고, 다른 한 명은 0+0=0 경계를 독립 검토하세요. '
        '두 검토자는 xsm으로 서로를 찾아 직접 질문과 실제 답을 주고받고, '
        '각자 자신의 짧은 검토 메모 사본을 상대에게 자료로 전달해 내용을 확인하세요. '
        '각자 후속 확인을 한 번 더 하여 자기 대화에 귀속된 작업과 자료가 맞는지 살펴보세요. '
        '부모가 본문을 중계하거나 다른 대화의 권한을 열지 말고 각 동료가 직접 수행하게 하세요. '
        '마지막에는 실제로 수행한 것과 불가능하거나 확인하지 못한 것을 구분해 보고하고 동료 작업을 정리하세요.')
out = {'label': 'A23-03 real native subagent process-sharing observation',
       'status': 'in-progress', 'native_CLI_launches': 1, 'native_automatic_retries': 0,
       'root': str(ROOT), 'source': str(SOURCE), 'registration_setup': [],
       'proxy_rewrites_or_fan_in': False, 'goal': GOAL,
       'basis': 'coordinator native-function evaluation; no new permission approval inferred'}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def save(name, value):
    p = ROOT / name
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    p.chmod(0o600)


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def events(path):
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return []
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result


def lstart(pid):
    return subprocess.run(['ps','-o','lstart=','-p',str(pid)], capture_output=True, text=True).stdout.strip() or None


def profile_guard():
    return {n: sha((PROFILE/n).read_bytes()) if (PROFILE/n).is_file() else None
            for n in ('config.toml','hooks.json','settings.json')}


def source_guard():
    return {str(p.relative_to(SOURCE)):sha(p.read_bytes()) for directory in ('xsm','hooks','skills')
            for p in sorted((SOURCE/directory).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}


os.environ['XSM_HOME'] = str(ROOT/'state')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))
registry = importlib.import_module('xsm.registry')
registered = set()
root_cid = None
known_threads = {}


def observe_and_register():
    global root_cid, known_threads
    root_cid = root_cid or next((x.get('thread_id') for x in events(ROOT/'native.jsonl')
                                if x.get('type')=='thread.started'), None)
    if not root_cid:
        return
    con = sqlite3.connect('file:'+str(PROFILE/'state_5.sqlite')+'?mode=ro', uri=True, timeout=1)
    try:
        rows = con.execute('select id,name,cwd,source,rollout_path from threads where cwd=?',
                           (str(ROOT/'work'),)).fetchall()
    finally:
        con.close()
    candidates = {v[0]:v for v in rows}
    allowed = {root_cid}
    for _ in range(4):
        for sid, row in candidates.items():
            try:
                parent = (((json.loads(row[3]) or {}).get('subagent') or {}).get('thread_spawn') or {}).get('parent_thread_id')
            except (ValueError, AttributeError):
                parent = None
            if parent in allowed:
                allowed.add(sid)
    known_threads = {sid:{'id':sid,'name':row[1],'cwd':row[2], 'source':row[3],
                           'rollout_path':row[4]} for sid,row in candidates.items() if sid in allowed}
    for folder in (ROOT/'proxies').iterdir():
        h = read(folder/'handles.json')
        if not h:
            continue
        ancestor = next((x for x in h['native_ancestor_chain'] if Path(x['comm']).name=='codex'), None)
        if not ancestor or lstart(ancestor['pid'])!=ancestor['lstart']:
            continue
        observed = {root_cid} if len(list((ROOT/'proxies').iterdir()))==1 else set()
        for row in events(folder/'events.jsonl'):
            meta = row.get('actual_meta')
            if row.get('direction')=='client' and row.get('method')=='tools/call' and isinstance(meta,dict):
                if isinstance(meta.get('threadId'),str):
                    observed.add(meta['threadId'])
        for sid in observed & set(known_threads):
            key = (sid,ancestor['pid'])
            if key in registered:
                continue
            row = known_threads[sid]
            rec = registry.upsert('codex',str(PROFILE),sid,ancestor['pid'],row['cwd'],
                                  name=row['name'] or None,mcp_pid=h['server']['pid'])
            registered.add(key)
            out['registration_setup'].append({'at':time.time(),'CID':sid,'home':str(PROFILE),
                 'native_pid':ancestor['pid'],'native_lstart':ancestor['lstart'],
                 'server_pid':h['server']['pid'],'proxy_pid':h['proxy']['pid'],
                 'provider_source':row['source'],'record':rec,
                 'basis':'actual native DB CID/source + actual MCP metadata/ancestor; initial setup only'})
    out['actual_native_threads'] = list(known_threads.values())
    save('result.json', out)


before_source = source_guard()
out['profile_before'] = profile_guard()
save('source-manifest.json', before_source)
out['actual_CLI_version'] = subprocess.run(['codex','--version'],capture_output=True,text=True).stdout.strip()
env = dict(os.environ,CODEX_HOME=str(PROFILE),XSM_HOME=str(ROOT/'state'),PYTHONPATH=str(SOURCE),
           PYTHONDONTWRITEBYTECODE='1',PATH=str(SOURCE/'bin')+os.pathsep+os.environ.get('PATH',''))
for key in ('CODEX_THREAD_ID','CLAUDE_CODE_SESSION_ID','CLAUDE_SESSION_ID',
            'CLAUDE_CODE_MESSAGING_SOCKET','CLAUDECODE','ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY'):
    env.pop(key,None)
args = ['codex','exec','--ignore-user-config','--json','--sandbox','workspace-write',
        '-c','approval_policy="never"','-c','mcp_servers.xsm.command="/usr/bin/python3"',
        '-c','mcp_servers.xsm.args='+json.dumps([str(ROOT/'proxy.py'),str(ROOT),str(SOURCE)]),
        '-c','mcp_servers.xsm.cwd='+json.dumps(str(SOURCE))]
for key in ('XSM_HOME','CODEX_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE'):
    args+=['-c','mcp_servers.xsm.env.'+key+'='+json.dumps(env[key])]
args.append(GOAL)
streams=[(ROOT/'native.jsonl').open('w'),(ROOT/'native.stderr').open('w')]
proc=subprocess.Popen(args,cwd=str(ROOT/'work'),env=env,stdin=subprocess.DEVNULL,
                      stdout=streams[0],stderr=streams[1],text=True,start_new_session=True)
out['handle']={'pid':proc.pid,'lstart':lstart(proc.pid),'alive_after_start':proc.poll() is None,'argv':args}
out['started_utc']=datetime.now(timezone.utc).isoformat()
save('result.json',out)
try:
    while time.time()<STOP_AT and proc.poll() is None:
        observe_and_register()
        time.sleep(.05)
    out['status']='native completed' if proc.poll() is not None else 'bounded native stop'
except BaseException as exc:
    out['status']='observer error; no automatic native retry'
    out['observer_error']={'type':type(exc).__name__,'message':str(exc)}
finally:
    own={proc.pid:out['handle']['lstart']}
    for folder in (ROOT/'proxies').iterdir():
        h=read(folder/'handles.json')
        if h:
            for row in h['native_ancestor_chain']:
                if Path(row['comm']).name=='codex':own[row['pid']]=row['lstart']
            for key in ('proxy','server'):own[h[key]['pid']]=h[key]['lstart']
    signals=[]
    for pid,start in own.items():
        if lstart(pid)==start:
            os.kill(pid,signal.SIGTERM);signals.append({'pid':pid,'lstart':start,'signal':'SIGTERM'})
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if lstart(proc.pid)==out['handle']['lstart']:proc.kill()
        proc.wait(timeout=5)
    for pid,start in own.items():
        if lstart(pid)==start:
            os.kill(pid,signal.SIGKILL);signals.append({'pid':pid,'lstart':start,'signal':'SIGKILL'})
    for stream in streams:stream.close()
    out['native_wrapper_exit']=proc.returncode
    out['cleanup_signals']=signals
    out['profile_after']=profile_guard()
    out['profile_unchanged']=out['profile_before']==out['profile_after']
    out['source_unchanged']=before_source==source_guard()
    out['finished_utc']=datetime.now(timezone.utc).isoformat()
    save('result.json',out)
    print(json.dumps({'status':out['status'],'native_CLI_launches':1,
                      'native_threads_observed':len(known_threads),
                      'MCP_process_instances':len(list((ROOT/'proxies').iterdir())),
                      'root':str(ROOT)},ensure_ascii=False),flush=True)
