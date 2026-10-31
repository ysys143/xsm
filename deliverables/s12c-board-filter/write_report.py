"""Render docs/spikes/S12c-results.md from saved measurements; no inference.

Adapted from S12b's write_report.py. Interpretive prose lives in report-notes.json (written after the numbers were
seen) and is inserted verbatim; every number in tables comes from metrics.json / artifact-verification.json.
"""
import collections
import datetime as dt
import json
import aggregate as a

ROOT = a.ROOT
DEST = ROOT.parents[1] / 'docs/spikes/S12c-results.md'
NAMES = {'R1': 'R1 직접', 'R2': 'R2 겹침', 'R3': 'R3 전제', 'R4': 'R4 자원'}
CRIT = {'R2 recall': 'R2 재현율', 'R3 recall': 'R3 재현율', 'R4 recall': 'R4 재현율', 'precision': '정밀도',
        'repeat spread overall': '반복 차이 전체', 'repeat spread R1': '반복 차이 R1', 'repeat spread R2': '반복 차이 R2',
        'repeat spread R3': '반복 차이 R3', 'repeat spread R4': '반복 차이 R4', 'quote fidelity': '인용 충실도'}


def frac(x):
    return f'{100 * x["value"]:.1f}% ({x["numerator"]}/{x["denominator"]})' if x['value'] is not None else 'NA (0건)'


def num(x, d=1):
    return f'{x:,.{d}f}' if x is not None else 'NA'


def pct(x, d=1):
    return f'{100 * x:.{d}f}%' if x is not None else 'NA'


def pp(x):
    return f'{100 * x:.1f}%p' if x is not None else 'NA'


