# 상태 모델 검증에서 나온 결함의 단계적 수정

- 상태: **확정**(3판, 2026-11-25)
  - D1~D3은 사용자가 결정했다.
  - 적대적 검토(critic)는 REVISE였다. 지적 11건을 반영했다(§11). 2판에 대한 critic 재검토는 하지 않았다. 사용자가 확정을 지시했다.
  - 사실 대조를 반영했다.
  - 3판에서 사용자 원칙 P*(§0)를 적용했다(§12).
- 기준 코드: `2a858d3`(0.6.1)
- 근거: `deliverables/statechart-20261125/`(TLA+ 모델 19개 설정, 재현 시험 약 60개, TLC 보고서)
- 범위: 1차 2건과 확장 11건, 모두 13건(F1~F13). 줄이지 않는다.

## 0. 제1원칙(사용자, 2026-11-25)

> "보안경계, 차단보다는 seamless한 ux를 최우선으로"

이 계획의 모든 결정은 아래 순서로 판단한다. 수정이 사용자가 원하는 대화를 새로 막거나 묻는 단계를 늘리면, 그 수정은 틀린 것이다.

1. 대화는 끊기지 않는다. 인수인계·이관·머신 간 전달 뒤에도 메시지와 답은 받는 쪽에 도착한다.
2. 확신이 없으면 막지 말고, 가장 그럴듯한 쪽으로 전달하고 표시한다. 표시의 예: "인수인계 미확인", "이전 처리 상태".
3. 사람에게 다시 묻는 것은 사람이 이미 멈춘 것(보류)과 명백히 잘못된 것(차단 목록, 순환·이중 인수인계)뿐이다. 그 경우에도 거부로 끝내지 않고 다음 행동을 제시한다.
4. 부분 실패는 건너뛰고 보고한다. 전체를 멈추지 않는다.

## 1. 사용자 이야기

- xsm 사용자는 세션 A의 자리를 B에게 인수인계한 뒤에도 일이 끊기지 않기를 원한다. A가 기다리던 답, A에게 온 메시지, A가 이야기하던 상대를 B가 빠짐없이 이어받아야 한다.
- 사용자는 게이트가 보류한 메시지가 자기 "예" 없이 어느 세션에도 보이지 않기를 원한다. "예"라고 한 메시지는 다시 묻지 않기를 원한다.
- 두 머신에서 일하는 사용자는 두 머신이 팀장·구성원과 인수인계 결과에 대해 같은 답을 내기를 원한다. 어느 쪽의 변경도 조용히 사라지면 안 된다.
- 인수인계가 "다 옮겼다"고 보고하면 그 보고는 사실이어야 한다. 옮기지 못한 것은 이름이 나와야 한다.

## 2. 결함 목록

