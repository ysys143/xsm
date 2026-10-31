"""S12b: assemble the hard sample, check its design rules, freeze it.

python3 build_fixture.py check   # rule checks only, writes nothing
python3 build_fixture.py freeze  # checks, then writes fixture/labels/prompts and freeze-inputs.json
"""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
S12 = ROOT.parent / 's12-board-filter'
LABELS = ['R1', 'R2', 'R3', 'R4']
NEW = '(이전 내용 없음: 새 항목)'


def load():
    meta = json.loads((SRC / 'sessions.json').read_text())
    sessions = meta['sessions']
    batches = []
    for b in range(1, 11):
        bid = f'B{b:02d}'
        p = SRC / f'{bid}.json'
        if not p.exists():
            continue
        entries = []
        for i, x in enumerate(json.loads(p.read_text()), 1):
            entries.append(dict(id=f'{bid}-{i:02d}', title=x['title'], before=x.get('before', NEW), after=x['after'],
                                labels=x['labels'], hn=x['hn']))
        batches.append(dict(id=bid, entries=entries))
    return meta, sessions, batches


def hits(text, terms):
    low = text.lower()
    return [t for t in terms if t.lower() in low]


def check(meta, sessions, batches, strict=True):
    terms = meta['distinctive_terms']
    names = [s['id'] for s in sessions]
    problems = []
    report = dict(items=0, words=[], hard_negative_cells=0, lexical_negative_cells=0, f0_negative_hits=[])
    for s in sessions:
        if set(s) - {'id', 'task', 'owned', 'files'}:
            problems.append(f'session {s["id"]} has extra fields {set(s) - {"id", "task", "owned", "files"}}')
    for b in batches:
        if len(b['entries']) != 8:
            problems.append(f'{b["id"]} has {len(b["entries"])} entries')
        for e in b['entries']:
            report['items'] += 1
            n = len(e['after'].split())
            report['words'].append(n)
            if not 60 <= n <= 200:
                problems.append(f'{e["id"]} words={n}')
            text = e['title'] + '\n' + e['after']
            for s, lab in e['labels'].items():
                if s not in names or lab not in LABELS:
                    problems.append(f'{e["id"]} bad label {s}={lab}')
            for s in sessions:
                sid = s['id']
                lab = e['labels'].get(sid, 'N')
                h = hits(text, terms[sid])
                if lab in ['R2', 'R3', 'R4'] and h:
                    problems.append(f'{e["id"]} {sid} {lab} shares terms {h}')
                if lab == 'R1':
                    keys = [sid] + s['owned'] + s['files']
                    if not any(k in text for k in keys):
                        problems.append(f'{e["id"]} {sid} R1 without name/owned/file')
                if sid in e['hn']:
                    if lab != 'N':
                        problems.append(f'{e["id"]} {sid} marked hard negative but labelled {lab}')
                    if not h:
                        problems.append(f'{e["id"]} {sid} hard negative without shared term')
                    report['hard_negative_cells'] += 1
                if lab == 'N' and h:
                    report['lexical_negative_cells'] += 1
                if lab != 'R1' and any(k in text for k in [sid] + s['owned'] + s['files']):
                    report['f0_negative_hits'].append(f'{e["id"]}:{sid}:{lab}')
    return problems, report


def counts(sessions, batches):
    c = {}
    for b in batches:
        for e in b['entries']:
            for s in sessions:
                lab = e['labels'].get(s['id'], 'N')
                c.setdefault(s['id'], {}).setdefault(lab, 0)
                c[s['id']][lab] += 1
    return c


