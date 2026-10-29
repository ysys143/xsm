# A16-07 / A18-02: 기존 trusted cwd의 native Esc 1회

**실제 MCP inbox wait 중 표준 Esc와 native turn 중단을 관측했다. 그러나 MCP `notifications/cancelled`는 0건이고, 원 RPC는 60.116초 뒤 빈 정상 결과로 끝났다.** 후속 문장은 PTY 입력창에 남았으며 두 번째 native turn은 시작되지 않았다. 따라서 native MCP 취소 전달·후속 회수 성공으로 표시하지 않는다. 이번 조건 뒤 추가 실행은 없다.

[조건](plan.json) · [trust 사전 확인](trust-preflight.json) · [trust 사후 확인](trust-postflight.json) · [실제 계수/상관 wire SHA](summary.json) · [manifest](manifest.json) · [PTY controller](run.py) · [기록 proxy](proxy.py) · [offline 검사기](offlinecheck.py)

## 신뢰와 실행 경계

기존 `.codex-3/config.toml`에서 정확한 `/Users/jaesolshin/Documents/GitHub/cross-session-messaging` project 항목의 trusted 여부만 내부에서 비교했다. 공개물에는 해당 boolean·파일 hash만 기록했다. 이미 trusted였으므로 이 cwd에서 소유 TUI **1회**를 실행했다. 새 trust 선택·신뢰 설정 override·승인 저장은 없다. 사후에도 같은 정확한 project 항목은 trusted다.

기존 구독 프로필과 일반 TUI `codex-cli 0.164.0`을 사용했다. 호출은 `read-only` sandbox·approval never이며 native 기본 도구/지침을 교체하지 않았다. 기존 평가와 같은 호출 한정 private XSM_HOME·frozen MCP/proxy 연결 인자만 사용했고 persisted 프로필 설정은 편집하지 않았다. 실제 MCP caller metadata에도 `sandbox_mode=read-only`가 있다. 모델 shell 동작은 frozen skill/guide를 읽는 cat 3회뿐이다. 다른 세션/서비스를 호출하거나 사용자 repo 파일을 쓰는 모델 동작은 없다.

