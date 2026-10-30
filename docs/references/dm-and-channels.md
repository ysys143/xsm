# DM과 공유 채널을 함께 제공하는 에이전트 통신 도구

- 조사일: 2026-10-30
- 질문: 특정 에이전트에게 보내는 DM과 여러 참여자가 공유하는 채널을 함께 제공하는 플러그인·MCP 도구가 있는가?
- 대상: `ExaDev/agent-comms`, `msanchezdev/agent-bridge`, `keshrath/agent-comm`.
- 방법: 세 프로젝트의 공식 README에서 기능·배포·수신 방식 설명을 확인하고, 원격 HEAD를 조회해 아래 커밋의 README에 다시 대조했다. 이 세 프로젝트는 구현 소스 분석·설치·테스트·실제 모델 통신을 실행하지 않았다.
- 추가 설계 검토: Parley에서 배울 채널 운영 방식과 기존 xsm DM의 재사용 범위를 덧붙였다. 앞선 [Parley 조사](parley.md)의 고정 소스·관찰 결과와 xsm 관련 코드를 대조한 해석이며, 이번 추가 편집에서 제품 검사나 실제 통신을 새로 실행하지 않았다.

## 요약

세 프로젝트 모두 DM과 공유 채널을 함께 제공한다고 명시한다. `agent-comms`는 room과 DM을 피어 간 TCP 메시 위에 두며, `agent-bridge`는 프로젝트별 로컬 파일에서 `#채널`과 `@개인`을 구분한다. `agent-comm`은 중앙 서버·SQLite에 직접 메시지와 채널 메시지를 저장하고 같은 수신함에서 읽는다.[1][2][3]

따라서 DM·채널은 수신 대상과 대화 맥락의 구분이고, P2P·공유 파일·중앙 서버는 전송과 저장 방식의 구분이다. **피어 간 통신과 공유 채널을 함께 두는 설계 사례가 있다.** 이는 문서에 설명된 구조의 비교이며 해당 제품의 신뢰성·보안·운영 성숙도를 실행으로 검증했다는 뜻은 아니다.[1]

## 확인한 버전과 출처 범위

| 프로젝트 | 조사 시 원격 HEAD | 확인 문서 |
|---|---|---|
| ExaDev/agent-comms | `e8f6f1697c280aab68e43e10f3966c4beb329089` | 해당 커밋 `README.md`의 Direct messages, Room types, Durable room sends from the library, Delivery status and read receipts 및 배포 설명 |
| msanchezdev/agent-bridge | `2fd6fec44dbff3c4892848e1e7468949335c0e92` | 해당 커밋 `README.md`의 채널·DM 명령, 수신 방식, namespace·worktree, 설치 설명 |
| keshrath/agent-comm | `113b14d5193a96962c747a785a39c956279c9dfe` | 해당 커밋 `README.md`의 구조, MCP tools, 직접 메시징, dashboard 설명 |

커밋은 각 저장소에 `git ls-remote https://github.com/<owner>/<repo>.git HEAD`를 실행해 확인했고, `https://raw.githubusercontent.com/<owner>/<repo>/<commit>/README.md`를 조회했다. 아래 출처는 움직이는 main 대신 이 커밋에 고정했다. 패키지 릴리스 번호나 전체 구현의 검증 상태를 HEAD로 대신하지 않는다.

## 한눈에 비교

| 프로젝트 | DM | 공유 채널 | 전송·저장 | 배포 형태 |
|---|---|---|---|---|
| ExaDev/agent-comms [1] | `dm` action으로 특정 agent 지정 | room 생성·참여·게시·이력 조회, public/private/secret 구분 | bridge 간 TCP 메시. 기본 메시 상태는 메모리 복제, 선택적 영속 기록은 아래 별도 설명 | Claude 플러그인·MCP·하네스별 bridge |
| msanchezdev/agent-bridge [2] | `@name`, 상대와의 DM thread 조회 | `#general` 및 여러 `#channel`에 참여 | 같은 머신의 프로젝트별 공유 로컬 파일 | 스킬·Claude 플러그인 |
| keshrath/agent-comm [3] | `comm_send`의 `to`로 상대 지정 | `comm_channel`로 생성·가입·이력 조회 | Node 서버와 SQLite WAL, MCP·REST·WebSocket | MCP 서버·웹 대시보드·연동 훅 |

