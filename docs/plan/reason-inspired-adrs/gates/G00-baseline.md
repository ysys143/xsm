# G00 기준선 — 실행 기록

- 상태: **passed** (기술 게이트 + P00 수행 항목). 마지막 개정 2026-10-28, Opus 5.5 독립 검토 3회와 그에 따른 보완 반영.
- revision: 저장소 커밋 `4fd7c9f550dd5bafa8e754701ab1f0802c74b064` (branch main), 제품 버전 0.4.20.
- 판정: 코디네이터 직접 실행 + 아래 증거 + **독립 검토(Opus 5.5) 3회**. 1차 지적(Python 버전, manifest 누락, crash fixture 미수행), 2차 지적(lookup 예산, 내부 모순, kill 조건 범위, manifest 잔여), 3차 지적(문서 모순 5건, fake codex 중복)을 모두 보완했다(7.1–7.5절).
- 계획 상태 `draft-implementation-not-started`(plan.json:5) → P00 `passed`. 제품 기능 변경 없음(테스트·문서만).
- 진입 게이트 없는 B00 단독 배치로 실행했다. 다음 배치 B01(P01·P11)의 진입 조건이 열렸다.
- **사용자 확인 항목:** G00.4 "경계별 crash 제어"의 **경계가 2개로 충분한지**는 문서가 아니라 계획·사용자가 정할 일이다(spec.md:201은 경계 목록을 정하지 않는다). 3차 검토가 이 범위 판단을 사용자 확인으로 남기기를 권고했다.

## 1. 종료 조건별 증거

| 조건 | 결과 | 증거 |
|---|---|---|
| 전체 기존 회귀 결과 | 통과(두 인터프리터). **fixture 포함 1040개 전부 OK** | fixture 이전: 3.9.6 `Ran 1034 / OK`(`clean-regression.log`), 3.14.6 `Ran 1034 / OK`(`clean-314-regression.log`). **fixture 포함 최종(둘 다 1040/OK):** 3.14.6 `Ran 1040 tests in 138.939s`(`f314.log`), 3.9.6 `Ran 1040 tests in 193.064s`(`f39.log`) — 모두 `/tmp/xsm-baseline-bkZPcz/` |
| 기준 버전/홈/하네스 manifest | 확보(보강) | 커밋·버전·Python·등록 홈·훅·MCP·설치 출처. 이 문서 2절. |
| S5 비동기 입력 채널 관측 | 관측·원인 확정 | 3절. 실제 Codex 트랜스크립트에서 답 이벤트 형식과 드롭 지점을 확인 |
| crash 제어 시험체 확보 | 확보(2경계) | `tests/test_crash_boundaries.py` 신규. 승인 적용↔전송, inbox claim↔ack에서 실제 프로세스를 SIGKILL하고 다음 실행을 관찰. 4절 |

## 2. manifest

