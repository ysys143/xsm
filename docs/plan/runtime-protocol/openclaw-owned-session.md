# OpenClaw owned native 실행과 세션 결속

현재 상태: OpenClaw2026.10.9 제공자를 catalog에 등록했고 실제 owned journal에서
정상 실행·같은 문맥의 재개·다른 문맥 분리·결과 저장·요청 replay를 확인했다.
실행 전·native 대기열·실행 중 취소와 확인 유실 readback을 macOS에서 확인했다.
Linux arm64에서도 실제 gateway를 통한 같은 native 행렬과 공개 protocol 취소를 확인했다.
Frontend 종료 뒤 살아 있는 native host의 완료 결과 회수도 macOS에서 확인했다.
성공 답변 없는 provider 오류 종료는 실행 lease만 정리하는 경로를 macOS에서 확인했다.
완료된 native run은 gateway 재시작 뒤 원래 transcript로 회수한 macOS 증거가 있다.
실행 도중 gateway 재시작과 전체 OS/모드 행렬은 미완이다. 아래 초기 시험과 거부 기록도
보존하며, 현재 통합 증거는 마지막 절을 따른다.

OpenClaw2026.10.9의 실제 gateway에서 모델 실행 없이 세션 생성·재조회를
확인했다. 이 기록은 owned 제공자 전체 완료나 모델/워커 실행 인증이 아니다.

## 선택한 native 경계

Plugin SDK의 createSessionEntry는 등록한 harness 소유 플러그인만 해당 세션을
만들도록 제한한다. xsm을 다른 harness의 소유자로 가장하거나 내부 함수를
제품 코드에 가져오는 대신, native operator RPC인 sessions.create를 사용한다.
고정 native loader의 내부 export를 찾는 기존 probe는 제품 연결부로 재사용하지 않는다.

생성 요청은 key를 지정하지 않고 message를 빈 문자열로 보내 native host가
새 key와 sessionId를 할당하게 한다. Reply의 ok=true, runStarted=false, 실제
entry.sessionId/lifecycleRevision과 workspace를 확인한 뒤에만 결속한다.
짧은 ID·label·최근 세션 선택은 사용하지 않는다. 재개는 정확한 sessionId로
sessions.resolve를 호출하고, 실제 목록의 같은 key/ID/agentId/revision을 확인한다.

후속 agent 요청용 인수는 expectedExistingSessionId와
expectedExistingSessionLifecycleRevision을 포함한다. 결속과 실행 사이의 native
reset/교체가 다른 모델 문맥으로 이어지지 않도록 하는 backend 전용 계약이다.
실제 operator agent RPC 시험에서는 이 인수의 사용이 거부됐다. 따라서 이 helper의
인수를 만들었다는 사실은 실행 경로를 확보했다는 증거가 아니다. 실행 시 cwd는
생성한 세션에서 상속하며, agent 요청에는 넣지 않는다. PermissionMode와
toolOverrides는 임의로 설정하지 않는다.

## 실행한 증거

- 최초 native gateway의 health/sessions.create/sessions.list가 정상 종료했다
  (openclaw-session-create-first/result.json).
- key를 생략한 native 생성과 정확한 sessionId 재조회도 정상 종료했다
  (openclaw-session-create-resolve/result.json).
- 검증 helper로 actual ID와 revision을 읽고 실제 private socket 계약에 ID를
  전달했다. Controller는 이 시험의 명시적 fixture이며 실제 owned journal
  reservation 인증으로 계산하지 않는다. Gateway가 살아 있는 동안 model turn 없이
  이 경계를 확인했다(openclaw-session-contract-native/result.json).
- 재현 스크립트도 통과했고 gatewayStopped=true를 확인했다
  (openclaw-worker-session-script/result.json).

위 artifact는 deliverables/protocol-foundation/ 아래에 있다. Native CLI는
2026.10.9, Node는 지정한24.22.2 경로를 사용했다. 격리 HOME/OPENCLAW_STATE_DIR/
OPENCLAW_CONFIG_PATH와 loopback gateway, 새 시험용 인증 토큰만 사용했다.
Heartbeat/cron과 외부 플러그인은 껐고 실제 메신저나 모델을 호출하지 않았다.
시험용 최소 profile에서 모델/runtime 기본값이 해석됐다는 사실을 모델 실행으로
세지 않는다. Native gateway는 각 실행 뒤 종료했다.

## 코드와 남은 단계

integrations/openclaw/worker_session.py는 RPC JSON 검증과 create/resolve/run 인수
계약만 구현한다. 중복 JSON key·비 JSON 수·이미 시작된 생성·다른 workspace나
ID·모호한 재조회·없는 revision을 거부한다. Unit5개가 통과했다. runStarted 검사를
제거한 변이는2개 assertion으로 검출됐다(openclaw-session-contract-mutant.log).

재현: scripts/probe-openclaw-worker-session.py --native-cli <고정 openclaw.mjs>
--node <지정 Node> --output <새 경로>. 실제 auth 값은 출력하지 않는다.

다음 필수 단계는 실제 owned frontend와 공통 journal의 결속, native agent 실행과
run ID에 결속된 결과/중단/복구, profile의 원래 harness/model 정책, native UI와
local/messenger 경계 검증이다. 이 초기 준비 시험 시점에는 제공자 catalog에
OpenClaw를 등록하지 않았다. 이후 정상 실행 연결은 마지막 절을 따른다.
이 범위를 줄이거나 지원 완료로 표시하지 않는다.

이 변경의 macOS core는 Python494+SDK52+native93+Node152=791개와 독립
mock39/변이14개를80.427초에 통과했다(openclaw-session-contract-core-final.log).
Linux에서도4c92db2의 계약을 포함한791개가 Python3.11.2에서64.191초,
Python3.14.10에서81.899초로 통과했다. 격리 VM 종료 코드도0이다
(openclaw-session-contract-linux). 이 결과는 아래 실제 실행 거부를 해결했다는
의미가 아니다.

## 실제 agent 실행에서 확인한 거부와 미완 경계

격리된 loopback gateway와 명시적 로컬 SSE model0 fixture로 agent RPC를
시험했다. 첫 실행은 `cwd is reserved for plugin-owned subagent runs`로 거부됐다
(openclaw-agent-run-first). Agent 인수에서 cwd를 제거한 두 번째 실행은
`expectedExistingSessionId is reserved for backend callers.`로 거부됐다
(openclaw-agent-run-second). 두 gateway 모두 종료됐으며 모델 실행 성공으로
계산하지 않는다. 생성 시 workspace 검증은 유지한다.

