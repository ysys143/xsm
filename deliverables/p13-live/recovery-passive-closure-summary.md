# A16-05 / A18-06 / A22-03 증거 종결 대조

원 plan의 criterion/positive/negative를 먼저 읽고 기존 postclaims·different-parent·N:N·fixture/process/raw를 대조했다. 새 성공을 반복하지 않고 실제 누락만 **새 native pair 2개(총 actor invocation 4회)**로 보완했다. 자동 actor/model 재시도·새 UI·권한 보정·수동 body/ACK/index 수정은 0이다. 제품 source1697·plan·completion ledger와 기존 산출물은 수정하지 않았다.

| 조건 | 판정 | 근거와 남긴 범위 |
|---|---|---|
| A16-05 | **기존 실제 실행 범위 충족, drift 한계 유지** | 현재 315 고정본 different-parent의 실제 auto→MCP-inbox 하향·미독 안내·cached tools/list 기반 inbox 회수/ACK를 wire로 재결속. native 추가 실행 없음 |
| A18-06 | **새 자연 tool 소비 범위 충족, drift 한계 유지** | 실제 note 1건 wake=never 저장, queued/wake 없음. 별도 계산을 이어간 receiver가 자연 선택한 list 안내→inbox 본문 읽기→ACK. 비관련 MCP 응답의 암묵적 body 첨부라고 확대하지 않음 |
| A22-03 | **partial** | 기존 정상 다회 검토 + 새 strict pair의 정상 1건→동일 본문 held→상태조회→원 ID 재전송/실제 final/ACK는 검증. 원 positive의 **다회 수정과 반복을 같은 조건**에서 대조한 한 trace로 합치지 않음 |

공유 MCP는 이 세 조건의 원 요구가 아니며 실제 공유 MCP를 만들거나 성공했다고 표시하지 않았다. 모든 하네스 조합·장시간 부하·유료 flood를 새 요구로 추가하지 않았다.

## 원문 기준과 SHA

[원 plan](../../docs/plan/reason-inspired-adrs/plan.json)의 세 객체와 [acceptance 원문](../../docs/plan/reason-inspired-adrs/acceptance.md)을 [결과 JSON](recovery-passive-closure-results.json)에 그대로 발췌했다. 각각의 criterion/positive/negative·evidence_levels·closure_gates 및 원문 SHA-256을 함께 저장했다.

- **A16-05 criterion:** 자동 수신 능력이 사라지면 미독 안내와 회수 경로가 살아 있다. 도구 숨김 때문에 답을 영원히 못 읽는 경우를 재현한다.
  - positive: 자동 수신 능력 하향과 cached tools/list에서 미독 조회·회수.
  - negative: 도구 숨김 뒤 영구 unread·복구 경로 소실.
- **A18-06 criterion:** FYI를 보낸 뒤 다음 자연 소비 시점에서 읽히는지 확인한다. unread 저장만 성공한 경우와 분리한다.
  - positive: FYI 후 무기상과 다음 자연 prompt/tool 경계의 실제 소비를 각각 추적.
  - negative: unread 저장만 확인하거나 queue 자체 기상 경로를 no-wake로 표시.
- **A22-03 criterion:** 구현자·검토자의 여러 차례 반례·수정·재검증이 정상 완료된다. 의미 없는 반복이 중단돼도 요청은 조회·복구 가능하다.
  - positive: 구현/검토 다회 수정과 의미 없는 반복을 같은 조건에서 대조.
  - negative: 정상 검토 제한·반복 중단 뒤 요청 소실/성공 종료.

## 기존 증거를 먼저 감사한 결과

### A16-05: native cached list와 하향 회수를 실제로 연결

`different-parent-native-20261029-5564a814`의 기존 manifest 파일을 다시 SHA 대조했다. 모두 일치했다. active child MCP 두 개는 각각 실제 **tools/list 1회**였고, 그 최초 응답에 xsm_inbox가 광고돼 있었다. 그 뒤 tools/list 재조회는 0회다.

