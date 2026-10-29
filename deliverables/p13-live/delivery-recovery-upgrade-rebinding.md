# 전달·회수·업그레이드 재결속

A18-01·A18-02·A23-08은 기존 증거를 수준별로 결합해 원 criterion 종결이 가능하다.
전체 하위 사례의 native 반복이나 전체 구버전 전수는 조건으로 추가하지 않았다. ledger 18 proven 및 gate 상태는 수정하지 않았다.

## 조사 범위와 기준

10분 상한 중 569.829초를 사용했다. frontier 원문/positive/negative/evidence_levels, 현재 v2 1700개 양 Python OK, 지정 fixture/process selector, 실제 typed fallback·factory 종료 회수 ACK·old native upgrade의 원 raw와 source만 조사했다. 추가 모델·실험·테스트·script 실행은 없다.

| 조건 | 판정 | 실제 남은 필수 셀 |
|---|---|---|
| A18-01 | criterion-closeable-by-bound-level-combination | 확인 범위 내 없음 |
| A18-02 | criterion-closeable-by-bound-level-combination | 확인 범위 내 없음 |
| A23-08 | criterion-closeable-by-bound-level-combination | 확인 범위 내 없음 |

## A18-01

queue 실행 실패·소켓 쓰기 성공 뒤 수신 실패를 주입하면 런타임 도달 성공으로 보고하지 않는다.

- positive: queue 실패·소켓 write 후 수신 실패에서 legacy status와 새 evidence 대조
- negative: send 접수 또는 static capability만으로 runtime-confirmed 생성
- evidence_levels: fixture, subprocess, harness

- fixture: DeliveryEvidenceTest: queue error has queued=false/runtime_reached=false; socket write only remains sent-unconfirmed; wrong error/-32600/permission fallback refusals preserved.
- subprocess: TwoMachinesTest uses real separate Python receiver/fake SSH and real AF_UNIX frames; forged/unrecorded receiver ID is blocked. LostAnswer receiving-machine no-receipt case is an in-process fault fixture, not relabeled process.
- harness: different-parent actual native 8 typed unsupported-capability queue failures retain queued=false/runtime_reached=false and immutable ID; actual MCP fallback claim/ACK is real. This is not an induced physical-Claude-socket failure.

한계:
- No actual physical-Claude-socket receive failure injection in native run; socket semantics covered by fixture/process and actual native queue failure separately.

## A18-02

확인 직전 수신 클라이언트 종료와 대기 취소를 재현해 미독을 회수한다. 정상 확인 뒤 같은 메시지가 반복 실행되지 않는지도 별도로 확인한다.

- positive: claim 전후·stdout 전후 종료/cancel/ack 유실 후 회수와 정상 중복 억제
- negative: 인계 전 사본 삭제 또는 정상 ack 뒤 동일 작업 반복
- evidence_levels: fixture, subprocess, harness

- fixture: claim release/cancel returns original body; wrong home/generation/token refuses ACK; ACK suppresses subsequent claim.
- subprocess: real stdio notifications/cancelled while ask waits; late reply recovered; real SIGKILL after claim/before output and ACK lost-response preserve ID and suppress duplicate.
- harness: factory actual claim response withheld0byte, client killed, sameCID fresh native generation owner-dead recovery, actual ACK/correlated reply and post-ACK empty inbox. Native cancel notifications=0 remains a scope limitation, not a new mandatory every-subcase native requirement.

한계:
- Native cancel notification count0; fixture and actual stdio cancellation already exercised. Initial active-writer refusal/observer tail race/profile drift remain.

## A23-08

이전 버전의 MCP·소켓을 사용하는 세션을 유지한 채 상태 위치와 어댑터를 업그레이드한다. 마이그레이션 중 실패하면 이전 경로가 계속 읽히고 사용자 설정이 보존되는지 확인한다.

- positive: 구 MCP/socket/hook 실행 중 상태/adapter 이동과 중간 실패·old reader 롤백
- negative: 살아 있는 구 snapshot 제거·미완 claim 삭제·설정 후속 수정 유실
- evidence_levels: fixture, subprocess, harness

- fixture: interrupted copy and metadata publish failure preserve old CURRENT/LINK/runtime, corrupt active snapshot not overwritten; CAS user followup/replaced flow preserve settings.
- subprocess: live old separate Python reader survives real CLI upgrade/prune, AF_UNIX listener remains; failed CLI upgrade keeps old snapshot/flow; old inbox reader import retains originals. This is owned fixture process, not native Claude.
- harness: old native CID and MCP PID/generation remain live across private CURRENT switch/prune and two actual correlated replies; old runtime/settings preserved. new-prefix quiet reply is additional only; no native failure migration or all-old-version matrix claimed.

