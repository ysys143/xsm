"""Check that deliberately injected failures change the measured outcomes and the mechanical verdict (S12b checks
plus the whole-body/excerpt split and the user's criteria). No model call."""
import copy
import aggregate as a

final = a.read(a.ROOT / 'labels-final.json')
gold = {(x['case'], x['item']): x['label'] for x in final}
hard = {(x['case'], x['item']) for x in final if x.get('hard_negative')}
lexical = a.lexical_negatives()
fixture = a.read(a.ROOT / 'fixture.json')
entries = {e['id']: e for b in fixture['batches'] for e in b['entries']}
criteria = a.read(a.ROOT / 'policy.json')['criteria']
case = next(c for c in sorted({k[0] for k in gold})
            if {'R2'} <= {l for (cc, _), l in gold.items() if cc == c} and any(k[0] == c for k in hard))
relevant = [i for (c, i), l in sorted(gold.items()) if c == case and l in a.REL]
hn = next(i for (c, i) in sorted(hard) if c == case)
r2 = next(i for (c, i), l in gold.items() if c == case and l == 'R2')


def item(i, whole=False):
    return dict(id=i, title=entries[i]['title'], quote=entries[i]['after'] if whole else entries[i]['after'][:40], reason='verification')


def measure(items, g=gold):
    return a.measure([case], {case: items}, g, entries, hard, lexical)


good = [item(i) for i in relevant]
base = measure(good)
assert base['recall_overall']['value'] == 1 and base['quote_fidelity']['value'] == 1 and base['precision']['value'] == 1
checks = [f'case {case}: clean predictions, all metrics 1.0']
assert measure([x for x in good if x['id'] != r2])['recall']['R2']['value'] < 1
checks.append('removed R2 item: R2 recall drops below 1.0 (detected)')
bad = copy.deepcopy(good)
bad[0]['quote'] = '원문에 없는 문장'
assert measure(bad)['quote_fidelity']['value'] < 1
checks.append('mutated quote: fidelity drops below 1.0 (detected)')
bad = copy.deepcopy(good)
bad[0]['quote'] = entries[hn]['after'][:30]
assert measure(bad)['quote_fidelity']['value'] < 1
checks.append('quote taken from another item: counted unfaithful (detected)')
w = measure([item(i, whole=True) for i in relevant])
assert w['quote_fidelity']['value'] == 1 and w['quote_whole_body']['value'] == 1 and w['quote_excerpt']['value'] == 0
assert base['quote_whole_body']['value'] == 0 and base['quote_excerpt']['value'] == 1
checks.append('whole-body quotes: faithful and counted as whole body; 40-char quotes counted as excerpts')
over = measure(good + [item(hn)])
assert over['precision']['value'] < 1 and over['hard_negative_pass_rate']['numerator'] == 1 and over['unrelated_pass_rate']['numerator'] == 1
checks.append('added hard negative: precision < 1, N pass 1, hard-negative pass 1 (detected)')
amb = gold.copy()
amb[(case, hn)] = 'AMBIGUOUS'
v = measure(good + [item(hn)], amb)
assert v['precision']['value'] == 1 and v['ambiguous_selected'] == 1
checks.append('ambiguous item selected: excluded from precision, counted separately')
v = measure(good + [dict(id='absent', title='x', quote='x', reason='verification')])
assert v['invalid_ids'] == 1 and v['precision']['value'] < 1
checks.append('unknown item ID: invalid ID 1, precision < 1 (detected)')
assert measure(good + [good[0]])['duplicates'] == 1
checks.append('duplicated prediction: duplicate count 1 (detected)')
# Mechanical verdict: start from a passing synthetic summary, break one criterion at a time.
ok = dict(baseline=dict(recall={l: dict(value=1.0) for l in a.REL}, precision=dict(value=0.9), quote_fidelity=dict(value=1.0)),
          repeat_spread={l: 0.0 for l in ['overall'] + a.REL})
assert a.verdict(ok, criteria)['met'] is True
for path, val in [(('baseline', 'recall', 'R3', 'value'), 0.949), (('baseline', 'precision', 'value'), 0.699),
                  (('baseline', 'quote_fidelity', 'value'), 0.949), (('repeat_spread', 'R2'), 0.101), (('repeat_spread', 'R1'), None)]:
    s = copy.deepcopy(ok)
    d = s
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = val
    assert a.verdict(s, criteria)['met'] is False, path
checks.append('verdict: all-pass summary is met; R3 0.949, precision 0.699, quote 0.949, R2 spread 0.101, R1 spread NA each flip it to not met')
s = copy.deepcopy(ok)
s['baseline']['recall']['R4']['value'] = 0.95
s['repeat_spread']['overall'] = 0.10
assert a.verdict(s, criteria)['met'] is True
checks.append('verdict: values exactly at the thresholds (R4 0.95, spread 0.10) count as met')
(a.ROOT / 'metrics-verification.txt').write_text('\n'.join(checks) + '\n')
print('\n'.join(checks))