세 번째는 독립적인 MCP 서버 형태다. 세 도구를 모두 같은 하네스의 네이티브 플러그인이라고 부르지는 않는다.

## 1. ExaDev/agent-comms: 피어 간 메시 위의 room과 DM

공식 설명은 하네스마다 붙는 bridge가 피어 노드가 되는 통신망이다. 같은 시스템에서 개별 DM과 room 게시를 제공하며, 사람도 웹 UI를 통해 에이전트·room·대화 기록을 볼 수 있다. 첫 DM은 수신 에이전트의 수락을 기다린다. 이 절차를 xsm의 사용자 승인과 같은 계약으로 보지 않는다.[1]

하네스에 전달하는 방식은 별개다. README는 pi·Claude의 push 경로와 MCP·Codex·OpenCode의 drain 경로를 구분한다. bridge 사이에 이벤트가 전파됐다는 사실만으로 idle 모델이 깨어나 읽었다고 판정할 수 없다. `read` 상태도 bridge가 소비한 시점이며 실제 업무 완료와 다르다.[1]

저장 설명에는 범위를 구분해야 할 부분이 있다. 기본 MeshStore의 메시 상태는 메모리에 복제되지만, 라이브러리 호출자는 `durable: true`로 서명된 room-notice를 발신자의 로컬 로그에 남길 수 있다. README는 이 로그를 자동으로 알리거나 가져오는 기능이 아직 없고, 오프라인 catch-up 정책과 bridge 연결이 필요하다고 명시한다. FileStore는 모든 메시지를 영속 보관한다고 별도로 설명한다. 따라서 현재 버전을 “디스크에는 키만 남는다” 또는 “영속 room 동기화까지 완성됐다”로 요약하지 않는다.[1]

기존 [agent-comms 소스 조사](agent-comms.md)는 `a68c00f`의 2026-09-19 표본이다. 이번 README 관찰을 그 소스의 동작이나 검사 결과로 소급 적용하지 않는다. 기존 [xsm·A2A·agent-comms·ACP 비교](xsm-a2a-agent-comms.md) 역시 당시 버전의 비교다.

## 2. msanchezdev/agent-bridge: 파일 기반의 채널과 개인 대화

하나의 게시 명령에서 목적지를 `#channel` 또는 `@name`으로 고른다. 채널 구독을 좁혀도 자기 DM은 계속 받으며, 개인 대화 전체를 보는 별도 thread 조회가 있다. 프로젝트별 namespace를 사용하고 Git worktree는 같은 저장소의 공통 room으로 모은다고 설명한다. 공유 파일을 쓰므로 같은 머신을 전제로 한다.[2]

README가 설명하는 수신 방식은 Claude Code의 Monitor 같은 배경 watcher, 메시지가 올 때까지 기다리는 loop, 자연스러운 작업 지점의 poll이다. Codex·OpenCode·Copilot에는 loop/poll을 설명하며, 모든 하네스에서 같은 idle push가 가능하다고 주장하지 않는다. watcher의 안정성·복구·권한은 이번에 실행으로 확인하지 않았다.[2]

## 3. keshrath/agent-comm: 하나의 수신함에서 읽는 DM과 채널

`comm_send`가 직접 수신자·채널·broadcast·답글을 다루고, `comm_inbox`는 직접 메시지와 채널 메시지를 함께 조회한다. `comm_poll`은 새 수신 메시지를 기다리며, `comm_channel`은 채널 생성·가입·탈퇴·이력 등을 맡는다. DM과 채널의 수신 대상을 구분하면서 읽는 경로는 통합한 사례다.[3]

