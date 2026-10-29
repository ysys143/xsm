# Reason Network 조사

조사 기준: 2026-10-23 KST. 질문: Reason Network는 무엇을 연결하고, 어떤 방식으로 동작하며, 실제 활용 범위와 한계는 무엇인가?

## 요약

Reason Network는 팀원들의 컴퓨터에서 실행 중인 코딩 에이전트 세션을 찾아 서로 메시지를 주고받게 하는 도구다. Claude Code가 동료의 Codex에 구현 내용을 묻거나, 다른 컴퓨터의 에이전트에 작업을 요청하는 용도다. 세션 목록에는 사람·컴퓨터·저장소·브랜치·작업 상태가 표시된다. [1]

핵심 가치는 이미 실행 중인 여러 에이전트에 연락할 수 있다는 점이다. 공개 엔진은 무료이며 MIT OR Apache-2.0으로 배포된다. 설치와 로그인을 돕는 Reason CLI는 비공개이고, Reason 클라우드 세션의 비용은 별도다. [2]

조사 판단: 소규모 팀에 유용한 통신 기반이다. 자동 파일 충돌 경고는 설계 문서의 후속 계획에 있다. [3]

## 현재 공개 상태

| 항목 | 확인 내용 |
|---|---|
| 개발 주체 | Reason Machines, `reason-machines/reason-network` |
| 구현 언어 | Rust |
| GitHub 저장소 생성 | 2026-10-16 15:34 UTC, 한국 시간 10-17 00:34 |
| 최신 릴리스 | `v0.12.9`, 2026-10-23 01:10 KST |
| 조회 당시 규모 | GitHub 별 1,080개, 포크 87개 |
| 소스 검토 기준 | 커밋 `039b9571dab11f980813918b60a827b8bb27fbfd` |

저장소 메타데이터와 최신 커밋은 GitHub API, 릴리스는 공식 릴리스 페이지에서 확인했다. 수치는 조회 시점의 값이다. 저장소 공개 기간은 약 일주일로 짧지만, 이를 전체 개발 기간으로 해석할 수는 없다. [4][5][6]

`v0.12.9`의 변경 사항에는 같은 밀리초에 보낸 메시지의 순서 보정이 포함된다. 변경이 활발한 초기 프로젝트라는 점과 장기 운영 안정성이 검증됐는지는 구분해야 한다. [5]

## 제공 기능

에이전트에 노출되는 MCP 도구는 다음 네 종류다. [7]

| 도구 | 역할 |
|---|---|
| `list_team` | 사람·컴퓨터·에이전트·저장소·브랜치·상태를 보고 수신 세션 선택 |
| `send_message` | 특정 세션에 메시지와 작은 텍스트 파일 전달 |
| `check_inbox` | 해당 세션의 수신 메시지 조회, 응답 대기 |
| `ask_user` | 로컬 사용자의 승인·거절을 팝업으로 요청 |

`ask_user`는 로컬 컴퓨터의 사용자에게 묻는다. 동료의 요청 ID를 연결하면 원래 요청을 함께 보여주고, 그 답변을 컴퓨터 키로 서명해 요청자에게 전달하는 경로가 있다. 이 승인은 해당 컴퓨터가 기록한 응답이라는 의미이며, 컴퓨터 자체가 장악된 상황까지 신원을 보장한다는 뜻은 아니다. [8][3]

첨부는 텍스트 파일 최대 10개, 파일당 256 KiB, 합계 512 KiB다. 에이전트의 첨부 경로는 작업 저장소 또는 작업 폴더 안으로 제한하며 숨김 파일과 주요 자격증명 폴더를 제외한다. 받은 파일은 별도 수신 폴더에 저장하고 자동 실행하지 않는다. 일반적인 대용량 파일 전송이나 저장소 동기화 용도는 아니다. [9]

## 통신 구조와 지원 범위

