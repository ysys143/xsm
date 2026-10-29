# P02 경계 명세 초안 — 연결 의도에서 원 요청 전달까지

- 기준 커밋: 4fd7c9f (2026-10-25). 작업 트리 변경 없음.
- 범위: 읽기 전용 조사. 제품 코드·테스트·설정을 수정하지 않았고 테스트를 실행하지 않았다.
- 표기: 코드 근거는 `파일:줄`. 추측은 **추측**으로 표시했다.
- 이 문서는 ADR-0015/P02의 게이트(G02, D01·D04) 이전 준비 자료다. 정책 채택이나 구현 완료가 아니다.

## 1. 실제 호출 경로 (함수 단위)

다른 저장소 동료로의 `xsm send` 한 번이 지나는 순서다. 모든 줄 번호는 이 저장소의 4fd7c9f 기준이다.

### 1.1 진입

| 단계 | 함수 | 위치 |
|---|---|---|
| CLI | `cmd_send` → `send.send(...)` | xsm/cli.py:664, xsm/cli.py:684 |
| MCP | `xsm_send` 핸들러 → `send_mod.send(...)` | xsm/mcp.py:398, xsm/mcp.py:401 |
| 공통 | `send`(span 래퍼) → `_send` | xsm/send.py:64, xsm/send.py:114 |

### 1.2 범위 판정과 거부

| 순서 | 함수 | 위치 | 하는 일 |
|---|---|---|---|
| 1 | `resolve.resolve` | xsm/send.py:164 | 대상 해석. 모호하면 후보와 함께 실패 |
| 2 | `config.scope_for` | xsm/send.py:184, xsm/config.py:199 | 범위 판정. 기본 repo/dir → link → worker → reach 순 |
| 3 | `config._scope_for` | xsm/config.py:350 | 같은 repo/worktree, 같은 dir, 명시 프로젝트 |
| 4 | `config._folder_link` | xsm/config.py:218 | `xsm link`로 연결된 두 프로젝트 폴더 |
| 5 | `config._worker_link` | xsm/config.py:297 | worker와 그 부모 |
| 6 | `config._reach_link` + `reach_holds` | xsm/config.py:249, xsm/config.py:267 | 세션 하나에 허용된 reach |
| 7 | 거부 문자열 조립 | xsm/config.py:238(`_link_hint`), 289(`_reach_hint`), 326(`_half_joined`) | 무엇을 물어야 하는지 문장으로 |

### 1.3 한 번의 "예"로 연결하고 보내는 경로

범위가 없고 `--resend`가 아니면 `connect.offer`가 호출된다 (xsm/send.py:185-187).

| 순서 | 함수 | 위치 | 하는 일 |
|---|---|---|---|
| 1 | `workers.human_terminal` | xsm/connect.py:123, xsm/workers.py:998 | 사람이 직접 친 것인지 판정 |
| 2 | `plan_for` | xsm/connect.py:126, 정의 xsm/connect.py:45 | 연결 계획 `{verb, target, here, cwd, what}` 계산 |
| 3 | `_typed` | xsm/connect.py:130, 정의 xsm/connect.py:98 | 사람이 직접 친 경우 그 자체를 승인으로 사용 |
| 4 | `consent.take_or_request` | xsm/connect.py:131, 정의 xsm/consent.py:756 | 이 세션의 요청 파일에서 답을 꺼내거나 없으면 ask를 기록 |
| 5 | `consent._take` | xsm/consent.py:522 | 아직 안 보여준 답 → (reply, False)로 보여주기만, 이미 보여준 답 → (reply, True) |
| 6 | `consent._record` | xsm/consent.py:550 | 없으면 ask를 남긴다(`verdict: None`) |
| 7 | `consent._from_request` | xsm/consent.py:724 | 답이 없을 때 사람의 직전 요청을 답으로 승격(정책 `reply_from_request`) |
| 8 | `outbox.put` | xsm/connect.py:134, 정의 xsm/outbox.py:55 | 거부된 메시지를 id와 함께 보관 |
| 9 | `consent.approved` | xsm/connect.py:139, 정의 xsm/consent.py:979 | decisions.jsonl에 기록하고 문장 반환 |
| 10 | `connect.run` | xsm/connect.py:141, 정의 xsm/connect.py:78 | 계획 적용 |
| 11 | `config.add_link` / `config.join` / `config.add_reach` | xsm/connect.py:83, 89, 92 (정의 xsm/config.py:495, 429, 562) | 실제 연결 기록 |
| 12 | 재판정 | xsm/send.py:196 | `scope_for`를 다시 호출해 "연결됨"을 확인 |
| 13 | 발신 | xsm/send.py:216-220 | `msg_id = step.id`로 **같은 id**를 쓰고 `ledger.queued` |

