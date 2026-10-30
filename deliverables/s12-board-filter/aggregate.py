"""Reproducible metrics for S12, with denominators and missing cases."""
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

ROOT=Path(__file__).resolve().parent
RUNS=ROOT/'runs'
LABELS=['R1','R2','R3','R4','N','AMBIGUOUS']

def read(p):return json.loads(p.read_text())
def ratio(n,d):return n/d if d else None
def numeric(values):
    if not values:return dict(n=0,mean=None,median=None,p95=None,min=None,max=None)
    v=sorted(values)
    return dict(n=len(v),mean=statistics.mean(v),median=statistics.median(v),p95=v[math.ceil(.95*len(v))-1],min=min(v),max=max(v))

def measure(cases,predictions,gold,entries):
    denom=collections.Counter();hits=collections.Counter();tp=fp=amb=invalid=quotes=faithful=title_bad=duplicate=0
    selected=[];errors=[]
    for case in cases:
        gs={item:label for (c,item),label in gold.items() if c==case}
        for label in gs.values():denom[label]+=1
        items=predictions[case]
        predicted=set()
        for item in items:
            quotes+=1
            iid=item.get('id');entry=entries.get(iid)
            q=item.get('quote')
            if entry and isinstance(q,str) and q.strip() and q in entry['after']:faithful+=1
            if not entry or item.get('title')!=entry['title']:title_bad+=1
            if iid in predicted:duplicate+=1
            predicted.add(iid)
        for iid in predicted:
            label=gs.get(iid)
            if label=='AMBIGUOUS':amb+=1
            elif label in ['R1','R2','R3','R4']:tp+=1;hits[label]+=1
            else:
                fp+=1
                if label is None:invalid+=1
                else:hits['N']+=1
                errors.append(dict(case=case,item=iid,type='false_positive',gold=label,text=entries.get(iid,{}).get('after')))
        for iid,label in gs.items():
            if label in ['R1','R2','R3','R4'] and iid not in predicted:
                errors.append(dict(case=case,item=iid,type='false_negative',gold=label,text=entries.get(iid,{}).get('after')))
        selected.append(dict(case=case,selected=sorted(str(x) for x in predicted)))
    return dict(cases=len(cases),label_denominators=dict(denom),label_hits=dict(hits),recall={l:dict(numerator=hits[l],denominator=denom[l],value=ratio(hits[l],denom[l])) for l in LABELS[:4]},recall_overall=dict(numerator=tp,denominator=sum(denom[l] for l in LABELS[:4]),value=ratio(tp,sum(denom[l] for l in LABELS[:4]))),precision=dict(numerator=tp,denominator=tp+fp,value=ratio(tp,tp+fp)),unrelated_pass_rate=dict(numerator=hits['N'],denominator=denom['N'],value=ratio(hits['N'],denom['N'])),quote_fidelity=dict(numerator=faithful,denominator=quotes,value=ratio(faithful,quotes)),ambiguous_selected=amb,invalid_ids=invalid,title_mismatches=title_bad,duplicates=duplicate,selected=selected,errors=errors)

def usage(meta):
    if 'claude_usage' in meta:
        u=meta['claude_usage'];fresh=u.get('input_tokens',0);read_cache=u.get('cache_read_input_tokens',0);write_cache=u.get('cache_creation_input_tokens',0)
        return dict(input=fresh+read_cache+write_cache,output=u.get('output_tokens',0),cached_input=read_cache,fresh_input=fresh+write_cache,source='Claude result.usage (all cache-inclusive input)')
    us=meta.get('codex_usage',[])
    if not us:return {}
    return dict(input=sum(u.get('input_tokens',0) for u in us),output=sum(u.get('output_tokens',0) for u in us),cached_input=sum(u.get('cached_input_tokens',0) for u in us),fresh_input=sum(u.get('input_tokens',0)-u.get('cached_input_tokens',0) for u in us),source='Codex turn.completed.usage (cache-inclusive input)')

