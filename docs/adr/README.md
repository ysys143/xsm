# Architecture Decision Records

`INTENT.md`의 요구에 따라, ADR은 **여러 차례의 토론 라운드**를 거쳐 확정한다.

## 상태

| 상태 | 의미 |
|---|---|
| Proposed | 질문과 선택지를 정리한 상태. 토론 전 |
| Discussing | 토론 라운드 진행 중 |
| Accepted | 결정됨. 결정과 근거가 기록됨 |
| Superseded | 다른 ADR로 대체됨 |
| Deferred | 사용자가 범위 밖으로 미룸. 다시 열 조건을 결정 절에 적는다 |

## 토론 라운드 절차

1. **Round 0 (근거 수집)**: 레퍼런스 조사(`docs/references/`)와 스파이크(`docs/plan/README.md` 5장) 결과를 ADR의 "근거" 절에 링크한다.
2. **Round 1..N (토론)**: 참가자마다 입장, 근거, 반론을 "토론 기록" 표에 한 줄씩 남긴다. 참가자는 사람, Claude 세션, Codex 세션이다.
   - 각 라운드는 이전 라운드의 반론에 답해야 한다.
   - 새 근거가 없으면 같은 주장을 반복하지 않는다.
3. **라운드 종료 조건**: 다음 중 하나가 성립하면 라운드를 끝내고 결정 단계로 간다.
   - 참가자 전원이 새 근거 없이 입장을 반복한다.
   - 결정을 가르는 사실이 스파이크나 조사로 확정됐다.
   - 3라운드를 넘겼다. 이때 남은 쟁점을 "미해결"로 적고 사용자에게 넘긴다.
4. **결정**: 사용자가 결정한다. 에이전트의 합의는 권고일 뿐 결정이 아니다. 결정 절에 선택지, 이유, 기각한 선택지와 그 이유를 적고 상태를 Accepted로 바꾼다.

## 목록