```
commit     4fd7c9f550dd5bafa8e754701ab1f0802c74b064
branch     main
version    0.4.20 (.claude-plugin/plugin.json, .codex-plugin/plugin.json)
          xsm/__init__.py __version__ = "0.1.0" (오래된 값, 제품 버전과 다름)
python     3.14.6 (/opt/homebrew/opt/python@3.14/bin/python3.14, 세션 셸 기본)
          3.9.6 (/usr/bin/python3, env -i 에서 잡히는 인터프리터)
harness CLI codex-cli 0.164.0 (`codex --version`)
            Claude Code 2.1.312 (`claude --version`)
home       /Users/jaesolshin/.xsm (XSM_HOME 기본)
harness    8 등록 홈: claude, claude-2, claude-3, claude-shared, claude-plugin-check
           codex, codex-2, codex-3
           (claude-plugin-check 는 doctor 에서 `gone`/삭제로 표시됨)
claude hooks (hooks/hooks.json, 6개):
            SessionStart, UserPromptSubmit, UserPromptExpansion, SessionEnd,
            PermissionRequest, PostToolUse(matcher=AskUserQuestion)
            단 PermissionRequest 는 `install.py`가 approvals 옵트인일 때만 설치하므로
            직접 설치 홈에는 없다(install.py:1147 `events = […] + (['PermissionRequest'] if approvals …)`)
codex hooks (hooks/codex-hooks.json, 2개): SessionStart, UserPromptSubmit
mcp         .mcp.json → xsm: ${CLAUDE_PLUGIN_ROOT}/hooks/xsm-mcp
            hooks/codex-mcp.json → xsm: ./hooks/xsm-mcp (cwd=".")
install 출처 codex-3: hooks trusted (~/.codex-3/hooks.json SessionStart·UserPromptSubmit add)
            claude-3: ~/.claude-3/settings.json 훅 keep (직접 설치, 플러그인 아님)
            doctor 기준 Claude 직접 설치 홈 4개(.claude, .claude-2, .claude-3, .claude-shared)
sandbox    Codex 세 홈 모두 완전 개방: `sandbox_mode="danger-full-access"`,
            `approval_policy="never"` (config.toml). **이 값이 S5 비동기 승인과 직접 관계된다:**
            승인 폼이 표시되지 않고 거부될 수 있는 조건이다.
            이 세션 등록 레코드도 `permission_mode=bypassPermissions`.
```

## 3. S5 비동기 승인 입력 채널 — 관측 결과

### 3.1 실제 이벤트 형식

하네스가 승인 답을 넣는 형식은 자유문장이 아니라 **태그+JSON**이다. 이 세션의 Codex rollout에서 확인했다.

```
<send_user_message_question_reply>
[{"answer":"…","question":"…","questionItemId":"[\"request_user_input_async\",\"call_…\",0]"}]
</send_user_message_question_reply>
```

이 텍스트는 `response_item`(`payload.type=message`, `role=user`)와 `event_msg`(`type=item_completed`, `item.type=UserMessage`) 두 항목으로 트랜스크립트에 남는다. **관측된 결론: 이 채널은 요청 ID(`questionItemId`)가 실려 오는 쪽이다**(spec.md:225가 요청 ID 있는 채널과 자유문장만 오는 채널을 둘 다 상정하므로 "가정 반증"이 아니라 "요청 ID 있는 채널로 관측"으로 적는다. 3차 검토 반영).

확인한 파일: `~/.codex-3/sessions/2026/10/23/rollout-2026-10-23T12-12-07-01a166ab-…_01a166be-…jsonl`의 파일 행 449·450(ordinal 448·449). **10-28 rollout에는 이 user 이벤트가 없다**(태그는 도구 출력과 추론 안에만 나온다) — 1차 문서의 "이 세션" 표기는 틀렸고 2차 검토에서 정정했다.

### 3.2 드롭 지점 (재현)

`xsm/consent.py`의 `not_a_reply()`가 이 문자열을 답이 아니라고 판정한다.

- `TAG_RE = \A<([a-z][a-z0-9]*[_-][a-z0-9_-]*)[\s>]` (consent.py:177) → `<send_user_message_question_reply>` 매치
- `not_a_reply()` (consent.py:305-315): 여는 태그와 같은 이름의 닫는 태그가 있으면 True → `record()` (consent.py:386)가 `note_verdict`/`remember`를 호출하지 않음

재현(격리 XSM_HOME, 제품 코드 무수정):

```
$ printf '%s' '{"hook_event_name":"UserPromptSubmit","session_id":"obs-session-1","prompt":"<send_user_message_question_reply>[{\"answer\":\"yes allow\",…}]</send_user_message_question_reply>"}' | python3 hooks/xsm-hook.py
(exit 0, stdout 없음, asked/ 미생성)
대조: prompt="응, 그 연결 허용해" → asked/<ref>.recent.json 에 기록됨
```

`envelope.looks_like_peer()`는 같은 문자열에 False다. 즉 **하네스 주입 텍스트를 거르는 안전장치와, 사람이 실제로 고른 답을 나르는 통로가 같은 문자열로 겹쳐 있다.**

