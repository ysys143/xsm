# G02 연결 복구 — 실행 기록

- 상태: **passed (로컬 G02 계약)**. 검토 정책(execution.md 7절, 2026-10-28 개정)에 따라 검토는 게이트당 1회로 줄였다. 전체 회귀 두 인터프리터 `Ran 1114 / OK`.
- revision: 작업 트리(커밋 `4fd7c9f` 위 미커밋 변경). 제품 버전 0.4.20.
- 실행자: 코디네이터 직접(서브에이전트가 조사 단계에 머물러 종료됨).
- 진입 게이트 G01 `passed`.

## 1. 종료 조건별 증거

| 종료 조건 (execution.md G02) | 결과 | 증거 |
|---|---|---|
| 같은 비동기 답 채널의 원문→유효 판단→연결 readback→같은 원 ID 전송→실제 회신 | 부분 | S5 근본 결함 수정(아래 2절). 같은 원 ID 전송은 3절. 실제 하네스 회신은 미실행 |
| 수집 단절은 unknown | 통과(기존) | `consent` 회귀 유지 |
| 거부/취소는 미연결 | 통과(기존) | test_person_decisions, test_one_yes |
| 적용 후 crash 재개에 같은 허용 재질문 없음 | 통과 | `tests/test_crash_boundaries.py` — 재시도가 새 질문을 열지 않고 held id로 전송 |
| 형제·다른 부모 직접 왕복 | 미검증 | 기존 test_one_yes만으로 해당 관계를 증명하지 못함. 검토에서 근거 오류 확인 |

## 2. S5 근본 결함 수정 (P02 항목 3)

G00이 찾은 결함을 고쳤다. Codex는 질문 도구의 답을
`<send_user_message_question_reply>[{...questionItemId...}]</send_user_message_question_reply>`
로 보내는데, `consent.not_a_reply()`의 하네스 태그 규칙이 이것을 드롭해 어떤 ask도 verdict를 받지 못했다.

수정(`xsm/consent.py`):
- `ANSWER_TAG`/`ANSWER_RE`/`answer_reply()` 추가: 태그+JSON을 사람의 답으로 인식하고 `questionItemId`를 요청 ID로 추출
- `not_a_reply()`가 이 태그를 답으로 인정
- `record()`의 `UserPromptSubmit` 분기가 `answer_reply()`를 호출해 `note_verdict(request=...)`로 저장, pending 파일에 `answer_request` 필드 추가

**반례 테스트:** `test_a_harness_answer_tag_is_the_persons_verdict`(태그 답변=verdict + 요청 ID 보존), `test_a_task_notification_is_still_not_a_verdict`(하네스 잡음은 여전히 드롭).
**변이 검출:** `record()`의 `answer_reply` 분기를 제거하면 첫 테스트가 실패한다(태그 원문이 verdict로 들어감).

## 3. 같은 원 ID 재개 (P02 항목 5)

G00 fixture가 "재시도가 새 id로 나가고 held 사본이 TTL까지 남는다"를 오늘의 동작으로 고정했었다. 고쳤다.

수정:
- `xsm/outbox.py`에 `find()` 추가: `put()`과 같은 키로 이 세션이 이미 보관한 사본을 찾되 **새로 만들지 않는다**
- `xsm/send.py`: 연결이 이미 있어 `connect.offer`를 안 거칠 때 `outbox.find()`로 사본을 집어 **그 id로 전송**하고, 가면 `outbox.drop`이 사본을 지운다

**테스트 변경:** `test_crash_boundaries.py`의 `test_the_retry_after_the_crash_sends_without_a_new_question`을 새 계약(재시도가 held id로 전송, 사본이 남지 않음)으로 바꿨다.

## 4. plan 결속과 적용 직전 재확인 (P02 항목 1·4)

`xsm/connect.py`:
- `_plan_digest()`: verb·target·here·cwd의 SHA-256을 plan에 넣어 사람이 승인한 계획을 고정
- `_target_handle()`: 대상의 ref·runtime·session_id·home·alias·pid·lstart를 plan에 결속(짧은 ref만으로는 부족)
- 당시 `_still_the_plan()`은 호출되지 않아 이 주장은 검토에서 기각됐다. 이후 이 함수를 삭제하고 승인 요청 키에 계획·핸들을 결속했다. 아래 최신 실행 기록을 따른다.

