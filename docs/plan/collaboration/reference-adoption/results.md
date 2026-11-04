# 레퍼런스 반영 결과

후속 검토 정정: 아래는 초기 73개 검사에서 확인한 범위다. 독립 검토는 즉시 시작의 시도 기록 누락, 미시작 워커가 다른 시도를
닫는 경우, 20건 보존 한도가 중단 반복으로 실패를 지우는 경우를 추가로 발견했다. 초기 검사는 시도를 직접 만든 짧은 이력에
편중되어 이 경계를 놓쳤다. 후속 수정의 [계획](followup.md)과 [보정 결과](followup-results.md)를 함께 본다.

2026-11-04. [실행 계획](spec.md)의 P1~P3를 구현했다. 레퍼런스 34개를 전부 기능으로 옮긴 작업은 아니다.
검증은 임시 상태와 전송·프로세스 경계 대역으로 수행했다. OpenCode·Pi·OpenClaw·Hermes를 포함해 실제 런타임 실행은 0회,
모델 호출과 메신저·게이트웨이 재시험도 0회다. 실제 사용자 프로필을 수정하지 않았다.

## 변경

| 단계 | 결과 | 구현 커밋 |
|---|---|---|
| P1 | 성공을 만났을 때 그 뒤에서 센 실패 수를 반환한다. 성공 뒤 실패가 0회로 사라지던 결함 수정 | `fcaec00` |
| P2 | 일반 stop 명령은 사용자 중단으로 표시해 최종 outcome 없이 시도 기록을 닫는다. 기존 실패를 늘리거나 초기화하지 않는다. 자동·내부 정지 분류와 이미 받은 회신은 유지 | `b8e74ae` |
| P3 | 미응답 질문의 정확한 로컬 대상에 명시적 종료 기록이 있으면 기존 reason에 설명한다. pending과 늦은 회신 수용은 유지하며, 같은 대화가 재개되면 설명을 제거 | `0df2541` |

P3는 등록 파일 하나를 직접 읽는다. 네이티브 런타임 조회·전체 directory·대화 기록 스캔을 추가하지 않는다.
stale·missing·원격·다른 홈·다른 대화의 등록을 명시 종료로 취급하지 않는다. 새 명령·필수 인자·wire outcome·결과 필드를 추가하지 않았다.

## 완료 기준과 근거

아래 검사는 실제 저장·상태·콜백·CLI/MCP 경로를 사용하고 외부 전송과 프로세스 실행 경계를 대역 처리한다.
네이티브 하네스의 동작을 재인증하는 검사는 아니다.

| 기준 | 확인한 경로 |
|---|---|
| R1 | `AttemptsTest.test_failures_after_latest_success_still_exhaust_the_limit`: 성공 뒤 실패 3회가 상한에 걸리고 새 성공 뒤 초기화 |
| R2 | 같은 검사에서 다른 폴더·다른 과제의 성공이 원래 과제의 상한을 해제하지 않음. 기존 outcome 없는 기록과 계보 검사도 통과 |
| R3 | `RequestedStopTest`: 사용자 중단 3회는 실패 0회, 기존 실패 2회는 그대로 유지 |
| R4 | 같은 테스트 묶음에서 후속 명시 실패는 계속 집계하고, 정지가 이미 기록된 성공·실패 회신을 덮어쓰지 않음 |
| R5 | 자동·내부 정지, once의 outcome 없는 회신과 정리, CLI를 통한 owned 제거 후 journal 보존, unknown 실행의 재실행 방지 |
| R6 | `QuestionsTest.test_explicit_target_end_is_explained_without_closing_or_mutating_question`: 설명·pending·recover_at 유지, 질문 원문 불변, 추가 전송 없음 |
| R7 | `QuestionsTest.test_resume_clears_end_explanation_and_late_final_reply_is_retained`: 재개 시 설명 제거, 늦은 성공 회신 수용 |
| R8 | live·stale·missing·다른 홈·대화·런타임·등록 거부·제외·원격의 음성 대조. 추가 네 런타임의 등록·종료·재개는 메타데이터 fixture만 사용 |
| R9 | `SharedQuestionServiceTest`의 CLI·MCP 응답과 `QuestionGroupTest`의 자식 설명 검사. 실제 격리 호스트 응답 2종을 기존 공개 결과 스키마로 검증 |

대상 회귀 명령:

```sh
python3 -B -m unittest \
  tests.test_workers.AttemptsTest \
  tests.test_workers.RequestedStopTest \
  tests.test_workers.OnceTest \
  tests.test_workers.FrameworkTest \
  tests.test_owned_workers.OwnedWorkerTest.test_idle_context_retirement_fresh_session_and_worker_removal_keeps_journal \
  tests.test_owned_workers.OwnedWorkerTest.test_unknown_execution_does_not_auto_repeat_side_effect_or_report_success \
  tests.test_questions tests.test_question_groups tests.test_question_service
```

최종 결과: `Ran 73 tests in 12.519s`, `OK`, 종료 코드 0. 원시 로그는 로컬
`/private/tmp/xsm-adoption-final-tests.log`에 있다. 이 중 새 회귀 검사는 13개이며, 기존 owned 제거 검사도 CLI 정지 경로를
통과하도록 보완했다. 공개 호스트 스키마 검사 2종은 `/private/tmp/xsm-adoption-final-schema.json`에 결과를 남겼다.
문서 링크와 R1~R9 근거 9개를 확인했고, `git diff --check`도 종료 코드 0이었다.

## 반증과 검사 대상 보정

- P1 새 회귀 검사는 수정 전 `0 != 3`으로 실패했다.
- P2 사용자 정지 검사 5개 중 2개가 수정 전 실패했다. 사용자 정지 3회가 실패 3회로 세어지고, 기존 실패 2회에 정지가 더해져 3회가 됐다.
- P3의 단일 조회·재개·그룹·CLI/MCP 검사 4개는 수정 전 종료 설명 부재로 실패했다.
- 첫 스키마 검사는 호스트 전용 스키마를 CLI 응답에 직접 적용해 실패했다. CLI와 내부 producer에는 호스트의 wait_budget 등 필수 봉투가 없다.
  스키마를 완화하거나 필드를 만들어 통과시키지 않고, 격리된 `Connection.operation.call`의 실제 응답으로 검사 대상을 바로잡았다.
  단일 미응답 결과와 종료된 수신자를 포함한 그룹 결과 2종이 기존 스키마를 통과했다. CLI·MCP는 해당 진입점의 회귀 검사로 확인했다.

## 미실행과 후속 범위

사용자 비용 제한에 따라 실제 런타임·구독 모델·메신저·게이트웨이는 다시 실행하지 않았다. 네이티브 경계를 바꾸지 않은 공통 코드 수정이므로,
이는 이번 완료 기준에서 제외하기로 정한 검증이며 실사용 효과를 새로 측정했다는 뜻이 아니다.

자동 정지 사유 전반의 재분류, once 중간 회신 정책 변경, 새 blocked/interrupted outcome, 자동 재배정·수락·복구는 구현하지 않았다.
34개 후보의 후속 조건과 사용자가 아직 결정하지 않은 사항은 계획서에 남아 있다. 전역 설치·push·릴리즈도 수행하지 않았다.