| ID | 결함 | 원인 위치 | 재현 시험(`deliverables/statechart-20261125/`) |
|---|---|---|---|
| F1 | 보류된 DM이 인수인계 문서로 B에게 그대로 보임 | `handoff.move_out`(`handoff.py:517`), `handover._unread`·`_letter`(`handover.py:398`, `:428`) | `round1/replay_test.py` `test_held_dm_reaches_successor_through_the_letter` |
| F2 | (a) A에 미소비로 있던 답이 B의 질문 기록에 색인되지 않음. (b) 인수인계 도중 도착한 답을 A가 읽고, 기록되지 않음 | (a) `_unread`, `poll_replies`가 자기 폴더만 읽음(`receive.py:237`). (b) 인수인계 기록을 마지막에 씀(`handover.py:455`) | `round1` `test_answer_waiting_at_A_is_never_recorded_for_B`, `test_answer_arriving_mid_handover_is_read_by_A_and_never_recorded` |
| F3 | 묶음: 인수인계 뒤 최종 답이 빠지고, 다 답한 묶음이 `refused`로 보임 | `_groups`는 무조건 옮기고(`handover.py:379`), `_questions`는 최종 답이 있는 질문을 남김(`:368`). `questions.status`는 정확한 발신자만 읽음(`questions.py:115`) | `scope-groups` `test_group_hides_a_final_answer_after_handover`, `test_fully_answered_group_reads_refused_after_handover` |
| F4 | P↔B 범위가 없으면 늦은 답이 발송 거절됨 | `send.py:431` `scope_for`. 인수인계는 팀만 옮김 | `scope-groups` `test_late_answer_reach_held_by_A`, `…_P_is_a_worker_of_A`, `…_same_folder_B_elsewhere`, `…_link_B_outside` |
| F5 | 동시 인수인계가 자리·질문·주소를 갈라놓거나 순환을 만듦 | `_check`→기록 사이에 잠금이 없음(`handover.py:440-455`) | `concurrent` `test_a_two_successors`, `test_b_cycle`, `test_b_cycle_and_the_late_answer`, `test_c_target_hands_over_meanwhile`, `…_and_the_late_answer` |
| F6 | 팀 목록을 두 번 계산해서 팀 자리와 보드 항목이 따로 움직임 | `handover.py:442`과 `_teams`(`:334`). `_teams`는 잠금 안에서 구성원인지 다시 보지 않음 | `teams/replay_places_test.py` `test_path_*` |
| F7 | 복사와 닫기 사이에 `owner/A`에 쓴 내용이 B에게 가지 않음. 머리 둘인 항목은 건너뛰고도 알리지 않음 | `_boards`(`handover.py:306-314`), `board.set_item` 부모 계산(`board.py:251`) | `teams/replay_board_test.py` |
| F8 | 두 머신의 팀 기록이 되돌려지거나 갈린 채 굳음 | `team_sync.py:89`. 로컬 기록에는 `origin`이 없어 동률이면 들어온 기록이 항상 이김 | `teams/replay_teamsync_test.py` |
| F9 | 원격 질문자가 B의 답을 영구 거절함(인수인계 뒤 질문, 증언 유실, 사슬) | `origins_for`(`network_messages.py:397-411`)가 `local == old`만 셈. `_publish`는 인수인계 때 한 번만 부름 | `remote` `test_asked_after_handover_b_answer_is_refused_on_the_asking_machine`, `test_testimony_lost_after_the_answer_was_refused_nothing_ever_recovers_it`, `test_chain_second_handover_is_not_told_to_the_machine_that_asked_a` |
| F10 | A가 읽지 않은 원격 질문에 B가 답장을 만들지 못함 | `move_out`이 원문을 닫고 B에게는 사본이 없음. `_ingress`가 원문을 못 찾음(`network_messages.py:447-450`) | `remote` `test_unread_question_at_handover_cannot_be_answered_by_the_successor` |
| F11 | `held deliver` 뒤에도 원문이 pending이라 다시 보류되거나 두 번 보임 | `cli.py:1551-1561`이 영수증만 바꾸고 원문은 두는 것 | `migration` `test_held_deliver_then_inbox_holds_again`, `…_inbox_shows_again`, `…_then_transfer_then_b_shows_again` |
| F12 | 이관 커밋 직후 A에서 생긴 보류 항목에 B가 닿지 못함 | `receive.hold`(`receive.py:285-312`)에 이관 검사가 없음 | `migration` `test_in_flight_gate_hold_after_the_move_stays_bound_to_a` |
| F13 | 아무도 보지 않은 메시지에 `delivered` 영수증이 남음 | `take_inbox_claims`가 영수증(`receive.py:1383`)을 쓴 뒤 `handoff.handoff`(`:1393`)를 부름. 훅 경로는 해당 없음 | `migration` `test_delivered_receipt_written_then_fence_refuses_the_handoff` |

## 3. 형태(Shape)

### 3.1 비교한 두 형태

**형태 A: 지점 수정.** `_unread`에서 보류된 원문을 거르고, 답을 색인하는 코드를 덧붙인다. 문서는 지금처럼 원문을 싣는다.
- F10이 풀리지 않는다. B의 저장소에 원문이 없어 역방향 검사(`_ingress`)가 실패한다.
- "A의 원문이 B에게 어떻게 가는가"를 세 곳이 각자 판단한다.

**형태 B: 원문의 소유권을 옮긴다(채택).** 인수인계가 A의 미소비 원문과 보류 항목을 B로 옮기고, 문서에는 건수와 ID만 싣는다. B는 평소 경로(게이트 → claim → ack)로 받는다.
- 비용: B의 게이트가 옮겨진 원문을 다시 판정한다. 그래서 게이트에 인수인계 원문 규칙이 필요하다(§3.3).
- 비용: p2p 원문은 결속 증명을 넓혀야 한다.

### 3.2 호출 모양(구현 전 계약)