| ADR | 제목 | 상태 | 관련 목표 |
|---|---|---|---|
| [0001](0001-session-registry.md) | 세션 레지스트리 위치와 형식 | Accepted | G1, G2 |
| [0002](0002-delivery-and-wakeup.md) | 에이전트별 전달·wakeup 방식 | Accepted | G2, G3 |
| [0003](0003-no-wrapper-runtime-boundary.md) | 진입점 래퍼 금지의 경계 | Accepted | C1 |
| [0004](0004-communication-scope.md) | 통신 범위(scope) 모델 | Accepted | G5 |
| [0005](0005-channel-thread-store.md) | 채널-스레드 기록 저장소 | Accepted (제거 예정, 0026) | G6 |
| [0006](0006-shared-document-editing.md) | 공동 문서 편집 규약 | Accepted | G7 |
| [0007](0007-remote-transport-and-trust.md) | 원격 통신과 신뢰 모델 | Accepted | G4 |
| [0008](0008-session-naming-and-namespace.md) | 세션 이름, 주소, 네임스페이스 | Accepted | G1, G2, G5 |
| [0009](0009-session-trust-handshake.md) | 세션 간 신뢰 수립(핸드셰이크) | Superseded | G1, G2, G4, G5 |
| [0010](0010-workers.md) | 워커를 띄우고 끝내는 일의 경계 | Accepted | C1 |
| [0011](0011-telemetry-without-an-sdk.md) | SDK 없이 관측 가능하게 만들기 | Accepted | G2, G3, C1 |
| [0012](0012-who-picks-the-next-node.md) | 여러 세션이 한 문제를 나눠 풀 때, 다음 노드는 누가 고르는가 | Proposed | G3, G6, G7, C1 |
| [0013](0013-native-claude-messages-by-scope.md) | Claude 네이티브 피어 메시지를 범위로 판정한다 | Accepted | G2, G5, C1 |
| [0014](0014-shared-board.md) | 공유 메시지 풀과 시각 대시보드 | Discussing | G4, G6 |
| [0015](0015-connection-intent-and-participation.md) | 연결 의도와 참여 범위를 실행 가능한 계약으로 잇는다 | Proposed | G1, G2, G5 |
| [0016](0016-agent-messaging-interface.md) | 에이전트의 요청과 응답을 일관된 도구 계약으로 제공한다 | Proposed | G2, G3, G6, C1 |
| [0017](0017-directory-and-session-lifecycle.md) | 업무로 세션을 찾고 대화 신원을 유지한다 | Proposed | G1, G2, G5 |
| [0018](0018-delivery-evidence-and-recovery.md) | 전달 증거와 메시지 복구를 같은 수명 계약으로 관리한다 | Proposed | G2, G3, G4 |
| [0019](0019-message-context-attachments.md) | 메시지에 필요한 자료 사본을 명시적으로 전달한다 | Proposed | G2, G4, G6, G7 |
| [0020](0020-human-decisions-and-attention.md) | 사람의 판단 원문을 보존하고 중복 질문과 알림을 조절한다 | Proposed | G2, G5, G6 |
| [0021](0021-cross-machine-network-and-membership.md) | 원격 연결의 편의와 머신 인증을 분리된 전송 계약으로 제공한다 | Accepted | G4, G5, C1 |
| [0022](0022-peer-authority-and-abuse-controls.md) | 동료 입력의 권위와 통신 오용을 분리해 제어한다 | Proposed | G2, G5, G6 |
| [0023](0023-runtime-adapters-and-operability.md) | 설치와 하네스 어댑터의 생명주기를 검증 가능하게 만든다 | Proposed | G1, G2, G3, G4, C1 |
| [0024](0024-discover-select-and-handshake.md) | 공개된 후보를 찾고 선택한 세션과 협업한다 | Accepted | G1, G2, G4, G5 |
| [0025](0025-team-and-multi-recipient-dm.md) | 함께 일하는 세션을 팀으로 묶고 DM을 여러 수신자에게 보낸다 | Accepted | G1, G2, G3, G5, G6 |
| [0026](0026-team-board-on-xsm-doc.md) | 팀 보드는 xsm doc이 소유하고 channel은 대체 뒤 제거한다 | Accepted | G6, G7 |

[ADR-0025](0025-team-and-multi-recipient-dm.md)와 [ADR-0026](0026-team-board-on-xsm-doc.md)은 2026-10-30 사용자 결정으로 Accepted다. 구현은 착수하지 않았다. 0025는 ADR-0024의 connect 의미를 바꾸고, 0026은 0005를 대체가 준비되면 제거하도록 정하며 0006을 확장하고 0014의 에이전트용 공유 기록 부분을 정한다. 결정의 배경과 실험은 [설계 메모](../plan/collaboration/team-communication-memo.md)에 있다.

[ADR-0024](0024-discover-select-and-handshake.md)는 2026-10-28 사용자 결정으로 Accepted다. 발견 후보·공개·선택·핸드셰이크에 관해 0015–0023의 관련 제안을 보완하며, 나머지 미결까지 일괄 채택한 것은 아니다. 구현목표는 [확정 설계](../plan/collaboration/collaboration-contract.md)를 따른다.

ADR-0021은 2026-10-29 사용자 결정으로 자체 P2P·선택적 Tailscale 경로·Reason식 동등 멤버십 요구사항을 확정했다. 이는 구현 완료나 실제 네트워크 변경 승인이 아니다. 나머지 ADR 상태는 위 표를 따른다.

0015–0023은 Reason Network 비교 조사를 반영한 제안이다. 무엇을 배웠고 무엇을 따르지 않았는지는 [Reason 비교 노트](../references/reason.md)에 있다. 기존 Accepted ADR과의 관계는 각 결정의 적용 범위를 따른다. ADR-0021은 신규 원격 경로의 SSH 필수 전제만 바꾸며 기존 SSH 기능과 로컬 경계를 보존한다.

새 ADR은 [TEMPLATE.md](TEMPLATE.md)를 복사해 만든다.