고정 소스의 agent-request-preflight.ts는 실제 client mode가 BACKEND인지 검사한다.
ChatSendParamsSchema에는 expectedLeafEntryId와 routing 계약이 있지만, 기대하는
session ID와 lifecycle revision을 함께 고정하는 필드는 없다. 이것만으로 owned
세션 결속을 대체했다는 판정을 내리지 않는다. 또한 runtime.gateway.request는
server-plugins.ts에서 bundled 또는 trusted official plugin만 허용하므로 일반
xsm 플러그인의 우회 실행 경로로 사용하지 않는다.

일반 operator CLI 경로는 위 이유로 실행에 사용하지 않는다. 아래 SDK 경로의
실행은 확인했지만, OpenClaw owned 제공자와 전체 계획은 여전히 미완이다.

## 공개 SDK backend 실행과 동일 세션 재개

고정 소스의 commands/agent-via-gateway.ts는 모델 변경·reset 요청에 인증된
BACKEND 연결을 사용한다. 공개 export인 openclaw/plugin-sdk/gateway-runtime의
GatewayClient도 이 연결 방식을 제공한다. 일반 xsm 플러그인이 official 신원을
취득하는 것과 달리, 이 시험은 격리 gateway의 시험용 operator 토큰으로 인증한
외부 backend client다. Client display name에도 XSM 시험임을 명시했다.

scripts/probe-openclaw-agent-native.py는 native package의 공개 export를 resolve해
이 client를 사용한다. 내부 hashed export나 trusted-plugin runtime은 쓰지 않는다.
인증 값은 격리된0600 config에서 프로세스 내부로만 읽고 argv·산출물에 넣지 않는다.
로컬 SSE fixture를 명시했으며 유료 모델이나 메신저를 호출하지 않는다.

openclaw-agent-native-resume/result.json에서 다음을 확인했다.

- 오래된 lifecycle revision의 agent 요청은 native의 세션 변경 검사에서 거부됐다.
  그 시점에 provider 요청 로그는 없었다.
- 올바른 revision의 첫 요청은 accepted였고, agent.wait의 terminal receipt에 같은
  runId/turnId와 생성한 native sessionId가 있었다.
- 두 번째 요청도 같은 native sessionId에서 완료됐다. 두 실행의 요청 ID는 다르다.
- 전체 fixture 요청은2회이고, gatewayStopped=true다. 실제 모델 추론은0회다.

accepted_run은 request ID·native key·agent ID를 검사한다. completed_run은 최종
상태와 run/turn/session ID 및 receipt/reply disposition의 일치를 검사한다.
Acceptance를 업무 결과나 전달 ACK로 승격하지 않는다. Terminal session ID 검사를
제거한 변이는 의도한 assertion1개로 검출됐다
(openclaw-agent-receipt-mutant-final.log). 첫 변이 러너는 예외 클래스가 달라
오류9개가 섞였으므로 검증 성공으로 계산하지 않았다. 실패 로그도 보존했다.

macOS 핵심 검사는 Python494+SDK52+native95+Node152=793개와 독립 mock39/
변이14개를81.067초에 통과했다(openclaw-agent-receipt-core.log). 앞선 Linux791개는
이번 receipt 검사2개를 포함하지 않는다. 실제 owned journal과 backend client의
결속, 취소·복구·native UI 및 전체 OS/런타임 행렬 검증은 남아 있다.

## 실행 순서를 보장하는 frontend

integrations/openclaw/worker_frontend.py는 실제 backend RPC와 inherited private
control client를 받아 create 또는 정확한 ID의 resolve/list를 수행한다. Native가
반환한 ID의 private bind ACK 이후에만 agent를 호출한다. Agent 응답이 유실되면
재실행하지 않는다. agent.wait의 timeout/pending은 같은 run ID를 계속 관측하며,
다른 run의 늦은 응답은 거부한다. 모델·권한·도구 정책을 대체하지 않는다.

Frontend의 unit6개는 실제 private socket과 명시적 native RPC fixture를 사용한다.
정상 fresh/resume, 결속 거부, agent 응답 유실, 관측 timeout, 다른 run 응답을
검사했다. Private bind 호출을 제거한 변이는 테스트의 순서 assertion으로 검출됐다
(openclaw-ordered-frontend-mutant.log). 이 테스트가 native gateway 실행을 대신하지
않으며, 별도 native 시험은 다음 명령의 --owned-frontend 경로다.

```sh
python3 -B scripts/probe-openclaw-agent-native.py --owned-frontend \
  --native-cli <고정 openclaw.mjs> --node <지정 Node> --output <새 경로>
```

첫 실제 실행(openclaw-ordered-frontend-native)은 create→bind ACK→agent→wait와
같은 ID의 resolve/list→bind ACK→agent→wait를 통과했다. Native receipt의
세션·요청 ID도 일치했으며 fixture 요청2회, 실제 모델 추론0회,
gatewayStopped=true다. Controller는 실제 private socket의 callback fixture다.
실제 owned journal reservation이나 실행 child PID의 인증으로 계산하지 않는다.
아직 제공자 catalog에 연결하지 않았으며 취소·복구 경로도 미완이다.

추가 실제 시험(openclaw-ordered-frontend-refusal-native)에서도 두 실행은 완료됐고,
세 번째 fresh 세션의 private bind를 callback에서 거부하자 agent를 호출하지
않았다. Fixture 요청은2회로 유지됐고 gateway도 종료됐다.

이번 macOS 핵심 검사는 Python494+SDK52+native101+Node152=799개와 독립 mock39/
변이14개를80.499초에 통과했다(openclaw-ordered-frontend-core.log). Linux의 앞선
791개 결과에는 이번 frontend6개와 receipt2개가 포함되지 않는다.

## Native 인증·전송 정책을 재사용하는 RPC 경로

worker_rpc.mjs는 공개 SDK의 callGatewayFromCli를 backend 모드로 호출한다.
Native가 profile/config·인증·연결 정책을 해석하며 XSM은 토큰이나 config 형식을
재구현하지 않는다. Native package 이름과2026.10.9 버전을 확인하고 공개 export를
resolve한다. 허용한 native method만 받으며 요청은 argv 대신 stdin으로 전달한다.

