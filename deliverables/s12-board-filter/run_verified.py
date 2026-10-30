"""Correct log correlation without modifying the frozen first runner or labels.

ocx 2.67.0 stores sha256(thread-id)[:32], not a dash-stripped UUID.
The initial unverified metadata and STOP.json are retained verbatim.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import run_experiment as base

ROOT=base.ROOT
RUNS=base.RUNS

def verified(name,condition,prompt):
    path=RUNS/f'{name}.meta.json'
    if path.exists():meta=json.loads(path.read_text())
    else:
        cmd=base.claude_cmd('haiku') if condition=='F1' else base.codex_cmd('openai/gpt-6-luna' if condition=='F2' else 'gpt-6.1-sol')
        meta=base.run(name,cmd,prompt)
    if meta.get('thread_ids'):
        wanted={hashlib.sha256(t.encode()).hexdigest()[:32] for t in meta['thread_ids']}
        raw=subprocess.run(['ocx','logs','--limit','300','--json'],capture_output=True,text=True,timeout=25)
        rows=[r for r in json.loads(raw.stdout).get('logs',[]) if r.get('conversationId') in wanted]
        base.dump(RUNS/f'{name}.proxy-verified.json',rows)
        meta={**meta,'response_models':sorted(set(r['servedModel'] for r in rows if r.get('servedModel'))),'proxy_requests':len(rows),'evidence_correction':'sha256(thread-id)[:32] correlation; original .meta/.proxy retained'}
    base.dump(RUNS/f'{name}.verified.json',meta)
    base.validate(meta,condition)
    print('VERIFIED',name,meta['response_models'],flush=True)
    return meta

def arm(condition):
    fixture=json.loads((ROOT/'fixture.json').read_text());policy=json.loads((ROOT/'policy.json').read_text())
    cases=[f'{b["id"]}-{s["id"]}' for b in fixture['batches'] for s in fixture['sessions']]
    selected=cases if condition!='F3' else [x for x in cases if x.split('-')[0] in policy['F3_batches']]
    rounds=[(0,selected)]+([(r,policy['repeats']) for r in range(1,4)] if condition in ['F1','F2'] else [])
    for repetition,subset in rounds:
        for case in subset:
            verified(f'{condition}-r{repetition}-{case}',condition,(ROOT/'prompts'/f'{case}.txt').read_text())

if __name__=='__main__':
    freeze=json.loads((ROOT/'freeze-evaluation.json').read_text())
    for name,digest in freeze['sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    # Resolve the one instrumentation stop from preserved, already completed
    # calls. No repeated inference and no changes to the fixture or labels.
    for condition in ['F1','F2']:
        verified(f'{condition}-r0-B01-Oriole',condition,(ROOT/'prompts/B01-Oriole.txt').read_text())
    base.dump(ROOT/'instrumentation-resolution.json',dict(reason='original collector matched raw UUID to a SHA256 digest',actual_F2='gpt-6-luna',action='offline correlation corrected; original STOP and outputs preserved; no model substitution or rerun',concurrency='one sequential F1 arm and one sequential F2 arm concurrently; F3 afterwards',fixed_inputs_unchanged=True))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(arm,c) for c in ['F1','F2']]
        for f in futures:f.result()
    arm('F3')
