# OpenClaw owned 실행 전 native 세션 결속

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
local/messenger 경계 검증이다. 제공자 catalog에는 아직 OpenClaw를 등록하지
않았다. 이 범위를 줄이거나 지원 완료로 표시하지 않는다.

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

이 transport와 frontend는 아직 provider catalog와 실제 owned journal에 연결하지
않았다. 전체 지원이나 취소·복구 완료로 계산하지 않는다.

최종 macOS 핵심 검사는 Python494+SDK52+native105+Node152=803개와 독립 mock39/
변이14개를80.708초에 통과했다(openclaw-sdk-transport-core-final.log). 앞선
79.948초 표본은 특정 exec 거부 boolean을 추가하기 전 결과로 따로 보존했다.
이번 native transport4개를 포함한 Linux 검증은 아직 미실행이다.
