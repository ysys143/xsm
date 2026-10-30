"""Audit saved evidence, planned counts, provenance, and pre-inference freeze."""
import collections
import datetime as dt
import hashlib
import json
import aggregate as a

def verify():
    m=a.aggregate();assert m['complete'] and m['observed_model_calls']==152 and not m['missing']
    freeze=a.read(a.ROOT/'freeze-evaluation.json');inputs=a.read(a.ROOT/'freeze-inputs.json')
    for f,h in inputs['sha256'].items():assert hashlib.sha256((a.ROOT/f).read_bytes()).hexdigest()==h,f
    for f,h in freeze['sha256'].items():assert hashlib.sha256((a.ROOT/f).read_bytes()).hexdigest()==h,f
    cells=a.read(a.ROOT/'labels-final.json');assert len(cells)==320
    assert len({(x['case'],x['item']) for x in cells})==320
    assert all(x['author']==x['independent']==x['label'] for x in cells)
    fixture=a.read(a.ROOT/'fixture.json');assert len(fixture['sessions'])==4 and len(fixture['batches'])==10
    assert all(len(b['entries'])==8 for b in fixture['batches'])
    assert (a.ROOT/'BOARD.md').read_text().count('\n## ')==32
    firstfreeze=dt.datetime.fromisoformat(inputs['frozen_at']);finalfreeze=dt.datetime.fromisoformat(freeze['frozen_at'])
    independent=a.read(a.RUNS/'labels-independent.meta.json')
    assert firstfreeze<dt.datetime.fromisoformat(independent['started_at'])<finalfreeze
    totals=collections.Counter();models=collections.defaultdict(set);proxy=0;usage_mismatches=[]
    for row in m['calls']:
        name=row['name'];meta=a.read(a.RUNS/f'{name}.verified.json')
        assert dt.datetime.fromisoformat(meta['started_at'])>finalfreeze
        assert meta['returncode']==0 and not meta.get('parse_error') and not meta.get('is_error') and not meta.get('unexpected_tool_use')
        prompt=(a.RUNS/f'{name}.prompt.txt').read_bytes()
        assert hashlib.sha256(prompt).hexdigest()==meta['prompt_sha256']
        assert prompt==(a.ROOT/'prompts'/f'{row["case"]}.txt').read_bytes()
        assert len(meta['response_models'])==1
        model=meta['response_models'][0];c=row['condition'];models[c].add(model);totals[c]+=1
        assert ('haiku' in model) if c=='F1' else model==('gpt-6-luna' if c=='F2' else 'gpt-6.1-sol')
        if c!='F1':
            records=a.read(a.RUNS/f'{name}.proxy-verified.json');assert records
            hashes={hashlib.sha256(t.encode()).hexdigest()[:32] for t in meta['thread_ids']}
            for r in records:
                assert r['conversationId'] in hashes and r['servedModel']==model and r['status']==200
                assert r['requestedModel']==('openai/gpt-6-luna' if c=='F2' else 'gpt-6.1-sol')
                assert all(x.get('model')==model and x.get('status')==200 for x in r.get('attempts',[]))
            proxy+=len(records)
            pi=sum(r.get('usage',{}).get('inputTokens',0) for r in records);po=sum(r.get('usage',{}).get('outputTokens',0) for r in records)
            if pi!=row['input'] or po!=row['output']:usage_mismatches.append(dict(name=name,cli_input=row['input'],proxy_input=pi,cli_output=row['output'],proxy_output=po))
    assert dict(totals)=={'F1':70,'F2':70,'F3':12},totals
    assert len(a.read(a.ROOT/'F0-output.json')['predictions'])==40
    result=dict(verified=True,model_calls=dict(totals),F0_cases=40,label_cells=320,label_disagreements=0,proxy_records=proxy,actual_models={k:sorted(v) for k,v in models.items()},freeze_verified=True,all_prompts_match_frozen=True,cli_proxy_usage_mismatches=usage_mismatches)
    (a.ROOT/'artifact-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':verify()