해당 native 실행은 requested auto를 유지하면서 exact unsupported를 만나 stored/mcp-inbox로 하향한 메시지 8건을 포함한다. wire에서 한쪽 client의 positive unread notice **3건**, cached inbox를 통한 실제 수신 task ID **4종**과 원 body SHA·ACK 상태를 직접 재결속했다. 예: `11f8150b86184fc2`, `7bbf155fed2340ad`, `8ebd81df269d48cb`, `6ef48ff9cb164b6f`. 저장만 한 것이 아니라 실제 native child가 원 본문을 받아 ACK했다.

이는 서로 다른 MCP process에서 각자 유지한 native client tools cache다. 한 shared server의 cache/격리를 꾸민 것이 아니다. 초기 목록에서 inbox를 사후 제거하거나 result/metadata를 바꾼 적도 없다. 영구 unread/회수 경로 소실 반례는 이 실행의 수신·ACK와 맞지 않는다. 과거 cache warning 1건과 profile drift writer unknown은 원 보고대로 유지한다.

### 기존 정상 다회 검토 / quiet의 한계

postclaims는 실제 제안 `2+2=5`→수정 `2+2=4`→경계 `0+0=0`와 handshake를 처리했고 body·reply_to·claims 직접 ACK를 결속한 원 감사가 있다. different-parent는 최종 receipt 고정본 315files/135primary에서 실제 다회 검토·부분/최종 reply·ACK가 있다. 이 성공을 다시 실행하지 않았다.

기존 P09 N:N은 실제 native quiet 질문/회신과 ACK가 있으나 goal에 명시적 polling 절차가 있고 실행 중 cli.py/mcp.py source drift가 기록돼 있다. 이를 최종 고정본의 자연 FYI 소비나 단일 고정 revision 성공으로 바꾸지 않았다. shared-MCP 표본은 실제로 process별 분리됐다는 원 한계를 유지한다.

fixture/process 근거는 기존 final-regression 두 Python **1697** 결과와 같은 source의 `test_open_mcp`, `test_question_interfaces`, `test_traffic_interfaces`, `test_traffic_policy`다. cached caller의 미독 안내, static inbox 도구 존재, passive claim/ACK, strict defer 원문 보존·same-ID retry 검사를 분리해 인용했다. 이번에 fixture/full 회귀를 다시 돌리지 않았다.

## 새 pair 1: strict defer → 같은 ID 조회/복구

private Git/XSM root: `/private/tmp/p13-recovery-passive-7yocp3dz`.