worker_transport.py는 이 모듈을 별도 프로세스로 호출한다. Private control FD의
환경 힌트와 worker label은 넘기지 않으며 native의 agent exec 표식은 유지한다.
실패·timeout이면 불명확한 실행으로 보고 재시도하지 않는다. Native 오류 원문은
출력하지 않고, probe에 필요한 특정 거부 사실만 boolean으로 내보낸다.

명시적 SDK package fixture의 unit4개는 실제 Node 자식에서 backend 인수, 정확한
요청, private hint 제거, 다른 버전·미허용 method 거부와 오류 내용 비노출을
검사했다. Hint 제거를 생략한 변이는 assertion1개로 검출됐다
(openclaw-sdk-transport-mutant.log). 이는 native 실행 인증과 구분한다.

실제 native 시험은 위 명령에 --sdk-transport를 추가한다.
openclaw-sdk-transport-native-guard-final에서 제품 transport를 통해 신규 실행과
동일 세션 재개, stale revision 거부, private bind 거부를 확인했다. 또한
OPENCLAW_SHELL=exec인 호출은 native의 출처 보존 규칙으로 거부됐다. Boolean
거부 사실은 native-exec-guard-facts.json으로 따로 확인했다. Fixture 요청2회,
실제 모델 추론0회, gatewayStopped=true다. 앞선 guard 표본은 일반 오류만 보고
실패를 판정했으므로 특정 native 규칙의 근거는 이 final 표본으로 한정한다.

이 SDK 전송 시험 시점에는 provider catalog와 실제 owned journal에 연결하지
않았다. 아래 후속 연결도 전체 지원이나 취소·복구 완료로 계산하지 않는다.

최종 macOS 핵심 검사는 Python494+SDK52+native105+Node152=803개와 독립 mock39/
변이14개를80.708초에 통과했다(openclaw-sdk-transport-core-final.log). 앞선
79.948초 표본은 특정 exec 거부 boolean을 추가하기 전 결과로 따로 보존했다.
이번 native transport4개를 포함한 Linux 검증은 아직 미실행이다.

## 실제 owned journal과 native 제공자 연결

worker_provider.py를 고정 catalog에 등록했다. Managed native 설치의 실제 파일
hash, native package 이름·버전과 operator가 선택한 CLI/Node 경로를 확인한다.
Agent는 native agents.list의 defaultId 또는 명시한 XSM_OPENCLAW_AGENT_ID로
선택하며, selectionRequired이거나 선택한 ID가 없으면 임의 대체하지 않는다.
설치된 연결 파일이 달라지면 실행을 거부한다. 공통 엔진에 OpenClaw 분기를
추가하지 않았다.

CLI는 상속된 private control FD로 실제 세션을 결속한 뒤 backend를 호출한다.
요청별 native run ID는 worker ID와 새 난수로 분리하며 실제 실행 argv에 보존한다.
출력에는 context ID/epoch와 native admission/terminal receipt를 함께 남긴다.
공통 readback에서 다른 context/epoch/세션이나 선택한 agent/workspace와 다른
결과를 수락하지 않는다. 답변의
실제 text만 공통 결과로 반환하며 native turn 완료를 업무 성공으로 만들지 않는다.
Model/thinking을 지정한 경우 native 인수로 전달하며 미지정이면 원래 정책을 따른다.

실제 재현 명령은 다음과 같다. 사용자 profile이나 전역 설정을 바꾸지 않는다.

```sh
python3 -B scripts/probe-openclaw-owned-native.py \
  --native-cli <고정 openclaw.mjs> --node <지정 Node> --output <새 경로>
```

openclaw-owned-native-final의23개 검사가 통과했다. 세 번의 실제 provider 요청
직전에 공통 journal의 running 요청 하나에 native session ID와 살아 있는 정확한
child PID/lstart 결속이 이미 저장돼 있었다. 같은 작업의 두 요청은 같은 native
세션을, 별도 작업은 다른 세션을 썼다. 세 결과는 실제 저장·게시됐고 outcome은
None으로 유지됐다. 동일 요청 replay는 원래 reply ID를 반환하고 provider를
다시 호출하지 않았다. 논리 worker의 두 native ID 인덱스도 일치했다.
Provider fixture3회, 실제 모델 추론0회, gatewayStopped=true다.

이 시험은 공통 workers API·실제 child/소켓·journal·gateway·로컬 답변 저장을
연결했다. 공개 protocol operation/UI/메신저 왕복을 대신하지 않는다. 최초 native
표본도 성공했으며 최종 표본은 설치별 Python import를 분리한 후 다시 실행했다.
SDK package fixture의 별도 unit4개는 common journal 재개/replay, 잘못된 결과
세대·receipt, 존재하지 않는 agent 선택과 변경된 설치 파일 거부를 검사한다.
Context epoch 검사를 제거한 변이는 assertion1개로 검출됐다
(openclaw-owned-provider-mutant.log).

이 정상 실행 연결 시점에는 native 취소 지원 flag를 선언하지 않았다. 취소 의도를 native 중단으로
승격하지 않으며, native 미확인 상태를 확인된 정지나 업무 결과로 만들지 않는다.
취소·native 상태 조회를 통한 복구·전체 Linux/모드/프로토콜 행렬은 남아 있다.

첫 core 실행에서는 공개 operation schema와 OpenClaw tools.mjs의 runtime enum을
재생성하지 않아 schema 비교2개와 설치본 계약2개, 총4개가 실패했다
(openclaw-owned-provider-core.log). 격리 HOME/XSM_HOME에서 기존 generator를
실행해 두 산출물을 갱신한 뒤, 실패한 경로4개는 모두 통과했다. 실패 로그는
보존했으며 첫 core 실행을 성공으로 계산하지 않는다.

Admitted agent/workspace 결과 검사를 추가한 뒤의 실제 재현은
openclaw-owned-native-admitted-result다. 같은23개 검사를 통과했고 결속 선행
관측3회, provider fixture3회, gatewayStopped=true였다. 최종 core는
Python494+SDK52+native109+Node152=807개와 독립 mock39/변이14개를81.593초에
통과했다(openclaw-owned-provider-core-final.log). 이번 제공자 연결을 포함한
Linux/native UI/공개 operation 왕복 검증은 아직 미실행이다.

## 실행 중 native 취소와 확인 유실 복구