중앙 Node 프로세스가 MCP·REST·WebSocket을 제공하고 SQLite WAL에 기록하며, 웹 UI는 참여자·메시지·채널·공유 상태를 보여 준다고 설명한다. 파일 접근 조정 훅과 공유 상태 기능도 있으므로 메시징만 하는 도구보다 범위가 넓다. 대시보드의 실시간 갱신이나 blocking poll이 곧 하네스의 idle wake를 증명하지는 않는다.[3]

## xsm과 비교해서 참고할 점

이 절은 위 문서를 바탕으로 한 설계 해석이다. 신규 기능의 승인이나 기존 ADR 변경이 아니다.

| 관찰 | xsm에 주는 의미 | 따로 확인할 것 |
|---|---|---|
| agent-comms가 피어 간 메시 위에 room과 DM을 함께 둠 | 공유 채널 도입 자체가 P2P 모델과 충돌하지는 않음 | 멤버십·권한·순서·누락 회수·오프라인 복구 계약 |
| agent-bridge가 `#채널`과 `@개인`을 목적지로 구분 | 제품 설명에서 DM과 채널을 구분하는 명칭 참고 | 표시 이름·실제 세션 ID·대상 변경의 결속 |
| agent-comm이 DM과 채널을 같은 inbox에서 조회 | 사용자가 두 저장소를 따로 확인하는 부담을 줄이는 UX 참고 | 게시·전파·읽기 확인·업무 결과의 차이를 표시하는가 |
| 도구마다 push·drain·watch·poll이 다름 | 채널의 존재, 기록의 전파, 모델 깨우기를 별도 능력으로 다뤄야 함 | 실제 하네스·버전·idle/busy/중단 상태별 도달 |
| 메모리 복제·파일·SQLite로 보존 방식이 다름 | 같은 “채널”이라도 장애 후 보장이 다름 | 전원 종료·모든 노드 종료·재접속 때 무엇을 회수하는가 |

현재 xsm의 [채널 구현](../../xsm/channel.py)은 프로젝트별 로컬 영속 기록이며 게시가 수신 세션을 깨우지 않는다. 직접 전달은 별도 메시징 경로다. [ADR-0005](../adr/0005-channel-thread-store.md)는 멘션 깨우기를 제외한 당시 사용자 결정과 함께, 다른 기계·사람과 원본을 나눌 필요가 생기면 재검토할 조건을 남겼다. 이 노트의 세 사례는 그 재검토를 위한 비교 근거다.

Parley와의 차이는 [Parley 조사](parley.md)에 있다. Parley의 nick 접두사로 상대를 부르는 채널 대화를, 여기서 확인한 별도의 DM 목적지·개인 대화 기능과 동일하게 세지 않는다.

## Parley에서 배울 채널 설계와 기존 DM의 재사용

Parley에서 배울 중심은 **공유 대화를 운영하는 방식**이고, 기존 xsm DM에서 재사용할 중심은 **내용을 안전하게 전달하고 회수하는 방식**이다. 기록을 구성원에게 공유하는 것과 모든 에이전트를 매번 깨우는 것은 별개의 정책이다. 어느 참여자가 어떤 글을 받고 언제 반응할지는 아직 확정된 설계로 취급하지 않는다.

이 절의 Parley 근거는 `07f445c48723e446fa4d62ed068acfdf53c3f803`에 고정한 [선행 조사](parley.md)다. 아래 표는 그 구현·스킬과 관찰 결과에서 도출한 설계 참고이며, 새 기능의 구현 완료나 ADR 변경을 뜻하지 않는다.[4]

### 배울 채널 운영 방식