def anomalies():
    fixture = a.read(ROOT / 'fixture.json')
    entries = {e['id']: e for b in fixture['batches'] for e in b['entries']}
    counts = collections.Counter()
    items = []
    for f in sorted(a.RUNS.glob('F[123]-*.meta.json')):
        p = f.with_name(f.name.replace('.meta.json', '.parsed.json'))
        if not p.exists():
            continue
        cond = f.name[:2]
        for it in a.read(p).get('items', []):
            e = entries.get(it.get('id'))
            issues = []
            if not e:
                issues.append('unknown ID')
            else:
                t = it.get('title', '')
                if t != e['title']:
                    counts[cond + ' title mismatch'] += 1
                    if t.lstrip('# ').strip() == e['title']:
                        counts[cond + ' title hash-prefix-only'] += 1
                    else:
                        issues.append('title content mismatch')
                q = it.get('quote', '')
                if not isinstance(q, str) or not q.strip() or q not in e['after']:
                    issues.append('quote mismatch')
            if issues:
                items.append(dict(run=f.name.replace('.meta.json', ''), id=it.get('id'), issues=issues, title=it.get('title'),
                                  expected_title=e['title'] if e else None))
    obj = dict(title_counts=dict(counts), items=items)
    (ROOT / 'anomalies.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    return obj


def report():
    m = a.aggregate()
    an = anomalies()
    inputs = a.read(ROOT / 'freeze-inputs.json')
    freeze = a.read(ROOT / 'freeze-evaluation.json')
    notes = a.read(ROOT / 'report-notes.json')
    policy = a.read(ROOT / 'policy.json')
    ver = a.read(ROOT / 'artifact-verification.json') if (ROOT / 'artifact-verification.json').exists() else None
    scrub = a.read(ROOT / 'scrub-check.json') if (ROOT / 'scrub-check.json').exists() else None
    conds = m['conditions']
    lc = m['label_counts']
    rc = m['repeat_label_counts']
    L = ['# S12c 결과: 더 크고 긴 표본에서 사용자 기준으로 걸러 읽기를 판정한다', '',
         f'- 상태: {"계획한 실행 및 집계 완료" if m["complete"] else "미완: 계획한 호출 수 미충족"}',
         f'- 실행일: 2026-10-30 (KST). 보고서 생성: {dt.datetime.now(dt.timezone.utc).isoformat()}',
         '- 원본 계획: [S12c-plan.md](S12c-plan.md). 비교 대상: [S12b-results.md](S12b-results.md), [S12-results.md](S12-results.md)',
         '- 자료·스크립트·응답: [deliverables/s12c-board-filter](../../deliverables/s12c-board-filter/)', '']
    L += notes['headline'] + ['']
    L += ['## 고정 자료와 라벨', '',
          '세션 7개, 독립 변경 묶음 13개(묶음당 항목 8개), 항목 104개다. 기본 실행은 F0·F1·F2가 91사례, 728개 변경 판정이다. 묶음은 같은 초기 보드에 대한 독립 diff다.', '']
    L += notes['fixture'] + ['']
    L += [f'입력·작성자 라벨·판정 정책·반복 사례는 **{inputs["frozen_at"]}** 에 먼저 고정했다. 그 뒤 별도 `claude -p --model opus` 실행(도구 목록 비움, MCP 없음)이 작성자 라벨과 숨은 메모 없이 세션 설명·변경·라벨 규칙만 받아 독립 라벨을 달았다. 실제 응답 모델은 `{", ".join(ver["label_model"]) if ver else "?"}`였다. 관련 셀을 열거하고 생략 셀을 N으로 보는 방식으로 728건 전체를 비교했다.', '',
          f'라벨 불일치: **{m["label_disagreements"]}/728건**. 최종 라벨 수는 ' + ', '.join(f'{l} {lc.get(l, 0)}건' for l in ['R1', 'R2', 'R3', 'R4', 'N']) + f', 모호 {lc.get("AMBIGUOUS", 0)}건이다. R2·R3·R4가 모두 사용자 요구 30셀 이상이다. 어려운 음성 표시 N 셀은 {m["hard_negative_cells"]}건, 세션의 구별 단어를 포함하는 N 셀은 {m["lexical_negative_cells"]}건이다.', '']
    L += notes['disagreements'] + ['']
    L += [f'필터 호출 전 **{freeze["frozen_at"]}** 에 최종 라벨, 프롬프트(필터 91개, F4 전체 읽기·보정 98개), 판정 정책, 실행 스크립트의 SHA-256을 다시 고정했다. 집계 시 고정 파일 검증 결과는 `{m["freeze_verified"]}`다. 결과를 본 뒤 라벨·기준은 바꾸지 않았다.', '',
          '| 고정 파일 | SHA-256 |', '|---|---|']
    for f in ['BOARD.md', 'fixture.json', 'labels-author.json', 'labels-final.json', 'policy.json', 'filter-prompt.txt', 'f4-prompt.txt']:
        L.append(f'| `{f}` | `{freeze["sha256"][f]}` |')
    L += ['', '## 실행 수와 실제 모델', '', '| 조건 | 기본 사례 / 계획 | 추가 반복 / 계획 | 모델 호출 / 계획 | 로그에서 확인한 실제 응답 모델 |', '|---|---:|---:|---:|---|']
    extra = 3 * len(policy['repeats'])
    for c in ['F0', 'F1', 'F2', 'F3', 'F4a', 'F4b', 'F4c', 'F4z']:
        x = conds[c]
        if c == 'F0':
            L.append(f'| F0 | {x["observed_baseline"]}/{x["expected_baseline"]} | 0/0 | 0/0 | 모델 없음 |')
            continue
        ob = x.get('observed_baseline', x['observed_calls'])
        eb = x.get('expected_baseline', x['expected_calls'])
        ep = extra if c in ['F1', 'F2'] else 0
        L.append(f'| {c} | {ob}/{eb} | {x["observed_calls"] - ob}/{ep} | {x["observed_calls"]}/{x["expected_calls"]} | ' + ', '.join(f'`{v}`' for v in x['actual_models']) + ' |')
    L += ['', f'모델 호출 합계: **{m["observed_model_calls"]}/{m["planned_model_calls"]}회**(독립 라벨 1회 제외). F3·F4는 사전 선택한 {"·".join(policy["F3_F4_batches"])}의 3묶음 × 7세션 = 21사례다. F4z는 변경 없는 보정 호출 3회다.', '']
    L += notes['runtime'] + ['']
    L += ['## 재현율·정밀도·인용', '',
          '기본 실행의 결과다(F1·F2 91사례, F3·F4 21사례). 반복 호출은 아래에서 따로 집계한다. 정밀도는 TP/(TP+FP), N 통과율은 FP_N/N이다. 모호 셀은 분모에서 뺐다. F4는 인용을 요구하지 않으므로 인용 칸이 비어 있다.', '',
          '| 조건 | R1 직접 | R2 겹침 | R3 전제 | R4 자원 | 전체 관련 재현율 | 정밀도 | N 통과율 | 어려운 음성 통과율 | 단어 겹침 N 통과율 | 인용 충실도 |',
          '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in ['F0', 'F1', 'F2', 'F3', 'F4a', 'F4b', 'F4c']:
        b = conds[c]['baseline']
        L.append('| ' + c + ' | ' + ' | '.join([frac(b['recall'][l]) for l in a.REL] + [frac(b[k]) for k in ['recall_overall', 'precision', 'unrelated_pass_rate', 'hard_negative_pass_rate', 'lexical_negative_pass_rate']]
                                            + [frac(b['quote_fidelity']) if c in ['F0', 'F1', 'F2', 'F3'] else '-']) + ' |')
    L += ['', '인용 충실도는 반환한 인용이 **같은 ID 항목의 변경 후 본문에 들어 있는 비어 있지 않은 연속 문자열**인 비율이다. 계획대로 본문 전체를 복사한 인용도 충실로 세고, 충실 인용을 본문 전체와 발췌로 나눴다.', '',
          '| 조건 | 충실 인용 중 본문 전체 | 충실 인용 중 발췌 | 긴 항목 인용: 반환/충실/본문 전체 | 충실 인용의 본문 대비 길이 중앙값 | 제목 불일치 | 중복 ID | 알 수 없는 ID | 모호 셀 선택 / 모호 셀 |',
          '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in ['F0', 'F1', 'F2', 'F3']:
        b = conds[c]['baseline']
        ql = b['quote_long_items']
        L.append(f'| {c} | {frac(b["quote_whole_body"])} | {frac(b["quote_excerpt"])} | {ql["returned"]}/{ql["faithful"]}/{ql["whole_body"]} | {pct(b["quote_share_of_item"]["median"])} | {b["title_mismatches"]} | {b["duplicates"]} | {b["invalid_ids"]} | {b["ambiguous_selected"]}/{b["ambiguous_cells"]} |')
    L += ['', '긴 항목(150–200어절)과 짧은 항목(60–100어절)의 관련 셀 재현율:', '', '| 조건 | 긴 항목 | 짧은 항목 |', '|---|---:|---:|']
    for c in ['F0', 'F1', 'F2', 'F3', 'F4a']:
        b = conds[c]['baseline']['recall_by_length']
        L.append(f'| {c} | {frac(b["long"])} | {frac(b["short"])} |')
    L += [''] + notes['f0'] + ['', '## 놓친 것과 잘못 고른 것 (기본 실행)', '']
    fixture = a.read(ROOT / 'fixture.json')
    entries = {e['id']: e for bb in fixture['batches'] for e in bb['entries']}
    for c in ['F1', 'F2', 'F3']:
        errs = conds[c]['baseline']['errors']
        fn = [e for e in errs if e['type'] == 'false_negative']
        fp = [e for e in errs if e['type'] == 'false_positive']
        L.append(f'- {c}: 누락 {len(fn)}건, 과잉 선택 {len(fp)}건.')
        for e in fn:
            L.append(f'  - 누락 {e["case"]} {e["item"]} (정답 {e["gold"]}, {"긴" if e.get("long") else "짧은"} 항목, 제목 `{entries[e["item"]]["title"]}`)')
        if len(fp) <= 30:
            for e in fp:
                tag = '어려운 음성' if e.get('hard_negative') else ('단어 겹침' if e.get('lexical_overlap') else ('알 수 없는 ID' if e.get('gold') is None else '일반 N'))
                L.append(f'  - 과잉 {e["case"]} {e["item"]} (정답 {e["gold"]}, {tag}, 제목 `{entries.get(e["item"], {}).get("title")}`)')
        else:
            tags = collections.Counter('어려운 음성' if e.get('hard_negative') else ('단어 겹침' if e.get('lexical_overlap') else ('알 수 없는 ID' if e.get('gold') is None else '일반 N')) for e in fp)
            L.append('  - 과잉 선택은 30건이 넘어 종류별 수만 적는다: ' + ', '.join(f'{k} {v}건' for k, v in tags.most_common()) + '. 전체 목록은 `metrics.json`의 `conditions.' + c + '.baseline.errors`에 있다.')
    L += [''] + notes['errors'] + ['', '## 반복 차이', '',
          f'반복 사례 {len(policy["repeats"])}개는 모델 호출 전에 작성자 라벨 분포로 골랐다(`select_repeats.py`). 최종 라벨 기준으로 이 사례들에는 ' + ', '.join(f'{l} {rc.get(l, 0)}셀' for l in a.REL) + (f', 모호 {rc.get("AMBIGUOUS", 0)}셀' if rc.get('AMBIGUOUS') else '') + '이 들어 있다.', '',
          '| 조건 | 회차 | 사례 | 전체 관련 재현율 | R1 | R2 | R3 | R4 | 정밀도 | N 통과율 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in ['F1', 'F2']:
        for r in conds[c]['repeat']:
            b = r['metrics']
            L.append(f'| {c} | {r["repetition"]} | {b["cases"]} | ' + ' | '.join([frac(b['recall_overall'])] + [frac(b['recall'][l]) for l in a.REL] + [frac(b['precision']), frac(b['unrelated_pass_rate'])]) + ' |')
    L += ['', '회차 0은 기본 실행 가운데 같은 사례만 추린 값이다. 차이는 4회 재현율의 최댓값−최솟값이다.', '', '| 조건 | 전체 차이 | R1 차이 | R2 차이 | R3 차이 | R4 차이 |', '|---|---:|---:|---:|---:|---:|']
    for c in ['F1', 'F2']:
        s = conds[c]['repeat_spread']
        L.append('| ' + c + ' | ' + ' | '.join(pp(s.get(l)) for l in ['overall'] + a.REL) + ' |')
    L += [''] + notes['repeats'] + ['', '## 호출당 토큰과 시간', '',
          '기본·추가 반복의 실제 호출 전체를 포함한다. 입력 토큰은 캐시 읽기를 포함한 총 입력이고 CLI의 시스템 지시 등 실행 환경 부담이 들어 있다. 시간은 프로세스 시작부터 끝까지이며 사후 프록시 기록 수집은 뺐다. F1과 F2는 1단계에서 두 갈래로 동시에 돌았고(갈래 안에서는 순차), F3·F4는 2단계에서 한 갈래로 차례로 돌았다.', '',
          '| 조건 | 호출 수 | 평균 입력 | 평균 캐시 입력 | 평균 출력 | 평균 초 | 중앙값 초 | p95 초 | 최소–최대 초 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in ['F0', 'F1', 'F2', 'F3', 'F4a', 'F4b', 'F4c', 'F4z']:
        x = conds[c]
        t = x['time_seconds']
        d = 8 if c == 'F0' else 2
        L.append(f'| {c} | {x["observed_calls"] if c != "F0" else "0 (로컬 91사례)"} | {num(x["tokens_input"]["mean"])} | {num(x["tokens_cached_input"]["mean"])} | {num(x["tokens_output"]["mean"])} | {num(t["mean"], d)} | {num(t["median"], d)} | {num(t["p95"], d)} | {num(t["min"], d)}–{num(t["max"], d)} |')
    co = m['cost']
    S = co['summary']
    L += ['', '## F4: 걸러 읽기와 전체 읽기의 비용 비교', '',
          f'계획 6절의 정의대로 F3·F4 {co["cases"]}사례마다 전체 읽기(F4a)와 걸러 읽기(F1+F4b, F2+F4c)를 나란히 놓았다. 메인 급 한계 입력은 각 호출의 입력 토큰에서 F4z 3회 평균 입력 {num(co["overhead_input_mean"])} 토큰(값: {", ".join(num(v, 0) for v in co["overhead_input_values"])})을 뺀 값이다.', '',
          '| 값 (사례당) | 평균 | 중앙값 | 최소–최대 |', '|---|---:|---:|---:|']
    rows = [('메인 급 한계 입력: 전체 읽기 F4a', 'F4a_marginal'), ('메인 급 한계 입력: F1 결과 읽기 F4b', 'F4b_marginal'), ('메인 급 한계 입력: F2 결과 읽기 F4c', 'F4c_marginal'),
            ('메인 급 총 입력 F4a', 'F4a_input'), ('메인 급 총 입력 F4b', 'F4b_input'), ('메인 급 총 입력 F4c', 'F4c_input'),
            ('메인 급 출력 F4a', 'F4a_output'), ('메인 급 출력 F4b', 'F4b_output'), ('메인 급 출력 F4c', 'F4c_output'),
            ('싼 모델 입력 F1 (haiku)', 'F1_input'), ('싼 모델 출력 F1', 'F1_output'), ('싼 모델 입력 F2 (luna)', 'F2_input'), ('싼 모델 출력 F2', 'F2_output'),
            ('시간: 전체 읽기 F4a 초', 'F4a_seconds'), ('시간: F1 초 + F4b 초', 'path_F1_seconds'), ('시간: F2 초 + F4c 초', 'path_F2_seconds')]
    for label, k in rows:
        s = S.get(k, {})
        L.append(f'| {label} | {num(s.get("mean"))} | {num(s.get("median"))} | {num(s.get("min"))}–{num(s.get("max"))} |')
    L += [''] + notes['cost'] + ['', '## 오류·이상치·미실행', '']
    L += notes['anomalies'] + ['']
    for c in ['F1', 'F2', 'F3']:
        tc = an['title_counts']
        L.append(f'- {c} 전체(기본+반복) 제목 불일치 {tc.get(c + " title mismatch", 0)}건 중 `## ` 접두만 다른 것 {tc.get(c + " title hash-prefix-only", 0)}건.')
    shown = an['items'][:40]
    for x in shown:
        L.append(f'- `{x["run"]}` / {x["id"]}: {", ".join(x["issues"])}. 반환 제목 `{x["title"]}`, 원래 제목 `{x["expected_title"]}`.')
    if len(an['items']) > len(shown):
        L.append(f'- 나머지 {len(an["items"]) - len(shown)}건은 `anomalies.json`에 있다.')
    L += ['', f'미실행: {len(m["missing"])}회, 무효 응답: {len(m["invalid"])}회. ' + ('계획한 모델 호출 425회와 F0 91사례를 모두 채웠다.' if m['complete'] else '계획을 채우지 못했으므로 완료가 아니다. 이름은 `metrics.json`의 `missing`·`invalid`에 있다.'), '']
    L += ['## 이 실험이 말해 주지 않는 것', ''] + notes['limits'] + ['', '## 식별자 차단과 설정 보호', ''] + notes['hygiene'] + ['']
    if scrub:
        L += [f'최종 검사(`python3 deliverables/s12c-board-filter/scrub_check.py`): 검사 파일 {scrub["files_scanned"]}개, 계정 키 옆 UUID {scrub["uuid_next_to_account_key"]}건, 이메일 꼴 문자열 {scrub["email_pattern"]}건, 계정 계열 키 이름 {scrub["account_key_names"]}건, 걸린 파일 {scrub["files_with_hits"]}개.', '']
    if ver:
        L += [f'Codex 설정 해시 비교(`verify_artifacts.py`, 실행 전 `codex-config-hash-before.json`과 실행 후): 바뀐 홈 {len(ver["codex_config_changed"])}개({", ".join(ver["codex_config_changed"]) or "없음"}).', '']
    L += ['## 집계 검증과 재현', '']
    if ver:
        L += [f'`verify_artifacts.py`가 두 번의 고정 해시와 순서, 프롬프트 일치(F4b·F4c는 F1·F2 출력에서 다시 만들어 대조), 계획 호출 수, 라벨 728건, 실제 응답 모델과 대응 프록시 기록, API 키 제거 명령, Codex 설정 해시를 검사했다. 결과는 `artifact-verification.json`의 `verified={ver["verified"]}`, 문제 {len(ver["problems"])}건이다. CLI와 프록시의 토큰 집계 불일치는 {len(ver["cli_proxy_usage_mismatches"])}건이다.', '']
    L += ['저장된 자료만으로 모델 호출 없이 다시 집계하고 이 문서를 만들 수 있다.', '', '```sh', 'python3 deliverables/s12c-board-filter/verify_metrics.py', 'python3 deliverables/s12c-board-filter/verify_artifacts.py',
          'python3 deliverables/s12c-board-filter/scrub_check.py', 'python3 deliverables/s12c-board-filter/write_report.py', '```', '',
          '`verify_metrics.py`는 R2 누락, 인용 변조, 다른 항목 인용, 본문 전체/발췌 구분, 어려운 음성 삽입, 모호 셀 선택, 알 수 없는 ID, 중복 ID를 일부러 넣고 각 지표가 잡는지 보며, 기준 하나씩을 경계 바로 밖으로 옮겨 판정이 미충족으로 바뀌는지도 본다. 결과는 `metrics-verification.txt`에 있다. `build_fixture.py freeze`와 `reconcile.py`는 고정 시각을 다시 쓰므로 보존된 자료 위에서 다시 돌리지 않는다.', '',
          '저장소의 코드와 다른 문서는 고치지 않았다. 이 결과 문서, 계획 문서, 지정한 자료 디렉터리에만 썼다. 커밋·push는 하지 않았다.', '']
    L += ['## 사용자 기준의 기계적 적용', '',
          '기준은 사용자가 2026-10-30에 정한 것이다(`policy.json`의 `criteria`, 필터 호출 전 고정). 네 기준이 모두 성립할 때만 충족이다. 아래는 수치를 기준값에 그대로 대 본 결과이며 그 밖의 권고는 적지 않는다.', '',
          '| 기준 | 기준값 | ' + ' | '.join(f'{c} 측정값 | {c} 판정' for c in m['verdicts']) + ' |', '|---|---|' + '---:|---|' * len(m['verdicts'])]
    keys = [r['criterion'] for r in next(iter(m['verdicts'].values()))['rows']]
    for i, k in enumerate(keys):
        any_row = next(iter(m['verdicts'].values()))['rows'][i]
        th = (pct(any_row['threshold'], 0) if 'spread' not in k else pp(any_row['threshold']))
        cells = []
        for c, v in m['verdicts'].items():
            r = v['rows'][i]
            val = pp(r['value']) if 'spread' in k else pct(r['value'])
            cells.append(f'{val} | {"충족" if r["ok"] else ("측정 안 함" if r["value"] is None and c == "F3" else "미충족")}')
        L.append(f'| {CRIT[k]} | {any_row["op"]} {th} | ' + ' | '.join(cells) + ' |')
    L.append('')
    for c, v in m['verdicts'].items():
        name = {'F1': 'F1 (haiku)', 'F2': 'F2 (luna)', 'F3': 'F3 (sol, 참고)'}[c]
        g = v['groups']
        bad = [n for n, k in [('재현율', 'recall'), ('정밀도', 'precision'), ('반복 차이', 'repeat_spread'), ('인용 충실도', 'quote')] if not g[k]]
        if v['met'] is None:
            L.append(f'- {name}: **판정 불가.** 반복을 돌리지 않아 반복 차이를 재지 않았다(계획 2절). 나머지 세 기준: ' + ', '.join(f'{n} {"충족" if g[k] else "미충족"}' for n, k in [('재현율', 'recall'), ('정밀도', 'precision'), ('인용 충실도', 'quote')]) + '.')
        else:
            L.append(f'- {name}: **{"기준 충족" if v["met"] else "기준 미충족"}.** ' + ('네 기준 모두 성립.' if v['met'] else '못 미친 기준: ' + ', '.join(bad) + '.'))
    DEST.write_text('\n'.join(L) + '\n')
    print('report:', DEST)


if __name__ == '__main__':
    report()