고정 native gateway의 chat.abort에 정확한 runId와 canonical sessionKey/agentId를
보내고 preserveSideRuns=true로 요청한다. Abort acceptance만으로 중단을 보고하지
않는다. 실제 agent.wait의 같은 runId, status=error, stopReason=rpc와 종료 시각,
native 세션 row의 같은 ID/revision/lastRunId, status=killed, abortedLastRun=true,
hasActiveRun=false, activeRunIds=[] 및 같은 시작·종료 시각을 함께 요구한다.
정지 증거에는 해당 row의 필요한 필드만 남기며 다른 대화의 목록은 저장하지 않는다.
Native stop shape는 openclaw-cancel-shape-native에서 직접 확인했다.

Frontend는 같은 run의 wait를 관측하면서 취소 의도를 확인한다. Native 실행 전
private intent를 확인하면 agent를 호출하지 않은 사실을 별도로 남긴다. 실제
native 실행 중이면 위 정지 증거가 모인 후 marker를 먼저 stdout에 남기고 private
report_stopped를 보낸다. CLI exit1/130만으로 정지를 판단하지 않는다. 정상 완료가
취소와 경쟁해 이기면 실제 native reply를 유지한다. RPC/aborted stop reason의
응답은 성공 답변으로 승격하지 않는다.

Native cancellation capability를 제공자 descriptor에 추가했다. Common engine의
intent·소유 발신자·child PID/lstart·context epoch·retained-output readback 검증을
그대로 사용하며 runtime 분기는 추가하지 않았다. 정지됐어도 이미 일어난 업무
효과는 unknown으로 유지하고 task result/reply를 만들지 않는다.

실제 재현은 위 owned 시험 명령에 --cancel을, 확인 유실은 추가로
--lose-cancel-confirmation을 지정한다. 두 표본 모두 격리 profile과 로컬 차단형
SSE fixture만 썼다. 실제 모델 추론0회이며 gateway는 종료했다.

- openclaw-owned-cancel-native-second:32개 검사 통과. Native provider 요청이
  실제 시작된 뒤 취소했고2.628초에 정지 확인·child 종료를 관측했다. 슬롯을
  해제하고 업무 unknown/result=None/reply=None을 유지했다.
- openclaw-owned-cancel-native-lost:35개 검사 통과. Private 확인에 오류를 주입한
  뒤 native_state=unverified와 슬롯 점유를 확인했다. 같은 child의 보존 출력에서
  정확한 native 정지 증거를 읽어 복구했고 새 native 실행은 없었다.

각 표본의 정상 완료 fixture 요청은3회, 차단된 취소 대상까지 HTTP 진입은4회다.
첫 취소 표본은 다른 발신자의 요청이 실제 OwnedError로 거부됐지만 시험기가 이를
잘못 처리해 실패했다(openclaw-owned-cancel-native-first). 소유자의 취소까지
실행하지 못했으며 성공으로 계산하지 않는다. 실제 오류형을 처리하고 실패 시
차단 fixture를 먼저 풀도록 고친 뒤 위 새 표본을 실행했다.

별도 unit은 잘못된 run/session/revision·계속 실행 중인 row·일반 오류·다른
epoch·이미 시작된 실행을 미시작으로 표시한 경우를 거부한다. 마지막 run ID
검사를 제거한 변이는 assertion1개로 검출됐다
(openclaw-cancel-generation-mutant.log). 현재 readback 코드로 위 두 실제 보존
출력을 다시 검증했다(openclaw-cancel-current-readback.log).

이 실행 중 취소 시험 시점에는 native 대기열 취소의 실제 검증·보강이 남아
있다. Terminal rpc stop reason이 있는 timeout을 단순 관측 timeout으로 무한
재관측하지 않지만, 실행 중 정지 증거를 충족하지 않으면 unknown으로 남긴다.
미시작 marker의 실제 child 경로, native 재시작 뒤 상태 조회, Linux/공개 operation/
UI·메신저 전체 검증도 미완이다.

최종 macOS core는 Python494+SDK52+native116+Node152=814개와 독립 mock39/
변이14개를80.348초에 통과했다(openclaw-owned-cancellation-core-final.log).
앞선811개 표본82.582초에는 마지막 readback unit3개가 없었으므로 별도 보존했다.

## Native 대기열과 결속 직후 취소

고정 native gateway에서 maxConcurrent=1로 독립적인 model0 요청 하나를 막고,
다른 세션의 요청이 수락된 뒤 provider에 진입하기 전에 취소했다
(openclaw-queued-cancel-shape-native). 이 경우 native는 status=error,
stopReason=rpc, endedAt과 providerStarted=false를 반환했으며 startedAt은 없었다.
세션 row에는 lastRunId나 killed 상태가 없고 abortedLastRun도 false였다.
실행 중 정지의 필드를 추측해 적용하지 않는다.

stopped_run은 이 명시적 providerStarted=false를 별도 경계로 검증한다. 정확한
run ID의 abort acceptance·최종 rpc stop·종료 시각과 변하지 않은 native 세션
ID/agent/revision, hasActiveRun=false, activeRunIds=[]를 요구한다. 명시적
비실행 증거가 없거나 startedAt이 함께 있으면 이 경계를 수락하지 않는다.
보존 marker에는 native_provider_not_started=true를 남긴다. 이는 agent RPC 자체를
호출하지 않았다는 native_not_started=true와 구분한다.

scripts/probe-openclaw-owned-native.py의 추가 mode와 실제 결과는 다음과 같다.

| mode | artifact | 검사 수 | 결과 |
|---|---|---:|---|
| --before-admission | openclaw-pre-admission-native | 28 | 결속 후 모델 요청 전 취소·정지 확인 |
| --before-admission --lose-cancel-confirmation | openclaw-pre-admission-native-lost | 30 | 미시작 child의 보존 출력으로 확인 유실 복구 |
| --cancel --queued-native | openclaw-owned-queued-cancel-first | 35 | native 대기열 취소, 독립 실행 보존 |
| --cancel --queued-native --lose-cancel-confirmation | openclaw-owned-queued-cancel-lost | 38 | 대기열 취소의 정확한 출력으로 확인 유실 복구 |