## 5. 남은 미해결

| 인터프리터 | 결과 |
|---|---|
| 3.14.6 | `Ran 1114 tests in 148.480s` / `OK` (`/tmp/p02-314.log`) |
| 3.9.6 | `Ran 1114 tests in 189.550s` / `OK` (`/tmp/p02-39.log`) |

기준선 1040 → 1114(신규 74개).

- **실제 하네스 셀 미실행:** 실제 비동기 채널의 질문→답→연결→원 ID 전달→실제 회신을 하나의 trace로 남기는 것은 이 세션에서 실행하지 않았다. 격리 fixture까지만 확인했다. P13에서 실제 세션으로 확인한다.
- **D01·D04 미결:** 기본 연결 단위·수명을 바꾸는 새 정책은 활성화하지 않았다(사용자 결정 전). 기존 범위·수명에서 승인 적용을 견고하게 만드는 부분만 진행했다.
- **P02 항목 2·6 미완:** 기존 구현·테스트가 덮는다는 이전 주장은 근거가 부족했다. 형제·다른 부모 왕복 및 승인 협업 집합을 검증해야 하며, 실제 하네스 조건을 P13으로 옮겨 G02를 통과시킬 수 없다.

## 6. 목표 재개 후 결속 경로 수정 (2026-10-28)

기존 4절의 digest/handle 함수는 정의만 있었고 `offer`에서 적용하지 않았다.
따라서 4절의 구현 설명은 경로 검증 증거가 아니었다. 이를 실제 경로로 연결했다.

- `consent.take_or_request(binding=...)`: 같은 pending 파일 잠금 안에서 이전 계획·핸들과 비교한다. 변경됐거나 구형 ask에 binding이 없으면 답을 재사용하지 않고 새 ask로 교체한다. 결속된 요청은 legacy 단일 슬롯 답으로 fallback하지 않는다.
- `connect.offer`: digest와 전체 대상 핸들을 전달하고 적용 직전 대상 검사를 호출한다.
- `tests/test_connection_binding.py`: 같은 ref·폴더의 다른 session_id가 이전 대상의 승인을 쓰는 경로를 재현했다. 수정 전 `AssertionError: True is not false`, 수정 뒤 통과.
- 실행: `python3 -m unittest tests.test_connection_binding tests.test_one_yes tests.test_person_decisions tests.test_crash_boundaries -q` → `Ran 118 tests in 29.451s / OK`. 로그 `/tmp/g02-binding-tests.log`.
- Opus 구독 CLI 독립 검토 실행 중. 기존 reviewer에도 검토를 요청했다(메시지 `ec11df2998fe425e`, receiver recorded).
- 실제 하네스 전체 승인 trace는 여전히 미실행이며 G02 passed 또는 B03 진입으로 세지 않는다.

## 7. 독립 검토 1차와 추가 수정

Opus 5.5 구독 CLI 검토 판정은 **통과 불가**. 원문 `/tmp/xsm-g02-opus-review.log`.
계획 결속 미적용, 구조화 답 ID의 미소비, 실제 하네스 증거 부재, 실패 주입 부족,
형제 왕복 증거 오류, held 재개 시 송신 원장 덮어쓰기 가능성을 지적했다.
6절 변경은 검토와 병행해 반영됐으므로 검토 원문이 보는 이전 상태와 구분한다.

추가 수정: `send.py`의 held 재개가 기존 원장을 먼저 조회한다. 전체 digest·대상이
다르면 거절하고, 이미 수신된 결과는 재송신·원장 덮어쓰기 없이 반환한다.
미확정 송신은 기존 resend 검사를 통과해야 하며 재개 ID를 notes에 표시한다.
`test_connection_binding`의 전달 후 잔여 사본 및 대상 교체 반례 2개는 수정 전
각각 sent-unconfirmed를 반환해 실패했고, 수정 후 기존 승인 결속 반례 포함 3개 통과.

미완: 구조화 답의 질문·요청 결속 소비, 실제 훅 발화 및 왕복 trace,
형제·다른 부모 왕복, 적용 실패의 같은 ID 복구 증거. G02 미통과로 B03 제품 구현은 전제 미충족.

## 8. ADR-0024 반영과 실제 하네스 실행 (2026-10-28)

