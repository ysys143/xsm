# A16-08 실제 missing 3셀 묶음

판정: 부분 충족 / 실패 항목 존재. 실제 모델 턴 12/12 (actor 2, owned 10).

## 실제 결과

| 검사 | 결과 |
|---|---|
| frozen_source_unchanged | PASS |
| profile_config_unchanged | PARTIAL |
| harness_completed_without_error | PASS |
| actual_actor_A | PASS |
| actual_actor_B | PASS |
| two_distinct_actual_actor_ids | PASS |
| native_one_turn_memory-A-first | PASS |
| default_permission_memory-A-first | PASS |
| native_one_turn_memory-B-first | PASS |
| default_permission_memory-B-first | PASS |
| native_one_turn_memory-A-follow | PASS |
| default_permission_memory-A-follow | PASS |
| native_one_turn_memory-B-follow | PASS |
| default_permission_memory-B-follow | PASS |
| native_one_turn_memory-A-after-retire | PASS |
| default_permission_memory-A-after-retire | PASS |
| native_one_turn_capacity-0 | PASS |
| default_permission_capacity-0 | PASS |
| native_one_turn_capacity-1 | PASS |
| default_permission_capacity-1 | PASS |
| native_one_turn_capacity-2 | PASS |
| default_permission_capacity-2 | PASS |
| native_one_turn_capacity-3 | PASS |
| default_permission_capacity-3 | PASS |
| native_one_turn_capacity-new-sender-5 | PASS |
| default_permission_capacity-new-sender-5 | PASS |
| sender_A_remembers_own_secret | PASS |
| sender_A_same_native_followup | PASS |
| sender_A_followup_no_token_reinjection | PASS |
| sender_B_remembers_own_secret | PASS |
| sender_B_same_native_followup | PASS |
| sender_B_followup_no_token_reinjection | PASS |
| same_work_across_actual_senders | PASS |
| sender_contexts_distinct | PASS |
| same_logical_worker | PASS |
| actual_shell_serial_admission | PASS |
| same_id_body_digest_after_serial_queue | PASS |
| same_context_execution_serialized | PASS |
| two_sender_concurrent_children | PASS |
| retired_old_context | PASS |
| fresh_native_after_retirement | PASS |
| native_reports_unknown_after_retirement | PASS |
| retirement_probe_no_tools | PASS |
| retirement_probe_no_secret_reinjection | PASS |
| four_busy_at_admission | PASS |
| new_sender_different_from_all_busy | PASS |
| fifth_queued_not_executed_or_success | PASS |
| same_id_body_sender_context_after_capacity_queue | PASS |
| fifth_eventually_real_reply | PASS |
| native_budget_at_most_12 | PASS |
| no_automatic_model_retries | PASS |

## 실행 조건·미확대 범위

- Python controller delegated requests using actual live native actor records; no synthetic actor ID/upsert.
- Actual shell CLI exercised create and run queued/context-busy/overloaded. Native execution after those queues used Python default executor and quiet public publish callback, not a shell-only end-to-end run.
- MCP profile settings were not injected. This private git/state condition does not prove default installation/Claude reply.
- New capacity sender B differs from all four currently busy A requests; B already participated in the memory cell.
- Prior capacity fifth same sender/different work remains a limitation of that prior sample.
- No ACK calls or request/body/outcome corrections; queued original IDs resumed once admission allowed.
- No independent=True native review was added; prior deterministic fixture evidence remains separate.
- Profile config.toml hash changed during execution. Native recorded tools and harness contain no direct profile edit, but writer/changed keys and semantic permission equivalence are unknown. No restore or additional experiment was attempted.

고정본 source 315개 hash는 실행 전후 동일하다. 그러나 profile config.toml hash는 실행 도중 달라져 무변경 조건은 PARTIAL이다. 기록된 native 도구는 actor bridge와 sleep뿐이고 harness에도 profile 직접 쓰기가 없지만, 변경 주체·키와 의미상 권한 동일성은 확인하지 못했다. 프로필을 되돌리거나 추가 실험하지 않았다. raw native 출력은 raw/에 그대로 복사하고 journal·전송 정본은 private 경로/hash로 결속했다. 제품·plan·ledger와 credential/권한/설치에 대한 직접 변경은 하지 않았다.

## 실제 요청별 관측

| ID | sender ID | native ID | 결과 |
|---|---|---|
| memory-A-first | 01a1850e-0d38-79f1-b0d7-2becfe1fa5a9 | 01a1850e-2b4b-7590-9fd8-643aaa25030a | secret-9aa5e7cbbffd4978a69475399f21fd77 |
| memory-B-first | 01a1850e-0d38-7092-ad27-419acfe92d10 | 01a1850e-2b65-7351-ba76-2b99fd1b6b40 | secret-6316a25c8c7147cf9669b0f3007c8a60 |
| memory-A-follow | 01a1850e-0d38-79f1-b0d7-2becfe1fa5a9 | 01a1850e-2b4b-7590-9fd8-643aaa25030a | secret-9aa5e7cbbffd4978a69475399f21fd77 |
| memory-B-follow | 01a1850e-0d38-7092-ad27-419acfe92d10 | 01a1850e-2b65-7351-ba76-2b99fd1b6b40 | secret-6316a25c8c7147cf9669b0f3007c8a60 |
| memory-A-after-retire | 01a1850e-0d38-79f1-b0d7-2becfe1fa5a9 | 01a1850e-abb9-7b92-ba5a-3e024102761d | UNKNOWN |
| capacity-0 | 01a1850e-0d38-79f1-b0d7-2becfe1fa5a9 | 01a1850e-c434-7352-ab4f-809e95bb5235 | capacity-done |
| capacity-1 | 01a1850e-0d38-79f1-b0d7-2becfe1fa5a9 | 01a1850e-c43c-7281-8c90-5a3bf0b34bff | capacity-done |
| capacity-2 | 01a1850e-0d38-79f1-b0d7-2becfe1fa5a9 | 01a1850e-c468-7842-8e4b-7b8f98e4de6f | capacity-done |
| capacity-3 | 01a1850e-0d38-79f1-b0d7-2becfe1fa5a9 | 01a1850e-c463-7f11-9564-c3e1d9432a64 | capacity-done |
| capacity-new-sender-5 | 01a1850e-0d38-7092-ad27-419acfe92d10 | 01a1850f-49b1-7560-8d6f-c51a5ddd6366 | capacity-done |

정확한 raw 경로·SHA256·입력/결과 대조는 check.json의 files/details와 results.json에 있다. 이 묶음 뒤 추가 실험은 하지 않았다.
