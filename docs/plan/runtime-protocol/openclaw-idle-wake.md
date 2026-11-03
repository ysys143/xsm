# OpenClaw 유휴 wake 연결 조사

상태: 고정2026.10.9 SDK 계약을 읽은 조사다. 새 wake 구현·실행 검증은 아직 없다.
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
실제 실행에서 이 target fence가 새 대화로의 이동을 막는지 아직 확인하지 않았다.

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
