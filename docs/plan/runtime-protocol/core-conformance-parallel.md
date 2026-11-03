# 핵심 검사에서 외부 적합성 시험 병렬화

상태: 120초 핵심 검사 조건을 유지하기 위한 부분 진척이다. 전체 계획은 미완이다.

## 변경

기존 Python 단일 unittest 묶음에서 tests.test_protocol_conformance를 별도
프로세스로 분리했다. 기존 MODULES를 정본 목록으로 유지하며, 다른 Python 묶음과
Node/native/SDK/독립 participant 검사를 그대로 실행한다. 분리된 프로세스도
run_phase의 별도 HOME/XSM_HOME/CODEX_HOME/CLAUDE_CONFIG_DIR를 사용한다.
모델·메신저·사용자 설정은 사용하지 않는다.

첫 단계6개 실행 뒤 두 번째 단계의 group 번호를 실제 첫 단계 길이에서 계산해
임시 폴더가 겹치지 않게 했다. 두 단계는 같은 시작 기준의120초 deadline을
유지한다. 실패 시 나머지 process group 종료와 부분 로그 보존은 기존 경로다.
지원 범위·검사 수·deadline을 줄이지 않았다. 서버나 SDK 코드는 바꾸지 않았다.

## 검증

새 regression은 실제 main의 command plan을 포착한다. Python 모듈 전체가
MODULES+NATIVE_MODULES와 중복/누락 없이 일치하고, 외부 적합성이 단독 묶음에
있으며 SDK/Node 및 independent v3/v5/v6가 각각 한 번 존재하는지 확인한다.
두 phase의 폴더 offset과 공통 deadline도 확인한다.

변경 전 이 검사1개는 실패했다(before.log). 분리 후 gate 검사4개가0.656초에
통과했다(after.log). 기존 실제 subprocess barrier는 private homes와 병렬 도달을,
deadline/failure 검사는 자식 종료와 부분 출력 보존을 확인한다.

임시 source에서 conformance 실행을 누락하거나 두 번째 phase offset을 예전5로
되돌린 변이2개도 새 regression이 각각 assertion failure1개로 검출했다.
일반 실행 오류는0개였고 원본 source를 변이하지 않았다(scheduling-mutants.json).
원시는 deliverables/protocol-foundation/core-conformance-parallel/에 있다.

## 남은 조건

Linux 고정 source의 재검증 전에는 두 OS의120초 조건 검증을 완료했다고
판정하지 않는다. 구현 담당 세션이 각 실행 결과를
확인해 갱신한다. Native p95/전체 runtime/UI/remote/설치 및 미완 계약들은
이 변경으로 완료되지 않는다. 승인된 전체 계획은 그대로 남아 있다.

## macOS 전체 실행

`python3 -B scripts/check-protocol.py`는 macOS/Python3.14.6에서871개
(Python501+외부 적합성29+SDK56+native133+Node152)를88.867초에 통과했다
(core.log, exit0). 이전870개에 새 회귀 검사1개가 추가됐고 누락은 없다.
독립 mock39/변이14는 별도 수치다.

직전 송신 계약 source의 macOS 표본은870개/107.777초였다. 두 기록은 source와
검사 수가 다르고 각각 단일 실행이므로 통계적 속도 배율/p95 증거로 쓰지 않는다.
이번 전체 실행이120초 이내이고 모든 기존 검사 묶음을 유지한 사실을 확인한다.
