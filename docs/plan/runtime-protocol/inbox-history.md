# Inbox 이력이 수신 지연을 늘리던 경로

상태: 로컬 코드 수정과 macOS Pi 표본 검증. 전체 런타임·Linux 인증은 미완이다.

## 영향 범위

`receive.take_inbox_claims`는 ACK된 이력에도 `handoff.claim`을 호출했다.
각 claim은 원문 폴더를 다시 읽으므로, 한 수신에서 이력이 반복 검색됐다.
`_import_handoff`도 보존한 호환 사본마다 발신자를 다시 찾고 stored 증거를
다시 기록했다. 두 경로는 일반 프로토콜뿐 아니라 같은 소비 함수를 쓰는
기존 CLI·MCP·네이티브 인수에도 적용된다.

첫 Pi 100회 실행은 160초 외부 실행 기한으로 중단됐다. 완료는 87회이며
원문은 88개(ACK 87, claimed 1)가 남았다. 13회는 완료하지 못했다.
이 표본에서는 후반 지연이 3초를 넘겼다. 100회 완료나 p95 통과로 쓰지 않는다.
실행 중이던 원문을 삭제하거나 완료 처리하지 않았다.

최초 하네스는 종료 시에만 native transcript를 파일로 썼으므로, 중단된
실행의 native RPC 원시 transcript는 복구하지 못했다. 터미널 도구 출력과
격리 상태·원문은 남았으며 `pi-native-100-interrupted.json`에 한계를 기록했다.
하네스를 수정해 원시 stdout/stderr와 표본별 JSON을 실행 중 계속 기록한다.

## 수정과 반례 검사

- 이미 있는 정본과 내용·priority·wake·수신자 증거가 모두 같은 호환 사본은
  발신자를 다시 찾거나 stored 증거를 다시 쓰지 않는다.
- 내용·priority·수신자 증거가 다르면 원래 검증 경로를 유지한다.
- ACK 등 인수할 수 없는 상태는 claim을 시도하지 않는다. 만료 인수의
  명시적 복구, 선택한 동일 소유자의 기존 인수, 소유권·세대 검사는 유지한다.
- ACK 이력 20개가 있는 실제 송수신 경로에서 기존 이력의 발신자 조회와
  claim 호출이 0회이고, 새 항목의 claim만 1회인 것을 검사했다.
- 바뀐 본문·priority·다른 수신자 증거가 조용히 무시되지 않는지 검사했다.
- 반복 발신자 조회와 반복 claim을 각각 되돌린 두 변이는 모두 검사를 실패시켰다.

## 수정 후 표본

새 격리 실행은 100회를 모두 완료했다. native `message_start`에서 본문·ID를
확인했고, 각 원문이 ACK 전에는 보존되며 명시적 ACK 뒤에만 완료됨을 확인했다.
전송 호출 시작부터 native 메시지 진입을 관찰할 때까지의 p95는 약 0.437초였다.
이는 저장→진입보다 넓은 구간이므로 해당 구간의 보수적인 상한이다.

근거: `deliverables/protocol-foundation/pi-native-100-fixed/result.json`,
`native.stdout`, `native.stderr`, `history-performance-check.log`,
`history-performance-mutations.json`.

조건은 macOS, Pi 1.4.0, 모델 미구성의 RPC 클라이언트이다. 실제 모델 회신,
사람이 보는 TUI, Linux, 전체 기능과 다른 런타임의 지연으로 일반화하지 않는다.
