# A17-04 정확한 criterion 증거 종결 감사

판정: **기존 근거를 수준별로 결속하면 A17-04 종결 가능**. 원문에 없는 모든 native 갱신 전수 행렬은 요구하지 않았다. source/plan/ledger와 기존 per-run partial 보고서는 수정하지 않았다.

원 ADR-0017:49·acceptance.md:209는 “작업 상태 추출기가 없는 하네스도 기본 통신을 수행한다. 제목·계획 갱신·부분 기록·캐시 만료를 검사한다”이며, fixture·실제 하네스·사람/독립 검토를 요구한다. 각 세부 항목에 모든 수준의 전수 실험을 요구하는 문구는 없다.

## 원 수준별 매핑

| 원 요구 | 기존 증거·현재 selector | 수준과 한계 |
|---|---|---|
| 추출 실패에도 기본 통신 | `DirectoryTest.test_source_failure_is_unknown_and_does_not_block_base_communication`; native title/summary/todo unknown 상태의 실제 discover→ask→inbox→reply_to→final | fixture는 두 parser 실패에도 receive/scope 유지, native는 실제 왕복. fixture를 실제 send라고 쓰거나 native에서 extractor를 제거했다고 쓰지 않음 |
| 제목·계획 갱신 | `test_native_rename_is_current_and_resume_retains_id`, `DirectoryContractTest.test_native_rename_changes_lookup_without_changing_pointer_identity`, `test_codex_native_summary_branch_source_freshness_and_busy_idle`, `test_claude_native_title_and_documented_todowrite_schema`, `test_unknown_plan_schema_clears_old_summary_and_never_scans_prose` | fixture. 현재 제목 변경·plan/TodoWrite 추출·후속 손상 plan의 이전summary 무효화. 두 정상 plan의 native 연속 갱신으로 확대하지 않음 |
| 부분 기록·재작성 | `test_partial_json_truncate_and_mismatched_session_are_unknown`, `test_atomic_replace_and_concurrent_truncation_are_unknown`, bounded reader 시험 | fixture. malformed/잘림/교체는 unknown, 전체 rollout 읽기 방지 |
| 캐시 만료·오래된 값 | `test_stale_metadata_is_labeled_not_consent_or_live_work`, hook-name fallback 시험, `BoundedTest.test_quick_caps_a_longer_deadline_and_remembers_one_answer_per_question`; source `probe.quick/remember` | fixture/source. quick 종료 시 memo 해제·밖에서는 매번 재계산. 300초는 display freshness 기준이며 권한·공개 TTL 아님 |
| 의미·공개 적절성 | a1/main ‘opencodex 설정 적용’, a2/main ‘설정 변경 리뷰’에 대한 실제 사용자 “충분하고 공개 범위에 맞음” | 사람 표본 검토. 실제 세션 공개 허가가 아니며 publication_permission=false |

## native 원문 대조

`session-lifetime-native-20261029-37d06cbd`의 manifest **98파일 모두 SHA 일치**를 확인하고 기존 client/server wire를 직접 읽었다. 실제 도구 호출 **9건**, RPC 오류0이며 decoded response hash가 원 summary와 일치한다. sender의 실제 discover 후보2개 모두 summary/todo unknown, hook-name fallback·freshness unknown이다. activity는 task_started에서 busy로 알려졌으므로 추출기 전체 제거/미지원 하네스 실측이라고 하지 않는다.

그 상태에서 실제 ask가 pending으로 저장되고 원 CID resume의 inbox 수신·동일 원 ID reply_to/outcome=succeeded·sender question_status final/succeeded까지 이어진다. 이는 사용 가능한 업무요약/계획 추출 결과가 없어도 핵심 통신이 유지된 native 증거다. B03의 실제 CLI/Claude MCP unknown 후보 검색·최종 회신은 이전 source의 보조 근거로만 결속했다.

원 표본의 `whole_A17_04_proven=false`와 미실행 native 갱신 행렬 기록은 그대로 보존한다. 그 단일 실행의 부분 판정과 이번 여러 기존 근거의 criterion 종결 판정은 다르다. ACK0·선택pair 수명 미확보는 A17-06 등의 한계이며 A17-04에 새 필수 조건으로 가산하지 않았다. profile drift writer 미확정도 보존했다.

## 사람 승인·현재 source 결속

사람 승인 artifact만 재인용하지 않고 원 native의 **response_item/user 이벤트**, timestamp `2026-10-28T10:21:54.517Z`와 해당 question ID·답변을 대조했다. 원 native line3181 SHA는 `9045a9681dc013bc3b7ae1b17772c44c83bed5ef0dc23e1e59d14c94e1730796`이다. 질문 선택지의 같은 문구나 assistant의 재인용을 user 답으로 세지 않았다.

기준은 최종 `/private/tmp/xsm-final-receipt-frozen-i3u9pms3`이고 **135 primary SHA 일치**다. B03 이후 directory.py는 바뀌었으므로 옛1305를 현재 실행으로 승격하지 않았다. 현재 fixture selector와 file/function SHA를 추출하고 최종1697 원 로그 둘의 SHA·각1697/OK를 재확인했다. 원 로그는 비상세라 개별 이름을 출력한 로그라고 쓰지 않는다. 최종고정본의 해당 시험/source와 최종 source에서 수행된 native wire를 함께 결속했다.

[JSON](directory-extraction-closure-audit.json)에 모든 source selector/위치·함수 hash, 원98파일 SHA, decoded wire response hash, 원 user 이벤트 line SHA, regression log SHA를 수록했다. source 검토에서 bounded parse와 unknown fallback 경로도 확인했다. **원criterion에 대한 추가 미확보 셀은 남기지 않는다.** 모든 native 갱신 전수나 모든 요약 공개 전수평가는 이 판정의 조건이 아니다.

새 모델·네트워크·diagnostic·제품/시험 실행은 모두0이다. 기존 offlinecheck는 summary 쓰기와 로그 복사를 하므로 실행하지 않고 source만 읽었다. doctor v3의 원 partial/unknown 파일은 hash까지 대조해 보존했다.