승인 게이트 순서의 요지: **묻기 → (다음 실행에서) 보여주기 → (그다음 실행에서) 적용**. 한 실행에서 바로 적용되지 않는다. `SHOW_DELAY = 1.0` (xsm/consent.py:130) 안의 재실행은 다시 보여주기만 한다 (xsm/consent.py:522-548).

### 1.4 사람 답이 들어오는 지점

| 런타임 | 이벤트 | 처리 | 위치 |
|---|---|---|---|
| Claude | `PostToolUse` (matcher `AskUserQuestion`) | `answers_text` → `note_verdict` | xsm/receive.py:277-283, xsm/consent.py:364-375, xsm/consent.py:329 |
| Claude | `UserPromptExpansion` | typed `/xsm link …` 를 승인으로 | xsm/receive.py:270-275, xsm/consent.py:376-380 |
| Codex/Claude | `UserPromptSubmit` | 일반 프롬프트 → `note_verdict` + `remember` | xsm/receive.py:295-301, xsm/consent.py:381-388 |
| Claude worker | `PermissionRequest` | worker 승인 대기 | xsm/receive.py:257, xsm/workers.py:898 |

설치되는 이벤트 집합: Claude는 `SessionStart, UserPromptSubmit, UserPromptExpansion, PostToolUse, SessionEnd` (xsm/install.py:41), Codex는 `SessionStart, UserPromptSubmit`(+조건부 `PermissionRequest`) (xsm/install.py:48, xsm/install.py:1147). **Codex에는 `PostToolUse`가 설치되지 않는다.**

## 2. 비동기 승인 답이 파싱되지 않는 지점

### 2.1 관측된 사실

- 2026-10-23 비교에서 사용자 답 `비교용 연결 허용, 종료 후 해제`는 이 대화에 실제로 도착했다. 그런데 xsm은 그 원문을 보관하지 못했다: `deliverables/xsm-reason-live-comparison-2026-10-23/evidence.json`의 `approval_ingestion`은 `answer_was_received_in_this_conversation: true`, `approval_text_in_recent_prompts: false`, `matching_pending_records[0].verdict: null`, `link_cleanup_result: "folders were not linked"`다.
- 같은 파일 `case_limits.S5_after_link`는 `actual asynchronous user approval was not captured by xsm; documented --reply fallback was rejected`로 남긴다.
- 그 답이 Codex 대화 기록에 실려 온 형식(외부 상태, 이 저장소 밖):
  `~/.codex-3/sessions/2026/10/23/rollout-2026-10-23T12-12-07-01a166ab-…jsonl` 1952행, `role: user`, 본문이 `<send_user_message_question_reply>\n[{"answer":…,"question":…,"questionItemId":["request_user_input_async","call_…",0]}]\n</send_user_message_question_reply>`.
- 즉 이 채널은 **답 원문 + 질문 + 도구 호출 id**를 함께 준다. 자유문장만 오는 채널이 아니다.

### 2.2 코드에서 어디로 들어와야 하는가

Codex 경로는 `UserPromptSubmit` 하나뿐이므로, 이 답은 `receive._handle` → `_record_consent` → `consent.record`의 `UserPromptSubmit` 분기로 들어와야 한다 (xsm/receive.py:295-301, xsm/receive.py:342-347, xsm/consent.py:381-388). 그 지점에서 `note_verdict`가 호출되어야 ask 파일의 `verdict`가 채워진다.

### 2.3 현재 상태: 파서 없음 + 필터에 의해 차단