### 3.3 결속 공백

- ask 파일(`ask`)의 키는 `digest(verb, want)`이고, 보관 메시지 키는 `digest(spec, kind, reply_to, outcome, body)`다. 서로를 참조하지 않는다.
- ask 파일에 `questionItemId`를 담을 필드가 없다. 승인과 원 요청의 결속은 다음 실행의 재계산에만 의존한다.
- 활성 세션 `~/.xsm/asked/e885bc.recent.json`의 3개 프롬프트에 해당 답변이 없다(답변 자체가 저장되지 않음). `decisions.jsonl`·`otel-spans.jsonl`에도 그 문자열이 없다.

### 3.4 남은 미확정

- Codex가 그 태그 메시지에 `UserPromptSubmit` 훅을 **실제로 발화하는지**는 미확정이다. `decisions.jsonl`은 성공 경로에서 아무 행도 쓰지 않으므로(receive.py:342) "훅 미발화"와 "발화 후 필터 차단"을 이 자료로는 가르지 못한다. 격리 재현에서 필터가 차단함은 확정.
- 이 항목은 G02/P02의 필수 선행(기존 S5 실패 재현)이다.

## 4. crash 제어 시험체 — 새로 추가

`tests/test_crash_boundaries.py`(신규, 6개 검사). 실제 프로세스를 `SIGKILL`로
죽이는 `sitecustomize.py`를 `PYTHONPATH`로 끼워, 경계에 닿으면 즉시 죽고
`boundary-reached` 표식을 남긴다. 하네스는 실제 `python -m xsm` 서브프로세스로
CLI를 구동하므로 mock이 아니라 진짜 프로세스 사망이다.

| 경계 | 검사 | 오늘 관측된 동작 |
|---|---|---|
| 승인 적용(`connect.run`→`add_link`) 직후, 전송 전 | `ConnectionThenCrashTest` 2개 | 링크는 적용된 채 남고, 메시지는 held 사본으로 남는다. 재실행은 새 질문 없이 전송한다. **다만 재전송은 held id가 아니라 새 id로 나가고, 죽은 실행의 held 사본은 TTL까지 남는다** — spec P02가 요구한 "같은 원 ID 전송"이 이 경로에서 지켜지지 않는다 |
| inbox claim(rename→`.taking`)과 ack(`unlink`) 사이 | `InboxClaimThenCrashTest` 2개 | `.taking` 파일이 남고, 다음 `xsm inbox`도 `prune`도 이 사본을 회수하지 않는다(메시지 유실) — P04가 고칠 대상 |

자기검증 2개(`FixtureSelfTest`)는 sitecustomize가 실제로 죽이는지, 경계에 닿지
않으면 표식을 남기지 않는지를 확인한다.

**변이 검출 확인(4건):**

| 변이 | 결과 |
|---|---|
| M1 `inbox.take`에서 rename 제거 | `InboxClaimThenCrashTest` 2개 FAIL |
| M2 `connect.run`이 `config.add_link`를 부르지 않음 | `ConnectionThenCrashTest` 2개 FAIL |
| M3 = M1(rename 제거) + kill 조건을 bare `.taking`으로 넓힘 | `xsm/inbox.py not found` FAIL — 스택 검사가 잡음(`cli.py:2493 → bounce.py:84`에서 죽었음). **단, bare 조건 단독(원본 코드)은 `OK`다: 원본은 bounce 경로에 닿지 않으므로 결함이 아니다** |
| M4 ack를 unlink 대신 `.done` rename으로 바꿈 | 2개 FAIL |

M1–M2는 이 세션에서, M3–M4는 3차 검토자가 스크래치 복사본에서 실행했다. M3의 정확한 구성(M1+bare)은 3차 검토자의 후속 정정(`b9b5ef018e9f45b4`)으로 확인했다.

