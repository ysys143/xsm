# 정책·호환성 네 후보의 읽기 전용 재결속

**이번 확인 범위에서 전체 조건 완료 가능한 항목은 0개다.** A16-07·A22-02·A23-05는 원 수준의 evidence cell을 재결속할 수 있지만 formal G07/G12를 통과시키지 않았다. A19-04는 gate 외에도 원 conditional 경계를 직접 보여주는 native 근거가 부분이다. ledger의 proven 18개는 변경하지 않았다.

| 조건 | cell 판정 | 전체 조건 | 남은 것 |
|---|---|---|---|
| A16-07 | fixture·process·native 충족 범위 결속 | partial: gateblocked | G07. 모든 취소/부분/final 경쟁 조합을 native·실제 UI에서 반복하는 새 의무는 추가하지 않음 |
| A19-04 | fixture 충족, native 부분 | partial: 증거+gateblocked | G12 및 capability/구버전/본문 대체 경계 중 하나의 직접 native trace 미확인. 모든 음성의 native 행렬 요구가 아님 |
| A22-02 | fixture·현재 source 읽기 전용 review 결속 | partial: gateblocked | G07. fixture+review 요구를 실제 승인 UI/native 전수로 늘리지 않음 |
| A23-05 | fixture·process·현재 source 읽기 전용 review 결속 | partial: gateblocked | G12. 실제 publisher 서명 검증/P12 선택을 완료한 것으로 만들지 않음 |

## 기준과 조사 범위

처음 `remaining-execution-frontier.json`의 지정 네 row와 required_levels·gateblocked·next_readonly_binding을 읽었다. frontier에 없는 positive/negative/evidence_levels 원문은 현재 plan의 동일 ID에서 읽어 [JSON](policy-compatibility-rebinding.json)에 원문과 SHA로 저장했다. 원 기록의 “native 모든 조합·장시간·원격 전수” gap은 그대로 새 기준으로 채택하지 않았다.

조사는 지정 네 조건, 현재 고정본 selector·기존 1700 verbose 로그, 이미 보존된 raw/manifest 및 관련 source review까지만 한정해 마감했다. 새 모델·실험·fixture/process/제품 실행·script/plan/ledger 수정은 0이다. 산출물은 요청된 JSON과 이 MD뿐이다. 추가 범위를 조사하며 계속하지 않았다.

현재 기준은 `/private/tmp/xsm-doctor-privacy-v2-frozen-i7xbamec`다. 135 primary의 현재/고정본/manifest hash가 모두 일치했고, 두 Python의 1700/OK·exit0·로그 SHA를 재대조했다. 테스트 24개 selector마다 정확한 클래스/메서드, source/AST SHA, 각 verbose 로그의 실제 `ok` line/line SHA를 결속했다. 이번에 검사를 재실행한 것이 아니다.

관련 제품 함수의 AST도 이전 receipt315와 일치함을 확인했다. install.py 전체 파일은 doctor 수정으로 달라도 이번 supply/snapshot/CAS 함수 AST가 같은 것은 별도로 확인했다. 원 epoch나 원 실행을 현재 1700 실행으로 바꿔 쓰지 않는다.

## A16-07 — 대기 종료·동시/부분 회신·ID 분배

원 positive는 timeout/cancel/여러 부분 reply/동시 final/양식 중 tool 호출의 ID 분배, negative는 입력 유실·교차 caller·대기 취소를 task 취소/재실행으로 바꾸는 것이다.

- **Fixture:** `test_timeout_cancel_keep_index_and_inbox_then_late_answer`, `test_parts_dedup_conflict_and_explicit_final`, `test_concurrent_reply_file_updates_no_lost_parts`, `test_concurrent_same_request_has_one_send`를 현재 1700 양쪽 로그에 대조했다. cancel/timeout 뒤 원 질문·inbox 유지, 부분 회신 중복/충돌 구분, 32 reply 동시 저장 무손실, 같은 요청 12회 경쟁의 실제 send1을 검사한다.
- **Process:** `test_ping_cancel_lost_auto_id_and_late_reply_keep_inbox_and_request`는 실제 MCP stdio process에 ping/cancel/tools-call을 보낸다. 취소 응답의 auto ID를 버린 클라이언트처럼 ID 없는 owner 목록에서 회수하고, 실제 service reply→status→ACK 뒤 peer inbox가 1개여서 task 재실행이 아님을 확인한다. transport는 fixture이며 구독 native 모델이라고 표시하지 않는다.
- **Form/reentrancy fixture:** `test_nested_forms_route_out_of_order_replies_to_their_own_caller`, `test_cancelled_form_does_not_apply_a_late_yes_and_next_tool_still_runs`, `test_nested_calls_do_not_inherit_another_callers_consent_globals`가 out-of-order ID·late yes·후속 호출·caller 전역 복원 반례다. 실제 사람이 본 UI 검사가 아니다.
- **Native:** 기존 different-parent의 원 요청 `11f8150b86184fc2`에서 outcome 없는 부분 reply와 succeeded final reply가 같은 원 ID에 결속됐다. question record와 두 canonical reply의 원 SHA를 기존 manifest와 대조했고, 실제 반환 body 및 reply_to·ACK도 일치했다. 경로·SHA·reply ID는 JSON에 있다.

취소/경쟁의 모든 하위 항목을 모든 native에서 다시 실행해야 한다는 문장은 원문에 없다. 실제 부분/final native와 정확한 fixture/process 범위를 합쳐 cell을 결속한다. 실제 UI cancel notification이 있었다고 쓰지는 않으며, **G07 formal gate는 그대로 미통과**다.

## A19-04 — capability·구버전·본문 한도

현재 fixture는 원 negative를 구체적으로 검사한다.