```python
# xsm/handover.py
def hand_over(me, target, summary, approval, plan) -> dict:
    with _handover_lock(timeout=30):                # F5: one handover at a time on this machine (blocking)
        _check(me, target, resume=True)             # same target may resume its own `moving` record
        rec = _begin(me, target, summary, approval, plan)   # handovers/<A>.json state="moving",
                                                            # stores summary/approval/plan/places/step marks
        # follow(A) == B from here (F2b); readers of letters/receipts see only state=="done"
        _step(rec, "boards",    lambda: _boards(me, target, rec["places"]))     # idempotent by marker
        _step(rec, "teams",     lambda: _teams(me, target, rec["places"]))      # rechecks membership under lock (F6)
        _step(rec, "questions", lambda: _questions(me, target))                 # + children of moved groups (F3)
        _step(rec, "groups",    lambda: _groups(me, target))
        _step(rec, "links",     lambda: _copy_links(me, target, rec["plan"]))   # D1; failures skipped, listed
        _step(rec, "originals", lambda: handoff.hand_to(me, target, rec["id"])) # F1 F2a F10; conflicts stay at A, listed
        _step(rec, "held",      lambda: held.rebind(me, target))                # D2; shared with migration_state.held
        _finish(rec)                                # state="done", letter with counts, ids, skipped items
    _publish(rec)                                   # outside the lock (network)

# xsm/handoff.py
def hand_to(source, target, handover_id) -> dict:   # {"moved": [...], "kept": [{"id", "why"}]}
    """Import legacy exports first (as migration_state does), then copy each
    non-acked original to target with handover_history=[{id, source, target,
    previous_state}] (NOT migration_history: 0.6.1 readers check only that field).
    Source copy: state=pending, moved_to=target. A digest conflict keeps that one
    message at the source and continues (fail-open). Idempotent per handover_id."""
```

- `transfer`와는 공용 본문(`_copy_originals(source, target, hop, history_field)`)만 나눈다. 인가와 이력 필드는 호출자가 넘긴다.
- `held.rebind`는 `migration_state.held`(`migration_state.py:207-232`)의 본문을 공용으로 뺀 것이다.

### 3.3 인수인계 원문의 증명과 게이트

- **증명:** `handover_history` 홉은 `handovers/<source>.json`(`moving` 또는 `done`, 같은 `to_identity`)으로 증명한다. 이 증명을 받는 곳은 넷이다: `_ingress`, `ledger.handoff_step`, `receive._file_record`, `handoff._read`. `migration_history`와 `proves_copy`는 바꾸지 않는다.
- **게이트(P* 적용):** `hand_to`는 옮기는 시점에 `scope_for(sender, A)`를 계산해, 사본에 `predecessor_scope`로 찍는다. B의 게이트는 `handover_history`가 있는 원문을 다음 순서로 판정한다. 범위 id 동일성 검사는 하지 않는다.
  1. 차단 목록(deny)의 발신자이면 지금처럼 차단한다.
  2. A에서 이미 보류된 원문이면 B에서도 보류다(D2). 다만 보류 이유가 범위였고 지금 `scope_for(sender, B)`가 성립하면 보류를 풀고 전달한다.
  3. 그 밖에는 `predecessor_scope`나 지금 `scope_for(sender, B)` 중 하나라도 있으면 통과한다. 둘 다 없어도 "인수인계로 넘어온 메시지, A와의 범위 근거 없음" 표시를 붙여 전달한다. A가 받았어야 할 메시지를 B에서 막지 않는다.
  - 새 원문은 지금처럼 판정한다.
- **안내:** A가 이미 보여 준(`handoff-recorded`) 원문을 B가 받으면, 이관과 같은 형태로 "이전 처리 상태" 안내를 붙인다(`receive.py:1369-1373`).

### 3.4 그 밖의 형태 결정

- **F3:** 옮기는 묶음의 하위 질문은 최종 답이 있어도 함께 옮긴다. 읽기 규칙(`questions.status`의 발신자 일치)은 넓히지 않는다. 그래야 A가 인수인계 뒤에 새로 묻는 질문이 B에게 보이지 않는다.
- **F8(D3):**
  - `team.json`에 구조화된 `pending_ops`를 둔다. 연산 형식은 `{op: add|remove|lead|replace, member, at_generation}`이다.
  - 상대가 받았음을 확인하는 표지 `acked_by: {machine: generation}`을 둔다.
  - 로컬 기록의 `origin`은 자기 머신 키로 본다.
  - 동률일 때:
    - 내용이 같으면 에코로 보고 무시한다.
    - 내용이 다르면 머신 키가 큰 기록을 양쪽이 받는다. 진 쪽은 확인되지 않은 자기 `pending_ops`를 받은 기록 위에 다시 적용하고, generation을 올려 다시 보낸다.
  - 다시 적용이 충돌하면 그 연산을 버리지 않고 팀 로그와 보드 알림에 남긴다. 충돌의 예는 이미 빠진 구성원을 지우는 경우다.
  - 인수인계 연산은 `replace(A, B)`로 둔다.