def write(name, obj):
    (ROOT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def freeze(meta, sessions, batches):
    fixture_batches = [dict(id=b['id'], entries=[{k: e[k] for k in ['id', 'title', 'before', 'after']} for e in b['entries']]) for b in batches]
    write('fixture.json', dict(sessions=sessions, batches=fixture_batches))
    labels = []
    for b in batches:
        for e in b['entries']:
            for s in sessions:
                labels.append(dict(case=f'{b["id"]}-{s["id"]}', item=e['id'], label=e['labels'].get(s['id'], 'N'),
                                   hard_negative=s['id'] in e['hn']))
    write('labels-author.json', labels)
    # The base board holds every section that any delta touches, with its pre-change content.
    seen = {}
    for b in batches:
        for e in b['entries']:
            seen.setdefault(e['title'].split()[0], e['before'])
    board = '# 합성 팀 보드 (S12b)\n\n' + '\n\n'.join(f'## {k}\n{v}' for k, v in sorted(seen.items())) + '\n'
    (ROOT / 'BOARD.md').write_text(board)
    # Filter prompt reused verbatim from S12.
    (ROOT / 'filter-prompt.txt').write_bytes((S12 / 'filter-prompt.txt').read_bytes())
    label_prompt = ('독립 보드 라벨러 역할이다. 최초 작성자의 라벨은 제공하지 않는다. 도구와 파일 접근 없이 아래 데이터만 읽고 모든 세션×변경을 라벨링하라. '
                    '각 배치는 같은 초기 보드에서 독립적으로 발생한다. 세션 설명에는 전제나 필요 자원이 목록으로 적혀 있지 않다. 작업 내용에서 합리적으로 추론되는 전제와 자원을 기준으로 판단하라. '
                    'R1=세션 이름/담당 항목 번호/담당 파일을 직접 지명. '
                    'R2=다른 사람이 그 세션과 같은 일(같은 대상의 같은 변경)을 시작했거나 하고 있음(지명 없음). '
                    'R3=그 세션의 작업이 성립하려면 참이어야 하는 사실(작업 설명에서 추론되는 것)을 뒤집거나 무효로 만듦. '
                    'R4=그 세션의 작업에 필요한 것(작업 설명에서 추론되는 환경·장비·계정·할당량)을 다른 작업이 점유하거나 쓸 수 없게 됨. '
                    'N=무관. 같은 단어가 나와도 다른 맥락이면 N. 복수 해당이면 R4>R3>R2>R1 우선. 생략된 셀은 N으로 처리한다. '
                    '관련 셀(N이 아닌 셀)을 빠짐없이 JSON {"labels":[{"case":"B01-Heron","item":"B01-01","label":"R1"}]}로만 반환하라. case는 "<배치 ID>-<세션 ID>"다.\n')
    (ROOT / 'label-prompt.txt').write_text(label_prompt + json.dumps(dict(sessions=sessions, batches=fixture_batches), ensure_ascii=False))
    files = ['BOARD.md', 'fixture.json', 'labels-author.json', 'policy.json', 'filter-prompt.txt', 'label-prompt.txt',
             'build_fixture.py', 'src/sessions.json'] + [f'src/{b["id"]}.json' for b in batches]
    write('freeze-inputs.json', dict(frozen_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                                     sha256={f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
                                     stage='pre-inference input/author-label/policy freeze; independent labels and reconciliation follow before any filter call'))


if __name__ == '__main__':
    meta, sessions, batches = load()
    problems, report = check(meta, sessions, batches)
    w = report.pop('words')
    print(json.dumps(dict(batches=len(batches), **report, words_min=min(w) if w else None, words_max=max(w) if w else None,
                          words_mean=sum(w) / len(w) if w else None, counts=counts(sessions, batches)), ensure_ascii=False, indent=1))
    print('problems:', len(problems))
    for p in problems:
        print(' -', p)
    if len(sys.argv) > 1 and sys.argv[1] == 'freeze':
        if problems or len(batches) != 10:
            raise SystemExit('not frozen: rule violations or missing batches')
        assert (ROOT / 'policy.json').exists(), 'policy.json must exist before freeze'
        freeze(meta, sessions, batches)
        print('frozen')