각 컴퓨터의 Rust 데몬에 로컬 MCP·훅이 연결되고, 컴퓨터끼리는 iroh 기반 QUIC로 통신한다. LAN 직접 연결이나 인터넷 연결을 시도하고, 필요하면 HTTPS 릴레이를 사용한다. 기본 릴레이는 Reason이 운영하며 자체 릴레이 설정도 지원한다. 따라서 직접 운영해야 할 중앙 메시지 서버는 없지만, 기본 경로에는 릴레이 인프라가 존재한다. [10]

컴퓨터 간 통신은 종단간 암호화하며 기본 주소 탐색에는 n0를 사용한다. 자체 릴레이 설정 시 네트워크 계층은 그 릴레이와 LAN 탐색을 사용한다. 로그인·업데이트·호스팅 봇의 외부 의존성은 별개다. [3]

설계 문서상 수신 방식은 다음과 같다. 실제 동작은 실행 검증하지 않았다. [3]

| 에이전트 | 전달 방식 |
|---|---|
| Claude Code, Codex, opencode, pi, Reason | 작업 중 메시지 전달 및 유휴 세션 깨우기 지원 |
| Cursor, Gemini CLI, Copilot CLI, Grok CLI | 다음 도구 호출이나 턴 종료 등에서 전달 |
| DeepSeek Harness, 일반 MCP 클라이언트 | 받은편지함 조회 시 확인 |

Grok Bot·Muse·ChatGPT 같은 호스팅 어시스턴트는 원격 MCP 서버로 연결한다. 공식 사이트도 이 경로는 Reason 서버를 거친다고 구분한다. 컴퓨터 사이의 암호화 경로 설명을 호스팅 봇의 전체 경로에 그대로 적용해서는 안 된다. [1][2]

## 보안과 운영에서 중요한 점

### 신뢰하는 팀원을 전제로 한 권한 구조

팀 상태 코드에는 모든 구성원이 컴퓨터를 추가·제거하고 초대할 수 있다고 명시돼 있다. 설계 대상도 서로 신뢰하는 팀원이며, 적대적인 내부자를 전제하지 않는다. 제거된 컴퓨터의 연결 차단과 그 컴퓨터가 가진 모든 암호학적 권한의 무력화는 구분된다고 설명한다. 기업의 관리자·일반 사용자 권한 분리와 동일하게 평가하기 어렵다. [11]

팀 링크는 교체 전까지 반복 사용할 수 있는 초대 수단이다. 링크 재발급 시 기존 초대가 만료되도록 구현돼 있다. 따라서 링크의 전달 범위가 네트워크 가입 범위에 영향을 준다. [11]

### 기본 수신 정책과 정보 공유

팀 메시지는 기본 `accept`이며, `hold`와 `refuse`도 지원한다. 전체 작업 경로 공유인 `share_paths`와 Reason Network를 로드하지 않은 Claude 세션 공유인 `share_unmanaged`는 기본적으로 꺼져 있다. 자동 업데이트는 기본적으로 켜져 있다. 특정 폴더의 세션을 네트워크에서 제외하는 설정도 존재한다. [12]

다만 전체 경로를 숨겨도 저장소·브랜치 등 작업 맥락은 세션 디렉터리의 일부다. 기존 대화 전체를 동기화하는 기능과는 별개다. [1][12]

### 에이전트 메시지와 사용자 승인의 구분

받은 본문은 `<reason-message>`로 구분해 표시하고, 발신자가 본문으로 메시지·승인 프레임을 위조하지 못하도록 처리한다. 이는 출처 구분을 위한 방어다. 자연어 메시지가 에이전트의 판단에 미치는 영향까지 제거한다는 보장은 아니다. [13]

메일 코드에는 발신 컴퓨터당 분당 60개 제한과, 에이전트 주소 쌍의 10분 내 반복 메시지 제한이 있다. 전달 확인 전까지 다시 전달할 수 있는 구조도 명시돼 있다. 따라서 외부 작업을 수행하는 연동에서는 중복 요청을 처리할 방법이 필요하다는 것이 조사자의 판단이다. [14]