def aggregate():
    fixture=read(ROOT/'fixture.json');policy=read(ROOT/'policy.json');final=read(ROOT/'labels-final.json')
    gold={(x['case'],x['item']):x['label'] for x in final}
    entries={e['id']:e for b in fixture['batches'] for e in b['entries']}
    cases=[f'{b["id"]}-{s["id"]}' for b in fixture['batches'] for s in fixture['sessions']]
    sessions={s['id']:s for s in fixture['sessions']};batches={b['id']:b for b in fixture['batches']}
    pred={};times=[]
    for case in cases:
        b,s=case.split('-');session=sessions[s];keys=[s]+session['owned']+session['files'];start=time.perf_counter()
        pred[case]=[dict(id=e['id'],title=e['title'],quote=e['after'],reason='literal match') for e in batches[b]['entries'] if any(k in e['title']+'\n'+e['after'] for k in keys)]
        times.append(time.perf_counter()-start)
    f0raw=ROOT/'F0-output.json'
    if f0raw.exists():
        saved=read(f0raw);pred=saved['predictions'];times=saved['elapsed_seconds']
    else:
        f0raw.write_text(json.dumps(dict(predictions=pred,elapsed_seconds=times),ensure_ascii=False,indent=2)+'\n')
    summary=dict(label_counts=dict(collections.Counter(gold.values())),label_disagreements=len(read(ROOT/'label-disagreements.json')),conditions={'F0':dict(baseline=measure(cases,pred,gold,entries),expected_baseline=40,observed_baseline=40,expected_calls=0,observed_calls=0,time_seconds=numeric(times),tokens_input=numeric([0]*40),tokens_output=numeric([0]*40),actual_models=[])},calls=[],missing=[])
    for condition in ['F1','F2','F3']:
        selected=cases if condition!='F3' else [c for c in cases if c.split('-')[0] in policy['F3_batches']]
        expected=[(0,c) for c in selected]+([(r,c) for r in range(1,4) for c in policy['repeats']] if condition in ['F1','F2'] else [])
        predictions={};metas={};observed=[]
        for repetition,case in expected:
            name=f'{condition}-r{repetition}-{case}';p=RUNS/f'{name}.verified.json';parsed=RUNS/f'{name}.parsed.json'
            if not p.exists() or not parsed.exists():summary['missing'].append(name);continue
            meta=read(p);obj=read(parsed)
            if meta.get('returncode')!=0 or meta.get('parse_error') or meta.get('is_error') or meta.get('unexpected_tool_use') or not isinstance(obj.get('items'),list):summary['missing'].append(name);continue
            predictions[(repetition,case)]=obj['items'];metas[(repetition,case)]=meta
            row=dict(name=name,condition=condition,repetition=repetition,case=case,models=meta['response_models'],elapsed_seconds=meta['elapsed_seconds'],**usage(meta));observed.append(row);summary['calls'].append(row)
        base_cases=[c for c in selected if (0,c) in predictions]
        metrics=measure(base_cases,{c:predictions[(0,c)] for c in base_cases},gold,entries)
        repeat=[]
        if condition in ['F1','F2']:
            for r in range(4):
                subset=[c for c in policy['repeats'] if (r,c) in predictions]
                repeat.append(dict(repetition=r,metrics=measure(subset,{c:predictions[(r,c)] for c in subset},gold,entries)))
        spreads={}
        if len(repeat)==4 and all(r['metrics']['cases']==10 for r in repeat):
            for lab in LABELS[:4]+['overall']:
                vals=[r['metrics']['recall_overall' if lab=='overall' else 'recall']['value'] if lab=='overall' else r['metrics']['recall'][lab]['value'] for r in repeat]
                spreads[lab]=max(vals)-min(vals) if all(v is not None for v in vals) else None
        summary['conditions'][condition]=dict(baseline=metrics,expected_baseline=len(selected),observed_baseline=len(base_cases),expected_calls=len(expected),observed_calls=len(observed),repeat=repeat,repeat_spread=spreads,time_seconds=numeric([r['elapsed_seconds'] for r in observed]),tokens_input=numeric([r['input'] for r in observed if 'input' in r]),tokens_output=numeric([r['output'] for r in observed if 'output' in r]),tokens_cached_input=numeric([r['cached_input'] for r in observed if 'cached_input' in r]),actual_models=sorted(set(m for r in observed for m in r['models'])))
    freeze=read(ROOT/'freeze-evaluation.json');summary['freeze_verified']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in freeze['sha256'].items())
    summary['planned_model_calls']=152;summary['observed_model_calls']=len(summary['calls']);summary['complete']=not summary['missing'] and summary['freeze_verified']
    (ROOT/'metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['calls','conditions','missing']},ensure_ascii=False));print('missing:',len(summary['missing']))
    for c,v in summary['conditions'].items():print(c,v['observed_calls'],{l:r['value'] for l,r in v['baseline']['recall'].items()},v['baseline']['precision'],v['baseline']['quote_fidelity'])
    return summary

if __name__=='__main__':aggregate()
