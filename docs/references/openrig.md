# OpenRig 조사

OpenRig는 Claude Code·Codex·Pi 세션을 YAML로 정의한 팀(rig)으로 띄우고, 상주 데몬이 그 팀의 구성·메시지·작업 큐·화면을 관리하는 멀티 에이전트 하니스다. 지금까지 검토한 것 중 xsm과 가장 직접 겹친다. 이미 떠 있는 세션을 편입하고 세션 사이에 메시지를 보낸다. 다만 메시지를 tmux 붙여넣기로 넣고 상주 데몬에 기대는 점에서 xsm과 정반대 선택을 했고, 이 점에서 Orca·herdr와 같은 부류다.

- 작성일: 2026-10-04
- 출처(모두 2026-10-04 조회):
  - 저장소: `mvschwarz/openrig`, `git clone --depth 1`, 커밋 `d3bb161` (2026-10-03)
  - 읽은 것: `README.md`, `ARCHITECTURE.md`, `docs/releases/v0.5.1.md`·`v0.5.2.md`, `packages/daemon/src/domain/session-transport.ts`(일부)
  - 메타데이터: GitHub API `repos/mvschwarz/openrig`
- 방법: 정적 조사(문서 열람, 소스 grep, 일부 파일 열람). 실행하지 않았다. multi-host 동작은 릴리스 노트 수준으로만 확인했다.

## 1. 프로젝트 상태

| 항목 | 값 |
|---|---|
| 저장소 | `mvschwarz/openrig` (npm `@openrig/cli`) |
| 라이선스 / 언어 | Apache-2.0 / TypeScript |
| 생성 | 2026-04-01 |
| 커밋 | 3,396 |
| 별 | 4,754 |
| 열린 이슈 | 94 |
| 마지막 푸시 | 2026-10-04 |
| 요구 사항 | macOS·Linux, Node.js 22 또는 24, tmux. 네이티브 Windows 미지원, WSL2 미시험 |

## 2. 하는 일

README "What It Does"와 ARCHITECTURE 기준이다.

- **정의와 기동:** YAML(RigSpec)로 pod, 관계(edge), seat, 연속성 정책을 정의하고, `rig up` 한 번으로 tmux 세션, 하니스, 시작 파일, 준비 확인까지 띄운다.
- **기존 세션 편입:** `rig discover`가 기존 tmux 세션을 식별하고(fingerprint), `rig adopt`가 관리 대상으로 편입한다. 편입 대상은 tmux 안의 세션이다. 이미 떠 있던 세션은 새로 쓴 설정을 반영하려면 재시작이 필요할 수 있다.
- **지속:** `rig down --snapshot`으로 구성을 저장하고 `rig up <이름>`으로 복원한다. `rig grow`, `rig shrink`, `rig launch`, `rig remove`로 실행 중인 구성을 바꾼다.
- **소통:** `rig send`, `rig broadcast`, `rig chatroom`. 작업은 `rig queue`에 기록한다(메시지를 보낸다고 큐 항목이 생기지는 않는다). Slack 연동은 실험적이다.
- **화면:** `rig tui`가 rig를 그래프와 표로 보여 주고, seat별 런타임, 모델, 컨텍스트, 상태를 표시한다. `rig tui --shared`는 공유 대시보드다.
- **multi-host:** v0.4.6에 들어왔고, v0.5.1·v0.5.2부터 기계 사이 메시지에 출처 기계를 붙인다. v0.5.2 노트에는 일부 기계 간 메시지의 회신 힌트가 등록된 호스트 이름 대신 기계 ID를 써서 실패할 수 있다는 알려진 문제가 있다.
- **구조:** 상주 데몬(`packages/daemon`)이 HTTP 라우트를 열고, 상태를 SQLite(WAL)에 두고, tmux 어댑터와 런타임 어댑터(Claude Code, Codex, Pi)로 세션을 다룬다.

## 3. 메시지 주입

`packages/daemon/src/domain/session-transport.ts`(1,995행) 기준이다.

- **tmux 붙여넣기와 Enter.** `send-keys`를 쓰는 파일이 런타임 어댑터와 전송 계층 등 14곳이다. Claude inbox 소켓이나 Codex 큐 같은 런타임 고유 경로는 쓰지 않는다. 소스에 `codex queue`, `thread/queue`가 없다. `app-server`가 나오는 파일 6곳은 사용량 조회와 Codex 데몬 지원 같은 다른 용도다.
- **보낼 시점은 화면 판독으로 정한다.** 마지막 줄들을 읽어 `agent_idle`, `agent_active`, `attention`, `unknown`으로 분류한다. 상태바 패턴, 빈 입력창 패턴, 작업 중 패턴(`Working … esc to interrupt` 등)을 쓴다. 판정 창은 12줄이다.
- **권한 질문 보호.** 화면에 권한 질문이 있으면 Enter가 그 질문을 승인해 버리므로, 위로 밀려 올라간 질문까지 찾아 "입력 필요"로 분류하고 보내지 않는다. 이 보호를 넘는 것은 `dangerouslyInteract`뿐이다. 강제 옵션(force)도 넘지 못한다.
- **붙여넣기 상태 식별.** 붙여 넣은 텍스트가 `[Pasted text #N +X lines]`로 접혀 보이는 상태를 식별하고, 여러 조각이 쌓인 상태에서는 Enter를 치지 않는다.
- **typing guard.** 사람이 직접 치는 seat를 `rig seat set-typing-guard`로 지정하면, 자동 메시지와 깨우기를 입력하지 않고 보류한다. 기본값은 꺼져 있다.
- 주석에 같은 함정을 겪은 다른 프로젝트(ntm, daintree, AgentDeck)의 기록을 근거로 인용한다. 오판의 비용이 비대칭이라(잘못된 거부는 넘길 수 있지만 잘못된 "쉬는 중"은 프롬프트에 메시지를 떨어뜨린다) "프롬프트가 있다" 쪽으로 판정한다.

