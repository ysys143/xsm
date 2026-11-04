# dsh-superagent 조사: 사람의 주의를 아끼는 상주 에이전트와 메시지 소유권

- 조사일: 2026-11-02
- 질문: DeepSeek의 dsh-superagent는 요청 수락·실행·복구·사람 호출을 어떻게 설계했으며, xsm에 참고할 것과 따르지 말아야 할 것은 무엇인가?
- 대상: [deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype/tree/main)
- 방법: 고정 커밋의 문서 전부(`docs/000`~`007`, `008`은 개요와 앞부분), 프롬프트 전부, 핵심 코드의 정적 분석. **빌드·테스트·실행은 하지 않았다.** 아래의 동작 설명은 문서와 코드에서 읽은 내용이며 관측 결과가 아니다.
- 현행 xsm과의 관계: 최초 비교 기준은 xsm `c388f5c`(0.5.2 뒤)다. 최초 조사 중 다른 세션이 `d6d2cd1`로 커밋한 `xsm/cli.py`, `xsm/operations.py`, `xsm/owned_service.py`, `tests/test_owned_interfaces.py` 변경은 당시 비교에 포함하지 않았다.
- XSM 비교 보정: 2026-11-04, `c61799f` 기준으로 조직 모델, 일반 세션과 owned worker의 결과 처리, 최종 outcome과 대기 상태, 승인 기록·스킬 안내를 정적으로 대조했다. 13~15절의 관련 비교와 검토 의견을 갱신했다. 상대 제품의 고정 소스·실행 동작을 새로 검증한 것은 아니다.
- 효력: 이 노트는 레퍼런스 분석이며 ADR의 상태를 바꾸지 않는다.
- 함께 볼 문서: [AgentTeams 조사](agentteams.md). 막힘·중단·실패, 완료 통지, 사람 대기 기록의 겹침을 함께 검토한다.

## 요약

dsh-superagent는 **GitHub 저장소 하나(선택적으로 Feishu 채팅)를 지켜보다가 허용된 사람의 요청을 작업으로 바꿔 처리하는 상주형 코딩 에이전트**다. DeepSeek Harness(이하 DSH) 번들로 패키징되어 있다. 호스트가 이벤트를 받아 SQLite에 기록하고, 라우팅 전용 세션(main Session)이 판단하고, 작업마다 Executor Session 하나와 디렉터리 하나를 둔다.[1][2]

설계 원칙은 "사람의 주의를 가장 적게 쓰고 가장 큰 가치를 준다"이다. 메시지·알림·질문·설정·패널 요소가 모두 주의 비용으로 평가된다.[3]

두 제품의 실행 구조는 다르다. dsh-superagent는 호스트가 세션을 소유하고 모든 메시지를 중앙에서 받는다. xsm은 기존 세션을 연결하며 선택적으로 워커를 생성·관리하지만, 별도의 중앙 오케스트레이터를 필수로 두지 않는다. 참고할 핵심은 **처리 책임·대기·보고를 명확히 하는 계약**이다.

xsm에서도 사용자가 지정한 팀장이 요청을 배분하고 결과를 수락하는 조직을 구성할 수 있다. [조직 구성과 권장 개발 운영 모델](../xsm/ORGANIZATION.md)은 장기 병렬 개발에 팀장과 수평 워커를 강력히 권고하면서 다른 조직도 허용한다. 통신 계층이 보장할 사실과, 선택한 조직의 스킬·자연어 지시로 수행할 절차를 구분해 적용한다.

가장 큰 참고점은 세 가지다.

1. **메시지 처리 책임 추적.** 메시지마다 "지금 누가 책임지는가"를 계산한다. 담당자가 맡거나, 사유를 붙여 돌려주거나, 끝날 때까지 손대지 않으면 시스템이 되돌린다. 전달됐는데 아무도 처리하지 않은 메시지가 조용히 사라지지 않게 하는 장치다.
2. **"읽음"의 관측 정의.** 도구가 메시지를 꺼낸 시점이 아니라 세션 기록에 들어간 시점을 읽음으로 삼고, 그 뒤 보고나 턴 종료가 있어야 읽은 것으로 인정한다.
3. **사람 대기의 구조화.** 사람을 기다리는 상태를 자유 텍스트가 아니라 구조화된 필드에서 도출한다. 질문은 한 슬롯에 하나이며 갱신 규칙이 정해져 있다.

한계도 분명하다. README가 연구 프로토타입이며 내부 버전과 다르다고 밝히고, 원문 글 *Exploring Super-agent Design*은 찾지 못했다. 이 설계가 운영에서 효과가 있었다는 근거는 저장소 안에 없다.

## 1. 소스와 버전 고정

| 대상 | 고정값 | 해석 |
|---|---|---|
| 조사 커밋 | `6337fc823ce20251c8de8085948165c81aaa701e` | 2026-10-31 20:05 +08:00, `feat: add the dsh-superagent research prototype` |
| 저장소 생성 | 2026-10-31 09:32 UTC | GitHub 메타데이터. 조사 시점 별 9,979개 |
| 패키지 | `dsh-superagent` 0.1.0, `private: true`, MIT | `package.json` |
| 요구 런타임 | Node `^22.19.0` 또는 `>=24.0.0`, `dsh ^0.2.1-alpha.2` | `package.json` |
| 규모 | `src` 111개 파일 15,587줄(`.ts`·`.tsx` 110개는 15,205줄), `tests` 65개 파일 14,960줄, 프롬프트 15개 파일 438줄 | clone에서 측정. 줄이 긴 편이라 줄 수만으로 분량을 비교하면 안 된다 |
| 제3자 의존 | Cordis 메타프레임워크 위의 DSH 플러그인 | Cordis 논문은 arXiv 2608.25512. 이번 조사에서 논문 본문은 초록만 읽었다[4] |

경로 인용은 모두 고정 커밋 기준이며 `https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/` 뒤에 붙이면 원본이다. xsm 경로는 이 저장소 기준이다.

README는 다음을 명시한다. 코드의 상당 부분을 코딩 에이전트가 작성했고, 공개용으로 고쳐서 내부 버전 및 글의 구현과 다르며, 글의 일부 설계는 미구현이다.[1]

## 2. 제품 경계와 실행 구조

### 무엇이 돌아가는가

- 전용 DSH 프로필 `superagent`와 `127.0.0.1` 패널. 사용자가 일하는 프로필과 분리한다. 플러그인이 프로세스 전역 `PATH`와 git 설정을 바꾸기 때문이다(`docs/006-deployment.md:7`).
- 전용 GitHub 계정과 선택적 Feishu 봇.
- 호스트 안의 `Runtime`이 `Engine`, `Store`, `Effects`, `SourceRegistry`, `DshExecutor`, `Sessions`, `Outbox`, `MasterAssessor`를 조립한다(`docs/007-architecture.md:7-22`, `:29-43`).
- 평소 쓰는 프로필에 매시간 상태를 점검하는 예약 작업을 둔다. 에이전트 서비스가 죽어도 살아 있어야 하기 때문이다(`docs/006-deployment.md:133-141`).

### 세션 역할

| 역할 | 코드 이름 | 하는 일 | 못 하는 일 |
|---|---|---|---|
| main Session | `orchestrator` | 후보 판단, Ticket 생성·연결·중단, 사람에게 보낼 답 작성 | 코드 조사·기술 판단(프롬프트 규칙), 긴 대기(코드 가드) |
| Executor Session | `worker` | Ticket 하나의 조사·구현·검증, 후속 메시지 판단 | 사람에게 직접 묻기, 다른 세션 시작, 프로필 변경(도구 제거) |

main Session에는 응용 도구 14개, Executor에는 6개가 있다(`docs/007-architecture.md:490-532`). Executor의 응용 도구는 다음 여섯이다.

