"""Reproducible metrics for S12c (S12b's aggregate.py plus quote whole/excerpt split, long/short split, F4 cost
comparison and the user's criteria applied mechanically). Reads saved runs only; makes no model call."""
import collections
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

import run_experiment as rx

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / 'runs'
REL = ['R1', 'R2', 'R3', 'R4']
FILTERS = ['F1', 'F2', 'F3']
F4 = ['F4a', 'F4b', 'F4c']


def read(p):
    return json.loads(Path(p).read_text())


def ratio(n, d):
    return n / d if d else None


def numeric(values):
    if not values:
        return dict(n=0, mean=None, median=None, p95=None, min=None, max=None)
    v = sorted(values)
    return dict(n=len(v), mean=statistics.mean(v), median=statistics.median(v), p95=v[math.ceil(.95 * len(v)) - 1], min=min(v), max=max(v))


def lexical_negatives():
    meta = read(ROOT / 'src/sessions.json')
    fixture = read(ROOT / 'fixture.json')
    out = set()
    for b in fixture['batches']:
        for e in b['entries']:
            low = (e['title'] + '\n' + e['after']).lower()
            for s in fixture['sessions']:
                if any(t.lower() in low for t in meta['distinctive_terms'][s['id']]):
                    out.add((f'{b["id"]}-{s["id"]}', e['id']))
    return out


def is_long(entry):
    return len(entry['after'].split()) >= 150


def measure(cases, predictions, gold, entries, hard, lexical, quotes_expected=True):
    denom, hits = collections.Counter(), collections.Counter()
    len_denom, len_hits = collections.Counter(), collections.Counter()
    tp = fp = amb = invalid = quotes = faithful = whole = excerpt = title_bad = duplicate = 0
    quotes_long = faithful_long = whole_long = 0
    hn_den = hn_fp = lx_den = lx_fp = 0
    qlen, selected, errors = [], [], []
    for case in cases:
        gs = {item: label for (c, item), label in gold.items() if c == case}
        for item, label in gs.items():
            denom[label] += 1
            if label in REL:
                len_denom['long' if is_long(entries[item]) else 'short'] += 1
            if label == 'N' and (case, item) in hard:
                hn_den += 1
            if label == 'N' and (case, item) in lexical:
                lx_den += 1
        predicted = set()
        for item in predictions[case]:
            iid = item.get('id')
            entry = entries.get(iid)
            if quotes_expected:
                quotes += 1
                q = item.get('quote')
                lg = bool(entry and is_long(entry))
                quotes_long += lg
                if entry and isinstance(q, str) and q.strip() and q in entry['after']:
                    faithful += 1
                    faithful_long += lg
                    qlen.append(len(q) / len(entry['after']))
                    if q.strip() == entry['after'].strip():
                        whole += 1
                        whole_long += lg
                    else:
                        excerpt += 1
                if not entry or item.get('title') != entry['title']:
                    title_bad += 1
            if iid in predicted:
                duplicate += 1
            predicted.add(iid)
        for iid in predicted:
            label = gs.get(iid)
            if label == 'AMBIGUOUS':
                amb += 1
            elif label in REL:
                tp += 1
                hits[label] += 1
                len_hits['long' if is_long(entries[iid]) else 'short'] += 1
            else:
                fp += 1
                if label is None:
                    invalid += 1
                else:
                    hits['N'] += 1
                    hn_fp += (case, iid) in hard
                    lx_fp += (case, iid) in lexical
                errors.append(dict(case=case, item=iid, type='false_positive', gold=label, hard_negative=(case, iid) in hard,
                                   lexical_overlap=(case, iid) in lexical))
        for iid, label in gs.items():
            if label in REL and iid not in predicted:
                errors.append(dict(case=case, item=iid, type='false_negative', gold=label, long=is_long(entries[iid])))
        selected.append(dict(case=case, selected=sorted(str(x) for x in predicted)))
    rel_den = sum(denom[l] for l in REL)
    f = lambda n, d: dict(numerator=n, denominator=d, value=ratio(n, d))
    return dict(cases=len(cases), label_denominators=dict(denom), label_hits=dict(hits),
                recall={l: f(hits[l], denom[l]) for l in REL},
                recall_overall=f(tp, rel_den),
                recall_by_length={k: f(len_hits[k], len_denom[k]) for k in ['long', 'short']},
                precision=f(tp, tp + fp),
                unrelated_pass_rate=f(hits['N'], denom['N']),
                hard_negative_pass_rate=f(hn_fp, hn_den),
                lexical_negative_pass_rate=f(lx_fp, lx_den),
                quote_fidelity=f(faithful, quotes) if quotes_expected else f(0, 0),
                quote_whole_body=f(whole, faithful) if quotes_expected else f(0, 0),
                quote_excerpt=f(excerpt, faithful) if quotes_expected else f(0, 0),
                quote_long_items=dict(returned=quotes_long, faithful=faithful_long, whole_body=whole_long),
                quote_share_of_item=numeric(qlen), ambiguous_selected=amb, ambiguous_cells=denom['AMBIGUOUS'],
                invalid_ids=invalid, title_mismatches=title_bad, duplicates=duplicate, selected=selected, errors=errors)


