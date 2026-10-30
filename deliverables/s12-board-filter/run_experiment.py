"""Subscription-only S12 runner. No global configuration writes, no API keys."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parent
RUNS=ROOT/'runs'
RUNS.mkdir(exist_ok=True)

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def env():
    e=os.environ.copy()
    # Never inspect or print credential values. Inherited API-key charging is
    # explicitly excluded; the CLI's existing subscription credentials remain.
    for k in ['ANTHROPIC_API_KEY','OPENAI_API_KEY','CLAUDECODE']:
        e.pop(k,None)
    return e

def claude_cmd(model):
    return ['claude','-p','--model',model,'--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--output-format','stream-json','--verbose','--include-partial-messages']

def codex_cmd(model):
    return ['codex','exec','--model',model,'--ephemeral','--sandbox','read-only','--json','--color','never','-c','mcp_servers.reason-network.enabled=false','-c','model_reasoning_effort="low"','-']

def parse_json(text):
    text=text.strip()
    if text.startswith('```'):
        text='\n'.join(text.splitlines()[1:-1])
    return json.loads(text)

def run(name,command,prompt,timeout=240):
    prefix=RUNS/name
    promptpath=prefix.with_suffix('.prompt.txt');promptpath.write_text(prompt)
    meta=dict(name=name,command=command,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
    dump(prefix.with_suffix('.started.json'),meta)
    t=time.monotonic()
    try:
        r=subprocess.run(command,input=prompt,text=True,capture_output=True,env=env(),cwd=ROOT,timeout=timeout)
        out,err=r.stdout,r.stderr;meta['returncode']=r.returncode
    except subprocess.TimeoutExpired as ex:
        out=ex.stdout or b'';err=ex.stderr or b''
        if isinstance(out,bytes):out=out.decode(errors='replace')
        if isinstance(err,bytes):err=err.decode(errors='replace')
        meta.update(returncode=None,error='timeout')
    meta['elapsed_seconds']=time.monotonic()-t
    prefix.with_suffix('.stdout.jsonl').write_text(out)
    prefix.with_suffix('.stderr.txt').write_text(err)
    events=[]
    for line in out.splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    models=set();response=[];usage=[]
    for event in events:
        if event.get('type')=='assistant':
            message=event.get('message',{});
            if message.get('model'):models.add(message['model'])
            response.extend(c.get('text','') for c in message.get('content',[]) if c.get('type')=='text')
        if event.get('type')=='result':
            meta['model_usage']=event.get('modelUsage',{})
            meta['claude_usage']=event.get('usage',{})
            meta['is_error']=event.get('is_error',False)
            if event.get('result'):response=[event['result']]
        if event.get('type')=='item.completed' and event.get('item',{}).get('type')=='agent_message':
            response.append(event['item'].get('text',''))
        if event.get('type')=='turn.completed':usage.append(event.get('usage',{}))
        if event.get('type') in ['item.started','item.completed'] and event.get('item',{}).get('type') in ['command_execution','mcp_tool_call','web_search']:
            meta['unexpected_tool_use']=True
    meta['response_models']=sorted(models);meta['codex_usage']=usage
    text='\n'.join(response);prefix.with_suffix('.response.txt').write_text(text)
    try:
        parsed=parse_json(text);dump(prefix.with_suffix('.parsed.json'),parsed)
    except Exception as ex:meta['parse_error']=str(ex)
    # ocx request records identify actual servedModel; persist only this
    # ephemeral Codex conversation to avoid mixing in S11/other live sessions.
    tids=[e['thread_id'] for e in events if e.get('type')=='thread.started']
    meta['thread_ids']=tids
    if tids:
        try:
            logs=subprocess.run(['ocx','logs','--limit','300','--json'],capture_output=True,text=True,timeout=25)
            records=json.loads(logs.stdout).get('logs',[])
            norm=lambda x:str(x).replace('-','')
            selected=[x for x in records if norm(x.get('conversationId')) in {norm(tid) for tid in tids}]
            dump(prefix.with_suffix('.proxy.json'),selected)
            meta['response_models']=sorted(set(x.get('servedModel') for x in selected if x.get('servedModel')))
            meta['proxy_requests']=len(selected)
        except Exception as ex:meta['proxy_error']=str(ex)
    meta['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();dump(prefix.with_suffix('.meta.json'),meta)
    print(name,json.dumps({k:meta.get(k) for k in ['returncode','elapsed_seconds','response_models','parse_error','unexpected_tool_use','proxy_requests']},ensure_ascii=False),flush=True)
    return meta

def label():
    return run('labels-independent',claude_cmd('opus'),(ROOT/'label-prompt.txt').read_text(),timeout=360)

def reconcile():
    fixture=json.loads((ROOT/'fixture.json').read_text());author=json.loads((ROOT/'labels-author.json').read_text())
    second=json.loads((RUNS/'labels-independent.parsed.json').read_text())['labels']
    keys={(a['case'],a['item']) for a in author};seen={}
    for x in second:
        key=(x['case'],x['item']);assert key in keys and key not in seen and x['label'] in ['R1','R2','R3','R4','N'],x
        seen[key]=x['label']
    final=[];disagreements=[]
    for a in author:
        other=seen.get((a['case'],a['item']),'N');row={**a,'independent':other,'author':a['label']}
        if a['label']!=other:
            row['label']='AMBIGUOUS';disagreements.append(row.copy())
        final.append(row)
    dump(ROOT/'labels-final.json',final);dump(ROOT/'label-disagreements.json',disagreements)
    # All prompts materialized before evaluation. Only labels-independent has
    # run at this point, never a filter for F1/F2/F3.
    prompts=ROOT/'prompts';prompts.mkdir(exist_ok=True)
    for b in fixture['batches']:
        for s in fixture['sessions']:
            p=(ROOT/'filter-prompt.txt').read_text()+'\n세션:\n'+json.dumps(s,ensure_ascii=False)+'\n변경 diff:\n'
            for x in b['entries']:
                p+=f'변경 ID: {x["id"]}\n## {x["title"]}\n- {x["before"]}\n+ {x["after"]}\n\n'
            (prompts/f'{b["id"]}-{s["id"]}.txt').write_text(p)
    files=[ROOT/x for x in ['BOARD.md','fixture.json','labels-author.json','labels-final.json','label-disagreements.json','policy.json','filter-prompt.txt','label-prompt.txt','freeze-inputs.json','run_experiment.py']]+sorted(prompts.glob('*.txt'))
    dump(ROOT/'freeze-evaluation.json',dict(frozen_at=dt.datetime.now(dt.timezone.utc).isoformat(),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},label_disagreements=len(disagreements),label_cells=len(final),stage='all labels/prompts/policy fixed before first F1/F2/F3 run'))
    print('reconciled',len(final),'ambiguous',len(disagreements))

def validate(meta,condition):
    models=meta['response_models']
    matches=bool(models) and all(('haiku' in x.lower()) if condition=='F1' else (x in ['gpt-6-luna','openai/gpt-6-luna'] if condition=='F2' else x=='gpt-6.1-sol') for x in models)
    if not matches:
        dump(ROOT/'STOP.json',dict(condition=condition,reason='actual model mismatch or no response-model evidence; no substitution permitted',meta=meta))
        raise SystemExit('STOP: response model mismatch / unavailable')
    if meta.get('returncode')!=0 or meta.get('is_error') or meta.get('parse_error') or meta.get('unexpected_tool_use'):
        dump(ROOT/'STOP.json',dict(condition=condition,reason='failed or invalid run; preserved, remaining planned calls not run',meta=meta))
        raise SystemExit('STOP: failed or invalid run')

def evaluate():
    freeze=json.loads((ROOT/'freeze-evaluation.json').read_text())
    for p,h in freeze['sha256'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
    fixture=json.loads((ROOT/'fixture.json').read_text());policy=json.loads((ROOT/'policy.json').read_text())
    cases=[f'{b["id"]}-{s["id"]}' for b in fixture['batches'] for s in fixture['sessions']]
    # Verify first real calls in sequence, then run the rest sequentially so
    # the same shared proxy is never flooded by this experiment.
    for cond in ['F1','F2']:
        case=cases[0];name=f'{cond}-r0-{case}'
        if (RUNS/f'{name}.meta.json').exists():
            meta=json.loads((RUNS/f'{name}.meta.json').read_text())
        else:
            cmd=claude_cmd('haiku') if cond=='F1' else codex_cmd('openai/gpt-6-luna')
            meta=run(name,cmd,(ROOT/'prompts'/f'{case}.txt').read_text())
        validate(meta,cond)
    for cond in ['F1','F2','F3']:
        selected=cases if cond!='F3' else [x for x in cases if x.split('-')[0] in policy['F3_batches']]
        for repetition,subset in [(0,selected)]+([(r,policy['repeats']) for r in range(1,4)] if cond in ['F1','F2'] else []):
            for case in subset:
                name=f'{cond}-r{repetition}-{case}'
                if (RUNS/f'{name}.meta.json').exists():
                    meta=json.loads((RUNS/f'{name}.meta.json').read_text())
                else:
                    prompt=(ROOT/'prompts'/f'{case}.txt').read_text()
                    cmd=claude_cmd('haiku') if cond=='F1' else codex_cmd('openai/gpt-6-luna' if cond=='F2' else 'gpt-6.1-sol')
                    meta=run(name,cmd,prompt)
                validate(meta,cond)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['label','reconcile','evaluate']);a=p.parse_args()
    globals()[a.stage]()
