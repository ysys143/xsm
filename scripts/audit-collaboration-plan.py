#!/usr/bin/env python3
"""P13 evidence index, not a completion approval or another product code review.

Default: exit 1 while product evidence/gates are incomplete. --structure-only:
exit 0 for a consistent index, explicitly NOT product completion. --refresh
updates only the two completion-ledger files. --self-test mutates in-memory
copies; it never edits plan/spec/artifacts or grants a skip/approval.

Evidence bindings below are deliberately scoped. Existing recorded runs may
support part of a condition; a passing gate, test source, daemon PID, installed
file, OS exit 0 or synthetic transport never proves an unexecuted environment.
To add future proof, add its concrete artifact predicate and coverage binding;
do not merely edit ledger statuses.
"""
from __future__ import annotations

import argparse
import ast
import copy
from contextvars import ContextVar
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

PLAN = 'docs/plan/collaboration/plan.json'
SPEC = 'docs/plan/collaboration/spec.md'
BASE = 'docs/plan/collaboration/'
# Where the plan lived until 2026-10-30. Recorded evidence and frozen snapshots keep it.
OLD_BASE = 'docs/plan/reason-inspired-adrs/'
OLD_RECORDS = {'current-handoff.md', 'development-policy.md', 'release-candidate.md',
               'adr-0021-implementation.md', 'policy-validation.json', 'validation.json'}
LEDGER = BASE + 'completion-ledger.json'
REPORT = BASE + 'completion-ledger.md'
# Full regression of the source with ADR-0025/0026 and the README notes (2026-10-30). It rebinds fixture/process
# cells only: native/UI/physical runs were made on earlier sources.
REBIND = 'deliverables/ledger-rebind-20261030-adr0025/'
ADR21 = 'deliverables/adr0021/'
# This audit under its current and earlier name; no test reads either.
AUDIT_SCRIPTS = {'scripts/audit-collaboration-plan.py', 'scripts/audit-reason-plan.py'}
ADR21_RELEASE_SHA = 'f17f03fafcdf3a31e374d6cbc0ccbbbd8000ba6a7eba5d9b44605e742c409aed'
STATES = {'proven', 'partial', 'missing', 'contradicted'}
LEVELS = {'fixture': 'fixture', 'subprocess': 'process', 'harness': 'native',
          'actual-harness': 'native', 'ui': 'UI', 'physical': 'physical',
          'physical-machines': 'physical', 'review': 'review'}
ADR_COUNTS = {15: 6, 16: 8, 17: 6, 18: 8, 19: 6, 20: 7, 21: 7, 22: 6, 23: 8, 24: 8}
ACCEPTANCE_IDS = {'A%02d-%02d' % (adr, n) for adr, count in ADR_COUNTS.items() for n in range(1, count + 1)}
RESIDUAL_IDS = {'R02', 'R04', 'R07', 'R09', 'R10', 'R16', 'R17', 'R18', 'R23', 'R25',
                'R26', 'R27', 'R29', 'R30', 'R35', 'R38', 'R39', 'R40', 'R41', 'R42'}
JOURNEY_IDS = {'J%02d' % n for n in range(1, 10)}

TESTS = {
 'P00': ['test_vectors', 'test_crash_boundaries'],
 'P01': ['test_mcp_identity', 'test_xsm', 'test_remote'],
 'P02': ['test_native_consent', 'test_connection_binding', 'test_peer_roundtrip', 'test_one_yes', 'test_selected_connection'],
 'P03': ['test_questions', 'test_question_interfaces', 'test_mcp_dispatch', 'test_mcp_wait_process'],
 'P04': ['test_handoff', 'test_handoff_consumer', 'test_handoff_crash', 'test_b04_interfaces', 'test_crash_boundaries'],
 'P05': ['test_directory', 'test_directory_contract', 'test_directory_interfaces', 'test_discovery_latency'],
 'P06': ['test_files', 'test_materials', 'test_file_interfaces'],
 'P07': ['test_decisions', 'test_attention', 'test_user_answers', 'test_person_decisions'],
 'P08': ['test_owned_workers', 'test_owned_requests', 'test_owned_crash', 'test_owned_native', 'test_owned_native_events', 'test_owned_interfaces'],
 'P09': ['test_provenance', 'test_abuse', 'test_policy_recovery', 'test_traffic_policy'],
 'P10': ['test_install_cli_flow', 'test_install_safety', 'test_setup_flow', 'test_install_runtime', 'test_install_codex', 'test_launcher', 'test_hook_status', 'test_version_mix'],
 'P11': ['test_remote'], 'P12': ['test_remote'], 'P13': [],
}
EXTRA_SOURCE = {'P06': ['xsm/files.py', 'xsm/materials.py'], 'P07': ['xsm/decisions.py', 'xsm/attention.py'],
                'P08': ['xsm/workers.py'], 'P09': ['xsm/provenance.py', 'xsm/abuse.py'],
                'P10': ['xsm/setup_flow.py']}

# Only these five reviewed criteria may obtain full cell credit from this run.
# Selectors bind specific counterexamples to the executed, immutable snapshot;
# file presence or the number 1649 alone never grants this credit.
CLOSURE_PROOFS = {
 'A18-03': {'levels': ['fixture', 'process'], 'origins': ['gate-G01', 'b05-local-integration'],
   'cases': {'tests/test_xsm.py': ['test_two_bodies_sharing_the_first_200_chars_are_not_the_same',
       'test_a_different_target_is_refused', 'test_the_identical_message_still_resends',
       'test_the_same_native_id_in_another_home_is_another_session'],
     'tests/test_handoff_consumer.py': ['test_same_id_different_body_or_endpoint_refused_before_original_export'],
     'tests/test_handoff.py': ['test_store_canonical_digest_original_and_duplicate_do_not_reset_claim'],
     'tests/test_handoff_crash.py': ['test_sigkill_after_store_commit_before_return_recovers_original_id']},
   'product': ['send', 'envelope', 'ledger', 'handoff', 'receive', 'registry', 'identity', 'paths']},
 'A18-07': {'levels': ['fixture', 'process'], 'origins': ['b04-regression', 'b05-local-integration'],
   'cases': {'tests/test_handoff.py': ['test_retention_expiry_delivery_and_outcome_are_separate_and_never_delete',
       'test_expired_or_backward_clock_token_cannot_ack_before_recovery'],
     'tests/test_xsm.py': ['test_a_legacy_entry_reads_as_legacy_and_unverified',
       'test_an_upgraded_legacy_row_stays_unverified', 'test_status_keeps_the_step_map_and_the_wrapper_apart'],
     'tests/test_questions.py': ['test_parts_dedup_conflict_and_explicit_final',
       'test_handshake_tracks_latest_explicit_outcome_across_partial_replies'],
     'tests/test_handoff_crash.py': ['test_sigkill_after_ack_commit_lost_response_readback_suppresses_duplicate']},
   'product': ['handoff', 'ledger', 'receive', 'send', 'outbox', 'paths', 'envelope', 'questions', 'connect']},
 'A22-06': {'levels': ['fixture', 'process'], 'origins': ['b05-local-integration'],
   'cases': {'tests/test_policy_recovery.py': ['test_invalid_json_without_prior_valid_file_does_not_open_same_directory',
       'test_last_valid_snapshot_preserves_existing_link_deny_and_native_policy',
       'test_read_and_snapshot_write_failures_preserve_policy_and_report_errors',
       'test_snapshot_recovers_in_a_fresh_python_process',
       'test_external_revocation_snapshot_wins_over_failed_write_memory_even_after_clock_rollback',
       'test_two_process_writers_share_lock_and_one_stale_revision_is_rejected'],
     'tests/test_b04_interfaces.py': ['test_corrupt_policy_preserves_existing_scope_but_blocks_new_grants'],
     'tests/test_handoff_consumer.py': ['test_traffic_journal_failure_is_diagnostic_and_does_not_block']},
   'product': ['config', 'policy', 'consent', 'handoff', 'receive', 'send', 'paths', 'abuse', 'mcp']},
 'A23-02': {'levels': ['fixture', 'process'], 'origins': ['b05-local-integration', 'p10-cli'],
   'cases': {'tests/test_install_safety.py': ['test_claude_and_codex_clean_reinstall_remove_preserve_user_settings_and_mode',
       'test_settings_changed_after_plan_are_preserved_and_not_registered_as_installed',
       'test_uninstall_preserves_later_edits_to_owned_hook_and_statusline',
       'test_skill_copy_uninstall_preserves_added_and_modified_user_files',
       'test_cooperative_installers_serialize_and_leave_one_group_per_event'],
     'tests/test_install_cli_flow.py': ['test_named_install_matrix', 'test_cli_cas_preserves_user_followup',
       'test_cli_failed_upgrade_keeps_old_snapshot_and_flow_id']},
   'product': ['install', 'setup_flow', 'cli', 'config', 'paths']},
 'A18-05': {'levels': ['native'], 'origins': ['b04-native'],
   'cases': {'tests/test_b04_interfaces.py': ['test_natural_mcp_boundary_receives_fyi_without_any_transport',
       'test_native_hook_exposes_ack_token_and_confirmed_message_never_replays']},
   'product': ['mcp', 'receive', 'send', 'handoff', 'registry', 'context', 'identity', 'envelope',
       'ledger', 'config', 'inbox', 'instructions', 'paths', 'connect', 'questions'],
   'native': True},
}

# Criterion-specific gaps: these are unfinished requirements, never exemptions.
GAPS = {
'A15-01': '같은 repo/linked worktree의 실제 CLI/MCP 전 조합과 현재 통합본 source 결속이 남음.',
'A15-02': 'G02 실제 trace는 질문 선결속 hardening 전 표본. hardening 뒤 동일 S5 채널 전체 복구/동시 CLI 재평가가 남음.',
'A15-03': '현재 native 수집 단절→unknown→동일 요청 회수 전체 표본이 없음.',
'A15-04': 'G07 실제 거부·취소·늦은 답·철회 경쟁의 사람 관측이 없음.',
'A15-05': '다른 부모 직접 왕복은 fixture가 있고 실제 두 worker의 부모 비중계 trace가 없음.',
'A15-06': '다른 업무·세대·철회·resume의 실제 승인 범위 전수 readback이 남음.',
'A16-01': 'B03 실제 질문/회신은 로컬 표본. 같은 입력의 CLI/MCP 및 현재 통합 revision 전체 의미 일치를 닫지 않음.',
'A16-02': '늦은 실제 답 표본은 있음. 장기 작업 중 독립 작업·중복 없는 회수의 현재 통합 여정이 남음.',
'A16-03': 'priority/wake/files/outcome/owned 전체 기능 표의 실제 양 인터페이스 전수 효과가 남음.',
'A16-04': '최종 source의 실제 sandbox child2 첫 reply MCP·원 요청 상관·ACK·셸 전송/권한 확대0을 원 wire/rollout SHA로 결속. clean 설치/J03 전체와 별개.',
'A16-05': 'cached tools/list·자동 수신 하향의 실제 모든 하네스 미독 회수 조합이 남음.',
'A16-06': 'owned Claude/Codex 두 turn 기억 표본은 있음. 일반 세션 대비·퇴출 뒤 기억·전체 공개 진입점 검증이 남음.',
'A16-07': 'fixture/process 대기 취소·시간초과·동시 reply/분배와 실제 부분/final native를 수준별 결속. G07 formal gate는 별도 미완이며 모든 음성을 native/UI에서 반복하는 의무는 없음.',
'A16-08': '실제 capacity10turn·독립검토3turn은 request subset/raw SHA로 재결속. 새 doctor epoch/full 검증 전 현재 credit은 대기하며 전체 journal 역사 SHA 일치를 주장하지 않음.',
'A17-01': '로컬 후보/동명 fixture 및 native discover 표본. 실제 다른 머신 동일 이름·업무/branch는 없음.',
'A17-02': '공유 MCP 실제 프로세스 하나의 A/B 교대 호출·신원 격리 fixture는 현재 HEAD 회귀로 결속. 실제 Codex daemon 두 스레드의 native 호출은 미관측.',
'A17-03': '로컬 resume/rename/pid fixture와 원격 동명·다른 머신 native 세대 행렬은 별개.',
'A17-04': 'directory 추출 fixture·unknown metadata native 통신·기존 사람 표본은 구체 selector/SHA로 결속. 새 epoch/full 검증 대기와 원 표본 한계를 분리.',
'A17-05': '등록/목록 제외 fixture에 실제 공유 MCP 첨부 소비의 제외/권한 행렬을 합쳐야 함.',
'A17-06': 'B04 원문 회수는 있음. 동명 새 대화/동일 resume과 승인 수명 전 조합 native 추적이 남음.',
'A18-01': 'G01 로컬 실패 주입 기록을 현재 실제 queue/socket 실패 하네스 전체와 혼합하지 않음.',
'A18-02': 'factory native claim0byte/실제client종료/같은CID 새세대 owner-dead회수/ACK·상관reply/ACK후빈inbox 관측. fixture/process취소는충족했으나 native cancel notification은0으로 native취소셀은missing; 전체partial. 첫resume거부/tail race/drift writer unknown 보존.',
'A18-03': '같은 ID 변조/200자 반례를 현재 HEAD 두 Python 전체 회귀로 재결속. 소스가 바뀌면 재평가.',
'A18-04': '로컬 claim/legacy/설치 실패 보존과 원격 변경 직전·직후 단절/readback은 별개. G12 없음.',
'A18-05': '두 실제 Codex 홈의 injected-MCP 수신/회신 있음. 기존/새 설치·idle/busy 전체 경로는 G10 미완.',
'A18-06': 'wake=False native 소비와 무전송 fixture 있음. 자연 소비 전 상태·현재 모든 하네스 조합이 남음.',
'A18-07': '상태/시계/legacy 반례를 현재 HEAD 두 Python 전체 회귀로 재결속. 소스가 바뀌면 재평가.',
'A18-08': 'actual owned controller SIGKILL5경계/child5/turn5/기본도구5/counter각1을현재1667/313source와결속. reply-stored만이며 nativeMCP/UI/ACK/현재caller certainty·mid-tool write종료로확대하지않음.',
'A19-01': 'Codex 두 홈 및 Claude의 실제 사본 token 읽기/ACK/reply 있음. 동일 입력 CLI/MCP 원문·사본 digest 전수 대조는 남음.',
'A19-02': '공유 MCP 실제 프로세스에서 A/B 각자 사본 읽기·상대 사본 거절 fixture는 현재 HEAD 회귀로 결속. 실제 하네스 native 호출은 미관측.',
'A19-03': '실제 정상 첨부 표본 두 건. 허가된 외부/숨김 성공 및 권한 밖/제외/symlink/충돌 전수는 남음.',
'A19-04': '기능미광고/구버전/본문한도 fixture는 결속했으나 정상 사본 native를 조건부 fallback native로 승격하지 않음. 해당 native 부분 및 G12를 유지.',
'A19-05': '저장·quota·승인 보류·재시작·만료·M3 cleanup 근거와 새1667 source 결속 있음. closure G07 미통과로 전체 partial; complete_for는 지정 5개에 한정.',
'A19-06': '사본 실제 읽기는 있음. 버전별 수정본/이전 사본 불변·독립 검토 native trace가 남음.',
'A20-01': 'UI intent 두 파일 모두 prepared-not-displayed. 실제 원문/잘림 표시와 사람 대조 증거 없음.',
'A20-02': '중복 질문 fixture는 실제 창 1개·적용 1회의 사람 관측을 대신하지 않음.',
'A20-03': 'waiter/decision process 검사는 있음. 실제 UI 늦은 답·철회·취소 경쟁이 없음.',
'A20-04': '실제 거부/닫힘/하네스 자동 거절/desktop 부재를 구분한 사람 UI 관측이 없음.',
'A20-05': '가짜 태그/다른 요청 승인 source 검사는 있음. 실제 native 승인 재사용 반례가 남음.',
'A20-06': 'OS 호출 exit 0만 관측. human_saw/observed_display_range가 null이며 UI 억제·접근성 행렬은 없음.',
'A20-07': 'G02 원 trace와 native-channel 진단은 scope가 다름. 최신 hardening 동일 채널 전체 재실행이 남음.',
'A21-01': '기본native15/cached5와 별도 C UDP/native1·post-bootstrap noSSH/native1·loopback CONNECT/native1 부분표본 있음. A/B/D·global network·신규설치무SSH·기업인증proxy·다른NAT·자가relay·P12는 미확보.',
'A21-02': '합성 임시 인증은 선택 backend의 계정/팀/제명/초대/전환 실패 의미를 입증하지 않음. D12 없음.',
'A21-03': '기본 A/B/D9+C6의 G11 독립검토와 문서후속 있음. C UDP/noSSH/proxy의 추가native각1은 별도 offline 근거로 원 모델 재검토 범위 밖. 무SSH 신규설치·설치/개입비용·미확보 환경은 남으며 D12 선택 자체를 비교 완료 전제로 만들지 않음.',
'A21-04': 'E10/E15 두 Mac 제품 후보 선택·handshake·직접 회신·ACK와 같은 CID 재개는 관측(5e20 이전 소스). 이후 receive/handoff 변경 소스의 재관측과 G12가 남음.',
'A21-05': '임시 responder 정리는 있음. 선택 remote/relay 중단 중 실제 로컬 유지·소유 서비스 제거는 없음.',
'A21-06': 'E6 두 Mac 가입 전후 directory·공개/제외·선택 필요 거절과 지정 범위 Opus 검토는 있음. 모델 0회 FILE actor 표본이며 현재 소스 재관측·hosted 내부·G12가 남음.',
'A21-07': 'E13 같은 호스트 IPv6 오류·점유 포트 대체 bind와 E4 실행 중 주소 변경 왕복은 관측. 호스트 전체 IPv6 부재·현재 소스 재관측·G12가 남음.',
'A22-01': 'renderer/attachment source 반례가 있음. 실제 native 공격 행렬과 G06/G07/G09 통합 종결은 없음.',
'A22-02': '다른 대상의 실제 fixture 승인과 peer 승인 주장은 current source/review로 결속. same-uid 방어 과장은 없으며 실제 UI 미관측과 formal G07은 유지.',
'A22-03': '동일 strict 정책의 실제 3라운드·반복 held·원 ID 회복 trace가 있음. 새 doctor epoch/full 전 현재 승격은 보류하고 profile drift/정리 한계를 유지.',
'A22-04': '일반·형제·다른 부모 성공은 원 raw로 재사용. full native endpoint와 distinct historical Gitcommon이 결속된 crossrepo 한 셀만 미확보.',
'A22-05': 'B04 native 로컬 수신과 정책 fixture가 있음. 최신 traffic/files 통합의 native/strict/deny 전수가 남음.',
'A22-06': 'last-valid·상태 실패 반례를 현재 HEAD 두 Python 전체 회귀로 재결속. 소스가 바뀌면 재평가.',
'A23-01': '실제 clean/stale/current native CLI 등록6셀·combined설치/제거 및 local G10passed 복구. 새clean 프로필 로그인/첫모델왕복은 여전히 미실행; 기존133primary1667을 대신 쓰지 않음.',
'A23-02': '원 native CLI 설치/제거 실패 보존. 최종 source의11개 새반례·91개씩/변이2·실제 등록6셀·combined/제거와1667을 재결속했으며 관련 hash가 달라지면 종결을 재평가.',
'A23-03': '공유 MCP A/B·다른 홈 같은 ID·상속 env fixture는 현재 HEAD 회귀로 결속. 실제 하네스의 같은 조합 native 전수는 미관측.',
'A23-04': 'flow 교체·설정/CAS fixture는 있음. 실제 UI 로그인·가입·reconnect/old API 전수 및 G12는 없음.',
'A23-05': 'checksum/team 불일치·update/CAS/merge 실패의 보존은 수준별 결속. caller-provided signature 한계와 formal G12를 유지.',
'A23-06': 'owned native 기억/MCP 관측은 있음. 기본 공개 owned 경로의 후속·권한·실제 reply 전체 행렬은 남음.',
'A23-07': '격리 CLI/소유 reader·redaction 검사는 있음. 실제 모든 사용자 프로필 진단·독립 검토는 아님.',
'A23-08': '실제 old native/MCP 유지 중 업그레이드/두 reply와 new-prefix reply 있음. 전체 구 native/socket·마이그레이션 행렬은 남음.',
'A24-01': '로컬 공개/repo 합집합 및 native discover 표본. 원격 후보 공개 집합/중복/비공개 전수는 없음.',
'A24-02': '로컬 common-dir/clone fixture. 실제 원격 repository 매핑은 없음.',
'A24-03': '원격 machine 필터는 unknown. Macmini의 해당 작업 후보 actual handle trace가 없음.',
'A24-04': '로컬 선택 계약은 있음. 두 머신 실제 한 지시·다른 후보 권한 불변/승인 수명 전수는 없음.',
'A24-05': '로컬 실제 candidate handshake 있음. 다른 머신·동명/세대 교체 실제 상대 trace는 없음.',
'A24-06': '로컬 timeout/회수는 있음. 원격 busy/lost result·부모 없는 양방향 실제 업무 전수는 없음.',
'A24-07': '로컬 withdraw/resume fixture. 원격 공개·승인·미독 세대 수명과 경로 비공개 실제 전수는 없음.',
'A24-08': 'MacBook→Macmini 후보 검색→선택→handshake→실제 작업 reply 전체 trace가 없음. transport 합성으로 대체 금지.',
}