| 도구 | 역할 |
|---|---|
| `orchestrator_read` | 자기 Ticket 자원 읽기 |
| `orchestrator_ack` | 사람 요청을 맡았다고 확인 |
| `orchestrator_report` | `progress`/`ready`/`blocked`/`failed`/`dropped` 보고. 질문은 `human_action` |
| `orchestrator_thread_unrelated` | 잘못 연결된 스레드 해제와 소유 메시지 반환 |
| `orchestrator_thread_follow` | 관련 스레드를 문맥용으로 구독 |
| `orchestrator_trigger_handback` | 범위 밖 메시지를 사유와 함께 한 번 반환 |

### 공통 흐름

Source가 Trigger를 만든다. Trigger는 Thread에 쌓이고, 구독한 Ticket으로 팬아웃된다. Ticket에 닿은 사람 메시지는 그 Ticket의 것이고, 나머지는 Eval로 간다. Eval이 수락하면 Mandate를 가진 Ticket이 생긴다. Assignment가 Ticket을 Executor에 묶고, 결과는 Channel로 Source에 돌아간다(`docs/001-domain.md:5-19`).

## 3. 도메인 모델

### 핵심 개념

| 개념 | 정의 | 지키는 규칙 |
|---|---|---|
| Source | 이벤트 흐름. kind는 재사용 구현, instance는 설정 하나 | 읽기 위치와 봇 신원을 가진다. 재시작이 이벤트를 재생하면 안 된다 |
| Trigger | 불변 이벤트 하나 | 두 번 받아도 Ticket은 하나. 감사와 멱등의 단위 |
| Thread | 시간순 Trigger. Source가 범위를 정의 | Eval은 한 번에 하나. Ticket은 여러 개 가능 |
| Correlation | 한 Trigger가 속한 Thread 사이의 관계 | 문맥만 더하고 라우팅하지 않는다 |
| Channel | Thread의 쓰기 측 | 응답·PR·리뷰 해결이 모두 쓰기 |
| Policy | 버전 있는 평가 규칙과 Source별 허용 범위 | 다른 Source의 신원을 서로 연결하지 않는다 |
| Eval | Trigger 묶음에 대한 판단. gate와 assessment 2층 | 상태를 갖지 않는다. 결과는 Decision |
| Mandate | 수락이 주는 권한. Policy 버전·범위·강도·규칙·발신자·수신 경로 | 불변. 범위를 넓히면 새 Ticket |
| Ticket | 승인된 작업 단위 | Eval만 만든다. 상태는 Executor를 따라가지 않고 자기가 정의 |
| Assignment | Ticket과 Executor 인스턴스의 결합 | Ticket 하나에 여럿. 최종 보고만 Ticket을 끝낼 수 있다 |
| Subscription | Ticket과 Thread의 다대다 관계 | 권한 없이 문맥만 전달 |

출처: `docs/001-domain.md:25-37`.

사람은 도메인 개념이 아니다. Trigger에 실린 식별자일 뿐이고, 허용 목록은 Source별 Policy의 일부다. 여러 플랫폼의 계정이 같은 사람이라는 사실은 프롬프트 텍스트로만 다룬다(`docs/001-domain.md:39`).

### 기각한 개념

저장소는 기각 이유를 표로 남긴다(`docs/001-domain.md:45-60`). 설계 판단을 배우기에 가장 밀도가 높은 부분이다.

| 기각 | 이유 |
|---|---|
| Principal·Membership 엔티티, 계정 연결 | 사람은 Trigger 메타데이터, 허용 목록은 Policy 일부 |
| Eval의 자체 지연 Trigger | 기다리는 조건은 평범한 Source다. Eval은 Source에 역의존하지 않는다 |
| 대기·철회 Eval 상태 | 대기는 Source 몫. 시간이 다한 Eval은 재대기하거나 `unavailable`로 끝난다 |
| Thread당 live Ticket 하나 | 한 스레드에 독립 작업이 여럿일 수 있다 |
| "Ticket에 덧붙이기" Decision | 덧붙이기는 팬아웃이고 Eval이 필요 없다 |
| 구독의 admission 검사 | 구독은 스레드 전체, Mandate가 권한과 문맥을 분리 |
| 라우팅하는 Correlation | 구독만 라우팅한다 |
| DSH Session을 따르는 Ticket 상태 | 인계·재개·복수 Executor 때문에 자체 상태 필요 |
| Executor가 "사람이 멈추라 했다"고 선언 | 끝의 강도는 Eval만 정한다 |
| 정책 변경 시 실행 중 Ticket 취소 | 반쯤 끝난 작업이 남는다. 기록하고 전달한다 |
| 실패·차단 시 세션 도구 전체 잠금 | 직접 작업하는 사람과 복구 뒤 보고를 막는다. 자동 입력만 멈춘다 |
| 보고 자유 텍스트로 "사람 대기" 추론 | 분류에는 구조화 사실이 필요하다. 구조화 필드로 묻는다 |

## 4. 메시지의 두 경로

### Eval 경로: 일을 시작할지 판단

Source가 메시지를 `mention` 또는 `direct`로 표시하고 gate가 발신자와 Policy를 검사한다(`docs/002-authorization.md:9-16`, `src/policy.ts:191-211`).

| 강도 | 경우 |
|---|---|
| explicit | 허용된 사람이 에이전트를 지목, 또는 Ticket이 있는 Thread에서 후속 발언, 또는 admission 칸이 explicit |
| inferred | 허용되지 않은 사람의 후속 발언, admission 칸이 inferred, 봇 목록의 봇 메시지 |
| 불허 | 그 밖의 봇, 표가 무시하는 것, accept 모드 `off`에서의 모든 inferred |

admission 표의 행은 수신 범위, 칸은 "목록 포함 여부 x 지목 여부"다. 기본값은 목록 안 비지목이 inferred, 목록 밖은 ignore다(`docs/002-authorization.md:56-73`).

accept 모드는 `off`, `observe`(기본), `auto`다. `observe`는 "수락했을 것"이라고 기록만 한다. 팀이 기록을 검토한 뒤 `auto`로 넘어가게 하는 장치다(`docs/002-authorization.md:91-101`). 추정 후보의 수락에는 활성화된 규칙 전체를 하나씩 판정한 평가가 필요하다.

평가는 세 가지 독립 사실을 먼저 세운다. 이 프로젝트를 겨냥하는가, 구체적 변경 의도가 있는가, 방향이 작은 수정을 할 만큼 정해졌는가(`prompts/admission.md:17`). 규칙이 충돌하거나 범위가 모호하면 조용히 무시한다. 확인 질문으로 사람을 부르지 않는다.

### Subscription 경로: 이어지는 작업

구독된 Thread의 메시지는 봇·CI 포함 모두 구독 Ticket에 문맥으로 도달한다. gate를 거치지 않고, 권한도 주지 않는다(`docs/002-authorization.md:18-20`).

한 메시지는 **하나 이상의 Ticket**에 닿을 수 있다. 그래서 소유도 배타적이지 않다. 5절의 규칙은 "모든 소유자가 손을 떼어야 Eval로 간다"이다.

## 5. 메시지 소유권: 가장 참고할 만한 계약

### 소유자 계산

소유자는 저장된 값이 아니라 기록에서 계산한다(`src/core/model.ts:75-88`의 `followupOwners`).

1. 사람 메시지가 아니면 소유자가 없다.
2. 사람이 재평가를 요청했다면 소유자가 없다.
3. 메시지가 닿은 Ticket에서, 이미 돌려준 Ticket과 문맥 전용 Ticket을 뺀다.
4. 메시지가 Eval 중이면 소유자가 없다.
5. 남은 Ticket 중 살아 있는 것, 또는 사람이 멈추지 않았고 메시지가 재개를 기다리는 것이 소유자다.

