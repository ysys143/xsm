"""Check that deliberately injected failures change the measured outcomes."""
import copy
import json
import aggregate as a

case='B01-Oriole'
gold={(x['case'],x['item']):x['label'] for x in a.read(a.ROOT/'labels-final.json')}
fixture=a.read(a.ROOT/'fixture.json')
entries={e['id']:e for b in fixture['batches'] for e in b['entries']}
relevant=[i for (c,i),label in gold.items() if c==case and label in ['R1','R2','R3','R4']]
negative=next(i for (c,i),label in gold.items() if c==case and label=='N')
def item(i):return dict(id=i,title=entries[i]['title'],quote=entries[i]['after'],reason='verification')
def measure(items,g=gold):return a.measure([case],{case:items},g,entries)
good=[item(i) for i in relevant]
baseline=measure(good)
assert baseline['recall_overall']['value']==1 and baseline['quote_fidelity']['value']==1 and baseline['precision']['value']==1
checks=['clean predictions: all metrics 1.0']
omitted=measure(good[:1]);assert omitted['recall']['R2']['value']==0
checks.append('removed R2 item: R2 recall 1.0 -> 0.0 (detected)')
bad=copy.deepcopy(good);bad[0]['quote']='원문에 없는 문장'
assert measure(bad)['quote_fidelity']['value']==.5
checks.append('mutated quote: fidelity 1.0 -> 0.5 (detected)')
over=measure(good+[item(negative)])
assert over['precision']['value']==2/3 and over['unrelated_pass_rate']['value']==1/6
checks.append('added unrelated item: precision 1.0 -> 2/3; N pass rate 0 -> 1/6 (detected)')
amb=gold.copy();amb[(case,negative)]='AMBIGUOUS';v=measure(good+[item(negative)],amb)
assert v['precision']['value']==1 and v['ambiguous_selected']==1
checks.append('ambiguous item: excluded from precision; separate count 1')
bad=measure(good+[dict(id='absent',title='bad',quote='bad',reason='verification')])
assert bad['invalid_ids']==1 and bad['quote_fidelity']['value']==2/3 and bad['precision']['value']==2/3
checks.append('unknown item ID: invalid ID 1; quote fidelity and precision 2/3 (detected)')
assert measure(good+[good[0]])['duplicates']==1
checks.append('duplicated prediction: duplicate count 1 (detected)')
(a.ROOT/'metrics-verification.txt').write_text('\n'.join(checks)+'\n')
print('\n'.join(checks))
