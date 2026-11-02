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
reset/교체가 다른 모델 문맥으로 이어지지 않도록 native 검증에 맡긴다. Cwd는
명시적으로 유지하고 permissionMode/toolOverrides/agentRuntime을 임의로 설정하지
않는다. 실제 agent RPC는 아직 이 시험에서 호출하지 않았다.

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
별도의 Linux 결과는59c59b3의786개이며 이번 계약/791개를 포함하지 않는다.