`intake`는 소유자가 없을 때만 메시지를 Eval로 보낸다(`src/core/intake.ts`). 그래서 사람의 "이어지는 대화"가 다시 라우터를 거치지 않는다. 소유자는 사람 메시지에만 생기므로, 봇·CI 메시지는 구독 Ticket에 문맥으로 가면서 Eval로도 간다.

### Executor의 세 선택

프롬프트는 Executor에게 사람 메시지를 스스로 결정하게 한다(`prompts/work.md:9`).

| 메시지 성격 | 행동 | 기록 |
|---|---|---|
| Ticket 범위 안의 요청 | 처리하고 `orchestrator_ack` | `disposition.acked`에 Ticket 추가(`src/core/part.ts:50-55`) |
| 범위 밖이거나 다른 Ticket의 일 | 한 문장 사유와 `orchestrator_trigger_handback` | `disposition.handbacks`(`src/core/part.ts:42-48`) |
| 평범한 대화·감사 | 답하지 않는다 | 읽음만 남는다 |

"조용히 버리지 말라(`never drop a request silently`)"가 명시되어 있다. 돌려주기는 메시지당 한 번이고 Ticket의 구독은 유지된다. 호출은 재평가 대기열에 들어갔는지를 `queued`로 돌려준다. 다른 Ticket이 아직 소유하거나, 이 Ticket이 소유한 적 없는 메시지(봇 메시지 등)이면 `false`다(`src/app/tools/executor.ts:66-73`, `docs/007-architecture.md:530`).

돌려받은 메시지를 main Session이 같은 Ticket에 다시 붙이는 일은 코드가 거부한다(`src/core/engine.ts:111-113`, 오류 `handedBackHere`). 왕복 고리를 막는 장치다.

### 끝날 때 되돌리기

Ticket이 끝나면 다음 메시지를 놓아 준다(`src/core/tickets.ts:345-364`의 `end`, `:294-309`의 `letGo`).

- Executor가 받지 못한 메시지.
- 마지막 보고 또는 턴 종료 **전에 읽지 않았고**, ack도 답도 돌려주기도 하지 않은 사람 메시지.

놓인 메시지는 다른 소유자가 없고, 아무도 맡지 않았고, Decision이 해결하지 않았다면 Eval로 돌아간다(`src/core/tickets.ts:304-307`). 읽었지만 행동하지 않은 메시지(감사 인사 등)는 돌아가지 않는다(`docs/003-execution.md:112`).

재개가 거부된 Ticket도 같은 경로를 쓴다. 메시지는 "닿지 않은 것"으로 취급되어 Eval로 간다(`docs/002-authorization.md:141`).

여기서 눈여겨볼 경계 사례가 있다. 최종 보고를 쓰는 동안 도착한 메시지다. 보고 뒤에는 Executor가 돌려줄 수 없으므로 시스템이 대신 놓는다. 주석이 이 이유를 그대로 적고 있다(`src/core/tickets.ts:339-344`).

### PR 닫힘과의 경합

PR이 닫혀도 두 경우에는 Ticket을 끝내지 않는다(`src/core/tickets.ts:370-379`의 `unfinished`).

- Executor가 맡은 사람 메시지를 읽은 뒤 progress가 아닌 보고나 턴 종료를 아직 하지 않은 경우.
- 닫힘 뒤에 재개·재시도·복구된 작업이 `ready` 보고를 하지 않았거나, 미전달 입력이 있거나, 그 보고 뒤에 입력이 온 경우. 정책 변경 입력은 세지 않는다.

이때 Ticket은 이후의 `ready` 또는 `dropped` 보고로 끝난다. 외부 사건이 진행 중인 약속을 지우지 않게 하는 규칙이다.

## 6. 권한

`docs/002-authorization.md:5`의 핵심 문장은 "호스트가 허용 목록·규칙·Mandate를 강제한다. 메시지·댓글·인용 문서는 판단의 입력이며 권한을 바꾸지 못한다"이다.

### Mandate

Mandate는 수락할 때 만들어지고 불변이다. 바뀌는 경우는 셋뿐이다. 수락이 만들고, 사람의 중단이 철회하고, 재검증 실패가 취소한다(`docs/002-authorization.md:129`). Ticket이 끝나도 Mandate는 끝나지 않으므로, 사람의 후속 메시지가 새 Eval 없이 같은 작업을 재개할 수 있다.

재개 전 재검증은 Mandate의 근거에 따라 다르다(`docs/002-authorization.md:131-139`, `src/policy.ts:213` 이하).

| 근거(`via`) | 재검증 조건 |
|---|---|
| 공통 | Source가 그 Thread를 아직 듣는다 |
| `followup` | explicit이면 통과. inferred면 `auto`와 규칙 유지 |
| `admission` | 현재 표와 소속으로 원래 강도 이상을 받는다. inferred 칸이면 `auto`와 규칙 유지도 필요 |
| `bot` | 봇 목록에 남아 있고, `auto`와 규칙 유지 |
| `addressed` | 발신자가 허용 목록에 남아 있다 |

실패하면 Ticket은 끝난 채로 남고, 기다리던 메시지는 닿지 않은 것으로 처리된다.

### 정책 변경

정책 버전은 규칙·accept 모드·Source별 정책을 해시한다(`src/policy.ts:116`). 버전이 바뀌면 실행 중 Eval을 버리고 Trigger를 다시 대기시키며, 영향을 받는 Ticket에만 알린다. Mandate를 바로 철회하지는 않는다(`docs/002-authorization.md:107-117`). 영향 없는 Ticket에는 알리지 않는다.

### 중단

- Thread에서 사람이 "멈춰"라고 하면 평범한 Trigger이고 Eval이 stop을 결정한다.
- 패널의 Stop은 명령이다.
- Executor는 "사람이 멈추라 했다"고 선언할 수 없다.
- 사람이 멈춘 Ticket은 끝난 채로 남고 아무것도 받지 않는다.

출처: `docs/002-authorization.md:125-145`.

### 후속 메시지 소유와 main Session의 제한

Executor가 메시지를 소유하는 동안 main Session은 사람 요청에 따른 중단만 할 수 있다. accept·attach·ignore·requeue는 거부된다(`docs/002-authorization.md:26`). 사람은 패널에서 소유 메시지를 Eval로 보낼 수 있지만 도구로는 안 된다(`docs/007-architecture.md:598`).

## 7. 실행

### Ticket 단계

위에서부터 첫 일치가 단계다(`docs/003-execution.md:5-19`, `src/core/stage.ts:9-22`).

| 단계 | 조건 | 패널 표시 |
|---|---|---|
| person / delivery | 입력 전달 실패 | Input undelivered |
| person / answer | Attention이 있음 | Awaiting answer |
| person / review | 최신 보고가 `ready` | Awaiting review |
| person / blocked, failed | 최신 보고가 그렇고 이후 사람 메시지 없음 | Blocked, Failed |
| working / queued | Assignment 없음 또는 pending | Queued |
| idle | 최신 보고가 `waiting` 또는 Assignment 종료 | Waiting for a Trigger |
| working | 나머지 | Working |

단계는 저장되지 않고 사실에서 계산된다. 라벨은 내부 상태가 아니라 "누구를 무엇 때문에 기다리는가"를 말한다(`docs/005-panel.md`의 원칙 2).

### 슬롯과 사람 우선

활성 턴과 launch가 worker slot을 잡는다. 상한을 넘어 **사람의 메시지나 상태 요청을 위한 슬롯 1개**가 더 있다. 새 작업이 사람의 기존 작업 계속을 막지 못한다. CI 같은 다른 입력은 일반 슬롯을 기다린다(`docs/003-execution.md:55-61`).

