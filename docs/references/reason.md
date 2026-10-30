# Reason Network 비교 노트

- 조사: 2026-10-23 ~ 2026-10-24
- 목적: xsm의 협업·원격 설계(ADR-0015 ~ ADR-0024)가 Reason Network에서 무엇을 배웠고 무엇을 따르지 않았는지 남긴다.
- 근거: Reason의 [공식 문서](https://reasonmachines.com/network), 공개 엔진 소스([reason-machines/reason-network](https://github.com/reason-machines/reason-network), MIT OR Apache-2.0), 두 도구를 같은 저장소에서 함께 써 본 기록.

## 범위와 공개하지 않는 것

Reason은 공개 엔진(Rust)과 공개 소스가 아닌 CLI로 이뤄진다. 이 노트는 공개 엔진의 소스와 공식 문서, 일반 사용에서 관찰한 동작만 근거로 쓴다. 공개되지 않은 CLI와 계정 서버의 내부 구현은 이 저장소에 싣지 않는다. 설계 판단에 쓴 세부 조사 기록은 저장소 밖에 보관한다. xsm은 Reason의 코드를 가져오지 않았다. 향후 공개 엔진 코드를 재사용한다면 그 라이선스와 NOTICE, 수정 이력을 보존해야 한다.

비교한 엔진 버전은 v0.12.10(`72ca2b3`)과 v0.12.11(`b3557ff`)이며 두 버전의 결과를 섞지 않았다. xsm 쪽 기준은 0.4.20(`b29b39c`)이다. 공개 엔진의 upstream 검사는 0.12.10에서 195개, 0.12.11에서 202개가 통과했다. 이 결과는 엔진 자체 검사이며 실제 하네스나 물리 머신 간 동작을 보증하지 않는다.

## 배운 것과 xsm의 결정

| 영역 | Reason에서 관찰한 것 | xsm의 대응 |
|---|---|---|
| 참여와 권한 | 기기가 팀에 가입하면 등록된 세션을 디렉터리에서 바로 고를 수 있다. 편하지만 그만큼 가입 범위가 넓다. 머신 키, 초대, 계정 증명, 멤버십, 작업 권한은 서로 다른 사실이다 | 발견 후보는 사용자가 공개한 세션과 같은 저장소 세션으로 한정하고, 선택은 그 대화 한 쌍에만 결속한다. 가입·공개·협업·파일 권한을 분리한다 ([ADR-0015](../adr/0015-connection-intent-and-participation.md), [ADR-0024](../adr/0024-discover-select-and-handshake.md)) |
| 업무 디렉터리 | repo/branch, busy/idle 지속 시간, 하고 있는 일, 수신 등급을 보여 준다. 하고 있는 일은 런타임 기록에서 추출한다 | 머신·업무·branch로 찾고, 각 값의 출처와 신선도를 함께 표시한다. 읽지 못한 값은 unknown으로 둔다 ([ADR-0017](../adr/0017-directory-and-session-lifecycle.md)) |
| 질문과 답 | 질문 한 번에 실제 답까지 돌려준다 | `ask`가 요청 ID를 돌려주고 `question-status`로 늦은 답도 회수한다. 답은 요청 ID로만 짝짓는다 ([ADR-0016](../adr/0016-agent-messaging-interface.md)) |
| 이름과 수명 | 대화 ID가 있는 세션의 이름은 일정 기간 보존되지만, 프로세스 기반 주소는 재시작한 다른 프로세스에 이름과 미독을 넘길 수 있다 | 이름·프로세스·대화의 지속성을 나눈다. 이름만 같은 새 대화는 승인과 미독을 물려받지 않는다 ([ADR-0017](../adr/0017-directory-and-session-lifecycle.md)) |
| 전달 증거와 복구 | 메시지 ID로 중복 저장을 막고, 명시적 Delivered 확인 전까지 미독으로 남기며, 전달 중 중복 노출을 억제하고, 재접속 뒤 재등록한다 | 저장·런타임 전달·읽은 뒤 수신 확인·실제 답을 별도 증거로 보고한다. 응답을 잃으면 같은 ID로 조회하고 새 ID로 재전송하지 않는다. 메시지 중복 제거를 작업의 exactly-once로 취급하지 않는다 ([ADR-0018](../adr/0018-delivery-evidence-and-recovery.md)) |
| 조용한 알림 | FYI는 깨우지 않고 저장한다. 다만 함께 써 본 기록에서는 FYI가 나중에도 미독으로 남은 표본이 있었다 | `--wake never`로 저장만 하고, 상대의 다음 자연스러운 턴이나 MCP 읽기에서 회수하게 한다 |
| 자료 사본 | 작은 사본을 본문과 함께 보내고, 수신 측 디렉터리·파일명·용량을 검사한다. 지원하지 않는 상대에게는 본문으로 풀거나 명시적으로 거절한다 | 첨부는 스냅숏 사본이고 원본을 건드리지 않는다. 지원하지 않는 상대는 거절하며 본문 대체는 사용자가 고를 때만 한다 ([ADR-0019](../adr/0019-message-context-attachments.md)) |
| 사람의 판단 | 사용자 질문은 동료 요청 원문을 먼저 보여 주고, 질문·본 내용·답·시각을 묶어 기록한다. 같은 질문은 기존 창을 기다린다 | 질문과 답을 원문으로 남기고, 같은 결정의 재시도는 같은 기록을 잇는다. 동료 메시지는 사용자의 승인이 아니다. OS 알림 호출 성공을 사람이 봤다는 증거로 쓰지 않는다 ([ADR-0020](../adr/0020-human-decisions-and-attention.md)) |
| 원격 네트워크 | 기기별 iroh endpoint와 공개키, LAN·NAT 통과·HTTPS relay를 쓴다. 서명된 멤버십 기록을 복제하고 활성 멤버만 통신시키며, 누구나 초대·제명하는 신뢰 팀 모델이다 | 자체 P2P를 기본으로, 공개 relay와 자체 relay, 선택적 Tailscale 경로를 둔다. 관리자 계층 없는 동등 멤버 모델을 따르되 기존 SSH와 로컬 경로를 유지한다. 엔진 바이너리를 backend로 채택하지는 않았다 ([ADR-0021](../adr/0021-cross-machine-network-and-membership.md)) |
| 오용 제어 | 본문의 예약 표시 위조를 렌더링에서 막고, 반복·속도·그룹 제한을 둔다 | 권위·권한·행동을 따로 검사한다. 트래픽은 기본 관찰만 하고 명시한 한도로만 막는다. 그룹 금지는 따르지 않는다 ([ADR-0022](../adr/0022-peer-authority-and-abuse-controls.md)) |
| 설치와 운영 | 설정 병합·백업·원자적 교체·권한 유지와 doctor를 제공한다. 새 등록이 이미 떠 있는 세션에 즉시 적용되지는 않는다 | 설치 성공과 첫 실제 왕복을 구분해 보고하고, xsm이 소유한 항목만 갱신·제거한다 ([ADR-0023](../adr/0023-runtime-adapters-and-operability.md)) |

## 따르지 않은 선택

- 데몬을 로컬 메시징의 필수 전제로 두지 않는다. 계속 떠 있는 프로세스는 선택적 P2P 서비스뿐이다.
- 실행 풀 상한, 그룹 대화 금지, 자동 업데이트 같은 기본값을 그대로 옮기지 않는다.
- 저장 형식을 SQLite로 바꾸는 결정은 하지 않았다.
- 이미 xsm에 있던 이름 주소, N:N 대화, 수신 영수증, 사용자 원문 기록을 새 기능처럼 다시 만들지 않는다.

## 함께 써 본 기록

같은 저장소에서는 두 도구 모두 왕복에 성공했다. 새 저장소의 세션과는 Reason이 별도 설정 없이 왕복했고, 이 편의가 ADR-0024의 "업무로 찾고 고른 상대와 연결" 흐름의 출발점이 됐다. 일반 Codex 세션으로 보낸 표본에서는 xsm이 분석·회신까지 성공했고 Reason은 전달 문구를 돌려준 뒤에도 미독으로 남았다. 원인은 단정하지 않았다. 원시 기록은 [공존 비교](../../deliverables/xsm-reason-live-comparison-2026-10-23/evidence.json), [실사용 근거](../../deliverables/reason-workflow-experience/evidence.json), [설치 평가](../../deliverables/reason-network-evaluation-2026-10-23.md), [양방향 비평 검증](../../deliverables/adversarial-cross-review-2026-10-23/verification.json)에 있다.

## 출처

- [Reason Network 공식 소개·FAQ](https://reasonmachines.com/network), [공식 에이전트 설치 안내](https://reasonmachines.com/network/skill.md)
- 공개 엔진 v0.12.11 [소스](https://github.com/reason-machines/reason-network/tree/b3557ff454cd26a04c2a18804ba83ae5db8b119d): [MCP](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/mcp.rs), [디렉터리](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/directory.rs), [송수신](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/mail.rs), [저장소](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/store.rs), [첨부](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/files.rs), [사용자 질문](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/daemon/ask.rs), [멤버십](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/team.rs), [P2P·relay](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/net.rs), [설치](https://github.com/reason-machines/reason-network/blob/b3557ff454cd26a04c2a18804ba83ae5db8b119d/src/setup.rs)
- 두 엔진 버전의 [차이](https://github.com/reason-machines/reason-network/compare/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690...b3557ff454cd26a04c2a18804ba83ae5db8b119d)