공식 보안 정책은 외부인의 가입·열람, 타인 사칭, 로컬 데몬 접근, 메시지를 통한 에이전트 오동작을 주요 제보 대상으로 명시한다. 보안 정책의 존재와 독립적인 보안 감사 완료는 별개이며, 이번 조사에서 엔진의 독립 감사 보고서는 확인하지 못했다. [15]

## 설치가 변경하는 범위

공식 설치는 데몬뿐 아니라 에이전트의 MCP·훅 설정도 연결한다. Codex 설정 코드에서는 `CODEX_HOME`이 있으면 그 디렉터리를, 없으면 `~/.codex`를 사용한다. 그 아래 `config.toml`과 `hooks.json`에 설정을 추가한다. 여러 Codex 홈을 사용하는 환경에서는 모든 프로필이 한 번에 설정된다고 가정할 수 없다. [16]

같은 코드에서 네트워크 MCP 서버에 `default_tools_approval_mode = "approve"`를 기록한다. 훅에는 세션 시작·사용자 입력·도구 실행 후·종료 등의 이벤트를 연결하며, 훅 신뢰에 대한 최초 승인 안내도 출력한다. 기존 설정과 함께 검토할 지점이다. [16]

이 조사는 설치 명령을 실행하지 않았고 에이전트 설정도 변경하지 않았다. 문서와 공개 소스의 정적 검토이며, 성능·실제 도달률·다중 머신 동작·사용자 환경과의 호환성은 검증 범위에 포함하지 않았다.

## 활용 판단

적합한 용도는 다른 에이전트의 현재 작업을 확인하고, 구현 근거를 질문하고, 작은 코드·스키마·로그를 전달하는 일이다. 세션을 맥락과 함께 찾아 연락한다는 기능 조합이 유용하다. [1][7][9]

파일 편집 충돌 자동 경고, 항상 켜진 보관 노드, 검색 가능한 팀 이력, 웹 대시보드는 설계 문서의 M4 계획이다. 현재 메시징을 통해 충돌을 줄일 수 있다는 설명과 자동 충돌 방지 기능의 구현 완료를 구분해야 한다. [3]

도입 판단은 먼저 세션 식별과 전달 시점이 실제 사용하는 에이전트·프로필에서 정확한지에 달려 있다. 이후 조직의 수신 정책과 팀원 권한 구조가 맞는지 평가할 수 있다. 이 판단은 공개된 기능과 설정 구조를 바탕으로 한 조사자의 해석이다.

## 출처

모든 자료는 2026-10-23 조회. 소스 링크는 검토 커밋에 고정했다. 초기 검색에서 발견한 과거 도구 개수·릴리스 수치보다 현재 공식 자료와 API 조회 결과를 우선했다.

[1] [공식 README](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/README.md)

[2] [Reason Network 공식 소개·FAQ](https://reasonmachines.com/network)

[3] [공식 설계 문서](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/DESIGN.md)

[4] [GitHub 저장소 메타데이터 API](https://api.github.com/repos/reason-machines/reason-network)

[5] [v0.12.9 공식 릴리스](https://github.com/reason-machines/reason-network/releases/tag/v0.12.9)

[6] [검토 기준 커밋](https://github.com/reason-machines/reason-network/commit/039b9571dab11f980813918b60a827b8bb27fbfd)

[7] [MCP 도구 구현: src/mcp.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/mcp.rs)

[8] [사용자 승인 구현: src/daemon/ask.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/daemon/ask.rs)

[9] [파일 전송 구현: src/files.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/files.rs)

[10] [네트워크 구현: src/net.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/net.rs)

[11] [팀 권한·초대 구현: src/team.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/team.rs)

[12] [설정과 기본값: src/config.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/config.rs)

[13] [수신 메시지 표시: src/render.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/render.rs)

[14] [전달·재전달·반복 제한: src/daemon/mail.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/daemon/mail.rs)

[15] [공식 보안 정책](https://github.com/reason-machines/reason-network/security)

[16] [에이전트 설정 구현: src/setup.rs](https://github.com/reason-machines/reason-network/blob/039b9571dab11f980813918b60a827b8bb27fbfd/src/setup.rs)
