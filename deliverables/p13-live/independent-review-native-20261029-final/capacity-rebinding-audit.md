# Capacity journal version rebinding 감사

원 capacity 기능 증거는 기존 request subset 대조로 복구 가능하다. 기존 10개 request의 영속 필드 22개씩이 당시 result snapshot과 전부 같고, 불변 native raw·기존 checker 결과와도 일치한다. 과거 journal 전체 SHA256 일치나 파일 복원은 주장하지 않는다.

## 실제 해시 차이와 영향 범위

- 원 journal: `/private/tmp/owned-capacity-native-rvvg7uo2/state/owned-requests/db471226f6af0464a223087039c0fa701a54fe8c9578572501fed294c66635a5.json`
- 당시 전체 SHA256: `44410d0ba7a1acd4b4541bf8b7429e584d405f284947edd2cd1c776ecdf0544b` (58833 bytes)
- 현재 전체 SHA256: `3c8fd210913093bbd3b3841d3e48b5c02980c67f07e3e36408ef09e07f458e6f` (77861 bytes)
- 원 capacity 79개 중 이 journal 1개 불일치, 나머지 78개 일치. independent 36개는 모두 일치한다.
- 같은 own state를 후속 단계에서 재사용한 것이 version 경계다. “행정 미승격”으로 처리하거나 기존 manifest/check를 고쳐 해시 차이를 숨기지 않았다.

## 과거 snapshot 검색

own fixture root와 두 산출물 디렉터리의 파일 220개를 확인하고 과거 크기 58833 bytes 후보를 hash 대조했다. 원 SHA와 같은 journal snapshot은 찾지 못했다. 전역 filesystem 전체에 snapshot이 없다고 주장하는 조사는 아니다. journal을 재구성·복원·덮어쓰기 하지 않았다.

## 기존 request 직접 결속