실행 전 mode는 시험 프로세스에서 durable bind 직후 취소를 주입한다. 실제 native
세션 생성과 child/control/journal은 실행하고 agent 요청은 내보내지 않았다.
정상 fixture 요청3회는 변하지 않았으며 실제 child marker와 exit130 또는 확인
유실 시 exit1을 검증했다. 기본 비실행 결과를 모델 답이나 업무 성공으로 만들지 않는다.

대기열 mode는 독립 native 요청 하나만 provider에 들어가도록 막는다. Owned
대상은 native가 수락했으나 provider 호출이 없었다. 대상 취소 후에도 독립 요청의
wait는 계속 timeout이었고, 대상의 providerStarted=false와 별도 정지를 확인했다.
확인 유실 표본도 재실행 없이 native-output으로 복구하고 슬롯을 해제했다.
정상 fixture3회와 독립 queue holder1회로 진입을 구분하며, 대상의 추가 provider
진입은0회다. 모든 gateway는 종료했고 실제 모델 추론은0회다.

명시적 provider 비실행 검사를 제거한 변이는 assertion2개로 검출됐다
(openclaw-queued-cancel-mutant.log). Core는 Python494+SDK52+native118+Node152=
816개와 독립 mock39/변이14개를80.745초에 통과했다
(openclaw-queued-cancel-core.log). Native 일반 재시작 복구와 Linux/UI/메신저/
공개 operation 및 전체 런타임 행렬은 계속 미완이다.

## 공개 operation과 실제 inbox claim/ACK

scripts/probe-openclaw-owned-protocol.py는 격리된 protocol serve 자식에 Python
SDK로 연결하고 실제 session.open/events.subscribe/operation.call을 사용한다.
xsm_owned의 create/run/status를 통해 native OpenClaw gateway를 실행했다.
이 parent는 시험용 일반 프로토콜 참여자이며 native UI나 사람 답을 가장하지 않는다.

openclaw-owned-protocol-first에서19개 검사가 통과했다. 같은 work_context는 같은
native 세션을 재개했고 별도 문맥은 다른 세션이었다. 세 답변을 실제 xsm_inbox에서
읽고 각각의 claim token을 xsm_ack에 전달해 소비했다. 정상 모델 turn을 task 성공으로
승격하지 않았으며 request replay는 같은 reply ID를 반환하고 provider를 호출하지
않았다. Fixture 요청3회, 실제 모델 추론0회, gatewayStopped=true다.

재현은 위 owned 시험과 같은 --native-cli/--node/--output 인수로 새 script를
실행한다. 이 결과는 공개 operation의 owned 정상 경로와 로컬 답변 소비를
검증한다. 공개 operation의 전체 취소·오류 행렬, native UI·메신저와 전체
런타임 조합을 검증한 것으로 확대하지 않는다.

## 고정 커밋의 Linux 핵심 회귀

1246d22의816개 core와 독립 mock39/변이14개가 Linux arm64 Python3.11.2에서
64.549초,3.14.10에서82.391초로 통과했다. 시험 VM 종료 코드도0이다.
원시는 openclaw-queued-cancel-linux이며 source archive hash와 재현 경계는
linux-validation.md의 마지막 절에 기록했다. macOS native 실행 증거와 Linux
fixture core를 섞어 실제 Linux gateway 지원 완료로 표시하지 않는다.

## 공개 operation의 실행 중 취소와 확인 유실

공개 시험 script에 --cancel과 --lose-cancel-confirmation을 추가했다. 격리
protocol serve 프로세스에서 native provider에 실제 진입한 작업을 xsm_owned
cancel로 취소하고 status/reconcile로 확인했다. 다른 public session의 취소는
RpcError로 거부됐으며 취소 의도만 있을 때 native_state는 unverified였다.

openclaw-owned-protocol-cancel의28개, openclaw-owned-protocol-cancel-lost의31개
검사가 통과했다. 유실 mode는 격리 server bootstrap에서 private 확인에만 오류를
주입한다. Native child 종료 뒤 슬롯 점유와 불명 상태를 확인하고, 공개 reconcile이
정확한 보존 출력으로 stop을 복구했다. 이 과정에서 provider 재호출은 없었다.
두 mode 모두 slot을 해제하되 업무 unknown/result=None/reply=None을 유지했고,
같은 불명 요청을 공개 run으로 재제출해도 native 실행은 늘지 않았다.

각 mode의 정상 fixture3회와 취소 대상 HTTP 진입1회를 구분했다. 실제 모델
추론0회이며 gatewayStopped=true다. 공개 취소 경로의 증거이며 native UI에서
수집한 사용자 답이나 메신저 권한 검증을 대신하지 않는다. 제품 코드는 변경하지
않았으므로 이번 변경에서 core를 반복 실행하지 않았다. 직전 고정 커밋의816개
macOS/Linux 결과는 위 절에 따로 기록했다.

## 실제 Linux arm64 gateway 행렬

f472d32의 소스를 고정하고 기존 Linux용2026.10.9 설치를 재사용했다. 첫8개
시도는 SDK/prompt helper용 설치의 package lifecycle이 미완이어서 gateway
시작 전에 모두 실패했다(openclaw-owned-linux). 이 표본을 성공으로 세지 않는다.

별도 private Docker volume으로 설치를 복사해 공식 npm rebuild와 native CLI
bootstrap으로 lifecycle을 완료했다. 기존 cache는 읽기 전용으로 보존했고 guard나
패키지 코드를 고치지 않았다. CLI가2026.10.9를 반환한 뒤 실행에서도 설치를 읽기
전용으로 마운트했다. 설치·실행 모두 network none, CPU2/memory3g를 유지했다.

openclaw-owned-linux-ready에서8/8 mode, 총257개 검사가 통과했다.

| Linux mode | 검사 수 |
|---|---:|
| 실행 중 취소 | 32 |
| 실행 중 확인 유실 복구 | 35 |
| native 대기열 취소 | 35 |
| native 대기열 확인 유실 복구 | 38 |
| native 요청 전 취소 | 28 |
| native 요청 전 확인 유실 복구 | 30 |
| 공개 protocol 취소·reply claim/ACK | 28 |
| 공개 protocol 확인 유실 복구·reply claim/ACK | 31 |

각 mode는 정상 실행·같은 문맥 재개·별도 문맥 분리·request replay도 먼저
검사한다. 확인 유실은 정확한 보존 출력으로 복구했고 native를 재실행하지 않았다.
모든 gatewayStopped=true, VM stopExit=0, 미실행 mode0이다. 실제 모델 추론은
0회이며 local SSE fixture만 사용했다. Native auth/config 파일은 산출물로 옮기지
않고 child의 stdout/stderr만 별도로 보존했다.