1. **전용 파서가 없다.** 저장소 전체에서 `send_user_message` 문자열은 계획 문서 한 곳에만 나온다(`docs/plan/reason-inspired-adrs/spec.md:195`). 코드·훅·테스트 어디에도 없다(전수 grep). `questionItemId`·`request_user_input` 문자열도 제품 코드에 없다.
2. **일반 경로에서도 걸러진다.** `consent.record`의 `UserPromptSubmit` 분기는 `not_a_reply(text)`가 True면 `note_verdict`/`remember`를 건너뛴다 (xsm/consent.py:386-388). 그리고 `not_a_reply`는 `TAG_RE`로 여는 태그를 잡고 같은 이름의 닫는 태그가 있으면 True를 돌려준다 (xsm/consent.py:305-314, xsm/consent.py:177).
   읽기 전용 확인: `<send_user_message_question_reply>…</send_user_message_question_reply>`에 대해 `not_a_reply`는 True, `envelope.looks_like_peer`는 False.
3. 그 필터의 목적은 정당하다 — 하네스가 주입하는 텍스트를 사람의 답으로 세지 않기 위함이다 (xsm/consent.py:166-176). 문제는 **이 태그가 하네스 주입 텍스트이면서 동시에 사람이 실제로 고른 답을 나르는 유일한 채널**이라는 점이다. 두 의미가 같은 문자열로 겹친다.
4. Claude 쪽 대응물인 `AskUserQuestion` 경로(`answers_text`, `tool_response`의 `answers`)는 Codex에 이식되어 있지 않다. 설치 이벤트 자체가 없다(xsm/install.py:48).

**추측:** 2.3의 2번(필터)만 고치면 되는지, 애초에 Codex가 이 메시지에 `UserPromptSubmit` 훅을 발화하지 않는지는 미확인이다. 관측 시각(답 도착 `t≈1792754377`) 전후로 `~/.xsm/decisions.jsonl`에 해당 세션의 `UserPromptSubmit` 행이 없다. 다만 이 파일은 성공 경로에서 아무 행도 쓰지 않으므로(xsm/receive.py:342-351), 행이 없는 것만으로 "훅이 안 왔다"를 확정할 수 없다. P00의 3번 항목이 이 관측을 요구한다(`docs/plan/reason-inspired-adrs/spec.md:195`).

### 2.4 요청 ID 결속의 공백

원문에 `questionItemId`(= 도구 호출 id)가 실려 오지만, 현재 어느 저장 구조에도 그 값을 담을 자리가 없다.

- ask 파일이 남기는 필드: `verb, target, here, cwd, t, session_id, verdict` (xsm/consent.py:557-560), 답이 오면 `verdict, verdict_t, shown` 추가 (xsm/consent.py:432-434). `via`는 `--reply`일 때만 `flag` (xsm/consent.py:569-571, xsm/consent.py:645).
- ask의 키는 `digest(verb, want)`다 (xsm/consent.py:470, xsm/consent.py:788). 보관 메시지의 키는 `digest(spec, kind, reply_to, outcome, body)`다 (xsm/outbox.py:60). **두 키는 서로를 참조하지 않는다.**
- 그래서 "이 승인이 어느 보관 메시지의 것인가"는 디스크에 없다. 다음 실행에서 `plan_for`를 다시 계산하고 `outbox.put`이 같은 digest를 찾아냄으로써만 복원된다 (xsm/connect.py:126, xsm/outbox.py:62-64). 본문이나 kind가 한 글자라도 달라지면 새 보관 메시지와 새 id가 생긴다.
- P02가 요구하는 "완전한 핸들·generation·원 요청 ID·plan digest 결속"(`docs/plan/reason-inspired-adrs/spec.md:222`)에 대응하는 필드는 현재 코드에 없다. `generation`, `plan_digest`, `intent_id` 전수 grep 결과 제품 코드 0건.

## 3. "프로젝트 이름·ID를 사용자에게 요구하지 않는다" 요구와 구현의 간극

요구: P02 2번 — "프로젝트 이름이나 ID 입력을 사용자에게 요구하지 않는다" (`docs/plan/reason-inspired-adrs/spec.md:224`). ADR-0015도 "사용자에게 내부 프로젝트 이름·ref 문법을 외우게 하지 않는다"고 적는다 (`docs/adr/0015-connection-intent-and-participation.md`).

### 3.1 요구를 만족하는 부분

