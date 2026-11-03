# 범용 호스트의 공개·선택 승인 연결

상태: P1/P2의 부분 구현이다. 전체 계획은 미완이다.

## 발견과 구현

xsm_publish와 범위 밖 xsm_connect는 UI 능력을 가진 범용 호스트에서도 기존
입력 훅용 selection-required만 반환했다. 최초 실제 Connection 검사2개가
기대한 waiting-for-user 대신 selection-required로 실패했다(before.log).

공통 connect 서비스에 선택적 승인 coordinator callback을 연결했다. CLI와 UI가
없는 호출은 기존 input-consent를 유지한다. MCP elicitation과 protocol의
user-decisions는 같은 permission form/decision journal을 사용한다. Runtime
이름별 새 분기는 없고 입력 API에 승인 flag나 모델 verdict 인자를 추가하지 않았다.

호스트 답을 저장해도 효과는 적용하지 않는다. 원 작업의 재호출이 있어야 공개나
정확한 pair 권한을 적용한다. Journal은 이 permission 효과만 기록하며 handshake
응답 전체를 캐시하지 않는다. 이후 handshake 상태/회신은 정본을 다시 읽는다.
Publication은 가시성일 뿐 pair/폴더 권한을 만들지 않는다.

Scope는 실제 native 신원 binding digest, 호출자 generation/cwd, 기존 효과 파일의
revision에 묶인다. Scope의 arguments는 permission 효과 설명이며 원 API 호출을
재생하는 template이 아니다. 표시 이름은 승인 키가 아니고 동일 신원의 질문은
원래 표시한 문장으로 고정한다. 이름을 다른 신원에 재배정하면 새 승인이 필요하다.
거부 뒤 표시 이름을 바꿔 다시 묻거나, 숨김 철회를 반복해 새 질문을 만드는 경로도
회귀 검사로 막았다. 실제 published→hidden 뒤 재공개는 새 승인이 필요하다.

적용 전 scoped application-start 기록을 요구한다. 적용이 실패하면 unknown을
유지하고 자동 재실행하지 않는다. 사람 응답 대신 자동 reviewer 응답이나 만들어낸
native answer_request를 넣어도 공개하지 않는다. Protocol의 native transcript
복구 미지원 경계는 그대로다.

## 실패와 검사

초기 재현2개는 수정 후1.008초에 통과했다(after.log). CLI/selected pair/network
interface와 관련 protocol 검사는63개가13.080초에 통과했다(focused.log).
이후 wire 결함 시험을 포함한98개가39.106초에 통과했다(focused-final.log).

추가 hardening에서 숨김 no-op 철회와 표시 이름 변경이 새 승인 key를 만들던
문제를 각각1개 실패로 재현했다(noop-before.log, rename-before.log). No-op은
identity 확인을 유지하며 상태를 갱신하지 않는다. 현재 최종 관련115개가
17.129초에 통과했다(hardening-final.log). MCP 실제 stdio reader의 accept,
auto_review 거부, 가짜 native 복구 거부를 합성 응답으로 구분했다.

첫 공개 suite는 상대 호스트에 UI cap이 없어 -32004가 반환됐는데 -32003을
기대한 시험 오류로17개 뒤 중단됐다(wire-first.json). 상대에게도 UI cap을 주고
identity 거부를 검사하도록 고쳤다. 이 실패를 성공으로 세지 않았다.

최종 `--suite selection --capture`는 lifecycle16개+승인12개 총28개를 통과했고
frame46개/host question3개를 관측했다(wire-final.json). 합성 host allow 저장 후
자동 공개하는 결함, 승인 결과로 handshake를 캐시하는 결함도 각각 의도한
검사에서 실패했다. 실제 사용자나 실제 native UI가 응답한 표본은 아니다.

## 결과 계약과 core

publication-result.schema.json과 예제6개를 추가했다. Published/hidden,
selection-required/refused, host UI pending 및 unconfirmed incoming 구조를
구분한다. 잘못된 결과8개와 가시성 제약을 약화한 schema 변이1개를 거부했다
(schema-current.json/schema-mutant.json). 질문 schema에는 connect의 qAwaiting을
추가해 예제23개/거부20개를 계속 검사한다. 실제46개 frame도 통과했다.

초기 core890개는94.805초, hardening 최종 core893개
(Python517+외부 적합성35+SDK56+native133+Node152)는96.634초에 Mac/Python3.14.6에서
통과했다(core.log/core-hardened.log). 서로 source/test 수가 달라 성능 배율로
해석하지 않는다. 독립 mock39/변이14는 별도 수치다. 최종 schema 필수 bundle
검사1개도0.113초에 통과했다. 모든 원시는
`deliverables/protocol-foundation/selection-host-ui/`에 있다.

## 남은 필수 조건

고정 source의 Linux core/새 stdio/schema 검증은 실행 결과 확인 전까지 미완이다.
새 경로의 실제 사람 UI, native 런타임 전체, 물리 원격/게이트웨이·설치/p95 행렬과
나머지 계약은 미완이다. Remote 서비스 callback은 연결됐으나 이번 host UI 표본은
로컬 pair다. 구현 담당 세션이 각 표면을 실행해 갱신한다. 전체 계획을 이 부분
결과로 대체하지 않는다.
