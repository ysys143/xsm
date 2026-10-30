"""S12c: reconcile author and independent labels, materialize prompts, freeze everything before any filter call.

Adapted from deliverables/s12b-hard-sample/reconcile.py. Every disagreement gets an explicit decision with a reason,
written here after reading the independent labels and before any F1/F2/F3/F4 call.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / 'runs'
MIN_FINAL = 30  # user decision: R2, R3, R4 each >= 30 cells in the final labels

# Filled in after reading the disagreements, before any filter call.
DECISIONS = {
}


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def render(entries):
    return ''.join(f'변경 ID: {x["id"]}\n## {x["title"]}\n- {x["before"]}\n+ {x["after"]}\n\n' for x in entries)


def main(write=True):
    fixture = json.loads((ROOT / 'fixture.json').read_text())
    author = json.loads((ROOT / 'labels-author.json').read_text())
    second = json.loads((RUNS / 'labels-independent.parsed.json').read_text())['labels']
    keys = {(a['case'], a['item']) for a in author}
    seen = {}
    for x in second:
        k = (x['case'], x['item'])
        assert k in keys and k not in seen and x['label'] in ['R1', 'R2', 'R3', 'R4', 'N'], x
        seen[k] = x['label']
    final, disagreements, undecided = [], [], []
    for a in author:
        k = (a['case'], a['item'])
        other = seen.get(k, 'N')
        row = {**a, 'author': a['label'], 'independent': other}
        if a['label'] != other:
            if k not in DECISIONS:
                undecided.append(dict(case=k[0], item=k[1], author=a['label'], independent=other))
            else:
                row['label'], row['reason'] = DECISIONS[k]
            disagreements.append(dict(row))
        final.append(row)
    if not write:
        return final, disagreements, undecided
    assert not undecided, f'undecided disagreements: {undecided}'
    assert len(disagreements) == len(DECISIONS), 'decision table does not match the observed disagreements'
    counts = {}
    for r in final:
        counts[r['label']] = counts.get(r['label'], 0) + 1
    short = {l: counts.get(l, 0) for l in ['R2', 'R3', 'R4'] if counts.get(l, 0) < MIN_FINAL}
    assert not short, f'final label cells below {MIN_FINAL}: {short}; stop before any filter call'
    dump(ROOT / 'labels-final.json', final)
    dump(ROOT / 'label-disagreements.json', disagreements)
    prompts, f4 = ROOT / 'prompts', ROOT / 'prompts-f4'
    prompts.mkdir(exist_ok=True)
    f4.mkdir(exist_ok=True)
    head = (ROOT / 'filter-prompt.txt').read_text()
    f4head = (ROOT / 'f4-prompt.txt').read_text()
    for b in fixture['batches']:
        for s in fixture['sessions']:
            sj = '\n세션:\n' + json.dumps(s, ensure_ascii=False) + '\n변경 diff:\n'
            (prompts / f'{b["id"]}-{s["id"]}.txt').write_text(head + sj + render(b['entries']))
            (f4 / f'{b["id"]}-{s["id"]}.txt').write_text(f4head + sj + render(b['entries']))
    for s in fixture['sessions']:
        (f4 / f'zero-{s["id"]}.txt').write_text(f4head + '\n세션:\n' + json.dumps(s, ensure_ascii=False) + '\n변경 diff:\n(변경 없음)\n')
    files = [ROOT / x for x in ['BOARD.md', 'fixture.json', 'labels-author.json', 'labels-final.json', 'label-disagreements.json', 'policy.json',
                                'filter-prompt.txt', 'label-prompt.txt', 'f4-prompt.txt', 'f4-filtered-note.txt', 'freeze-inputs.json',
                                'run_experiment.py', 'reconcile.py', 'select_repeats.py', 'runs/labels-independent.parsed.json']] \
        + sorted(prompts.glob('*.txt')) + sorted(f4.glob('*.txt'))
    dump(ROOT / 'freeze-evaluation.json', dict(frozen_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                                               sha256={str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
                                               label_disagreements=len(disagreements), label_cells=len(final), label_counts=counts,
                                               stage='all labels/prompts/policy fixed before the first F1/F2/F3/F4 call'))
    print('reconciled', len(final), 'disagreements', len(disagreements), counts)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'show':
        final, dis, und = main(write=False)
        print(json.dumps(und, ensure_ascii=False, indent=1))
        print('undecided', len(und))
    else:
        main()