### 쉘과 백그라운드

- Executor의 전경 쉘 명령은 5초 뒤 백그라운드 작업으로 옮겨진다. 긴 명령이 사람 메시지를 막지 않게 하기 위해서다(`cordis.patch.yml:14-16`, `docs/003-execution.md:27`).
- 백그라운드가 남은 채 턴이 끝나면 슬롯을 유지한다. 완료가 Executor를 깨운다.
- 턴 뒤 최대 30분이고, 넘으면 작업을 죽이고 waiting으로 보고한다.
- 사람에게 넘길 때는(`ready`, 질문, `blocked`, `failed`) 슬롯을 즉시 풀고 서브에이전트를 멈춘다. 쉘 작업은 Assignment가 끝날 때까지 남을 수 있다. 사람이 시험할 서버를 띄워 둔 경우를 위한 예외다.

출처: `docs/003-execution.md:31-47`.

### main Session은 기다리지 않는다

`noWait` 가드가 `sleep`, 30초 초과 쉘 타임아웃, 5초 초과 job 대기를 거부한다(`src/app/sessions.ts:77-86`). 정규식은 명령 위치의 `sleep`을 찾는다(`src/app/sessions.ts:70`). 보고·후보·작업 결과는 스스로 도착하며, 기다리는 step이 새 후보를 늦추기 때문이다(`docs/007-architecture.md:513`).

### 재시작

실행 중 Assignment는 "host restarted"로 끝나고, 복구 노트를 가진 새 Assignment가 오래된 Ticket부터 시작한다. 복구 노트는 외부 조치를 반복하기 전에 디렉터리·git 이력·GitHub 상태를 확인하고, 이미 끝난 외부 작업을 반복하지 말라고 지시한다(`src/core/assignments.ts:21`). 이미 대기·완료·차단·실패 보고를 했고 그 뒤 입력이 없는 Assignment는 세션을 유지한다(`src/core/assignments.ts:83-92`).

모델 제공자나 네트워크의 일시 실패는 지정된 조건(408, 429, 5xx, 연결 거부·리셋·타임아웃)에서 세 번 재시도한다. prepare 명령 실패는 재시도하지 않는다(`docs/003-execution.md:124`).

## 8. 신뢰성

### 저장 먼저, 실행은 나중

Engine의 모든 메서드는 동기이고 명령마다 트랜잭션 하나다. 포트는 트랜잭션 안에서 외부 작업을 대기열에 넣고, 어댑터가 커밋 뒤 실행한다(`docs/007-architecture.md:48`).

`Effects`(`src/app/effects.ts`)는 영속 부수효과 큐다.

| 종류 | 동시 수 | 재시도 |
|---|---|---|
| `assessment` | 4 | 2초에서 60초까지 배증 |
| `launch` | 빈 슬롯 수 | 일시 실패만 5초에서 300초, 3회 |
| `delivery` | 4 | 2초에서 60초 |
| `relay` | 1, 순서 유지 | 2초에서 60초 |
| `notice` | 1, 순서 유지 | 2초에서 60초 |
| `reply` | 1 | 5초에서 300초 |

출처: `docs/007-architecture.md:166-181`. `Later` 예외는 실패로 세지 않고 미룬다(`src/app/effects.ts:5`). 세 번 연속 실패해야 상태 오류가 된다(`src/app/effects.ts:7`). "일회성 네트워크 오류로는 사람을 부르지 않는다"는 원칙의 구현이다.

### Outbox

나가는 메시지는 영수증을 저장하고 효과를 넣는 일을 한 트랜잭션으로 한다(`src/app/outbox.ts:27-33`). 같은 Ticket의 같은 대화로 가는 메시지는 앞의 것이 나가거나 세 번 실패할 때까지 기다린다(`src/app/outbox.ts:45`). 응답 확인이 결과보다 늦게 도착하지 않게 하는 규칙이다.

메시지는 Source가 그 대화를 더 듣지 않거나, 대화가 영구히 사라졌을 때만 버려진다. 버려진 기록은 시각과 이유와 함께 남아 다시 대기하지 않는다(`docs/003-execution.md:185-191`). 프롬프트도 "버려진 메시지는 도착하지 않으니 다른 곳에 재전송하지 말라"고 지시한다(`prompts/replies.md:11`).

### 읽음의 정의

`inputsRead`는 세션 기록 진입(`user/message` 세션 이벤트)에서만 호출된다. 메시지를 클레임한 step이 모델 호출 전에 취소되면 읽지 않은 것이다(`src/executor/dsh.ts:493-505`, `docs/007-architecture.md:85`).

읽음이 인정되려면 진입 뒤 보고나 턴 종료가 따라와야 한다. `readBefore`와 `readUntil`이 그 비교를 맡는다(`src/core/tickets.ts:19-20`, `src/core/model.ts:341-344`). 재시도나 재시작은 이전 Assignment가 받지 못한 입력을 다시 건네고, 세션에 남은 복사본은 먼저 제거해 하나만 남긴다(`docs/003-execution.md:150-152`).

### 멱등 전달

`AgentDelivery`는 요청 ID에서 메시지 ID를 유도한다. 실시간 이벤트, 영속 이력, 대기 중 inbox를 모두 대조해 세션 복원 뒤에도 같은 메시지를 두 번 넣지 않는다(`src/app/delivery.ts:15-16`, `:61-64`). 플러그인 고유 source를 달아 사람이 쓴 메시지로 오인되지 않게 한다(`src/app/delivery.ts:27-29`).

### 장애 표시

- GitHub 읽기 실패는 해당 Thread에 머문다. 세 번 연속 실패한 폴링이 Source 오류가 된다. 비공개 저장소 접근을 잃어도 404가 오므로 404를 재시도한다(`docs/003-execution.md:164-170`).
- 처리 일시정지는 dispatch·Eval·전달·응답을 멈추지만 Trigger 기록은 계속하고, 진행 중 턴을 끊지 않는다. Eval 기한은 정지 시간만큼 뒤로 민다(`docs/003-execution.md:192-200`).
- 전달되지 못한 후보는 만료되지 않는다. 기한은 후보가 main Session에 도달한 때부터 잰다(`docs/002-authorization.md:149`).

## 9. 사람의 주의를 다루는 규칙

### 말할 조건

원칙은 다섯 줄이다(`docs/000-philosophy.md:11-15`).

- 요청받았거나 적어 둔 규칙이 허용할 때만 움직인다.
- 사람이 행동해야 하거나 결과를 쓸 수 있을 때만 말한다.
- 구체적 질문을 한 번에 하나만 묻는다.
- 노력이 아니라 영향으로 멈춘다.
- 정직하게 보고한다. 초안은 미완으로 표시하고, 실패는 실패로 보고하며, 묻지 않으려고 한도를 우회하지 않는다.

`prompts/team/communication.md`가 이를 행동 규칙으로 푼다. xsm 스킬 문구로 옮길 만한 표현은 다음과 같다.

| 줄 | 규칙 |
|---|---|
| 13 | 끼어드는 조건은 사람이 줘야 할 구체적 결정·권한·자원, 행동이 필요한 중대 위험, 완료 불가가 확정되어 요청을 닫아야 할 때뿐 |
| 14 | `blocked`/`failed` 라벨만으로는 메시지 사유가 아니다. 에이전트가 해결하거나 위임할 수 있으면 조용히 계속한다 |
| 18 | 보내기 전에 사람이 지금 검토·사용·결정·해소할 것을 짚는다. 없으면 보내지 않는다 |
| 30 | 작업 보고의 각 부분을 압축하지 말고 정보를 골라낸다 |
| 45 | 이미 승인된 일의 허락을 묻거나, 일상 구현 선호를 묻거나, 같은 결정을 반복 요청하거나, 변하지 않은 상태를 다시 보내지 않는다 |
| 51 | 절마다 묻는다. 지우면 사람이 결과를 이해하거나 행동하지 못하게 되는가. 아니면 지운다 |
| 53 | 마침표가 적다고 정보가 적은 것이 아니다. 세미콜론 연쇄로 욱여넣지 않는다 |
| 60 | 예시는 형식을 보여 줄 뿐 주장해도 되는 사실이 아니다 |