원시는 deliverables/protocol-foundation/openclaw-owned-linux-ready/의 result.json과
mode별 output/ 아래 있다. 이 결과는 Linux arm64 owned/native gateway의 경계다.
실제 모델·native UI·메신저, 일반 gateway 재시작 복구, 전체 런타임 행렬과 다른
아키텍처의 지원 완료를 뜻하지 않는다.

## 기본 목록의 첫 페이지 밖에 있는 owned 세션

기존 frontend의 재개·정지 확인은 인수 없는 sessions.list 결과에 의존했다.
Native의 기본 목록은100개로 제한되므로 오래된 owned 세션이 빠질 수 있었다.
페이지 밖의 세션을 찾는 unit을 먼저 추가했을 때 기존 코드에서
NativeSessionError로 실패했다(openclaw-exact-description-before.log).

재개는 정확한 sessionId의 sessions.resolve가 반환한 canonical key로
sessions.describe를 호출한다. 정지 확인도 결속한 key의 단건 description을 읽는다.
Key/agent 불일치·없는 description·다른 native ID/revision은 기존 검증으로
거부하며 다른 대화나 최근 목록으로 대체하지 않는다. Agent 요청의 ID/revision
검사는 유지한다. Resolve 실패 시 다른 세션을 조회하거나 private bind하지 않는다.

실제 재현은 owned script에 --crowded-profile을 지정한다. 시험용 공개 native
client로 빈 세션101개를 만들되 각 생성의 runStarted=false를 확인한다.
openclaw-exact-crowded-native의26개 검사가 통과했다. 실제 기본 목록은
count=100/limitApplied=100/hasMore=true였고 첫 owned 문맥은 없었다. 기존
resolve/list helper의 실패를 같은 실제 응답으로 재현한 후 새 frontend가 정확한
문맥을 재개했다. Native 문맥 두 개의 분리·reply 저장·request replay와 provider
fixture3회 유지도 확인했다. 빈 세션 생성에 모델 추론은 없었다.

새 조회의 실제 대기열 취소·확인 유실 복구38개는
openclaw-description-queued-native에서, 공개 protocol의 실행 중 취소·확인 유실
복구31개는 openclaw-description-protocol-native에서 통과했다. Gateway는 모두
종료했다. Description의 key 검사를 제거한 변이는 assertion1개로 검출됐다
(openclaw-description-key-mutant.log). 이 변경의 Linux 재검증은 앞선 f472d32
행렬과 구분해야 하며 아직 완료 근거로 가져오지 않는다.

이번 macOS core는 Python494+SDK52+native121+Node152=819개와 독립 mock39/
변이14개를80.638초에 통과했다(openclaw-exact-description-core.log).

9a0b086을 고정한 Linux arm64 실제 gateway 재검증도9/9 mode, 총283개
검사를 통과했다(openclaw-exact-description-linux). 빈 세션101개와 오래된 문맥의
재개26개를 추가하고 기존8개 native/public protocol 경로257개를 다시 실행했다.
모든 gatewayStopped=true, VM stopExit=0, 미실행 mode0이다. 공식 lifecycle을
완료한2026.10.9 캐시를 읽기 전용으로 재사용했으며 실제 모델 추론은0회다.
이는819개 Linux core 재실행과 구분한다.

## Frontend 종료 뒤 native 완료 결과 회수

CLI는 private bind ACK 직후 context ID/epoch, native locator와 run ID를
xsm_openclaw_bound JSONL로 기록한다. Regular stdout 파일이면 fsync한 뒤에만
agent 요청을 보낸다. 이 header는 native 실행 수락이나 완료의 증거가 아니다.
최종 결과 또는 정지 marker를 두 번째 record로 남기며, 기존 한 JSON 객체의
보존 결과도 읽는다. Header/final의 문맥·locator·run이 다르거나 frame이 중복되면
거부한다. Header에는 프롬프트·인증 값·private control capability가 없다.

공통 reconcile은 optional result recovery capability를 선언한 제공자에만
recover_result를 호출한다. 정확한 owned child의 종료와 PID/lstart 결속, owner가
보존한 예상 stdout 경로·no-follow regular file·UID를 먼저 확인한다. 제공자는
header의 문맥/세대/run과 immutable argv의 CLI·Node·agent·cwd·문맥/세대를
대조한다. 다른 세대·다른 run·살아 있는 child 또는 잘못된 binding은 native RPC
전에 거부한다. 일반 실행과 같은 공통 환경 정리·billing key 제외 정책을 사용한다.

Native 조회는 원래 run의 agent.wait와 원래 key의 sessions.describe뿐이다.
완료 receipt의 run/turn/session, 원래 lifecycle revision과 workspace가 일치해야
실제 reply text를 회수한다. Pending/timeout이나 유효한 최종 receipt가 없으면
unknown을 유지하며 agent 요청을 다시 보내지 않는다. 원래 child의 비정상 종료
코드는 보존하고 execution.recovered_from=native-host-status와 실제 receipt를
남긴다. Nonzero exit나 오류 문자열을 업무 답변으로 만드는 경로는 아니다.

OpenClaw 제공자는 execution_lifetime=native-host를 선언한다. 결속 후 frontend가
죽어도 host가 계속 실행할 수 있으므로 unknown 작업의 슬롯을 완료·정지 확인
전까지 유지한다. Child가 직접 실행을 소유하는 기존 제공자의 죽은 프로세스
슬롯 회수는 유지한다. 새 서비스의 선언이며 이전 기록에 이 능력을 소급하지 않는다.

실제 재현은 owned script의 --interrupt-frontend다. Native provider에 진입한
뒤 정확한 새 child process group만 SIGKILL했다. 살아 있는 gateway의 작업은
계속 막아 두고 reconcile이 결과를 만들지 않으며 슬롯을 유지함을 확인했다.
Fixture 응답을 푼 뒤 같은 native run의 완료 receipt로 답변을 회수했다.
원래 native ID와 exit=-9를 보존하고 outcome=None, 같은 request/reply ID의
replay를 확인했으며 native 재제출은 없었다. Gateway도 종료했다.