**킬 지점 증명(2차 검토 반영):** `bounce.take`도 `.taking` 이름을 쓴다(bounce.py:77-84). kill 조건을 `str(p).endswith('.taking')`로만 두면 엉뚱한 경계에서 죽어도 검사가 통과한다. 그래서 조건을 이 세션의 inbox 디렉터리 경로까지 좁히고, 죽는 순간의 스택을 `boundary-stack`에 남겨 `xsm/inbox.py`가 있고 `xsm/bounce.py`가 없는지 검사한다.

기존 시험체와의 관계:

| 경계 | 기존 시험체 | 판정 |
|---|---|---|
| 프로세스 사망 판정(`_dead_pid`, `os.kill(pid,0)`) | test_xsm.py:157, 3018; test_discovery_latency.py:466; test_stalled_probes.py:57 | 있음 |
| 실제 자식 프로세스 강제 종료 | test_stalled_probes.py:262, 309 | 있음(프로브 정지 한정) |
| 승인 적용↔전송 사이 중단 | test_crash_boundaries.py | **신규** |
| receive claim/ack 중간 종료 | test_crash_boundaries.py | **신규** |
| hook/inbox 동시 접근 | 없음 | **없음**(P04) |
| 세션/데몬 재시작 뒤 같은 ID 회복 | 없음 | **없음**(P04/P08) |

## 5. 환경 의존 실패 (기준선에 이미 있던 것 아님)

세션 환경변수를 그대로 둔 회귀에서 3건이 실패했고, `env -i`의 깨끗한 환경에서는 0건이었다.

| 실패 | 방아쇠 | 원인 |
|---|---|---|
| test_workers.SafetyTest.test_a_parent_goodbye_reaps_once_its_process_is_gone | `CLAUDE_CONFIG_DIR` 설정 | `stated_home`(receive.py:76-84)이 env를 보고 홈을 지정 → `mark_ended`가 home 불일치로 반환(registry.py:774-800) |
| test_xsm.LifecycleTest.test_sessionend_hook_marks_the_pointer | `CODEX_HOME` 설정 | 같은 경로 |
| test_xsm.ScopeTest.test_session_end_drops_the_reach | `CODEX_HOME` 설정 | 같은 경로 |

이 3건은 **제품 결함도 기준선 회귀 실패도 아니다.** 이미 테스트 프로세스가 활성 하네스 홈을 가리지 않는다고 가정한 테스트이고, 활성 세션 안에서 돌리면 깨진다. 진행 규칙: 기준선 회귀는 `env -i`(또는 해당 env 제거)로 실행한다.

**결함 해결과 기준선 준비를 구분한다:** 위 3건은 테스트 격리 문제로 기록만 하고, 제품 수정은 이 게이트의 성과로 계산하지 않는다.

## 6. 기준선 관측값

| 항목 | 값 |
|---|---|
| 전체 테스트 | 1034개, 203초(깨끗한 환경) |
| 실패/오류 | 0 |
| 발견 지연 예산(3.9.6) | `first pass 1.01s`, `100 repeat asks 0.0020s`, `records() over 5 hung homes 1.07s` |
| 발견 지연 예산(3.14.6) | 별도 로그 `clean-314-regression.log` |
| 호출자 lookup 예산 | `probe.QUICK_TIMEOUT = 1.0`, `probe.QUICK_BUDGET = 3.0` (xsm/probe.py:35-36). 한 번의 대화형 lookup이 공유하는 전체 예산 3초, 개별 프로브 상한 1초. 적용 위치: `registry.py:833`(me), `mcp.py:358`(MCP caller lookup), `send.py:154`, `cli.py:196`. (1차 문서의 `GIT_TIMEOUT` 설명은 틀렸다 — git 호출용 5초 상한은 다른 값이다.) |
| 등록 세션 | 102 registered, 7 live, 1 unregistered |
| gate 결정 누적 | pass 896, held 10, duplicate 10 (`otel-spans.jsonl`) |

## 7. 게이트 판정

P00 `passed`, G00 `passed`. **B01(P01·P11)의 진입 조건이 열렸다.**

