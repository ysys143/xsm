"""Render docs/spikes/S12b-results.md from saved measurements; no inference.

Interpretive prose lives in report-notes.json (written after the numbers were seen) and is inserted verbatim.
"""
import collections
import datetime as dt
import json
import aggregate as a

ROOT = a.ROOT
DEST = ROOT.parents[1] / 'docs/spikes/S12b-results.md'
NAMES = {'R1': 'R1 직접', 'R2': 'R2 겹침', 'R3': 'R3 전제', 'R4': 'R4 자원'}


def frac(x):
    return f'{100 * x["value"]:.1f}% ({x["numerator"]}/{x["denominator"]})' if x['value'] is not None else 'NA (0건)'


def num(x, d=1):
    return f'{x:,.{d}f}' if x is not None else 'NA'


def anomalies():
    fixture = a.read(ROOT / 'fixture.json')
    entries = {e['id']: e for b in fixture['batches'] for e in b['entries']}
    counts = collections.Counter()
    items = []
    for f in sorted(a.RUNS.glob('F*.meta.json')):
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
                items.append(dict(run=f.name.replace('.meta.json', ''), id=it.get('id'), issues=issues, title=it.get('title'), quote=it.get('quote'),
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
    ver = a.read(ROOT / 'artifact-verification.json') if (ROOT / 'artifact-verification.json').exists() else None
    scrub = a.read(ROOT / 'scrub-check.json') if (ROOT / 'scrub-check.json').exists() else None
    conds = m['conditions']
    lc = m['label_counts']
    L = ['# S12b 결과: 어려운 표본에서도 싼 모델이 보드 변경을 걸러 읽는가', '',
         f'- 상태: {"계획한 실행 및 집계 완료" if m["complete"] else "미완: 계획한 호출 수 미충족"}',
         f'- 실행일: 2026-10-30 (KST). 보고서 생성: {dt.datetime.now(dt.timezone.utc).isoformat()}',
         '- 원본 계획: [S12b-hard-sample-plan.md](S12b-hard-sample-plan.md). 비교 대상: [S12-results.md](S12-results.md)',
         '- 자료·스크립트·응답: [deliverables/s12b-hard-sample](../../deliverables/s12b-hard-sample/)', '']
    L += notes['headline'] + ['']
    L += ['## 고정 자료와 라벨', '',
          '세션 5개, 독립 변경 묶음 10개(묶음당 8개 항목), 항목 80개로 구성했다. 기본 실행은 조건당 50사례, 400개 변경 판정이다. 묶음은 같은 초기 보드에 대한 독립 diff다.', '']
    L += notes['fixture'] + ['']
    L += [f'입력·작성자 라벨·판정 정책은 **{inputs["frozen_at"]}** 에 먼저 고정했다. 그 뒤 별도 `claude -p --model opus` 실행(도구 목록 비움, MCP 없음)이 작성자 라벨과 숨은 전제 메모 없이 세션 설명·변경·라벨 규칙만 받아 독립 라벨을 달았다. 실제 응답 모델은 `claude-opus-5-5`였다. 관련 셀을 열거하고 생략 셀을 N으로 보는 방식으로 400건 전체를 비교했다.', '',
          f'라벨 불일치: **{m["label_disagreements"]}/400건**. 최종 라벨 수는 ' + ', '.join(f'{l} {lc.get(l, 0)}건' for l in ['R1', 'R2', 'R3', 'R4', 'N']) + f', 모호 {lc.get("AMBIGUOUS", 0)}건이다. 작성자가 어려운 음성으로 표시한 N 셀은 {m["hard_negative_cells"]}건, 세션의 구별 단어를 포함하는 N 셀(의도하지 않은 것 포함)은 {m["lexical_negative_cells"]}건이다.', '']
    L += notes['disagreements'] + ['']
    L += [f'필터 호출 전 **{freeze["frozen_at"]}** 에 최종 라벨, 50개 프롬프트, 판정 정책, 실행 스크립트의 SHA-256을 다시 고정했다. 집계 시 고정 파일 검증 결과는 `{m["freeze_verified"]}`다. 결과를 본 뒤 라벨이나 판정 기준은 바꾸지 않았다.', '',
          '| 고정 파일 | SHA-256 |', '|---|---|']
    for f in ['BOARD.md', 'fixture.json', 'labels-author.json', 'labels-final.json', 'policy.json', 'filter-prompt.txt']:
        L.append(f'| `{f}` | `{freeze["sha256"][f]}` |')
    L += ['', '## 실행 수와 실제 모델', '', '| 조건 | 기본 사례 / 계획 | 추가 반복 / 계획 | 모델 호출 / 계획 | 로그에서 확인한 실제 응답 모델 |', '|---|---:|---:|---:|---|']
    for c, x in conds.items():
        extra_plan = 30 if c in ['F1', 'F2'] else 0
        L.append(f'| {c} | {x["observed_baseline"]}/{x["expected_baseline"]} | {x["observed_calls"] - x["observed_baseline"] if c != "F0" else 0}/{extra_plan} | {x["observed_calls"]}/{x["expected_calls"]} | '
                 + (', '.join(f'`{v}`' for v in x['actual_models']) if c != 'F0' else '모델 없음') + ' |')
    L += ['', f'모델 필터 호출 합계: **{m["observed_model_calls"]}/{m["planned_model_calls"]}회**. 독립 라벨링 1회는 이 분모에 넣지 않는다. F3는 사전 선택한 B01·B05·B10의 3묶음, 각 5세션에만 실행했다. F1·F2 반복은 `policy.json`에 고정한 묶음당 1사례씩 10사례를 3회 더 실행했다.', '']
    L += notes['runtime'] + ['']
    L += ['## 재현율·정밀도·인용', '',
          '기본 50사례의 결과다(F3는 15사례). 반복 호출은 아래에서 따로 집계한다. 정밀도는 TP/(TP+FP), N 통과율은 FP_N/N이다. 어려운 음성 통과율은 작성자가 표시한 어려운 음성 N 셀 중 고른 비율, 단어 겹침 N 통과율은 세션의 구별 단어를 포함한 N 셀 중 고른 비율이다. 모호 셀은 분모에서 뺐다.', '',
          '| 조건 | R1 직접 | R2 겹침 | R3 전제 | R4 자원 | 전체 관련 재현율 | 정밀도 | N 통과율 | 어려운 음성 통과율 | 단어 겹침 N 통과율 | 인용 충실도 |',
          '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c, x in conds.items():
        b = x['baseline']
        L.append('| ' + c + ' | ' + ' | '.join([frac(b['recall'][l]) for l in a.REL] + [frac(b[k]) for k in ['recall_overall', 'precision', 'unrelated_pass_rate', 'hard_negative_pass_rate', 'lexical_negative_pass_rate', 'quote_fidelity']]) + ' |')
    L += ['', '인용 충실도는 반환한 인용이 **그 항목의 변경 후 본문에 글자 그대로 들어 있는 비어 있지 않은 연속 문자열**인지 본다(S12와 같다). 다른 항목에서 가져온 인용은 불충실로 센다.', '',
          '| 조건 | 제목 불일치 | 중복 ID | 알 수 없는 ID | 모호 셀 선택 / 모호 셀 | 충실 인용의 본문 대비 길이 중앙값 |', '|---|---:|---:|---:|---:|---:|']
    for c, x in conds.items():
        b = x['baseline']
        L.append(f'| {c} | {b["title_mismatches"]} | {b["duplicates"]} | {b["invalid_ids"]} | {b["ambiguous_selected"]}/{b["ambiguous_cells"]} | {num(100 * b["quote_share_of_item"]["median"], 1) + "%" if b["quote_share_of_item"]["median"] is not None else "NA"} |')
    L += [''] + notes['f0'] + ['', '## 놓친 것과 잘못 고른 것 (기본 실행)', '']
    fixture = a.read(ROOT / 'fixture.json')
    entries = {e['id']: e for bb in fixture['batches'] for e in bb['entries']}
    for c in ['F1', 'F2', 'F3']:
        errs = conds[c]['baseline']['errors']
        fn = [e for e in errs if e['type'] == 'false_negative']
        fp = [e for e in errs if e['type'] == 'false_positive']
        L.append(f'- {c}: 누락 {len(fn)}건, 과잉 선택 {len(fp)}건.')
        for e in fn:
            L.append(f'  - 누락 {e["case"]} {e["item"]} (정답 {e["gold"]}, 제목 `{entries[e["item"]]["title"]}`)')
        for e in fp:
            tag = '어려운 음성' if e.get('hard_negative') else ('단어 겹침' if e.get('lexical_overlap') else '일반 N')
            L.append(f'  - 과잉 {e["case"]} {e["item"]} (정답 {e["gold"]}, {tag}, 제목 `{entries.get(e["item"], {}).get("title")}`)')
    L += [''] + notes['errors'] + ['', '## 반복 차이', '', '| 조건 | 회차 | 사례 | 전체 관련 재현율 | R1 | R2 | R3 | R4 | N 통과율 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in ['F1', 'F2']:
        for r in conds[c]['repeat']:
            b = r['metrics']
            L.append(f'| {c} | {r["repetition"]} | {b["cases"]} | ' + ' | '.join([frac(b['recall_overall'])] + [frac(b['recall'][l]) for l in a.REL] + [frac(b['unrelated_pass_rate'])]) + ' |')
    L += ['', '회차 0은 기본 실행 가운데 같은 10사례만 추린 값이다. 차이는 4회 재현율의 최댓값−최솟값이다.', '', '| 조건 | 전체 차이 | R1 차이 | R2 차이 | R3 차이 | R4 차이 |', '|---|---:|---:|---:|---:|---:|']
    for c in ['F1', 'F2']:
        s = conds[c]['repeat_spread']
        L.append('| ' + c + ' | ' + ' | '.join(num(s[l] * 100, 1) + '%p' if s.get(l) is not None else 'NA' for l in ['overall'] + a.REL) + ' |')
    L += ['', '## 호출당 토큰과 시간', '',
          '기본·추가 반복의 실제 호출 전체를 포함한다. 입력 토큰은 캐시 읽기와 생성을 포함한 총 입력이고, CLI의 시스템 지시 등 실행 환경 부담이 들어 있다. 시간은 프로세스 시작부터 끝까지이며 사후 프록시 로그 수집은 뺐다. F1과 F2는 동시에 돌았고(조건 안에서는 순차), F3는 그 뒤에 돌았다. 공유 프록시의 다른 작업이 지연에 영향을 줄 수 있다.', '',
          '| 조건 | 호출 수 | 평균 입력 | 평균 캐시 입력 읽기 | 평균 출력 | 평균 초 | 중앙값 초 | p95 초 | 최소–최대 초 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c, x in conds.items():
        t = x['time_seconds']
        d = 8 if c == 'F0' else 2
        L.append(f'| {c} | {x["observed_calls"] if c != "F0" else "0 (로컬 50사례)"} | {num(x["tokens_input"]["mean"])} | {num(x["tokens_cached_input"]["mean"])} | {num(x["tokens_output"]["mean"])} | {num(t["mean"], d)} | {num(t["median"], d)} | {num(t["p95"], d)} | {num(t["min"], d)}–{num(t["max"], d)} |')
    L += ['', '## 오류·이상치·미실행', '']
    L += notes['anomalies'] + ['']
    for c in ['F1', 'F2', 'F3']:
        tc = an['title_counts']
        L.append(f'- {c} 전체(기본+반복) 제목 불일치 {tc.get(c + " title mismatch", 0)}건 중 `## ` 접두만 다른 것 {tc.get(c + " title hash-prefix-only", 0)}건.')
    for x in an['items']:
        L.append(f'- `{x["run"]}` / {x["id"]}: {", ".join(x["issues"])}. 반환 제목 `{x["title"]}`, 원래 제목 `{x["expected_title"]}`.')
    L += ['', f'미실행: {len(m["missing"])}회, 무효 응답: {len(m["invalid"])}회. ' + ('계획한 모델 호출과 F0 50사례를 모두 채웠다.' if m['complete'] else '계획을 채우지 못했으므로 완료가 아니다. 이름은 `metrics.json`의 `missing`·`invalid`에 있다.'), '']
    L += ['## 제안 기준과의 비교', '', '**R2·R3 재현율 90%, 인용 충실도 95%, 반복 차이 10%p는 S12에서 가져온 계획 작성자의 제안값이며 사용자가 정한 값이 아니다.** 아래는 측정값을 제안값과 나란히 놓은 것일 뿐 판정이 아니다. 걸러 읽기를 스킬에 권장할지(D32)와 실제 기준은 사용자가 정한다.', '',
          '| 조건 | R2 재현율 | R3 재현율 | 인용 충실도 | 최대 반복 차이 | 제안값과 비교 |', '|---|---:|---:|---:|---:|---|']
    for c in ['F1', 'F2']:
        x = conds[c]
        b = x['baseline']
        r2, r3, q = b['recall']['R2']['value'], b['recall']['R3']['value'], b['quote_fidelity']['value']
        sp = [v for v in x['repeat_spread'].values() if v is not None]
        mx = max(sp) if sp else None
        below = [n for n, v, th, up in [('R2', r2, .9, False), ('R3', r3, .9, False), ('인용', q, .95, False), ('반복 차이', mx, .1, True)]
                 if v is None or (v > th + 1e-12 if up else v < th - 1e-12)]
        L.append(f'| {c} | {num(100 * r2)}% | {num(100 * r3)}% | {num(100 * q)}% | {num(100 * mx) if mx is not None else "NA"}%p | ' + ('모두 제안값 안' if not below else '제안값 밖: ' + ', '.join(below)) + ' |')
    L += [''] + notes['interpretation'] + ['', '## 이 실험이 말해 주지 않는 것', ''] + notes['limits'] + ['', '## 식별자 차단과 설정 보호', ''] + notes['hygiene'] + ['']
    if scrub:
        L += [f'최종 검사(`python3 deliverables/s12b-hard-sample/scrub_check.py`): 검사 파일 {scrub["files_scanned"]}개, 계정 키 옆 UUID {scrub["uuid_next_to_account_key"]}건, 이메일 꼴 문자열 {scrub["email_pattern"]}건, 계정 계열 키 이름 {scrub["account_key_names"]}건.', '']
    if ver:
        L += [f'Codex 설정 해시 비교: 바뀐 홈 {len(ver["codex_config_changed"])}개({", ".join(ver["codex_config_changed"]) or "없음"}).', '']
    L += ['## 집계 검증과 재현', '']
    if ver:
        L += [f'`verify_artifacts.py`가 두 번의 고정 해시와 순서, 프롬프트 일치, 계획 호출 수, 라벨 400건, 실제 응답 모델과 대응 프록시 기록, API 키 제거 명령, Codex 설정 해시를 검사했다. 결과는 `artifact-verification.json`의 `verified={ver["verified"]}`, 문제 {len(ver["problems"])}건이다. CLI와 프록시의 토큰 집계 불일치는 {len(ver["cli_proxy_usage_mismatches"])}건이었다.', '']
    L += ['저장된 자료만으로 모델 호출 없이 다시 집계하고 이 문서를 만들 수 있다.', '', '```sh', 'python3 deliverables/s12b-hard-sample/verify_metrics.py', 'python3 deliverables/s12b-hard-sample/verify_artifacts.py',
          'python3 deliverables/s12b-hard-sample/scrub_check.py', 'python3 deliverables/s12b-hard-sample/write_report.py', '```', '',
          '`verify_metrics.py`는 R2 누락, 인용 변조, 다른 항목 인용, 어려운 음성 삽입, 모호 셀 선택, 알 수 없는 ID, 중복 ID를 일부러 넣고 각 지표가 잡는지 본다. 결과는 `metrics-verification.txt`에 있다. `build_fixture.py freeze`와 `reconcile.py`는 고정 시각을 다시 쓰므로 보존된 자료 위에서 다시 돌리지 않는다.', '',
          '저장소의 코드와 다른 문서는 고치지 않았다. 이 결과 문서, 계획 문서, 지정한 자료 디렉터리에만 썼다. 커밋·push는 하지 않았다.']
    DEST.write_text('\n'.join(L) + '\n')
    print('report:', DEST)


if __name__ == '__main__':
    report()