100단어는 프롬프트 권고가 아니라, Feishu(IM) 응답과 수락 확인 문구에 대해 전송이 거부하는 상한이다(`prompts/replies.md:27-28`, `src/app/outbox.ts:29`, `src/infra/text.ts:3`). GitHub 댓글에는 코드 상한이 없다. 긴 문장·연속 메시지로 우회하지 말라는 규칙이 뒤따른다. 정보는 줄이되 기록을 줄이지는 않는다. 사람에게 가는 메시지는 짧게, 근거는 PR과 내부 보고에 남긴다(`prompts/team/communication.md:48-50`).

### 질문 슬롯

Executor는 사람에게 직접 묻는 도구가 없다. `orchestrator_report`의 `human_action`에 질문 하나를 넣는다(`src/app/tools/executor.ts:80`).

| 입력 | 결과 |
|---|---|
| 생략 | 대기 중 질문 유지 |
| 같은 질문 | 기존 요청 재사용 |
| 다른 질문 | 새 요청으로 교체, 미전송 이전 질문은 outbox에서 철회 |
| `null` | 해제 |
| `ready` 보고 | 해제 |

출처: `prompts/handoff-worker.md:1-5`, `src/core/assignments.ts:113-124`.

교체 시 이전 질문의 전송 대기분을 철회하는 부분이 중요하다. 사람에게 이미 낡은 질문이 뒤늦게 도착하지 않는다. 질문이 있어도 Executor는 명확히 승인된 나머지 일을 계속할 수 있다(`state=progress`). main Session은 질문을 그대로 복사해야 하고, `purpose=attention` 응답은 현재 저장된 질문과 일치하지 않으면 거부된다(`src/core/replies.ts:77`). 질문은 그것을 일으킨 사람이 쓴 곳에서 묻는다(`question_for_trigger_id`).

### 응답 목적의 코드 강제

`orchestrator_reply`는 목적을 강제한다(`src/core/replies.ts:69-82`).

- `result`는 Ticket이 준비된 상태에서만.
- `attention`은 현재 구조화 질문에서만.
- `answer`는 원래 사람 질문을 가리켜야 하고, Executor가 그 질문에 답했다고 보고해야 한다. 허가는 메시지 하나로 소비된다.

진행 상황을 답으로 위장해 내보내는 경로를 코드로 막은 것이다.

### 패널

패널은 세 질문에 이 순서로 답한다. 지금 나를 필요로 하는 일이 있는가, 시스템은 건강한가, 작업 하나의 이력은 어떤가. 건강한 상태는 공간을 차지하지 않고, 숫자는 링크된 목록의 길이와 같아야 한다(`docs/005-panel.md`).

### 설치 대화

`SETUP.md`는 에이전트가 따르는 설치 지침이다. 한 번에 한 질문, 메시지당 300단어 이내, 권장 답을 함께 제시, 질문 중 실행 금지, 전체 계획 1회 확인, 비밀값은 채팅으로 받지 않음. 설치 자체에 같은 주의 원칙을 적용했다. 다만 이 지침이 실제로 잘 동작하는지는 실행해 보지 않았다.

### 리뷰

- 고쳤고 검증한 지적은 조용히 해결한다.
- 거절한 제안에는 한 문장 사유를 남긴다.
- 자동 리뷰어는 틀릴 수 있는 입력이지 권위나 완료 관문이 아니다.
- 자동 리뷰어별로 PR당 3라운드까지만 대응한다. 라운드는 인라인 댓글이 아니라 리뷰 실행 하나이며, 작업자·재시작·후속 Ticket을 넘어 센다. 다음 작업자가 이어 세도록 `orchestrator_report`에 기록한다(`prompts/team/communication.md:83-97`).

### 중복 작업 양보

사람의 브랜치나 PR이 Ticket의 코드를 포함하면 묻지 않고 자기 PR을 닫으며 한 문장을 남긴다. 관련만 있고 코드를 포함하지 않으면 닫지 않는다(`prompts/team/delivery.md:27-28`).

### 대기 지시의 유지

사람의 명시적 중단이나 확인 대기 요청은 후속 메시지·새 세션·재시작을 넘어 유지되며, 질문이나 새 단서로 풀리지 않는다. 자동 CI나 봇 피드백은 멈춘 구현을 재개하지 못한다(`prompts/team/scope.md:19-21`).

## 10. 프롬프트와 모델 표면

### 조립과 우선순위

시스템 프롬프트 조립 순서는 공용 지침과 역할, 팀 섹션 3개, 구독과 응답, dispatch 또는 work, admission(main만), 인계 지침, 실행 환경, Policy(main만)다. Policy를 맨 뒤에 둔 이유는 정책이 바뀌어도 앞쪽 프롬프트가 그대로 유지되게 하기 위해서다(`docs/004-prompts.md:46-59`).

우선순위는 강한 순으로 다음과 같다(`docs/004-prompts.md:65-71`).

1. 도구와 호스트가 강제하는 사실.
2. 내장·생성 섹션과 팀의 override.
3. 능동 Ticket의 일치 규칙 안의 절차와 소통(그 Executor에만).
4. 팀 섹션과 팀 스킬.
5. 외부 텍스트. 데이터이며 규칙이나 권한을 바꾸지 않는다.

### 프롬프트 버전

저장할 때마다 불변 버전이 생긴다. 저장은 기준 리비전을 명시하고, 충돌하면 초안을 버리지 않고 거부한다. 세션은 모델 요청마다 최신 버전을 읽고, 호스트가 세션이 쓴 리비전을 기록한다(`docs/004-prompts.md:91-96`). override는 어느 기본 문구를 바탕으로 했는지 기록하며, 기본값이 바뀌면 패널이 "Default updated"로 표시하고 차이를 보여 준다(`docs/004-prompts.md:40`).

### 표면 드리프트 검사

`tests/model-surface.spec.ts`는 모델이 읽는 모든 것(도구·프롬프트·스킬·입력)을 수집해 다음을 검사한다.

- 등록된 도구, 스키마 옵션, 환경 변수, 용어집 단어만 언급하는가.
- 문구가 말하는 단어 상한을 실제로 강제하는가.
- 역할별 문자 예산 안인가. 프롬프트와 도구를 합쳐 orchestrator 59,000자, worker 40,500자다(`tests/model-surface.spec.ts:40`).

프롬프트 파일은 한 줄 한 문장이고 `promptFile`이 합친다(`docs/007-architecture.md:600`).

### 코드 강제와 프롬프트 규칙의 구분

| 구분 | 내용 |
|---|---|
| 코드가 강제 | gate와 Mandate 재검증, 응답 목적, IM 응답과 수락 확인의 100단어 상한, 돌려받은 메시지 재연결 거부, `noWait`, 역할별 도구 제한, Ticket 종료 뒤 도구 거부, 정책 저장 출처 제한 |
| 프롬프트 규칙 | main Session의 코드 조사 금지(`docs/007-architecture.md:507`이 도구 제한이 아니라고 명시), 자동 리뷰어 3라운드, auto-merge 200줄 기준, 침묵 기본값, 사람의 대기 지시 유지, "조용히 버리지 말라" |