- 전체 회귀(두 인터프리터, fixture 포함 1040개)·manifest·S5 관측·crash 제어 fixture 2경계를 확보했다.
- 호출자 lookup 예산도 코드 값으로 닫았다(6절, 2차 검토 반영).
- crash fixture가 실제 결함을 잡는다는 것을 변이 4건으로 확인했다(4절).
- P00 `수정 후보`(tests/test_one_yes.py, test_mcp_identity.py, test_remote.py, fixtures)는 **하지 않았다**. 새 crash fixture만 추가했다.
- **미확정으로 남긴 것:** Codex가 태그 답변에 `UserPromptSubmit` 훅을 실제로 발화하는지(3.4절). 이것은 G00의 종료 조건이 아니라 G02/P02가 실제 하네스에서 재현할 대상이다.

### 7.1 독립 검토 1차 (Opus 5.5)

당시 `partial` 판정을 뒤집을 지적 세 가지를 받았다.

| 지적 | 확인 결과 | 처리 |
|---|---|---|
| 깨끗한 회귀가 3.14.6이 아니라 3.9.6에서 돌았다 | 맞다. `env -i PATH=/usr/bin:…`에서 `python3` → `/usr/bin/python3` = 3.9.6 | 3.14로 다시 돌려 별도 로그 확보 |
| manifest 누락·부정확 | 맞다. `PermissionRequest` 훅, MCP·sandbox·설치 출처 없음 | 2절 보강 |
| crash fixture 미수행을 "미확정"으로 돌리고 통과시킨 판정 | 틀렸다. 만들어야 할 시험체를 안 만든 경우는 execution.md:165의 "증거 부족" 규정 대상이 아니다 | fixture 신규 작성 후 재판정 |

검토 로그: `/tmp/xsm-g00-review-Jx2tfh/review.md`.

### 7.2 독립 검토 2차 (Opus 5.5) — 이 문서가 반영한 것

2차 검토는 종료 조건 4개 충족은 인정하면서 문서 자체의 결함을 지적했다.

| 2차 지적 | 확인 결과 | 처리 |
|---|---|---|
| P00 `passed`의 근거 없음 — lookup 예산을 코드 상수로 닫을 수 있는데 미확인으로 뒀다 | 맞다. 값은 `probe.py:35-36`에 있다 | 6절에 상수·적용 위치 기록, 미확인 해제 |
| 문서 내부 모순 — 7.1절 "partial로 정정", 7.2절 "남은 일: fixture" | 맞다 | 이 개정에서 7절 전체 정리 |
| inbox kill 조건(`.taking`)이 `bounce.take`와 겹친다 | 맞다. 변이 검사에서 `cli.py:2493 → bounce.py:84`에서 죽는 것을 확인 | kill 조건을 inbox 디렉터리 경로로 좁히고, 죽은 스택에 `xsm/inbox.py`가 있는지 검사 추가 |
| manifest에 하네스 CLI 버전·Codex sandbox 없음 | 맞다 | 2절에 `codex-cli 0.164.0`, `Claude Code 2.1.312`, `danger-full-access`/`never` 추가 |
| S5 출처 파일 표기 틀림(10-28 vs 실제 10-23) | 맞다 | 3.1절 정정 |
| `final-regression.log` 미인용 | 맞다 | 1절에 추가 |

검토 로그: `/tmp/xsm-g00-review2-DE9tZT/review.md`.

### 7.3 이 판정이 여전히 틀릴 수 있는 지점

- `fixture`는 경계가 닿았을 때 죽는 것과 다음 실행의 관찰을 고정한다. 회복이 **완전한지**는 P02/P04가 판정한다. 이 문서는 "회복이 불완전하다"는 사실(재전송이 새 id로 나감, `.taking` 미회수)을 기록했고 그것을 고쳤다고 하지 않는다.
- 계획 상태 파일(plan.json)의 `status`는 아직 `draft-implementation-not-started`다. 이 게이트 기록과 그 파일의 상태가 다르다.

### 7.4 fixture 이식성 결함 (3.9, 이 개정에서 발견·수정)