## 4. 설치와 실행이 바꾸는 것

README "What OpenRig changes on your machine" 기준이다.

- `rig setup`: `~/.tmux.conf`에 블록 추가. macOS에서는 cmux를 설치하고 그 자동화 소켓 설정을 바꿀 수 있다.
- 데몬 시작: `OPENRIG_HOME`(기본 `~/.openrig`)에 데이터베이스와 플러그인 자원. `~/.claude/skills`와 `~/.agents/skills`에 탐색 스킬을 심는다.
- Claude Code: 작업 공간 신뢰와 온보딩 완료를 기록한다. 작업 공간의 `.claude/settings.local.json`에 상태줄 명령과 활동 훅을 넣는다. 공유 설정 자원은 `permissions.defaultMode`를 `acceptEdits`로 두고 Exa·Context7 MCP를 켠다. 관리형 실행은 `--permission-mode acceptEdits`로 띄운다.
- Codex: `CODEX_HOME/config.toml`에 훅을 켜고, OpenRig 활동 전달 명령을 넣고, 그 명령의 신뢰 해시를 미리 기록한다. seat 시작 시 작업 공간을 `trust_level = "trusted"`로 둔다. 기본 샌드박스는 `-s workspace-write`다.
- 활동 전달: 이벤트 종류, seat 신원, 시각, 네이티브 세션 id를 데몬의 `/api/activity/hooks`로 보낸다. 프롬프트 본문과 도구 인자는 보내지 않는다고 적혀 있다.
- 권한: 처음에 에이전트가 "OpenRig 명령을 반복 확인 없이 실행하도록 허용할까요?"를 한 번 묻는다. 내장 부트스트랩은 허용 규칙을 직접 쓰지 않는다. YOLO는 기본으로 꺼져 있다.
- 관리형 실행은 `HOME`, `CODEX_HOME`, `OPENRIG_*` 신원·연결 환경변수를 넣는다.
- README는 일부 설정 작성기가 읽을 수 없는 설정을 빈 객체로 복구할 수 있어 보존·롤백을 보장하지 않으니 먼저 백업하라고 적는다.

## 5. xsm과 비교

| | xsm | OpenRig |
|---|---|---|
| 세션을 누가 띄우나 | 사람. 어느 터미널이든 훅으로 붙는다 | 주로 OpenRig(`rig up`). 기존 세션은 tmux 안에 있을 때만 편입 |
| 메시지 주입 | Claude inbox 소켓, `codex queue`와 `thread/queue/start` | tmux 붙여넣기와 Enter. 화면 판독으로 시점을 정한다 |
| 사람 입력과의 구분 | 봉투와 수신 게이트 | 런타임 입장에서는 사람 입력과 같다. typing guard로 사람 자리를 보호한다 |
| 런타임 의존 | 없다(훅, 파일, 일회성 CLI) | 상주 데몬, SQLite, tmux |
| 설치 시 바꾸는 것 | 훅, 스킬, MCP 등록 | 위 4장 |
| 프로필 | 프로필(CONFIG_DIR) 사이 발견 | 관리형 실행이 `HOME`·`CODEX_HOME`을 정한다 |
| 범위와 동의 | 프로젝트 범위, 사람 승인 양식 | rig·pod 구조, `rig` 명령 일괄 허용을 한 번 묻는다 |
| 화면 | CLI와 상태줄 | TUI 그래프와 표, 공유 대시보드, Slack |
| 팀 구성과 복원 | 없다(워커만) | YAML 구성, 스냅샷과 복원, 확장·축소 |
| 원격 | SSH 짝 | multi-host |

## 6. xsm에 대한 시사점

| 판단 | 내용 |
|---|---|
| 같은 부류 | 터미널을 소유하는 하니스라 Orca·herdr와 같은 부류다. E1 평가가 두 제품에 대해 지적한 "PTY 주입은 사람 입력과 구분되지 않는다"가 그대로 해당한다. 그 위험을 화면 판독과 typing guard로 막는 정도는 가장 공들인 축이다 |
| xsm이 앞섬 | tmux 밖이나 다른 프로필의 세션에 붙는다. 화면을 긁지 않고 런타임 고유 경로로 넣는다. 상주 프로세스가 없다 |
| OpenRig가 앞섬 | ADR-0014에서 xsm에 비어 있다고 확인한 영역(대시보드, 팀 구성과 지속, 작업 큐, Slack, 기계 간 화면)을 이미 갖췄다 |
| 공존 | ADR-0010은 Orca·herdr 안에서 xsm이 워커를 띄우지 않고 메시징만 맡게 한다. xsm의 프레임워크 감지는 지금 `orca`와 `herdr`뿐이다(`xsm/cli.py:545-572`). OpenRig가 관리형 seat에 `OPENRIG_*` 환경변수를 넣으므로 같은 방식으로 감지할 수 있어 보이나 시험하지 않았다 |
| 참고 | xsm은 `codex queue`에 넣은 뒤 `thread/queue/start`로 Esc 스레드를 깨울 때, 화면에 권한 질문이 떠 있는 상태와 겹치면 어떻게 되는지 확인하지 않았다. OpenRig의 "권한 질문 위에는 보내지 않는다" 규칙이 점검 기준이 된다 |
