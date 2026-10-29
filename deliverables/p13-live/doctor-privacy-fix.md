# P10 doctor 원문 비출력 수정

로컬 수정과 두 Python의 영향 검사를 완료했다. 제품 변경은 **xsm/install.py의 stuck() 한 곳**, 시험 변경은 기존 **tests/test_install_cli_flow.py**의 회귀 3개다. ledger/원문 정본과 기존 plan/ledger/artifact는 이 작업에서 수정하지 않았다. 기존1697 frozen source를 수정한 것이 아니라, 그 source와 같았던 workspace install.py에 별도 수정 epoch를 만들었다.

## 수정 전 영향 범위

- 데이터 경로 3개: stuck.undelivered, stuck.uncertain, stuck.send_failures.
- 출력 형식 3개: JSON은 전체 stuck report, 일반 text는 _stuck_lines의 오류 label을 출력했다. table은 원래 stuck을 표시하지 않았다.
- 제품 함수: stuck() 1개. CLI 소비 함수 cmd_doctor(JSON), _stuck_lines(text)는 수정하지 않았다. 기존 table 동작도 그대로다.
- 기존 직접 출력/회귀 검사: InstallCliFlowTest 8개, StuckReportTest 2개, DoctorSessionsTest 4개, DoctorRuntimeTest 5개. 기존 setup redaction 검사2개와 새3개를 더해 영향 검사24개를 선택했다.

## 원 실패와 변경

실제 ledger.queued/unknown/failed로 격리 원장5건을 만들었다. queued 시각은 현재보다600초 전이며 unknown/error에도 synthetic 본문·초대·raw 오류와 임의 중첩 필드를 저장했다. endpoint의 허용 필드 ref 안에도 dict 원문을 넣었다. 기존 fixture의 발견/버전 경계만 격리했으며 parser/doctor/install/stuck/ledger 서비스는 대체하지 않았다.

두 Python 모두 수정 전 실제 CLI 경로의 JSON과 일반 text에서 누출 검사가 실패했다. **3개 중2개 실패**이며 table은 원래 비누출 대조군으로 통과했다. table도 red였다고 보고하지 않는다.

수정은 다음 두 가지다.

1. undelivered/uncertain은 id/status/t/from/to를 새 dict로 만든다. endpoint도 name/alias/ref/runtime의 string만 선택한다. preview/body/임의 evidence와 중첩 dict/list를 원장 행째 반환하지 않는다.
2. send_failures는 알려진 고정 label 6개(sandbox-blocked, no-inbox, socket-error, no-codex-binary, codex-failed, codex-internal-changed)와 other로만 집계한다. 임의 raw error prefix/detail을 JSON key나 일반 text label로 쓰지 않는다.

원장의 전체 필드와 본문은 삭제하거나 변경하지 않는다. 각 JSON/text/table 실행 전후 원장 파일을 bytes 단위로 비교해 같음을 확인했다. 진단용 name/alias 등 허용 metadata 문자열 자체를 전역 익명화하는 변경은 아니다. 프로세스 unknown·권한·diagnostic 기능은 건드리지 않았다.

## 실행 결과

| 단계 | Python3.9.6 | Python3.14.6 |
|---|---|---|
| 원 source 누출 red | 3개 중2개 실패 | 3개 중2개 실패 |
| 수정 후 영향 검사 | 24개 / 43.752초 / OK | 24개 / 31.145초 / OK |
| 전체 ledger 행 반환 guard 제거 | 3개 중 JSON1개 실패 | 같음 |
| endpoint 선택 guard 제거 | 3개 중 JSON1개 실패 | 같음 |
| 오류 label 제한 guard 제거 | 3개 중 JSON/text2개 실패 | 같음 |
| 실제 CLI raw 별도 capture | 수정 전2fail / 수정 후3개 모두OK | 같음 |

변이는 모두 private source 사본에서만 수행했다. 실제 workspace의 guard를 제거했다가 되돌리는 방식은 쓰지 않았다. 변이 실행은 assertion failure로 끝났고 import/runtime error로 대신 실패하지 않았다.

영향 검사 명령은 아래 두 interpreter에서 같은 selector로 실행했다.

```text
/usr/bin/python3 -B -m unittest tests.test_install_cli_flow tests.test_xsm.StuckReportTest tests.test_discovery_latency.DoctorSessionsTest tests.test_install_runtime.DoctorRuntimeTest tests.test_setup_flow.SetupFlowTest.test_report_is_read_only_redacted_and_never_wakes_or_terminates_a_session tests.test_setup_flow.SetupFlowTest.test_credentials_invites_and_raw_errors_are_not_evidence_fields -v
/opt/homebrew/bin/python3 -B -m unittest tests.test_install_cli_flow tests.test_xsm.StuckReportTest tests.test_discovery_latency.DoctorSessionsTest tests.test_install_runtime.DoctorRuntimeTest tests.test_setup_flow.SetupFlowTest.test_report_is_read_only_redacted_and_never_wakes_or_terminates_a_session tests.test_setup_flow.SetupFlowTest.test_credentials_invites_and_raw_errors_are_not_evidence_fields -v
```

red·green·변이·capture의 **정확한 argv/cwd·source/test SHA·출력 SHA**는 [JSON](doctor-privacy-fix.json)에 있다. capture는 시험 harness의 결과를 보존만 하며 실제 제품 서비스를 교체하지 않는다. 수정 전후 두 interpreter의 실제 doctor 호출12건에 대해 개별 stdout/stderr 파일·SHA와 명령/격리 환경을 따로 결속했다. 원 실패 raw와 원 install.py는 `/private/tmp/doctor-privacy-fix-rvmeysuu`에 보존했다.

## 검토·보존 경계

[검토용 패치](doctor-privacy-fix.patch)는 이 작업 시작 직전 bytes와의 차이만 담았다. 기존 미커밋 작업을 HEAD diff에 섞어 이번 변경이라고 하지 않는다. 다른 제품 xsm 파일은 시작 시 hash와 같고, 기존 frozen primary135도 불변이다.

workspace의 current-handoff.md/plan.json 변경은 사용자가 확인한 coordinator의 G10 재개 기록이다. 권한 정책·수용 criteria 변경이 아니며 이 작업에서 수정하지 않았다. 기존1697 증거·doctor v3 partial/unknown·기존 verdict는 과거 source epoch의 기록으로 남겼다.

새 모델·커밋·push는0이다. **full 회귀와 새 coordinator freeze는 실행하지 않았다.** 이번 결과는 새 workspace source의 두 Python 영향 검사까지다.

## 사용자 source 동결 확인

사용자 지시 이후 제품·테스트 source 수정과 추가 시험은0이다. 현재 SHA가 위 targeted green/변이 검증에 결속한 SHA와 일치한다. freezer/full regression 및 Opus delta 검토는 coordinator가 진행하며 결과를 선취하지 않는다.

- `xsm/install.py`: `a8e712de6e8b2b9f368946333a6c8793168c6734484be45a60dbe967d0aa1960`
- `tests/test_install_cli_flow.py`: `2726d9a8ddb1b1acb93c9a6d82b7fae5ed811d79e13ba642083c67b08f9444b4`