- **F9(D5, pull, P* 적용):**
  - 조회 시점: `Gateway.receive` 시작부에서 잠금 밖에서 한 번 조회한다. 조건은 역방향 검사가 실패하고, 보낸 머신이 질문 대상의 머신과 같을 때다.
  - 조회 요청: 상대 요청 `succession {old, new}`로, 사슬 전체(8단계까지)를 한 번에 묻는다.
  - 결과: 증언으로 저장한다(`receive_testimony`와 같은 인증 규칙). 술어(`_reverse`)는 순수하게 둔다.
  - 조회가 실패하면(머신 오프라인 등) 답을 막지 않는다(P*). 다음 조건이면 질문 기록에 `succession: "unconfirmed"` 표시와 함께 기록한다.
    - 보낸 머신이 질문 대상(A)의 머신과 같다.
    - 답이 그 질문의 `reply_to`를 가진다.
  - 이렇게 기록하면 `question-status`가 "인수인계 미확인" 표시와 함께 답을 보여 준다. 증언이 도착하면 표시를 `confirmed`로 바꾼다. 증언이 다른 후임을 가리키면 `disputed`로 바꾸고 질문자에게 알린다. 답은 지우지 않는다.
  - 음성 캐시는 10분이다. `pending-succession/` 보관소는 두지 않는다.

## 4. 단계

단계마다 같은 순서로 진행한다.
1. RED 시험을 저장소 시험으로 넣는다.
2. 수정한다.
3. 변이 확인: 수정 핵심을 일시적으로 되돌려, 시험이 실패하는지 본다.
4. 전체 시험을 돌린다.
5. 해당 TLA+ 모델을 수정된 의미로 고쳐 확인한다.

main에 커밋으로 쌓고, 릴리스는 사용자 승인 뒤에 한 번 묶어서 한다.

| 단계 | 결함 | 내용 | 선행 |
|---|---|---|---|
| P0 | - | 재현 시험 중 RED 대상(아래 §5 각 기준이 가리키는 시험)을 `tests/test_state_model_*.py`로 옮긴다. 결정 표의 열린 질문 셋(§10)을 실측 시험으로 확인한다. `contract.yaml`(v2)을 쓰고 `contract_lint --spec`을 통과시킨다 | - |
| P1 | F5, F6, F2(b), F12 이관 판 | 인수인계 잠금(대기식 30초), `moving` 기록과 단계 표지, 재개, `xsm doctor`의 미완 인수인계 보고·재개, 구성원 재확인. `hold()`는 `migration.current_owner`를 따라 보류 항목을 묶는다 | P0 |
| P2 | F1, F2(a), F10, F11·F12 인수인계 판 | `hand_to`, `held.rebind` 공용화, `handover_history` 증명 넷, 게이트 규칙, 문서 형식 변경, 이전 처리 안내 | P1 |
| P3 | F3, F4 | 묶음 하위 질문 이동, `_copy_links`(D1), 승인 양식에 연결 목록 표시(plan→apply) | P2 |
| P4 | F11 이관 판, F13 | `held deliver`가 원문을 소비 처리(ack)한다. `take_inbox_claims`가 영수증을 handoff 뒤에 쓴다 | P0 |
| P5 | F7 | 보드 단계: 닫은 뒤 머리를 다시 확인해 남은 머리를 이어 옮긴다. 머리 둘인 항목은 `skipped`로 결과·문서·`handover/A`에 싣는다 | P1 |
| P6 | F8, F9 | `pending_ops`·`acked_by`·동률 규칙. succession 조회, 미확인 답의 기록·확정·이의 표시 | P2 |

P4는 P1~P3과 병렬로 진행할 수 있다. F11·F12의 인수인계 판은 P2에서 다룬다.

### 바뀌는 계약과 문서