- `test_unknown_unsupported_and_old_capabilities_never_automatically_fallback`: unknown/미광고/unsupported/version0·bool version 거절, 자동 fallback 없음.
- `test_explicit_inline_fallback_is_complete_and_requires_new_body_binding`: 명시 inline만 전체 원문/사본 digest를 포함해 새 body binding. inline 한도 10 bytes 초과와 binary는 거절한다.
- `test_explicit_count_size_and_quota_limits_fail_without_partial_delivery`: 파일/개수/합계/quota 한도 실패 뒤 partial incoming이 없고 저장 성공을 주장하지 않는다.
- `test_unknown_peer_requires_explicit_fallback_and_reports_recovery_id`: 미지원에서 body_sent=false와 원 request/manifest 회수 ID를 반환한 뒤 명시 fallback으로 진행한다.
- `test_capability_downgrade_keeps_previously_received_copies_readable`: 능력 하향으로 기존 사본 읽기까지 지우지 않는다.

실제 Codex 두 홈·Claude의 첨부 읽기/회신, 최신 material-boundary의 세 사본 content/SHA·ACK는 **정상 전달의 무누락** 근거다. 그러나 이 native MCP의 `name+text` caller-inline 입력은 **capability 미지원 시 본문 inline fallback**과 다르다. 실제 old-MCP upgrade의 일반 body 왕복도 첨부 negotiation의 거절/대체 증거는 아니다.

따라서 fixture는 충족하며 native는 정상 무누락까지의 부분 근거로 남긴다. 확인 범위에서 원 조건의 capability/구버전/본문 대체 경계를 직접 관측한 native trace는 찾지 못했다. 세 음성 각각을 native로 반복하거나 원격 모든 버전 행렬을 추가 요구하지 않는다. **G12와 이 증거 공백은 별개**다.

## A22-02 — 실제 다른 승인 vs peer 주장

원 수준은 **fixture+review**이며 native/UI가 아니다.

현재 `provenance.render_peer`는 peer의 source/approval/permission 키를 구조 입력으로 쓰지 않고, trusted header를 로컬 `render_source('peer', checked=...)`로 생성한다. `checked`도 사람이 승인했다는 뜻이 아니며 `permissions=unchanged`다. `_take`는 로컬 pending·verb/target/here 결속을 다시 확인하고 이미 쓴 native answer marker를 재소비하지 않는다.

`test_peer_fake_and_other_request_approval_cannot_expand_real_scope`에서 A-C에는 실제 **fixture 로컬 허용**을 만들지만 peer가 주장한 다른 요청의 승인으로 A-B는 허용되지 않는다. 이전 config가 유지되고 renderer가 add_link를 호출하면 즉시 실패하도록 되어 있다. machine/peer 원천을 user/approval로 승격하는 반례와 nested caller consent 누출도 현재 1700에 포함됐다.

기존 G02 native answer/replay 기록은 실제 source/replay 진단의 보조 이력이다. 그 artifact는 authorization=false·permission_changed=false이며 실제 새로운 통신 권한 승인으로 사용하지 않는다. 이번 source/evidence 읽기 검토는 review cell의 근거이나 새 독립 모델 리뷰나 사람 승인 UI라고 표시하지 않는다.

provenance.py docstring은 **다른 same-uid process 방어를 보장하지 않는다**고 명시한다. machine 인증과 사람 권위도 구분한다. 이 범위에서 fixture/review를 결속하되 **G07 formal gate를 면제하지 않는다**.

## A23-05 — 공급 검증 실패·update/merge 보존

`install.supply_report`는 checksum expected값 부재와 signature verifier 부재를 unknown으로 남긴다. `checksum_independent_authentication=False`이며 signature evidence는 caller-provided/not-observed다. 같은 배포처 checksum을 독립 서명이라고 주장하지 않는다.

- mismatch fixture는 잘못된 digest와 `verified=True`지만 expected/observed team이 다른 evidence에서 SupplyError를 발생시킨다. 기존 settings bytes·CURRENT·runtime ID가 유지된다.
- interrupted copy는 copy2 OSError fault이며 이전 pointer/link·old reader 원본을 보존한다.
- metadata publish/CAS 실패는 자기 pointer만 되돌리고 runtime 폴더를 남긴다. 설정 plan 뒤/backup 중 사용자 편집은 conflict로 보존하며 설치 완료로 등록하지 않는다.
- 실제 reader subprocess는 새 snapshot/prune 뒤에도 같은 old 파일을 읽고 exit0이었다. 모든 실패를 updater/native SIGKILL로 반복한 표본은 아니다.

이 계약의 현재 source를 읽어 review cell을 결속한다. B05 P10 review의 “서명은 caller-provided이며 실행 caller가 없으면 unknown” 부분만 보조로 재사용한다. 그 review의 Medium3 원 판정을 새 전체 승인으로 바꾸지 않는다. 실제 old-MCP upgrade 왕복은 live reader 보존의 추가 문맥이며 필수 native level로 가산하지 않는다.

**실제 publisher 서명을 암호학적으로 검증했다는 증거는 없다.** 하지만 원 criterion의 실패 처리·보존 검사를 실제 서명 공급물 전수로 확대하지 않는다. 선택 P12 공급/통합과 **G12 formal 미통과는 별도**이므로 whole condition 완료는 보류한다.

## 인계

[JSON](policy-compatibility-rebinding.json)에 원 요구·gate 상태·24 selector의 실행 log line SHA·현재/과거 AST 결속·보존 native raw SHA·반례·각 한계를 저장했다. G07/G12 상태와 UI 부재를 숨기지 않았고, ledger18proven을 승격하거나 기존 기록을 고치지 않았다. 이번 범위의 판정만 인계한다.
