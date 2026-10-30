"""Audit saved evidence: freeze hashes and order, planned counts, prompts, served models, proxy records, config hashes."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import aggregate as a


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify():
    m = a.aggregate()
    problems = []
    inputs = a.read(a.ROOT / 'freeze-inputs.json')
    freeze = a.read(a.ROOT / 'freeze-evaluation.json')
    for f, h in list(inputs['sha256'].items()) + list(freeze['sha256'].items()):
        if sha(a.ROOT / f) != h:
            problems.append(f'hash changed: {f}')
    t_in = dt.datetime.fromisoformat(inputs['frozen_at'])
    t_final = dt.datetime.fromisoformat(freeze['frozen_at'])
    lab = a.read(a.RUNS / 'labels-independent.meta.json')
    if not t_in < dt.datetime.fromisoformat(lab['started_at']) < t_final:
        problems.append('independent label run is not between the two freezes')
    cells = a.read(a.ROOT / 'labels-final.json')
    if len(cells) != 400 or len({(x['case'], x['item']) for x in cells}) != 400:
        problems.append('label cells != 400')
    totals = {}
    proxy = 0
    mismatches = []
    for row in m['calls']:
        name, c = row['name'], row['condition']
        meta = a.read(a.RUNS / f'{name}.meta.json')
        if dt.datetime.fromisoformat(meta['started_at']) <= t_final:
            problems.append(f'{name} started before final freeze')
        prompt = (a.RUNS / f'{name}.prompt.txt').read_bytes()
        if hashlib.sha256(prompt).hexdigest() != meta['prompt_sha256'] or prompt != (a.ROOT / 'prompts' / f'{row["case"]}.txt').read_bytes():
            problems.append(f'{name} prompt differs from frozen prompt')
        if 'ANTHROPIC_API_KEY' not in meta['command'] or 'OPENAI_API_KEY' not in meta['command'] or meta['command'][0] != 'env':
            problems.append(f'{name} command did not unset API keys')
        models = meta.get('response_models', [])
        ok = len(models) == 1 and (('haiku' in models[0]) if c == 'F1' else models[0] == ('gpt-6-luna' if c == 'F2' else 'gpt-6.1-sol'))
        if not ok:
            problems.append(f'{name} served model {models}')
        totals[c] = totals.get(c, 0) + 1
        if c != 'F1':
            rec = a.read(a.RUNS / f'{name}.proxy.json')
            want = {hashlib.sha256(t.encode()).hexdigest()[:32] for t in meta['thread_ids']}
            for r in rec:
                if r['conversationId'] not in want or r['servedModel'] != models[0] or r['status'] != 200 or \
                        r['requestedModel'] != ('openai/gpt-6-luna' if c == 'F2' else 'gpt-6.1-sol') or \
                        any(x.get('model') != models[0] or x.get('status') != 200 for x in r.get('attempts', [])):
                    problems.append(f'{name} proxy record inconsistent')
            if not rec:
                problems.append(f'{name} has no proxy record')
            proxy += len(rec)
            pi = sum((r.get('usage') or {}).get('inputTokens', 0) for r in rec)
            po = sum((r.get('usage') or {}).get('outputTokens', 0) for r in rec)
            if pi != row.get('input') or po != row.get('output'):
                mismatches.append(dict(name=name, cli_input=row.get('input'), proxy_input=pi, cli_output=row.get('output'), proxy_output=po))
    planned = {c: len(a.plan()[1][c][1]) for c in ['F1', 'F2', 'F3']}
    if totals != planned:
        problems.append(f'calls {totals} != planned {planned}')
    before = a.read(a.ROOT / 'codex-config-hash-before.json')['sha256']
    after = {h: sha(Path.home() / h / 'config.toml') for h in before}
    changed = [h for h in before if before[h] != after[h]]
    if changed:
        problems.append(f'codex config changed: {changed}')
    res = dict(verified=not problems, problems=problems, model_calls=totals, planned_calls=planned, F0_cases=len(a.read(a.ROOT / 'F0-output.json')['predictions']),
               label_cells=len(cells), proxy_records=proxy, actual_models={c: v['actual_models'] for c, v in m['conditions'].items()},
               cli_proxy_usage_mismatches=mismatches, codex_config_sha256_after=after, codex_config_changed=changed,
               checked_at=dt.datetime.now(dt.timezone.utc).isoformat())
    (a.ROOT / 'artifact-verification.json').write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in res.items() if k != 'cli_proxy_usage_mismatches'}, ensure_ascii=False, indent=1), 'usage mismatches', len(mismatches))
    return res


if __name__ == '__main__':
    verify()