JOURNEY_ACCEPTANCE = {
 'J01': ['A23-01', 'A23-02', 'A23-04', 'A16-04'],
 'J02': ['A15-02', 'A16-01', 'A20-07'],
 'J03': ['A16-04', 'A18-05', 'A23-01'],
 'J04': ['A15-05', 'A16-08', 'A19-06', 'A22-03', 'A22-04'],
 'J05': ['A18-02', 'A18-06', 'A18-08'],
 'J06': ['A20-01', 'A20-02', 'A20-03', 'A20-04', 'A20-06'],
 'J07': ['A21-01', 'A21-02', 'A21-04', 'A21-05'],
 'J08': ['A23-02', 'A23-08', 'A18-04'],
 'J09': ['A24-%02d' % n for n in range(1, 9)],
}
JOURNEY_LEVELS = {
 'J01': ['fixture', 'process', 'native', 'UI'], 'J02': ['fixture', 'process', 'native'],
 'J03': ['fixture', 'process', 'native'], 'J04': ['fixture', 'process', 'native', 'review'],
 'J05': ['fixture', 'process', 'native'], 'J06': ['fixture', 'process', 'native', 'UI'],
 'J07': ['fixture', 'process', 'native', 'physical'], 'J08': ['fixture', 'process', 'native'],
 'J09': ['fixture', 'native', 'physical'],
}
JOURNEY_ENVIRONMENTS = {
 'J01': ['human-UI'], 'J02': [], 'J03': [], 'J04': [], 'J05': [],
 'J06': ['human-UI', 'UI-late-cancel-focus-race'],
 'J07': ['different-NAT', 'UDP-blocked', 'HTTPS-proxy', 'self-hosted-relay',
         'physical-native-peer', 'selected-backend-D12'],
 'J08': [], 'J09': ['physical-native-peer', 'selected-backend-D12'],
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def local(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('repo-relative evidence path required: ' + relative)
    resolved = (root / path).resolve()
    if root.resolve() not in resolved.parents and resolved != root.resolve():
        raise ValueError('evidence path escapes repository: ' + relative)
    if not resolved.exists() and str(relative).startswith(OLD_BASE):
        moved = (root / moved_plan_path(str(relative))).resolve()
        if moved.exists():
            return moved
    return resolved


def moved_plan_path(relative):
    """The current place of a plan file a record names by its pre-2026-10-30 path."""
    rest = relative[len(OLD_BASE):]
    name = rest.split('#', 1)[0]
    return BASE + ('records/' + rest if name in OLD_RECORDS or name.startswith('gates/') else rest)


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def inventories(plan, spec):
    acceptance = plan['acceptance']
    residuals = plan['residuals']
    if len(acceptance) != 70 or {r['id'] for r in acceptance} != ACCEPTANCE_IDS:
        raise ValueError('original acceptance inventory must contain all 70 exact IDs')
    if len(residuals) != 20 or {r['finding'] for r in residuals} != RESIDUAL_IDS:
        raise ValueError('original residual inventory must contain all 20 exact IDs')
    if len(plan['journeys']) != 9 or set(plan['journeys']) != JOURNEY_IDS:
        raise ValueError('original journey inventory must contain J01-J09')
    journeys = []
    for line in spec.splitlines():
        cells = [part.strip() for part in line.strip().strip('|').split('|')]
        if len(cells) == 3 and cells[0] in JOURNEY_IDS:
            journeys.append({'id': cells[0], 'start_and_work': cells[1], 'required_result': cells[2]})
    if len(journeys) != 9 or {r['id'] for r in journeys} != JOURNEY_IDS:
        raise ValueError('all nine original journey descriptions must be present in spec.md')
    return acceptance, residuals, journeys


def fact(root, path, levels=(), *, scope, predicate=None, execution='recorded', authority='recorded-local-scope', complete_for=None):
    filename = local(root, path)
    value = {'path': path, 'levels': list(levels), 'scope': scope, 'authority': authority,
             'available': filename.is_file(), 'executed': False, 'result': 'missing', 'sha256': None,
             'coverage_ceiling': 'partial', 'complete_for': complete_for or {}}
    if not filename.is_file():
        return value
    content = filename.read_bytes()
    value['sha256'] = hashlib.sha256(content).hexdigest()
    try:
        data = json.loads(content) if filename.suffix == '.json' else content.decode('utf-8')
        checks = predicate(data) if predicate else {'record_exists': True}
        value['checks'] = checks
        passed = bool(checks) and all(item is True for item in checks.values())
        value['executed'] = execution == 'recorded' and passed
        value['result'] = ('recorded-pass' if passed else 'recorded-failure') if execution == 'recorded' else execution
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        value['checks'] = {'readable_expected_shape': False}
        value['result'] = 'unreadable-or-changed:' + type(exc).__name__
    return value


def c_native_checks(data):
    machines = data['physical_machines']
    runs = data['runs']
    phases = [p for run in runs for p in run['phases'] if p.get('native', {}).get('actual_native_call') is True]
    return {'two_physical_hosts': machines['local_hostname'] != machines['peer_hostname'],
            'two_runs_six_native': len(runs) == 2 and len(phases) == 6
                                  and data['native_successes'] == 6 and data['native_failures'] == 0
                                  and all(r['passed'] is True and r['native_model_calls'] == 3 for r in runs),
            'direct_both_nodes': len(phases) == 6 and all(
                any(m['is_me'] is False and m['link'] == 'direct' for m in p['readback'][side]['machines'])
                for p in phases for side in ('local', 'peer')),
            'native_reply_binding': all(p['actual_json_answer']['request_id'] == data['task_marker']
                                       and p['native']['request_engine_id_sha256'] == p['request_engine_id_sha256']
                                       and p['reply_engine_id_sha256'] in p['native']['reply_engine_ids_sha256']
                                       and (p['phase'] == 'after-reconnect' or
                                            (p['native']['received_body_sha256'] == p['request_body_sha256']
                                             and p['native']['answer_sha256'] == p['answer_body_sha256']))
                                       and any(e['native_conversation_sha256'] == p['native']['native_conversation_sha256']
                                               and e['received_body_sha256'] == p['native']['received_body_sha256']
                                               and e['exit_code'] == 0 for e in data['native_evidence'])
                                       and p['native']['native_process_exited'] is True for p in phases),
            'no_cache_rerun': data['cached_readbacks'] == 2 and data['cached_model_reruns'] == 0,
            'scope_not_promoted': data['overall_P11_complete'] is False
                                  and data['D12_backend_selection'] == 'unchanged/unselected'}


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def function_names(root, path):
    return {n.name for n in ast.walk(ast.parse(local(root, path).read_text()))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def head_rebind_regression_checks(root, data):
    """The current-HEAD freeze: every frozen input equals the working tree, every
    product/test/skill file is frozen, and both Pythons ran it in full."""
    manifest_file = local(root, REBIND + 'manifest.json')
    # This audit is not an input of the suite it audits (no test reads scripts/);
    # its own checks are --self-test and --predicate-self-test.
    manifest = {p: h for p, h in load_json(manifest_file).items() if p not in AUDIT_SCRIPTS}
    wanted = {str(p.relative_to(root)) for pattern in ('xsm/*.py', 'tests/test_*.py', 'hooks/*', 'skills/xsm/**/*.md', 'scripts/*.py')
              for p in root.glob(pattern) if p.is_file()} - AUDIT_SCRIPTS
    runs = data['full_regression']
    logs = []
    for run in runs:
        log = local(root, REBIND + run['log'])
        text = log.read_text(errors='replace') if log.is_file() else ''
        logs.append(file_sha(log) == run['log_sha256']
                    and re.search(r'^Ran %d tests in [0-9.]+s$' % run['tests_run'], text, re.M) is not None
                    and re.search(r'^OK$', text, re.M) is not None and 'skipped' not in text.split('\nRan ')[-1])
    return {'manifest_bytes_bound': file_sha(manifest_file) == data['freeze']['manifest_sha256'],
            'current_source_exact': bool(manifest) and all(file_sha(local(root, p)) == h for p, h in manifest.items()),
            'every_product_test_skill_file_frozen': wanted <= set(manifest),
            'both_Pythons': sorted(r['label'] for r in runs) == ['py314', 'py39'],
            'full_pass_skip0_same_count': all(r['exit_code'] == 0 and r['skipped'] == 0 for r in runs)
                                          and len({r['tests_run'] for r in runs}) == 1 and runs[0]['tests_run'] >= 1936,
            'exact_logs': len(logs) == 2 and all(logs),
            'release_engine': data['freeze']['binary_sha256'] == ADR21_RELEASE_SHA,
            'not_whole_plan': data['whole_plan_complete'] is False}


def head_rebind_cases(identifier):
    """The specific counterexamples a criterion was closed with (as in
    postqa_criterion_binding), now run by the current-HEAD regression."""
    if identifier == 'shared-mcp':
        return {'tests/test_mcp_shared_process.py': [
                    'test_two_threads_of_one_process_keep_their_own_inbox_and_copies',
                    'test_a_call_naming_no_thread_among_several_is_not_signed_as_the_newest'],
                'tests/test_mcp_identity.py': [
                    'test_abab_calls_keep_their_own_thread_folder_and_home',
                    'test_a_record_from_another_home_is_not_taken',
                    'test_an_inherited_codex_home_does_not_change_the_named_thread',
                    'test_a_named_thread_wins_over_an_inherited_other_thread',
                    'test_a_guessed_neighbor_cannot_read_a_file']}
    cases = copy.deepcopy(CLOSURE_PROOFS[identifier]['cases'])
    if identifier in ('A18-03', 'A18-07', 'A22-06'):
        cases['tests/test_question_interfaces.py'] = [
            'test_answer_claims_allow_exact_ack_without_extra_inbox_on_all_public_surfaces',
            'test_reply_handoff_rechecks_owner_generation_digest_and_receive_policy',
            'test_reply_claim_failure_preserves_verified_answer_and_recovery']
    if identifier == 'A23-02':
        cases['tests/test_install_native_mcp.py'] = [
            'test_clean_native_get_bootstrap_does_not_collide_with_installer',
            'test_concurrent_user_edit_rejected_even_for_current_state',
            'test_public_uninstall_invalid_json_is_exit4_without_traceback_or_partial_removal',
            'test_public_uninstall_symlink_is_exit4_without_traceback_or_partial_removal',
            'test_public_uninstall_normal_path_removes_owned_components',
            'test_public_native_remove_nonzero_exit_preserves_hooks_and_returns_exit4']
    return cases


def head_rebind_criterion_checks(root, identifier, evidence):
    cases = head_rebind_cases(identifier)
    product = [] if identifier == 'shared-mcp' else ['xsm/' + p + '.py' for p in CLOSURE_PROOFS[identifier]['product']]
    manifest = load_json(local(root, REBIND + 'manifest.json')) if local(root, REBIND + 'manifest.json').is_file() else {}
    checks = {'current_full_regression': evidence['head-rebind-regression']['executed'],
              'specific_cases_present': all(set(names) <= function_names(root, p) for p, names in cases.items()),
              'cases_and_product_frozen': all(manifest.get(p) is not None and manifest[p] == file_sha(local(root, p))
                                              for p in list(cases) + product)}
    if identifier != 'shared-mcp':
        checks['prior_scoped_execution_retained'] = all(evidence[k]['executed'] for k in CLOSURE_PROOFS[identifier]['origins'])
    return checks


def arrival_checks(root, data):
    archive = load_json(local(root, 'deliverables/p10-live/native-upgrade.json'))['trials'][0]
    pairs = [(data, archive['first_reply'])] + [(r, archive['second_reply']) for r in data.get('additional_arrivals', [])]
    return {'R1_R2_archive_exact': len(pairs) == 2 and all(
                r['message_id'] == a['id'] and r['request_id'] == a['reply_to'] and r['body'] == a['body']
                and r['controller_actual_arrival'] is True and r['fixture_archive_match'] is True for r, a in pairs),
            'unchecked_no_authority_or_human_prompt': all(r['global_receiver_provenance'] == 'unchecked'
                and r['permission_or_identity_promoted'] is False and r['additional_human_prompt'] is False for r, _ in pairs)}


def c_checker_checks(root, data):
    paths = {'manifest_sha256': 'deliverables/p11-live/C-native-evidence-manifest-20261029.json',
             'result_sha256': 'deliverables/p11-live/C-native-roundtrip-20261029.json',
             'checker_sha256': 'deliverables/p11-live/C-check-evidence.py'}
    rows = data['python_results']
    manifest = load_json(local(root, paths['manifest_sha256']))
    report = local(root, 'deliverables/p11-live/C-native-roundtrip-20261029.md')
    amendments = [r for r in manifest['files'] if Path(r['local_path']).name == report.name]
    return {'current_result_manifest_checker': all(data[k] == file_sha(local(root, p)) for k, p in paths.items()),
            'report_amendment_bound': len(amendments) == 1 and amendments[0]['sha256'] == file_sha(report)
                                     and amendments[0]['amendments'][-1]['new_sha256'] == file_sha(report),
            'both_versions_UTC': {r['python'] for r in rows} == {'Python 3.9.6', 'Python 3.14.6'}
                                and all(r['started_at_utc'].endswith('+00:00') and r['finished_at_utc'].endswith('+00:00')
                                        and datetime.fromisoformat(r['started_at_utc']) <= datetime.fromisoformat(r['finished_at_utc'])
                                        for r in rows),
            'passed': data['passed'] is True and len(rows) == 2,
            'both_checks': all(r['exit_code'] == 0 and r['result']['passed'] is True
                              and r['result']['hashed_files'] == len(manifest['files']) == 111
                              and r['result']['native_result_files'] == 6
                              and r['result']['native_model_calls_this_check'] == 0
                              and {m['case'] for m in r['result']['mutations']} ==
                                  {'synthetic-native', 'deleted-phase', 'model-reran-cache'}
                              and all(m['rejected'] is True for m in r['result']['mutations']) for r in rows)}


def g11_review_closure_checks(root, data):
    source = load_json(local(root, data['review_source_manifest']))
    return {'original_verdict_retained': data['review_original_verdict'] == 'G11 partial; corrections needed',
            'coordinator_not_second_model_review': data['coordinator_closure_only'] is True and data['second_model_review'] is False,
            'seven_document_findings': {r['id'] for r in data['findings']} == {'R%d' % i for i in range(1, 8)}
                                       and len(data['findings']) == 7 and all(bool(r['closure']) for r in data['findings']),
            'historical_document_amendment_hashes_recorded': len(data['amended_files_sha256']) == 3
                and all(re.fullmatch('[0-9a-f]{64}', h) for h in data['amended_files_sha256'].values()),
            'C_report_amendment_still_exact': data['amended_files_sha256']['deliverables/p11-live/C-native-roundtrip-20261029.md']
                == file_sha(local(root, 'deliverables/p11-live/C-native-roundtrip-20261029.md')),
            'native_raw_JSON_unchanged_since_review': all(source['files'][p] == file_sha(local(root, p)) for p in
                ('deliverables/p11-live/C-native-roundtrip-20261029.json',
                 'deliverables/p11-live/native-carrier-roundtrip-20261029.json')),
            'no_new_native_or_product_change': data['new_native_calls'] == 0 and data['product_changed'] is False,
            'G11_and_D12_not_promoted': data['gate_status'] == 'partial' and data['D12'] == 'unanswered'}


def local_regression_checks(root, data, manifest=None):
    manifest = manifest if manifest is not None else load_json(local(root, data['snapshot_manifest']))
    snapshot = Path('/private/tmp/xsm-p13-local-frozen-dn7tom1y')
    paths = manifest['stable_product_paths']
    logs_ok = []
    for row in data['results']:
        allowed = {'Python 3.9.6': '/tmp/p13-local39.log', 'Python 3.14.6': '/tmp/p13-local314.log'}
        path = Path(allowed.get(row['python'], '/nonexistent-p13-log'))
        text = path.read_text() if path.is_file() else ''
        logs_ok.append(row['log'] == str(path) and file_sha(path) == row['log_sha256']
                       and re.search(r'^Ran 1649 tests in [0-9.]+s$', text, re.M) is not None
                       and re.search(r'^OK$', text, re.M) is not None
                       and row['tests'] == 1649 and row['exit_code'] == 0
                       and row['result'] == 'OK' and row['skips'] == 0)
    return {'both_recorded_runs': len(logs_ok) == 2 and all(logs_ok)
                                  and {r['python'] for r in data['results']} == {'Python 3.9.6', 'Python 3.14.6'},
            'exact_snapshot': data['snapshot'] == manifest['snapshot'] == str(snapshot),
            'post_run_unchanged': data['product_source_unchanged_after_runs'] is True and data['changed_paths'] == [],
            '132_frozen_product_hashes': data['tested_product_paths'] == len(paths) == len(set(paths)) == 132
                                         and all(manifest['files'].get(p) == file_sha(local(snapshot, p)) for p in paths),
            'not_whole_plan': data['whole_plan_complete'] is False}


def current_source_binding(root, manifest):
    changed = [p for p in manifest['stable_product_paths'] if manifest['files'].get(p) != file_sha(local(root, p))]
    return {'status': 'changed-rebinding-required' if changed else 'matches-frozen-snapshot',
            'changed_paths': changed,
            'scope': '현재 source 관측은 고정본 실행 이력과 별도. 각 조건은 자기 dependency hash만으로 재결속하며 예정 수정 성공을 추정하지 않음'}


def natural_checks(root, data):
    raw_path = local(root, 'deliverables/p13-live/natural-collaboration.json')
    raw = load_json(raw_path)
    return {'raw_preserved': data['raw_result_preserved'] is True
                             and file_sha(raw_path) == data['original_result_sha256'],
            'no_rerun_or_correction': data['native_reruns'] == data['message_ack_index_corrections'] == 0,
            'two_conditions': {r['condition'] for r in data['conditions']} == {'B05-final', 'old-0.4.20'}
                              and len(data['conditions']) == len(raw['conditions']) == 2,
            'three_actual_math_each': all(r['audited_business_goal'] == 'passed' and r['actual_math_review_count'] == 3
                                         and len([p for p in r['reviews'] if p['category'] != 'handshake']) == 3
                                         and all(p['received_actual_body'] is True for p in r['reviews']) for r in data['conditions']),
            'new_handshake_only': all(r['actual_handshake_count'] == (1 if r['condition'] == 'B05-final' else 0)
                                      for r in data['conditions']),
            'no_relay_or_human_prompt': all(all(r['controller_interventions'][k] == 0
                                               for k in ('message', 'ack', 'index', 'user_clicks', 'user_commands', 'user_approvals'))
                                           and r['runtime_source_unchanged'] is True for r in data['conditions']),
            'two_native_homes': all({Path(r[k]['profile']).name for k in ('reviewer_invocation', 'initiator_invocation')}
                                    == {'.codex', '.codex-3'} and r['source_unchanged'] is True
                                    and r['source_before']['matches'] is True and r['source_after']['matches'] is True
                                    for r in raw['conditions']),
            'shared_new_guide_not_old_baseline': 'common new skill/guide' in data['old_condition']
                                               and all(r['equals_B05_frozen'] is True for r in data['workspace_documents_at_audit'].values())}


def criterion_binding(root, identifier, regression, evidence, *, before=None):
    proof = CLOSURE_PROOFS[identifier]
    final = load_json(local(root, regression['snapshot_manifest']))
    before = before if before is not None else load_json(local(root, 'deliverables/b05-live/final-source-manifest.json'))
    paths = sorted(set(proof['cases']) | {'xsm/' + p + '.py' for p in proof['product']})
    if proof.get('native'):
        paths += ['skills/xsm/SKILL.md', 'skills/xsm/references/guide.md', 'skills/xsm/references/messaging.md']
    hashes = {p: {'B05': before['files'].get(p), 'P13': final['files'].get(p),
                  'current': file_sha(local(root, p)),
                  'snapshot': file_sha(local(Path(final['snapshot']), p))} for p in paths}
    selectors = {}
    for path, names in proof['cases'].items():
        tree = ast.parse(local(root, path).read_text())
        functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        selectors[path] = {name: name in functions for name in names}
    checks = {'regression_verified': evidence['p13-local-regression']['executed'],
              'specific_counterexamples_present': all(all(v.values()) for v in selectors.values()),
              'same_B05_final_current_snapshot_hashes': bool(hashes) and all(
                  v['B05'] is not None and len(set(v.values())) == 1 for v in hashes.values()),
              'prior_scoped_execution': all(evidence[k]['executed'] for k in proof['origins'])}
    if identifier == 'A23-02':
        counterexample = local(root, 'deliverables/p13-live/clean-install.json')
        checks['native_install_counterexample_not_open'] = (counterexample.is_file() and
            load_json(counterexample)['installer']['exit_code'] == 0)
    if proof.get('native'):
        raw = load_json(local(root, 'deliverables/p13-live/natural-collaboration.json'))
        checks['natural_native_two_homes'] = evidence['p13-natural-audit']['executed'] and any(
            r['condition'] == 'B05-final' and r['source_before']['matches'] is True
            and r['source_after']['matches'] is True and r['source_unchanged'] is True for r in raw['conditions'])
    return {'checks': checks, 'paths': hashes, 'selectors': selectors,
            'prior_execution_refs': proof['origins'],
            'regression_ref': 'p13-local-regression',
            'native_ref': 'p13-natural-audit' if proof.get('native') else None,
            'scope': '기록된 조건별 경로 + skip 없는 현재 실행 + B05/P13/실행후 hash 결속. 원격/UI로 확장하지 않음'}


def postqa_regression_checks(root, data, manifest=None):
    manifest = manifest if manifest is not None else load_json(local(root, data['snapshot_manifest']))
    snapshot = Path('/private/tmp/xsm-p13-postqa-frozen-bukwksw6')
    paths = manifest['stable_product_paths']
    checks = []
    for row in data['results']:
        allowed = {'Python 3.9.6': '/tmp/p13-postqa39.log', 'Python 3.14.6': '/tmp/p13-postqa314.log'}
        log = Path(allowed.get(row['python'], '/nonexistent-postqa-log'))
        text = log.read_text() if log.is_file() else ''
        checks.append(row['log'] == str(log) and file_sha(log) == row['log_sha256']
                      and re.search(r'^Ran 1667 tests in [0-9.]+s$', text, re.M) is not None
                      and re.search(r'^OK$', text, re.M) is not None
                      and row['tests'] == 1667 and row['result'] == 'OK' and row['exit_code'] == row['skips'] == 0)
    return {'two_exact_runs': len(checks) == 2 and all(checks)
                             and {r['python'] for r in data['results']} == {'Python 3.9.6', 'Python 3.14.6'},
            'exact_snapshot': data['snapshot'] == manifest['snapshot'] == str(snapshot),
            '133_primary_hashes_frozen': data['tested_product_paths'] == len(paths) == len(set(paths)) == 133
                                         and all(manifest['files'][p] == file_sha(local(snapshot, p)) for p in paths),
            'recorded_postrun_unchanged': data['product_source_unchanged_after_runs'] is True and data['changed_paths'] == [],
            'not_whole_plan': data['whole_plan_complete'] is False}


def clean_final_checks(root, data):
    final = load_json(local(root, 'deliverables/p13-live/post-qa-source-manifest.json'))
    post = load_json(local(root, 'deliverables/p13-live/clean-install.diagnostic-post.json'))
    bad = load_json(local(root, 'deliverables/p13-live/clean-install.uninstall-fixed.json'))
    normal = load_json(local(root, 'deliverables/p13-live/clean-install.uninstall-normal.json'))
    mutations = [load_json(local(root, 'deliverables/p13-live/' + name)) for name in
                 ('clean-install.mutations.json', 'clean-install.uninstall-mutation.json')]
    expected = {(runtime, condition) for runtime in ('claude', 'codex') for condition in ('clean', 'existing-stale', 'current')}
    return {'artifact_hashes': len(data['evidence']) == 8 and all(r['sha256'] == file_sha(local(root, r['path'])) for r in data['evidence'].values()),
            'recorded_frozen_install_source': all(h == final['files'].get(p) == file_sha(local(Path(final['snapshot']), p))
                                                 for p, h in data['source'].items())
                                             and final['files']['xsm/cli.py'] == file_sha(local(Path(final['snapshot']), 'xsm/cli.py')),
            '91_each_log_bound': set(data['verification']) == {'3.9', '3.14'} and all(
                r['tests'] == 91 and r['passed'] is True and r['sha256'] == file_sha(Path(r['log']))
                and re.search(r'^Ran 91 tests ', Path(r['log']).read_text(), re.M) is not None
                and re.search(r'^OK$', Path(r['log']).read_text(), re.M) is not None
                for r in data['verification'].values()),
            'six_real_registration_cells': len(post['cases']) == 6
                and {(r['runtime'], r['condition']) for r in post['cases']} == expected
                and all(r['exception'] is None and r['native_config_readback_exit'] == 0
                        and r['native_loaded_installed_prefix'] is True for r in post['cases']),
            'combined_native_registration': post['combined_cli']['exit_code'] == 0
                and len(post['combined_cli']['native_readbacks']) == 2
                and all(r['exit_code'] == 0 and r['native_loaded_private_installed_runtime'] is True
                        for r in post['combined_cli']['native_readbacks']),
            'damaged_inputs_preserved': len(bad['cases']) == 2 and bad['original_failed_fixtures_untouched'] is True
                and all(r['public_exit_code'] == 4 and r['traceback'] is False and r['success_reported'] is False
                        and r['hooks_unchanged'] is True and r['damaged_mcp_preserved'] is True and r['symlink_preserved'] is True
                        for r in bad['cases']),
            'normal_uninstall': normal['install_exit'] == normal['uninstall_exit'] == 0
                and normal['claude_xsm_entry_remaining'] is normal['codex_xsm_entry_remaining'] is False,
            'two_mutations_detected': all(r['detected'] is True for r in mutations),
            'failure_retained_no_clean_LLM': data['original_failure_preserved'] is True
                and data['native_model_calls'] == 0 and data['credential_values_read_or_copied'] is False}


def postclaims_checks(root, data):
    raw_path = local(root, 'deliverables/p13-live/post-claims-collaboration.json')
    raw = load_json(raw_path)
    manifest_path = local(root, 'deliverables/p13-live/post-qa-source-manifest.json')
    manifest = load_json(manifest_path)
    expected_digest = hashlib.sha256(json.dumps(manifest['files'], sort_keys=True).encode()).hexdigest()
    return {'original_raw_preserved': data['raw_result_preserved'] is True and file_sha(raw_path) == data['raw_result_sha256'],
            'private_native_event_hashes': len(data['private_raw_evidence']) == 4
                and all(str(Path(r['path']).resolve()).startswith('/private/tmp/p13-post-claims-')
                        and file_sha(Path(r['path'])) == r['sha256'] for r in data['private_raw_evidence']),
            'executed_runner_preserved': data['runner_sha256'] == file_sha(local(root, 'deliverables/p13-live/post-claims-collaboration.py')),
            'exact_new_snapshot': len(raw['conditions']) == 1 and raw['conditions'][0]['runtime'] == manifest['snapshot']
                and data['snapshot_source_readback']['manifest_sha256'] == expected_digest
                and data['source_manifest_sha256'] == file_sha(manifest_path),
            'two_native_same_goals_no_reruns': data['native_processes_started'] == 2 and data['native_reruns'] == 0
                and data['baseline_executed'] is False and data['goals_unchanged'] is True
                and data['original_launch_and_registration_code_unchanged'] is True,
            'actual_three_math_one_handshake': data['business_goal'] == 'passed-this-sample'
                and data['actual_math_reviews'] == 3 and data['actual_handshakes'] == 1 and len(data['reviews']) == 4
                and all(r['reply_to_matches'] is True and r['actual_native_endpoint_pair_matches'] is True
                        and r['received_actual_body'] is True and r['canonical_state_after'] == 'acknowledged' for r in data['reviews']),
            'direct_ACK_not_extra_inbox': data['initiator_direct_answer_ACKs'] == 4 and data['initiator_unnecessary_inbox_calls'] == 0
                and any(r['role'] == 'initiator' and r['mcp_calls_started'] == 9 and r['inbox_calls'] == 0
                        and len(r['direct_answer_ACKs']) == 4 and all(c['intervening_inbox_calls'] == 0 for c in r['direct_answer_ACKs'])
                        for r in data['actors']),
            'no_controller_relay_or_human_inputs': data['setup_initial_actual_native_registrations'] == 2
                and data['controller_message_calls'] == data['controller_ACK_calls'] == data['controller_index_repairs']
                    == data['additional_human_prompts_clicks_commands_approvals'] == 0,
            'processes_exit_and_sources_unchanged': all(r['exit_code'] == 0 and not r['mcp_errors'] for r in data['actors'])
                and data['profile_unchanged'] is True and data['runtime_source_unchanged'] is True
                and not any(r['live_non_zombie_at_audit'] for r in data['cleanup_readback'])}


def udp_checks(data):
    nodes = data['kernel_preflight']
    return {'two_hosts_kernel_child_deny': nodes['local']['hostname'] != nodes['peer']['hostname']
                and all(nodes[s]['passed'] is True and nodes[s]['denied_udp']['output']['errno'] == 1
                        and nodes[s]['denied_udp']['datagram_received'] is False
                        and nodes[s]['TCP_under_same_profile']['output']['tcp_ok'] is True for s in ('local', 'peer')),
            'only_owned_daemons_not_global_or_cli': data['production_team_or_global_network_policy_changed'] is False
                and data['SSH_and_native_CLI_outside_network_profile'] is True,
            'one_new_native_correlated': data['native_model_attempts_total'] == data['native_model_successes'] == 1
                and data['model_retries'] == data['native_exit_code'] == 0 and data['correlated_reply_and_SHA_confirmed'] is True,
            'both_peer_links_relay': data['relay_link_after_reply'] == ['relay', 'relay']
                and all(any(m['is_me'] is False and m['link'] == 'relay' for m in data['readback'][s]['machines']) for s in ('local', 'peer')),
            'not_connection_only_or_D12': data['relay_connected_alone_not_used_as_proof'] is True
                and data['D12_backend_selection'] == 'unchanged/unselected',
            'unavailable_environment_limit_retained': all(s in data['unexecuted'] for s in
                ('different NAT', 'authenticated HTTPS proxy', 'self-hosted relay', 'global firewall', 'SSH unavailable'))}


def udp_manifest_checks(root, data):
    records = data['files']
    def approved(path):
        resolved = Path(path).resolve()
        return root.resolve() in resolved.parents or str(resolved).startswith('/private/tmp/p11-C-udp')
    return {'76_hash_bound_files': len(records) == 76 and all(approved(r['path'])
                and file_sha(Path(r['path'])) == r['sha256'] for r in records),
            'one_native_not_baseline15': data['native_model_attempts_total'] == 1,
            'no_raw_secrets_published': data['raw_capability_or_key_values_published'] is False}


def factory_handoff_checks(root, data):
    raw = Path('/private/tmp/native-handoff-factory-cytvti8g')
    recorded = load_json(raw / 'source-manifest.json')
    final = load_json(local(root, 'deliverables/p13-live/post-qa-source-manifest.json'))
    return {'same_frozen_source': data['source'] == final['snapshot'] and data['source_unchanged'] is True
                and all(h == final['files'].get(p) == file_sha(local(Path(final['snapshot']), p)) for p, h in recorded.items()),
            'normal_factory_not_disabled': data['native_default_instructions_preserved'] is True
                and data['native_features_disabled_by_evaluator'] == [] and data['env_builder_matches_successful_Actor_start'] is True,
            'actual_claim_withheld_then_owner_dead': data['withheld_actual_claim_response_bytes_forwarded'] == 0
                and data['owner_dead_recovery'] is True and data['old_native_pid'] != data['new_native_pid']
                and data['old_generation'] != data['new_generation'] and data['old_claim_token_sha256'] != data['new_claim_token_sha256']
                and data['original_digest_unchanged'] is True,
            'actual_ACK_reply_and_no_redelivery': data['actual_ACK_observed'] is True
                and data['correlated_native_reply_observed'] is True and data['sender_question_index_replies'] == 1
                and data['ACK_then_actual_inbox_empty'] is True and data['canonical_state_after'] == 'acknowledged',
            'setup_and_control_caveats_retained': data['actual_registration_setup_count'] == 3
                and data['setup_sender_model_calls'] == 1 and data['setup_ordinary_send_by_coordinator'] == 0
                and data['native_CLI_invocations_total'] == 4
                and data['actual_native_turns_started'] == data['actual_native_turns_completed'] == 3
                and data['same_CID_resume_calls'] == 2 and 'active writer' in data['first_resume']
                and bool(data['observer_tail_failure']) and data['no_synthetic_ACK_reply_or_index_repair'] is True
                and data['additional_human_inputs'] == 0,
            'drift_not_falsely_immutable_or_release': data['profile_configuration_unchanged'] is False
                and data['profile_drift_writer'].startswith('unknown') and data['whole_J05_or_release_pass_claimed'] is False}


def factory_manifest_checks(root, data):
    raw = Path('/private/tmp/native-handoff-factory-cytvti8g')
    return {'private_and_public_hashes': len(data['files']) == 95 and data['raw_root'] == str(raw)
                and all((raw in Path(r['path']).resolve().parents or root.resolve() in Path(r['path']).resolve().parents)
                        and file_sha(Path(r['path'])) == r['sha256'] for r in data['files']),
            'tokens_not_published': data['raw_values_published'] is False}


def factory_cancel_count():
    raw = Path('/private/tmp/native-handoff-factory-cytvti8g')
    count = 0
    for folder in ('receiver-initial', 'receiver-resume-verified', 'sender'):
        for line in (raw / folder / 'client-wire.jsonl').read_text().splitlines():
            row = json.loads(line)
            if row.get('method') in ('notifications/cancelled', '$/cancelRequest'):
                count += 1
    return count


def owned_crash_checks(root, data):
    cases = {r['boundary']: r for r in data['cases']}
    expected = {'request-stored', 'acknowledged', 'after-execution', 'result-stored', 'reply-sent'}
    if set(cases) != expected or len(data['cases']) != 5:
        return {'five_actual_controller_SIGKILL_boundaries': False}
    final = load_json(local(root, 'deliverables/p13-live/post-qa-source-manifest.json'))
    return {'five_actual_controller_SIGKILL_boundaries': set(cases) == expected and len(data['cases']) == 5
                and all(r['initial']['returncode'] == -9 and r['boundary_reached'] is True and r['verified'] is True for r in cases.values()),
            'same_313_source_not_new_product': data['frozen'] == final['snapshot'] and data['manifest_checked_files'] == 313
                and data['manifest_match'] is True and data['source_unchanged_after'] is True,
            'five_real_native_children_default_tools': data['executor_mocked'] is False and data['readback_injected'] is False
                and data['total_native_children'] == data['total_native_started_turns'] == data['total_default_tool_calls'] == 5
                and all(r['native_child']['returncode'] == 0 and r['actual_turn_started_events'] == r['terminal_completed_events'] == 1
                        and r['native_default_tool_calls'] == 1 for r in cases.values()),
            'pre_model_cuts_first_execution_only': all(cases[k]['native_turns_at_cut'] == 0 and cases[k]['native_turns_total'] == 1
                and cases[k]['effect_at_cut'] is None for k in ('request-stored', 'acknowledged')),
            'post_execution_unknown_then_real_stdout_no_rerun': cases['after-execution']['recovered']['status'] == 'unknown'
                and cases['after-execution']['fenced_same_id_resume']['status'] == 'unknown'
                and all(cases[k]['native_turns_at_cut'] == cases[k]['native_turns_total'] == 1
                        and cases[k]['same_native_execution_after_recovery'] is True for k in ('after-execution', 'result-stored', 'reply-sent')),
            'request_reply_and_effect_preserved': all(r['immutable_request_preserved'] is True
                and r['before']['id'] == r['final']['id'] and r['before']['digest'] == r['final']['digest']
                and r['effect_final'] == '1' and r['canonical_reply_originals'] == 1 and r['canonical_reply_body_matches'] is True
                and r['final']['status'] == 'reply-stored' and r['final_outcome'] == 'succeeded' for r in cases.values())
                and all(cases[k]['stored_reply_unchanged'] is True and cases[k]['reply_id_unchanged'] is True for k in ('result-stored', 'reply-sent'))
                and cases['reply-sent']['reply_ledger'][0]['resends'] == 2,
            'no_MCP_or_retry_or_UI_ACK_claim': data['total_mcp_calls'] == data['automatic_model_retries'] == 0
                and data['model_permissions_adjusted'] is False
                and all(r['native_mcp_calls'] == 0 and r['remaining_child_alive'] is False and r['remaining_native_process_group'] == []
                        and r['controller_still_present'] is False for r in cases.values())}


def owned_manifest_checks(root, data):
    raw = Path('/private/tmp/p13-owned-crash-jly3ax9r')
    return {'public_results_code_hashes': {'owned-crash-eval.py', 'owned-crash-audit.py', 'owned-crash-results.json'} <= set(data['files']) and all(
                h == file_sha(local(root, 'deliverables/p13-live/' + name)) for name, h in data['files'].items()),
            'private_journal_and_native_hashes': data['raw_root'] == str(raw) and bool(data['private_evidence'])
                and all(h == file_sha(local(raw, p)) for p, h in data['private_evidence'].items()),
            'same_frozen_manifest': data['frozen_manifest'] == 'deliverables/p13-live/post-qa-source-manifest.json'
                and data['frozen_source'] == '/private/tmp/xsm-p13-postqa-frozen-bukwksw6'}


def worktree_checks(root, data):
    raw_path = local(root, 'deliverables/p13-live/worktree-native-20261029-a15.json')
    raw = load_json(raw_path)
    manifest = load_json(local(root, 'deliverables/p13-live/worktree-native-20261029-a15.manifest.json'))
    private = Path('/private/tmp/p13-worktree-native-isksjjba')
    return {'original_auto_result_preserved': file_sha(raw_path) == data['original_result_sha256']
                and data['original_result_preserved'] is True and raw['status'] == data['original_automatic_status'],
            'real_three_native_pairs': data['A15_01_functional_sample'] == 'passed'
                and data['actual_correlated_math_request_reply_pairs'] == len(data['pairs']) == 3
                and all(p['actual_body_matches_response'] is True and p['exact_native_pair'] is True
                        and p['reply_to'] == p['request_id'] and p['reply_canonical_state'] == 'acknowledged' for p in data['pairs']),
            'real_same_git_different_cwd': data['same_git_common'] is True and data['different_actual_native_cwd'] is True
                and data['git_evidence'][0]['common_dir'] == data['git_evidence'][1]['common_dir']
                and data['git_evidence'][0]['cwd'] != data['git_evidence'][1]['cwd'],
            'no_extra_scope_or_human_input': data['permission_API_calls'] == data['permission_shell_calls'] == []
                and data['publications'] == data['selected_collaboration_records'] == data['additional_human_inputs'] == 0
                and data['private_config_file_exists'] is False and data['controller_send_ACK_index_corrections'] == 0,
            'no_native_rerun_or_formal_handshake_invention': data['native_reexecutions'] == 0 and data['native_CLI_invocations'] == 2
                and data['formal_handshakes'] == data['MCP_connect_calls'] == 0,
            'raw_hashes_and_source_preserved': data['source_unchanged'] is True and data['raw_manifest_hashes_match'] is True
                and manifest['raw_root'] == str(private)
                and all(h == file_sha(local(private, p)) for p, h in manifest['files'].items()),
            'profile_guard_limit_retained': data['profile_guard_unchanged'] is False and bool(data['profile_guard_limit'])}


def final_regression_checks(root, data):
    m = load_json(local(root, data['snapshot_manifest']))
    snapshot = Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
    logs = {'Python 3.9.6': '/tmp/p13-receipt-final39.log', 'Python 3.14.6': '/tmp/p13-receipt-final314.log'}
    return {'both_1697_skip0': len(data['results']) == 2 and {r['python'] for r in data['results']} == set(logs)
                and all(r['tests'] == 1697 and r['result'] == 'OK' and r['exit_code'] == r['skips'] == 0
                        and r['log'] == logs[r['python']] and file_sha(Path(r['log'])) == r['log_sha256']
                        and re.search(r'^Ran 1697 tests ', Path(r['log']).read_text(), re.M)
                        and re.search(r'^OK$', Path(r['log']).read_text(), re.M) for r in data['results']),
            'exact_final_snapshot': data['snapshot'] == m['snapshot'] == str(snapshot),
            '135_primary_historical_snapshot_unchanged': data['tested_product_paths'] == len(m['stable_product_paths']) == 135
                and data['product_source_unchanged_after_runs'] is True and data['changed_paths'] == []
                and all(h == file_sha(local(snapshot, p))
                        for p, h in m['files'].items() if p in m['stable_product_paths']),
            'whole_plan_not_claimed': data['whole_plan_complete'] is False}


# Source epochs are selected from verified bytes/logs, never pipeline status prose.
HISTORICAL_MANIFEST = 'deliverables/p13-live/final-source-manifest.json'
DOCTOR_MANIFEST = 'deliverables/p13-live/doctor-privacy-source-manifest.json'
DOCTOR_REGRESSION = 'deliverables/p13-live/doctor-privacy-regression.json'
DOCTOR_V2_MANIFEST = 'deliverables/p13-live/doctor-privacy-v2-source-manifest.json'
DOCTOR_V2_REGRESSION = 'deliverables/p13-live/doctor-privacy-v2-regression.json'


def _ast_members(text):
    result = {}
    def walk(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                key = prefix + node.name
                if isinstance(node, ast.ClassDef):
                    result[key + ':header'] = ast.dump(ast.ClassDef(name=node.name, bases=node.bases,
                        keywords=node.keywords, body=[], decorator_list=node.decorator_list), include_attributes=False)
                    walk(node.body, key + '.')
                else:
                    result[key] = ast.dump(node, include_attributes=False)
    walk(ast.parse(text).body)
    return result


def doctor_delta_checks(root, old, new, *, worker_fixture=False):
    paths = set(old['stable_product_paths']) | set(new['stable_product_paths'])
    changed = {p for p in paths if old['files'].get(p) != new['files'].get(p)}
    allowed = {'xsm/install.py', 'tests/test_install_cli_flow.py'} | ({'tests/test_workers.py'} if worker_fixture else set())
    checks = {'only_doctor_files_changed': bool(changed) and changed <= allowed,
              'same_primary_path_inventory': set(old['stable_product_paths']) == set(new['stable_product_paths'])}
    base, after = Path(old['snapshot']), Path(new['snapshot'])
    a = _ast_members(local(base, 'xsm/install.py').read_text())
    b = _ast_members(local(after, 'xsm/install.py').read_text())
    # Diagnostics may grow private helpers, not installer behavior/public APIs.
    added = set(b) - set(a)
    helper_names = {n for n in added if n.startswith('_') and any(t in n for t in ('diagnos', 'stuck', 'failure'))}
    checks['existing_install_functions_preserved'] = all(b.get(k) == v for k, v in a.items() if k != 'stuck')
    nodes = {n.name: n for n in ast.parse((after/'xsm/install.py').read_text()).body if isinstance(n, ast.FunctionDef)}
    reachable, pending = {'stuck'}, ['stuck']
    while pending:
        name = pending.pop()
        for n in ast.walk(nodes[name]):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in added - reachable:
                reachable.add(n.func.id)
                pending.append(n.func.id)
    checks['stuck_changed_and_only_private_diagnostic_helpers_added'] = a.get('stuck') != b.get('stuck') and added <= helper_names & reachable
    def nondefinitions(path):
        tree = ast.parse(path.read_text())
        return [ast.dump(n, include_attributes=False) for n in tree.body
                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    checks['install_module_nondefinitions_preserved'] = nondefinitions(base/'xsm/install.py') == nondefinitions(after/'xsm/install.py')
    ta = _ast_members((base/'tests/test_install_cli_flow.py').read_text())
    tb = _ast_members((after/'tests/test_install_cli_flow.py').read_text())
    new_tests = set(tb) - set(ta)
    modified = {k for k in ta if ta[k] != tb.get(k)}
    checks['CLI_module_nondefinitions_preserved'] = nondefinitions(base/'tests/test_install_cli_flow.py') == nondefinitions(after/'tests/test_install_cli_flow.py')
    checks['only_doctor_CLI_tests_added_or_changed'] = bool(new_tests or modified) and all(
        (k.split('.')[-1].startswith('test_') or k.split('.')[-1].startswith('_doctor')) and ('doctor' in k or 'stuck' in k)
        for k in new_tests | modified) and not (set(ta) - set(tb))
    if worker_fixture:
        worker = 'tests/test_workers.py'
        before_members = _ast_members((base/worker).read_text())
        after_members = _ast_members((after/worker).read_text())
        method = 'SafetyTest.test_a_parent_goodbye_reaps_once_its_process_is_gone'
        checks['only_one_worker_fixture_method_changed'] = set(before_members) == set(after_members) and {
            k for k in before_members if before_members[k] != after_members[k]} == {method}
        class HomeFixtureOnly(ast.NodeTransformer):
            def visit_With(self, node):
                retained = []
                for item in node.items:
                    call = item.context_expr
                    is_home_patch = (isinstance(call, ast.Call) and len(call.args) == 2 and not call.keywords
                        and ast.dump(call.func) == ast.dump(ast.parse('mock.patch.dict', mode='eval').body)
                        and ast.dump(call.args[0]) == ast.dump(ast.parse('os.environ', mode='eval').body)
                        and isinstance(call.args[1], ast.Dict) and len(call.args[1].keys) == 1
                        and isinstance(call.args[1].keys[0], ast.Constant) and call.args[1].keys[0].value == 'CLAUDE_CONFIG_DIR'
                        and ast.dump(call.args[1].values[0]) == ast.dump(ast.parse('self.tmp', mode='eval').body))
                    if not is_home_patch:
                        retained.append(item)
                node.items = retained
                self.generic_visit(node)
                return node if retained else node.body

            def visit_Dict(self, node):
                self.generic_visit(node)
                pairs = [(k, v) for k, v in zip(node.keys, node.values) if not (
                    isinstance(k, ast.Constant) and k.value in ('config_dir', 'claude_config_dir', 'home', 'CLAUDE_CONFIG_DIR')
                    and isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name)
                    and v.value.id == 'self' and v.attr == 'tmp')]
                node.keys, node.values = [k for k, v in pairs], [v for k, v in pairs]
                return node
        def method_node(path):
            return next(n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.FunctionDef)
                        and n.name == method.split('.')[-1])
        prior_node, new_node = method_node(base/worker), method_node(after/worker)
        checks['worker_assertions_and_logic_preserved_except_home_field'] = ast.dump(prior_node, include_attributes=False) == ast.dump(HomeFixtureOnly().visit(new_node), include_attributes=False)
        v1 = load_json(local(root, DOCTOR_MANIFEST))
        checks['product_and_privacy_tests_identical_to_v1_review'] = all(new['files'][p] == v1['files'][p]
            for p in ('xsm/install.py', 'tests/test_install_cli_flow.py'))
    return checks


def doctor_regression_checks(root, data, manifest, *, manifest_ref=DOCTOR_MANIFEST):
    rows = data.get('results', [])
    snapshot = Path(manifest['snapshot'])
    count = {r.get('tests') for r in rows}
    old_snapshot = Path(load_json(local(root, HISTORICAL_MANIFEST))['snapshot'])
    old_tests = _ast_members((old_snapshot/'tests/test_install_cli_flow.py').read_text())
    new_tests = _ast_members((snapshot/'tests/test_install_cli_flow.py').read_text())
    expected_count = 1697 + sum(k not in old_tests and k.split('.')[-1].startswith('test_') for k in new_tests)
    checks = {'exact_new_manifest': data.get('snapshot_manifest') == manifest_ref
                  and data.get('snapshot') == str(snapshot) and str(snapshot) != load_json(local(root, HISTORICAL_MANIFEST))['snapshot'],
              'both_Python_full_runs': len(rows) == 2 and {tuple(re.findall(r'\d+', r.get('python', ''))[:2]) for r in rows}
                  == {('3', '9'), ('3', '14')},
              'same_actual_test_count_not_old_execution': len(count) == 1 and count == {expected_count} and expected_count > 1697,
              'two_passed_skip0_exact_logs': bool(rows) and all(r.get('result', r.get('summary')) == 'OK' and r.get('exit_code') == 0
                  and r.get('skips') == 0 and Path(r['log']).is_file()
                  and file_sha(Path(r['log'])) == r['log_sha256']
                  and re.search(r'^Ran %d tests ' % r['tests'], Path(r['log']).read_text(), re.M)
                  and re.search(r'^OK$', Path(r['log']).read_text(), re.M) for r in rows),
              'postrun_source_unchanged': ((data.get('product_source_unchanged_after_runs') is True
                  and data.get('changed_paths') == [] and data.get('tested_product_paths') == len(manifest['stable_product_paths']))
                  or (bool(data.get('source_binding')) and all(data['source_binding'].get(k) is True for k in (
                      'primary_current_equals_frozen_after_run', 'primary_current_unchanged_since_launch',
                      'primary_frozen_unchanged_since_launch', 'all315_frozen_unchanged_after_run',
                      'original315_snapshot_unchanged', 'original1697_artifacts_unchanged')))),
              'snapshot_all_bytes_match': bool(manifest['files']) and all(file_sha(local(snapshot, p)) == h for p, h in manifest['files'].items()),
              'current_primary_exact': all(file_sha(local(root, p)) == manifest['files'].get(p) for p in manifest['stable_product_paths']),
              'not_whole_plan': data.get('whole_plan_complete') is False}
    return checks


_BUILD_SOURCE_EPOCH = ContextVar("reason_audit_build_epoch", default=None)


def source_epoch(root):
    cached = _BUILD_SOURCE_EPOCH.get()
    if cached is not None and cached[0] == root.resolve():
        return cached[1]
    return _read_source_epoch(root)


def _read_source_epoch(root):
    historical = load_json(local(root, HISTORICAL_MANIFEST))
    current_old = all(file_sha(local(root, p)) == historical['files'][p] for p in historical['stable_product_paths'])
    old_valid = all(final_regression_checks(root, load_json(local(root, 'deliverables/p13-live/final-regression.json'))).values())
    result = {'manifest_path': HISTORICAL_MANIFEST, 'manifest': historical,
              'regression_ref': 'final-regression', 'regression_path': 'deliverables/p13-live/final-regression.json',
              'status': 'historical1697-current' if current_old and old_valid else 'doctor-privacy-pending',
              'ready': bool(current_old and old_valid), 'historical1697_valid': old_valid,
              'candidate_manifest': DOCTOR_MANIFEST, 'candidate_regression': DOCTOR_REGRESSION,
              'doctor_checks': {}, 'delta_checks': {}}
    # A started/new candidate supersedes old readiness, including incomplete files.
    candidates = [(DOCTOR_V2_MANIFEST, DOCTOR_V2_REGRESSION), (DOCTOR_MANIFEST, DOCTOR_REGRESSION)]
    selected = next(((m, r) for m, r in candidates if local(root, m).is_file() or local(root, r).is_file()), None)
    if selected:
        manifest_ref, regression_ref = selected
        result.update(candidate_manifest=manifest_ref, candidate_regression=regression_ref)
        result.update(ready=False, status='doctor-privacy-v2-pending' if manifest_ref == DOCTOR_V2_MANIFEST else 'doctor-privacy-v1-pending')
        try:
            new = load_json(local(root, manifest_ref))
            result['candidate_snapshot'] = new['snapshot']
            result['delta_checks'] = doctor_delta_checks(root, historical, new, worker_fixture=manifest_ref == DOCTOR_V2_MANIFEST)
            full = load_json(local(root, regression_ref))
            result['doctor_checks'] = doctor_regression_checks(root, full, new, manifest_ref=manifest_ref)
            result['observed_full_status'] = full.get('status')
            if any(r.get('exit_code', 0) != 0 for r in full.get('results', [])):
                result['status'] = 'doctor-privacy-v2-failed' if manifest_ref == DOCTOR_V2_MANIFEST else 'doctor-privacy-v1-failed'
            if all(result['delta_checks'].values()) and all(result['doctor_checks'].values()):
                result.update(ready=True, status='doctor-privacy-v2-current' if manifest_ref == DOCTOR_V2_MANIFEST else 'doctor-privacy-current', manifest_path=manifest_ref,
                              manifest=new, regression_ref='doctor-privacy-v2-regression' if manifest_ref == DOCTOR_V2_MANIFEST else 'doctor-privacy-regression', regression_path=regression_ref)
        except (OSError, ValueError, KeyError, TypeError, SyntaxError) as exc:
            result['pending_reason'] = '준비/검사 미완: ' + type(exc).__name__
    return result


def epoch_summary(epoch):
    return {k: v for k, v in epoch.items() if k != 'manifest'}


def scoped_epoch_checks(root, cases, paths=()):
    epoch = source_epoch(root)
    manifest = epoch['manifest']
    wanted = set(paths) | set(cases)
    if not wanted:
        wanted = {'xsm/mcp.py', 'xsm/receive.py', 'xsm/send.py', 'xsm/questions.py',
                  'xsm/registry.py', 'xsm/config.py', 'xsm/handoff.py', 'xsm/inbox.py'}
    return {'scoped_dependency_hashes': all(file_sha(local(root, p)) == manifest['files'].get(p) for p in wanted),
            'specific_executed_selectors': all(all(name in {n.name for n in ast.walk(ast.parse(local(root, p).read_text()))
                if isinstance(n, ast.FunctionDef)} for name in names) for p, names in cases.items())}


def strict_review_checks(root, data):
    manifest = load_json(local(root, 'deliverables/p13-live/strict-review-native-manifest.json'))
    original = load_json(local(root, 'deliverables/p13-live/strict-review-native-results.json'))
    rows = data['rounds']
    return {'same_condition_full_trace': data['functional_criterion_passed'] is True
                and len(data['checks']) == 23 and all(v is True for v in data['checks'].values())
                and len(rows) == 4 and len({r['request_id'] for r in rows}) == 4,
            'real_three_review_and_same_body_repeat': len({r['request_body'] for r in rows[:3]}) == 3
                and rows[2]['request_body'] == rows[3]['request_body']
                and all(r['final'] and r['outcome'] == 'succeeded' and r['reply_to'] == r['request_id']
                    and r['request_ACK'] and r['reply_ACK'] for r in rows),
            'same_ID_recovery_no_invented_success': data['same_ID_resend']['count'] == 1
                and data['same_ID_resend']['id'] == rows[3]['request_id']
                and data['private_policy'] == {'traffic_control': {'mode': 'strict', 'window_seconds': 60, 'max_same_body': 1}}
                and data['cleanup_verified']['remaining'] == 0,
            'original_bytes_bound': data['original_runtime_result_sha256'] == file_sha(local(root, 'deliverables/p13-live/strict-review-native-results.json'))
                and all(file_sha(local(root, p)) == h for p, h in manifest['files'].items())
                and all(file_sha(local(Path(original['root']), p)) == h for p, h in manifest['raw_evidence'].items()),
            'limits_preserved': data['profile_guard_unchanged'] is False
                and data['native_lifecycle']['reviewer_self_terminated'] is False
                and data['previous_pairs_reused_for_success'] is False and data['automatic_model_actor_retries'] == 0}


def evidence_path(root, path):
    return Path(path) if Path(path).is_absolute() else local(root, path)


def directory_extraction_checks(root, data):
    selectors = data['source_binding']['selectors']
    selected = []
    frozen = Path(data['source_binding']['snapshot'])
    for row in selectors:
        path = Path(row['file'])
        text = path.read_text()
        node = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef) and n.name == row['name'])
        # Original checker hashes exact source slices, including the final newline.
        fragment = '\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])
        expected = row['function_sha256']
        selected.append(file_sha(path) == row['file_sha256'] and
                        expected == hashlib.sha256(fragment.strip().encode()).hexdigest())
    wire = data['native_wire_checks']
    rpc_bound = []
    for row in wire:
        requests = [json.loads(line) for line in evidence_path(root, row['client_wire']['path']).read_text().splitlines()]
        responses = [json.loads(line) for line in evidence_path(root, row['server_wire']['path']).read_text().splitlines()]
        request = next((v for v in requests if v.get('id') == row['rpc_id'] and v.get('method') == 'tools/call'), {})
        response = next((v for v in responses if v.get('id') == row['rpc_id'] and 'result' in v), {})
        encode = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()
        rpc_bound.append(request.get('params', {}).get('name') == row['tool'] and encode(request) == row['request_sha256']
                         and encode(response) == row['wire_response_sha256'])
    return {'exact_criterion_cells_mapped': data['criterion'] == 'A17-04' and data['closure_possible'] is True
                and data['remaining_exact_criterion_cells'] == [] and {r['level'] for r in data['level_mapping']} == {'fixture', 'harness', 'review'},
            'selectors_and_original_evidence_hashes': len(selectors) == 22 and all(selected)
                and all(file_sha(evidence_path(root, r['path'])) == r['sha256'] for r in data['evidence_files']),
            'real_unknown_metadata_basic_communication': len(wire) == 9 and all(rpc_bound) and all(r['isError'] is False
                and (r.get('matches_summary_response_sha256') is True or r['tool'] == 'xsm_send')
                and all(file_sha(evidence_path(root, r[k]['path'])) == r[k]['sha256'] for k in ('client_wire', 'server_wire')) for r in wire)
                and all(r['final'] is True and r['final_outcome'] == 'succeeded' and r['reply_count'] == 1 for r in data['actual_final_status']),
            'human_sample_not_publication_consent': data['human_review']['publication_permission'] is False
                and bool(data['human_review']['answer']) and data['retained_native_limitations']['old_report_unchanged'] is True,
            'not_all_harness_or_UI_invention': data['safety']['new_models'] == data['safety']['source_plan_ledger_writes'] == 0
                and data['retained_native_limitations']['actual_ACK_ID_count'] == 0}


def doctor_opus_checks(root, review, *, raw=None):
    expected = 'claude-opus-5-5'
    path = Path(review['raw_private_root'])/'review-raw.json'
    payload = load_json(path) if raw is None else raw
    rows = payload if isinstance(payload, list) else [payload]
    init = [r for r in rows if r.get('type') == 'system' and r.get('subtype') == 'init']
    final = [r for r in rows if r.get('type') == 'result']
    return {'requested_and_reported_exact_Opus55': review['requested_model'] == review['actual_init_model'] == expected
                and review['actual_modelUsage_IDs'] == [expected],
            'original_raw_result_SHA': file_sha(path) == review['raw_result_sha256'],
            'actual_raw_init_and_modelUsage_exact_Opus55': len(init) == len(final) == 1
                and init[0].get('model') == expected and rows[-1] is final[0]
                and set(final[0].get('modelUsage', {})) == {expected}
                and final[0].get('subtype') == 'success' and not final[0].get('is_error', False)}


def doctor_privacy_native_checks(root, data):
    base = 'deliverables/p13-live/doctor-privacy-native-20261029-828fa71c/'
    manifest = load_json(local(root, base+'manifest.json'))
    review = load_json(local(root, 'deliverables/p13-live/g10-doctor-privacy-opus-review.json'))
    v1 = load_json(local(root, DOCTOR_MANIFEST))
    index = load_json(Path(manifest['private_index']['path']))
    return {'real_postfix_diagnostic_and_survival': data['exit_code'] == 0 and data['CLI_invocations'] == 1
                and data['native_registration']['actual_native_DB_and_rollout_header_verified'] is True
                and data['native_registration']['actual_OS_native_ancestor_verified'] is True
                and all(v is True for v in data['runtime_survival'].values()),
            'markers_and_original_ledger_preserved': len(data['synthetic_nonoutput']) == 7
                and data['leaked_marker_count'] == 0 and all(r['in_stdout'] is r['in_stderr'] is False for r in data['synthetic_nonoutput'].values())
                and data['ledger']['files'] == 5 and data['ledger']['bytes_before_after_identical'] is data['ledger']['record_set_unchanged'] is True,
            'exact_captures_bound': file_sha(Path(manifest['private_index']['path'])) == manifest['private_index']['sha256']
                and all((r.get('role') == 'protected-negative-original' and r.get('post_read') is False and r.get('post_hash') is False
             and len(r.get('setup_sha256','')) == 64) if r.get('role') == 'protected-negative-original' else
            file_sha(Path(index[r['private_file_id']])) == r['sha256'] for r in manifest['private_files'])
                and all(file_sha(local(root, base+r['path'])) == r['sha256'] for r in manifest['public_files'])
                and all(file_sha(Path(r['path'])) == r['sha256'] for r in data['streams'].values()),
            'review_exact_product_delta_not_worker_fixture_review': review['process_exit_code'] == 0
                and review['Medium_plus_findings'] == [] and review['model_review_count'] == 1 and review['model_retries'] == 0
                and review['mcp_servers'] == [] and all(doctor_opus_checks(root, review).values())
                and all(row['actual'] == row['expected'] == v1['files'][path] for path, row in review['source_after_review'].items()),
            'known_limits_not_universal_privacy_or_authority': data['real_credentials_loaded_or_compared'] is False
                and data['native_registration']['authority_or_caller_certainty_claimed'] is False
                and data['signals_login_wake_grants_profile_writes_by_driver'] == data['credential_file_reads_by_driver'] == 0
                and data['whole_plan_complete'] is False}


def capacity_rebinding_checks(root, data):
    base = 'deliverables/p13-live/independent-review-native-20261029-final/'
    capacity = load_json(local(root, 'deliverables/p13-live/owned-capacity-native-20261029-bundle/check.json'))
    independent = load_json(local(root, base+'check.json'))
    old = data['original_journal_binding']
    journal = load_json(Path(old['path']))
    old_files = {r['path']: r['sha256'] for r in capacity['files']}
    mismatches = [p for p, h in old_files.items() if file_sha(Path(p)) != h]
    rows = data['stage_A_request_rows']
    projected = []
    for row in rows:
        previous = load_json(Path(row['historical_result_snapshot']))
        projection = {k: v for k, v in previous.items() if k not in {
            'context', 'persisted', 'accepted', 'side_effects_exactly_once', 'slot_occupied', 'execution_state', 'status'}}
        projection['state'] = previous['status']
        live = journal['requests'][row['request_id']]
        digest_value = hashlib.sha256(json.dumps(live, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        projected.append(len(projection) == len(live) == 22 and projection == live
            and row['persisted_fields_compared'] == 22 and row['changed_persisted_fields'] == []
            and row['snapshot_sha256'] == old_files.get(row['historical_result_snapshot']) == file_sha(Path(row['historical_result_snapshot']))
            and digest_value == row['historical_persisted_projection_sha256'] == row['current_request_canonical_sha256'])
    return {'whole_journal_mismatch_not_hidden': old['whole_journal_hash_matches_original'] is False
                and old['old_whole_journal_snapshot_found'] is False and mismatches == [old['path']]
                and file_sha(Path(old['path'])) == old['current_sha256'] != old['historical_expected_sha256'],
            'ten_by_22_exact_persisted_fields': len(rows) == 10 and all(projected)
                and len(journal['requests']) == 13 and len(data['stage_B_additions']['additional_request_ids']) == 3,
            '78_old_36_new_raw_exact': len(old_files) == 79 and len(mismatches) == 1
                and data['integrity_recheck']['capacity']['matching'] == 78
                and data['integrity_recheck']['independent']['matching'] == 36
                and len(independent['files']) == 36 and all(file_sha(Path(r['path'])) == r['sha256'] for r in independent['files'])
                and all(file_sha(evidence_path(root, r['path'])) == r['sha256'] for r in data['evidence_bindings']),
            'functional_limits_retained': all(v is True for v in data['functional_revalidation'].values())
                and data['stage_A_request_subset_digest']['not_a_reconstruction_of_original_full_journal'] is True
                and data['preservation']['original_manifest_or_check_reissued'] is False
                and data['new_models'] == data['new_experiments'] == 0}

# 공통 byte/selector 검증. ledger baseline은 refresh에 따라 바뀌는 문맥이며 실행 증거가 아니다.
def evidence_rows_bound(root, rows):
    return bool(rows) and all(file_sha(evidence_path(root, r['path'])) == r['sha256'] for r in rows
        if not (r.get('kind') == 'read-only-ledger-baseline' and r['path'] in (LEDGER, OLD_BASE + 'completion-ledger.json')))


def scoped_ast_node(path, name):
    parts = name.split('.')
    nodes = ast.parse(Path(path).read_text()).body
    node = None
    for part in parts:
        node = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == part), None)
        if node is None:
            return None
        nodes = getattr(node, 'body', [])
    return node


def selector_rows_bound(root, rows):
    checks = []
    for r in rows:
        path = r.get('path', r.get('file'))
        file = evidence_path(root, path)
        expected = r.get('snapshot_file_sha256', r.get('source_sha256'))
        selector = r['selector']
        module = Path(path).stem
        suffix = selector.split(module+'.', 1)[-1]
        node = scoped_ast_node(file, suffix)
        executions = r.get('actual_1700_verbose_OK_lines', r.get('executions', []))
        passed = node is not None and file_sha(file) == expected and len(executions) == 2
        for execution in executions:
            log = execution.get('log')
            if log:
                lines = Path(log).read_text().splitlines()
                hits = execution['passed_line_matches']
                passed = passed and bool(hits) and all(lines[h['line']-1] == h['text'] and
                    (h['text'].endswith('ok') or ('continuation_line' in h and
                     lines[h['continuation_line']-1] == h['continuation_text'] and h['continuation_text'].endswith('ok'))) for h in hits)
            else:
                # policy artifact는 양 log의 정확한 line SHA를 기록한다.
                epoch = source_epoch(root)
                full = load_json(local(root, epoch['regression_path']))
                item = next(x for x in full['results'] if x['python'] == execution['python'])
                line = Path(item['log']).read_text().splitlines()[execution['line']-1]
                passed = passed and file_sha(Path(item['log'])) == execution['log_sha256'] and line.endswith('ok') and hashlib.sha256(line.encode()).hexdigest() == execution['line_sha256']
        checks.append(passed)
    return bool(checks) and all(checks)


def indexed_manifest_bound(root, base):
    manifest = load_json(local(root, base+'manifest.json'))
    directory = Path(manifest['root'])
    index_path = directory/'raw-index.private.json'
    index = load_json(index_path)
    return (manifest['negative_original_content_never_postread'] is True and file_sha(index_path) == manifest['private_index_sha256'] and
        all((r.get('role') == 'protected-negative-original' and r.get('post_read') is False and r.get('post_hash') is False
             and len(r.get('setup_sha256','')) == 64) if r.get('role') == 'protected-negative-original' else
            file_sha(Path(index[r['private_file_id']])) == r['sha256'] for r in manifest['private_files']) and
        all(file_sha(local(root, base+r['path'])) == r['sha256'] for r in manifest['public_files']))


def parity_native_checks(root, data):
    base = 'deliverables/p13-live/persistent-parity-native-v3-20261029'
    manifest = load_json(local(root, base+'.audit-manifest.json'))
    raw = Path(manifest['raw_root'])
    records = {r['id']: r for r in [load_json(p) for p in (raw/'state/handoffs').glob('*/*.json')]}
    digests = []
    content = []
    for pair in data['pairs'].values():
        for key in ('request_id', 'reply_id'):
            row = records[pair[key]]
            identity = row['identity']
            canon = {k: v for k, v in identity.items() if k not in ('from', 'to')}
            for side in ('from', 'to'):
                value = identity.get(side)
                canon[side] = {k: value.get(k) for k in ('ref', 'runtime', 'home', 'conversation')} if isinstance(value, dict) else None
            calculated = hashlib.sha256(json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8', 'replace')).hexdigest()
            digests.append(row['state'] == 'acknowledged' and row['digest'] == calculated == pair['request_digest' if key == 'request_id' else 'reply_digest'])
        request, reply = records[pair['request_id']], records[pair['reply_id']]
        content.append(reply['message']['reply_to'] == pair['reply_to'] == pair['request_id']
                       and request['message']['sender']['session_id'] == pair['sender_CID']
                       and request['receiver']['session_id'] == pair['receiver_CID']
                       and hashlib.sha256(request['message']['body'].encode()).hexdigest() == data['input_body_raw_SHA'])
    copies = data['received_copies']
    answers = {surface: json.loads(records[pair['reply_id']]['message']['body']) for surface,pair in data['pairs'].items()}
    body_marker = re.search(r'BODY_[0-9a-f]+',(raw/'body.txt').read_text()).group()
    material = (raw/'material.md').read_bytes()
    file_marker = re.search(rb'FILE_[0-9a-f]+',material).group()
    actual_answers = (answers['CLI plain'] == answers['MCP plain'] and answers['CLI file'] == answers['MCP file']
        and all(v['verdict']=='reject' and v['correct_sum']==4 and v['body_marker']==body_marker for v in answers.values())
        and all(v['file_sha256']==data['input_file_SHA']==hashlib.sha256(material).hexdigest()
                and v['file_marker_sha256']==hashlib.sha256(file_marker).hexdigest()
                for k,v in answers.items() if k.endswith('file')))
    return {'four_actual_pairs_eight_ACKs_and_digests': set(data['pairs']) == {'CLI plain','CLI file','MCP plain','MCP file'}
                and len(digests) == 8 and all(digests) and all(content)
                and all(p['request_and_reply_acknowledged'] for p in data['pairs'].values()),
            'body_and_content_parity_not_full_hash_equality': actual_answers and data['plain_answers_equal'] is data['file_answers_equal'] is True
                and data['canonical_digests_all_valid'] is True and data['canonical_digests_equal_across_requests'] is False
                and len({p['request_digest'] for p in data['pairs'].values()}) == 4
                and len(data['actual_file_reads']) == len(copies) == 2
                and {c['manifest_owner']['session_id'] for c in copies} == {data['host']['actual_CID'],data['child_CID']}
                and {c['files'][0]['input_source'] for c in copies} == {'cli-os-read','caller-inline'}
                and all(r['actual_content_SHA'] == data['input_file_SHA'] for r in data['actual_file_reads'])
                and all(c['body_binding_SHA'] == data['input_body_semantic_SHA'] and c['owner']['session_id'] == data['receiver_CID']
                        and len(c['files']) == 1 and c['files'][0]['sha256'] == data['input_file_SHA'] for c in copies),
            'exact_raw_and_audit_hashes': all(file_sha(local(raw,p)) == h for p,h in manifest['files'].items())
                and all(file_sha(local(root,'deliverables/p13-live/'+p)) == h for p,h in manifest['public_files'].items()),
            'real_host_and_child_not_fabricated': data['host']['who_exit'] == 0 and data['host']['markers_absent'] is True and data['source315_verified'] is True and data['new_native_launches']==2
                and data['host']['who']['session_id'] == data['host']['actual_CID']
                and data['host']['actual_CID'] != data['child_CID'] != data['receiver_CID']
                and data['host_session_preserved'] is True,
            'original_collector_and_runtime_limits_retained': data['collector_original_status'] == 'original-failure-preserved-no-retry'
                and bool(data['collector_failure']) and data['child_turns'] == [2,1]
                and data['previous_conditions'] == 5 and data['previous_launches'] == 9
                and data['total_conditions'] == 6 and data['total_launches'] == 11
                and data['automatic_model_retries'] == 0 and all(not r['same_generation_alive'] for r in data['cleanup'])
                and data['product_hash_unchanged'] is True}


def exclusion_native_checks(root, data, identifier):
    base = 'deliverables/p13-live/exclusion-cli-native-20261029-6c6ee4c8/'
    reused = load_json(local(root,base+'reused-evidence.json'))
    positive = load_json(local(root,'deliverables/p13-live/material-boundary-native-20261029-a30cd9e0/summary.json'))
    result = {'exact_current_caller_negative_and_raw': indexed_manifest_bound(root,base)
                and data['source_frozen315_unchanged'] is True and data['preexisting_current_primary_difference'] == ['tests/test_workers.py']
                and data['sandbox_markers_cleared_or_added'] is False,
              'no_original_read_copy_body_or_posthash': data['protected_source_open_events'] == data['protected_original_postread_or_posthash'] == 0
                and all(v == 0 for v in data['counts_each_state'].values())
                and all(r['stat_preserved'] and r['post_run_hash'] == 'not read' for r in data['originals'].values()),
              'synthesis_and_inline_limits_preserved': data['new_models'] == data['new_native_TUIs'] == 0
                and all(file_sha(local(root,r['path'])) == r['sha256'] for r in reused['evidence'])
                and reused['file_fixture_source_unchanged_across_freezes'] is True
                and any('inline' in line and 'source-path' in line for line in data['limits'])}
    if identifier == 'A17-05':
        p = data['A17_05']
        result['same_realpath_registration_and_discovery_excluded'] = p['same_native_cwd_realpath'] is p['symlink_alias_only'] is True and p['registry_upsert_both_rejected'] is p['preexisting_self_pointer_bytes_preserved'] is True and p['discovery']['candidates'] == [] and p['CLI_capture_API_rejections'] == ['excluded-or-unknown']*2 and p['in_process_CLI_parser_executed'] is False
    else:
        p = data['A19_03']
        result['real_API_and_CLI_parser_denials'] = p['direct_files_prepare_cli_codes'] == ['excluded-or-unknown','credential-path'] and len(p['real_cli_main_parser']) == 2 and all(r['exit_code'] == 2 and r['status'] == 'attachment-error' and r['body_sent'] is False and r['manifest_id'] is None and r['natural_identity_context']['sure'] is True for r in p['real_cli_main_parser'])
        result['prior_positive_material_reads_not_just_storage'] = positive['actual_receiver_entry_reads'] == 3 and positive['OS_mode000_errno13'] is True and positive['actual_ACK_IDs'] == 2 and positive['correlated_reply_to_preserved'] is True
    return result


def delivery_rebinding_checks(root, data, identifier):
    assessment = next(r for r in data['assessments'] if r['id'] == identifier)
    source_rows = data['source_current_binding']
    sources = {r['sha256']: evidence_path(root,r['path']) for r in data['evidence_files'] if r['kind'] == 'actual-native-source'}
    ast_checks = []
    for row in source_rows:
        current = local(root,row['path'])
        previous = sources[row['historical_file_sha256']]
        before = scoped_ast_node(previous,row['function'])
        after = scoped_ast_node(current,row['function'])
        equal = ast.dump(before,include_attributes=False) == ast.dump(after,include_attributes=False)
        allowed = False
        if not equal and row['function'] == 'take_inbox_claims':
            class PassiveRouteOnly(ast.NodeTransformer):
                def visit_BoolOp(self,node):
                    self.generic_visit(node)
                    expected = ast.dump(ast.parse("record.get('delivery_route') != 'mcp-inbox'",mode='eval').body)
                    if isinstance(node.op,ast.And):
                        node.values = [n for n in node.values if ast.dump(n) != expected]
                    return node
            allowed = ast.dump(before,include_attributes=False) == ast.dump(PassiveRouteOnly().visit(after),include_attributes=False)
        ast_checks.append(file_sha(current) == row['v2_current_file_sha256'] and row['function_ast_equal'] is equal and (equal or allowed))
    common = {'criterion_levels_not_expanded': assessment['verdict'] == 'criterion-closeable-by-bound-level-combination' and assessment['mandatory_missing_cells'] == [] and {r['level'] for r in assessment['levels']} == {'fixture','subprocess','harness'},
              '25_executed_selectors_and_source_AST': len(data['selectors']) == 25 and data['selector_binding_failures'] == [] and selector_rows_bound(root,data['selectors']) and all(ast_checks),
              '263_native_raw_plus_other_source_hashes': evidence_rows_bound(root,data['evidence_files'])
                and [(r['total'],r['matching'],r['mismatches']) for r in data['native_manifest_integrity']] == [(95,95,[]),(168,168,[])],
              'original_limits_not_hidden': data['new_models'] == data['new_experiments'] == data['new_tests_run'] == 0
                and data['native_handoff']['observed_native_cancel_notifications'] == 0
                and data['source_delta_accounting']['factory_take_inbox_claims_ast_changed'] is True}
    if identifier == 'A18-01':
        p=data['typed_native_fallback']
        common['actual_typed_queue_failure_no_runtime_success'] = p['summary_declared_count'] == p['raw_revalidated_count'] == len(p['rows']) == 8 and all(r['queued_ok'] is r['sender_ledger_runtime_reached'] is False and r['delivery_route']=='mcp-inbox' and r['canonical_state']=='acknowledged' for r in p['rows'])
    elif identifier == 'A18-02':
        p=data['native_handoff']
        common['actual_termination_recovery_ACK_not_synthetic_cancel'] = p['withheld_actual_response_bytes'] == 0 and p['synthetic_result'] is False and p['owner_dead_recovery'] is p['actual_ACK'] is p['correlated_reply'] is p['post_ACK_actual_inbox_empty'] is True
    else:
        p=data['native_upgrade'];u=p['upgrade'];protection=p['protection']
        common['actual_old_native_live_across_upgrade_and_reply'] = u['old_snapshot_exists'] is u['source_ids_differ'] is u['after_prune']['native_process_alive'] is u['after_prune']['same_mcp_generation_alive'] is True and u['removed'] == [] and p['reply_before']['sender_native'] == p['reply_after']['sender_native'] == p['old_native_cid'] and p['reply_before']['id'] != p['reply_after']['id'] and protection['settings_unchanged'] is protection['credential_metadata_unchanged'] is protection['old_runtime_unchanged'] is True
    return common


def policy_rebinding_checks(root, data, identifier):
    p=data['conditions'][identifier]
    source_ok=[]
    for row in p['product_selectors']:
        file=local(root,row['path']);node=scoped_ast_node(file,row['name'])
        old=Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')/row['path'];prior=scoped_ast_node(old,row['name'])
        source_ok.append(file_sha(file)==row['snapshot_sha256'] and ast.dump(node,include_attributes=False)==ast.dump(prior,include_attributes=False) and row['AST_equal_to_receipt315'] is True)
    result={'original_levels_and_formal_gates_preserved': p['whole_condition'].startswith('partial-') and p['formal_blocked_gates'] == (['G07'] if identifier in ('A16-07','A22-02') else ['G12']) and data['safety']['formal_gate_waivers'] == 0,
            'exact_executed_selectors_and_scoped_source': selector_rows_bound(root,p['fixture_selectors']) and all(source_ok),
            'retained_evidence_hashes': all(file_sha(local(root,path))==h for path,h in data['evidence_sha256'].items()),
            'no_new_runs_or_UI_credit': data['safety']['new_models']==data['safety']['new_experiments']==data['safety']['new_test_runs']==data['safety']['new_UI_success_claims']==0}
    if identifier=='A16-07':
        rows=p['native_proof'];result['actual_partial_final_original_ID_bound'] = bool(rows) and all(file_sha(Path(r['question_record']))==r['raw_sha256'] and any(x['outcome'] is None for x in r['replies']) and any(x['outcome']=='succeeded' for x in r['replies']) and all(file_sha(Path(x['canonical_path']))==x['raw_sha256'] and x['acknowledged'] for x in r['replies']) for r in rows)
    elif identifier=='A22-02':
        result['peer_approval_not_same_uid_protection_or_actual_UI'] = p['context_native_replay']['authorization'] is p['context_native_replay']['permission_changed'] is False and p['context_native_replay']['replay_blocked'] is True and p['review']=='proven-local-readonly-review'
    else:
        result['caller_supplied_signature_and_recovery_limits'] = p['review']=='proven-local-readonly-review' and any('caller-provided' in s for s in p['limits'])
    return result


def topology_partial_checks(root,data):
    def walk(v):
        if isinstance(v,dict):
            if 'path' in v and 'sha256' in v:yield v
            for x in v.values():yield from walk(x)
        elif isinstance(v,list):
            for x in v:yield from walk(x)
    return {'existing_three_topologies_raw_bound': evidence_rows_bound(root,list(walk({k:data[k] for k in ('siblings','different_parents','ordinary')}))),
            'distinct_Gitcommon_missing_not_fabricated': data['whole_condition_complete'] is False and data['crossrepo']['distinct_historical_Gitcommon_bound'] is False and data['crossrepo']['full_endpoint_CID_cwd_bound'] is False and len(data['missing_cells'])==1 and data['missing_cells'][0]['id']=='approved-distinct-Gitcommon-native-pair',
            'no_new_run_or_authority': all(v==0 for v in data['safety'].values())}


def different_parent_checks(data):
    relations = data['parent_relations']
    return {'provider_two_real_parents': len(relations) == 2
                and len({r['actual_parent_thread_id_hash'] for r in relations}) == 2
                and all(r['parent_CID_hash'] == r['actual_parent_thread_id_hash'] for r in relations)
                and data['distinct_parent_thread_ids_proven'] is True and data['distinct_real_native_PIDs'] is True,
            'final_source_and_setup': data['source'] == '/private/tmp/xsm-final-receipt-frozen-i3u9pms3'
                and data['source_manifest_files_verified'] == 315 and data['primary_paths'] == 135
                and data['source_unchanged'] is True and data['native_parent_CLI_launches'] == data['actual_native_children'] == 2
                and data['initial_real_registration_setup_count'] == 4,
            'eight_immutable_auto_MCP_ACKs': data['actual_claim_ACK_IDs'] == len(data['messages']) == data['typed_auto_fallbacks'] == 8
                and all(r['delivery_route'] == 'mcp-inbox' and r['typed_auto_fallback_observed'] is True
                        and r['actual_claim_ACK'] is True and r['immutable_digest_valid'] is True
                        and r['native_queued'] is r['native_wake'] is False for r in data['messages']),
            'three_final_math_and_two_incoming_reads': len(data['question_roundtrips']) == 3
                and all(r['original_reply_to_preserved'] is True and r['final_outcome'] == 'succeeded' for r in data['question_roundtrips'])
                and len(data['incoming_file_content_reads']) == 2
                and all(r['content_SHA_matches'] is True for r in data['incoming_file_content_reads']),
            'no_parent_relay_or_proxy_injection': all(v == 0 for v in data['parent_xsm_calls'].values())
                and data['parent_body_relay_or_manual_ACK_by_evaluator'] is data['proxy_meta_ID_results_ACKs_modified'] is False
                and data['model_condition_retries'] == data['known_processes_alive'] == 0,
            'limits_retained': data['shared_MCP_success_claimed'] is data['profile_unchanged'] is False
                and data['profile_drift_writer'].startswith('unknown') and data['whole_plan_pass_claimed'] is False
                and data['RPC_errors'] == []}


def first_reply_checks(root, data):
    summary = load_json(local(root, data['prior_summary']))
    replies = {r['ID_hash'] for r in summary['messages'] if r['kind'] == 'reply'
               and r['actual_claim_ACK'] and r['immutable_digest_valid']}
    return {'actual_final_source_native': data['passed'] is data['source_unchanged'] is True
                and data['source'] == '/private/tmp/xsm-final-receipt-frozen-i3u9pms3'
                and data['summary_sha256'] == file_sha(local(root, data['prior_summary'])),
            'two_distinct_sandboxed_first_replies': len(data['proofs']) == 2
                and len({p['caller_CID_sha256'] for p in data['proofs']}) == 2
                and all(p['first_actual_reply_via'] == 'xsm_send MCP'
                    and p['sandbox'] == 'workspace-write' and p['approval_policy'] == 'never'
                    and p['shell_delivery_attempts'] == 0 and p['RPC_error'] is False
                    and p['actual_received_ACK'] is True and p['reply_ID_sha256'] in replies
                    and p['original_reply_to_sha256'] in {r['request_ID_hash'] for r in summary['question_roundtrips']}
                    for p in data['proofs']),
            'original_native_wire_hashes': all(file_sha(Path(p[k + '_path'])) == p[k + '_sha256']
                for p in data['proofs'] for k in ('native_rollout', 'client_wire')),
            'no_new_model_or_modified_results': data['native_reruns'] == data['models_this_check'] == 0
                and data['metadata_or_results_modified'] is False}


def async_work_checks(root, data):
    manifest = load_json(local(root, 'deliverables/p13-live/async-independent-native-manifest.json'))
    original = load_json(Path(data['original_result_path']))
    return {'24_actual_continuity_checks': data['functional_continuity_passed'] is True
                and len(data['checks']) == 24 and all(v is True for v in data['checks'].values()),
            'single_question_same_ID_and_ACK': data['question_send_count'] == data['reviewer_reply_send_count'] == 1
                and data['request_id'] == data['reply_to'] and data['request_id'] != data['reply_id']
                and data['request_id'] in data['ACKs']['reviewer'] and data['reply_id'] in data['ACKs']['sender']
                and data['work_completed_before_reply_seconds'] > 0,
            'original_public_and_private_hashes': data['original_result_preserved'] is True
                and file_sha(Path(data['original_result_path'])) == data['original_result_sha256']
                and all(file_sha(local(root, p)) == h for p, h in manifest['files'].items())
                and all(file_sha(local(Path(original['root']), p)) == h for p, h in manifest['private_evidence'].items()),
            'source_and_no_rerun': data['source_before']['matches'] is data['source_after']['matches'] is True
                and manifest['product_modified'] is False and manifest['native_reruns'] == 0,
            'unclassified_profile_guard_preserved': data['clean_protected_inputs_passed'] is False
                and data['profile_guard_diagnostic']['cannot_identify_changed_file_from_captured_guard'] is True}


def version_review_checks(root, data):
    manifest = load_json(local(root, 'deliverables/p13-live/version-review-native-20261029-a19.manifest.json'))
    versions = data['versions']
    return {'actual_two_version_review': data['result'] == 'passed-this-two-version-native-sample'
                and [v['version'] for v in versions] == [1, 2]
                and versions[1]['previous_manifest'] == versions[0]['manifest_id']
                and versions[0]['request_id'] != versions[1]['request_id']
                and data['v2_read_then_same_v1_reread'] is data['v1_bytes_digest_marker_unchanged'] is True,
            'actual_copy_reads_and_final_replies': len(data['actual_incoming_entry_reads']) == 3
                and all(r['returned_content_matches_blob'] is r['SHA_matches_entry'] is r['actual_reviewer_owner'] is True
                    for r in data['actual_incoming_entry_reads'])
                and all(v['request_canonical_state'] == 'acknowledged'
                    and any(r['outcome'] == 'succeeded' and r['canonical_state'] == 'acknowledged'
                        and r['actual_native_pair_matches'] is True for r in v['replies']) for v in versions),
            'original_raw_hashes_and_no_leak': data['original_result_preserved'] is True
                and data['original_result_SHA'] == file_sha(local(root, 'deliverables/p13-live/version-review-native-20261029-a19.json'))
                and all(file_sha(local(Path(manifest['raw_root']), p)) == h for p, h in manifest['files'].items())
                and data['raw_marker_in_message_bodies'] == [],
            'source_and_no_rerun': data['source_unchanged'] is True
                and data['native_launches'] == 2 and data['automatic_model_retries'] == data['native_reruns_for_audit'] == 0,
            'unclassified_profile_guard_preserved': data['profile_guard_unchanged'] is False
                and 'not established' in data['profile_limit']}


def owned_memory_checks(root, data):
    trials = {t['id']: t for t in data['trials']}
    ordinary, owned = trials['ordinary-codex-parent'], trials['owned-codex-public-mcp']
    return {'two_real_paths_two_turns_each': ordinary['two_turns'] is ordinary['memory_matches'] is True
                and ordinary['followup_token_omitted_in_producer'] is True
                and owned['two_turns'] is owned['same_native_id'] is owned['memory_matches'] is True
                and owned['second_input_omits_token'] is True
                and ordinary['native_id'] != owned['turns'][0]['native']['native_ids'][0]
                and len(ordinary['turns']) == len(owned['turns']) == 2,
            'raw_and_source_hashes_verified': len(data['evidence_files']) == 55
                and all(file_sha(local(root, r['path']) if r['location'] == 'repository' else Path(r['path'])) == r['sha256']
                    for r in data['evidence_files'])
                and all(r['ast_equal'] is r['saved_snapshot_hash_verified'] is True
                    and file_sha(local(root, r['file'])) == r['current_sha256'] for r in data['source_checks']),
            'native_review_and_scope_preserved': data['validation']['all_memory_assertions_passed'] is True
                and data['validation']['all_snapshot_manifest_assertions_passed'] is True
                and data['decisions']['A16-06']['can_close_without_new_model_for_observed_pair'] is True
                and data['decisions']['A23-06']['can_close_default_public_cli_unconditionally'] is False
                and data['new_models_started'] == data['network_calls'] == 0}


def passive_recovery_checks(root, data, identifier):
    manifest = load_json(local(root, 'deliverables/p13-live/recovery-passive-closure-manifest.json'))
    common = {'retained_raw_and_public_hashes': all(file_sha(local(root, p)) == h for p, h in manifest['files'].items())
                and all(file_sha(Path(p)) == h for p, h in manifest['raw_evidence'].items()),
              'no_hidden_retries_or_manual_corrections': data['source_unchanged_new_pairs'] is True
                and data['native_budget']['automatic_actor_retries'] == data['native_budget']['manual_body_ACK_index_corrections'] == 0,
              'strict_multireview_remains_partial': data['A22-03']['assessment'].startswith('partial-')}
    if identifier == 'A16-05':
        proof = data[identifier]
        common.update(cached_tools_survive_downgrade=len(proof['evidence']) == 2
            and all(e['tools_list_count'] == 1 and e['later_tools_list_refreshes'] == 0
                and e['inbox_in_initial_list'] is True for e in proof['evidence']),
            native_unread_recovered_and_ACK=any(e['positive_unread_notices'] for e in proof['evidence'])
                and all(e['canonical_recovered'] and all(v['status'] == 'acknowledged' and v['route'] == 'mcp-inbox'
                    and mid in e['ACK_IDs'] for mid, v in e['canonical_recovered'].items()) for e in proof['evidence'])
                and len(proof['native_downgraded_messages']) == 8
                and all(m['actual_claim_ACK'] is True and m['typed_auto_fallback_observed'] is True
                    and m['native_queued'] is m['native_wake'] is False for m in proof['native_downgraded_messages']))
    else:
        proof = data[identifier]
        common.update(natural_FYI_consumption=len(proof['checks']) == 12 and all(v is True for v in proof['checks'].values())
            and proof['stored_at'] < proof['work_complete_observed'] < proof['list_complete_observed'] < proof['inbox_body_returned_observed'],
            profile_drift_retained=proof['profile_guard_unchanged'] is False)
    return common


def owned_isolation_checks(root, data):
    capacity = load_json(local(root, 'deliverables/p13-live/owned-capacity-native-20261029-bundle/check.json'))
    base = 'deliverables/p13-live/independent-review-native-20261029-final/'
    manifest = load_json(local(root, base + 'manifest.json'))
    return {'capacity_memory_serial_retirement_and_new_sender': capacity['behavioral_checks_pass'] is True
                and capacity['failed_checks'] == ['profile_config_unchanged']
                and all(v is True for k, v in capacity['checks'].items() if k != 'profile_config_unchanged'),
            'independent_review_and_normal_context': data['behavioral_pass'] is True and data['failed_checks'] == []
                and all(v is True for v in data['checks'].values())
                and data['actual_counts']['child_turns'] == 3 and data['actual_counts']['actor_turns'] == 1,
            'actual_subprocesses_completed': len(capacity['details']['requests']) == 10 and len(data['rows']) == 3
                and all(type(r['execution']['pid']) is int and r['execution']['pid'] > 0
                    and r['execution']['returncode'] == 0 and bool(r['execution']['lstart'])
                    for r in list(capacity['details']['requests'].values()) + data['rows']),
            'native_files_and_current_functions': all(file_sha(Path(r['path'])) == r['sha256']
                for r in data['files'])
                and all(capacity_rebinding_checks(root, load_json(local(root, base+'capacity-rebinding-audit.json'))).values())
                and all(file_sha(local(root, base + p)) == h for p, h in manifest['files'].items())
                and all(r['ast_equal'] is True and file_sha(local(root, r['path'])) == r['current_sha256']
                    for r in data['source_current_binding']),
            'global_and_delivery_limits_preserved': manifest['global_profile_immutability_claim'] is False
                and manifest['default_reply_statuses'] == ['result-ready'] * 3}


def scoped_current_checks(root, cases):
    return scoped_epoch_checks(root, cases)


def positive_receipt_review(private):
    records = [load_json(p) for p in (Path(private) / 'state/handoffs').glob('*/*.json')]
    receipts = [load_json(Path(private) / 'state/ledger' / (r['id'] + '.recv.json'))
                for r in records if (Path(private) / 'state/ledger' / (r['id'] + '.recv.json')).is_file()]
    return {'canonical_records': len(records), 'receipts': len(receipts),
            'held_blocked': sum(r.get('decision') in ('held', 'blocked') for r in receipts),
            'allowed_positive_only': bool(records) and not any(r.get('decision') in ('held', 'blocked') for r in receipts)}


def final_binding(root, identifier, evidence):
    epoch = source_epoch(root)
    m = epoch['manifest']
    if identifier in ('A15-01', 'A15-05'):
        cases = {'tests/test_xsm.py': ['test_a_worktree_and_its_main_checkout_share_the_repository_scope']} if identifier == 'A15-01' else {
            'tests/test_peer_roundtrip.py': ['test_different_parents_roundtrip_both_ways_under_approved_folder_link']}
        names = ('config', 'registry', 'receive', 'send', 'handoff', 'mcp', 'inbox')
        b = {'paths': {p: {'selected_epoch': m['files'].get(p), 'current': file_sha(local(root, p))}
                      for p in list(cases) + ['xsm/' + n + '.py' for n in names]},
             'selectors': cases, 'checks': {}}
        b['checks']['specific_cases_present'] = all(all(name in {n.name for n in ast.walk(ast.parse(local(root, p).read_text()))
            if isinstance(n, ast.FunctionDef)} for name in selectors) for p, selectors in cases.items())
        b['checks']['current_source_exact'] = all(h['selected_epoch'] == h['current'] for h in b['paths'].values())
        b['checks']['actual_native'] = evidence['worktree-native-audit' if identifier == 'A15-01' else 'different-parent-native']['executed']
    else:
        b = postqa_criterion_binding(root, identifier, evidence, manifest=m)
        known = {'skills/xsm/references/messaging.md', 'tests/test_install_native_mcp.py', 'tests/test_mcp_wait_process.py',
                 'tests/test_question_interfaces.py', 'tests/test_xsm.py', 'tests/test_handoff_pending_ids.py', 'tests/test_subagent_transport.py',
                 'xsm/cli.py', 'xsm/install.py', 'xsm/instructions.py', 'xsm/mcp.py', 'xsm/receive.py', 'xsm/handoff.py',
                 'xsm/inbox.py', 'xsm/adapters.py', 'xsm/send.py'}
        if epoch['ready'] and epoch['status'].startswith('doctor-privacy') and all(epoch['delta_checks'].values()):
            # The new CLI cases exercise only diagnostics; the verified AST
            # delta preserves every existing installer function and assertion.
            known.add('tests/test_install_cli_flow.py')
        b['checks']['source_deltas_accounted_for'] = set(b['changed_paths_since1649']) <= known
        for h in b['paths'].values():
            h['selected_epoch'] = h.pop('postqa1667')
    b['checks']['historical1697_valid'] = evidence['final-regression']['executed']
    b['checks']['current_epoch_full_verified'] = epoch['ready']
    b['source_epoch'] = epoch_summary(epoch)
    b['checks']['M1_negative_gate_guard_closed'] = evidence['receipt-filter-M1-local-fix']['executed']
    positive = {
        'A15-01': '/private/tmp/p13-worktree-native-isksjjba', 'A18-05': '/private/tmp/p13-post-claims-uwu7xsx2/post-claims-current',
        'A18-02': '/private/tmp/native-handoff-factory-cytvti8g', 'A18-08': '/private/tmp/p13-owned-crash-jly3ax9r'}
    if identifier in positive:
        b['reused_positive_receipt_review'] = positive_receipt_review(positive[identifier])
        b['checks']['reused_native_has_no_M1_negative_receipts'] = b['reused_positive_receipt_review']['allowed_positive_only']
    b['regression_ref'] = epoch['regression_ref']
    b['scope'] = '선택 epoch의 실제 full 및 source·구체 반례·version을 보존한 native positive 재결속. M1 held/blocked 음성은 actual_gate로 별도 확인하며 미관측 UI/sharedMCP/network로 확대하지 않음'
    return b


def postqa_criterion_binding(root, identifier, evidence, *, manifest=None):
    if identifier == 'A18-02':
        proof = {'origins': ['b04-regression', 'b05-local-integration'], 'product': [
            'receive', 'handoff', 'mcp', 'cli', 'questions', 'inbox', 'ledger', 'registry', 'identity', 'context', 'envelope', 'paths'],
            'cases': {
                'tests/test_handoff_consumer.py': ['test_actual_send_legacy_export_claim_cancel_recover_and_explicit_ack',
                    'test_sigkill_after_actual_consumer_handoff_before_output_recovers_same_id'],
                'tests/test_handoff_crash.py': ['test_sigkill_after_claim_commit_recovers_dead_owner_and_invalidates_old_token',
                    'test_sigkill_after_ack_commit_lost_response_readback_suppresses_duplicate'],
                'tests/test_mcp_wait_process.py': ['test_ping_cancel_lost_auto_id_and_late_reply_keep_inbox_and_request'],
                'tests/test_question_interfaces.py': ['test_mcp_answer_cancel_or_output_failure_releases_its_handoff_call']}}
    elif identifier == 'A18-08':
        proof = {'origins': ['b05-local-integration'], 'product': [
            'workers', 'owned_requests', 'handoff', 'receive', 'send', 'ledger', 'identity', 'paths', 'config'],
            'native': True, 'cases': {
                'tests/test_owned_crash.py': ['test_kill_after_request_store_before_ack',
                    'test_kill_after_ack_before_execution', 'test_kill_after_effect_before_result_journal_requires_readback',
                    'test_kill_after_result_store_resends_without_model', 'test_kill_after_reply_before_commit_reuses_exact_reply_id'],
                'tests/test_owned_interfaces.py': ['test_public_status_recovers_a_saved_answer_after_worker_record_removal',
                    'test_cancelled_mcp_waiter_does_not_stop_a_saved_owned_request'],
                'tests/test_owned_requests.py': ['test_result_immutable_send_retry_same_reply_and_no_extra_execution'],
                'tests/test_owned_workers.py': ['test_controller_cancel_releases_pre_run_and_preserves_post_run_result']}}
    else:
        proof = copy.deepcopy(CLOSURE_PROOFS[identifier])
    if identifier in ('A18-03', 'A18-07', 'A22-06', 'A18-05'):
        proof['cases']['tests/test_question_interfaces.py'] = [
            'test_answer_claims_allow_exact_ack_without_extra_inbox_on_all_public_surfaces',
            'test_reply_handoff_rechecks_owner_generation_digest_and_receive_policy',
            'test_reply_claim_failure_preserves_verified_answer_and_recovery']
    if identifier == 'A23-02':
        proof['cases']['tests/test_install_native_mcp.py'] = [
            'test_clean_native_get_bootstrap_does_not_collide_with_installer',
            'test_concurrent_user_edit_rejected_even_for_current_state',
            'test_public_uninstall_invalid_json_is_exit4_without_traceback_or_partial_removal',
            'test_public_uninstall_symlink_is_exit4_without_traceback_or_partial_removal',
            'test_public_uninstall_normal_path_removes_owned_components',
            'test_public_native_remove_nonzero_exit_preserves_hooks_and_returns_exit4']
    manifest = manifest if manifest is not None else load_json(local(root, 'deliverables/p13-live/post-qa-source-manifest.json'))
    prior = load_json(local(root, 'deliverables/p13-live/local-source-manifest.json'))
    paths = sorted(set(proof['cases']) | {'xsm/' + p + '.py' for p in proof['product']})
    if proof.get('native'):
        paths += ['skills/xsm/SKILL.md', 'skills/xsm/references/guide.md', 'skills/xsm/references/messaging.md']
    hashes = {p: {'prior1649': prior['files'].get(p), 'postqa1667': manifest['files'].get(p),
                  'snapshot': file_sha(local(Path(manifest['snapshot']), p)), 'current': file_sha(local(root, p))} for p in paths}
    selectors = {p: {name: name in {n.name for n in ast.walk(ast.parse(local(root, p).read_text()))
                                   if isinstance(n, ast.FunctionDef)} for name in names} for p, names in proof['cases'].items()}
    known_deltas = {'skills/xsm/references/messaging.md', 'tests/test_install_native_mcp.py',
                    'tests/test_mcp_wait_process.py', 'tests/test_question_interfaces.py', 'xsm/cli.py',
                    'xsm/install.py', 'xsm/instructions.py', 'xsm/mcp.py', 'xsm/receive.py'}
    changed = [p for p, h in hashes.items() if h['prior1649'] != h['postqa1667']]
    checks = {'1667_exact_execution': evidence['postqa-regression']['executed'],
              'specific_cases_present': all(all(v.values()) for v in selectors.values()),
              'postqa_snapshot_current_equal': all(h['postqa1667'] is not None and h['postqa1667'] == h['snapshot'] == h['current'] for h in hashes.values()),
              'source_deltas_accounted_for': set(changed) <= known_deltas,
              'prior_scoped_execution_retained': all(evidence[k]['executed'] for k in proof['origins'])}
    if changed and identifier != 'A18-08':
        checks['claims_delta_actual_native_readback'] = evidence['postclaims-native']['executed']
    if proof.get('native') and identifier != 'A18-08':
        checks['two_home_actual_native_postqa'] = evidence['postclaims-native']['executed']
    if identifier == 'A23-02':
        checks['native_install_and_uninstall_counterexamples_closed'] = evidence['clean-install-final']['executed']
    if identifier == 'A18-02':
        checks['factory_native_claim_termination_readback'] = evidence['factory-handoff-native']['executed']
        checks['factory_manifest_bound'] = evidence['factory-handoff-manifest']['executed']
    if identifier == 'A18-08':
        checks['actual_five_native_journal_boundaries'] = evidence['owned-crash-native']['executed']
        checks['actual_owned_manifest_bound'] = evidence['owned-crash-manifest']['executed']
    return {'checks': checks, 'paths': hashes, 'changed_paths_since1649': changed, 'selectors': selectors,
            'regression_ref': 'postqa-regression', 'prior_execution_refs': proof['origins'],
            'native_ref': 'owned-crash-native' if identifier == 'A18-08' else 'postclaims-native' if proof.get('native') or changed else None,
            'fix_ref': 'clean-install-final' if identifier == 'A23-02' else None,
            'scope': '구체 반례 + 원 실행 이력 + 알려진 claims/installer delta + 1667/현재 동일 hash. 종전1649를 새 제품 실행으로 읽지 않음'}


def catalog(root):
    result = {}
    def add(key, path, levels=(), **kwargs):
        result[key] = fact(root, path, levels, **kwargs)
    for number, name in ((0, 'baseline'), (1, 'identity-integrity'), (2, 'connection-intent'),
                         (3, 'question-interface'), (4, 'recoverable-handoff'), (5, 'directory')):
        add('gate-G%02d' % number, BASE + 'records/gates/G%02d-%s.md' % (number, name), ('fixture', 'process'),
            scope='게이트 문서에 기록된 해당 로컬 revision/검사만; 조건 전체·현재 통합·다른 환경으로 승격 금지',
            predicate=lambda d: {'reported_gate_result': 'passed' in d, 'execution_result_recorded': 'OK' in d or '통과' in d})
    for number, name in ((6, 'material-copies'), (8, 'owned-runtime'),
                         (9, 'provenance-traffic'), (10, 'installation-evidence')):
        add('gate-G%02d' % number, BASE + 'records/gates/G%02d-%s.md' % (number, name), ('fixture', 'process'),
            scope=('clean native CLI 등록/제거 반례·91개씩 및 새1667에 결속된 local G10만; clean 로그인/첫모델/UI/전체여정 아님'
                   if number == 10 else 'B05에 연결된 해당 로컬 기술 gate만; 전체 수용 조건/UI/원격 완료 아님'),
            predicate=lambda d, n=number: ({'local_pass': 'passed' in d and 'clean-install.final.json' in d,
                                            'new_frozen_regression': '1667' in d and 'post-qa-regression.json' in d,
                                            'clean_LLM_not_run': '미실행' in d} if n == 10 else
                                          {'local_pass': 'passed' in d and 'B05-local-integration.md' in d,
                                           'bounded_scope': '전체 70개' in d}))
    add('b05-local-integration', BASE + 'records/gates/B05-local-integration.md', ('fixture', 'process'),
        scope='고정본 두 Python 1648 OK 기록; 앞선 1629 실패/1648 matrix 오류와 구별. G13 최종 회귀 아님',
        predicate=lambda d: {'both_runs': all(s in d for s in ('1648개 / 309.054초 / OK', '1648개 / 424.796초 / OK')),
                             'manifest_binding': 'final-source-manifest.json' in d,
                             'whole_goal_unfinished': '미완' in d and '전체 70개' in d})
    add('b05-source-manifest', 'deliverables/b05-live/final-source-manifest.json',
        scope='B05 당시 파일별 hash/snapshot 포인터. 현재 작업 트리와 동일하다는 주장이 아님; 실행 증거는 B05 문서',
        execution='source-manifest', predicate=lambda d: {'bound_snapshot': bool(d['snapshot']) and bool(d['files'])})
    add('b05-review-mutations', 'deliverables/b05-live/review-mutations.json', ('fixture',),
        scope='당시 coordinator 변이 이력. M3 mutation_detected=false를 성공으로 덮지 않음; 전체 재리뷰 아님',
        execution='historical-counterexample',
        predicate=lambda d: {'M3_not_detected': any(r['finding'] == 'M3-poisoned-copy-store' and r['mutation_detected'] is False for r in d)})
    add('b03-regression', 'deliverables/b03-live/closure.json', ('fixture', 'process'),
        scope='B03 고정 source에서 1305개 회귀; P04 이후 조건 미포함',
        predicate=lambda d: {'passed_record': d['status'] == 'passed', 'later_scope_retained': bool(d['remaining'])})
    add('b04-regression', BASE + 'records/gates/G04-recoverable-handoff.md', ('fixture', 'process'),
        scope='B04 frozen2: 두 Python 1517 OK 기록. 첫 실패 기록을 최종 성공으로 읽지 않음',
        predicate=lambda d: {'frozen2_record': '1517' in d and 'frozen2' in d, 'scope_local': '전체 70개' in d})
    add('b04-first-failure', 'deliverables/b04-live/frozen-regression.json',
        scope='first_run은 5 fail/3 error. 최종 frozen2는 별도 G04 문서; 역사적 counterexample 보존',
        execution='historical-counterexample', predicate=lambda d: {'initial_failed': d['first_run']['status'] == 'failed'})
    add('g02-native', 'deliverables/g02-live/trace.json', ('native',),
        scope='질문 선결속 hardening 전 실제 link/request/reply. 최신 hardening 전체 trace로 재사용 금지',
        predicate=lambda d: {'correlated_reply': d['reply_to_matches'] is True, 'revision_limit_recorded': bool(d['execution_revision_note'])})
    add('b03-question', 'deliverables/b03-live/question-answer.json', ('native',),
        scope='로컬 실제 CLI 질문 final reply 한 표본; 원 ID·reply 구분',
        predicate=lambda d: {'actual_reply': d['final'] is True and bool(d['replies']), 'reply_wait': d['wait_end_reason'] == 'reply'})
    add('b03-mcp', 'deliverables/b03-live/native-mcp-fixed.json', ('native',),
        scope='별도 actual Claude MCP 평가 표본; old sender baseline과 구분',
        predicate=lambda d: {'not_tool_error': d['is_error'] is False, 'tools_recorded': bool(d['tool_calls'])})
    add('b03-handshake', 'deliverables/b03-live/handshake-answer.json', ('native',),
        scope='로컬 선택 candidate의 actual correlated reply; 원격/동명 전수 아님',
        predicate=lambda d: {'completed': d['handshake'] == 'completed', 'has_reply': bool(d['replies'])})
    add('b03-sandbox', 'deliverables/b03-live/sandbox-first-reply.json', ('native',),
        scope='실제 sandbox 첫 MCP 송신. 평가 prompt가 경로를 지정했고 clean 설치 기본 선택은 미검증',
        predicate=lambda d: {'no_shell_send': d['model_shell_send_attempts'] == 0,
                             'mcp_first': d['first_send'] == 'MCP xsm_send', 'no_widening': d['permission_widened'] is False})
    add('b03-human-sample', 'deliverables/b03-live/human-review.json', ('review',),
        scope='격리 a1/a2 요약의 실제 사용자 표본 평가; G07 화면 관측이나 실제 공개 승인이 아님',
        predicate=lambda d: {'user_answer': d['native_role'] == 'user' and bool(d['answer']), 'not_publication_grant': d['publication_permission'] is False})
    add('b04-native', 'deliverables/b04-live/native-profiles.json', ('native',),
        scope='실제 .codex/.codex-3 injected MCP 수신→ack→reply; 전역 설치/모든 idle/busy 조합 아님',
        predicate=lambda d: {'two_profiles': len(d) == 2, 'correlated': all(r['actual_correlated_reply'] is True for r in d),
                             'exit_zero': all(r['exit_code'] == 0 for r in d)})
    add('b04-legacy', 'deliverables/b04-live/legacy-reader.json', ('process',),
        scope='설치된 구 inbox.py 실제 별도 Python reader. native LLM/MCP 업그레이드 증거 아님',
        predicate=lambda d: {'recovered': d['new_consumer_recovered_original'] is True, 'retained': d['original_retained'] is True,
                             'no_duplicate': d['duplicate_after_ack'] is False, 'not_native': d['native_llm_used'] is False})
    add('p06-native', 'deliverables/p06-live/native-files.json', ('native',),
        scope='실제 두 Codex 프로필 xsm_files로 사본의 랜덤 토큰을 읽음; shared server/전체 권한 행렬은 아님',
        predicate=lambda d: {'two_profiles': len(d) == 2, 'actual_file_reads': all(r['files_tools_used'] > 0 for r in d),
                             'actual_replies': all(r['actual_correlated_reply'] is True for r in d)})
    add('p06-claude-native', 'deliverables/p06-live/native-claude-files.json', ('native',),
        scope='실제 Claude 첨부 token 읽기/ACK/상관 reply 한 표본; 전체 파일 권한 행렬 아님',
        predicate=lambda d: {'actual_reply': d['actual_attachment_reply'] is True and bool(d['reply_ids']),
                             'file_tool': 'mcp__xsm__xsm_files' in d['tool_calls'],
                             'no_permission_adjustment': d['permission_adjustments'] is False,
                             'no_denials': d['permission_denials'] == [] and d['exit_code'] == 0})
    for key, filename in (('ui-intent-1', 'ui-intent.json'), ('ui-intent-2', 'ui-intent2.json')):
        add(key, 'deliverables/p07-live/' + filename, ('UI',),
            scope='prepared-not-displayed인 질문 의도. 실제 화면/답/잘림 증거 없음', execution='not-run',
            predicate=lambda d: {'not_displayed': d['status'] == 'prepared-not-displayed'})
    add('p07-os', 'deliverables/p07-live/actual-os-notification.json', ('process',),
        scope='실제 OS 명령 exit 0. human_saw/display_range null; 사람 확인이나 화면 성공 아님',
        predicate=lambda d: {'os_succeeded': d['status'] == 'os-call-succeeded' and d['exit_code'] == 0,
                             'human_unknown': d['human_saw'] is None and d['observed_display_range'] is None})
    add('p08-native', 'deliverables/p08-live/native-memory.json', ('native',),
        scope='owned Claude/Codex 각 두 turn·같은 native ID·기억 표본; 일반 세션/용량+1/퇴출 전체 아님',
        predicate=lambda d: {'two_runtimes': {r['runtime'] for r in d['results']} == {'claude', 'codex'},
                             'memory_matches': all(r['memory_matches'] and r['same_native_conversation'] for r in d['results']),
                             'normal_permissions': d['model_permissions_widened'] is False})
    add('p08-owned-mcp-native', 'deliverables/p08-live/native-owned-mcp.json', ('native',),
        scope='실제 부모 MCP owned 두 호출/양 대화 기억. 둘째 자식 outcome 없음: task finality unknown 유지',
        predicate=lambda d: {'same_native': d['same_owned_native'] is True and d['parent_same_native'] is True,
                             'memory': d['owned_memory_matches'] is True and d['parent_followup_remembers'] is True,
                             'two_requests': len(d['owned_requests']) == 2,
                             'finality_not_invented': d['owned_task_finality'][1]['outcome'] is None,
                             'no_widening': d['permission_adjustments'] is False})
    add('p09-native', 'deliverables/p09-live/results.json', ('native',),
        scope='일반 두 Codex 프로필의 직접 3라운드 ask/reply/ACK. cli/mcp source drift 있어 단일 동결 revision 아님; 장시간 전수 아님',
        predicate=lambda d: {'native_sample': d['status'] == 'passed-this-native-sample' and d['ordinary_native_peers'] is True,
                             'three_rounds': len(d['evaluation']['rounds']) == 3 and d['evaluation']['direct_three_rounds_passed'] is True,
                             'correlated_ack': all(r['correlated_direct_reply'] is True and r['both_claims_acknowledged'] is True
                                                   and r['original_reply_to'] == r['request_id'] for r in d['evaluation']['rounds']),
                             'no_controller_relay': d['evaluation']['controller_forwarded_review_content'] is False})
    add('p08-capacity', 'deliverables/p08-live/native-capacity.json', ('native',),
        scope='실제 Codex 4+1 admission. 원 completed의 parser unknown 3건은 별도 readback으로 회수; 전체 격리/퇴출 행렬 아님',
        predicate=lambda d: {'actual_overlap': d['overlap_observed'] is True,
                             'overload_not_executed': d['fifth_admission'] == 'overloaded' and d['fifth_initial_executed'] is False,
                             'same_id_resumed': d['fifth_resumed_same_id'] is True and d['fifth_resumed_status'] == 'reply-stored',
                             'permissions_unchanged': d['permission_adjustments'] is False})
    add('p08-capacity-readback', 'deliverables/p08-live/native-capacity-readback.json', ('native',),
        scope='보존 stdout에서 unknown 3건을 reply-stored로 회수. 원 출력 불변·모델 재실행 없음; 중단 경계 전수 아님',
        predicate=lambda d: {'recovery_recorded': bool(d['recovered']),
                             'all_recovered': all(r['before'] == 'unknown' and r['after'] == 'reply-stored' for r in d['recovered']),
                             'originals_retained': all(r['original_stdout_unchanged'] is True for r in d['recovered']),
                             'no_reruns': all(r['model_rerun'] is False for r in d['recovered'])})
    add('p10-cli', 'deliverables/p10-live/matrix.json', ('fixture', 'process'),
        scope='94개 격리 CLI 셀/소유 reader. LLM first_roundtrip unknown, G04 수집 당시 pending; native/UI 아님',
        predicate=lambda d: {'all_recorded_cells': d['counts']['passed'] == d['counts']['total_cells'] == len(d['cells']),
                             'no_failed_cells': d['counts']['failed'] == 0,
                             'no_LLM': d['safety']['LLM_roundtrips_executed'] is False,
                             'roundtrip_unknown': d['safety']['first_roundtrip'] == 'unknown'})
    add('p10-upgrade-native', 'deliverables/p10-live/native-upgrade.json', ('native', 'process'),
        scope='실제 old native/MCP 유지→private CURRENT 교체/prune→동일 대화 두 reply 및 new-prefix reply. new 최종 turn 완료로 확대 금지',
        predicate=lambda d: {'passed': d['status'] == 'passed',
                             'old_preserved': d['upgrade']['old_snapshot_exists'] is True and d['upgrade']['after_prune']['same_mcp_generation_alive'] is True,
                             'same_native': d['trials'][0]['same_native_conversation'] is True,
                             'correlated': all(r['reply_to'] == r['request_id'] for r in
                                               (d['trials'][0]['first_reply'], d['trials'][0]['second_reply'], d['trials'][1]['reply'])),
                             'settings_unchanged': d['protection']['settings_unchanged'] is True})
    add('p10-controller-arrival', 'deliverables/p10-live/controller-native-arrival.json',
        scope='R1 보존/R2 actual main 도착을 native-upgrade 원 id/reply_to/body와 대조. provenance unchecked·identity/permission승격0·추가humanprompt0; goal auto 활성의 wake 원인은 미확정',
        predicate=lambda d: arrival_checks(root, d))
    add('local-release-preparation', BASE + 'records/release-candidate.md',
        scope='미커밋 로컬 변경·복구/검토 문서만. 릴리스/배포/후속 변경 전체 회귀/원격/UI 완료 아님',
        execution='local-preparation-only',
        predicate=lambda d: {'not_a_release': '배포판이 아니며' in d,
                             'whole_release_incomplete': '전체 릴리스 기준은 미충족' in d,
                             'followup_scope_separate': '후속 변경까지 포함한 결과로 사용하지 않는다' in d})
    add('remote-comparison', BASE + 'remote-decision.md', ('physical',),
        scope='A/B/D·C native 비교 요약과 과거 합성/IPC 이력. 상세 실행은 별도 JSON; 문서 일부 역사 행을 현재 C 미실행으로 읽지 않음. NAT/relay/D12 아님',
        predicate=lambda d: {'physical_native_summary': '두 물리 머신' in d and 'native 15회' in d,
                             'D12_unselected': 'D12는 사용자 미응답·미선택' in d,
                             'C_artifact_linked': 'C-native-roundtrip-20261029.json' in d})
    add('p11-abd-native', 'deliverables/p11-live/native-carrier-roundtrip-20261029.json', ('native', 'physical'),
        scope='A/B/D 두 물리 Mac carrier fixture native 9회. SSH bootstrap/현재 LAN-tailnet 전제; 제품 discovery/approval/handshake 아님',
        predicate=lambda d: {'two_hosts': d['local_hostname'] != d['peer_hostname'],
                             'actual_calls': d['actual_agent_roundtrip'] is True and d['actual_native_calls'] == 9,
                             'three_carriers': {r['candidate'] for r in d['results']} == {'A-LAN-SSH', 'B-private-TCP', 'D-Tailscale-SSH'},
                             'passed': all(r['passed'] is True and r['native_calls'] == 3 for r in d['results']),
                             'no_backend_selection': d['product_boundary']['backend_selected'] is False})
    add('p11-c-native', 'deliverables/p11-live/C-native-roundtrip-20261029.json', ('native', 'physical'),
        scope='C 격리 두 머신 direct native 6회/캐시 2회. relay 접속은 relay task 증거 아님; 제품 원격 peer 여정/D12와 별개',
        predicate=c_native_checks)
    add('p11-c-evidence-check', 'deliverables/p11-live/C-evidence-check-20261029.json', ('fixture', 'process'),
        scope='G11 문구 정정 후 두 Python offline 재검사, UTC·현재 manifest/result/checker SHA·보고서 amendment 결속. 111files/변이3씩; 새 native 호출0',
        predicate=lambda d: c_checker_checks(root, d))
    add('p11-opus-review', 'deliverables/p11-live/opus-review.md', ('review',),
        scope='독립 검토 1회 원판정 partial/서술 수정 필요. native15/cached5 수치 일치; 실제 hash 재계산·모델 재현은 하지 않은 검토. passed 재리뷰로 인용 금지',
        authority='independent-review-original-partial',
        predicate=lambda d: {'original_partial': 'G11을 **partial**' in d and '수정' in d,
                             'counts_compared': 'native 15회 / cached 5회' in d,
                             'limits_retained': 'SHA-256 재계산' in d and '하지 못했습니다' in d})
    add('p11-review-closure', 'deliverables/p11-live/review-closure.json', ('review',),
        scope='기본native15 자료의 코디네이터 문서 지적7개 후속 이력. 이후 decision/G11 문서 revision은 다르며 추가UDP 독립 재리뷰 아님. 원 C보고서/nativeJSON hash는 유지; G11 partial/D12 미응답',
        authority='coordinator-document-followup-not-independent-rereview',
        predicate=lambda d: g11_review_closure_checks(root, d))
    followup = load_json(local(root, 'deliverables/p11-live/review-closure.json'))
    result['p11-review-closure']['document_revision_binding'] = {
        p: {'coordinator_followup_sha256': h, 'current_sha256': file_sha(local(root, p)),
            'same_revision': h == file_sha(local(root, p))} for p, h in followup['amended_files_sha256'].items()}
    for key, path in (('p11-abd-manifest', 'deliverables/p11-live/native-carrier-manifest-20261029.json'),
                      ('p11-c-manifest', 'deliverables/p11-live/C-native-evidence-manifest-20261029.json'),
                      ('p12-contract-source', 'deliverables/p12-prep/network_contract.py'),
                      ('p12-contract-tests', 'deliverables/p12-prep/test_network_contract.py')):
        add(key, path, scope='파일 hash 포인터/준비 source만; 존재를 실제 제품 실행이나 전체 완료로 승격하지 않음', execution='source-or-manifest')
    add('p12-prep-contract', 'deliverables/p12-prep/README.md', ('fixture',),
        scope='IC06 준비 codec/negative conformance: 두 Python 22개 및 메모리 변이 2개 기록. transport/backend/status wire/전체 P12 아님',
        predicate=lambda d: {'two_python_results': 'Python 3.9.6: Ran 22 tests' in d and 'Python 3.14.6: Ran 22 tests' in d,
                             'separate_semantics': 'xsm.network-semantic/v1' in d and 'generation' in d,
                             'unfinished_product': '전체 P12는 미완' in d})
    add('p13-local-regression', 'deliverables/p13-live/local-regression.json', ('fixture', 'process'),
        scope='수정 전 post-goalfilter 고정본 1649/두 Python/skip0·실행 당시132 hash/원 로그 검증. 이후 현재 source 동등성과 구분; 제품 패치 검증으로 승격 금지',
        predicate=lambda d: local_regression_checks(root, d))
    result['p13-local-regression']['current_source_binding'] = current_source_binding(root,
        load_json(local(root, 'deliverables/p13-live/local-source-manifest.json')))
    add('p13-clean-install-counterexample', 'deliverables/p13-live/clean-install.json',
        scope='실제 native CLI MCP 등록 포함 install exit4 InstallConflictError. no-mcp matrix와 다른 경로. clean home auth 전제도 미충족·모델 실행0; 원인/수정 결과 미확정',
        execution='recorded-counterexample',
        predicate=lambda d: {'install_failed': d['installer']['exit_code'] == 4,
                             'native_registration_included': '--no-mcp' not in d['installer']['argv'],
                             'no_model_success_substitution': d['agent_model_processes_started'] == 0})
    add('p13-natural-audit', 'deliverables/p13-live/natural-collaboration-audit.json', ('native',),
        scope='raw 불변·모델 재실행0. 두 홈의 조건별 실제 수학3회, 새 조건 handshake1/old0, 중계/사람 추가 prompt0. old도 새 공통 안내 사용, 불변 old-product baseline 아님',
        predicate=lambda d: natural_checks(root, d))
    regression = load_json(local(root, 'deliverables/p13-live/local-regression.json'))
    for identifier, proof in CLOSURE_PROOFS.items():
        binding = criterion_binding(root, identifier, regression, result)
        key = 'p13-bound-' + identifier
        add(key, 'deliverables/p13-live/local-regression.json', proof['levels'],
            scope=identifier + ': 지정된 반례/실제 process 또는 native 표본의 현재 동일 hash 결속만. 타 조건 전체로 전이 금지',
            predicate=lambda d, b=binding: b['checks'],
            execution='recorded' if all(binding['checks'].values()) else 'binding-pending',
            complete_for={identifier: proof['levels']} if all(binding['checks'].values()) else {})
        result[key]['condition_binding'] = binding
        result[key]['supports_acceptance'] = [identifier]
        result[key]['coverage_ceiling'] = 'specified-cells-only'
        result[key]['historical_reviewed_cells'] = {identifier: proof['levels']}
        result[key]['superseded_by'] = 'postqa-bound-' + identifier
        # Current credit is now re-evaluated below against the 1667 snapshot.
        result[key]['complete_for'] = {}
        result[key]['scope'] += '; 1649 이전 source 검토 이력만 보존하며 현재 credit은 postqa-bound로 분리'
    add('postqa-manifest', 'deliverables/p13-live/post-qa-source-manifest.json',
        scope='313 files/133 primary 고정 source 포인터. 자체로 native/UI 완료 아님', execution='source-manifest')
    add('postqa-regression', 'deliverables/p13-live/post-qa-regression.json', ('fixture', 'process'),
        scope='설치/질문claims 수정 후 두 Python 1667 OK·skip0/133 primary 실행후 불변. 1649 역사와 별도; 전체P12/G13 완료 아님',
        predicate=lambda d: postqa_regression_checks(root, d))
    result['postqa-regression']['current_source_binding'] = current_source_binding(root,
        load_json(local(root, 'deliverables/p13-live/post-qa-source-manifest.json')))
    add('clean-install-final', 'deliverables/p13-live/clean-install.final.json', ('fixture', 'process'),
        scope='native CLI 등록6셀/combined·정상제거·손상JSON/symlink 보존/91개씩·변이2. 진단 실행 revision과 최종 guard revision은 source hash로 구분. clean 로그인/첫모델왕복은 미실행',
        predicate=lambda d: clean_final_checks(root, d))
    result['clean-install-final']['diagnostic_install_source_sha256'] = load_json(local(root,
        'deliverables/p13-live/clean-install.diagnostic-post.json'))['source_install_sha256']
    add('clean-install-report', 'deliverables/p13-live/clean-install.md',
        scope='설치 원 실패·수정·미로그인/모델0의 범위 설명. 전체 J01 native 성공 아님', execution='scope-document')
    add('postclaims-raw', 'deliverables/p13-live/post-claims-collaboration.json',
        scope='current 조건 native2 원 관측 보존. 상세 ACK/body/hash readback은 별도 offline 감사', execution='recorded-source')
    add('postclaims-native', 'deliverables/p13-live/post-claims-collaboration.audit.json', ('native',),
        scope='같은 자연goal current1조건/native2·math3/handshake1·직접ACK4·initiator inbox0/MCP9. source/원문 보존. 새 clean로그인·전체J03/J04·속도우위 아님',
        predicate=lambda d: postclaims_checks(root, d))
    for identifier, proof in CLOSURE_PROOFS.items():
        binding = postqa_criterion_binding(root, identifier, result)
        key = 'postqa-bound-' + identifier
        valid = all(binding['checks'].values())
        add(key, 'deliverables/p13-live/post-qa-regression.json', proof['levels'],
            scope=identifier + ': 기존 구체 반례와 새 claims/installer 반례·1667/current source·실제 native의 지정 cell 재결속만',
            predicate=lambda d, b=binding: b['checks'], execution='recorded' if valid else 'binding-pending',
            complete_for={identifier: proof['levels']} if valid else {})
        result[key].update(condition_binding=binding, supports_acceptance=[identifier], coverage_ceiling='specified-cells-only')
    add('udp-native', 'deliverables/p11-live/udp-blocked-results-20261029.json', ('native', 'physical'),
        scope='기본15/cached5와 별도 C 추가native1: own-daemon kernel UDP deny+양끝 peer link relay+상관 reply. SSH/native CLI는 deny 밖; A/B/D/global firewall/다른NAT/proxy/자체relay/SSH불가/제품P12 미증명',
        predicate=udp_checks)
    result['udp-native']['sample_counts'] = {'baseline_native': 15, 'baseline_cached': 5, 'additional_C_UDP_native': 1,
                                           'independent_G11_model_review_covers': 'baseline15 only; UDP addition not independently model-reviewed'}
    add('C-noSSH-v2', 'deliverables/p11-live/no-ssh-v2-results.json', ('native', 'physical'),
        scope='C post-bootstrap own-process TCP22deny 양쪽kernelEPERM/SSH255·windowSSH0·autonomous helper engine→native1→engine reply/6.984564s. libproc 비승격 새fixture; 신규설치무SSH/전역network/A·B·D/P12 아님',
        predicate=lambda d: {'27_recorded_checks': d['passed'] is True and d['checks_passed'] == len(d['checks']) == 27
                and all(v is True for v in d['checks'].values()),
            'native_one_window_SSH_zero': d['native']['model_count'] == d['native']['model_attempts'] == 1
                and d['native']['automatic_retry_count'] == d['SSH']['data_window_count'] == 0
                and d['request_id'] == d['reply_to'],
            'old_failure_and_product_preserved': all(d['old_failure_files_unchanged'].values())
                and d['product_source_modified'] is False})
    add('C-noSSH-v2-manifest', 'deliverables/p11-live/no-ssh-v2-manifest.json',
        scope='새 noSSH fixture의 immutable 결과/code hash. 원 setuid ps EPERM 실패를 보존하며 offline audit는 coordinator가 PASS 확인',
        predicate=lambda d: {'results_code_hashes': all(h == file_sha(local(root, p))
            for p, h in d['files'].items() if not p.endswith('.md')),
            'result_bound': d['files']['deliverables/p11-live/no-ssh-v2-results.json']
                == file_sha(local(root, 'deliverables/p11-live/no-ssh-v2-results.json'))})
    add('C-proxy-variant', 'deliverables/p11-live/proxy-variant-summary-20261029.json', ('native', 'physical'),
        scope='C own-engine 양쪽 direct kernel/TLS차단·정확한loopback CONNECT port 허용/native1·8.840102s·양쪽relay/상관SHA/window relay bytes. CONNECT2225/2299·거부2179/2249·nonCONNECT3각각은 모델재시도0과 별개. 기업인증proxy/전역network/P12 아님',
        predicate=lambda d: {'one_native_correlated_relay': d['native_model_attempts'] == 1
                and d['native_automatic_retries'] == d['native_CLI_exit'] == 0
                and d['reply_to_and_native_SHA_correlation_verified'] is True
                and d['relay_connected_alone_used_as_proof'] is False,
            'both_owned_proxy_preflights_and_window_bytes': all(d['preflights'][s]['passed'] is True
                and d['preflights'][s]['direct_TCP_no_connection'] is True
                and d['preflights'][s]['TLS_tunnel']['certificate_verification_disabled'] is False
                and sum(d['proxy_stats'][s]['native_window_relay_bytes_up_down']) > 0 for s in ('local', 'peer')),
            'old_failure_product_and_limits_preserved': d['old_proxy_failure_C_UDP_results_unchanged'] is True
                and d['product_source_1697_modified'] is False and d['TLS_MITM_or_verify_disabled'] is False
                and d['cleanup']['known_processes_alive'] == 0})
    add('C-proxy-variant-manifest', 'deliverables/p11-live/proxy-variant-manifest-20261029.json',
        scope='proxy variant immutable 결과/code hash. coordinator offline audit PASS; 원 profile 준비실패와 별도',
        predicate=lambda d: {'public_core_hashes': all(r['sha256'] == file_sha(Path(r['path'])) for r in d['files']
                if str(root.resolve()) in r['path'] and not r['path'].endswith('.md')),
            'result_bound': any(Path(r['path']).name == 'proxy-variant-summary-20261029.json'
                and r['sha256'] == file_sha(local(root, 'deliverables/p11-live/proxy-variant-summary-20261029.json')) for r in d['files'])})
    for key, p in (('C-noSSH-original-failure', 'no-ssh-native-results.json'),
                   ('C-proxy-original-preparation-failure', 'proxy-native-preparation-failure-20261029.json')):
        add(key, 'deliverables/p11-live/' + p, scope='원 준비실패 그대로 보존. 후속 variant 성공으로 원실행을 성공으로 소급하지 않음', execution='historical-preparation-failure')
    for key, p in (('C-noSSH-v2-audit-source', 'no-ssh-v2-audit.py'), ('C-proxy-variant-audit-source', 'proxy-variant-audit.py')):
        add(key, 'deliverables/p11-live/' + p, scope='coordinator가 재실행 PASS 확인한 offline audit source; 본 색인 갱신은 추가실행/모델호출 없음', execution='source-only')
    add('udp-manifest', 'deliverables/p11-live/udp-blocked-manifest-20261029.json',
        scope='UDP own-daemon 원자료/코드/결과 76개 integrity binding; 독립 attest 아님',
        predicate=lambda d: udp_manifest_checks(root, d))
    add('udp-offline-check', 'deliverables/p11-live/udp-blocked-evidence-check-20261029.json', ('fixture', 'process'),
        scope='76 files/peer29·실제 native thread/turn1·회신hash 및 connection-only 반례 offline검사. 새 모델0/독립 모델리뷰 아님',
        predicate=lambda d: {'passed': d['passed'] is True and d['manifest_records'] == 76 and d['peer_files_verified'] == 29,
                             'actual_native_one': d['native_thread_started_events'] == d['native_turn_completed_events'] == 1,
                             'not_connection_only': d['hashes_and_reply_correlations_match'] is True
                                and d['relay_connected_only_counterexample_rejected'] is True and d['new_model_calls'] == 0})
    for key, path, count in (
        ('native-handoff-first-preparation', 'deliverables/p13-live/native-handoff-20261029-f2193749/summary.json', 'claim_count'),
        ('native-handoff-workspace-preparation', 'deliverables/p13-live/native-handoff-workspace-20261029-9879d1a2/summary.json', 'claims')):
        add(key, path, scope='tools/call0·claim0의 host 준비 실패. native handoff fault 경계 미도달, positive credit 없음. workspace 프로필 drift는 writer unknown으로 보존',
            execution='preparation-failure-no-positive-credit',
            predicate=lambda d, c=count: {'no_product_path': d['MCP_tools_call_count'] == d[c] == 0
                                           and d['fault_boundary_triggered'] is False})
    result['native-handoff-workspace-preparation']['profile_observation'] = {
        'unchanged': False, 'attribution': 'unknown; no evaluator edit attribution established',
        'source': 'summary.json profile_guard_delta/profile_drift_attribution'}
    add('native-handoff-factory-pending', 'deliverables/p13-live/native-handoff-factory-20261029-7091030d/plan.json',
        scope='factory 평가 계획 원문 자체는 credit 없음. 완료 functional 표본은 별도 summary/manifest로 결속하며 전체J05는 미완', execution='plan-only-not-credited')
    add('factory-handoff-native', 'deliverables/p13-live/native-handoff-factory-20261029-7091030d/summary.json', ('native',),
        scope='actual claim0byte→SIGKILL/동일CID 새세대 owner-dead 회수→ACK/상관reply→ACK후빈inbox. CLI4/turn3/setup등록3·active-writer 거절/tail race/drift writer unknown 보존. native toolcancel은 관측하지 않음; 전체J05/A18-04/G12 성공 아님',
        predicate=lambda d: factory_handoff_checks(root, d))
    result['factory-handoff-native']['observed_cancel_notifications'] = factory_cancel_count()
    add('factory-handoff-manifest', 'deliverables/p13-live/native-handoff-factory-20261029-7091030d/manifest.json',
        scope='functional handoff 원자료/실행source/summary 95개 hash 결속. 앞선 host 준비실패2건은 그대로 보존',
        predicate=lambda d: factory_manifest_checks(root, d))
    add('factory-handoff-report', 'deliverables/p13-live/native-handoff-factory-20261029-7091030d/report.md',
        scope='native 기능 표본과 두 제어실패·프로필 drift의 제한 설명; 독립리뷰/전체 여정 판정 아님', execution='scope-document')
    binding = postqa_criterion_binding(root, 'A18-02', result)
    valid = all(binding['checks'].values())
    add('postqa-bound-A18-02-local', 'deliverables/p13-live/post-qa-regression.json', ('fixture', 'process'),
        scope='종료·claim취소/release·대기취소·원문회수·ACK후중복억제의 구체 fixture/실stdio/SIGKILL process만 full cell 결속. native 취소를 이 근거로 승격하지 않음',
        predicate=lambda d, b=binding: b['checks'], execution='recorded' if valid else 'binding-pending',
        complete_for={'A18-02': ['fixture', 'process']} if valid else {})
    result['postqa-bound-A18-02-local'].update(condition_binding=binding, supports_acceptance=['A18-02'])
    add('owned-crash-native', 'deliverables/p13-live/owned-crash-results.json', ('native', 'process'),
        scope='Codex owned 실제5 journal경계/controller SIGKILL·child5/turn5/기본도구5·counter각1. 모델전2경계 회복은 최초실행, 나머지추가모델0. after-execution은child정상완료후/답journal전. reply-stored만이며 nativeMCP/UI/ACK/certain-current-caller 증거 아님',
        predicate=lambda d: owned_crash_checks(root, d))
    result['owned-crash-native']['assurance_limits'] = {
        'native_MCP_calls': 0, 'publication': 'publish_owned(wake=False), reply-stored only',
        'caller_identity': 'not upgraded; actual registry.me endpoint re-registered privately; recorded cwd differs from app-server cwd',
        'mid_tool_write_or_child_running_kill': 'not observed; after-execution is after terminal child completion',
        'effects_exactly_once_general_guarantee': False}
    add('owned-crash-manifest', 'deliverables/p13-live/owned-crash-manifest.json',
        scope='고정 source/실행·offline audit/결과/5경계 원journal·native stdout hash 결속. 기존프로필 startup/MCP 호환 성공으로 확대하지 않음',
        predicate=lambda d: owned_manifest_checks(root, d))
    add('owned-crash-offline-source', 'deliverables/p13-live/owned-crash-audit.py',
        scope='실제 표본의 읽기 전용 감사 source. 이 색인 갱신에서 실행하거나 새 모델을 부르지 않음', execution='source-only')
    add('owned-crash-report', 'deliverables/p13-live/owned-crash-summary.md',
        scope='5경계 의미·publish 저장상태·owner/cwd 한계의 설명. 전체P08/J05/네트워크 행렬 완료 아님', execution='scope-document')
    binding = postqa_criterion_binding(root, 'A18-08', result)
    valid = all(binding['checks'].values())
    add('postqa-bound-A18-08', 'deliverables/p13-live/post-qa-regression.json', ('fixture', 'process', 'native'),
        scope='A18-08의 owned journal5경계 및 기존process/cancel/immutable-answer 반례만 종결. nativeMCP/수신UI/ACK/현재caller확실성·mid-tool kill을 추가 관측했다고 쓰지 않음',
        predicate=lambda d, b=binding: b['checks'], execution='recorded' if valid else 'binding-pending',
        complete_for={'A18-08': ['fixture', 'process', 'native']} if valid else {})
    result['postqa-bound-A18-08'].update(condition_binding=binding, supports_acceptance=['A18-08'])
    add('worktree-native-raw', 'deliverables/p13-live/worktree-native-20261029-a15.json',
        scope='원 자동 not-completed 결과 보존. 실제3회신에 대한 문자분류 오류는 별도 offline audit에서 정정; 새native 재실행 아님', execution='recorded-source')
    add('worktree-native-audit', 'deliverables/p13-live/worktree-native-20261029-a15.audit.json', ('native',),
        scope='이전313 source의 A15-01 실제sameGitcommon/다른cwd/3질문회신·ACK/추가권한0 기능표본. formalhandshake0, profileguard변화 writer unknown. A24/J09나 새315 source 종결 아님',
        predicate=lambda d: worktree_checks(root, d))
    add('worktree-native-manifest', 'deliverables/p13-live/worktree-native-20261029-a15.manifest.json',
        scope='고유private Git fixture/raw/state hash 포인터. 사용자repo Git/worktree/staging을 사용하지 않은 단일조건', execution='source-manifest')
    add('worktree-native-report', 'deliverables/p13-live/worktree-native-20261029-a15.md',
        scope='수집기오분류·실제기능왕복·handshake0·profile관측한계를 분리한 보고', execution='scope-document')
    add('native-integration-preparation', 'deliverables/p13-live/native-integration-source-manifest.json',
        scope='315files/135primary 새고정본 준비. 두Python 전체회귀 및1parent/2child 후속은 coordinator 결과 전달 전; positive credit 없음',
        execution='pending-no-credit', predicate=lambda d: {'expected_snapshot': d['snapshot'] == '/private/tmp/xsm-native-integration-frozen-tsucjdu0',
            '315_files_135_primary': len(d['files']) == 315 and len(d['stable_product_paths']) == 135})
    add('receipt-filter-M1-local-fix', 'deliverables/p13-live/pending-receipt-review-fix.json', ('fixture', 'process'),
        scope='M1 actual receive gate의 held/blocked red2→green·guard 제거 변이·두Python162 영향 검사. 해당 source의 로컬 수정 근거만이며 이전1695나 진행 중 최종전체회귀로 확대하지 않음',
        predicate=lambda d: {'actual_gate_red_green_mutation': d['logs']['red']['subtest_failures'] == 2
                and d['logs']['green']['passed'] is True and d['logs']['guard_removed_mutation']['mutation_detected'] is True,
            'two_162_impacts': all(d['logs'][k]['tests'] == 162 and d['logs'][k]['passed'] is True
                for k in ('impact_python39', 'impact_python314')),
            'stored_log_hashes': all(r['sha256'] == file_sha(Path(r['path'])) for r in d['logs'].values()),
            'frozen_source_hashes': all(r['sha256'] == file_sha(local(
                Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3'), p)) for p, r in d['source'].items()),
            'no_new_model_or_full_run': d['additional_model_calls'] == d['additional_full_regression_runs'] == 0})
    add('final-receipt-preparation', 'deliverables/p13-live/final-source-manifest.json',
        scope='최종 receipt-filter source315/135 포인터. 완료1697/다른부모N:N은 별도 실행 artifact로 결속하며 manifest 자체로 성공을 만들지 않음',
        execution='source-manifest', predicate=lambda d: {'expected_snapshot': d['snapshot'] == '/private/tmp/xsm-final-receipt-frozen-i3u9pms3',
            '315_files_135_primary': len(d['files']) == 315 and len(d['stable_product_paths']) == 135})
    add('final-regression', 'deliverables/p13-live/final-regression.json', ('fixture', 'process'),
        scope='M1 포함 최종 source315/135: 두Python1697/skip0/원log SHA/current hash 일치. 이전1695/1667과 별도이며 전체계획 완료 아님',
        predicate=lambda d: final_regression_checks(root, d))
    result['final-regression']['epoch_role'] = 'immutable-historical1697'
    result['final-regression']['current_source_observation'] = current_source_binding(root, load_json(local(root, HISTORICAL_MANIFEST)))
    epoch = source_epoch(root)
    add('doctor-privacy-regression', DOCTOR_REGRESSION, ('fixture', 'process'),
        scope='새doctor epoch의 실제 두Python full·exact snapshot/current 및 허용 AST delta 확인 전 pending. old1697 이력과 별개',
        predicate=lambda d: dict(doctor_regression_checks(root, d, load_json(local(root, DOCTOR_MANIFEST))),
            **doctor_delta_checks(root, load_json(local(root, HISTORICAL_MANIFEST)), load_json(local(root, DOCTOR_MANIFEST)))))
    result['doctor-privacy-regression']['source_epoch'] = epoch_summary(epoch)
    add('doctor-privacy-v2-regression', DOCTOR_V2_REGRESSION, ('fixture', 'process'),
        scope='v1 errors1은 원 실패로 보존. v2는 동일 제품+부모종료 테스트 home fixture만 정정한 별도 full epoch',
        predicate=lambda d: dict(doctor_regression_checks(root,d,load_json(local(root,DOCTOR_V2_MANIFEST)),manifest_ref=DOCTOR_V2_MANIFEST),
            **doctor_delta_checks(root,load_json(local(root,HISTORICAL_MANIFEST)),load_json(local(root,DOCTOR_V2_MANIFEST)),worker_fixture=True)))
    add('doctor-privacy-postfix-native-history', 'deliverables/p13-live/doctor-privacy-native-20261029-828fa71c/summary.json',
        ('native', 'review'), scope='실제 doctor v1 진단 privacy/survival positive와 제품 delta Opus 이력만. 실패 v1 full 또는 미실행 v2를 현재 성공으로 전이하지 않음',
        predicate=lambda d: doctor_privacy_native_checks(root,d))
    result['doctor-privacy-postfix-native-history']['supports_acceptance'] = ['A23-07']
    add('doctor-v1-failed-full-history', DOCTOR_REGRESSION,
        scope='두 Python1700/errors1 원 실패와 로그 SHA만 보존; 현재 성공 credit 없음',execution='failure-preserved',
        predicate=lambda d: {'two_actual_failed_fulls':len(d['results'])==2 and all(r['tests']==1700 and r['exit_code']==1
            and r.get('summary')=='FAILED (errors=1)' and file_sha(Path(r['log']))==r['log_sha256'] for r in d['results'])})

    add('pre-M1-1695-regression', 'deliverables/p13-live/native-integration-regression.json', ('fixture', 'process'),
        scope='원Opus 검토 source의 pre-M1 1695개씩 이력만. receipt-filter 포함1697과 구분하며 현재 complete_for 없음',
        predicate=lambda d: {'pre_M1_snapshot': d['snapshot'] == '/private/tmp/xsm-native-integration-frozen-tsucjdu0',
            'two_recorded_1695': len(d['results']) == 2 and all(r['tests'] == 1695 and r['exit_code'] == 0 and r['result'] == 'OK'
                and r['sha256'] == file_sha(Path(r['log'])) for r in d['results']), 'not_whole_plan': d['whole_plan_complete'] is False})
    add('native-delta-Opus-original', 'deliverables/p13-live/native-integration-opus-review.md', ('review',),
        scope='원delta 독립Opus는 Medium1 수정 필요. 보안/불변성 범위 관측을 전체 승인으로 바꾸지 않음',
        authority='independent-review-original-fix-required', predicate=lambda d: {'Medium_recorded': 'medium' in d.lower()})
    add('different-parent-native', 'deliverables/p13-live/different-parent-native-20261029-5564a814/summary.json', ('native',),
        scope='최종source 실제다른 parent_thread_id2/child2·auto typedfallback8/claimACK8·최종수학3·상대file읽기2·parent중계0. sharedMCP아님, cachewarning1/profiledrift unknown 보존',
        predicate=different_parent_checks)
    current_parent = load_json(local(root, 'deliverables/p13-live/different-parent-native-20261029-5564a814/summary.json'))
    result['different-parent-native']['caveats'] = {'runtime_warnings': current_parent['runtime_warnings'],
        'RPC_errors': current_parent['RPC_errors'], 'profile_drift_writer': current_parent['profile_drift_writer'],
        'shared_MCP_success_claimed': False}
    add('native-delta-coordinator-closure', 'deliverables/p13-live/native-integration-review-closure.json', ('review',),
        scope='재모델리뷰 없는 coordinator 로컬종결: M1 actual_gate/guard변이·162영향·1697·최종N:N. unresolvedcaller notice 및 unboundexport unknown 한계 유지; 전체P12/UI 승인 아님',
        authority='coordinator-followup-not-independent-rereview',
        predicate=lambda d: {'original_fix_required': 'Medium1 fix required' in d['original_verdict'],
            'no_second_review_or_whole_approval': d['second_model_review'] is d['product_complete'] is False,
            'specific_final_evidence': result['receipt-filter-M1-local-fix']['executed']
                and result['final-regression']['executed'] and result['different-parent-native']['executed']})
    add('different-parent-manifest', 'deliverables/p13-live/different-parent-native-20261029-5564a814/manifest.json',
        scope='최종N:N 원문/provider 관계/수신/ACK/파일read/실행source SHA 결속. 새모델이나추가실험없음',
        predicate=lambda d: {'raw_and_public_hashes': bool(d['files']) and all(
            (str(Path(r['path']).resolve()).startswith('/private/tmp/different-parent-native-3jr1o8uv/')
             or local(root, 'deliverables/p13-live/different-parent-native-20261029-5564a814') in Path(r['path']).resolve().parents)
            and file_sha(Path(r['path'])) == r['sha256'] for r in d['files']),
            'one_condition_no_retries': d['new_model_conditions'] == 1 and d['automatic_retries'] == 0})
    levels = {i: p['levels'] for i, p in CLOSURE_PROOFS.items()}
    levels.update({'A15-01': ['fixture', 'native'], 'A15-05': ['fixture', 'native'],
                   'A18-02': ['fixture', 'process'], 'A18-08': ['fixture', 'process', 'native']})
    for identifier, kinds in levels.items():
        b = final_binding(root, identifier, result)
        if identifier == 'A15-05':
            b['checks']['native_manifest_bound'] = result['different-parent-manifest']['executed']
        valid = all(v is True for v in b['checks'].values())
        add('final-bound-' + identifier, source_epoch(root)['regression_path'], kinds,
            scope=identifier + ': 선택 epoch의 실제 full·specific selector·현재 source·범위한정 native 재결속만',
            predicate=lambda d, b=b: b['checks'], execution='recorded' if valid else 'binding-pending',
            complete_for={identifier: kinds} if valid else {})
        result['final-bound-' + identifier].update(condition_binding=b, supports_acceptance=[identifier])
    late_proofs = (
        ('A16-04', 'sandbox-first-reply-native', 'first-reply-mcp-evidence.json', ['native'], first_reply_checks, {}),
        ('A16-02', 'async-independent-native', 'async-independent-native-audit.json', ['fixture', 'native'], async_work_checks,
            {'tests/test_questions.py': ['test_receipt_is_not_answer_and_late_reply_is_recovered',
                'test_timeout_cancel_keep_index_and_inbox_then_late_answer']}),
        ('A19-06', 'version-review-native', 'version-review-native-20261029-a19.audit.json', ['fixture', 'native'], version_review_checks,
            {'tests/test_files.py': ['test_changed_original_during_approval_requires_new_manifest_version',
                'test_explicit_export_frozen_keeps_old_version_without_reopening_source',
                'test_same_manifest_reused_with_changed_material_never_replaces_received_copy']}),
        ('A16-06', 'owned-memory-path-comparison', 'owned-default-closure-audit.json', ['native'], owned_memory_checks, {}),
        ('A16-05', 'cached-inbox-recovery-native', 'recovery-passive-closure-results.json', ['fixture', 'native'],
            lambda root, d: passive_recovery_checks(root, d, 'A16-05'),
            {'tests/test_question_interfaces.py': ['test_internal_MCP_route_is_passive_without_mutating_logical_wake',
                'test_pending_notice_uses_cached_caller_without_another_registry_lookup']}),
        ('A18-06', 'natural-FYI-consumption-native', 'recovery-passive-closure-results.json', ['fixture', 'native'],
            lambda root, d: passive_recovery_checks(root, d, 'A18-06'),
            {'tests/test_b04_interfaces.py': ['test_natural_mcp_boundary_receives_fyi_without_any_transport']}),
        ('A23-07', 'doctor-privacy-native-and-review', 'doctor-privacy-native-20261029-828fa71c/summary.json',
            ['fixture', 'native', 'review'], doctor_privacy_native_checks,
            {'tests/test_install_cli_flow.py': ['test_doctor_json_selects_metadata_and_fixed_failure_categories',
                'test_doctor_text_never_uses_private_errors_as_failure_labels',
                'test_doctor_table_does_not_disclose_stored_message_or_error']}),
        ('A22-03', 'strict-multireview-recovery-native', 'strict-review-native-audit.json', ['fixture', 'native'], strict_review_checks,
            {'tests/test_traffic_interfaces.py': ['test_strict_defer_retains_original_and_same_id_passive_retry_after_window']}),
        ('A17-04', 'directory-extraction-closure', 'directory-extraction-closure-audit.json', ['fixture', 'native', 'review'], directory_extraction_checks,
            {'tests/test_directory.py': ['test_native_rename_is_current_and_resume_retains_id',
                'test_codex_native_summary_branch_source_freshness_and_busy_idle']}),
        ('A16-08', 'owned-capacity-and-isolation-native', 'independent-review-native-20261029-final/check.json',
            ['fixture', 'process', 'native'], owned_isolation_checks,
            {'tests/test_owned_workers.py': ['test_same_sender_work_resumes_two_senders_jobs_and_review_stay_isolated',
                'test_same_context_serial_other_context_parallel_capacity_plus_one_queued'],
             'tests/test_owned_requests.py': ['test_explicit_context_retirement_keeps_old_request_and_fresh_native_identity']}))
    late_proofs += (
        ('A16-01','persistent-CLI-MCP-parity','persistent-parity-native-v3-20261029.audit.json',['fixture','native'],parity_native_checks,
            {'tests/test_question_interfaces.py':['test_cli_and_MCP_wait_return_on_canonical_arrival_not_deadline']}),
        ('A19-01','persistent-file-parity','persistent-parity-native-v3-20261029.audit.json',['fixture','native'],parity_native_checks,
            {'tests/test_file_interfaces.py':['test_inline_mcp_send_receive_read_copy_preserves_original_body_and_bytes','test_cli_hidden_file_to_mcp_copy_read_needs_no_server_source_path_read']}),
        ('A17-05','native-caller-exclusion','exclusion-cli-native-20261029-6c6ee4c8/summary.json',['fixture','native'],
            lambda r,d:exclusion_native_checks(r,d,'A17-05'),{'tests/test_directory_contract.py':['test_exclusion_enforcement_across_registration_listing_and_attachments']}),
        ('A19-03','native-CLI-exclusion-materials','exclusion-cli-native-20261029-6c6ee4c8/summary.json',['fixture','native'],
            lambda r,d:exclusion_native_checks(r,d,'A19-03'),{'tests/test_files.py':['test_known_credential_paths_are_rejected_without_opening_them','test_excluded_or_unknown_source_policy_is_not_exported']}),
        *((identifier,'delivery-recovery-rebound-'+identifier,'delivery-recovery-upgrade-rebinding.json',['fixture','process','native'],
            lambda r,d,i=identifier:delivery_rebinding_checks(r,d,i),{}) for identifier in ('A18-01','A18-02','A23-08')),
        *((identifier,'policy-compatibility-'+identifier,'policy-compatibility-rebinding.json',kinds,
            lambda r,d,i=identifier:policy_rebinding_checks(r,d,i),{}) for identifier,kinds in (
                ('A16-07',['fixture','process','native']),('A22-02',['fixture','review']),('A23-05',['fixture','process','review']))))
    for identifier, key, artifact, kinds, predicate, cases in late_proofs:
        def checks(d, predicate=predicate, cases=cases):
            return dict(predicate(root, d), **scoped_current_checks(root, cases),
                        historical1697_execution=result['final-regression']['executed'])
        add(key, 'deliverables/p13-live/' + artifact, kinds,
            scope=identifier + ': 실제 native 원문/사본/상관 ACK 이력과 선택 source epoch를 별도 결속. 프로필 drift 한계 보존; 다른 조건/clean 설치로 확대하지 않음',
            predicate=checks)
        result[key]['source_epoch'] = epoch_summary(source_epoch(root))
        if result[key]['executed'] and source_epoch(root)['ready'] and (identifier != 'A23-07' or source_epoch(root)['manifest_path'] == DOCTOR_V2_MANIFEST):
            result[key]['complete_for'] = {identifier: kinds}
        result[key]['supports_acceptance'] = [identifier]
    for key in ('native-caller-exclusion','native-CLI-exclusion-materials'):
        result[key]['assurance_limits'] = {'original_experiment_open_postread_counts':'원 실행 window의 0을 보존; 모든 향후 감사 접근이 0이라는 주장이 아님',
            'auditor_initial_helper_posthash':'초기 표적 검사에서 합성 protected 원본1건을 사후 hash함. 내용 출력/복사/제품 실행 없음. 수정 helper는 setup SHA/stat만 검증하고 해당 원본을 열지 않음.'}
    add('policy-compatibility-A19-04-partial','deliverables/p13-live/policy-compatibility-rebinding.json',('fixture','native'),
        scope='원 capability/구버전/본문 fallback fixture는 있음. 정상 사본 native를 조건부 fallback native로 승격하지 않아 partial 유지',
        predicate=lambda d:{'native_partial_not_promoted':d['conditions']['A19-04']['native']=='partial' and d['conditions']['A19-04']['whole_condition'].startswith('partial-'),
            'specific_fixture_selectors':selector_rows_bound(root,d['conditions']['A19-04']['fixture_selectors'])})
    result['policy-compatibility-A19-04-partial']['supports_acceptance']=['A19-04']
    add('topology-scoped-rebinding','deliverables/p13-live/topology-rebinding.json',('native',),
        scope='일반/형제/다른부모 raw 성공만 재사용. distinct historical Gitcommon crossrepo1셀은 미확보이며 전체 A22-04 partial',
        predicate=lambda d:topology_partial_checks(root,d))
    result['topology-scoped-rebinding']['supports_acceptance']=['A22-04']
    add('strict-defer-recovery-native-partial', 'deliverables/p13-live/recovery-passive-closure-results.json', ['native'],
        scope='실제 strict held→원 ID 조회/재전송/최종회신·ACK15검사. 같은 조건의 다회수정 대조는 미충족',
        predicate=lambda d: dict(passive_recovery_checks(root, d, 'A18-06'),
            strict_same_ID_recovery=len(d['A22-03']['checks']) == 15 and all(d['A22-03']['checks'].values())))
    result['strict-defer-recovery-native-partial']['supports_acceptance'] = ['A22-03']
    add('material-boundary-native-partial', 'deliverables/p13-live/material-boundary-native-20261029-a30cd9e0/summary.json', ['native'],
        scope='OS읽기/inline/수신사본3종·mode000 거절. CLI 원경로/제외 API는 미관측, inline 원경로 보장 unknown',
        predicate=lambda d: {'three_actual_reads_and_OS_denial': d['actual_receiver_entry_reads'] == 3
            and d['OS_mode000_errno13'] is True and d['negative_cases_transmitted'] == []
            and d['actual_ACK_IDs'] == 2 and d['correlated_reply_to_preserved'] is True,
            'partial_scope_retained': d['whole_A19_03_proven'] is False and d['CLI_attempts'] == 0,
            'raw_manifest': all(file_sha(Path(r['path'])) == r['sha256'] for r in load_json(local(root,
                'deliverables/p13-live/material-boundary-native-20261029-a30cd9e0/manifest.json'))['files']
                if 'sha256' in r)})
    result['material-boundary-native-partial']['supports_acceptance'] = ['A19-03']
    add('session-lifetime-native-partial', 'deliverables/p13-live/session-lifetime-native-20261029-37d06cbd/summary.json', ['native'],
        scope='실제 동명 새CID 미독0·원CID 새PID resume 원문회수/상관reply. ACK0·선택pair권한 미검증·추출metadata 부분만',
        predicate=lambda d: {'native_unread_lifecycle': all(d['checks'][k] is True for k in
            ('old_new_real_CID_different', 'old_resume_real_CID_same', 'new_native_inbox_empty',
             'old_unchanged_through_new', 'resumed_real_claim_original', 'correlated_reply_original')),
            'missing_ACK_and_permission_not_promoted': d['actual_ACK_ID_count'] == 0
                and d['whole_A17_06_proven'] is d['whole_A17_04_proven'] is False,
            'raw_manifest': all(file_sha(Path(r['path'])) == r['sha256'] for r in load_json(local(root,
                'deliverables/p13-live/session-lifetime-native-20261029-37d06cbd/manifest.json'))['files'])})
    result['session-lifetime-native-partial']['supports_acceptance'] = ['A17-04', 'A17-06']
    add('owned-capacity-native-partial', 'deliverables/p13-live/owned-capacity-native-20261029-bundle/check.json', ['native'],
        scope='실제 sender2·owned10turn의 기억/직렬화·retirement/UNKNOWN·4busy+다른sender 회수. profile drift·independent native 누락 유지',
        predicate=lambda d: {'behavioral_checks': d['behavioral_checks_pass'] is True
                and d['failed_checks'] == ['profile_config_unchanged'] and d['all_pass'] is False,
            'actual_turns': d['details']['actual_counts']['owned_native_turns'] == 10
                and d['details']['actual_counts']['actor_native_turns'] == 2,
            'request_subset_and_raw_rebinding': all(capacity_rebinding_checks(root, load_json(local(root,
                'deliverables/p13-live/independent-review-native-20261029-final/capacity-rebinding-audit.json'))).values())})
    result['owned-capacity-native-partial']['supports_acceptance'] = ['A16-08', 'A23-06']
    # Positive credit is narrower than a same-kind artifact link. In particular,
    # separate-profile native calls are not a shared-MCP A/B proof, and LAN TCP
    # is not a UDP/IPv6/team-membership or selected-backend proof.
    add('head-rebind-regression', REBIND + 'summary.json', ('fixture', 'process'),
        scope='현재 HEAD 동결본의 두 Python 전체 회귀만. 이전 native/UI/physical 실행을 현재 소스로 옮기지 않음',
        predicate=lambda d: head_rebind_regression_checks(root, d))
    for identifier in ('A18-03', 'A18-07', 'A22-06', 'A23-02', 'shared-mcp'):
        rebind = head_rebind_criterion_checks(root, identifier, result)
        valid = all(v is True for v in rebind.values())
        levels = ('fixture',) if identifier == 'shared-mcp' else tuple(CLOSURE_PROOFS[identifier]['levels'])
        supports = ['A17-02', 'A19-02', 'A23-03'] if identifier == 'shared-mcp' else [identifier]
        add('head-rebind-' + identifier, REBIND + 'summary.json', levels,
            scope=('공유 MCP 실제 프로세스 A/B·다른 홈·상속 env 격리 fixture만. 실제 Codex 하네스(native)는 미관측'
                   if identifier == 'shared-mcp' else
                   identifier + ': 원 구체 반례를 현재 HEAD 전체 회귀로 재실행한 fixture/process만'),
            predicate=lambda d, rebind=rebind: rebind, execution='recorded' if valid else 'binding-pending',
            complete_for={i: list(levels) for i in supports} if valid else {})
        result['head-rebind-' + identifier]['supports_acceptance'] = supports
    # ADR21 records (two Macs, a phone on another NAT, fault injection). They ran on
    # sources before the later receive/handoff change, so they stay partial here.
    for key, path, levels, supports, scope, predicate in (
            ('adr21-samename-latest', 'native-journey-samename-latest-20261029T152847Z/results.json', ('native', 'physical'),
             ['A21-04', 'A24-03', 'A24-05', 'A24-08'],
             'E15: 두 Mac 동명 후보의 실제 원격 선택·handshake·직접 회신·양쪽 MCP ACK. 5e20 53모듈 소스; 이후 receive/handoff 변경',
             lambda d: {'passed': d['status'] == 'passed', 'all_checks': bool(d['checks']) and all(v is True for v in d['checks'].values()),
                        'source_bound': load_json(local(root, ADR21 + 'native-journey-samename-latest-20261029T152847Z/source-binding.json'))['latest_final_source_differences'] == []}),
            ('adr21-two-mac-journeys', 'native-journey-20261029T060853Z-fresh164-v2/resume-results.json', ('native', 'physical'),
             ['A21-04'],
             'E10: 두 물리 Mac Codex 같은 CID 재개와 혼합 런타임 자료 여정. 당시 소스·profile 관측 제한 유지',
             lambda d: {'resume_completed': d['completed'] is True,
                        'mixed_journey_completed': load_json(local(root, ADR21 + 'native-journey-mixed-proc-20261029T084031Z/results-final.json'))['status'].startswith('공개 후보 선택')}),
            ('adr21-physical-policy', 'physical-policy-20261029T073330Z/results.json', ('physical',),
             ['A21-02', 'A21-06'],
             'E6: 두 Mac·3노드 멤버십·공개/제외 정책. FILE actor, 모델 0회',
             lambda d: {'completed': d['completed'] is True}),
            ('adr21-ipv6-port-fallback', 'carrier-ipv6-fault-resolved-20261029T085407Z/result.json', ('fixture',),
             ['A21-07'],
             'E13: 같은 호스트 엔진별 IPv6 EAFNOSUPPORT·점유 포트 대체 bind. 호스트 전체 IPv6 부재 아님',
             lambda d: {'passed': d['passed'] is True}),
            ('adr21-phone-nat', 'phone-nat-20261029T0817Z/results.json', ('physical',),
             ['A21-01', 'A21-07'],
             'E4: Mac·Android 다른 공인 IPv4 구간 relay 왕복과 실행 중 주소 변경. 같은 NAT에서 가입한 기존 멤버, 모델 0회',
             lambda d: {'different_IPv4': d['different_IPv4_before_and_after'] is True, 'not_whole_ADR': d['whole_ADR_complete'] is False}),
            ('adr21-selfhost-relay', 'physical-core-selfhost-20261029-product-results.json', ('process',),
             ['A21-01'],
             'E3: 공식 자체 relay(loopback HTTP 개발 relay)에서 제품 가입·왕복. 외부 HTTPS 자체 서버 운영 아님',
             lambda d: {'verified': d['status'] == 'actual-product-local-selfhost-verified'}),
            ('adr21-final-review', 'final-review-20261030/summary.json', ('review',),
             ['A21-03', 'A21-06'],
             'Opus 5.5 지정 변경 범위 정적 검토(5e20). 실제 네트워크·ADR 전체 승인 아님',
             lambda d: {'approved': d['verdict'] == 'approved', 'no_findings': d['findings'] == [],
                        'actual_model': d['actual_model'] == 'claude-opus-5-5'})):
        add(key, ADR21 + path, levels, scope=scope, predicate=predicate)
        result[key]['supports_acceptance'] = supports
    scoped = {
      'g02-native': ['A15-02', 'A15-06', 'A20-07'],
      'b03-question': ['A15-01', 'A16-01', 'A16-02', 'A16-03', 'A24-05'],
      'b03-mcp': ['A16-01', 'A16-02', 'A16-03', 'A17-01', 'A17-04', 'A24-01', 'A24-04', 'A24-05'],
      'b03-handshake': ['A24-04', 'A24-05', 'A24-08'],
      'b04-native': ['A18-02', 'A18-05', 'A18-06', 'A22-04', 'A22-05'],
      'p06-native': ['A19-01', 'A19-03'],
      'p06-claude-native': ['A19-01', 'A19-03'],
      'p08-owned-mcp-native': ['A16-06', 'A16-08', 'A18-08', 'A23-06'],
      'p09-native': ['A22-03', 'A22-04', 'A22-05'],
      'p10-upgrade-native': ['A23-02', 'A23-08', 'A18-04'],
      'p11-abd-native': ['A21-01', 'A21-03', 'A21-05'],
      'p11-c-native': ['A21-01', 'A21-03', 'A21-05'],
      'p11-c-evidence-check': ['A21-03'],
      'p11-opus-review': ['A21-03'],
      'p11-review-closure': ['A21-03'],
      'p12-prep-contract': ['A21-02', 'A22-01', 'A22-02', 'A24-02'],
      'p13-natural-audit': ['A16-04', 'A18-05', 'A18-06', 'A22-03', 'A24-05'],
      'postclaims-native': ['A16-04', 'A18-05', 'A18-06', 'A22-03', 'A24-05'],
      'clean-install-final': ['A23-01', 'A23-02', 'A23-04', 'A23-05', 'A23-08'],
      'postqa-regression': ['A18-03', 'A18-07', 'A19-05', 'A22-06', 'A23-02'],
      'udp-native': ['A21-01', 'A21-03'],
      'udp-offline-check': ['A21-01', 'A21-03'],
      'factory-handoff-native': ['A18-02'],
      'owned-crash-native': ['A18-08'],
      'worktree-native-audit': ['A15-01'],
      'different-parent-native': ['A15-05'],
      'C-noSSH-v2': ['A21-01', 'A21-03'],
      'C-proxy-variant': ['A21-01', 'A21-03'],
      'remote-comparison': ['A21-01', 'A21-03', 'A21-05'],
    }
    for key, identifiers in scoped.items():
        result[key]['supports_acceptance'] = identifiers
    return result


def bindings(identifier):
    adr = int(identifier[1:3])
    refs = {15: ['gate-G02', 'g02-native'], 16: ['gate-G03', 'b03-regression', 'b03-question', 'b03-mcp'],
            17: ['gate-G05', 'b03-regression', 'b03-mcp'], 18: ['b04-regression', 'b04-native', 'b04-legacy'],
            19: ['p06-native'], 20: ['b04-regression', 'ui-intent-1', 'ui-intent-2'],
            21: ['remote-comparison'], 22: ['b04-regression'], 23: ['p10-cli'],
            24: ['gate-G02', 'gate-G03', 'gate-G05', 'b03-regression', 'b03-handshake']}[adr]
    refs = list(refs)
    if identifier in ('A16-06', 'A16-08', 'A18-08', 'A23-06'):
        refs = ['p08-native', 'p08-capacity', 'p08-capacity-readback']
    if identifier == 'A15-01':
        refs += ['b03-question', 'worktree-native-audit', 'worktree-native-raw', 'worktree-native-manifest', 'worktree-native-report']
    if identifier in ('A16-04', 'A23-01'):
        refs.append('b03-sandbox')
    if identifier in ('A16-06', 'A16-08', 'A18-08', 'A23-06'):
        refs += ['p08-native', 'p08-capacity', 'p08-capacity-readback']
    if identifier in ('A17-04',):
        refs.append('b03-human-sample')
    if identifier in ('A18-01', 'A18-03', 'A17-02', 'A23-03'):
        refs.append('gate-G01')
    if identifier == 'A20-06':
        refs.append('p07-os')
    if identifier in ('A22-04', 'A22-05', 'A23-03', 'A23-08'):
        refs += ['b04-native', 'b04-legacy']
    if identifier == 'A23-04':
        refs += ['ui-intent-1', 'ui-intent-2']
    # Local gates and bounded native samples only; no complete_for credit.
    if adr in (18, 19, 22, 23):
        refs.append('b05-local-integration')
    if adr == 19:
        refs += ['gate-G06', 'p06-claude-native']
    if identifier in ('A16-06', 'A16-08', 'A18-08', 'A23-06'):
        refs += ['gate-G08', 'p08-owned-mcp-native']
    if adr == 22:
        refs += ['gate-G09', 'p09-native']
    if adr == 23:
        refs += ['gate-G10', 'p10-upgrade-native']
    if adr == 21:
        refs += ['p11-abd-native', 'p11-c-native', 'p11-c-evidence-check']
    if identifier == 'A21-03':
        refs += ['p11-opus-review', 'p11-review-closure']
    if identifier in ('A21-02', 'A22-01', 'A22-02', 'A24-02'):
        refs.append('p12-prep-contract')
    if identifier == 'A18-04':
        refs.append('p10-upgrade-native')
    if identifier in CLOSURE_PROOFS:
        refs.append('p13-bound-' + identifier)
        refs.append('postqa-bound-' + identifier)
    if identifier in ('A16-04', 'A18-05', 'A18-06', 'A22-03', 'A24-05'):
        refs.append('p13-natural-audit')
    if identifier == 'A19-05':
        refs += ['p13-local-regression', 'postqa-regression']
    if identifier in ('A23-01', 'A23-02'):
        refs.append('p13-clean-install-counterexample')
    if identifier in ('A23-01', 'A23-02', 'A23-04', 'A23-05', 'A23-08'):
        refs += ['clean-install-final', 'clean-install-report']
    if identifier in ('A16-04', 'A18-05', 'A18-06', 'A22-03', 'A24-05'):
        refs.append('postclaims-native')
    if identifier in ('A21-01', 'A21-03'):
        refs += ['udp-native', 'udp-offline-check']
        refs += ['C-noSSH-v2', 'C-noSSH-v2-manifest', 'C-proxy-variant', 'C-proxy-variant-manifest']
    if identifier == 'A18-02':
        refs += ['native-handoff-first-preparation', 'native-handoff-workspace-preparation', 'native-handoff-factory-pending']
        refs += ['factory-handoff-native', 'factory-handoff-manifest', 'factory-handoff-report', 'postqa-bound-A18-02-local']
    if identifier == 'A18-08':
        refs += ['owned-crash-native', 'owned-crash-manifest', 'owned-crash-offline-source', 'owned-crash-report', 'postqa-bound-A18-08']
    if identifier in set(CLOSURE_PROOFS) | {'A15-01', 'A15-05', 'A18-02', 'A18-08'}:
        refs.append('final-bound-' + identifier)
    if identifier == 'A15-05':
        refs += ['different-parent-native', 'different-parent-manifest']
    for accepted, key in (('A16-04', 'sandbox-first-reply-native'), ('A16-02', 'async-independent-native'),
                          ('A19-06', 'version-review-native'), ('A16-06', 'owned-memory-path-comparison'),
                          ('A16-05', 'cached-inbox-recovery-native'), ('A18-06', 'natural-FYI-consumption-native'),
                          ('A16-08', 'owned-capacity-and-isolation-native')):
        if identifier == accepted:
            refs.append(key)
    for accepted, key in (('A22-03', 'strict-defer-recovery-native-partial'), ('A19-03', 'material-boundary-native-partial'),
                         ('A17-04', 'session-lifetime-native-partial'), ('A17-06', 'session-lifetime-native-partial'),
                         ('A16-08', 'owned-capacity-native-partial'), ('A23-06', 'owned-capacity-native-partial')):
        if identifier == accepted:
            refs.append(key)
    if identifier == 'A22-03': refs.append('strict-multireview-recovery-native')
    if identifier == 'A17-04': refs.append('directory-extraction-closure')
    if identifier == 'A23-07': refs.extend(['doctor-privacy-native-and-review','doctor-privacy-postfix-native-history'])
    extra_refs={'A16-01':'persistent-CLI-MCP-parity','A19-01':'persistent-file-parity','A17-05':'native-caller-exclusion',
        'A19-03':'native-CLI-exclusion-materials','A19-04':'policy-compatibility-A19-04-partial','A22-04':'topology-scoped-rebinding'}
    if identifier in extra_refs:refs.append(extra_refs[identifier])
    if identifier in ('A18-01','A18-02','A23-08'):refs.append('delivery-recovery-rebound-'+identifier)
    if identifier in ('A16-07','A22-02','A23-05'):refs.append('policy-compatibility-'+identifier)
    if identifier in ('A18-03', 'A18-07', 'A22-06', 'A23-02'):
        refs.append('head-rebind-' + identifier)
    if identifier in ('A17-02', 'A19-02', 'A23-03'):
        refs.append('head-rebind-shared-mcp')
    adr21 = {'A21-01': ['adr21-phone-nat', 'adr21-selfhost-relay'], 'A21-02': ['adr21-physical-policy'],
             'A21-03': ['adr21-final-review'], 'A21-04': ['adr21-samename-latest', 'adr21-two-mac-journeys'],
             'A21-06': ['adr21-physical-policy', 'adr21-final-review'],
             'A21-07': ['adr21-ipv6-port-fallback', 'adr21-phone-nat'],
             'A24-03': ['adr21-samename-latest'], 'A24-05': ['adr21-samename-latest'], 'A24-08': ['adr21-samename-latest']}
    refs += adr21.get(identifier, [])
    return sorted(set(refs))


def environment_bindings(identifier):
    result = []
    if identifier.startswith('A20-') and identifier not in ('A20-05', 'A20-07') or identifier == 'A23-04':
        result += ['human-UI', 'UI-late-cancel-focus-race']
    if identifier.startswith(('A21-', 'A24-')) or identifier in ('A17-01', 'A17-03', 'A18-04', 'A19-04', 'A23-04', 'A23-05'):
        result += ['selected-backend-D12', 'physical-native-peer']
    if identifier in ('A21-01', 'A21-03'):
        result += ['different-NAT', 'UDP-blocked', 'HTTPS-proxy', 'self-hosted-relay', 'SSH-unavailable', 'remote-C-two-machines']
    return sorted(set(result))


def environments(evidence, plan):
    definitions = {
      'human-UI': ('UI', ['ui-intent-1', 'ui-intent-2', 'p07-os'], '실제 화면·원문 전체·사람의 응답 관측 없음. OS exit 0은 화면 확인이 아님.'),
      'UI-late-cancel-focus-race': ('UI', ['ui-intent-1', 'ui-intent-2'], '실제 중복 창·포커스·늦은 답/철회/취소 경쟁 없음.'),
      'different-NAT': ('physical', ['remote-comparison'], '다른 회선/NAT 실측 미확보. 동일 LAN/egress로 대체 금지.'),
      'UDP-blocked': ('physical', ['udp-native', 'udp-manifest', 'udp-offline-check'], 'C own-daemon child kernel UDP deny+양쪽 peer link relay+추가 native1은 관측. A/B/D·global firewall·다른NAT·자체relay·전체 제품 경로는 미검증이므로 범위한정 partial.'),
      'HTTPS-proxy': ('physical', ['C-proxy-variant', 'C-proxy-variant-manifest'], 'C own-engine loopback CONNECT/TLS direct-deny/native1/양쪽relay 부분관측. 기업인증proxy·전역network·A/B/D·P12 성공 아님.'),
      'self-hosted-relay': ('physical', ['remote-comparison'], '자체 relay 서버/실제 전환 관측 없음.'),
      'SSH-unavailable': ('physical', ['C-noSSH-v2', 'C-noSSH-v2-manifest'], 'C bootstrap 이후 own-process TCP22deny/windowSSH0/native1 부분관측. 신규설치 무SSH·전역network·다른backend·제품peer 여정은 미검증.'),
      'remote-C-two-machines': ('physical', ['p11-c-native', 'p11-c-evidence-check', 'p11-c-manifest'], '격리 C 두 물리 머신의 native direct 6회와 offline evidence 검사. 제품 peer 발견/승인/handshake 및 다른 NAT/relay 성공과 별개.'),
      'physical-native-peer': ('physical', ['p11-abd-native', 'p11-c-native'], 'carrier native 왕복은 있으나 제품 peer discovery→approval→handshake 전체 trace 없음.'),
      'selected-backend-D12': ('decision', [], 'D12 backend 선택은 사용자 결정이며 색인이 대신 승인하지 않음.'),
    }
    result = {key: {'level': level, 'status': 'missing', 'context_refs': refs, 'reason': reason,
                  'owner': '코디네이터 및 해당 실환경 검증 담당',
                  'revisit': '해당 실제 환경/실행 근거와 필요한 사용자 결정이 확보되면 재평가'}
            for key, (level, refs, reason) in definitions.items()}
    if all(evidence[key]['executed'] for key in ('p11-c-native', 'p11-c-evidence-check')) and evidence['p11-c-manifest']['available']:
        result['remote-C-two-machines']['status'] = 'proven'
    if all(evidence[key]['executed'] for key in ('udp-native', 'udp-manifest', 'udp-offline-check')):
        result['UDP-blocked']['status'] = 'partial'
    for environment, refs in (('SSH-unavailable', ('C-noSSH-v2', 'C-noSSH-v2-manifest')),
                              ('HTTPS-proxy', ('C-proxy-variant', 'C-proxy-variant-manifest'))):
        if all(evidence[k]['executed'] for k in refs):
            result[environment]['status'] = 'partial'
    # ADR21 observations: each is one bounded sample on a source before the later
    # receive/handoff change, so none closes its environment.
    for environment, key, reason in (
            ('physical-native-peer', 'adr21-samename-latest',
             'E15 두 Mac 제품 후보 발견→사용자 선택→handshake→직접 회신·양쪽 MCP ACK 관측(5e20 소스). 이후 receive/handoff 변경과 다른 환경·자동 wake는 미검증.'),
            ('different-NAT', 'adr21-phone-nat',
             'E4 Mac·Android 다른 공인 IPv4 relay 왕복 관측. 같은 NAT에서 가입한 기존 멤버의 이동이며 모델 협업·다른 NAT 신규 가입은 미검증.'),
            ('self-hosted-relay', 'adr21-selfhost-relay',
             'E3 공식 자체 relay(loopback HTTP 개발 relay) 제품 가입·왕복 관측. 외부 HTTPS 자체 서버 운영은 미검증.')):
        if evidence[key]['executed']:
            result[environment].update(status='partial', reason=reason,
                                       context_refs=sorted(set(result[environment]['context_refs']) | {key}))
    if 'D12' in plan.get('decision_resolutions', {}):
        result['selected-backend-D12'].update(status='partial', context_refs=[BASE + 'plan.json#/decision_resolutions/D12'],
            reason='사용자가 ADR-0021로 자체 P2P 기본·선택적 Tailscale·Reason식 멤버십을 결정(2026-10-29). 결정 기록은 backend 통합 성공의 증거가 아님.')
    return result


def classify(cells, environment_ids, env):
    statuses = [cell['status'] for cell in cells.values()] + [env[key]['status'] for key in environment_ids]
    if 'contradicted' in statuses:
        return 'contradicted'
    if statuses and all(status == 'proven' for status in statuses):
        return 'proven'
    if any(status in ('proven', 'partial') for status in statuses):
        return 'partial'
    return 'missing'


def closure_gate_blockers(requirement, gate_statuses):
    # G13 is a final product/integration gate, not a recursive per-row prerequisite.
    return [key for key in requirement['closure_gates'] if key != 'G13'
            and gate_statuses.get(key) != 'passed']


def acceptance_status(cells, environment_ids, env, blocked_gates):
    state = classify(cells, environment_ids, env)
    return 'partial' if state == 'proven' and blocked_gates else state


def cells_for(levels, refs, evidence, identifier, related=()):
    result = {}
    for level in sorted(set(levels)):
        candidates = [key for key in refs if level in evidence[key]['levels']]
        matching = [key for key in candidates if 'supports_acceptance' not in evidence[key] or
                    set(evidence[key]['supports_acceptance']) & ({identifier} | set(related))]
        recorded = [key for key in matching if evidence[key]['available'] and evidence[key]['executed']]
        full_scope = [key for key in recorded if level in evidence[key]['complete_for'].get(identifier, [])]
        result[level] = {'status': 'proven' if full_scope else 'partial' if recorded else 'missing', 'refs': matching,
                         'full_scope_refs': full_scope,
                         'context_only_refs': [key for key in candidates if key not in matching],
                         'scope': '지정 criterion/level의 구체 경로·실행·hash 결속으로 종결; 다른 조건/환경으로 전이 금지' if full_scope else
                                  '기록된 한정 표본만 재사용; 조건 전수/현재 통합 증거로 자동 승격하지 않음' if recorded
                                  else '해당 종류의 실행 증거 없음. source/intent/다른 환경으로 대체하지 않음'}
    return result


def build(root, plan, spec):
    # 한 build 안에서만 동일 source 관측을 재사용한다. 다음 build는 새로 읽는다.
    token = _BUILD_SOURCE_EPOCH.set((root.resolve(), _read_source_epoch(root)))
    try:
        return _build(root, plan, spec)
    finally:
        _BUILD_SOURCE_EPOCH.reset(token)


def _build(root, plan, spec):
    acceptance, residuals, journeys = inventories(plan, spec)
    evidence = catalog(root)
    env = environments(evidence, plan)
    groups = {'acceptance': [], 'residuals': [], 'journeys': []}
    gate_statuses = {g['id']: g['status'] for g in plan['execution']['gates']}
    for item in acceptance:
        identifier = item['id']
        refs = bindings(identifier)
        levels = [LEVELS[level] for level in item['evidence_levels']]
        environment_ids = environment_bindings(identifier)
        cells = cells_for(levels, refs, evidence, identifier)
        blocked_gates = closure_gate_blockers(item, gate_statuses)
        state = acceptance_status(cells, environment_ids, env, blocked_gates)
        steps = item['closure_steps']
        source = sorted(set(item['implementation_paths'] + [path for step in steps for path in EXTRA_SOURCE.get(step, [])]))
        tests = sorted({'tests/' + name + '.py' for step in steps for name in TESTS.get(step, [])})
        groups['acceptance'].append({'id': identifier, 'requirement': copy.deepcopy(item),
            'required_levels': sorted(set(levels)), 'evidence': cells, 'context_refs': refs,
            'required_environments': environment_ids, 'status': state,
            'blocked_closure_gates': blocked_gates,
            'source_paths': source, 'test_sources': tests,
            'source_presence': {name: local(root, name).exists() for name in source + tests},
            'gap': ('해당 criterion의 지정 evidence cell 및 closure gate 충족. 전체 product/G13 완료와 별개.'
                    if state == 'proven' else GAPS[identifier]),
            'owner': item['owner_step'] + ' 구현/실환경 검증 담당 및 코디네이터',
            'revisit': '조건별 남은 실제 증거와 해당 closure gate/통합 revision이 확보되면 재평가',
            'skip_authorized': False})
        if identifier == 'A18-02':
            native = 'proven' if evidence['factory-handoff-native']['executed'] else 'missing'
            local_status = 'proven' if evidence['postqa-bound-A18-02-local']['executed'] else 'missing'
            groups['acceptance'][-1]['component_coverage'] = {
                'client_termination_before_ACK': {'native': native, 'fixture_process': local_status},
                'waiter_or_tool_cancellation': {'native': 'missing', 'fixture_process': local_status,
                    'observed_native_cancel_notifications': evidence['factory-handoff-native']['observed_cancel_notifications']},
                'same_CID_new_generation_original_recovery': {'native': native, 'fixture_process': local_status},
                'actual_ACK_reply_then_no_redelivery': {'native': native, 'fixture_process': local_status},
                'scope': 'native 종료/회수/ACK 셀은 관측했으나 native 취소 notification 실측은 없음. native cancel0은 미관측 구성요소로 보존. fixture/process 취소와 실제 native 종료/회복 수준조합의 criterion credit과 분리하며 전사례 native 반복을 가산하지 않음'}
    by_id = {entry['id']: entry for entry in groups['acceptance']}
    for item in residuals:
        related = [a['id'] for a in acceptance if item['finding'] in a['findings']]
        if item['finding'] == 'R38':
            related = sorted(by_id)
        groups['residuals'].append(aggregate(item['finding'], item, related, by_id, evidence, env,
                                            gap=item['remaining'], owner=item['owner_role']))
    for item in journeys:
        related = JOURNEY_ACCEPTANCE[item['id']]
        entry = aggregate(item['id'], item, related, by_id, evidence, env,
                          gap='관련 조건의 미완을 유지하며 전체 여정 trace·사용자 개입 수·회복 호출 수를 별도로 확보해야 함.',
                          owner='P13 코디네이터 및 관련 단계 실환경 검증 담당',
                          required_levels=JOURNEY_LEVELS[item['id']], required_environments=JOURNEY_ENVIRONMENTS[item['id']])
        groups['journeys'].append(entry)
    gates = {g['id']: {'declared_status': g['status'], 'passed': g['status'] == 'passed',
                      'scope': g['acceptance_scope'], 'progress_note': plan.get('current_progress', {}).get(g['id']),
                      'entry_gates': g['entry_gates']} for g in plan['execution']['gates']}
    for gate, keys in {'G04': ['b04-regression'],
                       'G06': ['gate-G06', 'b05-local-integration'],
                       'G08': ['gate-G08', 'b05-local-integration'],
                       'G09': ['gate-G09', 'b05-local-integration'],
                       'G10': ['gate-G10', 'clean-install-final', 'postqa-regression']}.items():
        gates[gate]['local_evidence'] = {'refs': keys, 'recorded_pass': all(evidence[k]['executed'] for k in keys),
                                       'scope': '기록된 로컬 gate만; 원 plan 선언 상태 및 전체 완료는 변경하지 않음'}
    decisions = {'D12': {'status': 'missing', 'source': BASE + 'plan.json#/decision_resolutions',
                         'reason': '현재 plan에 D12 선택 resolution 없음; 원격 비교 문서도 미선택을 명시'}}
    if 'D12' in plan.get('decision_resolutions', {}):
        decisions['D12'] = {'status': 'partial', 'source': BASE + 'plan.json#/decision_resolutions/D12',
                            'reason': '새 resolution은 증거/범위 재결속 필요; 존재만으로 backend 통합 성공 아님'}
    ledger = {'schema_version': 1, 'purpose': 'P13 완료 증거 색인/검사; 승인·생략·완료 선언 권한 없음',
              'plan_path': PLAN, 'spec_path': SPEC,
              'inventory_sha256': digest({'acceptance': acceptance, 'residuals': residuals, 'journeys': journeys}),
              'evidence_catalog': evidence, 'environments': env, 'gates': gates, 'decisions': decisions,
              **groups, 'counts': {key: len(value) for key, value in groups.items()},
              'status_counts': {key: sum(entry['status'] == key for values in groups.values() for entry in values) for key in sorted(STATES)},
              'evidence_kind_counts': {level: {status: sum(entry['evidence'].get(level, {}).get('status') == status
                                           for values in groups.values() for entry in values) for status in sorted(STATES)}
                                      for level in sorted(set(LEVELS.values()))},
              'product_complete': (all(entry['status'] == 'proven' for values in groups.values() for entry in values)
                                   and all(value['passed'] for value in gates.values())
                                   and all(value['status'] == 'proven' for value in env.values())
                                   and all(value['status'] == 'proven' for value in decisions.values())),
              'rules': ['로컬 gate passed는 전체 조건 proven이 아님', 'fixture/process/native/UI/physical/review를 서로 대체하지 않음',
                        '없는 증거·환경은 missing이며 생략 승인을 만들지 않음', '기록 당시 source 범위를 현재 최종 통합 revision으로 확대하지 않음',
                        'prepared-not-displayed·human_saw null·LLM 미실행은 성공 증거가 아님']}
    integration = load_json(local(root, 'deliverables/p13-live/native-integration-source-manifest.json'))
    historical_path = local(Path(integration['snapshot']), OLD_BASE + 'completion-ledger.json')
    historical = load_json(historical_path)
    ledger['historical_completion_snapshot'] = {
        'path': str(historical_path), 'sha256': file_sha(historical_path),
        'manifest_hash_matches': file_sha(historical_path) == integration['files'].get(OLD_BASE + 'completion-ledger.json'),
        'source_scope': '1667/133 primary 시대의 완료 색인을 새315 고정본에 원문 보존. 새135 primary 성공으로 전이하지 않음',
        'counts': historical['counts'], 'status_counts': historical['status_counts'],
        'proven_acceptance': [r['id'] for r in historical['acceptance'] if r['status'] == 'proven']}
    epoch = source_epoch(root)
    receipt = epoch['manifest']
    ledger['current_integration'] = {
        'manifest': epoch['manifest_path'] if epoch['ready'] else None,
        'source_epoch': epoch_summary(epoch),
        'historical1697_manifest': HISTORICAL_MANIFEST,
        'snapshot': receipt['snapshot'] if epoch['ready'] else None, 'files': len(receipt['files']),
        'primary': len(receipt['stable_product_paths']),
        'current_source_binding': current_source_binding(root, receipt),
        'full_regression': ('완료: ' + epoch['regression_path']) if epoch['ready'] else 'partial: doctor privacy epoch/full 검증 대기; old1697은 역사 실행만 유효',
        'full_regression_ref': epoch['regression_ref'] if epoch['ready'] else None,
        'current_proof_promotion_allowed': epoch['ready'],
        'one_parent_two_child_native_followup': '역사315 positive의 source 의존성만 재결속; 새epoch native 실행이나 shared-MCP 성공 아님',
        'different_parents_native_followup': '역사 receipt315 native의 실제 관계/fallback8/ACK8/math3/files2를 scoped 재결속; 새doctor native 실행 아님, drift 유지',
        'previous_1695_scope': 'pre-M1 snapshot only; never a receipt-filter full regression',
        'previous315_positive_scope': 'observed MCP receive/ACK8, final replies3, incoming file reads4; version retained, receipt-filter negative cases separate',
        'previous315_receipt_review': positive_receipt_review('/private/tmp/subagent-followup-p41ahv_v'),
        'scope': '역사1697과 선택 epoch 실제 full을 분리하고 native는 의존 source 범위만 재결속. 이전1695/1667·원실패·독립Opus수정필요 및 전체 미완 한계 유지'}
    return ledger


def aggregate(identifier, requirement, related, by_id, evidence, env, *, gap, owner,
              required_levels=None, required_environments=None):
    selected = [by_id[key] for key in related]
    levels = sorted({level for entry in selected for level in entry['required_levels']})
    refs = sorted({ref for entry in selected for ref in entry['context_refs']})
    environment_ids = sorted({name for entry in selected for name in entry['required_environments']})
    if identifier == 'R42':
        levels = sorted(set(levels) | {'physical'})
        environment_ids = sorted(set(environment_ids) | {'different-NAT', 'UDP-blocked', 'self-hosted-relay'})
    if identifier in ('R17', 'R18'):
        levels = sorted(set(levels) | {'UI'})
        refs = sorted(set(refs) | {'ui-intent-1', 'ui-intent-2', 'p07-os'})
        environment_ids = sorted(set(environment_ids) | {'human-UI', 'UI-late-cancel-focus-race'})
    if required_levels is not None:
        levels = sorted(required_levels)
    if required_environments is not None:
        environment_ids = sorted(required_environments)
    cells = cells_for(levels, refs, evidence, identifier, related)
    return {'id': identifier, 'requirement': copy.deepcopy(requirement), 'related_acceptance': related,
            'required_levels': levels, 'evidence': cells, 'context_refs': refs,
            'required_environments': environment_ids, 'status': classify(cells, environment_ids, env),
            'gap': gap, 'owner': owner, 'revisit': '관련 조건 및 이 항목 전체의 실제 trace/환경 확보 후 재평가',
            'skip_authorized': False}


def audit(root, plan, spec, ledger, *, structure_only=False):
    errors = []
    try:
        expected = build(root, plan, spec)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ['canonical-input-invalid: ' + str(exc)], []
    for key in ('schema_version', 'plan_path', 'spec_path', 'inventory_sha256', 'counts', 'rules'):
        if ledger.get(key) != expected[key]:
            errors.append('index-integrity: ' + key)
    for key in ('acceptance', 'residuals', 'journeys'):
        actual = ledger.get(key)
        wanted = expected[key]
        if not isinstance(actual, list) or len(actual) != len(wanted) or {r.get('id') for r in actual if isinstance(r, dict)} != {r['id'] for r in wanted}:
            errors.append('inventory-loss: ' + key)
            continue
        indexed = {r['id']: r for r in actual}
        for correct in wanted:
            row = indexed[correct['id']]
            if row != correct:
                errors.append('unsubstantiated-or-stale-claim: ' + correct['id'])
            if row.get('status') not in STATES or row.get('skip_authorized') is not False:
                errors.append('invalid-status-or-new-skip: ' + correct['id'])
    for key in ('evidence_catalog', 'environments', 'gates', 'decisions', 'status_counts', 'evidence_kind_counts', 'product_complete',
                'historical_completion_snapshot', 'current_integration'):
        if ledger.get(key) != expected[key]:
            errors.append('evidence-or-gate-integrity: ' + key)
    for key, fact_value in (ledger.get('evidence_catalog') or {}).items():
        try:
            exists = local(root, fact_value['path']).is_file()
            if fact_value.get('available') and not exists:
                errors.append('missing-artifact: ' + key)
            if fact_value.get('executed') and fact_value.get('result') != 'recorded-pass':
                errors.append('unexecuted-evidence-promoted: ' + key)
        except (KeyError, TypeError, ValueError):
            errors.append('invalid-evidence-reference: ' + key)
    blockers = []
    for key in ('acceptance', 'residuals', 'journeys'):
        for row in expected[key]:
            if row['status'] != 'proven':
                blockers.append(row['id'] + ':' + row['status'])
    blockers += [key + ':' + value['declared_status'] for key, value in expected['gates'].items() if not value['passed']]
    blockers += [key + ':' + value['status'] for key, value in expected['environments'].items() if value['status'] != 'proven']
    blockers += [key + ':' + value['status'] for key, value in expected['decisions'].items() if value['status'] != 'proven']
    return errors, [] if structure_only else blockers


def markdown(ledger):
    lines = ['# P13 완료 증거 색인', '',
             '이 문서는 현재 요구와 증거의 연결표다. 제품 완료 선언·생략 승인·새 검토 판정이 아니다.', '',
             '- 원문 보존: 수용 조건 70개, 잔여 항목 20개, 사용자 여정 9개.',
             '- local gate/전체 회귀와 조건 종결을 분리한다. 지정 5개 및 추가 A18-08은 구체 반례·1667/current hash·실제 native 범위로 종결한다. A18-02는 fixture/process만 proven이며 native 취소 미관측으로 전체 partial이다.',
             '- `proven`: 필요한 범위와 종류의 실행 증거가 모두 충족됨. 현재 기록의 부분 표본을 확대하지 않는다.',
             '- `partial`: 관련 실행/로컬 검증이 있으나 조건·revision·환경 전체는 남음.',
             '- `missing`: 필요한 실행 증거가 없음. `contradicted`: 해당 범위의 유효 반대 증거가 있음.', '',
             '검사 명령:', '', '```sh',
             'python3 scripts/audit-collaboration-plan.py --structure-only  # 색인 무결성: exit 0, 제품 완료 아님',
             'python3 scripts/audit-collaboration-plan.py                   # 미완/필수 gate 미충족: exit 1이 정상',
             'python3 scripts/audit-collaboration-plan.py --self-test       # in-memory 변이 검출',
             'python3 scripts/audit-collaboration-plan.py --refresh --structure-only', '```', '',
             '현재 행 분류(70+20+9): ' + ', '.join('%s %d' % pair for pair in ledger['status_counts'].items()) + '.', '',
             '2026-10-30 재결속: 이전 증명은 doctor-privacy v2(1697) 소스에 묶여 있었고 ADR21 통합으로 제품 모듈 15개가 바뀌었다. '
             '현재 HEAD 동결본의 두 Python 전체 회귀(`deliverables/ledger-rebind-20261030/`)로 구체 반례가 있는 fixture/process 셀만 다시 묶었다. '
             '이전 소스의 native/UI/physical 실행은 현재 소스의 증명으로 옮기지 않는다. ADR21 실측(E3/E4/E6/E10/E13/E15)은 범위 한정 partial로 등록했다. 전체계획은 여전히 미완이다.', '',
             '보존된 이전 색인 분류: ' + ', '.join('%s %d' % pair for pair in ledger['historical_completion_snapshot']['status_counts'].items()) + '.',
             '이전 proven 조건: ' + ', '.join(ledger['historical_completion_snapshot']['proven_acceptance']) + '. 원 JSON/hash는 새 고정본 안에 보존했다.', '',
             '`partial` 행 안에서도 없는 UI/native/physical 증거 셀은 `missing`으로 유지한다.', '',
             '| 증거 종류 | proven | partial | missing | contradicted |', '|---|---|---|---|---|']
    for kind, counts in ledger['evidence_kind_counts'].items():
        lines.append('| %s | %d | %d | %d | %d |' % (kind, counts['proven'], counts['partial'], counts['missing'], counts['contradicted']))
    lines += ['',
             '## 필수 환경과 결정 공백', '', '| 항목 | 상태 | 필요한 증거 |', '|---|---|---|']
    for key, value in ledger['environments'].items():
        lines.append('| %s | %s | %s |' % (key, value['status'], value['reason']))
    lines += ['', '## 최종 로컬 통합과 분리된 관측', '',
              '- 최종 receipt 고정본: 두 Python1697 OK/skip0,135 primary 현재hash 일치. preM1의1695·이전1667/133·1649/132는 각 고정본 역사다.',
              '- local G10: 실제 등록6셀·combined 설치/정상제거·손상 JSON/symlink 명시 실패 보존·91개씩/변이2. clean 프로필 로그인/첫모델왕복은 미실행이다.',
              '- post-claims current native2: math3/handshake1, 요청자 MCP9·inbox0·직접ACK4. 설정/goal 조건과 본문·native pair·원reply_to를 대조했으며 전체 J03/J04나 속도우위 아님.',
              '- P11 baseline native15/cached5와 C own-daemon UDP-deny 추가native1을 분리한다. 양쪽 peer relay 및 상관reply를 관측했으나 UDP 환경 전체는 partial이다.',
              '- G11 독립 Opus 원검토는 baseline15 자료만의 partial 판정이다. 문서7개 지적 후속과 UDP offline 검사로 추가 독립 모델리뷰를 만들어내지 않는다.',
              '- native-handoff 준비실패2건은 tools/call0·claim0이다. 완료 factory 표본의 종료/회수/ACK 셀과 native 취소 미관측을 구분하며 profile drift writer는 unknown이다. owned5경계는 nativeMCP0/reply-stored 한정으로 결속한다. 다른부모2/child각1의8건수신ACK·3최종reply·상대file읽기2는 관측했다. 실제한MCPprocess2thread는 미확보로 credit 없음.', '']
    lines += ['', '## gate 범위', '', '| gate | 원 plan 상태 | 로컬 기록 근거 | 범위 |', '|---|---|---|---|']
    for key, value in ledger['gates'].items():
        refs = ', '.join(value.get('local_evidence', {}).get('refs', [])) or '기존 plan 선언만'
        lines.append('| %s | %s | %s | %s |' % (key, value['declared_status'], refs, value['scope']))
    lines += ['', '## 증거 목록', '', '파일이 있거나 코드가 정의됐다는 사실만으로 실행/능력을 통과시키지 않는다. 아래 범위 제한을 그대로 유지한다.', '']
    for key, value in ledger['evidence_catalog'].items():
        href = '../../../' + value['path']
        link = '[%s](%s)' % (value['path'], href) if value['available'] else '`%s` (파일 없음)' % value['path']
        lines += ['- **%s**: %s, `%s`; %s' % (key, link, value['result'], value['scope'])]
    for section, title, field in (('acceptance', '원문 70개 수용 조건', 'criterion'),
                                   ('residuals', '원문 20개 잔여 항목', 'remaining'),
                                   ('journeys', 'J01–J09 사용자 여정', 'required_result')):
        lines += ['', '## ' + title, '', '| ID | 상태 | 원 요구 | 필요한 증거/현재 상태 | 남은 범위 |', '|---|---|---|---|---|']
        for row in ledger[section]:
            requirement = row['requirement'][field]
            if section == 'journeys':
                requirement = row['requirement']['start_and_work'] + ' — ' + requirement
            kinds = ', '.join('%s:%s' % (key, value['status']) for key, value in row['evidence'].items())
            if row.get('blocked_closure_gates'):
                kinds += '; closure gate 미충족: ' + ', '.join(row['blocked_closure_gates'])
            refs = ' '.join('[%s](../../../%s)' % (key, ledger['evidence_catalog'][key]['path'])
                            if ledger['evidence_catalog'][key]['available'] else '`%s:missing`' % key
                            for key in row['context_refs'])
            if section == 'acceptance':
                refs += ' [원 ADR](../../../%s)' % row['requirement']['source']
                if row['test_sources']:
                    refs += ' [test source](../../../%s)' % row['test_sources'][0]
            lines.append('| %s | %s | %s | %s | %s %s |' % (
                row['id'], row['status'], requirement.replace('|', '\\|'), kinds,
                row['gap'].replace('|', '\\|'), refs))
    lines += ['', '## 재개 소유자와 조건', '',
              '각 항목 JSON의 `owner`, `revisit`, 원문 `closure_gates`/`required_gates`를 따른다. 환경·실행 근거·D12가 없는 항목은 missing으로 남고 새 생략 승인을 만들지 않는다.', '',
              'JSON에는 원 plan record 전체, 필요한 증거 종류, source/test 경로의 존재 여부, artifact hash와 실행 범위가 보존된다. 테스트 파일 링크는 실행 성공 증거가 아니다.', '',
              'B04 frozen JSON의 `first_run` 실패와 G04 문서의 두 번째 1517 OK는 서로 다른 실행이다. P07 intent는 실제 UI가 아니고, OS 호출 성공은 사람이 보았다는 뜻이 아니다. P10 94개 CLI 셀은 native LLM 첫 왕복이 아니다. B05 1648 OK는 해당 고정본만의 근거다. P10 native-upgrade는 CLI matrix와 별도 표본이다. P11 A/B/D native 및 C 두 머신 direct 성공은 carrier 근거다. C 환경 proven은 제품 peer discovery→approval→handshake·다른 NAT·UDP 차단·proxy·relay·SSH 불가·D12/UI 성공으로 확대하지 않는다. P12-prep는 준비 계약이다. 최종 로컬 1649/두 Python·132 source hash와 완료 자연사용 감사는 별도 catalog에 결속했다. 자연사용 old 조건도 새 공통 안내를 사용했으며 untouched old-product baseline은 아니다.', '']
    return '\n'.join(lines)


def self_test(root, plan, spec, ledger):
    errors, _ = audit(root, plan, spec, ledger, structure_only=True)
    if errors:
        raise ValueError('baseline index invalid: ' + '; '.join(errors))
    cases = []
    mutant = copy.deepcopy(ledger)
    for section in ('acceptance', 'residuals', 'journeys'):
        for row in mutant[section]:
            row['status'] = 'proven'
            for cell in row['evidence'].values():
                cell['status'] = 'proven'
    mutant['product_complete'] = True
    cases.append(('fake-all-proven', plan, mutant))
    combined = copy.deepcopy(mutant)
    combined['evidence_catalog']['p10-cli']['path'] = 'deliverables/p10-live/nonexistent-proof.json'
    combined['evidence_catalog']['p10-cli']['available'] = True
    cases.append(('fake-all-proven-with-missing-artifact', plan, combined))
    mutant = copy.deepcopy(ledger)
    mutant['evidence_catalog']['p10-cli']['path'] = 'deliverables/p10-live/nonexistent-proof.json'
    mutant['evidence_catalog']['p10-cli']['available'] = True
    cases.append(('nonexistent-artifact', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['acceptance'].pop()
    cases.append(('deleted-acceptance', plan, mutant))
    for section in ('residuals', 'journeys'):
        mutant = copy.deepcopy(ledger)
        mutant[section].pop()
        cases.append(('deleted-' + section, plan, mutant))
    changed_plan, mutant = copy.deepcopy(plan), copy.deepcopy(ledger)
    changed_plan['acceptance'].pop()
    mutant['acceptance'].pop()
    cases.append(('deleted-from-plan-and-ledger', changed_plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['environments']['different-NAT']['status'] = 'proven'
    mutant['environments']['different-NAT']['context_refs'] = ['remote-comparison']
    cases.append(('unexecuted-environment-as-success', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['environments']['physical-native-peer']['status'] = 'proven'
    cases.append(('carrier-as-product-discovery-approval-handshake', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['environments']['UDP-blocked']['status'] = 'proven'
    cases.append(('own-daemon-UDP-sample-as-entire-environment', plan, mutant))
    for environment in ('SSH-unavailable', 'HTTPS-proxy'):
        mutant = copy.deepcopy(ledger)
        mutant['environments'][environment]['status'] = 'proven'
        cases.append(('C-process-variant-as-full-' + environment, plan, mutant))
    mutant = copy.deepcopy(ledger)
    for key in ('native-handoff-first-preparation', 'native-handoff-workspace-preparation', 'native-handoff-factory-pending'):
        mutant['evidence_catalog'][key].update(executed=True, result='recorded-pass')
    cases.append(('pre-tools-failures-and-pending-plan-as-native-success', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['evidence_catalog']['factory-handoff-native']['observed_cancel_notifications'] = 1
    cases.append(('factory-kill-as-native-tool-cancel-success', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['evidence_catalog']['owned-crash-native']['assurance_limits']['caller_identity'] = 'certain'
    cases.append(('owned-private-endpoint-as-current-caller-certainty', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['current_integration']['full_regression'] = 'passed'
    mutant['current_integration']['one_parent_two_child_native_followup'] = 'passed'
    cases.append(('pending-integration-as-completed', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['decisions']['D12']['status'] = 'proven'
    cases.append(('comparison-as-backend-selection', plan, mutant))
    mutant = copy.deepcopy(ledger)
    mutant['evidence_catalog']['ui-intent-1'].update(executed=True, result='recorded-pass')
    next(row for row in mutant['acceptance'] if row['id'] == 'A20-01')['evidence']['UI']['status'] = 'proven'
    cases.append(('prepared-UI-as-executed', plan, mutant))
    mutant = copy.deepcopy(ledger)
    for value in mutant['gates'].values():
        value.update(passed=True, declared_status='passed')
    cases.append(('local-gates-promote-whole-plan', plan, mutant))
    for name, selected_plan, changed in cases:
        rejected, _ = audit(root, selected_plan, spec, changed, structure_only=True)
        if not rejected:
            raise AssertionError('mutation survived: ' + name)
        print('변이 검출: ' + name)
    # Negative predicates exercise the catalog builder, not only edited ledgers.
    native = load_json(root / 'deliverables/p11-live/C-native-roundtrip-20261029.json')
    for name, change in (
        ('C-same-host-is-not-two-machines', lambda d: d['physical_machines'].update(
            peer_hostname=d['physical_machines']['local_hostname'])),
        ('C-missing-native-phase', lambda d: d['runs'][0]['phases'].pop(0)),
        ('C-cached-model-rerun', lambda d: d.update(cached_model_reruns=1)),
        ('C-not-direct', lambda d: [m.update(link='relay') for run in d['runs'] for p in run['phases']
                                  if p.get('native', {}).get('actual_native_call') is True
                                  for side in ('local', 'peer') for m in p['readback'][side]['machines']])):
        changed = copy.deepcopy(native)
        change(changed)
        if all(c_native_checks(changed).values()):
            raise AssertionError('catalog mutation survived: ' + name)
        print('변이 검출: ' + name)
    for key in ('p11-c-native', 'p11-c-evidence-check', 'p11-c-manifest'):
        changed = copy.deepcopy(ledger['evidence_catalog'])
        changed[key].update(executed=False, available=False)
        if environments(changed, plan)['remote-C-two-machines']['status'] != 'missing':
            raise AssertionError('missing C evidence promoted: ' + key)
        print('변이 검출: C-required-evidence-missing:' + key)
    # Evidence-layer counterexamples: never touch product files or rerun models.
    regression = load_json(local(root, 'deliverables/p13-live/local-regression.json'))
    for name, change in (
        ('P13-skipped-tests', lambda d: d['results'][0].update(skips=1)),
        ('P13-post-run-source-change', lambda d: d.update(product_source_unchanged_after_runs=False)),
        ('P13-log-hash-mismatch', lambda d: d['results'][0].update(log_sha256='0' * 64))):
        changed = copy.deepcopy(regression)
        change(changed)
        if all(local_regression_checks(root, changed).values()):
            raise AssertionError('regression mutation survived: ' + name)
        print('변이 검출: ' + name)
    before = load_json(local(root, 'deliverables/b05-live/final-source-manifest.json'))
    before['files']['xsm/envelope.py'] = '0' * 64
    binding = criterion_binding(root, 'A18-03', regression, ledger['evidence_catalog'], before=before)
    if all(binding['checks'].values()):
        raise AssertionError('unbound counterexample source accepted')
    print('변이 검출: P13-counterexample-source-hash-mismatch')
    natural = load_json(local(root, 'deliverables/p13-live/natural-collaboration-audit.json'))
    for name, change in (
        ('P13-natural-raw-rewritten', lambda d: d.update(original_result_sha256='0' * 64)),
        ('P13-natural-model-rerun', lambda d: d.update(native_reruns=1)),
        ('P13-natural-content-relay', lambda d: d['conditions'][0]['controller_interventions'].update(message=1))):
        changed = copy.deepcopy(natural)
        change(changed)
        if all(natural_checks(root, changed).values()):
            raise AssertionError('native audit mutation survived: ' + name)
        print('변이 검출: ' + name)
    native_criterion_mutants = 0
    for filename, predicate, mutate, label in (
        ('first-reply-mcp-evidence.json', first_reply_checks,
         lambda d: d['proofs'][0].update(shell_delivery_attempts=1), 'first-reply-shell-refusal'),
        ('async-independent-native-audit.json', async_work_checks,
         lambda d: d['checks'].update(work_completed_before_actual_reply=False), 'async-work-after-answer'),
        ('version-review-native-20261029-a19.audit.json', version_review_checks,
         lambda d: d.update(v1_bytes_digest_marker_unchanged=False), 'old-copy-overwritten'),
        ('owned-default-closure-audit.json', owned_memory_checks,
         lambda d: d['trials'][-1].update(second_input_omits_token=False), 'owned-followup-repeats-token'),
        ('recovery-passive-closure-results.json', lambda root, d: passive_recovery_checks(root, d, 'A16-05'),
         lambda d: d['A16-05']['evidence'][0].update(inbox_in_initial_list=False), 'cached-list-hides-inbox'),
        ('recovery-passive-closure-results.json', lambda root, d: passive_recovery_checks(root, d, 'A18-06'),
         lambda d: d['A18-06']['checks'].update(no_queue_evidence=False), 'queued-FYI-as-no-wake'),
        ('independent-review-native-20261029-final/check.json', owned_isolation_checks,
         lambda d: d['checks'].update(independent_actual_unknown=False), 'independent-review-leaks-normal-memory')):
        changed = load_json(local(root, 'deliverables/p13-live/' + filename))
        mutate(changed)
        if all(predicate(root, changed).values()):
            raise AssertionError('native criterion mutation survived: ' + label)
        native_criterion_mutants += 1
        print('변이 검출: ' + label)
    pending = next(r for r in plan['acceptance'] if r['id'] == 'A19-05')
    gates = {g['id']: g['status'] for g in plan['execution']['gates']}
    hypothetical_full_cells = {'fixture': {'status': 'proven'}, 'process': {'status': 'proven'}}
    blocked = closure_gate_blockers(pending, gates)
    if 'G07' not in blocked or acceptance_status(hypothetical_full_cells, [], {}, blocked) != 'partial':
        raise AssertionError('full local evidence bypassed unpassed G07')
    if closure_gate_blockers({'closure_gates': ['G13']}, {'G13': 'partial'}):
        raise AssertionError('G13 recursively blocks per-criterion closure')
    print('변이 검출: full-local-evidence-cannot-bypass-G07')
    print('검사 통과: final-G13-is-not-a-recursive-row-gate')
    manifest = load_json(local(root, regression['snapshot_manifest']))
    manifest['files']['xsm/install.py'] = '0' * 64
    if current_source_binding(root, manifest)['status'] != 'changed-rebinding-required':
        raise AssertionError('installer current-source change was hidden')
    if not all(local_regression_checks(root, regression).values()):
        raise AssertionError('current-source observation erased frozen regression history')
    print('변이 검출: current-installer-change-requires-scoped-rebinding')
    install_binding = criterion_binding(root, 'A23-02', regression, ledger['evidence_catalog'])
    if install_binding['checks']['native_install_counterexample_not_open'] is not False:
        raise AssertionError('known native install failure was preemptively cleared')
    print('변이 검출: no-mcp-matrix-cannot-close-known-native-install-failure')
    if acceptance_status({'native': {'status': 'proven'}}, [], {}, ['G10']) != 'partial':
        raise AssertionError('native proof bypassed unpassed installer gate')
    print('변이 검출: native-cell-proven-cannot-bypass-verifying-G10')
    checker = load_json(local(root, 'deliverables/p11-live/C-evidence-check-20261029.json'))
    checker['manifest_sha256'] = '0' * 64
    if all(c_checker_checks(root, checker).values()):
        raise AssertionError('stale C checker manifest binding accepted')
    print('변이 검출: amended-C-manifest-with-stale-checker-SHA')
    followup = load_json(local(root, 'deliverables/p11-live/review-closure.json'))
    for name, change in (
        ('G11-followup-as-second-independent-review', lambda d: d.update(second_model_review=True)),
        ('G11-followup-as-passed-gate', lambda d: d.update(gate_status='passed')),
        ('G11-document-amendment-hash-mismatch', lambda d: d['amended_files_sha256'].update(
            {'deliverables/p11-live/C-native-roundtrip-20261029.md': '0' * 64}))):
        changed = copy.deepcopy(followup)
        change(changed)
        if all(g11_review_closure_checks(root, changed).values()):
            raise AssertionError('review followup mutation survived: ' + name)
        print('변이 검출: ' + name)
    new_count = 0
    post = load_json(local(root, 'deliverables/p13-live/post-qa-regression.json'))
    for name, change in (
        ('1667-skipped-tests', lambda d: d['results'][0].update(skips=1)),
        ('1667-unbound-log', lambda d: d['results'][0].update(log_sha256='0' * 64)),
        ('1667-postrun-source-changed', lambda d: d.update(product_source_unchanged_after_runs=False))):
        changed = copy.deepcopy(post); change(changed)
        if all(postqa_regression_checks(root, changed).values()):
            raise AssertionError('postqa regression mutation survived: ' + name)
        new_count += 1; print('변이 검출: ' + name)
    manifest = load_json(local(root, 'deliverables/p13-live/post-qa-source-manifest.json'))
    manifest['files']['xsm/install.py'] = '0' * 64
    if all(postqa_criterion_binding(root, 'A23-02', ledger['evidence_catalog'], manifest=manifest)['checks'].values()):
        raise AssertionError('postqa source mismatch retained A23-02 credit')
    new_count += 1; print('변이 검출: 1667-installer-source-binding-mismatch')
    post_native = load_json(local(root, 'deliverables/p13-live/post-claims-collaboration.audit.json'))
    for name, change in (
        ('postclaims-missing-ACK', lambda d: d.update(initiator_direct_answer_ACKs=0)),
        ('postclaims-controller-relay', lambda d: d.update(controller_message_calls=1)),
        ('postclaims-body-not-actually-read', lambda d: d['reviews'][0].update(received_actual_body=False))):
        changed = copy.deepcopy(post_native); change(changed)
        if all(postclaims_checks(root, changed).values()):
            raise AssertionError('postclaims mutation survived: ' + name)
        new_count += 1; print('변이 검출: ' + name)
    clean = load_json(local(root, 'deliverables/p13-live/clean-install.final.json'))
    clean['source']['xsm/install.py'] = '0' * 64
    if all(clean_final_checks(root, clean).values()):
        raise AssertionError('unbound clean installer accepted')
    new_count += 1; print('변이 검출: clean-final-source-mismatch')
    udp = load_json(local(root, 'deliverables/p11-live/udp-blocked-results-20261029.json'))
    for name, change in (
        ('UDP-relay-connected-only', lambda d: [m.update(link=None) for s in ('local', 'peer') for m in d['readback'][s]['machines']]),
        ('UDP-own-daemon-as-global-firewall', lambda d: d.update(production_team_or_global_network_policy_changed=True))):
        changed = copy.deepcopy(udp); change(changed)
        if all(udp_checks(changed).values()):
            raise AssertionError('UDP scope mutation survived: ' + name)
        new_count += 1; print('변이 검출: ' + name)
    factory = load_json(local(root, 'deliverables/p13-live/native-handoff-factory-20261029-7091030d/summary.json'))
    for name, change in (
        ('factory-no-owner-dead-recovery', lambda d: d.update(owner_dead_recovery=False)),
        ('factory-response-not-withheld', lambda d: d.update(withheld_actual_claim_response_bytes_forwarded=1)),
        ('factory-drift-erased-as-immutable', lambda d: d.update(profile_configuration_unchanged=True))):
        changed = copy.deepcopy(factory); change(changed)
        if all(factory_handoff_checks(root, changed).values()):
            raise AssertionError('factory mutation survived: ' + name)
        new_count += 1; print('변이 검출: ' + name)
    owned = load_json(local(root, 'deliverables/p13-live/owned-crash-results.json'))
    for name, change in (
        ('owned-missing-boundary', lambda d: d['cases'].pop()),
        ('owned-effect-reran', lambda d: d['cases'][2].update(effect_final='2')),
        ('owned-mocked-executor', lambda d: d.update(executor_mocked=True)),
        ('owned-two-canonical-replies', lambda d: d['cases'][-1].update(canonical_reply_originals=2))):
        changed = copy.deepcopy(owned); change(changed)
        if all(owned_crash_checks(root, changed).values()):
            raise AssertionError('owned mutation survived: ' + name)
        new_count += 1; print('변이 검출: ' + name)
    worktree = load_json(local(root, 'deliverables/p13-live/worktree-native-20261029-a15.audit.json'))
    for name, change in (
        ('worktree-body-not-read', lambda d: d['pairs'][0].update(actual_body_matches_response=False)),
        ('worktree-formal-handshake-invented', lambda d: d.update(formal_handshakes=1)),
        ('worktree-extra-scope-ignored', lambda d: d.update(permission_API_calls=['xsm_link'])),
        ('worktree-profile-guard-drift-erased', lambda d: d.update(profile_guard_unchanged=True))):
        changed = copy.deepcopy(worktree); change(changed)
        if all(worktree_checks(root, changed).values()):
            raise AssertionError('worktree evidence mutation survived: ' + name)
        new_count += 1; print('변이 검출: ' + name)
    final = load_json(local(root, 'deliverables/p13-live/final-regression.json'))
    final['results'][0]['tests'] = 1695
    if all(final_regression_checks(root, final).values()):
        raise AssertionError('pre-M1 count substituted for1697')
    new_count += 1; print('변이 검출: pre-M1-1695-as-final1697')
    parent = load_json(local(root, 'deliverables/p13-live/different-parent-native-20261029-5564a814/summary.json'))
    parent['parent_relations'][1]['actual_parent_thread_id_hash'] = parent['parent_relations'][0]['actual_parent_thread_id_hash']
    if all(different_parent_checks(parent).values()):
        raise AssertionError('same provider parent accepted as different parents')
    new_count += 1; print('변이 검출: same-provider-parent-as-different-parent')
    arrival = load_json(local(root, 'deliverables/p10-live/controller-native-arrival.json'))
    arrival['additional_arrivals'][0]['body'] += 'changed'
    if all(arrival_checks(root, arrival).values()):
        raise AssertionError('R2 arrival body mismatch accepted')
    new_count += 1; print('변이 검출: R2-arrival-not-exact-archive-body')
    _, blockers = audit(root, plan, spec, ledger)
    if not blockers:
        raise AssertionError('incomplete product unexpectedly passed')
    return len(cases) + 22 + new_count + native_criterion_mutants


def predicate_self_test(root):
    """새 predicate/epoch만 검사한다. 합성 full fixture는 제품 실행 증거가 아니다."""
    import tempfile
    import shutil
    from unittest import mock
    count = 0
    suites = [
        ('strict-review-native-audit.json', strict_review_checks, (
            ('strict-같은ID-교체', lambda d: d['same_ID_resend'].update(id='wrong')),
            ('strict-수정라운드-소실', lambda d: d['rounds'].pop(1)),
            ('strict-반복본문-교체', lambda d: d['rounds'][3].update(request_body='different')),
            ('strict-drift-은폐', lambda d: d.update(profile_guard_unchanged=True)))),
        ('doctor-privacy-native-20261029-828fa71c/summary.json', doctor_privacy_native_checks, (
            ('doctor-실제marker누출', lambda d: d.update(leaked_marker_count=1)),
            ('doctor-진단후세션종료', lambda d: d['runtime_survival'].update(same_PID_generation_before_after=False)),
            ('doctor-원장변경', lambda d: d['ledger'].update(bytes_before_after_identical=False)))),
        ('directory-extraction-closure-audit.json', directory_extraction_checks, (
            ('directory-selector-SHA', lambda d: d['source_binding']['selectors'][0].update(file_sha256='0'*64)),
            ('directory-native-RPC-error', lambda d: d['native_wire_checks'][0].update(isError=True)),
            ('directory-RPC-ID교체', lambda d: d['native_wire_checks'][0].update(rpc_id='없는RPC')),
            ('directory-사람표본을-publication으로승격', lambda d: d['human_review'].update(publication_permission=True)))),
        ('independent-review-native-20261029-final/capacity-rebinding-audit.json', capacity_rebinding_checks, (
            ('capacity-whole-journal-SHA-위장', lambda d: d['original_journal_binding'].update(whole_journal_hash_matches_original=True)),
            ('capacity-22필드-digest-불일치', lambda d: d['stage_A_request_rows'][0].update(current_request_canonical_sha256='0'*64)),
            ('capacity-기존request-소실', lambda d: d['stage_A_request_rows'].pop()),
            ('capacity-78raw를79일치로위장', lambda d: d['integrity_recheck']['capacity'].update(matching=79))))]
    for path, predicate, mutations in suites:
        original = load_json(local(root, 'deliverables/p13-live/'+path))
        assert all(predicate(root, original).values()), '원 predicate 실패: '+path
        for label, mutate in mutations:
            changed = copy.deepcopy(original)
            mutate(changed)
            try:
                accepted = all(predicate(root, changed).values())
            except (ValueError, KeyError, IndexError, TypeError):
                accepted = False
            assert not accepted, '변이 생존: '+label
            count += 1
            print('변이 검출: '+label)
    opus = load_json(local(root, 'deliverables/p13-live/g10-doctor-privacy-opus-review.json'))
    assert all(doctor_opus_checks(root,opus).values())
    for label, mutate in (
        ('Opus-다른요청모델', lambda d:d.update(requested_model='other-model')),
        ('Opus-다른init모델', lambda d:d.update(actual_init_model='other-model')),
        ('Opus-다른usage모델', lambda d:d.update(actual_modelUsage_IDs=['other-model'])),
        ('Opus-세metadata모두다른모델', lambda d:d.update(requested_model='other-model',actual_init_model='other-model',actual_modelUsage_IDs=['other-model'])),
        ('Opus-raw-SHA교체',lambda d:d.update(raw_result_sha256='0'*64))):
        changed=copy.deepcopy(opus);mutate(changed)
        assert not all(doctor_opus_checks(root,changed).values()),label
        count+=1;print('변이 검출: '+label)
    raw=load_json(Path(opus['raw_private_root'])/'review-raw.json')
    for label, kind in (('Opus-원raw-init교체','init'),('Opus-원raw-usage교체','usage')):
        changed=copy.deepcopy(raw)
        if kind=='init':next(r for r in changed if r.get('subtype')=='init')['model']='other-model'
        else:next(r for r in changed if r.get('type')=='result')['modelUsage']={'other-model':{}}
        assert not all(doctor_opus_checks(root,opus,raw=changed).values()),label
        count+=1;print('변이 검출: '+label)
    old = load_json(local(root, HISTORICAL_MANIFEST))
    # doctor manifest가 준비되기 전에도 pending 전환 검사를 실행할 수 있다.
    if local(root, DOCTOR_MANIFEST).is_file():
        test_manifest = DOCTOR_V2_MANIFEST if local(root,DOCTOR_V2_MANIFEST).is_file() else DOCTOR_MANIFEST
        new = load_json(local(root, test_manifest))
        worker_fixture = test_manifest == DOCTOR_V2_MANIFEST
        with tempfile.TemporaryDirectory(prefix='audit-doctor-full-fixture-') as folder:
            if file_sha(local(root,'tests/test_workers.py')) != new['files']['tests/test_workers.py']:
                snapshot = Path(folder)/'snapshot'
                shutil.copytree(Path(new['snapshot']),snapshot)
                shutil.copyfile(local(root,'tests/test_workers.py'),snapshot/'tests/test_workers.py')
                new = copy.deepcopy(new);new['snapshot']=str(snapshot)
                new['files']['tests/test_workers.py']=file_sha(snapshot/'tests/test_workers.py')
                worker_fixture=True;test_manifest=DOCTOR_V2_MANIFEST
            assert all(doctor_delta_checks(root,old,new,worker_fixture=worker_fixture).values())
            rows = []
            for version in ('3.9.6', '3.14.6'):
                log = Path(folder)/(version+'.log')
                log.write_text('Ran 1700 tests in 1.0s\n\nOK\n')
                rows.append({'python':'Python '+version, 'tests':1700, 'result':'OK', 'exit_code':0,
                             'skips':0, 'log':str(log), 'log_sha256':file_sha(log)})
            full = {'snapshot_manifest':test_manifest, 'snapshot':new['snapshot'], 'results':rows,
                    'tested_product_paths':len(new['stable_product_paths']), 'product_source_unchanged_after_runs':True,
                    'changed_paths':[], 'whole_plan_complete':False}
            assert all(doctor_regression_checks(root, full, new,manifest_ref=test_manifest).values()), '합성 audit fixture 불일치'
            for label, mutate in (
                ('doctor-full-미실행', lambda d:d.update(results=[])),
                ('doctor-old1697을새실행으로위장', lambda d:d['results'][0].update(tests=1697)),
                ('doctor-한Python만완료', lambda d:d['results'].pop()),
                ('doctor-skip', lambda d:d['results'][0].update(skips=1)),
                ('doctor-log-SHA불일치', lambda d:d['results'][0].update(log_sha256='0'*64)),
                ('doctor-실행뒤-source변경', lambda d:d.update(product_source_unchanged_after_runs=False))):
                changed=copy.deepcopy(full); mutate(changed)
                assert not all(doctor_regression_checks(root,changed,new,manifest_ref=test_manifest).values()), label
                count+=1;print('변이 검출: '+label)
            bad=copy.deepcopy(new);bad['files']['xsm/envelope.py']='0'*64
            assert not doctor_delta_checks(root,old,bad,worker_fixture=worker_fixture)['only_doctor_files_changed']
            count+=1;print('변이 검출: doctor-무관-product-delta')
            original_members=_ast_members
            new_text=(Path(new['snapshot'])/'xsm/install.py').read_text()
            def corrupt_install(text):
                result=original_members(text)
                if text==new_text:result['install_mcp']+='변경'
                return result
            with mock.patch.dict(globals(),_ast_members=corrupt_install):
                assert not doctor_delta_checks(root,old,new,worker_fixture=worker_fixture)['existing_install_functions_preserved']
            count+=1;print('변이 검출: doctor-기존설치함수-변경')
    real_load=load_json
    def no_full(path):
        if Path(path).resolve() in {local(root,DOCTOR_REGRESSION),local(root,DOCTOR_V2_REGRESSION)}:raise FileNotFoundError('full 미완 fixture')
        return real_load(path)
    with mock.patch.dict(globals(),load_json=no_full):
        pending=source_epoch(root)
        assert not pending['ready'] and pending['historical1697_valid']
    count+=1;print('변이 검출: doctor-running은현재완료가아님')
    assert all(final_regression_checks(root,real_load(local(root,'deliverables/p13-live/final-regression.json'))).values())
    print('검사 통과: old1697 frozen history 보존, 합성 audit fixture는 실제 full 아님')
    if local(root, REBIND + 'summary.json').is_file():
        summary = load_json(local(root, REBIND + 'summary.json'))
        assert all(head_rebind_regression_checks(root, summary).values()), '원 현재HEAD 회귀 predicate 실패'
        for label, mutate in (
            ('rebind-한Python만', lambda d: d['full_regression'].pop()),
            ('rebind-skip', lambda d: d['full_regression'][0].update(skipped=1)),
            ('rebind-실패exit', lambda d: d['full_regression'][1].update(exit_code=1)),
            ('rebind-검사수불일치', lambda d: d['full_regression'][0].update(tests_run=d['full_regression'][0]['tests_run'] - 1)),
            ('rebind-log-SHA교체', lambda d: d['full_regression'][0].update(log_sha256='0'*64)),
            ('rebind-manifest-bytes교체', lambda d: d['freeze'].update(manifest_sha256='0'*64)),
            ('rebind-다른엔진', lambda d: d['freeze'].update(binary_sha256='0'*64)),
            ('rebind-전체계획완료주장', lambda d: d.update(whole_plan_complete=True))):
            changed = copy.deepcopy(summary); mutate(changed)
            try:
                accepted = all(head_rebind_regression_checks(root, changed).values())
            except (ValueError, KeyError, IndexError, TypeError):
                accepted = False
            assert not accepted, '변이 생존: ' + label
            count += 1; print('변이 검출: ' + label)
        # A frozen input that no longer matches the working tree.
        real_sha = file_sha
        def drifted(path):
            return '0'*64 if Path(path) == local(root, 'xsm/send.py') else real_sha(path)
        with mock.patch.dict(globals(), file_sha=drifted):
            assert not head_rebind_regression_checks(root, summary)['current_source_exact']
            assert not head_rebind_criterion_checks(root, 'A18-03', {'head-rebind-regression': {'executed': True},
                **{k: {'executed': True} for k in CLOSURE_PROOFS['A18-03']['origins']}})['cases_and_product_frozen']
        count += 2; print('변이 검출: rebind-실행뒤-source변경, rebind-조건의존파일변경')
        # A counterexample the criterion was closed with is gone from the source.
        proofs = copy.deepcopy(CLOSURE_PROOFS)
        proofs['A18-03']['cases']['tests/test_xsm.py'].append('test_that_does_not_exist')
        with mock.patch.dict(globals(), CLOSURE_PROOFS=proofs):
            assert not head_rebind_criterion_checks(root, 'A18-03', {'head-rebind-regression': {'executed': True},
                **{k: {'executed': True} for k in proofs['A18-03']['origins']}})['specific_cases_present']
        count += 1; print('변이 검출: rebind-구체반례-소실')
    return count


def rebinding_self_test(root):
    """이번 결속 predicate만 검사한다. 새 제품 실행/모델/원 artifact 수정은 없다."""
    from unittest import mock
    cases = [
        ('persistent-parity-native-v3-20261029.audit.json',parity_native_checks,(
            ('parity-본문동등실패',lambda d:d.update(plain_answers_equal=False)),
            ('parity-전체digest동일로위장',lambda d:d.update(canonical_digests_equal_across_requests=True)),
            ('parity-file내용교체',lambda d:d['actual_file_reads'][0].update(actual_content_SHA='0'*64)),
            ('parity-상관reply교체',lambda d:d['pairs']['CLI plain'].update(reply_to='wrong')),
            ('parity-원collector실패은폐',lambda d:d.update(collector_original_status='success')))),
        ('exclusion-cli-native-20261029-6c6ee4c8/summary.json',lambda r,d:exclusion_native_checks(r,d,'A17-05'),(
            ('exclusion-제외후발견노출',lambda d:d['A17_05']['discovery'].update(candidates=[{'id':'leak'}])),
            ('exclusion-원본문open',lambda d:d.update(protected_source_open_events=1)))),
        ('exclusion-cli-native-20261029-6c6ee4c8/summary.json',lambda r,d:exclusion_native_checks(r,d,'A19-03'),(
            ('CLI거절인데본문전송',lambda d:d['A19_03']['real_cli_main_parser'][0].update(body_sent=True)),
            ('CLI거절인데사본생성',lambda d:d['counts_each_state'].update(copy_records=1)))),
        ('delivery-recovery-upgrade-rebinding.json',lambda r,d:delivery_rebinding_checks(r,d,'A18-01'),(
            ('queue실패를runtime도달로위장',lambda d:d['typed_native_fallback']['rows'][0].update(sender_ledger_runtime_reached=True)),)),
        ('delivery-recovery-upgrade-rebinding.json',lambda r,d:delivery_rebinding_checks(r,d,'A18-02'),(
            ('native취소notification허위추가',lambda d:d['native_handoff'].update(observed_native_cancel_notifications=1)),
            ('claim원응답노출',lambda d:d['native_handoff'].update(withheld_actual_response_bytes=1)))),
        ('delivery-recovery-upgrade-rebinding.json',lambda r,d:delivery_rebinding_checks(r,d,'A23-08'),(
            ('live-old-snapshot삭제',lambda d:d['native_upgrade']['upgrade'].update(old_snapshot_exists=False)),)),
        ('policy-compatibility-rebinding.json',lambda r,d:policy_rebinding_checks(r,d,'A16-07'),(
            ('부분reply만있고final소실',lambda d:[p.update(outcome=None) for row in d['conditions']['A16-07']['native_proof'] for p in row['replies']]),)),
        ('policy-compatibility-rebinding.json',lambda r,d:policy_rebinding_checks(r,d,'A22-02'),(
            ('실제권한변경을비승격으로위장',lambda d:d['conditions']['A22-02']['context_native_replay'].update(permission_changed=True)),)),
        ('policy-compatibility-rebinding.json',lambda r,d:policy_rebinding_checks(r,d,'A23-05'),(
            ('G12공식gate면제',lambda d:d['conditions']['A23-05'].update(formal_blocked_gates=[])),)),
        ('topology-rebinding.json',topology_partial_checks,(
            ('crossrepo구별없이전체완료',lambda d:d.update(whole_condition_complete=True)),
            ('distinctGitcommon허위추가',lambda d:d['crossrepo'].update(distinct_historical_Gitcommon_bound=True))))]
    count=0
    for path,predicate,mutants in cases:
        original=load_json(local(root,'deliverables/p13-live/'+path))
        baseline=predicate(root,original)
        assert all(baseline.values()), ('원 predicate 실패',path,baseline)
        for label,change in mutants:
            changed=copy.deepcopy(original);change(changed)
            try:accepted=all(predicate(root,changed).values())
            except (ValueError,KeyError,IndexError,TypeError,StopIteration):accepted=False
            assert not accepted,'변이 생존: '+label
            count+=1;print('변이 검출: '+label)
    manifest=load_json(local(root,'deliverables/p13-live/exclusion-cli-native-20261029-6c6ee4c8/manifest.json'))
    index=load_json(Path(manifest['root'])/'raw-index.private.json')
    protected={Path(index[r['private_file_id']]).resolve() for r in manifest['private_files'] if r['role']=='protected-negative-original'}
    real=file_sha
    def no_protected_hash(path):
        assert Path(path).resolve() not in protected,'보호 원본 사후 hash 접근'
        return real(path)
    with mock.patch.dict(globals(),file_sha=no_protected_hash):
        data=load_json(local(root,'deliverables/p13-live/exclusion-cli-native-20261029-6c6ee4c8/summary.json'))
        assert all(exclusion_native_checks(root,data,'A17-05').values())
        assert all(exclusion_native_checks(root,data,'A19-03').values())
    count+=1;print('접근 반례 차단: 보호 합성 원본 setup SHA만 결속, 사후 hash0')
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--structure-only', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--rebinding-self-test',action='store_true',help='이번 parity/exclusion/recovery/policy/topology 표적 검사만; 제품 실행 없음')
    parser.add_argument('--predicate-self-test', action='store_true', help='새 epoch/proof의 표적 변이만 검사; 제품 실행 없음')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    filename = args.ledger or root / LEDGER
    try:
        plan, spec = load_json(root / PLAN), (root / SPEC).read_text(encoding='utf-8')
        if args.rebinding_self_test:
            count=rebinding_self_test(root)
            print('추가 결속 표적 변이/접근 검사 %d개 통과; 제품 완료 아님' % count)
            return 0
        if args.predicate_self_test:
            count = predicate_self_test(root)
            print('표적 predicate 변이 %d개 검출; 제품 full/완료 아님' % count)
            return 0
        if args.refresh:
            ledger = build(root, plan, spec)
            filename.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            (root / REPORT).write_text(markdown(ledger), encoding='utf-8')
        ledger = load_json(filename)
        if args.self_test:
            count = self_test(root, plan, spec, ledger)
            print('색인 변이 %d개 검출; 제품 완료 판정 아님' % count)
            return 0
        errors, blockers = audit(root, plan, spec, ledger, structure_only=args.structure_only)
        if args.ledger is None:
            report_file = root / REPORT
            if not report_file.is_file() or report_file.read_text(encoding='utf-8') != markdown(ledger):
                errors.append('markdown-index-stale-or-missing')
        print('색인: 수용 %s / 잔여 %s / 여정 %s' % tuple(ledger.get('counts', {}).get(key, '?') for key in ('acceptance', 'residuals', 'journeys')))
        print('분류: ' + json.dumps(ledger.get('status_counts'), ensure_ascii=False))
        for error in errors:
            print('색인 오류: ' + error)
        if args.structure_only:
            print('구조 검사만 수행: 제품 완료를 뜻하지 않음')
        else:
            print('전체 완료 미충족: %d개 조건/gate/환경/결정 blocker' % len(blockers))
            print(', '.join(blockers))
        return 1 if errors or blockers else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('감사 입력 오류: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