제품 source는 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`이다. 저장소의 primary 135파일을 실행 전·후 고정 manifest와 대조했고 일치했다. frozen 315파일도 일치한다. private registry에는 이 실제 CID의 record 1개뿐이며 외부 CID는 **0개**다. 실제 native hook의 등록을 사용했고 controller 보완 등록은 0회다. caller metadata·도구 결과·ID·claim·ACK·취소 notification은 위조하거나 바꾸지 않았다.

원 [새 폴더 trust/CID 0 준비 실패](../native-cancel-20261029-660a8b39/report.md)는 그대로 보존하고 manifest SHA를 연결했다. 이 보완 표본으로 원 실패를 성공으로 덮지 않는다.

## 실제 상관 경로

소유 TUI native PID **37769**, lstart **Thu Oct 29 09:41:26 2026**, CID SHA `6781d04e…`의 전체 값은 summary에 기록한다. full CID/home은 private raw에 보존했다. 실제 native 호출 경로는 일반 `exec` 도구에서 `tools.mcp__xsm__xsm_inbox({wait:60})`를 실행하는 현재 하네스 경로다. proxy의 원 client `_meta.threadId`와 실제 native/registry CID가 일치했다.

| UTC 시각 | 실제 관측 | 판정 범위 |
|---|---|---|
| 00:41:52.040 | xsm_inbox wait 60, JSON-RPC ID **2**가 server로 전달됨 | 반환 없는 pending을 재확인한 뒤만 Esc 실행 |
| 00:41:52.508 | 표준 Esc **1회** | 원 요청·meta·결과 수정 없음 |
| 00:41:52.513 | native turn_aborted와 TUI `Error: interrupted` / `Conversation interrupted` | native 대화 interrupt는 실제 관측 |
| 00:42:52.156 | 같은 RPC ID **2**가 messages/claims 빈 배열·inbox_pending 0, isError=false로 반환 | RPC 총 60.116초, Esc 뒤 59.648초. client notification에 의한 server 취소 경로를 통과했다고 추정하지 않음 |
| 00:44:23 이후 | bounded 후속 대기 종료 및 소유 프로세스 정리 | cleanup 입력/신호는 취소 notification으로 세지 않음 |

원 client wire 전체에서 `notifications/cancelled`는 **0건**이다. EOF 기록도 관측되지 않았다. 첫 RPC가 Esc 뒤에도 응답한 사실과 cleanup 종료를 구분한다. EOF가 없다는 사실만으로 다른 런타임이나 모든 취소 방식을 미지원으로 단정하지 않는다. 이 CLI·현재 exec→MCP 호출 경로 한 표본의 취소 전파 미확보 근거다. server의 fixture 취소 처리 구현이 실패했다고 단정할 근거는 없다.

wire의 request/response 원 bytes SHA와 caller CID hash, 실제 pending ID/시각은 summary에 있다. native `Error: interrupted` 1건, MCP isError 0건, 평가기 후속 timeout 1건은 서로 다른 사건이다. MCP 오류가 없다는 사실을 전체 평가 성공으로 바꾸지 않는다.

## 후속 입력·원문 회수 한계

Esc 뒤 후속 자연 목표를 같은 PTY에 1회 입력했지만, 화면의 입력창에 남았고 실제 rollout에는 두 번째 task_started가 없다. 150초 후속 예산에서 완료되지 않아 평가기는 `same-CID follow-up did not complete`를 보존했다. 입력 제출이 되지 않은 원인은 확정하지 않았다. native 후속 수신 경로가 실행됐다는 주장이나 제품 회수 실패 판정은 하지 않는다. 추가 Enter·대체 app-server 입력·모델 재시도로 성공시키지 않았다.

이 조건의 inbox는 처음부터 비어 있었고 실제 원문을 수신하거나 evaluator가 원문을 심지 않았다. canonical 원문/claim/ACK는 모두 0건이다. **late 원문 보존·회수는 미관측**이다. 기존 kill/resume 성공 표본을 재실행하거나 이 조건의 성공으로 옮기지 않았다.

## 계수·정리·보존

- 새 TUI 1회, 실제 CID 1개, native task_started 1회, turn_aborted 1회, task_complete 0회. 초기/후속 입력문 2개와 모델 turn 수를 구분한다. 자동 조건/모델 재시도 0회다.
- 실제 MCP tools/call 1회, pending-call Esc 1회, cancelled notification 0건. 다른 MCP 서비스 호출·outgoing send 0회, registry 외부 record 0개다.
- cleanup Ctrl-D와 소유 PID/lstart를 확인한 SIGTERM 요청 3건은 모두 측정 종료 뒤다. kill을 취소 notification·EOF로 세지 않는다. 최종 wrapper/native/proxy/MCP 및 고유 root의 native 후보 잔여는 **0**이다. 사용자/기존 daemon/다른 세션은 종료하지 않았다.
- config.toml hash drift가 관측됐고 변경 주체는 미확정이다. hook/settings hash는 같고 exact project의 trusted 상태는 전후 확인됐다. 평가기·모델의 profile 편집 명령은 없으며 profile 전체 불변을 주장하지 않는다.
- product/원 ledger/원 plan 수정은 없다. `offlinecheck.py --require-native-cancellation-propagation`은 notification·후속 turn·회수 증거 미확보 때문에 **exit 1**이다. 기본 실행 exit 0은 raw/SHA/계수 정합성만 뜻한다.

raw PTY·native rollout·원 MCP client/server wire·state·process handle은 `/private/tmp/native-cancel-trusted-w23wicuo`에 보존했다. 공개물에는 비밀값이나 가짜 wire를 만들지 않고 원 bytes hash/경로만 연결했다. A16-07/A18-02는 부분 근거로 남기며 이번 최종 보완 뒤 추가 실험 없이 종결했다.