- `plan_for`는 프로젝트 이름을 **사람에게 묻지 않는다.** 대상의 `joined_projects`에서 보낸이 미가입 프로젝트를 계산해 하나면 join 계획으로 제안한다 (xsm/connect.py:68-72, xsm/config.py:319).
- 사람이 하는 일은 예/아니오 한 번이다. xsm은 답의 단어를 읽지 않고 에이전트가 읽는다(`take_or_request` 독스트링, xsm/consent.py:757-762).
- 프로젝트 이름이 필요한 명령(`xsm join <name>`)은 사람이 아니라 **에이전트**에게 안내된다 (xsm/cli.py:369, xsm/cli.py:410, xsm/config.py:326-334).

### 3.2 실질 간극

1. **의도 → 계획을 옮기는 코드 경로가 없다.** `plan_for`의 입력은 해석이 끝난 `sender`/`target` 레코드이고 `ref`·`cwd`를 요구한다 (xsm/connect.py:55-57). 사람의 자연어 의도를 계획으로 번역하는 함수는 없다. `connect.offer`도 `send`가 이미 범위 거부로 실패한 뒤에만 호출된다 (xsm/send.py:184-187). 즉 "다른 저장소의 이 동료와 협업하고 싶다"는 요청 자체가 진입점이 아니고, **거부가 먼저 나야** 계획이 생긴다.
2. **사람에게 보이는 질문 문안이 없다.** `plan["what"]`은 에이전트에게 주는 영어 기술 문장이다 (xsm/connect.py:65-75). 사람에게 무엇을 어떻게 물을지는 `consent.asks`가 에이전트에게 지시하는 문장뿐이다 (xsm/consent.py:942-956). 사람에게 프로젝트 이름을 요구하지 않는 것과, 사람이 이해할 수 있는 질문을 코드가 만드는 것은 다르다.
3. **join 계획일 때 범위 차이가 질문에 결속되지 않는다.** 승인 키는 `(verb, target)`뿐이라(xsm/consent.py:788), "프로젝트 X에 가입해서 열린다"는 사실이 사람의 답과 구조적으로 묶이지 않는다. ADR-0015의 "요청 원문과 열릴 범위를 한 질문에 결속"과 거리가 있다.
4. **모호한 대상의 후보 제시는 코드에 있다**(xsm/resolve.py:72, 136). 다만 그것은 세션 후보이지 프로젝트 후보가 아니다.

## 4. 나중에 사람이 결정할 정책 지점 (D01·D04)

### 4.1 D01 — 실제 답 채널의 신뢰 근거, 자유문장 해석·적용, 늦은 판단 재사용

| 지점 | 코드 근거 | 열린 문제 |
|---|---|---|
| 채널 신뢰 근거 | Claude: `PostToolUse`+`AskUserQuestion`만 사람의 선택으로 인정 (xsm/consent.py:369-375). Codex: `UserPromptSubmit`의 비태그 텍스트 전부 (xsm/consent.py:381-388) | 두 채널의 결속 강도가 다르다. Codex 비동기 답은 태그로 걸러져 아예 들어오지 않는다(2.3). 어떤 태그를 "사람의 답"으로 인정할지 정해야 한다 |
| 출처 보존 | ask 파일에 `via`는 `flag`일 때만 기록 (xsm/consent.py:645, xsm/consent.py:987-988) | 답이 어느 채널로 왔는지, 어느 질문 id였는지가 저장되지 않는다 |
| 자유문장 해석 | xsm은 읽지 않고 에이전트가 읽는다 (xsm/consent.py:757-762). 예외로 `_from_request`가 `INTENT_RE`+`_mentions`로 자동 승격 (xsm/consent.py:724-753, xsm/consent.py:155-159) | 모델 해석과 휴리스틱 자동 승격이 같은 `verdict` 슬롯을 쓴다. 둘을 구분해 기록할지 |
| 늦은 판단 재사용 | ask는 `ASK_MAX=1800`초, 답은 `TTL=600`초 (xsm/consent.py:121, xsm/consent.py:117, xsm/consent.py:267-276) | 30분을 넘긴 답은 버려진다. 늦은 유효 답을 어디까지 재사용할지 |
| 같은 말 재사용 방지 | `_spend`가 쓴 단어를 표시 (xsm/consent.py:485-508). `SHOW_DELAY=1.0` (xsm/consent.py:130) | 명령 반복만으로 새 승인이 생기지 않게 하는 장치가 이미 있다. 이 값을 유지할지 |
| 수집 단절 시 상태 | `take_or_request`가 `(None, False, False)` 반환 (xsm/consent.py:785-786, xsm/consent.py:802-803), `cannot_keep` 문안 (xsm/consent.py:1021-1033) | "unknown"을 지금은 호출자가 문장으로만 표현한다. 상태로 남길지 |