"조용히 버리지 말라"가 프롬프트 규칙이어도, Ticket 종료 시 되돌리기는 코드가 하므로 이중 안전망이 된다. 다른 프롬프트 규칙에 코드 측 보완이 있는지는 전수 확인하지 않았다.

## 11. 구현 규율

| 규율 | 내용 |
|---|---|
| 상태별 단일 작성자 | Trigger·Thread·Decision·Ticket·Assignment는 Engine만, 영수증은 Outbox만, 건강 항목은 등록한 부분만 쓴다(`docs/007-architecture.md:259-271`) |
| 역할별 좁은 인터페이스 | 호출자는 역할에 맞는 Engine의 `Pick`만 받는다(`EngineForSources`, `EngineForMainSession`, `EngineForPeople`, `EngineForSettings`, `EngineForExecutor`) |
| 요청과 사실의 이름 구분 | 요청은 명령형(`stopTicket`), 어댑터가 보고한 사실은 과거형(`assignmentStarted`) |
| 코어 순수성 | `src/core`는 외부를 임포트하지 않고 I/O를 하지 않는다(`docs/007-architecture.md:258`) |
| 고정 거부 코드 | 사람이나 에이전트가 유발할 수 있는 거부는 `UserError(code, values)`, 패널이 코드별로 문구를 낸다 |
| 사유 코드 | Decision의 이유는 코드와 값의 목록이며, 사람 말은 `said` 코드로 구분한다 |
| 문서 순서 검사 | 번호 문서는 앞 문서만 링크해야 하고, 아키텍처 표는 모든 모듈·테스트를 나열해야 한다(`docs/007-architecture.md:446`) |
| 실데이터 검토 | 임시 `DSH_HOME`에 백업 DB를 복사하고, Source를 끄고, 처리를 멈추고, CLI를 읽기 전용 대역으로 바꿔 변경을 검토한다(`docs/007-architecture.md:612`) |

## 12. 보안 경계와 스스로 밝힌 한계

문서가 스스로 경계가 아니라고 말하는 것들이다.

- 두 preset 모두 `danger-full-access`로 운영자 OS 사용자로 돈다. 격리하려면 전용 OS 계정을 써야 한다(`docs/006-deployment.md:19`).
- 계정 래퍼와 디렉터리는 기본값일 뿐 보안 경계가 아니다. 워커는 절대 경로로 프로그램을 실행할 수 있다(`docs/003-execution.md:80`).
- 어떤 Trigger 필드를 신뢰할지는 미결 질문이다(`docs/007-architecture.md:616`).
- 오래된 레코드를 지우는 기능이 없어 여러 저장소가 무제한으로 자란다(`docs/007-architecture.md:484`).
- auto-merge 지침은 에이전트를 다스릴 뿐 GitHub 병합 규칙이 아니다. 강제하려면 브랜치 보호를 쓰라고 안내한다(`docs/003-execution.md:90`).

조사자가 본 위험도 적는다.

- main Session 하나가 모든 판단을 거친다. `noWait`가 필요한 이유 자체가 이 병목이다.
- 철학은 "적은 개념"이지만 후속 메시지 소유 규칙의 예외는 많다. `docs/002-authorization.md`의 소유·반환·재개 규칙과 `src/core/tickets.ts`의 분기는 단순하지 않다. 그만큼 규칙이 정확한지 판단하려면 운영 표본이 필요한데 공개된 것이 없다.
- 프롬프트가 큰 몫을 맡는다. 예산이 있어도 worker 40,500자는 작지 않다.

## 13. xsm과 비교

최초 조사의 `c388f5c` 비교를 바탕으로, 아래 조직·수신 확인·결과 처리·사람 질문 항목을 `c61799f`에서 보정했다. 그 밖의 항목은 원조사의 정적 분석 범위이며 최신 제품 전체를 재검증한 표가 아니다.

| 축 | dsh-superagent | xsm | 참고점 |
|---|---|---|---|
| 세션 소유 | 호스트가 세션을 만들고 소유 | 기존 세션 연결과 선택적 워커 생성·owned 실행 | 필수 호스트와 선택적인 워커 관리의 차이를 구분한다 |
| 라우팅 | main Session과 gate | 통신 상대를 지정하고, 팀장의 배분·조율 역할은 자연어로 정한다 | 기본 통신 계약과 조직별 업무 절차를 분리한다 |
| 메시지 단위 | Trigger, Thread, 구독 팬아웃 | 메시지, 질문, 팀 DM, 보드 | 스레드 구독에 대응하는 개념은 보드 알림 정도 |
| 전달 증거 | 영수증과 입력 상태 | `ledger.py`의 다단계 증거, ADR-0018(Proposed) | 전달 증거는 xsm이 더 세밀하다 |
| 수신 확인 | 세션 기록 진입을 호스트가 관측 | inbox/ACK 증거와 120초 claim lease(`xsm/handoff.py:31`) | ACK와 업무를 맡았다는 표시는 별개다. 일반 세션에서 dsh와 같은 진입·턴 종료 결합 계약은 확인하지 못했다 |
| 처리 책임 | `followupOwners`, ack·handback·letGo | 일반 세션에는 전용 상태 없음. owned worker만 `reserved`/`acknowledged`/`running`/`unknown`(`xsm/owned_requests.py:22`) | 가장 큰 차이 |
| 결과 저장과 회신 | 보고를 저장한 뒤 outbox가 전송 | 일반 세션은 모델이 회신을 호출한다. owned worker는 실제 결과를 저장한 뒤 코드가 회신 발행을 시도하고 전송 근거를 기록한다 | owned의 저장·회수·재전송 경로와 일반 세션의 미응답 문제를 나눠 검토한다 |
| 답 없음 | 끝날 때 Eval로 복귀 | 회신이 없고 상태가 `held`·`blocked`·`refused`·`error`가 아니면 `pending`. 전달 확인(`delivered`), 오프라인, 미확인도 모두 `pending`으로 보인다(`xsm/questions.py:78-83`) | 아래 D04 |
| 작업 결과 | `ready`/`blocked`/`failed`/`dropped` | 최종 outcome은 `succeeded`/`failed`(`xsm/envelope.py:34`) | 대기·반환·중단과 최종 결과를 먼저 구분해야 한다. outcome 열거형만 늘리면 대기 중인 질문이 종료될 수 있다 |
| 사람 질문 | 슬롯 하나, 구조화 필드 | 결정 저널·네이티브 답 복구·생성자 측 가입 요청 경로가 있다 | 기존 요청 결속을 유지하면서 대기 이유와 보고 경로의 가시성을 검토한다 |
| 세션 상태 공개 | 단계 표 | directory의 busy/idle, ended/stale | 사람 대기 값은 찾지 못했다 |
| 권한 | gate와 불변 Mandate | 범위·연결·팀 권한, 동료 메시지는 권한 아님 | 원칙은 같고, 재개 시 재검증과 변경 통지가 추가 참고점 |
| 인계 | Assignment 교체, 복구 노트 | `xsm handover`: 팀 자리·보드 항목·미확인 DM·대기 질문·요약 이전 | xsm이 사용자 세션 인계는 더 풍부하다 |
| 반복 제어 | 프롬프트의 리뷰 3라운드 | `abuse.py`의 관찰 기본, 명시 한도 시 제한 | 리뷰어별·PR별 상한이라는 단위가 참고점 |
| 재시작 부수효과 | 복구 노트로 재확인 지시 | owned journal은 알 수 없는 부수효과를 자동 재시도하지 않음 | 방향이 같다 |
| 사람 슬롯 | 상한 + 1 | worker capacity 예약 | 사람 입력 우선 슬롯은 xsm에서 찾지 못했다 |
| 프롬프트 버전 | 불변 버전, base 추적 | 팀이 편집하는 프롬프트 없음 | 해당 없음 |