- PROTOCOL §5.15(인수인계 순서, 문서 내용, 동시 인수인계, 인수인계 원문의 게이트 판정)와 §3(`handoffs`·`handovers`·`held` 행, 질문 기록의 `succession` 표시)
- 인수인계 승인 문구(`operations.py` `authorize`, `handover_service.py`), `summary_line`, MCP 결과 스키마(`operation_schema.py`)
- 기존 시험 `tests/test_handover.py:92` `test_unread_dms_go_in_the_letter_and_are_closed_as_moved`의 기대
- `migration_state.questions`가 `handover._questions`·`_groups`를 부른다(`migration_state.py:141-142`). 이관 경로 영향 시험을 넣는다.
- 잠금 순서를 한 곳에 적는다: handover 잠금 → `registry.lock_records` → `teams._locked` → `handoff._locked`

## 5. 수용 기준

각 기준은 P0에서 만든 시험으로 확인한다. "RED에서 실패 → 수정 뒤 통과 → 변이에 실패"까지 본다.

- **SM-F1:** 보류된 DM을 가진 A가 B에게 인수인계하면 다음이 모두 성립한다.
  - B의 문서에 본문이 없고 "보류 1건"이 있다.
  - B의 `xsm inbox`가 그 본문을 보여 주지 않는다.
  - B의 held 목록에 그 항목이 같은 이유로 있고, B의 에이전트가 `held deliver`를 하면 보인다.
- **SM-F2a:** A의 폴더에 미소비 답이 있는 채로 인수인계하면 B의 `question-status`가 `final`이고 답 1건이다. B가 A와 다른 저장소에 있고 D1 복사가 실패한 경우에도 같다.
- **SM-SEAM:** 보류되지 않았고 차단 목록에도 없는 A의 미소비 원문은, P↔B 범위가 없어도 B에게 전달된다. 근거가 없으면 표시가 붙는다. 인수인계 전체 과정에서 사람에게 묻는 것은 인수인계 승인 한 번뿐이다.
- **SM-F2b:** `_begin` 뒤에 도착한 답은 B로 가고 B의 질문 기록에 남는다.
- **SM-F3:** 묶음 조회 결과가 다음과 같다.
  - 답 1건이 온 묶음을 인수인계하면 B의 조회는 `reply_received`이고 답 1건이다.
  - 다 답한 묶음은 `final`이고 답 2건이다.
  - A가 인수인계 뒤에 새로 보낸 질문은 B의 `question-status`에서 `refused`다.
- **SM-F4:** P↔A 범위 근거가 A의 reach, worker 관계, 같은 폴더(B는 다른 폴더), link 밖일 때 다음이 모두 성립한다.
  - P의 늦은 답이 B의 질문 기록에 남는다.
  - 결과와 문서에 복사된 연결이 나열된다.
  - 복사가 실패한 연결은 건너뛰고 나열되며, 인수인계는 끝난다.
  - B가 얻는 범위는 A가 가졌던 범위를 넘지 않는다. A와 범위가 없던 세션 Q는 B와도 범위가 없다.
- **SM-F5:** 두 인수인계를 동시에 시작해도, 두 호출이 끝난 뒤 다음이 성립한다. 세 조합(A→B‖A→C, A→B‖B→A, A→B‖B→C)을 각각 시험한다.
  - 팀 자리, 질문 발신자, `follow(A)`가 같은 세션을 가리킨다.
  - 순환이 없다.
  - A→B‖B→C는 둘 다 성공해 A→B→C 사슬이 된다.
  - 거부되는 것은 이중 인수인계와 순환뿐이다. 거부 결과는 다음 행동을 담는다. 예: "A는 이미 B에게 넘어갔다. B를 C에게 넘기려면 B에서 실행하라."
- **SM-F5r:** `_begin` 뒤에 프로세스가 죽으면, 같은 대상으로 다시 실행해 끝낼 수 있다. `owner/B` 본문은 원래 내용이다. `xsm doctor`가 미완 인수인계를 보고한다.
- **SM-F6:** 인수인계 도중 팀장이 A를 팀에 넣거나 빼도, 팀 자리와 `owner/A` 항목이 같은 팀 집합에서 함께 옮겨진다. 빠진 팀에 B가 들어가지 않는다.
- **SM-F7:** 복사와 닫기 사이에 `owner/A`에 쓴 내용이 `owner/B`에 있다. 머리 둘인 항목의 이름이 결과의 `skipped`, 문서, `handover/A`에 나온다.
- **SM-F8:** 두 머신이 같은 generation으로 동시에 바꾼 뒤 기록을 주고받으면 다음이 성립한다.
  - 두 머신의 기록이 같다.
  - 인수인계로 빠진 A가 팀장으로 돌아오지 않는다.
  - 진 머신의 변경도 남는다.
  - 같은 기록의 에코가 generation을 올리지 않는다.