| Parley에서 관찰한 요소 | xsm에 적용할 설계 참고 |
|---|---|
| 사람과 에이전트가 같은 대화를 봄 | 사람이 개별 DM을 중계하지 않아도 진행·반론·질문의 맥락을 따라갈 수 있는 공유 뷰 |
| 역할별로 필요한 변화만 알림 | 다른 참여자의 작업에 영향을 주는 변경과 질문을 공유. 역할은 사람이 정하고 에이전트가 대화로 조율 |
| 정본을 먼저 쓰고 짧게 알림 | 코드·문서·결정은 원래 위치에 남기고 채널에서 변경 내용과 커밋·문서 등의 위치를 연결 |
| 연속 게시물을 묶어 전달 | 짧은 글마다 새 턴을 만드는 비용과 문맥 분절을 줄이되 묶음의 시간·크기·최대 대기 계약을 정의 |
| 반복 대화의 전달을 멈추고 사람의 개입을 기다림 | 채널 전체의 반복을 관측하고, 중단 상태와 재개 주체를 참여자에게 명확히 표시 |

Parley의 line 스킬은 불필요한 수신 인사·동의만 반복하는 게시를 피하고 작업 경계에서 메시지를 반영하도록 한다. line/table의 breaker는 자기 게시까지 세며, 시간 경과만으로 풀리지 않고 chair 발언으로 보류를 해제한다. 이는 front별 전달 제어이고 모든 게시·실행을 멈추는 전역 정지는 아니다.[4]

현재 xsm의 [트래픽 제어](../../xsm/abuse.py)는 **발신자→수신자 짝별**이며 기본값은 관찰 모드다. 따라서 A→B→C→A로 이어지는 N:N 반복이나 채널 전체의 사람 대기 상태가 이미 해결됐다고 볼 수 없다. DM 제어를 재사용하더라도 채널 집계·중단·재개 계약은 따로 정의하고 검증해야 한다.

### 기존 기능에서 재사용할 것과 새로 연결할 것

| 요소 | 기존 xsm 기반 | 채널에서 추가로 설계할 연결 |
|---|---|---|
| 세션에 전달·깨우기 | 하네스별 네이티브 전달 경로 | 어떤 구독자를 언제 깨울지, 실제 도달과 단순 기록 공유를 구분 |
| 질문·답·업무 결과 | 원 요청 ID, 상관 회신, outcome과 늦은 답 회수 | 어느 게시글·스레드에 관한 요청인지 연결 |
| 출처·권한 | peer 본문과 사용자 승인 구분, 통신 범위 검사 | 채널 가입이 어떤 읽기·게시·호출 권한을 주는지 명시. 가입을 임의 실행 승인으로 해석하지 않음 |
| 원문·수신 복구 | 영속 원문, claim·ACK, 답 회수 | 게시물 하나와 수신자별 전달·소비 상태의 연결 |
| 스레드·태그·공동 기록 | 현재 채널의 답글 관계·태그·영속 기록 | 원격 복제와 참여자별 읽은 위치, 재접속 뒤 누락 회수 |

재사용 근거는 [송신](../../xsm/send.py), [질문·회신](../../xsm/questions.py), [출처 표시](../../xsm/provenance.py), [수신](../../xsm/receive.py), [협업 권한](../../xsm/collaboration.py), [채널](../../xsm/channel.py) 구현이다. 기존 코드가 있다는 사실과 채널에서 연결·검증됐다는 사실은 구분한다.

특히 **DM 복구가 있으므로 채널 복구도 끝났다고 보면 안 된다.** 여러 머신이 같은 게시물을 중복 없이 합치고 오프라인 참여자가 빠진 기록을 회수하는 계약은 별도다. 게시물의 안정된 ID·답글 관계·정렬 기준, 구성원의 가입·탈퇴에 따른 이력 공개 범위와 수신자별 상태를 함께 정해야 한다.

### 그대로 가져오지 않을 세부 방식