처리 책임 축의 주의점: `xsm/question_groups.py:97-98`의 `ended`는 명시적 final, 또는 `refused`·`selection-required`·`held`·`blocked`·`error`·`not-found` 상태만 뜻한다. 수신 세션이 끝났다는 뜻이 아니다. 질문 상태 계산(`xsm/questions.py`의 결과 구성)은 registry나 directory를 참조하지 않는다. 대상 해석만 `resolve`를 거쳐 registry를 쓴다.

세션 종료 자체는 xsm이 일부 안다. Claude는 `SessionEnd` 훅이 `registry.mark_ended`를 호출한다(`xsm/receive.py:351`, `xsm/registry.py:834`). 워커 정지, owned 턴 종료, 프로토콜 호스트 종료에서도 같은 기록이 남는다(`xsm/workers.py:1252`, `:1664`, `xsm/protocol.py:410`). Codex 훅에는 `SessionStart`와 `UserPromptSubmit`만 있어(`hooks/codex-hooks.json`) 일반 Codex 세션은 `stale`로 읽힌다(`xsm/install.py:43-44`). 충돌도 `mark_ended`를 호출하지 않으며, 그 차이가 `ended`와 `stale`을 가른다(`xsm/registry.py:836-838`).

팀 DM에 붙는 담당 표시나 소유 상태는 `xsm/multisend.py`, `xsm/board_service.py`에서 찾지 못했고, ADR-0025에도 DM 수준의 담당 규칙은 없다. ADR-0025는 받는 세션에게 다른 수신자 목록을 보여 주고(결정 5), `ask`는 수신자별 답을 모은다(결정 6). 결정 20은 "보드의 담당 항목"을 인수인계 대상으로 적고, 팀 문서는 담당 사실을 보드에 적도록 안내한다(`skills/xsm/references/teams.md:13`). 강제되는 소유 상태는 아니다.

2026-11-04 보정에서 확인한 코드 경로는 다음과 같다.

- [questions.py](../../xsm/questions.py)의 `_result`는 `envelope.OUTCOMES`에 속하는 회신이 있으면 `final`로 계산한다. 전달 상태의 `blocked`와 작업이 사람을 기다리는 상태도 서로 다른 개념이다.
- [owned_requests.py](../../xsm/owned_requests.py)의 `save_result`는 실제 결과·요약값·회신 ID를 저장하고, `claim_send`·`finish_send`는 발행 소유권과 전송 근거를 기록한다. [workers.py](../../xsm/workers.py)의 `run_owned`는 저장 뒤 회신을 시도한다. 결과 저장과 외부 전송이 하나의 원자적 트랜잭션이라는 보장은 아니다.
- [decisions.py](../../xsm/decisions.py)에는 요청별 결정 기록과 `capture_native_answer`가 있고, [delegation.py](../../xsm/delegation.py)의 `request_join`은 연결된 워커의 가입 요청을 생성자 세션으로 모은다. 새 사람 대기 체계를 설계하기 전에 이 기록으로 무엇을 관측할 수 있는지 확인해야 한다.

수평 협업에서는 **생성자·팀장·현재 요청자·원래 의뢰인**이 다를 수 있다. 팀장이 띄운 보조 워커에게 주력 워커가 일을 요청했다면 결과는 그 요청의 회신 경로로 돌아가고, 팀장은 필요한 진행을 공유받는다. 사람 판단은 정해진 창구로 모은다. 모두를 생성자에게 보고하는 규칙으로 합치지 않는다. 팀장들의 조율 팀도 별도의 협의 관계이며, 모든 작업 결과의 목적지가 자동으로 그 팀으로 바뀌지는 않는다.

## 14. 설계 참고와 후속 검증 조건

이 절은 조사자의 해석이며 구현 지시나 기존 ADR 변경이 아니다. 관련 ADR 0018·0020·0022는 Proposed 상태다. 19개 항목은 참고 후보로 보존한다. 기존 구현의 재사용, 조직별 운영 지침, 추가 재현·설계가 필요한 공백을 구분한 뒤 각각 판단한다.

| ID | 발견 | xsm에 주는 의미 | 검증해야 할 조건 |
|---|---|---|---|
| D01 | 메시지별 책임 소유 계산 | ADR-0018의 수신 증거와 별개인 "처리 책임" 축을 `task` 중심으로 검토 | 맡음 표시가 성공으로 오해되지 않는가. 일반 note·reply까지 추가 확인 왕복을 요구하지 않는가 |
| D02 | 사유 있는 1회 돌려주기 | 범위 밖 `task`를 outcome `failed`와 구별해 돌려주는 표현 | 돌려주기가 거절 남용이나 왕복 고리가 되지 않는가. dsh는 재연결 거부로 막는다 |
| D03 | 복수 소유, 모두 손을 떼면 복귀 | 팀 DM `task`에서 "아무도 맡지 않음"을 발신자가 보게 하기 | 담당 충돌을 막는 게 아니라 무담당을 드러내는 수준으로 충분한가 |
| D04 | 끝날 때 미처리 메시지 복귀 | 세션 종료 시 답하지 않은 질문을 발신자에게 표시 | `pending`을 "상대 종료, 미응답"과 구별할 수 있는가. Codex 종료·충돌·재개를 정직하게 다루는가 |
| D05 | 세션 기록 진입 기준 읽음 | ADR-0018의 런타임 인계와 회신 사이 증거 단계 후보 | 트랜스크립트 스키마 변화와 지연을 감당하는가. `xsm/directory.py:30-37`이 이미 이 위험을 적고 있다 |
| D06 | 진입 뒤 보고·턴 종료까지 요구 | 턴 경계 근거로 읽음을 판단 | 최종 outcome을 쓰는 중 도착한 메시지가 유실 없이 드러나는가 |
| D07 | 구조화된 사람 대기 슬롯 | 기존 결정·승인·위임 요청 기록을 이용해 누구의 어떤 판단을 기다리는지 공개할지 검토 | 네이티브 질문의 대기를 관측할 수 있는가. 표시되지 않음·응답 대기·명시 거부를 구분하는가 |
| D08 | 질문 교체 시 이전 질문 철회 | 낡은 승인 요청을 대체할 때 대기 표시 철회. ADR-0020과 연결 | 이미 답을 받은 이전 질문을 잃지 않는가 |
| D09 | 질문을 일으킨 곳에서 묻기 | 생성자·팀장·현재 요청자·원 의뢰인의 역할과 회신 경로를 명시하고 승인 창구에 원 요청 맥락을 전달 | 수평 워커와 팀장 조율 팀에서도 결과 회신과 사용자 승인 경로가 섞이지 않는가 |
| D10 | Mandate 재검증과 변경 통지 | 연결 해제·팀 탈퇴 때 진행 중 위임 작업에 알리기 | `xsm/collaboration.py`의 철회가 진행 중 작업을 어떻게 다루는지 미확인 |
| D11 | 문맥 구독은 권한을 주지 않음 | 보드 알림과 첨부가 권한이 아님을 같은 문장으로 고정 | 기존 ADR-0022 표현과 중복인지 |
| D12 | 긴 대기 금지 가드 | 팀장 세션의 긴 `--wait`가 사람 입력을 늦추는지 확인 | 훅으로 강제 가능한지 또는 스킬 안내로 충분한지 |
| D13 | 사람 입력용 여분 슬롯 | owned worker 용량이 찼을 때도 사람의 지시가 들어가는가 | `reserve`와 용량 규칙에서 재현 |
| D14 | 복구 노트 문구 | 인계·재시작 뒤 외부 행동 반복 전 상태 확인을 안내 | handover 편지와 워커 재시작 안내에 이미 있는지 |
| D15 | 리뷰어별 라운드 상한과 기록 | 검토자 왕복 상한을 세션 수명을 넘어 세는 단위 | ADR-0022가 경계하는 정상 왕복 차단이 되지 않는가 |
| D16 | 메시지 문구 규칙 | 기존 조직·소통 스킬에 변하지 않은 상태의 반복 통지를 줄이는 지침을 대조 | 사용자가 요청한 진행 보고를 침묵 규칙으로 막지 않는가. 스킬 분량 증가 대비 소음 감소가 있는가 |
| D17 | 기각 개념 표 | 도메인 문서 끝에 "넣지 않은 개념"을 유지 | ADR의 선택지 표와 중복되지 않는가 |
| D18 | 모델 표면 검사와 문자 예산 | 기존 `SkillLayoutTest`와 프로토콜 연산 스키마 생성·대조 검사를 바탕으로 남은 드리프트를 검토 | 기존 검사의 범위와 중복되지 않는가. 문자열·링크 일치를 실제 모델의 역할 수행 검증과 구분하는가 |
| D19 | 관찰 모드 우선 | 새 자동 동작은 기록만 하는 단계부터 | `abuse.py`의 기본과 같은 원칙이며 확대 적용 범위를 정해야 한다 |

