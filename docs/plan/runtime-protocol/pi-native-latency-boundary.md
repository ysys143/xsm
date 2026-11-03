# Pi native 지연 관측 경계

상태: 관측 경계를 조사했다. 새 canonical store→native queue 100표본은 미실행이다.
기존 Pi/OpenCode probe의 상한 값은 보존하며 이번 측정의 결과로 바꾸지 않는다.

`probe-pi-protocol.py`는 operation.call 전 perf_counter부터 RPC message_start 수신까지,
`probe-opencode-protocol.py`는 송신 전 monotonic부터 native transcript 조회까지를 잰다.
두 값 모두 프로토콜 호출·관측 지연을 포함한 상한이며, canonical store와 native queue
수락 각각의 원시 tick을 기록한 결과는 아니다.

## 고정 Pi 1.4.0의 실제 분기

로컬에 준비된 패키지의 agent-session.js와 session-manager.js를 직접 읽었다.
원본4개 파일의 SHA256과 sendCustomMessage 주변 코드를
`deliverables/protocol-foundation/pi-native-latency-boundary/`에 보존했다.

- 유휴·triggerTurn true는 `_startRun`으로 들어간다. agent 이벤트는 extension/public
  listener에 전달된 후 message_end에서 sessionManager에 저장된다. 따라서
  message_start를 전사 저장 완료로 부를 수 없다.
- 유휴·무깨우기는 `_appendCustomMessage`가 실제 appendCustomMessageEntry와
  finalized context 갱신 후 message_start/message_end를 낸다.
- streaming steer/followUp, nextTurn, settled 중 deferred action은 별도 분기다.
  유휴 wake 표본으로 다른 분기의 인계도 인증했다고 표시하지 않는다.
- appendCustomMessageEntry는 `_appendEntry` 후 실제 entry.id를 반환한다. 이는
  전사 commit 관측 후보이며, wake 경로에서 필요한 입력 큐 수락 경계와의 관계는
  `_startRun`·native agent의 enqueue 구현까지 더 확인해야 한다.

## 후속 측정에서 필요한 증거

송신은 기존 protocol_timed_host의 실제 handoff.store 성공 반환 관측을 사용한다.
수신은 고정 native 실행의 실제 큐 수락 경계를 관측하고 원래 메서드에 위임한다.
송수신 clock domain을 먼저 정렬하며 stdout·RPC 응답만으로 commit을 만들지 않는다.
표본마다 원문 ID/native item·현재 세션과 idle을 대조하고 명시적 ACK 후 다음 표본을
시작한다. 두 OS 각각100개, 실패·미실행 보존, 원시 p95 재계산과 관측 제거 변이까지
필요하다. SDK 직접 호출과 설치된 CLI 경로의 인증 범위도 구분한다.

이 조사는 새 latency 합격이나 실제 모델/UI 검증이 아니다. 원래 전체 계획은 미완이다.
