# 사람 결정 상태·입력 승인 진단 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

## 정의와 경계

xsm_decision_status의 목록/상세/not-found, 적용 중·적용 완료에 대한 취소 거부,
legacy pending/unbound 입력과 닫힌 marker를 schema로 정의했다. 공통 claim은
inbox와 같아야 한다. Schema/예제를 public bundle REQUIRED에 추가했다.
서버·SDK 실행 의존성이나 승인 정책은 변경하지 않았다.

답 수신과 적용 관측을 구분한다. Started application은 outcome unknown이며
취소로 중단됐다고 말하지 않는다. Applied도 별도 domain 효과 관측이 필요하고,
기록된 결과를 API 재실행 template으로 쓰지 않는다. Scope와 raw reply/result는
의도적으로 tool별 opaque metadata다. 출처 label/allow 문자열만으로 승인하지 않는다.
Attention의 OS 호출 성공은 사람이 봤다는 뜻이 아니며 human_saw/viewport는 null이다.

Native 질문/질문·표시 text digest, applied의 관측 metadata, attention ID,
consent marker/ID의 내부 결속은 개발 checker가 확인한다. 현재 권한·reader liveness·
실제 인간 여부는 coordinator/runtime의 별도 검증이다. 상세 의미는
`docs/protocol/output-contract.md`의 human decision status 절에 있다.

## 표본과 실행

공개 decisions suite에 적용 후 취소 거부, 외부 소유자 조회/목록 거부, 목록 복구,
미적용 취소와 늦은 답 거부, pending consent 조회/닫기와 host decision 분리를
추가했다. 최종 suite45개/frame58개가 통과했다(wire-final.json).

예제27개는 실제 격리 stdio11개(공개 예제에서는 scope cwd를 fixture 경로로 치환),
격리 decision-store/Connection API16개다. 후자는 합성 host/receipt와 fake OS runner를
썼다. 실제 OS 알림·사람 승인·domain 변경을 수행한 표본이 아니다. Deny/dismissed/
unshown-or-declined/unknown/expired/superseded, started cancellation refusal,
typed/input receipt, legacy application과 attention·unbound 입력도 포함한다.

```sh
python3 -B scripts/conform-host-protocol.py --suite decisions --capture \
  --output deliverables/protocol-foundation/decision-status-contract/wire-final.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
python3 -B scripts/check-protocol-schema.py \
  --wire-trace deliverables/protocol-foundation/decision-status-contract/wire-final.json \
  --output deliverables/protocol-foundation/decision-status-contract/schema-final.json
```

예제27개와 실제 frame58개가 통과했고 잘못된 결과16개는 거부했다. OS-call 성공을
human_saw=true로 만들거나 applied의 관측 검사를 빼는 변이2개도 의도한 invalid
result failure로 검출했다(mutants.json). Import/일반 실행 오류를 검출로 세지 않았다.

초회 checker는 unbound가 비어 있는 stdio 표본을 선택해 IndexError로 실패했다
(schema-first.log). 실제 unbound event가 있는 fixture를 고른 뒤 통과했다. 실패를
삭제하거나 구조 검증 성공으로 계산하지 않았다. 최종 bundle 누락 거부 검사1개도
0.095초에 통과했다. 원시는 deliverables/protocol-foundation/decision-status-contract/다.

## 남은 조건

현재 source의 전체 core와 Linux 고정 source·새 wire/schema 실행은 결과 확인 전까지
미완이다. 실제 사람/native/물리 원격/설치/p95 전체 행렬과 미정의 계약은 별도다.
구현 담당 세션이 해당 표면을 실행해 갱신한다. 이 부분 계약을 전체 계획 완료로
대체하지 않는다.

## Mac 전체 core

`python3 -B scripts/check-protocol.py`는 Mac/Python3.14.6에서893개
(Python517+외부 적합성35+SDK56+native133+Node152)를94.949초에 통과했다
(core.log, exit0). Decisions suite의 check 수를35→45로 늘렸지만 unittest case
수는 유지했다. 독립 mock39/변이14는 별도 수치다.
