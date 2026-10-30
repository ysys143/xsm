"""Render Markdown strictly from saved measurements; no inference."""
import collections
import datetime as dt
import json
from pathlib import Path
import aggregate as a
from diagnose_outputs import diagnose

ROOT=a.ROOT
DEST=ROOT.parents[1]/'docs/spikes/S12-results.md'

def frac(x):
    return f'{100*x["value"]:.1f}% ({x["numerator"]}/{x["denominator"]})' if x['value'] is not None else 'NA (0건)'
def num(x,d=1):return f'{x:,.{d}f}' if x is not None else 'NA'

def report():
    m=a.aggregate();anomalies=diagnose();freeze=a.read(ROOT/'freeze-evaluation.json');inputs=a.read(ROOT/'freeze-inputs.json');policy=a.read(ROOT/'policy.json')
    conds=m['conditions'];complete=m['complete']
    lines=['# S12 결과: 싼 모델이 보드 변경을 걸러 읽을 수 있는가','',f'- 상태: {"계획한 실행 및 집계 완료" if complete else "미완 — 계획한 호출 수 미충족"}',f'- 실행일: 2026-10-30 (KST). 보고서 생성: {dt.datetime.now(dt.timezone.utc).isoformat()}','- 원본 계획: [S12-board-filter-plan.md](S12-board-filter-plan.md)','- 자료·스크립트·원시 응답: [deliverables/s12-board-filter](../../deliverables/s12-board-filter/)','']
    if complete:
        f1=conds['F1'];f2=conds['F2']
        lines += [f'이 합성 표본에서 haiku의 R2 재현율은 {frac(f1["baseline"]["recall"]["R2"])}이고 R3는 {frac(f1["baseline"]["recall"]["R3"])}였다. luna의 R2는 {frac(f2["baseline"]["recall"]["R2"])}이고 R3는 {frac(f2["baseline"]["recall"]["R3"])}였다. 아래 반복 변동과 토큰·시간을 함께 봐야 한다.','']
    lines += ['## 고정 자료와 라벨','',f'합성 보드 32개 항목, 세션 4개, 독립 변경 묶음 10개(묶음당 8개 항목)로 구성했다. 기본 실행은 조건당 40사례, 320개 변경 판정이다. 묶음은 같은 초기 보드에 대한 독립 diff이며 순차 누적 이력이 아니다.','',f'입력·작성자 라벨·판정 정책은 **{inputs["frozen_at"]}** 에 먼저 고정했다. 별도 Claude 실행은 첫 라벨 없이 세션 설명·변경·분류 규칙만 받았고 도구 목록은 비웠다. 실제 독립 라벨러는 `claude-opus-5-5`였다. 관련 셀을 열거하고 생략 셀을 N으로 처리하는 방식으로 전체 320건을 비교했다.', '', f'라벨 불일치: **{m["label_disagreements"]}/320건**, 모호: **{m["label_counts"].get("AMBIGUOUS",0)}건**. 최종 라벨 수는 '+', '.join(f'{l} {m["label_counts"].get(l,0)}건' for l in ['R1','R2','R3','R4','N'])+'이다.', '',f'필터 호출 전 **{freeze["frozen_at"]}** 에 최종 라벨, 40개 프롬프트, 판정 정책, 최초 실행 스크립트의 SHA-256을 다시 고정했다. 원시 해시는 `freeze-inputs.json`과 `freeze-evaluation.json`에 전부 있다. 집계 시 고정 파일 검증 결과는 `{m["freeze_verified"]}`다. 결과를 본 뒤 라벨이나 판정 기준은 바꾸지 않았다.','']
    lines += ['| 고정 파일 | SHA-256 |','|---|---|']
    for f in ['BOARD.md','fixture.json','labels-author.json','labels-final.json','policy.json','filter-prompt.txt']:
        lines.append(f'| `{f}` | `{freeze["sha256"][f]}` |')
    lines += ['','## 실행 수와 실제 모델','', '| 조건 | 기본 사례 / 계획 | 추가 반복 / 계획 | 모델 호출 / 계획 | 로그에서 확인한 실제 응답 모델 |','|---|---:|---:|---:|---|']
    for c,x in conds.items():
        lines.append(f'| {c} | {x["observed_baseline"]}/{x["expected_baseline"]} | {x["observed_calls"]-x["observed_baseline"] if c!="F0" else 0}/{30 if c in ["F1","F2"] else 0} | {x["observed_calls"]}/{x["expected_calls"]} | '+(', '.join('`'+v+'`' for v in x['actual_models']) if c!='F0' else '모델 없음')+' |')
    lines += ['',f'모델 필터 호출 합계: **{m["observed_model_calls"]}/{m["planned_model_calls"]}회**. 별도 독립 라벨링 1회는 이 분모에 포함하지 않는다. F3는 사전 선택한 B01·B05·B10의 3묶음, 각 4세션에만 실행했다. F1·F2 반복은 `policy.json`에 고정한 묶음당 1사례씩 총 10사례를 3회 더 실행했다.','', 'F1은 `claude -p --model haiku`, F2는 `codex exec --model openai/gpt-6-luna`로 실행했다. F3는 현재 세션과 같은 모델 계열인 `gpt-6.1-sol`을 지정했다. Codex 호출의 reasoning effort는 F2·F3 모두 `low`로 고정했으므로 F3는 같은 effort에서의 모델 참고값이다. 높은 effort까지 포함한 성능 상한을 측정한 것은 아니다. F1의 생각 토큰과 Codex 출력 토큰은 각 CLI가 보고한 사용량에 포함된다.','', 'F1은 응답 이벤트의 `message.model`, F2·F3는 ocx의 해당 대화 `requestedModel`·`resolvedModel`·`servedModel`로 확인했다. ocx의 대화 ID가 `sha256(thread-id)[:32]`라는 구현을 확인하여 다른 세션이나 S11 요청과 분리했다. 검증된 메타데이터는 `runs/*.verified.json`, 대응 프록시 원문은 `*.proxy-verified.json`에 있다.','', 'Claude 인증 조회는 `authMethod=claude.ai`, `subscriptionType=max`, `apiProvider=firstParty`였고 Codex의 저장된 인증 유형은 `chatgpt`, API 키 없음이었다. 호출 환경에서 `ANTHROPIC_API_KEY`와 `OPENAI_API_KEY`를 제거했으며 키 값을 조회하지 않았다. 사용자·프록시 설정 파일은 변경하지 않았다. F1과 F2는 각 조건 내 순차 실행, 두 조건 사이에는 최대 2개 호출이 겹칠 수 있었다. F3는 그 뒤 실행했다.','']
    lines += ['## 재현율·정밀도·인용','', '기본 40사례만의 결과다. F3는 12사례다. 반복 호출은 아래에서 별도로 집계한다. 정밀도는 TP/(TP+FP), 무관 통과율은 FP_N/N이다. 계획서의 정밀도 설명이 무관 통과율을 가리켜 두 값을 모두 기록했다.','', '| 조건 | R1 직접 | R2 겹침 | R3 전제 | R4 자원 | 전체 관련 재현율 | 정밀도 | N 통과율 | 인용 충실도 |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c,x in conds.items():
        b=x['baseline'];lines.append('| '+c+' | '+' | '.join([frac(b['recall'][l]) for l in ['R1','R2','R3','R4']]+[frac(b['recall_overall']),frac(b['precision']),frac(b['unrelated_pass_rate']),frac(b['quote_fidelity'])])+' |')
    lines += ['', '인용 충실도는 반환한 각 항목의 인용이 **그 항목의 변경 후 본문에 글자 그대로 포함되는 비어 있지 않은 연속 문자열**인지 검사한다. 다른 항목에서 가져온 인용은 불충실로 센다. 제목 불일치·중복 ID·알 수 없는 ID도 별도 검사한다.', '', '| 조건 | 제목 불일치 | 중복 ID | 알 수 없는 ID | 모호 항목 선택 |','|---|---:|---:|---:|---:|']
    for c,x in conds.items():
        b=x['baseline'];lines.append(f'| {c} | {b["title_mismatches"]} | {b["duplicates"]} | {b["invalid_ids"]} | {b["ambiguous_selected"]} |')
    lines += ['', 'F0는 세션 이름·담당 항목·파일 경로의 문자열 일치만 사용한다. 자원 이름을 추가하지 않았기 때문에 이 자료의 R4를 잡지 못했다. 이는 계획된 F0 정의에서 생긴 결과이며, 자원 이름까지 등록한 다른 기계적 필터의 성능은 측정하지 않았다. F0의 인용은 선택한 원문 본문 자체다.','', '## 반복 차이','', '| 조건 | 회차 | 사례 | 전체 관련 재현율 | R1 | R2 | R3 | R4 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for c in ['F1','F2']:
        for r in conds[c]['repeat']:
            b=r['metrics'];lines.append(f'| {c} | {r["repetition"]} | {b["cases"]} | '+ ' | '.join([frac(b['recall_overall'])]+[frac(b['recall'][l]) for l in ['R1','R2','R3','R4']])+' |')
    lines += ['', '회차 0은 기본 실행 중 동일한 10사례만 추린 값이다. 차이는 4회 재현율의 최댓값−최솟값이며, 분모가 없는 라벨은 NA다.','', '| 조건 | 전체 차이 | R1 차이 | R2 차이 | R3 차이 | R4 차이 |','|---|---:|---:|---:|---:|---:|']
    for c in ['F1','F2']:
        s=conds[c]['repeat_spread'];lines.append('| '+c+' | '+' | '.join(num(s.get(l)*100,1)+'%p' if s.get(l) is not None else 'NA' for l in ['overall','R1','R2','R3','R4'])+' |')
    lines += ['', '## 호출당 토큰과 시간','', '기본·추가 반복의 실제 호출 전체를 포함한다. 입력 토큰은 캐시 읽기와 생성을 포함한 총 입력이며, 순수 사용자 프롬프트 토큰만의 값이 아니다. CLI의 시스템 지시·스킬 등 실행 환경 부담이 포함된다. 출력은 CLI의 보고값을 사용했다. 시간은 프로세스 시작부터 종료까지이며 사후 프록시 로그 수집 시간은 제외한다. 캐시와 두 조건의 동시 실행, 공유 프록시의 다른 작업이 지연에 영향을 줄 수 있다.','', '| 조건 | 호출 수 | 평균 입력 | 평균 캐시 입력 읽기 | 평균 출력 | 평균 초 | 중앙값 초 | p95 초 | 최소–최대 초 |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c,x in conds.items():
        t=x['time_seconds'];d=8 if c=='F0' else 4
        lines.append(f'| {c} | {x["observed_calls"] if c!="F0" else "0 (로컬 40사례)"} | {num(x["tokens_input"]["mean"])} | {num(x.get("tokens_cached_input",{}).get("mean",0))} | {num(x["tokens_output"]["mean"])} | {num(t["mean"],d)} | {num(t["median"],d)} | {num(t["p95"],d)} | {num(t["min"],d)}–{num(t["max"],d)} |')
    lines += ['', '호출별 값은 `metrics.json`의 `calls`에 있으며, 각각 원시 응답·CLI 사용량·실제 모델 기록과 연결된다. F0 시간은 문자열 필터의 Python 실행 시간만이다. Claude가 로그에 표시한 목록가 기반 `costUSD`는 구독 추가 청구액으로 해석하지 않았다.','', '## 오류·이상치·미실행','', '처음 F2 호출이 끝난 뒤 로그 수집기가 UUID의 하이픈만 제거해 비교하여 실제 모델을 찾지 못했다. 즉시 추가 호출을 중단했다. `STOP.json`, 최초 `*.meta.json`과 빈 `*.proxy.json`을 보존했다. ocx 구현을 읽고 올바른 해시로 **같은 호출**의 로그를 다시 연결하자 `servedModel=gpt-6-luna`가 확인됐다. 모델 불일치나 대체 모델 호출은 없었으며 추론을 재실행하지 않았다. 최초 러너와 고정 해시는 그대로 두고 `run_verified.py`로 검증된 기록을 추가했다. 이 수집기 수정은 라벨·프롬프트·판정 기준을 바꾸지 않았다.','', 'MCP의 ack/send는 현재 세션 hook record를 찾지 못해 실패했다. 제한 없는 셸에서 CLI 경로로 수신 확인과 통신을 복구했다. 원래 claim 만료 후 inbox에서 재수신·ack했으며 같은 작업을 중복 실행하지 않았다.','']
    for c in ['F1','F2','F3']:
        x=conds[c]
        for err in x['baseline']['errors']:
            lines.append(f'- {c} 기본 {err["case"]} {err["item"]}: {err["type"]}, 정답 {err["gold"]}. 원문: “{err["text"]}”')
    if not any(conds[c]['baseline']['errors'] for c in ['F1','F2','F3']):lines.append('- 모델 기본 실행에서 누락·과잉 선택 없음.')
    lines += ['', '추가 반복의 누락·과잉 선택은 `metrics.json`의 `conditions.*.repeat.*.metrics.errors`에 보존했다. 지연 최댓값 및 각 호출의 원시 출력도 제거하지 않았다.','',f'미실행: {len(m["missing"])}회. '+('계획된 모델 호출 152회와 F0 40사례를 모두 채웠다.' if complete else '계획을 충족하지 못했으므로 완료가 아니다. 남은 ID는 metrics.json의 missing 배열을 따른다.'),'', '## 제안 기준과 해석','', '**R2·R3 재현율 90%, 인용 충실도 95%, 반복 차이 10%p는 계획 작성자의 제안값이며 사용자가 정한 값이 아니다.** 라벨별·전체 반복 차이 중 어느 것이든 10%p를 넘으면 계획에 따라 해당 모델에 대한 권장 결론을 보류한다.','']
    anomaly_lines=['', '제목의 글자 단위 불일치 중에는 Markdown `## `를 붙인 형식 차이가 포함된다. 전체 기본·반복 호출에서 형식 차이만 있는 건수와 원문 변조는 `anomalies.json`에 구분했다. 이 사후 진단은 점수나 기준을 바꾸지 않는다.','']
    for c in ['F1','F2','F3']:
        counts=anomalies['title_counts'];anomaly_lines.append(f'- {c} 전체 제목 불일치 {counts.get(c+" title exact mismatch",0)}건 중 `## ` 형식 차이만 {counts.get(c+" title hash-prefix-only",0)}건.')
    for x in anomalies['items']:
        item=x['item'];expected=x['expected'];anomaly_lines.append(f'- `{x["run"]}` / {item["id"]}: '+', '.join(x['issues'])+f'. 반환 제목 “{item.get("title")}”, 원래 제목 “{expected.get("title") if expected else None}”. 반환 인용 “{item.get("quote")}”, 원문 “{expected.get("after") if expected else None}”.')
    anomaly_lines.append('')
    insert=lines.index('## 제안 기준과 해석');lines[insert:insert]=anomaly_lines
    for c in ['F1','F2']:
        x=conds[c];b=x['baseline'];ready=x['observed_calls']==x['expected_calls'];r2=b['recall']['R2']['value'];r3=b['recall']['R3']['value'];q=b['quote_fidelity']['value'];spread=x['repeat_spread'];stable=bool(spread) and all(v is not None and v<=.1+1e-12 for v in spread.values())
        qualifies=ready and r2 is not None and r3 is not None and q is not None and r2>=.9 and r3>=.9 and q>=.95 and stable
        lines.append(f'- {c}: '+('이 표본에서는 제안 기준을 충족했다.' if qualifies else '제안 기준을 모두 충족했다고 결론 내리지 않는다.')+f' R2 {num(r2*100) if r2 is not None else "NA"}%, R3 {num(r3*100) if r3 is not None else "NA"}%, 인용 {num(q*100) if q is not None else "NA"}%, 반복 안정 조건 {stable}.')
    lines += ['', '이 자료는 작업 영역이 네 개로 뚜렷하고 대부분의 관련 변경을 영역당 두 개씩 배치한 합성 표본이다. 은어·대명사·간접 일정 의존·정반대 의미의 무관 문장 같은 어려운 음성 사례는 충분히 포함하지 않았다. 라벨러 둘은 독립 실행했지만 하나는 자료를 만든 세션, 다른 하나는 모델이라 사람 정답을 대신하지 않는다. 따라서 실제 장기 세션에서 조용한 누락이 안전한지까지 보증할 수 없다.','', 'Q1은 위 라벨별 재현율과 반복 차이, Q2는 인용 일치율, Q3는 F0 비교, Q4는 호출별 토큰·시간으로 답했다. 필터 결과를 받은 메인 세션의 행동, 실제 세션 문맥 전달량, 대형 보드·실제 변경 빈도의 누적 비용은 측정 범위 밖이다.','', '## 집계 검증과 재현','', '저장된 자료만으로 아래 명령을 실행하면 모델 호출 없이 재집계와 보고서 생성이 가능하다.','', '```sh','python3 deliverables/s12-board-filter/verify_metrics.py','python3 deliverables/s12-board-filter/write_report.py','```','', '`verify_metrics.py`는 R2 누락, 원문 인용 변조, 무관 항목 삽입, 알 수 없는 ID, 중복 ID를 일부러 주입하고 각 지표가 이를 탐지하는지 검사한다. 결과는 `metrics-verification.txt`에 있다. `build_fixture.py`는 자료의 생성 원본이며, 실행하면 고정 시각을 다시 쓰므로 보존된 고정 자료에 덮어 실행하지 않는다.','', '기존 저장소 코드·문서는 수정하지 않았으며 결과 문서 하나와 지정한 원시 자료 디렉터리에만 산출물을 추가했다. 커밋·push는 하지 않았다.']
    verification=ROOT/'artifact-verification.json'
    trustcheck=ROOT/'codex-trust-side-effect-check.json'
    if trustcheck.exists():
        check=a.read(trustcheck)
        pos=lines.index('## 오류·이상치·미실행')+2
        lines[pos:pos]=['위임 세션이 S11에서 관측한 Codex의 trust 블록 자동 기록을 알려와, 종료 후 세 Codex 홈의 `config.toml` 프로젝트 키를 읽기 전용으로 조사했다. '+', '.join(f'{x["home"]}: S12 경로 블록 {x["s12_projects_count"]}개' for x in check['homes'])+'였다. 설정 복원이나 수정은 하지 않았다. 증거는 `codex-trust-side-effect-check.json`에 있다. 실행 전후 전체 설정 파일 해시를 비교한 검증은 아니다.','']
    if verification.exists():
        v=a.read(verification)
        pos=lines.index('## 집계 검증과 재현')+2
        lines[pos:pos]=[f'`verify_artifacts.py`가 고정 해시, 고정 전후 시각, 프롬프트 일치, 계획 호출 수 70·70·12, 라벨 320건, 실제 응답 모델과 대응 프록시 로그를 검증했다. 결과는 `artifact-verification.json`의 `verified={v["verified"]}`다. CLI와 프록시 토큰 집계 불일치는 {len(v["cli_proxy_usage_mismatches"])}건이었다.','']
        command=lines.index('python3 deliverables/s12-board-filter/verify_metrics.py')
        lines.insert(command+1,'python3 deliverables/s12-board-filter/verify_artifacts.py')
    DEST.write_text('\n'.join(lines)+'\n');print('report:',DEST)

if __name__=='__main__':report()
