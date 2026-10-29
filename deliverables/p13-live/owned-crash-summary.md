# P08/A18-08 실제 native 종료 경계 표본

고정본 `/private/tmp/xsm-p13-postqa-frozen-bukwksw6`의 5개 journal 경계에 모두 도달했다. 실제 구독 Codex child 5개, native turn.started 5회, 기본 셸 도구 실행 5회였다. 각 private counter의 최종값은 1이었다. native MCP 도구 호출은 0회이며 MCP 호출 성공 표본으로 세지 않는다. 실행 본체는 61.44초였으며 준비·분석·보고를 포함해 25분 상한 이내다.

## 경계별 관측

모든 최초 controller는 해당 checkpoint에서 실제 SIGKILL(exit -9)됐다. ID·원문 digest·sender·work context·context ID는 회복 전후 동일하다.

| 경계 | 종료 시 native / 회복 추가 | counter 종료 시 → 최종 | 종료 시 → recover 상태 | 실제 회복 경로 | 저장 답 / reply ID | publication 시도 / canonical 원본 | 잔여 child·process group |
|---|---:|---|---|---|---|---:|---:|
| 요청 보관 직후 | 0 / 1 | 없음 → 1 | queued → queued | 같은 ID·원문 run_owned | 종료 시 미생성 | 1 / 1 | 0 |
| 수락/ack 직후 | 0 / 1 | 없음 → 1 | acknowledged → queued | 죽은 controller 예약 회수 후 같은 요청 실행 | 종료 시 미생성 | 1 / 1 | 0 |
| 부작용 뒤·답 보관 전 | 1 / 0 | 1 → 1 | running → unknown | 동일 ID 재호출은 unknown 유지; 기본 reconcile stdout readback | 종료 시 미생성; readback 후 최초 생성 | 1 / 1 | 0 |
| 답 보관 직후 | 1 / 0 | 1 → 1 | result-ready → result-ready | resend_owned | 결과 전체·digest·reply ID 동일 | 1 / 1 | 0 |
| 답 전송 직후·journal 확정 전 | 1 / 0 | 1 → 1 | sending → result-ready | resend_owned | 결과 전체·digest·reply ID 동일 | 2 / 1 | 0 |

각 child의 실제 PID·lstart·CID·종료코드와 도구 종류, turn 이벤트 수, stdout SHA는 [결과 JSON](owned-crash-results.json)에 결속했다. child 종료코드는 모두 0, 명시 outcome은 모두 succeeded였다. 최초 fault controller도 모두 종료됐으며 child PID와 해당 process group의 잔존 프로세스가 없었다.

`after-execution`은 실제 기본 도구가 counter를 쓰고 읽어 확인한 뒤 native child가 정상 완료한 시점, 답 journal 저장 직전이다. 도구 write 중간이나 child 실행 중간을 죽인 표본은 아니다. effect 불명 상태를 강제로 성공 처리하지 않았다. 먼저 `unknown`과 동일 ID 실행 차단을 확인했고, 이어 제품 기본 readback이 보존 stdout의 실제 정상 terminal event를 검증해 답을 회수했다. 모델 재실행·custom readback·가짜 결과 주입은 없다.

## 실제 경로와 조건

- `create_owned` → `run_owned` → `owned_status`/`owned_requests.recover` → `reconcile_owned` 또는 `resend_owned`를 사용했다. executor는 제품 기본 `_execute_owned` 그대로다.
- fault 계측은 제품이 제공하는 checkpoint callback에서 평가 controller 자신을 SIGKILL하는 코드뿐이다. journal/state 수동 보정은 없다.
- 실제 native는 기존 owner의 Codex home과 기본 프로필로 실행했다. 제품이 원래 넣는 workspace-write/approval never 외에 allowedTools·permission·trust·framework 설정을 보정하지 않았다. API 키 경로를 사용하거나 credential을 복사하지 않았다.
- native 모델에 고유 private tmp의 counter를 기본 파일/셸 도구로 한 번 증가시켜 읽어 확인하도록 요청했다. 실제 기본 command_execution은 각 1회, exit 0이었다. 이 표본의 counter=1 관측은 일반 부작용 exactly-once 보장이 아니다.
- 답 발행은 제품 `publish_owned(wake=False)`를 사용했다. private canonical 보관만 확인했으며 최종 상태는 모두 `reply-stored`다. native UI 전달·수신·ACK를 증명하지 않는다. 마지막 경계의 두 발행 시도는 같은 reply ID를 유지했고 canonical 원본은 1개였다.
- 모델 호출 전 두 경계는 최초 종료 당시 실제 child 0개다. 해당 두 요청의 회복 실행은 최초 모델 실행이며 자동 모델 재시도가 아니다. 나머지 세 경계는 기존 child·stdout을 유지해 추가 모델 실행 0회다.

## identity 및 설치 조건 구분

owner runtime/home/SID/PID는 실제 `registry.me()`의 native endpoint를 그대로 private registry에 재등록했다. owner SID/PID를 합성하지 않았다. worker 이름·요청 ID·work context·marker 경로만 평가 fixture다. 별도 scope/grant를 만들지 않았다.

기존 owner record의 cwd는 `~/.codex-3/plugins/cache/xsm/xsm/0.4.20`이었다. 이 값을 그대로 worker cwd로 사용했다. 별도 관측한 app-server PID의 프로세스 cwd는 `~/Documents/GitHub/opencodex-setup`이므로, registry의 세션 cwd와 app-server cwd를 동일한 사실로 취급하지 않는다. 이번 제품 owned controller는 고정본 모듈을 import했으며 시작 전 manifest 313개와 종료 후 같은 파일 해시 일치를 확인했다. native는 기존 profile의 설치 안내/MCP 설정을 그대로 볼 수 있는 조건이다. factory MCP를 주입하지 않았고 native MCP 호출 자체는 없었다. 따라서 이 표본은 고정본 owned journal/native executor 회복 검증이며, 고정본 native MCP startup 호환성이나 Claude 종료 경계의 추가 증거는 아니다.

## 산출물과 한계

- [실행 하네스](owned-crash-eval.py), [읽기 전용 사후 대조](owned-crash-audit.py), [결과](owned-crash-results.json), [증거 manifest](owned-crash-manifest.json).
- 원 fault 상태, 전후 journal copy, native stdout/stderr와 marker는 `/private/tmp/p13-owned-crash-jly3ax9r`에 보존했다. 공개 산출물에는 claim/reservation token이나 원시 개인 본문을 복사하지 않았다.
- 경계 미도달·permission 거부·host 준비 실패는 이 표본에서 없었다. 5개 종료 경계는 모두 관측했다. 전체 P08 또는 모든 runtime/장애 유형 완료로 확대하지 않는다.
- 새 제품 결함은 재현되지 않았다. 제품 소스 수정·전역 설정 변경·모델 자동 재시도는 없었다. 소유 native child와 fault controller가 모두 종료됐고 사용자/peer 세션을 종료하지 않았다.
