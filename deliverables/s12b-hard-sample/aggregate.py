"""Reproducible metrics for S12b (S12 structure plus hard-negative and lexical-negative pass rates)."""
import collections
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / 'runs'
LABELS = ['R1', 'R2', 'R3', 'R4', 'N', 'AMBIGUOUS']
REL = ['R1', 'R2', 'R3', 'R4']


def read(p):
    return json.loads(p.read_text())


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


def measure(cases, predictions, gold, entries, hard, lexical):
    denom = collections.Counter()
    hits = collections.Counter()
    tp = fp = amb = invalid = quotes = faithful = title_bad = duplicate = 0
    hn_den = hn_fp = lx_den = lx_fp = 0
    qlen = []
    selected = []
    errors = []
    for case in cases:
        gs = {item: label for (c, item), label in gold.items() if c == case}
        for item, label in gs.items():
            denom[label] += 1
            if label == 'N' and (case, item) in hard:
                hn_den += 1
            if label == 'N' and (case, item) in lexical:
                lx_den += 1
        predicted = set()
        for item in predictions[case]:
            quotes += 1
            iid = item.get('id')
            entry = entries.get(iid)
            q = item.get('quote')
            if entry and isinstance(q, str) and q.strip() and q in entry['after']:
                faithful += 1
                qlen.append(len(q) / len(entry['after']))
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
            else:
                fp += 1
                if label is None:
                    invalid += 1
                else:
                    hits['N'] += 1
                    hn_fp += (case, iid) in hard
                    lx_fp += (case, iid) in lexical
                errors.append(dict(case=case, item=iid, type='false_positive', gold=label, hard_negative=(case, iid) in hard, lexical_overlap=(case, iid) in lexical))
        for iid, label in gs.items():
            if label in REL and iid not in predicted:
                errors.append(dict(case=case, item=iid, type='false_negative', gold=label))
        selected.append(dict(case=case, selected=sorted(str(x) for x in predicted)))
    rel_den = sum(denom[l] for l in REL)
    return dict(cases=len(cases), label_denominators=dict(denom), label_hits=dict(hits),
                recall={l: dict(numerator=hits[l], denominator=denom[l], value=ratio(hits[l], denom[l])) for l in REL},
                recall_overall=dict(numerator=tp, denominator=rel_den, value=ratio(tp, rel_den)),
                precision=dict(numerator=tp, denominator=tp + fp, value=ratio(tp, tp + fp)),
                unrelated_pass_rate=dict(numerator=hits['N'], denominator=denom['N'], value=ratio(hits['N'], denom['N'])),
                hard_negative_pass_rate=dict(numerator=hn_fp, denominator=hn_den, value=ratio(hn_fp, hn_den)),
                lexical_negative_pass_rate=dict(numerator=lx_fp, denominator=lx_den, value=ratio(lx_fp, lx_den)),
                quote_fidelity=dict(numerator=faithful, denominator=quotes, value=ratio(faithful, quotes)),
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
                cached_input=sum(u.get('cached_input_tokens', 0) for u in us), source='Codex turn.completed.usage (cache-inclusive input)')


def plan():
    fixture = read(ROOT / 'fixture.json')
    policy = read(ROOT / 'policy.json')
    cases = [f'{b["id"]}-{s["id"]}' for b in fixture['batches'] for s in fixture['sessions']]
    out = {}
    for c in ['F1', 'F2', 'F3']:
        sel = cases if c != 'F3' else [x for x in cases if x.split('-')[0] in policy['F3_batches']]
        out[c] = (sel, [(0, x) for x in sel] + ([(r, x) for r in range(1, 4) for x in policy['repeats']] if c != 'F3' else []))
    return cases, out


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
    cases, schedule = plan()
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
    summary = dict(label_counts=dict(counts), hard_negative_cells=len(hard), lexical_negative_cells=sum(1 for k in lexical if gold.get(k) == 'N'),
                   label_disagreements=len(read(ROOT / 'label-disagreements.json')),
                   conditions={'F0': dict(baseline=measure(cases, pred, gold, entries, hard, lexical), expected_baseline=len(cases), observed_baseline=len(pred),
                                          expected_calls=0, observed_calls=0, time_seconds=numeric(times), tokens_input=numeric([0] * len(cases)),
                                          tokens_output=numeric([0] * len(cases)), tokens_cached_input=numeric([0] * len(cases)), actual_models=[])},
                   calls=[], missing=[], invalid=[])
    for c in ['F1', 'F2', 'F3']:
        selected, expected = schedule[c]
        predictions, observed = {}, []
        for rep, case in expected:
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
            predictions[(rep, case)] = obj['items']
            row = dict(name=name, condition=c, repetition=rep, case=case, models=meta.get('response_models', []), elapsed_seconds=meta['elapsed_seconds'], **usage(meta))
            observed.append(row)
            summary['calls'].append(row)
        base = [x for x in selected if (0, x) in predictions]
        metrics = measure(base, {x: predictions[(0, x)] for x in base}, gold, entries, hard, lexical)
        repeat, spreads = [], {}
        if c != 'F3':
            for r in range(4):
                sub = [x for x in policy['repeats'] if (r, x) in predictions]
                repeat.append(dict(repetition=r, metrics=measure(sub, {x: predictions[(r, x)] for x in sub}, gold, entries, hard, lexical)))
            if all(r['metrics']['cases'] == 10 for r in repeat):
                for lab in REL + ['overall']:
                    vals = [r['metrics']['recall_overall']['value'] if lab == 'overall' else r['metrics']['recall'][lab]['value'] for r in repeat]
                    spreads[lab] = max(vals) - min(vals) if all(v is not None for v in vals) else None
        summary['conditions'][c] = dict(baseline=metrics, expected_baseline=len(selected), observed_baseline=len(base), expected_calls=len(expected),
                                        observed_calls=len(observed), repeat=repeat, repeat_spread=spreads,
                                        time_seconds=numeric([r['elapsed_seconds'] for r in observed]),
                                        tokens_input=numeric([r['input'] for r in observed if 'input' in r]),
                                        tokens_output=numeric([r['output'] for r in observed if 'output' in r]),
                                        tokens_cached_input=numeric([r['cached_input'] for r in observed if 'cached_input' in r]),
                                        actual_models=sorted({m for r in observed for m in r['models']}))
    freeze = read(ROOT / 'freeze-evaluation.json')
    summary['freeze_verified'] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in freeze['sha256'].items())
    summary['planned_model_calls'] = sum(len(schedule[c][1]) for c in schedule)
    summary['observed_model_calls'] = len(summary['calls'])
    summary['complete'] = not summary['missing'] and not summary['invalid'] and summary['freeze_verified']
    if write:
        (ROOT / 'metrics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    m = aggregate()
    print(json.dumps({k: v for k, v in m.items() if k not in ['calls', 'conditions', 'missing', 'invalid']}, ensure_ascii=False))
    print('missing', len(m['missing']), 'invalid', len(m['invalid']))
    for c, v in m['conditions'].items():
        b = v['baseline']
        print(c, v['observed_calls'], {l: r['value'] for l, r in b['recall'].items()}, 'prec', b['precision']['value'], 'N', b['unrelated_pass_rate']['value'],
              'HN', b['hard_negative_pass_rate']['value'], 'quote', b['quote_fidelity']['value'], 'spread', v.get('repeat_spread'))
