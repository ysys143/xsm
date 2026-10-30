"""Check that deliberately injected failures change the measured outcomes (S12 checks plus hard-negative counting)."""
import copy
import aggregate as a

final = a.read(a.ROOT / 'labels-final.json')
gold = {(x['case'], x['item']): x['label'] for x in final}
hard = {(x['case'], x['item']) for x in final if x.get('hard_negative')}
lexical = a.lexical_negatives()
fixture = a.read(a.ROOT / 'fixture.json')
entries = {e['id']: e for b in fixture['batches'] for e in b['entries']}
# A case with an R2 and a marked hard negative.
case = next(c for c in sorted({k[0] for k in gold})
            if {'R2'} <= {l for (cc, _), l in gold.items() if cc == c} and any(k[0] == c for k in hard))
relevant = [i for (c, i), l in sorted(gold.items()) if c == case and l in a.REL]
hn = next(i for (c, i) in sorted(hard) if c == case)
r2 = next(i for (c, i), l in gold.items() if c == case and l == 'R2')


def item(i):
    return dict(id=i, title=entries[i]['title'], quote=entries[i]['after'][:40], reason='verification')


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
(a.ROOT / 'metrics-verification.txt').write_text('\n'.join(checks) + '\n')
print('\n'.join(checks))