당시 result snapshot은 `_view` 출력이며 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/owned_requests.py:106`에 따라 request를 deepcopy하고 state를 status로 표시한 뒤 context·persisted·accepted·side_effects_exactly_once·slot_occupied 등의 파생 필드를 붙인다. 이 파생 필드만 비교에서 분리하고 status/state 이름을 맞춰 기존 영속 필드 전체를 대조했다. 원본 snapshot·journal의 값은 수정하지 않았다.

| 기존 request | 비교한 영속 필드 | 바뀐 필드 | snapshot projection / 현재 항목 canonical SHA256 |
|---|---:|---|---|
| capacity-0 | 22 | 없음 | `db5e297fca6107acaceb9f4e73633890b1b601d3ba3f07ffd038182f0d4b5045` |
| capacity-1 | 22 | 없음 | `db68bd4ad5007bfea4a6d59420f2f22d1cc92d3e036425d7596ddbe7e82b6741` |
| capacity-2 | 22 | 없음 | `3f512e4a1d6e8d633125cb44c7d85da3b891d48e6d0e55aa1bdc9fcf9d987d85` |
| capacity-3 | 22 | 없음 | `05a29bc0914b8ab94bd78ed93dab07dc8ac7f56d0a805e4c890f355df054207a` |
| capacity-new-sender-5 | 22 | 없음 | `c1a69e9fe5c980ad8325f7c05eb3f38cb9acdc0b9a42f672ae5a847ee335fad3` |
| memory-A-after-retire | 22 | 없음 | `1ad928f3c971ce2ba32441cd903506b7a3a90ece5e57f78d3dae1afcdde8b7bf` |
| memory-A-first | 22 | 없음 | `5cafa6df2894614129b9a89f77573e78122099ca7a73e204f1eab53730f25dec` |
| memory-A-follow | 22 | 없음 | `aeaa7d8d346a63c11e70ea02ff98c24f4060efa4eb725942122bc7ddf6353933` |
| memory-B-first | 22 | 없음 | `0bf8fc2f4210193bbde1c3a3499f64516533d74a30d0e87b213e7db4d557913a` |
| memory-B-follow | 22 | 없음 | `8d53b70c79a14b550d7c031a4fef491e69f452fc168bd221ef33c26b9b584401` |

10개 subset의 당시 snapshot projection digest와 현재 digest는 모두 `31f3632086bdd806fa1a7cc680870a50211cbc924f793daa90443a9310792d0c`다. 이 digest는 JSON 의미의 비교용이며 과거 journal 파일 전체 byte SHA가 아니다.

본문·native sender/owner·work·context ID·예약/실행/전송 필드·events·reply ID·result digest·실제 result/argv/PID/lstart까지 22개 전체가 같다. 기존 request 항목의 변경은 발견되지 않았다. 별도로 각 result의 원 native stdout hash와 terminal 응답·outcome·CID, 기존 checker의 events/실행/회신 결과를 다시 대조했다.

## Context와 새 단계 분리

capacity 당시 context는 8개이며, 현 journal에서는 2개가 늘어 10개다. 기존 8개의 지원되는 단계말 필드는 일치한다. memory A의 옛 context에서 result snapshot의 retired=false와 현재 true가 다른 것은 capacity 자체의 명시 retirement 전/후 차이다. 당시 capacity check의 retired_old_context=true가 이미 이를 확인했으므로 independent 단계가 바꾼 것으로 분류하지 않았다. 이 역사적 판단을 원 snapshot 수정으로 표현하지 않는다.

추가 request는 아래 3개이며, 각각 independent의 실제 result snapshot/36개 결속과 일치한다. 새 context 2개는 normal 재사용 단위와 independent 단위다. 이 추가분을 원 capacity journal의 원래 내용으로 소급 포함하지 않는다.

- `ir-054fbd75-independent-review`
- `ir-054fbd75-normal-first`
- `ir-054fbd75-normal-followup`

추가 context:
- `375436d2ed8c92347ef4d796d263deb916d70af60b12429db29a676a7d945398`
- `9cd054d18d1f662af2630772d8eef303f6852b223e5b68d0f553c3b0fa8a084d`

## Header의 확인 범위

현재 header 키는 version/owner/slots다. owner는 기존 10개 snapshot의 owner와 당시 worker parent_native에 일치한다. version=1은 보존 source의 schema와 일치한다. 하지만 과거 전체 journal/header snapshot이 없으므로 header 키 전수·slots의 당시 byte 값까지 불변이라고 인증할 수 없다. 이 한계는 기존 request 10개의 완전한 필드 일치와 별도로 남긴다.

## 기능 증거 재판정

| 검사 | 결과 |
|---|---|
| A_own_memory_preserved | PASS |
| A_followup_without_reinjection | PASS |
| B_own_memory_preserved | PASS |
| B_followup_without_reinjection | PASS |
| two_real_actor_contexts_distinct | PASS |
| two_sender_running_overlap | PASS |
| same_context_queued_then_serial | PASS |
| retirement_unknown_new_native_old_context_retired | PASS |
| four_busy_new_sender_queued_without_execution | PASS |
| capacity_same_id_digest_body_sender_actual_recovery | PASS |
| all_ten_requests_unchanged_22_fields_each | PASS |
| all_eight_capacity_end_contexts_supported | PASS |
| new_stage_exactly_three_requests_two_contexts | PASS |
| original_cap_behavior_checks_were_pass | PASS |

동일 sender별 표식 기억·두 sender 문맥 분리/동시성·동일 문맥 직렬화·retirement 후 UNKNOWN·4busy의 다른 sender 보류와 같은 ID 회수는 기존 불변 raw 및 변경 없는 request subset으로 다시 결속됐다. 기존 request 필드가 하나라도 달랐다면 partial로 분류했을 것이며 이번 대조에서는 220개 필드가 모두 일치했다.

## 보존 및 종결

이전 profile drift, CLI queued 진입/quiet publication 조건, independent 최초 harness PID 비교 오류 및 result-ready 회신 한계를 바꾸지 않았다. 과거 전체 journal SHA는 여전히 불일치이며, 이 별도 감사는 기능 증거의 version-aware 재결속이지 원 manifest를 통과로 재발행한 것이 아니다.

기존 산출물 68개 byte hash와 현재 journal hash를 감사 전후 확인했다. 새 모델·추가 실험·원정본 복원/덮어쓰기·기존 report/manifest/check·product/ledger/plan 수정 없이 이 JSON/MD 두 파일만 작성했다.