def usage(meta):
    if 'claude_usage' in meta:
        u = meta['claude_usage']
        fresh = u.get('input_tokens', 0)
        rc = u.get('cache_read_input_tokens', 0)
        wc = u.get('cache_creation_input_tokens', 0)
        return dict(input=fresh + rc + wc, output=u.get('output_tokens', 0), cached_input=rc, source='Claude result.usage (cache-inclusive input)')
    us = meta.get('codex_usage', [])
    if not us:
        return {}
    return dict(input=sum(u.get('input_tokens', 0) for u in us), output=sum(u.get('output_tokens', 0) for u in us),
                cached_input=sum(u.get('cached_input_tokens', 0) for u in us),
                reasoning_output=sum(u.get('reasoning_output_tokens', 0) for u in us), source='Codex turn.completed.usage (cache-inclusive input)')


def load_calls(summary):
    """All planned calls; returns {(cond, rep, case): (meta, items)} for valid ones and records missing/invalid."""
    out = {}
    for cond, lst in rx.plan().items():
        for c, rep, case in lst:
            name = f'{c}-r{rep}-{case}'
            p, parsed = RUNS / f'{name}.meta.json', RUNS / f'{name}.parsed.json'
            if not p.exists():
                summary['missing'].append(name)
                continue
            meta = read(p)
            obj = read(parsed) if parsed.exists() else {}
            if meta.get('returncode') != 0 or meta.get('parse_error') or meta.get('is_error') or meta.get('unexpected_tool_use') or not isinstance(obj.get('items'), list):
                summary['invalid'].append(name)
                continue
            out[(c, rep, case)] = (meta, obj['items'])
            row = dict(name=name, condition=c, repetition=rep, case=case, models=meta.get('response_models', []),
                       elapsed_seconds=meta['elapsed_seconds'], **usage(meta))
            summary['calls'].append(row)
    return out


def check(value, op, threshold):
    if value is None:
        return False
    return value >= threshold - 1e-12 if op == '>=' else value <= threshold + 1e-12


def verdict(cond_summary, criteria):
    b = cond_summary['baseline']
    sp = cond_summary.get('repeat_spread') or {}
    rows = []
    for l in ['R2', 'R3', 'R4']:
        v = b['recall'][l]['value']
        rows.append(dict(criterion=f'{l} recall', value=v, op='>=', threshold=criteria[f'{l}_recall_min'], ok=check(v, '>=', criteria[f'{l}_recall_min'])))
    v = b['precision']['value']
    rows.append(dict(criterion='precision', value=v, op='>=', threshold=criteria['precision_min'], ok=check(v, '>=', criteria['precision_min'])))
    for l in ['overall'] + REL:
        v = sp.get(l)
        rows.append(dict(criterion=f'repeat spread {l}', value=v, op='<=', threshold=criteria['repeat_spread_max'],
                         ok=check(v, '<=', criteria['repeat_spread_max'])))
    v = b['quote_fidelity']['value']
    rows.append(dict(criterion='quote fidelity', value=v, op='>=', threshold=criteria['quote_fidelity_min'], ok=check(v, '>=', criteria['quote_fidelity_min'])))
    groups = dict(recall=all(r['ok'] for r in rows if 'recall' in r['criterion']), precision=rows[3]['ok'],
                  repeat_spread=all(r['ok'] for r in rows if r['criterion'].startswith('repeat')), quote=rows[-1]['ok'])
    return dict(rows=rows, groups=groups, met=all(groups.values()))