한계:
- Not every old version/runtime; old MCP native and socket fixture are distinct levels. New-prefix final native turn incomplete; not used for old-runtime completion.

## 구체 실행·반례 결속

| 기준 | selector | 두 현재 full 로그 |
|---|---|---|
| A18-01 | `tests.test_xsm.DeliveryEvidenceTest.test_a_queue_failure_is_not_a_runtime_reach` | 양쪽 ok |
| A18-01 | `tests.test_xsm.DeliveryEvidenceTest.test_a_socket_write_alone_is_not_a_runtime_reach` | 양쪽 ok |
| A18-01 | `tests.test_remote.LostAnswerTest.test_the_receiving_machine_does_not_call_a_stored_frame_reached` | 양쪽 ok |
| A18-01 | `tests.test_remote.TwoMachinesTest.test_pair_send_gate_and_reply_across_machines` | 양쪽 ok |
| A18-01 | `tests.test_remote.LostAnswerTest.test_a_peer_that_stored_it_but_never_handed_it_over_is_not_reached` | 양쪽 ok |
| A18-01 | `tests.test_subagent_transport.SubagentTransportTest.test_fallback_preserves_full_request_and_honest_evidence` | 양쪽 ok |
| A18-01 | `tests.test_subagent_transport.SubagentTransportTest.test_no_broad_error_fallback` | 양쪽 ok |
| A18-01 | `tests.test_subagent_transport.SubagentTransportTest.test_string_reason_alone_and_non_codex_cannot_select_fallback` | 양쪽 ok |
| A18-01 | `tests.test_subagent_transport.SubagentTransportTest.test_real_queue_with_not_loaded_wake_stays_native_unconfirmed` | 양쪽 ok |
| A18-02 | `tests.test_handoff_consumer.HandoffConsumerTest.test_actual_send_legacy_export_claim_cancel_recover_and_explicit_ack` | 양쪽 ok |
| A18-02 | `tests.test_handoff_consumer.HandoffConsumerTest.test_sigkill_after_actual_consumer_handoff_before_output_recovers_same_id` | 양쪽 ok |
| A18-02 | `tests.test_handoff_consumer.HandoffConsumerTest.test_batch_output_cancel_releases_all_unreturned_claims` | 양쪽 ok |
| A18-02 | `tests.test_handoff_crash.HandoffCrashTest.test_sigkill_after_claim_commit_recovers_dead_owner_and_invalidates_old_token` | 양쪽 ok |
| A18-02 | `tests.test_handoff_crash.HandoffCrashTest.test_sigkill_after_ack_commit_lost_response_readback_suppresses_duplicate` | 양쪽 ok |
| A18-02 | `tests.test_mcp_wait_process.McpWaitProcessTest.test_ping_cancel_lost_auto_id_and_late_reply_keep_inbox_and_request` | 양쪽 ok |
| A18-02 | `tests.test_question_interfaces.QuestionInterfacesTest.test_mcp_answer_cancel_or_output_failure_releases_its_handoff_call` | 양쪽 ok |
| A23-08 | `tests.test_install_safety.InstallerSafetyTest.test_interrupted_copy_preserves_old_reader_pointer_and_metadata` | 양쪽 ok |
| A23-08 | `tests.test_install_safety.InstallerSafetyTest.test_metadata_publish_failure_restores_only_our_pointer_and_retains_old_runtime` | 양쪽 ok |
| A23-08 | `tests.test_install_safety.InstallerSafetyTest.test_live_old_reader_survives_upgrade_and_prune_and_can_read_again` | 양쪽 ok |
| A23-08 | `tests.test_install_safety.InstallerSafetyTest.test_active_corrupt_snapshot_is_preserved_instead_of_deleted_or_replaced` | 양쪽 ok |
| A23-08 | `tests.test_install_cli_flow.InstallCliFlowTest.test_cli_failed_upgrade_keeps_old_snapshot_and_flow_id` | 양쪽 ok |
| A23-08 | `tests.test_install_cli_flow.InstallCliFlowTest.test_cli_cas_preserves_user_followup` | 양쪽 ok |
| A23-08 | `tests.test_install_cli_flow.InstallCliFlowTest.test_cli_replaced_flow_cannot_write_old_settings_or_completion` | 양쪽 ok |
| A23-08 | `tests.test_install_cli_flow.InstallCliFlowTest.test_actual_cli_upgrade_preserves_live_reader_and_reports_only_passive_observations` | 양쪽 ok |
| A23-08 | `tests.test_handoff_consumer.HandoffConsumerTest.test_old_taking_is_imported_and_legacy_original_is_preserved` | 양쪽 ok |