- **메모리 보류와 cursor 진행의 수명 차이:** Parley의 보류 큐·gate는 메모리이며, 보류 뒤까지 cursor가 저장된 상태에서 새 Deliverer를 만들면 보류 내용을 기본 경로로 회수하지 못하는 경계를 관찰했다. 이 관찰은 합성 Stream의 API 조건이며 OS 프로세스 강제 종료 시험은 아니다. xsm에서는 원문과 보류·중단 상태의 영속 복구를 함께 다뤄야 한다.
- **등록 nick에 사람의 권위를 부여하는 규약:** 이름 인증과 특정 작업의 사용자 승인을 같은 사실로 취급하지 않는다. 기존 xsm의 요청에 결속된 승인 체계를 이어 쓴다.
- **IRC 서버와 참가용 세션 시작 절차:** 공유 대화가 필요하다는 이유만으로 Parley의 서버·새 대화 생성·개발 channel 실행 플래그까지 옮기지는 않는다. xsm의 기존 세션 등록·네이티브 전달·P2P 연결을 활용하는 설계를 검토한다.
- **table의 첫 초안 가리기와 build의 상세 협상 규약:** 독립 검토와 구현 협상이라는 특정 협업에는 참고하되 일반 채널의 공통 동작과 분리한다. table의 gate는 자기 게시 하나로 열리므로 답변의 의미상 독립성을 코드가 증명하는 것으로 쓰지 않는다.

이 네 항목의 구현·실측 범위와 한계는 [Parley 조사](parley.md)에 기록돼 있다. 별도 채널 설계에서 채택할 정책·기본값은 사용자 결정과 수용 조건을 거쳐야 한다.[4]

후속 비판적 토론은 [Channel 설계 계약 초안](../plan/collaboration/channel-design-discussion.md)에 정리했다. DM fan-out의 한계, 별도 채널 권한, 오래된 멤버십·오프라인 철회, 자동 본문 주입을 포함한 pause 경계를 반례로 검토했으며 정책·기본값과 새 채널 구현은 확정하지 않았다.

## 확인한 것과 남은 것

- 확인: 세 저장소의 원격 HEAD, 해당 커밋의 공식 README, DM·공유 채널의 명시적 인터페이스, 문서에 적힌 저장·수신 방식.
- 추가 확인: 앞선 Parley 조사와 xsm의 트래픽 제어·전달·회신·출처·채널 코드에서 채널 설계 참고와 기존 기능의 재사용 범위를 대조했다.
- 미실행: 설치·빌드·자동 검사·실제 에이전트 왕복·사용자 UI·원격/NAT·강제 종료와 복구 시험.
- 해석의 한계: 문서상 공존 사례를 확인한 것이며 xsm에 그대로 적용 가능한 구현이나 우월한 안정성을 검증한 것은 아니다. 벤치마크·토큰 절감·성능 수치는 이번 노트의 근거로 사용하지 않았다.

## 출처

[1] ExaDev/agent-comms 공식 README, `e8f6f1697c280aab68e43e10f3966c4beb329089`: https://github.com/ExaDev/agent-comms/blob/e8f6f1697c280aab68e43e10f3966c4beb329089/README.md

[2] msanchezdev/agent-bridge 공식 README, `2fd6fec44dbff3c4892848e1e7468949335c0e92`: https://github.com/msanchezdev/agent-bridge/blob/2fd6fec44dbff3c4892848e1e7468949335c0e92/README.md

[3] keshrath/agent-comm 공식 README, `113b14d5193a96962c747a785a39c956279c9dfe`: https://github.com/keshrath/agent-comm/blob/113b14d5193a96962c747a785a39c956279c9dfe/README.md

[4] Parley 선행 조사의 고정 소스: [README](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/README.md), [Deliverer와 gate](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/internal/stream/deliver.go), [line 스킬](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/skills/parley-line/SKILL.md), [table 스킬](https://github.com/colinsurprenant/parley/blob/07f445c48723e446fa4d62ed068acfdf53c3f803/skills/parley-table/SKILL.md). 해석과 기존 API 관찰은 로컬 [Parley 노트](parley.md)와 [실행 기록](parley/validation.json)을 따른다. 이번 편집에서 재실행하지 않았다.