def aggregate(write=True):
    fixture = read(ROOT / 'fixture.json')
    policy = read(ROOT / 'policy.json')
    final = read(ROOT / 'labels-final.json')
    gold = {(x['case'], x['item']): x['label'] for x in final}
    hard = {(x['case'], x['item']) for x in final if x.get('hard_negative')}
    lexical = lexical_negatives()
    entries = {e['id']: e for b in fixture['batches'] for e in b['entries']}
    sessions = {s['id']: s for s in fixture['sessions']}
    batches = {b['id']: b for b in fixture['batches']}
    cases = [f'{b["id"]}-{s["id"]}' for b in fixture['batches'] for s in fixture['sessions']]
    sub = [x for x in cases if x.split('-')[0] in policy['F3_F4_batches']]
    f0raw = ROOT / 'F0-output.json'
    if f0raw.exists():
        saved = read(f0raw)
        pred, times = saved['predictions'], saved['elapsed_seconds']
    else:
        pred, times = {}, []
        for case in cases:
            b, s = case.split('-')
            keys = [s] + sessions[s]['owned'] + sessions[s]['files']
            t = time.perf_counter()
            pred[case] = [dict(id=e['id'], title=e['title'], quote=e['after'], reason='literal match') for e in batches[b]['entries']
                          if any(k in e['title'] + '\n' + e['after'] for k in keys)]
            times.append(time.perf_counter() - t)
        if write:
            f0raw.write_text(json.dumps(dict(predictions=pred, elapsed_seconds=times), ensure_ascii=False, indent=2) + '\n')
    counts = collections.Counter(gold.values())
    rep_counts = collections.Counter(gold[(c, i)] for (c, i) in gold if c in policy['repeats'])
    summary = dict(label_counts=dict(counts), repeat_label_counts=dict(rep_counts), hard_negative_cells=len(hard),
                   lexical_negative_cells=sum(1 for k in lexical if gold.get(k) == 'N'),
                   label_disagreements=len(read(ROOT / 'label-disagreements.json')),
                   conditions={'F0': dict(baseline=measure(cases, pred, gold, entries, hard, lexical), expected_baseline=len(cases),
                                          observed_baseline=len(pred), expected_calls=0, observed_calls=0, time_seconds=numeric(times),
                                          tokens_input=numeric([0] * len(cases)), tokens_output=numeric([0] * len(cases)),
                                          tokens_cached_input=numeric([0] * len(cases)), actual_models=[])},
                   calls=[], missing=[], invalid=[])
    calls = load_calls(summary)
    by_cond = collections.defaultdict(list)
    for r in summary['calls']:
        by_cond[r['condition']].append(r)
    schedule = rx.plan()
    for c in FILTERS + F4:
        selected = cases if c in ['F1', 'F2'] else sub
        base = [x for x in selected if (c, 0, x) in calls]
        metrics = measure(base, {x: calls[(c, 0, x)][1] for x in base}, gold, entries, hard, lexical, quotes_expected=c in FILTERS)
        repeat, spreads = [], {}
        if c in ['F1', 'F2']:
            for r in range(policy['extra_repeats'] + 1):
                s = [x for x in policy['repeats'] if (c, r, x) in calls]
                repeat.append(dict(repetition=r, metrics=measure(s, {x: calls[(c, r, x)][1] for x in s}, gold, entries, hard, lexical)))
            if all(r['metrics']['cases'] == len(policy['repeats']) for r in repeat):
                for lab in ['overall'] + REL:
                    vals = [r['metrics']['recall_overall']['value'] if lab == 'overall' else r['metrics']['recall'][lab]['value'] for r in repeat]
                    spreads[lab] = max(vals) - min(vals) if all(v is not None for v in vals) else None
        obs = by_cond[c]
        summary['conditions'][c] = dict(baseline=metrics, expected_baseline=len(selected), observed_baseline=len(base),
                                        expected_calls=len(schedule[c]), observed_calls=len(obs), repeat=repeat, repeat_spread=spreads,
                                        time_seconds=numeric([r['elapsed_seconds'] for r in obs]),
                                        tokens_input=numeric([r['input'] for r in obs if 'input' in r]),
                                        tokens_output=numeric([r['output'] for r in obs if 'output' in r]),
                                        tokens_cached_input=numeric([r['cached_input'] for r in obs if 'cached_input' in r]),
                                        actual_models=sorted({m for r in obs for m in r['models']}))
    zero = by_cond['F4z']
    summary['conditions']['F4z'] = dict(expected_calls=len(schedule['F4z']), observed_calls=len(zero),
                                        time_seconds=numeric([r['elapsed_seconds'] for r in zero]),
                                        tokens_input=numeric([r['input'] for r in zero if 'input' in r]),
                                        tokens_output=numeric([r['output'] for r in zero if 'output' in r]),
                                        tokens_cached_input=numeric([r['cached_input'] for r in zero if 'cached_input' in r]),
                                        actual_models=sorted({m for r in zero for m in r['models']}))
    summary['cost'] = cost(summary, sub)
    criteria = policy['criteria']
    summary['verdicts'] = {c: verdict(summary['conditions'][c], criteria) for c in ['F1', 'F2'] if summary['conditions'][c]['observed_baseline']}
    if summary['conditions']['F3']['observed_baseline']:
        v = verdict(summary['conditions']['F3'], criteria)
        v['met'] = None
        v['note'] = 'repeat spread not measured by design (no repeats for F3); not evaluable'
        summary['verdicts']['F3'] = v
    freeze = read(ROOT / 'freeze-evaluation.json')
    summary['freeze_verified'] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in freeze['sha256'].items())
    summary['planned_model_calls'] = sum(len(v) for v in schedule.values())
    summary['observed_model_calls'] = len(summary['calls'])
    summary['complete'] = not summary['missing'] and not summary['invalid'] and summary['freeze_verified']
    if write:
        (ROOT / 'metrics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


def cost(summary, sub):
    idx = {(r['condition'], r['repetition'], r['case']): r for r in summary['calls']}
    zero = [r['input'] for r in summary['calls'] if r['condition'] == 'F4z' and 'input' in r]
    overhead = statistics.mean(zero) if zero else None
    rows = []
    for case in sub:
        g = lambda c: idx.get((c, 0, case))
        a, b, c4, f1, f2 = g('F4a'), g('F4b'), g('F4c'), g('F1'), g('F2')
        if not all([a, b, c4, f1, f2]):
            continue
        m = lambda r: r['input'] - overhead if overhead is not None else None
        rows.append(dict(case=case, F4a_input=a['input'], F4b_input=b['input'], F4c_input=c4['input'],
                         F4a_marginal=m(a), F4b_marginal=m(b), F4c_marginal=m(c4),
                         F4a_output=a['output'], F4b_output=b['output'], F4c_output=c4['output'],
                         F1_input=f1['input'], F1_output=f1['output'], F2_input=f2['input'], F2_output=f2['output'],
                         F4a_seconds=a['elapsed_seconds'], path_F1_seconds=f1['elapsed_seconds'] + b['elapsed_seconds'],
                         path_F2_seconds=f2['elapsed_seconds'] + c4['elapsed_seconds'],
                         F1_seconds=f1['elapsed_seconds'], F2_seconds=f2['elapsed_seconds'],
                         F4b_seconds=b['elapsed_seconds'], F4c_seconds=c4['elapsed_seconds']))
    keys = [k for k in (rows[0] if rows else {}) if k != 'case']
    return dict(overhead_input_mean=overhead, overhead_input_values=zero, cases=len(rows),
                summary={k: numeric([r[k] for r in rows if r[k] is not None]) for k in keys}, rows=rows)


if __name__ == '__main__':
    m = aggregate()
    print(json.dumps({k: v for k, v in m.items() if k not in ['calls', 'conditions', 'missing', 'invalid', 'cost', 'verdicts']}, ensure_ascii=False))
    print('missing', len(m['missing']), 'invalid', len(m['invalid']))
    for c, v in m['conditions'].items():
        if 'baseline' not in v:
            continue
        b = v['baseline']
        print(c, v['observed_calls'], {l: r['value'] for l, r in b['recall'].items()}, 'prec', b['precision']['value'], 'N', b['unrelated_pass_rate']['value'],
              'quote', b['quote_fidelity']['value'], 'whole', b['quote_whole_body']['value'], 'spread', v.get('repeat_spread'))
    for c, v in m['verdicts'].items():
        print(c, 'met' if v['met'] else ('not evaluable' if v['met'] is None else 'not met'), v['groups'])
