"""S12c: choose the repeat cases from the author labels before any model call (user decision: stratified repeats).

Rule (frozen in policy.json): greedy over cases in sorted ID order; at each step take the case that adds the most
still-needed R1-R4 cells toward the target (ties: more relevant cells, then the earlier case ID), at most 3 cases
per batch, until every target is met. Targets: R1 >= 10, R2 >= 12, R3 >= 12, R4 >= 12 author cells.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REL = ['R1', 'R2', 'R3', 'R4']
TARGET = dict(R1=10, R2=12, R3=12, R4=12)
CAP = 3


def author_cases():
    sessions = [s['id'] for s in json.loads((ROOT / 'src/sessions.json').read_text())['sessions']]
    cases = {}
    for b in range(1, 14):
        bid = f'B{b:02d}'
        for x in json.loads((ROOT / 'src' / f'{bid}.json').read_text()):
            for s in sessions:
                cases.setdefault(f'{bid}-{s}', Counter())[x['labels'].get(s, 'N')] += 1
    return cases


def select():
    cases = author_cases()
    chosen, tot = [], Counter()
    while any(tot[l] < TARGET[l] for l in REL):
        best = None
        for c, cnt in sorted(cases.items()):
            if c in chosen or sum(1 for x in chosen if x[:3] == c[:3]) >= CAP:
                continue
            gain = sum(min(cnt[l], max(0, TARGET[l] - tot[l])) for l in REL)
            key = (gain, sum(cnt[l] for l in REL))
            if best is None or key > best[0]:
                best = (key, c)
        assert best and best[0][0] > 0, 'targets cannot be met'
        chosen.append(best[1])
        tot += Counter({l: cases[best[1]][l] for l in REL})
    return sorted(chosen), {l: tot[l] for l in REL}


if __name__ == '__main__':
    ch, tot = select()
    print(len(ch), tot)
    print(ch)