### 4.2 D04 — 기본 협업 집합·연결 단위·수명·재개 후 허용 재사용

| 연결 단위 | 수명 | 코드 근거 |
|---|---|---|
| link | 폴더 두 개, 양방향, `unlink`까지 무기한 | xsm/config.py:495, xsm/config.py:218, xsm/config.py:526 |
| join | 명명 프로젝트 멤버십, 무기한 | xsm/config.py:429, xsm/config.py:319 |
| reach | 세션 **한 번의 실행** 동안만 | xsm/config.py:267-288(`reach_holds`), xsm/config.py:562 |
| worker | ref 쌍, 부모-자식 | xsm/config.py:297-318 |
| 사람이 친 send | 그 자리에서 연결을 만든다 | xsm/policy.py:34, xsm/connect.py:104, xsm/connect.py:124 |

정책 결정이 필요한 대목:

- **재개 후 재사용.** reach는 `session_id`+`pid`+`lstart`가 모두 같아야 유효하다(xsm/config.py:274-288). 반면 worker 링크는 ref만 보므로 재개된 같은 세션 id에도 남는다 — 이 모순은 코드 주석이 스스로 "미결"이라고 적어 두었다(xsm/config.py:303-308). D04가 정해야 할 항목이다.
- **세션 종료 시 회수.** reach는 `SessionEnd`에서 즉시 삭제된다(xsm/receive.py:262-266). link/join에는 대응하는 자동 회수가 없다.
- **한 요청의 승인이 만드는 범위.** `plan_for`가 고르는 것은 셋 중 하나이고(xsm/connect.py:64-75), 적용은 그 하나만 바꾼다(xsm/connect.py:82-95). 일회성 승인을 폴더 전체 지속 연결로 확대하지 않는다는 ADR-0015의 약속과 코드는 일치한다. 다만 `link`는 무기한이므로 "일회성 권한이 기본"이라는 결정은 아직 내려지지 않았다.
- **typed send의 지위.** `human_send_connects`(기본 true)는 사람이 직접 친 send를 연결 승인으로 본다(xsm/policy.py:34, xsm/connect.py:98-114). 사람 판정 근거는 `human_terminal`이며 코드가 스스로 "보안 경계가 아니다"라고 밝힌다(xsm/workers.py:998-1007).

## 5. 미확인으로 남기는 것

1. Codex가 `<send_user_message_question_reply>` 메시지에 `UserPromptSubmit` 훅을 발화하는지. 발화 여부와 필터 차단 여부를 구분하지 못했다(2.3). 격리 fixture로 재현해야 한다.
2. 이 채널 외에 Codex의 다른 비동기 답 형식이 있는지. `request_user_input` 계열 전수 확인은 하지 않았다.
3. 설치본과 체크아웃의 일치 여부. 2026-10-23 산출물의 `plugin_source_checks`는 `send.py, receive.py, config.py, mcp.py, adapters.py` 다섯 개만 대조했고 **`consent.py`와 `outbox.py`는 검사 대상이 아니다**(해당 evidence.json). 이번 조사의 줄 번호가 실행 중인 설치본에도 그대로 적용된다고 단정하지 않는다.
4. Claude의 `AskUserQuestion` 경로가 실제 세션에서 끝까지 도는지. 테스트는 있다(`tests/test_person_decisions.py:660`). 이번 턴에 실행하지 않았다.
5. `plan_for`가 고른 연결이 실제 왕복까지 이어지는지. 2026-10-23 비교는 "연결 성립 후" 구간을 미검증으로 남겼다(`deliverables/xsm-reason-live-comparison-2026-10-23.md:87`).
6. `_from_request`의 자동 승격이 실제 사람 발화에서 오탐을 내는 빈도. 휴리스틱 경로(`INTENT_RE`, `_mentions`)의 실측 표본을 확인하지 않았다.