A18-01의 socket write 단독 fixture와 receiving-machine no-receipt fixture를 실제 native 실패라고 바꿔 부르지 않았다. 실제 native 근거는 typed -32600 queue 실패 8건이며 원 ledger의 queued=false/runtime_reached=false와 canonical MCP claim/ACK를 각각 대조했다. 별도 process는 실제 Python/SSH fixture·AF_UNIX frame이다.

A18-02의 notifications/cancelled는 실제 별도 stdio process에서 재현됐고, native client 종료/동일 CID 새 세대 회수/ACK 후 빈 inbox는 별도 실제 native 표본이다. native cancel0을 사실대로 남기되 원문에 없는 모든 사례 native 교차곱을 추가하지 않았다. ACK 후 중복 claim 억제와 lost-response/SIGKILL 반례도 현재 full에 있다.

A23-08은 old native/MCP 동일 세대 유지·CURRENT 교체/prune·두 상관 회신을 실제 하네스로 확인했다. 실제 old reader/socket 보존과 실패·사용자 후속 설정 보존은 현재 fixture/별도 process로 확인했다. old inbox reader 유지도 따로 결속했다. 새 prefix의 최종 turn 미관측을 old native 완료로 사용하지 않는다.

## Raw와 source의 현재 결속

- `deliverables/p13-live/native-handoff-factory-20261029-7091030d/manifest.json`: 95/95 hash 일치, 불일치 0개.
- `deliverables/p13-live/different-parent-native-20261029-5564a814/manifest.json`: 168/168 hash 일치, 불일치 0개.

| 실제 실행 epoch | 파일·함수 | v2/current AST 동일 |
|---|---|---|
| fallback | `xsm/adapters.py:143 to_codex` | True |
| fallback | `xsm/send.py:83 send` | True |
| fallback | `xsm/ledger.py:194 evidence_of` | True |
| fallback | `xsm/ledger.py:145 step` | True |
| factory | `xsm/handoff.py:308 claim` | True |
| factory | `xsm/handoff.py:384 recover` | True |
| factory | `xsm/handoff.py:374 ack` | True |
| factory | `xsm/handoff.py:369 handoff` | True |
| factory | `xsm/handoff.py:379 release` | True |
| factory | `xsm/receive.py:1090 take_inbox_claims` | False |
| factory | `xsm/receive.py:1273 ack_inbox` | True |
| factory | `xsm/receive.py:1284 release_inbox` | True |
| upgrade_new | `xsm/install.py:912 make_snapshot` | True |
| upgrade_new | `xsm/install.py:1089 prune_snapshots` | True |
| upgrade_new | `xsm/install.py:1041 _running_from` | True |
| upgrade_new | `xsm/install.py:174 _cas_bytes` | True |

factory의 take_inbox_claims만 passive_only/wake=True일 때 mcp-inbox route를 예외로 허용하는 후속 차이가 있다. claim/recover/ACK/release의 AST는 동일하다. 이 차이는 현재 fallback selector와 더 최신 different-parent 실제 native fallback으로 결속했으며 factory 파일 전체가 같다고 주장하지 않는다. upgrade 핵심 4함수와 최신 typed fallback 전송 함수도 동일하다.

정확한 raw 경로·SHA256·selector 행·각 full 로그의 실제 ok 행은 JSON의 evidence_files/selectors에 있다. prior factory의 writer-unknown profile drift·active-writer resume 거절·observer tail race를 지우지 않았고, 원 성공 셀을 취소하지도 않았다. 현재 raw를 새 native 실행으로 계산하지 않았다.

이 판정은 세 원 criterion의 재결속 제안이다. ledger/gate/제품/plan/기존 artifact는 수정하지 않았으며 전체 제품 완료나 환경 전수 성공을 선언하지 않는다.

verbose docstring selector 한 건은 이름 행 다음의 설명 행에 `... ok`가 출력돼 두 행을 함께 결속했다. 테스트나 원 로그는 다시 실행·수정하지 않았다. 종료 시 사용한 증거 318개 hash도 다시 일치했다.