이 절이 앞선 시점의 미실행/미결 기록보다 최신이다. G02 passed 판정은 수정 검토와 최종 회귀를 마친 뒤 별도로 기록한다.

- **세션 선택 범위:** `collaboration.py`에 runtime·home·session_id 한 쌍의 양방향 허용·철회를 추가했다. `connect.select`는 확실한 호출자·대상 재확인·사용자 선택을 소비하며, `config.scope_for`는 기존 범위를 유지하면서 선택한 대화 쌍만 추가로 허용한다. 일반 `send`의 기존 폴더 연결과 명시적 link/join/reach는 호환 경로다. 새 선택 인터페이스는 P03에서 실제 핸드셰이크에 연결한다.
- **적용 실패 재개:** 승인 적용 callback을 consent의 잠금/소비 경계에 넣었다. 적용 실패면 원래 승인을 소비하지 않고, 같은 원 ID를 재시도한다. `test_failed_application_keeps_the_same_approval_and_message_for_retry`가 이를 실행한다.
- **native 사용자 답 readback:** 오래된 설치 훅에서 누락된 Codex 응답을 `user_answers.read_answer`가 실제 rollout의 session_meta·user role·질문 ID로 확인한다. 상한 2MiB tail+bounded metadata만 읽고 가짜 hook event를 만들지 않는다. `--answer-request`는 원 질문의 실제 답을 보여주고 다음 정상 재실행으로 적용한다. 질문의 대상 대조, 요청별 single-use marker/ask nonce, 최초 회수 시점의 기존 application TTL을 적용한다. 원 source timestamp는 별도 native_evidence에 남기고 재회수로 TTL을 연장하지 않는다.
- **출처와 미지원 구분:** 설치본 snapshot의 구조화 답 미수집이 실제로 재현됐다. 새 CLI로 실제 native 답을 readback해 복구했고 설치본이 자동 갱신됐다고 주장하지 않는다. 훅이 발화했다고 주장하지도 않는다.
- **실제 trace:** 사용자가 `call_7279cdb9975947b29075d6d8934afa5d` 질문에 준 “평가용 연결 허용, 종료 후 해제”를 native Codex role=user에서 확인 → CLI가 원 질문/답을 표시 → 재실행 link readback → 실제 Claude `-p` 세션 `60d01a`로 요청 `bf3cfcd1e4c04154` 전달 → 실제 회신 `29eb4fe1ba8c4d3d`의 reply_to가 원 ID와 일치 → 현재 Codex inbox에서 `G02-LIVE-ACK` 수신. `[deliverables/g02-live/trace.json]`에 요청·회신 원장과 연결 해제 readback을 보존했다.
- **정리:** 승인된 임시 폴더 연결을 `xsm unlink`로 해제했다. readback 결과 `evaluation_link_remaining=false`. Claude 평가 프로세스 정상 종료(exit 0), 로그 `/tmp/xsm-g02-live-claude.log`.
- **형제/다른 부모:** `tests/test_peer_roundtrip.py`는 두 토폴로지에서 실제 registry/config/send/receive 서비스로 총 4회 왕복·8개 메시지를 확인한다. transport만 mock한 fixture이며 두 물리 머신 증거가 아니다.
- **검증:** 관련 단위 143개 `/tmp/g02-targeted-latest.log`에서 OK. 이후 추가한 nonce/short-name 변경은 별도 영향 검사와 최종 회귀에서 대조한다. 전체 회귀와 Opus 수정 범위 검토는 실행 중이다.

잔여 원격·핸드셰이크·디렉터리 부분은 명시된 소유 단계(P03/P05/P12/P13)에 남으며 G02에서 구현했다고 세지 않는다. 기존 62개와 A24-01–08의 전체 종결도 별도다.

## 9. readback 경계 검토와 수정

Opus 수정 검토는 훅에서 이미 소비한 답 재사용, 후속 철회 무시, 오래된 source,
질문 동사 미결속, a1 짧은 이름, 실제 진입점 부재를 지적했다.

