"""S12b: reconcile author and independent labels, materialize prompts, freeze everything before any filter call.

Every disagreement gets an explicit decision with a reason, written down here before evaluation.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / 'runs'

# Decided after reading the six disagreements, before any F1/F2/F3 call.
DECISIONS = {
    ('B01-Tern', 'B01-02'): ('AMBIGUOUS', 'Tern의 작업 설명은 캐싱 위치를 말하지 않는다. 공용 인메모리 저장소에 기댄다는 전제는 작성자의 숨은 메모에만 있고 설명에서 추론된다고 보기 어렵다. 근거가 갈려 모호로 둔다.'),
    ('B03-Tern', 'B03-02'): ('AMBIGUOUS', '같은 이유. 공용 저장소의 스테이징 사본이 Tern에게 필요한 자원인지는 설명만으로 정해지지 않는다.'),
    ('B04-Tern', 'B04-02'): ('AMBIGUOUS', '같은 이유. 키 자동 소멸 기능이 Tern의 캐싱 전제인지는 설명만으로 정해지지 않는다.'),
    ('B02-Heron', 'B02-04'): ('R3', '독립 라벨 채택. Heron은 이식 전후 동작이 같음을 확인해야 하는데, 이 변경은 그 기준 동작(활동 시 보관 기간 갱신)을 바꾼다. R2에도 해당하지만 우선순위 R3>R2에 따라 R3.'),
    ('B05-Heron', 'B05-07'): ('R3', '독립 라벨 채택. 강제 로그아웃의 기준 동작 자체를 바꾸는 작업이다. R2에도 해당하지만 우선순위에 따라 R3.'),
    ('B10-Heron', 'B10-04'): ('R3', '독립 라벨 채택. 보관 기간 갱신 계산과 내보내기 동작을 새로 짜서 기준 동작이 바뀐다. 우선순위에 따라 R3.'),
}


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def main():
    fixture = json.loads((ROOT / 'fixture.json').read_text())
    author = json.loads((ROOT / 'labels-author.json').read_text())
    second = json.loads((RUNS / 'labels-independent.parsed.json').read_text())['labels']
    keys = {(a['case'], a['item']) for a in author}
    seen = {}
    for x in second:
        k = (x['case'], x['item'])
        assert k in keys and k not in seen and x['label'] in ['R1', 'R2', 'R3', 'R4', 'N'], x
        seen[k] = x['label']
    final, disagreements = [], []
    for a in author:
        k = (a['case'], a['item'])
        other = seen.get(k, 'N')
        row = {**a, 'author': a['label'], 'independent': other}
        if a['label'] != other:
            assert k in DECISIONS, f'undecided disagreement {k}'
            row['label'], row['reason'] = DECISIONS[k]
            disagreements.append(dict(row))
        final.append(row)
    assert len(disagreements) == len(DECISIONS), 'decision table does not match the observed disagreements'
    dump(ROOT / 'labels-final.json', final)
    dump(ROOT / 'label-disagreements.json', disagreements)
    prompts = ROOT / 'prompts'
    prompts.mkdir(exist_ok=True)
    head = (ROOT / 'filter-prompt.txt').read_text()
    for b in fixture['batches']:
        for s in fixture['sessions']:
            p = head + '\n세션:\n' + json.dumps(s, ensure_ascii=False) + '\n변경 diff:\n'
            for x in b['entries']:
                p += f'변경 ID: {x["id"]}\n## {x["title"]}\n- {x["before"]}\n+ {x["after"]}\n\n'
            (prompts / f'{b["id"]}-{s["id"]}.txt').write_text(p)
    files = [ROOT / x for x in ['BOARD.md', 'fixture.json', 'labels-author.json', 'labels-final.json', 'label-disagreements.json', 'policy.json',
                                'filter-prompt.txt', 'label-prompt.txt', 'freeze-inputs.json', 'run_experiment.py', 'reconcile.py',
                                'runs/labels-independent.parsed.json']] + sorted(prompts.glob('*.txt'))
    counts = {}
    for r in final:
        counts[r['label']] = counts.get(r['label'], 0) + 1
    dump(ROOT / 'freeze-evaluation.json', dict(frozen_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                                               sha256={str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
                                               label_disagreements=len(disagreements), label_cells=len(final), label_counts=counts,
                                               stage='all labels/prompts/policy fixed before the first F1/F2/F3 call'))
    print('reconciled', len(final), 'disagreements', len(disagreements), counts)


if __name__ == '__main__':
    main()