openclaw-frontend-native-recovery-final의36개 검사가 통과했다. 최초 native 표본은
frontend 종료만으로 슬롯이 풀리는 기존 문제 때문에 실패했다(first). Host 수명
선언을 추가한 second와 공통 환경 정리 후 final에서 각각36개가 통과했다.
기존 header 없는 종료 fixture도 먼저 unknown에 머무는 실패를 확인했다
(openclaw-native-recovery-before.log).

Slot guard를 제거한 변이는 assertion1개로 검출됐다
(openclaw-native-host-slot-mutant-final.log). 첫 변이 러너는 TempState의 module
격리 뒤 패치가 사라져 검출하지 못했으므로 성공으로 세지 않고 로그를 보존했다.
두 record 출력의 실제 공개 protocol 취소·확인 유실31개와 native 대기열
취소·확인 유실38개도 통과했다(openclaw-bound-output-{protocol,queued}-native).
실제 모델 추론은 모두0회다.

최종 macOS core는 Python494+SDK52+native125+Node152=823개와 독립 mock39/
변이14개를81.610초에 통과했다(openclaw-native-host-recovery-core-final.log).
앞선81.006초 표본은 최종 공통 환경 정리·guard 보강 전 결과다. 이 변경의 Linux,
공개 protocol의 frontend 강제 종료, gateway 자체 재시작, header가 없는 불명
실행과 성공 reply 없는 native 종료의 수명 정리, 전체 UI/모델/메신저 행렬은
계속 미완이다. 오류를 업무 실패로 합성하거나 기존 unknown 기록을 지우지 않는다.

## Native 오류 종료의 실행 lease 정리

기존 host readback은 실제 답변이 없는 오류 종료를 계속 unknown으로 유지했지만,
host 수명 lease도 계속 점유했다. 이 상태를 unit으로 먼저 재현했다
(openclaw-error-lease-before.log). Task의 불명 효과와 실행 중 여부를 분리해
정리하는 관측을 추가했다.

Native gateway에 로컬 HTTP401 거부 fixture를 연결해 실제 응답을 확인했다
(openclaw-error-settlement-shape). 같은 run의 status=error와 세션 status=failed,
lastRunId 및 inactive를 확인했지만 세션 종료와 최종 job 종료 시각은47ms 달랐다.
새 helper는 같은 시작 시각과 session_end <= final_end의 닫힌 구간을 요구하며
임의의 ms 허용 오차를 두지 않는다. ID/revision·lastRun·비활성 상태가 함께
일치해야 한다. Pending/yielded/retryable 관측은 종료 증거로 수락하지 않는다.

Provider는 body 없이 native_state=settled 관측을 반환한다. Common journal은
원래 reservation·PID/lstart·native ID·context epoch와 child 종료를 다시 확인해
native_execution.state=settled를 기록한다. 슬롯만 해제하며 task status=unknown,
result=None, reply=None과 문맥 fence는 유지한다. 취소 의도나 업무 실패를
합성하지 않는다. 오류 원문도 관측·reply에 싣지 않는다. 동일 관측의 reconcile은
idempotent다. 이 증거가 있으면 명시적 service stop은 metadata만 제거할 수
있고 원본 journal·native profile과 불명 효과는 보존한다.

실제 재현은 owned script의 --native-error다.
openclaw-native-error-settlement-first의35개 검사가 통과했다. 정상 fixture3회와
오류 요청의 HTTP 진입1회를 구분했다. 오류 후 lease 점유, native 종료 관측 후
lease 해제, reply·취소 의도 없음, replay의 비재실행, metadata 제거 후 journal
bytes 보존과 원래 sender의 retained status 접근을 확인했다. Gateway는 종료했고
실제 모델 추론은0회다.

처음 구현한 journal 호출은 _event의 지원하지 않는 keyword 때문에 unit1개가
오류였으며 기존 positional 서명으로 수정했다. 첫 core 실행에서는 별개로 SDK
fixture가 JSON을 갱신 중 읽히는 경합1개가 발생했다
(openclaw-error-settlement-core.log). Fixture 저장을 임시 파일의 atomic rename으로
바꿔 수정했으며 이를 실제 native journal 문제로 계산하지 않는다. 실패 로그는
보존했다. Native lastRun 검사를 제거한 변이는 assertion1개로 검출됐다
(openclaw-failed-settlement-mutant.log).

최종 macOS core는 Python494+SDK52+native128+Node152=826개와 독립 mock39/
변이14개를80.423초에 통과했다(openclaw-error-settlement-core-final.log).
이번 변경의 Linux·공개 protocol 오류 종료 검증과 gateway 자체 재시작,
성공 reply 없는 정상 종료·header가 없는 불명 실행 및 전체 UI/모델/메신저
행렬은 계속 미완이다.

## 공개 protocol의 frontend 종료와 native 오류 정리

공개 시험기의 --interrupt-frontend는 실제 provider 진입 뒤 정확한 child의
PID/lstart를 확인해 해당 process group만 종료한다. Native가 막힌 동안 공개
reconcile은 unknown과 lease를 유지했다. 응답을 푼 뒤 같은 native 완료 receipt로
원래 답변을 회수하고 실제 inbox claim token을 ACK했다. Exit=-9와 native ID를
보존하고 replay도 같은 reply ID를 반환했으며 native 추론 재제출은 없었다.
openclaw-public-frontend-recovery에서32개 검사가 통과했다.

--native-error는 로컬 HTTP401 거부를 사용한다. 공개 run/status에서 먼저 unknown과
lease 점유를 확인하고 공개 reconcile이 native_execution=settled만 기록했다.
Result/reply와 취소 의도는 없었으며 inbox에도 오류 답변이 없었다. Idempotent
reconcile과 request replay 비재실행을 확인했다.
openclaw-public-error-settlement에서26개 검사가 통과했다.

두 표본은 정상 fixture3회와 별도 요청의 HTTP 진입1회를 구분했고 실제 모델
추론0회, gatewayStopped=true다. 이번 변경은 시험기와 문서만이며 제품 코드는
0760bd0과 같다. 직전826개 core 결과를 재실행한 것으로 계산하지 않는다.

## 같은 소스의 Linux native·core 재검증

56c1126을 고정해 Linux arm64에서13/13 native mode, 총412개 검사가 통과했다
(openclaw-host-recovery-linux). 기존9개 경로와 직접 frontend 결과 회수36개,
직접 native 오류 정리35개, 공개 오류 정리26개·frontend 결과 회수/ACK32개를
포함한다. 같은 source의826개 core는 Python3.11.2에서65.352초,3.14.10에서
83.236초로 통과했다. 모든 gateway와 VM이 종료됐고 미실행 native mode0이다.
실제 모델 추론0회이며 archive hash와 상세 경계는 linux-validation.md에 기록했다.