- **SM-F9:** 증언이 유실된 경우, 인수인계 뒤 질문, 사슬(A→B→C) 모두에서 B나 C의 답이 원격 질문자의 기록에 남는다. 발신자가 다시 보내지 않아도 된다.
  - 증언을 확인하지 못했으면 `unconfirmed` 표시로 남고, 증언이 오면 `confirmed`가 된다.
  - A와 다른 머신의 세션이 보낸 답은 지금처럼 기록되지 않는다.
- **SM-F10:** A가 읽지 않은 원격 질문에 B가 답장을 만들어 보낼 수 있다.
- **SM-F11:** `held deliver` 뒤에는 inbox, 이관, 인수인계 어느 경로에서도 같은 메시지가 다시 보류되거나 다시 보이지 않는다.
- **SM-F12:** 이관 커밋 직후 A의 게이트가 보류한 항목을 B의 에이전트가 `held deliver`로 풀 수 있다. 인수인계 뒤 A의 네이티브 대기 사본이 A의 게이트에 걸려도 A에 새 보류 항목이 생기지 않는다.
- **SM-F13:** 펜스로 handoff가 거부되면 발신자의 `ledger.status`가 `delivered`가 아니다.
- **SM-COMPAT:** 다음 두 호환이 유지된다.
  - 0.6.1 코드로 B의 `handoffs` 폴더를 읽어도 예외가 나지 않는다(인수인계로 옮긴 기록 포함).
  - `state` 필드가 없는 옛 `handovers/` 기록은 완료로 읽힌다.
- **SM-REG:** `python3 -m unittest discover -s tests` 전체가 통과한다.
- **SM-MODEL**(모델 확인이고, 코드 증거가 아니다): 수정 의미로 고친 모델에서 이번에 깨졌던 규칙이 지켜진다.

## 6. 경계 사례

- 원문 하나의 digest가 B의 같은 ID와 다르면 그 원문만 A에 두고, 문서와 결과에 적은 뒤 나머지를 진행한다.
- 복사할 연결 하나가 실패해도(폴더 없음 등) 인수인계는 계속한다. 실패한 연결은 문서에 적는다.
- 이관 중인 세션의 인수인계는 지금처럼 거부한다. 같은 세션에 이관과 인수인계가 겹치는 경우는 P1에서 잠금 순서로 다룬다. 이관 시작이 인수인계 잠금을 확인한다.
- succession 조회가 실패(머신 오프라인)하면 답은 `unconfirmed`로 기록된다. 거절로 끝나지 않는다.
- 다른 대상으로 새 인수인계를 요청했는데 `moving` 기록이 남아 있으면, 먼저 원래 대상으로 남은 단계를 자동으로 끝낸다. 그다음 새 요청은 일반 규칙(이중 인수인계)으로 판정하고, 다음 행동을 제시한다.

## 7. 제약

- C1·C2(INTENT): 런타임을 새로 두지 않고, 에이전트 CLI를 고치지 않는다.
- 제1원칙 P*(§0): 새 거부는 이중 인수인계와 순환뿐이다. 그 경우에도 다음 행동을 돌려준다. 확신이 없는 전달은 표시를 붙여 통과시킨다. 부분 실패는 건너뛰고 보고한다.
- 버전 혼합: 사용자 환경에는 여러 버전의 세션이 함께 떠 있다. 새 필드는 옛 코드가 무시할 수 있는 곳에만 둔다(`handover_history`, `pending_ops`, `acked_by`, `state`).
- 릴리스와 push는 사용자 승인 뒤에 한다.

## 8. 결정

