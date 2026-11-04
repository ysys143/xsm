# AgentTeams 조사: 작업 상태를 코드에 묶은 Matrix 기반 다중 에이전트 플랫폼

- 조사일: 2026-11-04
- 질문: Alibaba AgentScope 팀의 AgentTeams는 에이전트 사이의 작업 위임·완료 통지·사람 호출·세션 깨우기를 어떻게 설계했으며, xsm에 참고할 것과 따르지 말아야 할 것은 무엇인가?
- 대상: [agentscope-ai/AgentTeams](https://github.com/agentscope-ai/AgentTeams)
- 방법: 고정 커밋의 README, `docs/design/` 중 협업 계약에 해당하는 문서, TeamHarness MCP·Matrix 채널·DeepSeek Harness 브리지 코드 일부의 정적 분석. **빌드·테스트·실행은 하지 않았다.** 동작 설명은 문서와 코드에서 읽은 것이며 관측 결과가 아니다.
- 현행 xsm과의 관계: 최초 비교 기준은 xsm `9cee7ad`다.
- XSM 비교 보정: 2026-11-04, `c61799f` 기준으로 조직 모델, 일반 세션·owned worker의 결과 처리, 최종 outcome·대기 상태, 결정 기록·스키마 검사를 대조했다. 9~12절의 관련 비교와 검토 의견을 갱신했다. AgentTeams 고정 소스·실행 동작을 새로 검증한 것은 아니다.
- 효력: 이 노트는 레퍼런스 분석이며 ADR의 상태를 바꾸지 않는다.
- 함께 볼 문서: [dsh-superagent 조사](dsh-superagent.md). 두 조사의 설계 참고 항목이 겹치는 곳은 11절에 표시했다.
- 후속 반영: [구현 기록](../plan/collaboration/reference-adoption/results.md)과 [경로 일관성 보정](../plan/collaboration/reference-adoption/followup.md)을 함께 본다. 아래 고정 버전 비교를 현행 전체 구현 상태로 읽지 않는다.

## 요약

AgentTeams는 **Kubernetes 컨트롤러가 Manager·Worker 에이전트 컨테이너를 만들고, 모든 대화를 자체 Matrix 서버의 방(room)에서 사람과 함께 하게 하는 플랫폼**이다. LLM 키는 Higress 게이트웨이가 쥐고 Worker는 소비자 토큰만 가진다. 파일과 작업 상태는 MinIO(S3 호환)에 둔다.[1][2]

두 제품의 실행 구조는 다르다. AgentTeams는 에이전트를 직접 만들고 소유하며 서버 세 개(Matrix, 게이트웨이, 저장소)를 전제한다. xsm은 기존 세션 연결과 선택적 워커 실행을 제공하며 별도의 중앙 오케스트레이터를 필수로 두지 않는다(ADR-0003). 참고할 핵심은 **모델이 기억해야 할 절차를 줄이는 결과 저장·통지·복구 계약**이다.

xsm에서도 팀장이 일을 나누고 결과를 검토·수락하는 운영을 선택할 수 있다. [조직 구성과 권장 개발 운영 모델](../xsm/ORGANIZATION.md)은 장기 병렬 개발에 팀장과 수평 워커를 강력히 권고하며, 팀장들이 동등하게 협의하는 조율 팀과 다른 조직도 허용한다. 통신 계층의 보장과 조직별 업무 절차를 나눠 적용한다.

가장 큰 참고점은 네 가지다.

1. **완료 통지를 모델의 기억에서 떼어 냈다.** 운영에서 Worker가 컨텍스트 압축 뒤 "끝났다"는 메시지를 잊는 일이 실제로 있었고, 그래서 작업 제출 도구가 통지를 직접 보내게 바꿨다. 통지는 공유 저장소 동기화가 성공한 뒤에만 나간다.[3]
2. **작업 상태를 한 표와 한 입구로 바꿨다.** 전이표 JSON 하나를 Python 쓰기 쪽과 Go 읽기 쪽 테스트가 함께 읽고, 모든 전이가 한 함수를 지나며 이력이 남는다.[4]
3. **결과 다섯 종.** 성공, 메모 붙은 성공, 수정 필요, 막힘, 중단을 구별한다. xsm의 `succeeded`·`failed` 두 값보다 세밀하다. 특히 "막힘"이 "실패"와 다르다.[5]
4. **낡은 답을 보내지 않는 게이트.** 턴이 끝나 답을 보내기 직전에, 턴 시작 뒤 그 턴과 관련된 새 메시지가 왔으면 초안을 버리고 새 맥락으로 다시 돌린다. 재시도는 두 번, 대기는 600초까지다.[6]

한계도 분명하다. 핵심 복구 경로 일부는 스스로 "PR2로 미룸"이라고 적었고, 저장소 쓰기의 정확성은 "작업마다 동시에 쓰는 쪽이 하나"라는 전제에 기댄다. 운영 효과를 보여 주는 수치는 저장소에서 찾지 못했다.

## 1. 소스와 버전 고정

| 대상 | 고정값 | 해석 |
|---|---|---|
| 조사 커밋 | `c69037acb24c99a3c4a91517d5b6ce15f888e9d7` | 2026-11-04 02:52 +08:00, `fix(ci): make the human-files job wait for RustFS…` |
| 저장소 | 2026-02-21 생성, Apache-2.0, 주 언어 Go | GitHub 메타데이터. 조사 시점 별 5,928개 |
| 최신 릴리스 | v1.2.5 (2026-10-16) | README News |
| 규모 | `.git` 제외 1,232개 파일. TeamHarness MCP Python 9,798줄, Matrix 채널 `channel.py` 5,154줄 | clone에서 측정 |
| 런타임 | OpenClaw(Node), QwenPaw(Python), Hermes, DeepSeek Harness(실험, `@deepseek-ai/dsh@0.1.1-rc.2` 고정) | `docs/design/architecture.md`, `deepseek-harness/README.md` |

경로 인용은 모두 고정 커밋 기준이며 `https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/` 뒤에 붙이면 원본이다. xsm 경로는 이 저장소 기준이다.

TeamHarness 설계 문서 일부(`task-transition-engine.md`, `project-task-runtime-design.md`)는 중국어 원문이다. 인용한 내용은 직접 읽고 옮겼다.

## 2. 제품 구조

| 구성 | 역할 |
|---|---|
| `agentteams-controller` | Go 오퍼레이터. Worker·Manager·Team·Human CRD를 조정하고 REST API(:8090)를 연다. 로컬 설치에서는 Higress·Tuwunel·MinIO·Element Web을 한 컨테이너에 묶는다 |
| Manager | 조정 에이전트. 사람(L1 관리자)과의 대화를 컨트롤러 API 호출로 바꾼다. 선택 사항이다 |
| Team Leader | 팀마다 정확히 하나. 작업을 쪼개 Worker에게 맡기고 결과를 받아들인다 |
| Worker | 작업 수행자. 컨테이너 하나, 상태는 저장소에 두므로 교체 가능 |
| Human | CRD로 선언한다. 권한 L1(관리자)·L2(팀 범위)·L3(특정 Worker 읽기 전용) |
| Tuwunel | 자체 Matrix 홈서버. 사람과 에이전트의 모든 대화가 지난다 |
| Higress | LLM·MCP 프록시. 실제 키와 GitHub PAT를 쥐고 신원별 소비자 키로 범위를 나눈다 |
| MinIO | `agents/<name>/`, `shared/tasks/`, `shared/projects/` 등 공유 상태 |

README가 내세우는 원칙은 "숨은 에이전트 간 호출이 없다"이다. 모든 위임이 사람이 들어 있는 방에서 일어나고, 사람은 언제든 끼어들 수 있다.[1]

협업 규칙은 **TeamHarness**라는 런타임 중립 플러그인에 모여 있다. 프롬프트, 팀 스킬, MCP 도구 다섯 개(`health`, `message`, `filesync`, `projectflow`, `taskflow`)로 구성된다. TeamHarness는 Worker 수명, 컨트롤러 조정, 런타임 훅을 소유하지 않는다고 경계를 명시한다. Claude Code 어댑터는 설치 로그만 남기는 자리표시 수준이다.[7]

## 3. 요청의 세 갈래와 상태 객체

Leader는 들어온 요청을 세 모드 중 하나로 분류한다.[5]

| 모드 | 언제 | 상태 |
|---|---|---|
| Direct Reply | 질문, 확인, 상태 문의 | 아무것도 만들지 않고 그 자리에서 답한다 |
| Quick Task | Worker 하나, 수락 기준이 분명한 일 | `create_quick_project` 한 번으로 Project·plan 노드·TaskMeta·spec을 만든다. 메시지는 따로 보낸다 |
| Project Task | 여러 Worker, DAG 의존, 반복(Loop) | `plan_dag`/`plan_loop` → `ready_nodes` → `delegate_task` |

Quick Task 도구가 따로 있는 이유는 "Leader가 `create_project → plan_dag → ready_nodes → delegate_task`를 손으로 엮게 하지 않으려고"다. 모델이 여러 단계를 정확히 이어 붙이는 일을 도구 하나로 접었다.

두 상태 객체가 역할을 나눈다.

- **`ProjectMeta.reply_route`**: 최종 결과를 돌려보낼 원래 요청 통로(DingTalk 세션, Matrix 방 등). 프로젝트에만 있고 Task에는 복사하지 않는다.
- **`TaskMeta.room_id`**: Worker가 일하는 내부 협업 방. 외부 통로가 아니다.

Leader가 Worker의 완료 이벤트로 깨어났을 때의 복구 순서가 고정되어 있다. `check_task(task_id)` → `resolve_project(taskId)` → `accept_task_result(submissionId, accepted)` → `reply_route`로 보고 → `mark_requester_report_sent`. 문서는 "Leader는 현재 세션에서 project, reply route, 다음 단계를 추측하지 않는다"고 적는다. 목표는 세션 메모리 공유가 아니라, **어느 세션이 깨어나든 저장된 상태에서 맥락을 복원하는 것**이다.[5]

## 4. 작업 상태 기계

### 4.1 전이표 하나, 입구 하나

이전에는 다섯 호출 지점이 저마다 상태를 썼고, 지점마다 검사가 달랐다. `accept_task_result`는 출발 상태를 검사하지 않았고, project 쪽만 쓰고 task 쪽은 쓰지 않아 둘이 영구히 갈라질 수 있었다. 진행 상황도 기계가 읽을 기록이 없었다.[4]

고친 방식은 다음과 같다.

- 전이표 `plugins/teamharness/contracts/task-transitions.json`이 유일한 원천이다. 상태는 `planned, prepared, assigned, in_progress, submitted, completed, revision, blocked, cancelled` 아홉 개이고 뒤의 넷이 종료 상태다.
- Python 쓰기 쪽 상수는 Ruby 계약 테스트(`plugins/tests/teamharness/mcp/tools/test-transition-table.rb`)가, Go 읽기 쪽은 Go 테스트가 같은 파일과 대조한다. 런타임에 표를 공유하지는 않고, 공유하는 것은 테스트 고정값이다.
- 모든 전이가 `_transition_task()`를 지난다. 전이표 검사, 상태 쓰기, 이력 추가, task·project 동기화가 한 묶음이다.
- 순서를 어긴 호출은 다음 행동을 알려 주는 구조화 오류로 거절된다. 예: `submit_task: task is 'planned'; ack_task it first`.

### 4.2 이력과 진행 보고

- task meta에 `history`가 붙는다. 코드의 항목은 `{ts, from, to, actor, action, seq}`이고 `note`는 비어 있지 않을 때만 붙는다(`transitions.py:260-272`, 설계 문서는 `note`를 항상 둔다). 최대 50개다(`plugins/teamharness/mcp/common/constants.py:35`). 같은 상태로의 재진입(멱등 재시도)은 기록하지 않는다.
- 초 단위 타임스탬프가 겹쳐도 순서를 잃지 않도록 작업별 일련번호 `history_seq`를 함께 저장한다(`plugins/teamharness/mcp/lifecycle/transitions.py:238-259`). 컨트롤러의 이벤트 API는 이 번호로 커서를 만든다.
- `report_progress`는 상태를 바꾸지 않는 이력 항목이다. note는 200자 이내이고 **방에 알림을 보내지 않는다**. 문서는 이를 "v1 소음 방지"라고 부른다.

### 4.3 제출 식별자와 결과 요약값

- 첫 `submit_task`가 불변 `submission_id`와 결과 요약값 `result_digest`를 만든다. 요약값은 `status`, 공백을 정규화한 `summary`, `deliverables` 세 필드만으로 계산하며, 도메인 접두어와 NUL 구분자를 프로토콜로 고정했다. 그래서 두 런타임이 식별자 형식을 다르게 만들어도 같은 결과는 같은 요약값을 가진다.
- 같은 결과의 재시도는 같은 제출로 처리하고, 다른 결과는 충돌로 거절한다. 제출된 결과는 덮어쓰지 못하며, 고치려면 Leader가 종료 결정을 내리고 새 task를 만든다.
- Leader의 수락·취소는 현재 `submissionId`를 그대로 실어야 한다. 낡은 식별자는 거절한다. Worker는 수락·취소를 호출할 수 없다.

### 4.4 정확성의 경계를 스스로 적었다

> 이 보장은 "감지 가능, 재시도 가능, 복구 가능"이지 exactly-once도, 파일 간 원자적 커밋도 아니다.[5]

- 정확성은 **작업마다 동시에 쓰는 런타임이 하나**라는 전제에 기댄다. 파일 하나는 임시 파일과 원자적 교체로 쓰지만, 프로세스 간 잠금이나 공유 저장소의 CAS는 없다.
- ProjectMeta와 TaskMeta는 별개 파일이라 중간에 실패할 수 있다. 그때는 `retryable: true, statePersisted: true, synced: false`를 돌려주고, 같은 내용의 재시도가 빠진 쪽을 채운다.
- "제출됐지만 아직 수락되지 않은" 작업을 찾아 Leader를 깨우는 주기 검사는 PR2로 미뤘다. 문서는 그때까지 "pending 표시는 저장된 사실일 뿐이며 자동으로 Leader를 깨우지 않고, 작업이 복구됐다고 주장할 수 없다"고 적는다.[5]

## 5. 완료 통지를 코드가 보낸다

### 5.1 문제

`delegate_task`는 맡기는 순간 방에 멘션 메시지를 보내고 그 이벤트 ID를 상태에 기록했다. `submit_task`는 결과 파일만 올리고, 완료 메시지는 `notificationNeeded` 힌트로 Worker 모델에게 맡겼다. 운영에서 여러 턴짜리 세션이 컨텍스트 압축 뒤 그 줄을 잊었다. Leader는 깨어날 신호를 받지 못했고 뒤 작업은 누가 방을 찌를 때까지 멈췄다.[3]

### 5.2 고친 방식

| 항목 | 내용 |
|---|---|
| 보내는 쪽 | `submit_task`가 직접 보낸다. 토큰은 Worker 자신의 것 |
| 첫 줄 | 결과 종류별 토큰. `TASK_COMPLETED`, `TASK_REVISION_NEEDED`, `TASK_BLOCKED`, `TASK_INTERRUPTED`. Leader 프롬프트가 첫 줄만 보고 분기할 수 있다 |
| 멘션 | Leader와 팀의 사람 구성원 모두 |
| 중복 방지 | Matrix 트랜잭션 ID `submit-<task>-<status>`. 같은 상태의 재시도는 기록된 이벤트를 재사용하고, 상태가 바뀌면 새 이벤트를 보낸다. 처음에 `BLOCKED`로 보고했다가 나중에 `SUCCESS`를 내면 Leader가 다시 깨어난다(재사용·무효화는 `plugins/teamharness/mcp/room/notify.py:564-606`, 트랜잭션 ID는 같은 파일의 `_send_task_completion_notification`) |
| 순서 | 로컬 상태 → 결과 파일 게시 → 공유 저장소 동기화 → **그다음 통지**. 동기화가 실패하면 통지를 보내지 않고 재시도 가능 실패를 돌려준다. "Leader가 읽을 수 없는 결과로 깨어나는" 창을 닫는 장치다 |
| 통지 실패 | 방·Leader·멘션 대상이 없거나 HTTP 오류면 최선 노력으로 처리한다. 제출 자체는 성공으로 남는다 |

이 설계의 요점은 **상태 변경과 통지를 한 호출로 묶는 것**이다. 모델이 기억해야 할 일이 둘에서 하나로 준다. 다만 모델이 `submit_task` 자체를 잊으면 여전히 아무 일도 없다. 그 경우의 대비책은 Leader의 `check_task` 폴링과, 미뤄 둔 PR2의 주기 검사다. 문서도 폴링을 당장 없애지 않는 이유를 "자동 통지가 운영에서 입증될 때까지 대조 경로로 둔다"고 적었다.[3]

### 5.3 진행 중 사람 호출: `request_attention`

작업 도중 사람의 결정이 필요하면, 그전에는 방에 아무 말이나 던지고 누가 보기를 바랐다. 이제는 도구 동작이 있다.[3]

- `kind`는 `approval | decision | escalation | other` 중 하나이고, `question`은 500자 이내다. 종료된 task에는 쓸 수 없다.
- 같은 종류의 미해결 요청을 다시 부르면 기록된 이벤트를 재사용하고 다시 핑하지 않는다. 첫 동기화가 실패해 이벤트 ID가 없는 대기 기록도 재사용하여, 재시도가 기록 하나와 이벤트 하나만 남긴다(`notify.py:486`의 트랜잭션 `attention-<task>-<kind>-<attempt>`).
- 닫을 때도 동기화가 먼저다. 열린 요청이 없는데 닫으려 하면 거절한다. 미리 닫힌 기록을 만들면 새 핑이 나가 "핑 없이 닫는다"는 계약이 깨지기 때문이다.
- Leader가 `accept_task_result`를 부르면 그 task의 미해결 요청이 모두 닫힌다.
- **제안 단계(미구현)**: 승인 요청은 선택지 `options: [{id, label}]`를 싣고, 답은 그중 하나의 ID를 그대로 돌려줘야 한다. `suggested`는 참고일 뿐 자동 적용하지 않는다. 만료되면 거부로 처리하고 사유를 기록한다. 경로는 기본 콘솔이고 방은 선택이며, 한 요청을 두 곳에 보내지 않는다. 먼저 답한 사람이 이기고 누가·언제·무엇에 답했는지 남긴다.

## 6. 세션을 깨우는 것과 깨우지 않는 것

정리된 표가 따로 있다.[8]

| 목적 | 수단 |
|---|---|
| 외부 시계로 방·세션 깨우기 | 예약 작업(cron `run_at`) |
| 에이전트 코드에서 특정 방·세션 깨우기 | `message`에 `type: PROJECT_REQUESTED`와 구조화된 `replyRoute` |
| 일반 자기 메시지 | **깨우지 않는다.** 설계상 자기 발신은 건너뛴다 |

- 자기 메시지를 무시하는 규칙은 채널 입구에서 일찍 판정된다. 유일한 예외는 메시지 내용의 `m.teamharness.trigger`에 `kind: self_cross_session`이 있고 배달된 방이 대상과 일치할 때다(`plugins/agentteams-matrix-channel/agentteams_matrix/channel.py:1881-1899`). 보내는 쪽은 발신자가 현재 런타임의 Matrix ID와 같아야 하며 역할 이름은 거절한다.
- 하트비트는 깨우기 수단이 아니라고 못 박았다. 방에 나타난 하트비트는 자기 메시지라서 건너뛰어지기 때문이다. QwenPaw 기준으로 하트비트는 기본 꺼짐, 주기 6시간, 늦은 틱은 60초 유예 뒤 조용히 버려진다.

xsm의 ADR-0002가 "훅 기반 전달은 완전 유휴 Claude를 깨우지 못했다"(`docs/adr/0002-delivery-and-wakeup.md:27`)고 적은 것과 같은 종류의 문제를, AgentTeams는 무엇이 깨우는지를 표 하나로 정리해 다뤘다.

이 ADR의 실험은 당시 하네스에 대한 기록이다. 현행 추가 런타임의 pull·native wake·FYI 경로는 [호스트 프로토콜 안내](../protocol/README.md)와 각 런타임 안내에 따로 적혀 있다. AgentTeams의 표나 과거 Claude 실험으로 현재 모든 XSM 런타임의 깨우기 능력을 일반화하지 않는다.

## 7. Matrix 채널의 대화 규칙

### 7.1 낡은 답을 보내지 않는 게이트

턴의 최종 답을 방에 내보내기 직전에, 턴 시작 시 찍어 둔 맥락 시점 뒤에 새 방 이벤트가 있는지 본다(`channel.py:166-171`, `4492-4627`, #1244).[6]

- 새 이벤트가 **이 턴과 관련 있으면**(같은 발신자가 보냈거나 이 Worker를 이름으로 부르면) 초안을 버린다. 관련성으로 좁힌 것은 #1386에서 고친 내용이다. 놓친 이벤트를 방별 기록에서 복원해 "이전 초안은 보내지 않았다. 새 메시지 N개가 도착했다"는 안내와 함께 다시 돌린다.
- 관련 없는 동료 대화라면 초안을 그대로 보낸다.
- 예산은 재트리거 두 번, 벽시계 600초다. 예산이 다하면 초안을 보내고 짧은 메모를 붙인다.
- DM과 스레드에는 적용하지 않는다.
- 비교 기준은 공유 버퍼가 아니라 턴마다 찍은 세대 번호다. 다른 멘션이 버퍼를 비우면 첫 턴의 신호가 사라지기 때문이다(`channel.py:4544-4549`).

### 7.2 에이전트끼리 끝없이 주고받지 않게

- **`NO_REPLY`**: 본문이 정확히 `NO_REPLY`이면 조용히 버린다. 주석은 "에이전트 간 무한 핑퐁을 막기 위해"라고 적는다(`channel.py:2900-2909`).
- **자동 멘션은 한 홉만**: DSH 브리지는 다른 에이전트에게 답할 때, 모델이 상대 ID를 빠뜨려도 원 발신 에이전트를 자동으로 멘션한다. 다만 원 이벤트가 이미 자동 멘션으로 온 것이면 다시 붙이지 않는다(`deepseek-harness/scripts/matrix_bridge.py:118-137`). Matrix 내용의 표시 키는 `com.agentteams.auto_source_mention`이다(`deepseek-harness/scripts/matrix_channel.py:73`). 모델이 상대를 직접 멘션하는 것은 막지 않는다.
- **멘션 게이트와 선언적 정책**: 그룹 방에서는 허용 목록에 있는 발신자의 멘션만 턴을 연다. CRD의 `channelPolicy`(`groupAllowExtra`/`groupDenyExtra`/`dmAllowExtra`/`dmDenyExtra`)로 기본값 위에 더하거나 뺀다. Team의 `peerMentions`(기본 true)는 Worker끼리 서로 멘션할 수 있는지를 정한다.[9]
- 방마다 직렬 처리 키를 두어 같은 세션에 동시 접근하지 않는다(`channel.py:501-504`).

### 7.3 사람 권한과 방 권한

- L1/L2/L3 권한 단계를 Matrix power level로 옮긴다. L1은 100, L2·L3는 50이다. 50이면 이름 바꾸기, 초대, 0인 Worker 강퇴가 되지만 100인 Manager·Leader는 못 건드린다.[10]
- 권한 부여는 **병합**이다. 기존 상태를 읽고 사람 항목만 올리며 바뀐 경우에만 쓴다. 정상 상태에서 방마다 GET 한 번, 쓰기 0번이다.
- Matrix 규칙상 같은 수준끼리는 강등·강퇴가 안 된다. 철회 연쇄는 관리자 강퇴, 본인 토큰으로 스스로 나가기, 관리 봇 강제 퇴장 순이다. 각 단계는 앞 단계가 못 하는 경우를 맡는다. 403을 성공으로 삼키던 버그를 고친 기록도 있다.
- 읽기 API는 범위 밖 대상에 균일한 404를 준다. 없는 것과 볼 수 없는 것을 구별하지 못하게 하는 장치다.[11]

## 8. 선택적 구조화 메시지 봉투

`org.agentteams.run` v1은 런타임이 메시지 내용에 `text, thinking, tool_call, confirmation, error` 블록을 실을 수 있게 한다.[12]

- 봉투가 없거나 v1에서 유효 블록이 0개면 본문 텍스트로 되돌아간다. 메시지는 언제나 보인다.
- 필수 필드가 빠진 블록은 고치지 않고 건너뛴다. 모르는 블록 종류도 건너뛴다. 모르는 버전이면 봉투 전체를 무시한다.
- `tool_call_id`, `confirmation_id`는 개정·재전송을 넘어 유지해야 한다.
- 채택은 런타임별, 블록 종류별로 할 수 있다. 전부 아니면 전무가 아니다.

xsm 봉투(`xsm/envelope.py`)와 직접 겹치지는 않는다. "구조를 더해도 본문만 읽는 쪽이 깨지지 않는다"는 점진 도입 규칙만 참고할 만하다.

## 9. xsm과 비교

최초 조사의 `9cee7ad` 비교를 바탕으로, 조직·완료 회신·owned 상태 기록·사람 요청과 최종 outcome의 의미를 `c61799f`에서 보정했다. 나머지는 원조사의 정적 분석 범위이며 최신 제품 전체를 재검증한 표가 아니다.

| 주제 | AgentTeams | xsm | 근거 |
|---|---|---|---|
| 실행 구조 | 컨트롤러가 컨테이너를 만들고 Matrix 서버를 거친다 | 기존 세션 연결과 선택적 워커 실행. 기본 통신에 중앙 오케스트레이터를 요구하지 않으며 업무상 팀장은 선택 가능 | ADR-0003, 조직 운영 문서 |
| 위임 단위 | TaskMeta. 상태 9개, 전이표 | `task` 메시지와 질문 기록. 질문 상태는 `pending`·`reply_received`·`final`이고, 회신 전 전달이 끝난 경우 `held`·`blocked`·`refused`·`error`가 된다 | `xsm/questions.py:63-108` |
| 결과 종류 | 5개(SUCCESS, SUCCESS_WITH_NOTES, REVISION_NEEDED, BLOCKED, INTERRUPTED) | 최종 outcome은 `succeeded`·`failed`다. 질문은 유효한 outcome이 있으면 `final`이 되므로 대기 상태와 분리해 설계해야 한다 | `xsm/envelope.py:34`, `xsm/questions.py`의 `_result` |
| 완료 통지 | 상태 도구가 직접 보낸다. 상태 변경과 통지가 한 호출 | 일반 세션은 모델이 회신을 호출하고 수신 측이 기록한다. owned worker는 실제 결과를 저장한 뒤 코드가 회신을 시도하고 전송 상태를 기록한다 | `xsm/questions.py`의 `record_reply`, `xsm/owned_requests.py`의 `save_result`·`finish_send`, `xsm/workers.py`의 `run_owned` |
| 같은 결과 재전송 | 요약값 fence. 같은 결과는 재사용, 다른 결과는 충돌 | 같은 회신 ID는 멱등, 같은 ID의 다른 내용은 거절. 회신 여러 개(중간·최종) 허용 | `xsm/questions.py:331-355` |
| 실패 반복 상한 | 이번 조사 범위에서 작업 시도 상한은 보지 않았다 | 마지막 성공 뒤 `failed`가 3번(설정 가능)이면 같은 과제의 spawn 거절. 결과 없이 끝난 시도는 세지도 초기화하지도 않는다 | `xsm/attempts.py:70-81`, `xsm/workers.py:648`, `skills/xsm/references/workers.md:65-73` |
| 맡음 표시 | `ack_task`로 `assigned → in_progress` | 일반 세션에는 없음. owned worker에는 `reserved`·`acknowledged`·`running` 상태 | `xsm/owned_requests.py` |
| 진행 기록 | `report_progress`. 알림 없음, 이력만 | 팀원이 함께 쓰는 팀 보드 | ADR-0026 |
| 사람 호출 | `request_attention`. 종류별 멱등, Leader 수락 시 자동 해제 | 결정 저널과 검증된 네이티브 답 복구가 있다. 연결된 워커의 가입 요청은 생성자 측으로 모으며, 다른 사용자 판단은 지정된 창구로 전달하도록 스킬에서 안내한다 | `xsm/decisions.py`, `xsm/delegation.py`의 `request_join`, 워커 스킬 |
| 낡은 답 차단 | 최종 답 직전 게이트, 재트리거 2회 | Stop 훅이 없다. 턴 종료 시점 검사 장치 없음 | `hooks/hooks.json`, `hooks/codex-hooks.json` |
| 에이전트 간 고리 | `NO_REPLY`, 자동 멘션 한 홉, 멘션 게이트 | 반복·속도·중복 근거 제어를 원칙으로 둠. 수치는 미결정 | ADR-0022 36·60행 |
| 깨우기 | 자기 메시지는 안 깨움. 구조화된 자기 트리거 하나만 예외 | ADR-0002가 런타임별 깨우기 한계를 기록 | ADR-0002 |
| 상태 위치 | 공유 S3 + 단일 작성자 전제 | 기계별 로컬 파일과 요청별 잠금 | `xsm/questions.py:35-44` |

owned worker의 구체적인 비교 경로는 [workers.py](../../xsm/workers.py)의 `run_owned`·`_reply_owned`와 [owned_requests.py](../../xsm/owned_requests.py)의 `save_result`·`claim_send`·`finish_send`다. 모델 실행에서 실제 결과를 얻으면 이를 저장하고 회신 ID를 유지한 채 발행하며 전송 근거를 기록한다. 저장과 외부 전송이 원자적이거나, 모든 일반 TUI 세션이 자동으로 완료 보고한다는 뜻은 아니다.

## 10. xsm이 이미 가진 것

조사에서 확인한 기존 대응 장치와 2026-11-04 보정이다. 새 장치를 검토할 때 중복을 피하기 위해 실행 경로별로 구분한다.

- **일반 질문 회신의 기록.** 수신 측의 `record_reply`가 회신을 질문 기록에 남긴다. 모델이 회신 호출 자체를 잊는 문제와, 보낸 회신을 기록하는 문제는 별개다.
- **owned 결과의 저장과 발행.** 결과 저장 뒤 코드가 회신을 시도한다. 전송 실패 시 저장된 결과를 회수·재전송할 수 있으며, 일반 세션에 이 경로를 그대로 적용할 수 있는지는 별도 문제다.
- **owned 상태 이력.** `_event`가 `{phase, at}`를 `events`에 남긴다. A08·A09는 이 기존 이력과 전이 검사를 바탕으로 검토한다.
- **같은 ID의 다른 내용 거절.** 요약값 fence와 같은 목적을 회신 ID 단위로 이미 한다.
- **실패 반복 상한.** 같은 과제가 마지막 성공 뒤 세 번(기본값, `xsm/workers.py:648`) 실패하면 다시 띄우지 않는다. 이력은 워커 기록이 지워져도 남는다(`xsm/attempts.py:1-11`).
- **권한 세탁 금지.** 무인 워커가 사람 대신 승인하지 못하게 하는 규칙이 스킬과 코드에 있다(`skills/xsm/references/workers.md:40-49`).

## 11. 설계 참고와 후속 검증 조건

번호는 dsh 조사의 D와 구분해 A로 붙였다. "겹침" 열은 dsh 조사의 같은 주제 항목이다.

15개 항목은 검토 후보이며 승인된 구현 목록이 아니다. 기존 구현 재사용, 선택한 조직의 스킬·업무 절차, 통신 계약 변경, 하네스별 실험을 구분한다. 생성자·팀장·현재 요청자·원 의뢰인의 역할이 다를 수 있으므로 결과 회신과 사용자 승인 경로도 각각 유지한다.

| ID | AgentTeams 장치 | xsm에서의 검토 대상 | 검증 조건 | 겹침 |
|---|---|---|---|---|
| A01 | `BLOCKED`·`INTERRUPTED`를 실패와 구별 | 사람·권한 대기, 범위 밖 반환, 중단과 최종 결과를 먼저 구분한다. 현재 무응답 워커 정지는 `failed`로 시도 기록을 닫는다 | 같은 과제 재생성(`--retry-of` 포함)에서 권한 대기·사용자 중단이 실패 상한에 포함되는지 재현. `OUTCOMES`의 새 값이 대기 중 질문을 `final`로 만들지 않는지 설계. 기존 워커에 단계를 다시 보내는 경로와 구분 | D02 |
| A02 | 결과별 첫 줄 토큰 | 회신 첫 줄에 결과를 기계가 읽을 형태로 두는 규칙 | 이미 `outcome` 헤더가 있으므로 본문 규칙이 중복이 아닌가 | D16 |
| A03 | 동기화 뒤 통지 | 일반 세션의 첨부·보드 쓰기와 완료 회신 순서를 검토. owned는 결과 저장 후 발행 경로가 이미 있다 | 첨부·보드를 상대가 읽을 수 있는 시점과 회신 순서를 확인. owned의 결과 저장·발행을 모든 산출물의 원자적 게시로 오해하지 않는가 | - |
| A04 | 상태 바뀐 재제출은 새 통지 | 같은 질문에 `failed` 뒤 `succeeded`가 오면 질문자가 다시 알림을 받는가 | `final_outcome`이 마지막 결과를 따르는지는 확인함(`xsm/questions.py:73-74`). 알림 경로는 확인하지 않음 | - |
| A05 | 낡은 답 게이트 | Claude Stop 훅으로 "턴 중 도착했는데 아직 반영하지 않은 관련 메시지"가 있으면 종료를 한 번 막을지 | Stop 훅 차단이 사람의 대화를 방해하지 않는가. 재시도 예산과 관련성 판정을 정할 수 있는가. Codex에 같은 수단이 있는가 | D06 |
| A06 | 자동 응답 한 홉 표시 | owned의 완료 결과 발행과, 받은 응답에 자동으로 다시 응답하는 경로를 구분 | `_reply_owned`의 발행이 있다는 사실만으로 자동 멘션·핑퐁 고리가 있다고 판단하지 않는다. 실제 자동 전달·응답 경로와 고리가 있는지 별도 확인 | - |
| A07 | `NO_REPLY` 규약 | "할 말 없음"을 명시하는 짧은 회신을 수신 측이 조용히 닫기 | ADR-0022의 정상 왕복 보호와 충돌하지 않는가. 질문 기록에서 `final`로 셀지 | D15 |
| A08 | 작업 이력 50개와 일련번호 | owned의 기존 `events`와 ledger를 바탕으로 상태 이력·순서 정보의 공백 검토 | `_event`는 `{phase, at}`를 이미 남긴다. 새 이력·일련번호·보존 상한이 해결할 문제와 기존 기록의 중복을 확인 | D01 |
| A09 | 전이표 단일 원천 + 언어 간 테스트 | 기존 owned 상태별 검사와 이력 기록을 유지하면서 전이 규칙의 중복·드리프트 검토 | 현재 전이 입구와 검사·테스트를 먼저 센다. 검증 없이 전이표 체계 전체를 이식하지 않는다 | D18 |
| A10 | `report_progress`는 알림 없음 | 팀 보드의 기존 진행 기록과, 깨우지 않는 DM의 구별을 안내 | `note` 종류 자체가 무알림을 뜻하지 않는다. 보드 또는 명시적 `wake=never`로 충분한지 확인하고 사용자가 요청한 진행 보고는 유지 | D16 |
| A11 | 깨우기 수단 표 | 런타임별로 "무엇이 세션을 깨우고 무엇이 깨우지 않는가"를 한 표로 스킬에 | ADR-0002와 스킬 문서에 이미 같은 표가 있는지 | - |
| A12 | 요청 종류별 멱등 사람 호출 | 기존 결정 저널·결정 키·정확한 질문 결속·생성자 측 요청 기록을 재사용해 대기 가시성을 검토 | 다른 범위·질문을 종류가 같다는 이유로 합치지 않는가. 요청·답 복구는 유지하면서 표시되지 않음·응답 대기·명시 거부를 구분하는가 | D07, D08 |
| A13 | 선택지 ID를 그대로 돌려받기(제안) | `person_answer`의 기존 선택지 검사와 검증된 네이티브 답 복구를 대조 | 선택지를 제공한 기존 양식은 허용 값 이외의 답을 거절한다. 새 ID 체계가 필요한 문제인지와 기존 결속의 공백을 구분 | - |
| A14 | 균일한 404 | 범위 밖 세션 조회를 "없음"과 같은 모양으로 | directory·discover 응답이 범위 밖 존재를 드러내는지 | D11 |
| A15 | 스스로 적은 보장 범위 | ADR·문서에 "감지·재시도·복구 가능이지 exactly-once가 아니다" 같은 한 줄 | ADR-0018(Proposed) 19·38행에 이미 같은 성격의 문장이 있다. 새로 둘 필요는 사용자 문서와 스킬 쪽에서만 따진다 | - |

### 우선순위에 대한 의견

A01을 먼저 확인하고, dsh의 D01·D04(담당·미응답 가시성), D07·D08과 A12(기존 기록을 활용한 사람 대기 표시)를 잇는 순서로 본다. 워커 스킬은 권한 부족을 끝으로 받아들이지 말라고 안내하지만 최종 outcome은 두 값이고 시도 상한은 `failed`를 센다. [workers.py](../../xsm/workers.py)의 `stop`은 무응답 시도를 `failed`로 닫고, [attempts.py](../../xsm/attempts.py)의 `failures`는 그 값을 센다.

기존 워커에 단계를 다시 보내는 경로는 새 시도를 열지 않는다. 확인할 경로는 권한 부족으로 실패 회신한 워커를 끝내고 같은 과제로 다시 띄우는 경우와, 사람 응답 대기·사용자 중단으로 멈춘 워커가 실패로 닫히는 경우다. 실제 사용자 흐름에서 상한에 걸리는지는 재현하지 않았다. 대기 상태와 최종 결과를 분리할지 결정하기 전에 이 경로를 확인한다. `SUCCESS_WITH_NOTES` 같은 상대 제품의 결과 종류도 모두 wire 값으로 옮길 필요가 있다고 전제하지 않는다.

A05는 효과가 클 수 있지만 하네스 의존성이 가장 높다. dsh 조사의 D05·D06과 함께 스파이크로 다루는 편이 낫다.

### 아직 모르는 것

- **xsm에 "모델이 잊는" 지점이 어디인가.** AgentTeams 문서는 컨텍스트 압축 뒤 통지 누락 사례를 근거로 들었다. XSM 일반 세션에서 같은 일이 발생하는 빈도는 조사하지 않았다. owned의 코드 발행 경로와, 일반 세션에서 회신 호출 자체가 누락되는 경로를 분리해야 한다.
- **"막힘"을 누가 푸는가.** AgentTeams에서는 Leader의 결정(`accept_task_result`)이 고리를 닫는다. XSM에서는 현재 요청자·업무상 팀장·사용자 승인 창구가 다를 수 있다. 생성자에게 모두 귀속하지 않고, 선택한 조직의 역할과 질문의 회신 경로를 기준으로 정해야 한다.
- **Stop 훅 차단의 비용.** AgentTeams 게이트는 채널이 최종 답의 전송을 쥐고 있어서 가능하다. xsm은 네이티브 하네스의 답을 막을 수 없다. 턴 종료를 막는 것은 답을 막는 것과 다르다.

## 12. 따르지 않을 것

아래는 XSM 핵심 통신 계약의 일률적인 기본값으로 채택하지 않을 장치다. 사용자가 선택한 조직의 배분·검토·수락 절차는 스킬과 자연어 지시로 구성할 수 있다. 기각 범위와 조직 활용의 자유를 구분한다.

| 항목 | 이유 |
|---|---|
| Matrix 서버·게이트웨이·S3를 전제로 하는 구조 | 별도 런타임에 의존하지 않는다는 경계(INTENT.md, ADR-0003)와 어긋난다 |
| 모든 세션을 컨트롤러 소유로 만드는 전제 | 기존 사용자 세션을 그대로 연결하는 경로를 유지한다. 선택적인 워커 생성·owned 실행과 필수 컨트롤러는 구분한다 |
| 모든 회신에 Leader의 명시적 수락을 강제하는 2단계 | 팀장이 결과를 검토·수락하는 운영은 선택 가능하다. DM과 보드로 그 절차를 구성하되 N:N 통신 전체의 필수 왕복으로 만들지 않는다 |
| 모든 대화를 사람이 있는 방으로 제한 | XSM은 수신자를 지정한 세션·다중 수신·팀 DM을 제공한다. 사람에게 보여 줄 진행과 결정은 조직별 보드·보고 규칙으로 정한다 |
| L1/L2/L3 권한과 power level | 여러 사람이 한 배포를 쓰는 조직용이다. xsm은 한 사용자의 세션이 대상이다 |
| 런타임 블록 봉투 전체 | 대시보드 렌더링용이다. 점진 도입 규칙만 참고한다 |
| 하트비트를 깨우기에 쓰지 않는다는 결론의 수치 | QwenPaw 고유 설정이다. Claude·Codex에는 그대로 옮길 수 없다 |

## 13. 조사 한계와 미검증

- 2026-11-04 보정은 `c61799f`의 관련 XSM 코드·조직·스킬 문서를 대조한 자체 검토다. AgentTeams 원본의 전수 재검증, 런타임 실행, 실패 상한 충돌 재현과 모델 행동 평가는 하지 않았다. 아래 독립 검증 기록은 원조사에 대한 것이며 이번 보정의 독립 검증을 뜻하지 않는다.
- 정적 조사다. 테스트(`make test`, Ruby·Go·Python 테스트)를 돌리지 않았으므로 통과 여부를 알 수 없다. 받은 코드를 실행하지 않았다.
- `agentteams-controller`(Go) 본체, Helm 차트, Manager 스킬 16개, Hermes·OpenClaw·QwenPaw 런타임, 블로그 글은 자세히 읽지 않았다. Matrix 채널 `channel.py`는 인용한 구간만 읽었다.
- `task-completion-notification.md`의 v2 내용 일부(`PROJECT_COMPLETED`, 승인 선택지)는 문서만 읽었다. 승인 선택지는 문서 스스로 "제안, 동작 변경 없음"이라고 밝힌다.
- AgentTeams가 DSH `0.1.1-rc.2`를 워커로 감싼다는 점은 README에서 읽었다. dsh-superagent가 요구한 `dsh ^0.2.1-alpha.2`와는 버전이 달라, 두 조사의 DSH 동작이 같다고 가정하면 안 된다.
- xsm 쪽 "없다", "찾지 못했다"는 지정한 파일의 grep 범위 안의 결과이며 부재의 증명이 아니다. Stop 훅 부재(`hooks/hooks.json`, `hooks/codex-hooks.json`), 작업 시도 상한 외의 반복 상한, 일반 세션의 자동 전달·응답 고리가 여기에 해당한다. owned 결과 발행 경로의 존재와는 구분한다.
- 작성 뒤 독립 사실 검증을 한 번 거쳤다. 명백한 오류는 없었고, 부정확한 표현 10건(xsm 질문 상태 목록, 시도 상한의 셈 방식과 위치, A01의 재현 경로, 이슈 번호 귀속, 인용 줄 범위, 이력 항목 필드, 전이표 테스트 언어 등)을 고쳤다. 검증도 정적 대조였고, 별 수와 저장소 생성일은 대조하지 못했다. 수정본을 다시 전체 검증하지는 않았다.

## 출처

[1] README: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/README.md

[2] 아키텍처: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/architecture.md

[3] 완료 통지와 사람 호출: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/task-completion-notification.md

[4] 전이 엔진: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/teamharness/task-transition-engine.md

[5] Project/Task 런타임 설계: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/teamharness/project-task-runtime-design.md

[6] Matrix 채널: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/plugins/agentteams-matrix-channel/agentteams_matrix/channel.py

[7] TeamHarness 경계: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/teamharness/boundary-and-contracts.md

[8] 깨우기와 자기 트리거: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/teamharness/wakeups-and-self-triggers.md

[9] Kubernetes 네이티브 오케스트레이션: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/k8s-native-orchestration.md

[10] 방 권한: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/room-power-levels.md

[11] Worker Chats API: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/worker-chats-api.md

[12] 런타임 블록 프로토콜: https://github.com/agentscope-ai/AgentTeams/blob/c69037acb24c99a3c4a91517d5b6ce15f888e9d7/docs/design/runtime-block-protocol.md