## Gateway 자체 재시작의 확인된 미완 경계

2026-11-03 구현 담당 세션이 별도 profile에서 실제 native run을 완료한 뒤
gateway만 정상 종료·재시작했다(openclaw-gateway-restart-shape). 재시작 전에는
같은 run의 실제 reply와 terminal receipt가 있었으나 재시작 후 agent.wait는
status=timeout만 반환했다. 세션 description에는 같은 sessionId/lastRunId와
status=done이 남았다. Provider fixture는1회로 유지돼 native 재추론은 없었다.
Gateway는 종료했다. 이 표본은 실패로 보존하며 cold recovery 성공으로 세지 않는다.

고정 source의 agent-wait.ts도 context dedupe와 agent job snapshot 관측을
사용한다. 세션의 lastRunId/done만으로 실제 답변이나 완료 receipt를 만들지
않으며 최근 transcript를 원래 run의 결과로 추측하지 않는다. 현재 host 상태
조회 방식만으로는 이 재시작 경계를 완료하지 못했다.

같은 구현 담당자가 원래 run에 결속된 durable completion을 공개 native API에서
검증하거나, native 권한 경계를 지키는 host 관측 저장 경로를 구현한 뒤 이 표본을
재검사한다. 버전·하네스·모델을 임의 대체하거나 이 조건을 제외하는 사용자
승인은 없으므로 전체 계획과 gateway 재시작 복구는 계속 미완이다.

## Run에 결속된 durable history로 완료 결과 회수

권한을 우회하지 않고 공개 chat.history를 조회했다. 첫 조회는 sessionId를
messageId 없이 지정해 native가 거부했다(openclaw-durable-history-shape). 해당
조합을 강제하지 않고 API 서명에 맞춰 canonical key로 조회하되 결과의 sessionId와
sessionInfo의 identity/revision을 검증했다(v2). 이 API 읽기 성공을 cold recovery
성공으로 계산하지 않는다. Wait receipt는 여전히 timeout이었다.

실제 assistant record에는 __openclaw.runId와 고유 message ID·transcript source/
sequence가 남아 있었다. 고정 source의 sessions/transcript-events.ts는
attachSessionTranscriptRunId에서 assistant/tool-result의 원래 run 소유권을
붙인다. User input의 native idempotencyKey는 같은 run의 :user 키다. 모델이
본문에 쓴 run ID나 최근 assistant라는 이유로 연결하지 않는다.

Wait가 timeout이면 원래 native ID/key/agent/revision/workspace, lastRunId,
status=done, abortedLastRun=false와 inactive를 먼저 요구한다. 공개 history를
1개 단위로 역방향 조회해 해당 input까지 읽고, 같은 run의 완전한 final assistant
하나와 같은 source의 증가하는 native sequence를 확인한다. 원래 세션·실행의
닫힌 구간을 조회 후 다시 검증한다. Pending input, 다른 run/분기·중복 final·
truncated/partial 메시지는 회수하지 않는다. Terminal receipt를 합성하지 않고
native-chat.history 출처와 실제 input/assistant message ID를 보존한다.

Fixture에서 wait cache를 잃은 경우를 먼저 실패로 확인했다
(openclaw-cold-history-before.log). 최신 문구가 다른 run에 속한 canary와 원래
run ID의 답변을 구분하는 unit도 포함했다. Truncated 검사를 제거한 변이는
assertion1개로 검출됐다(openclaw-cold-history-mutant.log).

실제 재현은 --interrupt-frontend --restart-gateway이며 추가로
--crowded-profile을 지정했다. openclaw-cold-native-recovery-final의43개 검사가
통과했다. 여러 turn을 가진 같은 native 문맥에서 실제 provider 진입 후 frontend를
SIGKILL하고, native 완료 뒤 XSM에 결과를 저장하기 전에 gateway를 재시작했다.
Wait receipt 소실을 확인한 뒤 persisted run metadata로 원래 답변을 회수했다.
101개 빈 세션으로 기본 목록에서 오래된 문맥이 제외된 조건도 함께 확인했다.

원래 native ID와 exit=-9, outcome=None, request/reply ID replay를 보존했다.
Input/assistant message ID는 실제 기록이며 terminal_receipt 필드는 만들지 않았다.
정상 fixture3회와 별도 요청의 HTTP 진입1회가 전부이고 추론 재제출은 없었다.
Gateway는 종료했으며 실제 모델 추론0회다. 첫 cold recovery 표본도38개 검사를
통과했으나 초기 label의 receipt 표현은 history 출처와 구분해 최종 표본에서 고쳤다.

Mac core는 Python494+SDK52+native130+Node152=828개와 독립 mock39/변이14개를
80.533초에 통과했다(openclaw-cold-history-core.log). 이번 변경의 Linux·공개
protocol cold recovery, 실행 도중 gateway 종료, 없는 bound header·잘린/모호한
history·성공 reply 없는 정상 종료와 전체 UI/모델/메신저 행렬은 미완이다.

## 공개 protocol의 gateway 재시작 회수

공개 시험기의 --interrupt-frontend --restart-gateway를 실행했다.
openclaw-public-cold-recovery-first에서36개 검사가 통과했다. 같은 여러-turn
문맥에서 원래 frontend를 종료하고, native 완료 뒤 XSM에 결과를 저장하기 전에
gateway를 재시작했다. 원래 wait receipt가 사라진 상태를 실제 확인한 뒤 공개
reconcile이 원래 run의 persisted message ID로 답변을 회수했다.

실제 reply를 inbox에서 읽고 해당 claim을 ACK했다. 원래 native ID, exit=-9,
outcome=None과 replay의 같은 reply ID를 유지했다. Terminal receipt를 만들거나
native 추론을 재제출하지 않았다. 정상 fixture3회와 별도 요청 HTTP 진입1회,
실제 모델 추론0회, gatewayStopped=true다. 시험기와 문서만 바뀌었으므로 직전
828개 core를 반복한 결과로 계산하지 않는다. Linux 재검증은 별도 frozen source로
수행하며 아직 이 macOS 표본에 합치지 않는다.