| ID | 질문 | 결정 |
|---|---|---|
| D1 | P↔B 범위가 없을 때 인수인계로 넘어간 대화를 어떻게 할까 | **A의 연결을 B에게 복사한다**(사용자, 2026-11-25). 방법은 아래 D1 세부 |
| D2 | 보류된 메시지를 인수인계에서 어떻게 다룰까 | **B에게 보류째로 옮긴다**(사용자, 2026-11-25) |
| D3 | 두 머신이 같은 generation으로 팀을 동시에 바꾸면 | **머신 키로 정하고, 진 쪽이 자기 변경을 다시 적용한다**(사용자, 2026-11-25). 구조는 §3.4 |
| D4 | 미완 인수인계 | 단계 표지로 멱등하게 만든다. 같은 대상으로 다시 실행하거나 `xsm doctor`로 이어서 끝낸다 |
| D5 | 원격 증언 | 거절 시점에 조회(pull)한다. 유실, 인수인계 뒤 질문, 사슬을 하나의 장치로 덮는다. 조회가 실패하면 `unconfirmed`로 기록한다(P*) |
| D6 | 인수인계 결과 표현 | 형태 B. 원문 소유권 이전, 문서에는 건수·ID·건너뛴 것 |
| D7 | 동시 인수인계 잠금 | 머신 단위 대기식 잠금(30초)이다. 기다린 뒤 `_check`가 다시 판정하므로 결과가 순서와 무관하게 일관된다. 사슬(A→B‖B→C)은 둘 다 성공한다 |
| D8 | 인수인계 원문의 수신 판정 | A가 받았어야 할 메시지는 B에서 막지 않는다. 범위 근거가 없으면 표시해 전달한다. 보류는 D2를 유지하되, 범위 이유가 B에서 해소되면 자동으로 푼다(§3.3, P*) |

### D1 세부: 연결 종류별 복사 방법

"복사"는 A가 가졌던 범위를 B도 갖게 한다는 뜻이다. A의 범위는 그대로 둔다. B가 얻는 범위는 A가 가졌던 범위를 넘지 않는다.

| A의 연결 | 묶인 대상 | B에게 주는 것 |
|---|---|---|
| A가 가진 reach (`config.py:671`) | A의 실행 | 같은 root의 reach를 B의 실행(pid·lstart 포함)에 묶어 새로 만든다 |
| A의 폴더 범위: 같은 폴더·저장소(dir/repo), 그 폴더와 link된 폴더 | 폴더 | B가 그 폴더 밖에 있으면 각 폴더에 대한 reach를 B에게 준다. reach는 B 한 세션과 그 폴더의 세션들을 잇는다. A가 그 폴더 안에서 가졌던 범위와 같다 |
| worker·부모 관계 (`config.py:719`, `delegation.py`) | ref 쌍. 부모는 하나뿐이다 | 부모를 바꾸지 않는다. A를 부모로 둔 채 B와 그 worker(또는 A의 부모)를 `connect`와 같은 짝 팀(`pair-…`)으로 잇는다 |
| 팀·짝 팀 | 팀 기록 | 이미 `_teams`가 옮긴다 |

- 복사 목록은 승인 양식을 만들 때(`authorize`) 계산하고, 승인된 plan에 묶어 `hand_over`가 그대로 적용한다. 패턴은 `scope_service`의 plan→apply다.
- 첫 판에 있던 "대화 기록이 있는 상대로 한정"은 뺐다. ledger에 발신자 색인이 없어 계산할 수 없고, A의 연결은 상대와 무관하게 정의된다.

## 9. 가정(되돌릴 수 있음)

- 잠금 대기 30초: 인수인계 한 번은 로컬 파일 쓰기뿐이라 몇 초 안에 끝난다. 시험에서 넘치면 다시 본다.
- 음성 캐시 10분: 머신이 잠깐 꺼졌다 돌아오는 흔한 경우를 덮는다. 실사용에서 늦다는 보고가 오면 줄인다.

## 10. 열린 질문(P0에서 실측으로 닫는다)

- **Q1:** 인수인계 뒤 A의 네이티브 대기 사본(소켓·Codex 큐)이 A의 게이트에 걸리면 새 보류 항목이 생기는가(critic, 확신 낮음). 생기면 SM-F12 둘째 문장이 RED다.
- **Q2:** 사슬 A→B→C에서 두 증언이 다 도착하면 지금 코드의 `endpoint_succeeds`가 통과하는가(critic, 확신 중간). 통과하면 F9 사슬은 "증언이 안 감"만 원인이다.
- **Q3:** `migration_state.held`를 공용화할 때 이관 경로의 동작이 바뀌지 않는가. 이관 시험 전체로 확인한다.

## 11. 적대적 검토 반영