fixture를 3.9.6에서 처음 돌렸을 때 `test_crash_boundaries` 모듈 import가 실패했다.

```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
  tests/test_crash_boundaries.py:129, def _cli(self, *argv, probe: str | None = None …)
```

저장소는 3.9+를 지원한다(`docs/xsm/TESTPLAN.md`). 기존 테스트는 PEP 604 유니언을 쓰지 않는다(future import 0개). fixture의 시그니처를 3.9 호환으로 고쳤고, 두 인터프리터에서 확인했다.

```
py3.9 : Ran 6 tests in 4.132s / OK
py3.14: Ran 6 tests in 2.757s / OK
```

이 결함은 **fixture 자체의 결함**이지 제품 결함이 아니다. 다만 3.14에서만 돌렸다면 놓쳤을 종류라, 기준선 회귀를 두 인터프리터에서 돌리는 규칙의 근거가 된다. 이 실패 원문은 `/tmp/xsm-baseline-bkZPcz/py39-final-regression.log`(`Ran 1035 tests`, `FAILED (errors=1)`, import 실패)에 남아 있다. 같은 디렉터리에 수정 후 `f39.log`(`Ran 1040 / OK`)가 있다.

### 7.5 독립 검토 3차 (Opus 5.5) — 이 문서가 반영한 것

3차 검토는 `passed`에 동의하면서 문서 모순 5건을 지적했고, 모두 확인해 반영했다.

| 3차 지적 | 확인 결과 | 처리 |
|---|---|---|
| 5행 "독립 검토 2회", "7.0–7.3절" — 7.0절이 없고 7.4절이 있다 | 맞다 | 3회·7.1–7.5로 정정 |
| 6행 `planned-not-executed`라는 값이 어디에도 없다 | 맞다. plan.json:5는 `draft-implementation-not-started`, P00은 `planned-not-started` | 실제 값으로 정정 |
| 109행 "두 변이"와 159행 "변이 3건"이 다르다 | 맞다 | 변이 4건 표로 통일(4절) |
| 64행 "448·449행"은 ordinal이지 파일 행이 아니다 | 맞다 | 파일 행 449·450 / ordinal 448·449로 병기 |
| 62행 "spec.md 225줄의 가정을 반증"은 사실이 아니다 | 맞다. 225줄은 두 채널을 다 상정한다 | "요청 ID 있는 채널로 관측"으로 정정 |
| `_fake_codex`가 test_codex_wake.py:244에 이미 있다 | 맞다. 새로 쓴 것은 중복 | 아래에 기록(판정에는 영향 없음) |

3차 검토가 직접 실행한 것: `tests.test_crash_boundaries` 두 인터프리터 `Ran 6 / OK`, 변이 M1–M4. 검토 로그는 reviewer 세션 응답 메시지 `0c6ea2ba3ff9487e`에 있다.

3차 검토는 이어서 **3.9 전체 회귀를 독립으로 다시 돌려** `Ran 1040 tests in 198.137s` / `OK`를 확인했다(리뷰어 세션 응답 `dbab56d6277b4cd9`, 로그 `…/scratchpad/py39-full.log`, `test_crash_boundaries.py` sha1 `27482186` = 현재 파일). 이로써 두 인터프리터 1040/OK가 서로 다른 실행자에서 나왔다.

**미흡 1건:** spec.md P00.4 앞 문장은 "기존 fixture 재사용"인데, 새 fixture는 fake codex를 자체 정의한다(`test_crash_boundaries.py`의 `_fake_codex`). `test_codex_wake.py:244`의 같은 목적 헬퍼를 재사용하지 않았다. 판정을 뒤집지 않지만 계획 문면과 어긋나므로 P01에서 통합 여부를 정한다.

## 8. 재현 명령

```sh
# 기준선 회귀 (깨끗한 환경)
cd <repo>
env -i PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin HOME="$HOME" \
  XSM_HOME="$(mktemp -d)/state" PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s tests -v
```
