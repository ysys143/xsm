"""Descriptive output anomalies; never changes preregistered scoring."""
import collections
import json
import aggregate as a

def diagnose():
    entries={e['id']:e for b in a.read(a.ROOT/'fixture.json')['batches'] for e in b['entries']}
    out=[];counts=collections.Counter()
    for f in sorted(a.RUNS.glob('F*.verified.json')):
        for item in a.read(f.with_name(f.name.replace('.verified.json','.parsed.json')))['items']:
            entry=entries.get(item.get('id'));title=item.get('title','');quote=item.get('quote','');issues=[]
            if not entry:issues.append('unknown ID')
            else:
                if title!=entry['title']:
                    counts[f.name[:2]+' title exact mismatch']+=1
                    if title.lstrip('# ').strip()==entry['title']:counts[f.name[:2]+' title hash-prefix-only']+=1
                    else:issues.append('title content mismatch')
                if not quote.strip() or quote not in entry['after']:issues.append('quote mismatch')
            if issues:out.append(dict(run=f.name,item=item,issues=issues,expected=entry))
    obj=dict(title_counts=dict(counts),items=out)
    (a.ROOT/'anomalies.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    return obj

if __name__=='__main__':print(json.dumps(diagnose(),ensure_ascii=False,indent=2))