- 모든 구조화 hook 답 소비도 같은 single-use marker를 남긴다. importer는 native source `since=now-TTL`·`latest_only=True`를 적용한다. 원 질문 ID와 원문 digest가 해당 pending/대상 binding에 결속되지 않으면 거절한다. readback 시간으로 오래된 source를 갱신하지 않는다.
- 공개 CLI는 `--answer-request QUESTION_ID --question ORIGINAL_TEXT`를 함께 받아 제품 경로에서 bind_question을 호출한다. bound ask가 여러 개면 binding으로 정확한 키를 고른다. 두 글자 a1은 collaborate에 한해 정확한 경계로 매칭하고, 한 글자 plan b를 세션 선택으로 읽지 않는다.
- `xsm connect`와 `xsm_connect`가 실제 `connect.select`를 호출한다. 현재 `permitted`는 권한만 적용된 상태이며 핸드셰이크는 `not-started`로 표시한다. P03이 실제 답 서비스에 연결한다.
- 적용 callback은 ValueError/OSError 실패 모두 승인·원 메시지를 보존한다. 새 세션 선택도 저장 성공 뒤 승인을 소비한다.
- `tests/test_native_consent.py` 7개는 공개 CLI의 자동 결속→실제 native fixture 답 표시→link 적용과 hook 소비 후 재회수, 오래된 source, 후속 철회, 다른 질문을 검증한다. `tests/test_selected_connection.py` 5개는 a1 포함 실제 서비스 선택을 검증한다.
- 최신 실제 도구 응답 `call_13624da3e4a3409e871585d1615cd4cb`의 `G02 채널 확인`을 현재 코드에서 원 질문 digest/source TTL/latest로 확인→표시→소비→재회수 거절했다. 이는 진단용 응답이며 권한 확대에 쓰지 않았다. `deliverables/g02-live/native-channel.json`.
- 앞선 전체 실제 link 왕복은 hardening 전 실행이라는 provenance를 `trace.json`에 명시했다. 당시 bind_question을 직접 호출하지 않았고, 당시 제품 CLI에서 readback했다. 현재 hardened 공개 CLI 경로는 격리 native fixture로 별도 실행했다. 실제 진단은 서비스 경로로 실행했다. 이 증거 종류를 섞지 않는다.

최종 전체 회귀 실행 중: `/tmp/g02-final314.log`, `/tmp/g02-final39.log`.
검토자에게 N1/N2의 공개 경로·binding 수정 범위 확인을 요청했다.

## 10. G02 판정

코디네이터 판정: passed. Opus 5.5 최초 검토와 reviewer 수정 범위 확인에서 나온 차단 결함을 수정했다. reviewer의 최종 확인 `4e1437c9d23b46c9`는 N1/N2 수정과 변이 검출, 해당 수정 범위의 차단 결함 없음을 확인했다.

- 고정 소스: `deliverables/g02-live/source-manifest.json`. 실행 종료 뒤 모든 기록된 xsm/tests 파일의 hash 재대조에서 변경 0개.
- Python 3.14.6: `Ran 1196 tests in 157.510s / OK (skipped=1)` — `/tmp/g02-final314.log`.
- Python 3.9.6: `Ran 1196 tests in 175.378s / OK (skipped=1)` — `/tmp/g02-final39.log`.
- skip 1개는 P05의 공통 제외 정책 준비 검사로 G02 조건이 아니다. P05에서 실제 검사로 전환한다.
- 실제 link 왕복과 hardening 뒤 실제 native 응답 진단, 현재 공개 CLI의 fixture 실행을 위 8·9절처럼 분리해 판정했다. 현재 모든 수용 조건이 같은 revision의 실제 하네스로 닫혔다고 주장하지 않는다.
- 범위: 원 ID·대상 결속, 승인 적용 실패/재개, 실제 승인 채널 및 왕복 관측, 형제/다른 부모 직접 왕복, 선택 세션 한 쌍 권한의 로컬 계약. 실제 peer 핸드셰이크 결과를 반환하는 인터페이스는 G03, 디렉터리는 G05, 원격은 G12/G13에서 종결한다.
- 비차단 기록: native readback은 현재 CLI 전용이다. MCP의 공통 서비스/능력 안내는 P03에서 통합한다. 원 질문/동작의 의미를 에이전트가 읽고 판단하는 기존 uid 경계는 유지하며, question ID·digest·대상 binding을 기계적으로 대조한다. UI 원문/동작 결속 보강은 계획된 P07 소비 범위로 추적한다.
