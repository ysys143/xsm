# OpenClaw 유휴 wake 연결 조사

상태: 고정2026.10.9 SDK의 실제 plugin 실행 경계를 검증했다. 제품 wake 연결은 미완이다.
현재 `context-queue.mjs`는 lifecycleRevision에 결속된 next-turn queue commit을
확인하지만 실제 turn을 시작하지 않는다. 기존 queue100개 검사를 idle wake
검증으로 계산하지 않는다.

## 고정 package에서 확인한 경계

공개 PluginRuntime의 `agent.runEmbeddedAgent`는 native
`runPluginEmbeddedAgent`에 연결된다. 이 함수는 실제 plugin runtime scope의
pluginId를 요구하며, 호출자가 admittedRunContext/preparedRunAdmission 같은
host authority를 공급하면 거부한다. 실행 ingress는 plugin/plugin-runtime으로
기록되고 native admission을 통해 실행된다. 이 소유 경계를 재사용할 후보로 둔다.

공개 params의 sessionTarget에는 agentId/sessionId/sessionKey/storePath와
expectedLifecycleRevision이 있다. expectedWriterRunId는 내부 writer claim이므로
임의로 만들어 전달하지 않는다. InputProvenance는 inter_session을 지원한다.
실제 standalone plugin 실행에서는 이 필드만으로 원하는 fence가 성립하지 않았다.
아래 실행 표본과 구별한다.

`system.requestHeartbeat`의 공개 요청에는 route/agent/store와 source/intent가 있지만
expected SID/revision 필드는 없다. 이 타입만으로 기존 대화에 결속된 wake를
증명할 수 없다. 비동기 heartbeat 예약 성공을 queue receipt로 쓰지 않는다.

`onUserMessagePersisted`와 queue/lifecycle 관측 callback은 존재하지만 호출 시점과
보장 범위가 다르다. Native source에서 실제 호출 순서를 확인하고, 실제 SDK
실행에서 callback→provider 순서와 target readback을 비교해야 한다. Model 완료까지
deliver callback을 막으면 ACK 뒤 admitted report가 실행될 수 있으므로 완료 promise를
그대로 queue acceptance로 바꾸지 않는다.

## 다음 실행 표본의 기준

임시 profile의 실제 plugin loader와 backend gateway RPC로 plugin-owned 함수를
호출한다. 명시적 localhost scripted provider만 쓰고 실제 계정·구독 모델·메신저는
이 표본에서 부르지 않는다. 실제 기존 session을 생성한 뒤 같은 target의 실행과
stale expectedLifecycleRevision 거부를 비교한다. 거부 표본은 persistence callback과
provider 요청이 모두0이어야 한다. 성공 표본에서는 callback 시점의 native SID/
revision과 실제 provider 원문을 확인하고 plugin lifecycle 종료도 검증한다.

실행 scope 보존은 기존 api.lifecycle.runInBackgroundContext와 함께 실제로
확인한다. Model tool caller나 agent exec를 backend operator로 승격해 우회하지
않는다. Product의 기존 queue commit·untrusted 원문·FYI 무깨우기·별도 ACK를
유지한 채 native wake와 연결해야 한다. API 이름이 있다는 이유로 완료라 하지 않는다.

검토한 고정 package의 주요 경로는 dist/config-contracts-DzLaG7FV.d.ts,
dist/runtime-BYO1NOXw.mjs, dist/runtime-embedded-agent.runtime-Bf_SKDe_.mjs다.
각각 PluginRuntimeCore/RunEmbeddedAgentParams, runtime method 연결,
runPluginEmbeddedAgent의 scope·authority 검사를 확인했다. Source hashes는
`deliverables/protocol-foundation/openclaw-wake-api/source-audit.json`에 보존한다.

## 실제 SDK 실행 — 2026-11-04

`scripts/probe-openclaw-wake-spi.py`는 실제 등록 plugin의 gateway method 안에서
공개 runtime API를 호출한다. 새 HOME/XSM_HOME/OPENCLAW_STATE_DIR/workspace만
사용하고, native2026.10.9/Node24.22.2와 localhost scripted provider를 실행한다.
Docker network=none이고 실제 서비스·모델·제품 XSM 수신 연결의 증거는 아니다.

단독 third 표본에서 기존 실제 session의 SID와 일부러 다른 expected revision을
SDK에 전달했는데, SDK가 원문을 저장하고 provider까지 호출했다. Callback readback은
SID 일치/revision 불일치였다. 따라서 이 인수만으로 기존 실행 세대를 보장할 수
없다. 내부 성격 필드를 임의 호출한 이 표본을 SDK 전체의 보안 결함으로 확대하지 않는다.
그 실행은 의도한 fence 검사를 실패했고 valid 사례는 미실행으로 남았다.

`--guarded-admission` 표본은 공개 runWithWorkAdmission 안에서 최신 SID/revision을
확인하고, native가 제공한 admission signal을 SDK run에 전달한다. 이 경우 stale은
adapter 측 snapshot guard에서 거부된다. 이를 SDK 자체 revision 검사 성공으로
보고하지 않는다. 정확한 revision의 실행은 실제 원문 callback→provider 순서를
통과했고 callback readback의 SID/revision도 일치했다.

Race 표본은 세대 확인 뒤 SDK 호출 직전에 barrier를 둔다. 별도 backend RPC로
실제 sessions.reset을 실행하자 native admission signal이 aborted가 됐다. Plugin
root controller는 aborted가 아니었다. Barrier에서 돌아와 SDK를 호출했지만 native
취소 검사가 persistence callback과 provider 양쪽을 막았다. Guarded 표본은8개
checkpoint/20.641초를 통과했고 gatewayStopped=true/VM stopExit=0이었다.
이 경로가 XSM context queue와 ordinary idle wake로 연결된 것은 아직 아니다.

## 실패와 실행기 정리

First는 생성 JavaScript 문자열의 newline escape 오류로 plugin 로드에 실패했다.
Raw template과 gateway 시작 전 node --check로 보완했다. SDK fence에는 도달하지
못한 실패이며 원시는 보존했다.

실행기 복사 시 불필요한 후속 전체 core loop가 남아 있었고, 첫 실행기의 종료 전에
두 번째를 시작하는 운영 오류가 있었다. 같은 임시 VM의 controller2개/container2개가
겹쳤다. 두 controller에 SIGINT해 모두 terminal을 확인했고, private VM p의 Stopped
상태와 잔여 해당 container/process 없음도 확인했다. First stopExit=1/second=0을
숨기지 않는다. 겹친 실행의 결과는 완료 근거에서 제외했다. 사용자 설정·계정·제품
code에는 변경이 없다.

이후에는 core loop를 제거한 SPI1건 전용 runner를 읽어 확인하고, private VM의
exclusive lease와 이전 terminal/stopExit 확인을 함께 사용했다. 단독 third와
guarded 표본은 각각 stopExit=0이다. Source는1402559 base에 probe overlay SHA와
archive SHA를 기록한 실행이며 pristine base로 표시하지 않는다. 실패·동시 실행·
단독 재검증 원시는 `deliverables/protocol-foundation/openclaw-wake-spi-linux-*`와
`openclaw-wake-api/`에 구분한다.