| critic 지적 | 반영 |
|---|---|
| #1 `transfer` 본문 공유가 `proves_copy`에 묶여 B 폴더 전체가 읽히지 않음, 옛 버전 B | 별도 `handover_history`, 증명 넷, SM-COMPAT(§3.2, §3.3) |
| #2 B 게이트의 범위 id 동일성 검사 | 인수인계 원문은 지금 범위로 판정(§3.3). SM-F2a에 "다른 저장소" 추가 |
| #3 `held/`와 레거시 내보내기 | `hand_to`가 레거시를 먼저 가져옴, `held.rebind` 공용화 |
| #4 재개 불가(보드 비멱등, `_check` 자기 거부, 읽는 곳 KeyError) | 단계 표지, `_begin`에 summary·plan 저장, 같은 대상 재진입, 읽는 곳은 `done`만 봄, doctor 재개, SM-F5r |
| #5 오래된 팀 목록 | 잠금 안 구성원 재확인(`migration_state.teams` 방식), SM-F6 보강 |
| #6 후임 읽기 허용의 시간 범위 | 읽기 규칙은 넓히지 않고 하위 질문을 옮김(§3.4), SM-F3 셋째 문장 |
| #7 D1 "복사"와 worker 이동, reach는 폴더 단위, ledger 색인 없음, plan 결속, 부분 실패 | D1 세부 다시 씀, 상대 한정 제거, plan→apply, 건너뛰기 |
| #8 D3 구조 없음, 에코 루프, 충돌 | `pending_ops`·`acked_by`·로컬 origin·에코 규칙·충돌 기록(§3.4), SM-F8 보강 |
| #9 D5 잠금 안 조회, 보관소, 폭주 | 잠금 밖 조회, 음성 캐시, 사슬 한 번 조회(§3.4). 보관소는 3판에서 `unconfirmed` 기록으로 바꿈(§12) |
| #10 단계 의존 모순, SM-TLC가 코드 증거 아님, 수 불일치, 잠금 종류 | F11·F12를 판별로 나눔, SM-MODEL로 이름 변경, 변이 확인 추가, 19개 설정·약 60개 시험으로 정정, D7 |
| #11 digest 충돌 시 전체 정지 | 그 원문만 A에 두고 진행(§6) |
| 경미한 것 | 이전 처리 안내, 이관 경로 영향 시험, 승인 문구·스키마 갱신, 잠금 순서(§3.3, §4) |

## 12. 제1원칙(P*) 적용으로 3판에서 바뀐 것

| 2판 | 3판 |
|---|---|
| B에서 범위가 없으면 옮겨진 원문을 보류 | 차단 목록만 막는다. 그 밖에는 표시를 붙여 전달한다. 범위 이유의 보류는 B에서 해소되면 자동으로 푼다 |
| 원격 증언 조회가 실패하면 답을 `pending-succession/`에 보관 | A와 같은 머신의 답은 `unconfirmed`로 바로 기록한다. 증언이 오면 확정한다. 보관소를 없앴다 |
| 다른 대상으로 재개하는 것을 거부 | 남은 단계를 원래 대상으로 자동 완료한 뒤, 새 요청을 판정한다 |
| 동시 인수인계 결과는 "거부 + 이유" | 사슬은 둘 다 성공한다. 거부는 이중 인수인계와 순환뿐이고, 다음 행동을 돌려준다 |
| (없음) | SM-SEAM: 인수인계에서 사람에게 묻는 것은 승인 한 번뿐이다 |

- **보안 경계를 낮춘 지점:** 같은 머신의 세션이 "A의 후임"이라며 보낸 답이, 증언 없이 질문 기록에 남을 수 있다(`unconfirmed` 표시). 이는 P*에 따라 사용자가 고른 절충이다.
- **보안 경계를 지키는 지점:** 다른 머신 세션의 답은 지금처럼 거부한다.

## 13. 확대 점검(zoom-out)

- **겹침:** 원문 복사(`transfer`), 보류 재결속(`migration_state.held`), 구성원 재확인(`migration_state.teams`), plan→apply(`scope_service`)를 공용으로 뽑아 쓴다. 이관과 인수인계가 같은 부품을 쓴다.
- **층:** 다음처럼 나눈다.
  - 원문 소유권: `handoff`
  - 보류: `held`(공용으로 뽑음)
  - 주소와 순서: `handover`
  - 수신 판정: `receive.check`
  - 머신 간 기록: `team_sync`·`network_messages`
- **과함:** 다음은 넣지 않는다. 지금 결함에 필요하지 않다.
  - 머신 간 분산 잠금. 인수인계 대상은 이 머신의 세션으로 제한되어 있다.
  - 팀 기록의 일반 CRDT. 연산 넷이면 된다.
  - 후임 읽기 규칙의 일반화.