최종 고정본 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`와 기존 정상 factory/native 프로필을 사용했다. private fixture에만 초기 `traffic_control={mode:strict,window_seconds:60,max_same_body:1}`을 설정했다. 전역 policy·권한·제품 source를 바꾸지 않았다. 모델에는 두 동일 문장의 반복 보류를 관측하고 새 ID로 치환하지 말라는 업무 의도와 private 정책을 주었고, 실제 ID는 모델/제품이 생성했다.

| 실제 단계 | 원 ID / 결과 |
|---|---|
| 첫 정상 질문 | `4f82264981f44424`, 실제 final/succeeded 회신·ACK |
| 같은 본문 두 번째 질문 | `82b9339d054f4580`, 실제 held, final=false, final_outcome=null |
| 같은 ID 조회 | `82b9339d054f4580`, held/미완료 유지 |
| 읽기 전용 중간 snapshot | canonical 원문·digest 보존, delivery_state=held, 실제 receipt decision=held |
| 실제 시간 대기 후 기존 재전송 | xsm_send의 resend가 **원 ID `82b9339d054f4580`**를 사용. 단 1회, 같은 원문 |
| 원 ID 최종 조회 | 실제 reply `39931ec134554d5e`, reply_to가 원 ID와 일치, succeeded. sender와 receiver가 실제 ACK |

clock mock·본문 재생성/주입·ACK/index 보정은 없다. final 원문/message/digest가 보류 snapshot과 일치했고, 원 요청과 실제 답 모두 canonical acknowledged다. **15개 offline check**를 통과했다. 다만 이 새 strict pair의 정상 비교는 첫 질문 1건이다. 별도 기존 다회 수정 trace와 합쳐 엄격히 동일 정책의 한 다회수정/반복 contrast라고 표시하지 않았으므로 A22-03 whole credit은 partial로 남긴다.

## 새 pair 2: FYI → 다음 자연 소비 도구

private Git/XSM root: `/private/tmp/p13-passive-fyi-phb8nuwk`.

receiver는 독립 20초 정수 샘플링을 마친 뒤 협업 동료·참고 정보를 확인한다는 업무 목표만 받았다. 이는 상태를 관측하기 위한 한 작업이며 장시간 실행을 수용 기준으로 추가한 것이 아니다. sender는 작업을 깨우거나 답을 요구하지 않는 참고 note를 한 번 남기라는 목표였다. evaluator는 inbox 호출 순서·인자·상대 ID를 native goal에 주입하지 않았다.

- 실제 note ID: **`d0b6f09d01da4a25`**.
- 실제 sender call은 kind=note, wake=never, body는 “FYI: 다음 검산에서 3 또는 5의 배수 비율의 기준값은 7/15입니다.”였다.
- canonical logical wake=false, native queue evidence 없음, wake.ok=false다. 단순 native queue 기상 실패를 no-wake로 바꾼 것이 아니다.
- note 저장은 receiver의 실제 계산 command 시작과 완료 사이였다. 계산이 끝난 뒤 receiver는 제품 skill을 읽고 **스스로 xsm list를 선택**해 미독 안내를 받았으며, 이어 xsm_inbox에서 실제 원 본문·claim을 읽고 xsm_ack했다. 수신 미독 저장만 성공한 표본이 아니다.
- receiver에 새 prompt나 evaluator inbox poll을 주지 않았다. sender는 stored만 보고했고 읽었다고 주장하지 않았다. 실제 body/ACK 확인은 receiver raw와 canonical로 별도 대조했다.
- 이 실제 소비 표면은 **자연 agent 선택의 list→inbox/ACK**다. 다른 MCP 도구 응답에 본문이 자동 첨부된 것, TUI가 자발적으로 깨어난 것, 모든 하네스의 소비를 증명했다고 말하지 않는다. 원 기준에 없는 그 추가 경로를 필수조건으로 삼지도 않았다.

**12개 offline check**로 무기상 축과 실제 소비 축을 각각 대조했다. 별도 파일의 sample_count=53,177,824, matched_count=24,811,182 및 ratio 기록도 남았다.

## 실행·소유·drift 한계

- 새 조건은 위 **2개 pair뿐**이다. actual actor 실행 4회, 각 pair의 초기 actual CID/PID/home/cwd registry setup 2회와 a1 역할 이름만 부여했다. 본문 relay/수동 ACK/index 수정은 모두 0이다.
- 두 pair 모두 고정본 315파일 전후 hash가 일치했다. 신규 UI·권한·allowedTools·프로필 편집·credential 복사·API 키 경로·native 재시도는 없다.
- 두 pair의 aggregate profile/settings/auth metadata guard는 **false**다. 기존 하네스는 경로별 전후값을 저장하지 않아 변경 주체/파일을 이 비교만으로 확정하지 못한다. 이 원 한계를 숨기거나 profile 불변이라고 표시하지 않았다.
- 각 actual native 및 MCP의 기록된 동일 generation 생존은 모두 false다. strict pair: native PID 94654/94829, MCP 94786/94945. FYI pair: native PID 3544/3768, MCP 3701/3905. 기존 user 세션/전역 서비스를 종료하지 않았다.
- source/ledger/plan 판정을 새롭게 덮어쓰지 않는다. 이 파일은 증거 재결속과 남은 partial을 coordinator에게 인계하는 별도 산출물이다. 추가 모델 실행으로 partial을 채우지 않았다.

## 증거

[원문·조건별 대조/실행·SHA JSON](recovery-passive-closure-results.json) · [offline audit](recovery-passive-closure-audit.py) · [manifest](recovery-passive-closure-manifest.json)

새 원 실행은 [strict script](recovery-passive-closure-run.py)/[원 결과](recovery-passive-closure-native.json), [FYI script](recovery-passive-closure-fyi-run.py)/[원 결과](recovery-passive-closure-fyi-native.json)에 분리했다. 실제 token/body/index/receipt/native JSONL은 각 private root에 보존했다. 공개 artifact에는 claim token 원문을 복사하지 않았다.