### 우선순위에 대한 의견

두 노트를 함께 검토한 우선순위는 **막힘·중단·실패의 구분(AgentTeams A01) → 요청의 담당·미응답 가시성(D01·D04) → 기존 기록을 활용한 사람 대기 표시(D07·D08, A12)**다. A01은 무응답 워커 정지가 실패로 기록되고 `failed`가 시도 상한에 포함되는 현재 경로를 근거로 삼는다. 권한 대기나 사용자 중단이 실제 재시도 흐름에서 상한에 걸리는지는 재현하지 않았다.

D01·D04는 일반 세션의 수신 확인과 담당·완료를 구분하는 문제다. owned worker에는 이미 실행·결과·전송 기록이 있으므로 함께 "미구현"으로 묶지 않는다. D05·D06과 AgentTeams A05는 하네스별 관측·턴 제어 비용을 별도로 확인할 항목이다. 전체 후보의 우선순위는 조사 의견이며 사용자가 승인한 구현 범위를 뜻하지 않는다.

### 아직 모르는 것

- **되돌릴 곳.** dsh에는 Eval이 있다. xsm에는 필수 중앙 재평가자가 없다. 선택한 조직의 요청자·팀장이 반환을 받을 수 있지만 그 세션도 끝났을 수 있다. 보존·표시와 자동 재배정을 구분해 정해야 한다.
- **"끝났다"의 의미.** Ticket의 끝은 호스트가 선언한다. 사용자 세션은 나중에 다시 열린다. 답 없이 사라진 것과 잠시 닫힌 것을 구분하지 못하면, 끝남을 표시하는 값이 거짓이 된다.
- **맡음의 비용.** 에이전트에게 맡음 표시를 요구하면 프로토콜 부담이 는다. xsm 철학("Who does what is decided in conversation")과의 균형이 필요하다. 자연어 회신을 맡음으로 볼 수 있는지 불명이다.
- **읽음 관측 가능성.** dsh는 자기 하네스 이벤트를 받는다. xsm은 훅과 네이티브 기록을 읽는 처지다. directory가 트랜스크립트와 rollout을 읽지만, 메시지 진입 판정을 안정적으로 할 수 있는지는 시험하지 않았다.

## 15. 따르지 않을 것

아래는 XSM의 핵심 통신 계약에 일률적으로 넣지 않을 장치다. 사용자가 선택한 팀장 조직의 배분·검토·결과 수락 절차는 스킬과 자연어 지시로 구성할 수 있으며, 이 표가 그 활용을 금지하지 않는다.

| 항목 | 이유 |
|---|---|
| 모든 통신에 상주 호스트·중앙 main Session을 필수화 | 기본 전달 경로와 특정 조직의 조율 역할을 결합하게 된다. 사용자가 선택한 팀장이 요청을 배분하는 운영은 별도로 가능하다 |
| 런타임이 세션 도구를 제거하는 방식 | 사용자가 연 세션에는 적용할 수 없다 |
| Eval, accept 모드, admission 표 | 조직이 공용 봇을 운영하는 맥락의 장치다. 개인 세션 N:N에는 범위 모델이 이미 있다 |
| 중앙 SQLite 하나에 모든 상태 | ADR-0018(Proposed)이 저장소 교체를 별도 근거가 필요한 일로 둔다 |
| 사람 계정 연결 거부를 그대로 수용 | xsm은 한 사용자의 여러 세션을 다룬다. 전제가 다르다 |
| 웹 패널 | xsm은 하네스 안에서 쓰인다. 패널의 "먼저 사람 대기 표시" 원칙만 `xsm doctor`류 출력에 참고할 수 있다 |
| `danger-full-access` 기본 | 저장소 스스로 경계가 아니라고 밝힌다. 권한 모델의 모범으로 삼지 않는다 |
| 자동 PR 닫기, 공동 저자 기록 절차의 통신 기본값화 | GitHub 납품 업무에서 선택할 운영 규칙이다. 통신 계층 전체에 강제하지 않는다 |

## 16. 조사 한계와 미검증

- 2026-11-04 보정은 `c61799f`의 관련 XSM 코드와 조직·스킬 문서를 대조한 자체 검토다. 상대 제품 원본의 전수 재검증, 런타임 실행, 실패 상한 충돌 재현, 모델 행동 평가는 하지 않았다. 아래 독립 사실 검증 기록은 최초 조사에 대한 것이며 이번 보정의 독립 검증을 뜻하지 않는다.
- 정적 조사다. `pnpm check`를 돌리지 않았으므로 테스트 통과 여부는 알 수 없다. 받은 코드를 실행하지 않았다.
- 실제 DSH 환경, GitHub, Feishu, 모델 호출을 쓰지 않았다.
- `src/client`, Feishu Source 세부, `src/app/migration.ts`, `docs/006-deployment.md`의 절차 대부분, `docs/008-cookbook.md`의 뒷부분은 자세히 읽지 않았다.
- 원문 글 *Exploring Super-agent Design*은 웹 검색 2회, arXiv 제목 검색 1회, GitHub 코드 검색 1회로 찾지 못했다. 코드 검색의 유일한 결과는 이 저장소 README였다. 글에만 있는 설계는 반영하지 못했다.
- `src/app/sessions.ts:61-62`의 `WORK_TOOLS`에 `send_message`, `list_agents`, `interrupt_agent`가 있다. 주석은 다른 Session에 메시지를 보내는 도구를 주지 않는다고 말한다. `cordis.patch.yml:102`의 `tool-subagent-control`이 제공하는 서브에이전트 제어 도구로 보이지만 DSH 소스를 확인하지 않았다.
- xsm 쪽 "찾지 못했다"는 표현은 지정한 파일의 grep 범위 안의 결과이며 부재의 증명이 아니다. 일반 세션의 처리 책임 상태, directory의 사람 대기 값, 사람 입력 우선 슬롯이 여기에 해당한다.
- 작성 뒤 독립 사실 검증을 한 번 거쳐 지적 사항을 반영했다. 검증도 정적 대조이며, 인용과 수치, 5절 의미론, 13절과 15절의 사실 근거가 범위였다. 별 수(9,979개)는 시점 값이라 대조하지 못했다. 검증 뒤 저장소 별 수는 달라졌다.

## 출처

[1] README: https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/README.md

[2] DeepSeek Harness 공식 페이지: https://www.deepseek.com/en/harness/

[3] 철학 문서: https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/000-philosophy.md

[4] Cordis 논문 초록, *A Programming Paradigm for Spatiotemporal Composability*: https://arxiv.org/abs/2608.25512
