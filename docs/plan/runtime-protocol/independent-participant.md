# 명세만 제공한 독립 참조 참여자 검증

## 입력과 구현 경계

사용자가 별도 독립 에이전트 실행을 승인한 뒤, fork 없이 공개 명세·schema·
적합성 검사기만 담은 묶음을 제공했다. 구현자는 xsm/, clients/, tests/와
다른 작업 기록을 읽지 않도록 지시받았다. 구현은 표준 라이브러리만 쓰는
Python stdio 참여자다. 이 입력 분리와 구현자의 경계 준수 보고는 인지적
독립 인증이나 모든 금지 파일 접근의 OS 차단 증거가 아니다.

결과 코드는 examples/independent-participant/에 있다. participant.py는
transport hardening을 반영한 v2, participant_v3.py는 duplicate-key 거부와
구조화된 inbox 결속 검사를 더한 v3다. 기존 성공·실패 증거와 v2 소스를
보존하면서 v3를 별도로 작성했다. 운영자가 실행 파일·계약 묶음·검사기·
새 출력 경로를 지정한다. 개인 경로가 기본값으로 들어 있지 않다.

각 실행은 격리 HOME/XSM_HOME/cwd와 PATH/LANG/TMPDIR만 상속한다.
선택한 서버 executable과 checker는 신뢰하는 운영자 설정이며, 수신 메시지나
첨부 데이터에서 실행 명령을 만들지 않는다. 이 격리는 OS sandbox가 아니다.

## 부모 작업자의 새 동결본 재실행

서버는 a1e48042c772592b7fcb070f0b755131c9badaa7의 git archive를 별도
임시 경로에 풀어 동결했다. source commit·archive SHA-256·실행 argv는
`deliverables/protocol-foundation/independent-reference-server-v4.json`에 있다.
입력 v4 묶음은 공개 문서 16개와 해시 manifest이며 구현 코드를 포함하지 않는다.
독립 구현자가 쓴 verify_v3.py를 부모 작업자가 수정 없이 실행했다.

- 종료 코드 0. 공개 suite 실행 120회 통과: lifecycle 16, messaging 33,
  events 36, decisions 35. 반복 lifecycle이 포함되므로 고유 요구 120개가 아니다.
- 후속 시나리오 8개·checkpoint 90개 통과. files, fresh-inline,
  preparation-recovery, wake, error-precedence, framing-precedence,
  decision-lifecycle, permission-decisions다.
- 부모가 별도로 실행한 자체 mock 검사 16개가 통과했고 결함 변이 4개가 탐지됐다.
- 이전 27a7c8e 동결본의 음수 wait 불일치 2개는 그대로 실패 증거로 남았다.
  새 서버에서는 기대 오류 -32602로 통과했다. 명세 기대값을 낮추지 않았다.

재실행 증거는 `independent-parent-results-v4/summary.json`과 시나리오별
wire, `independent-parent-v4.log`, `independent-parent-local-v3.json`에 있다.
기존 `independent-participant-results-v3/REPORT.md`는 이전 실패 표본의
보고서이며 새 통과 기록으로 덮어쓰지 않았다.

## 한계와 미완

결정 검사는 합성 host callback이며 실제 사용자 UI·사람 승인·native
transcript로 계산하지 않는다. 실제 만료까지 기다린 검사는 실행하지 않았다.
unknown 저장 wake=null은 합성 schema fixture로만 확인했고 서버 저장값을
수정해 만들지 않았다. manifest digest의 canonical byte encoding 계약,
모든 도메인의 결과 schema, streaming upload, 부분 적용·lease/강제 사망
전수, native runtime·모델·worker·remote·외부 메신저는 남은 검증이다.

공개 checker를 독립 transport에 연결한 suite와 구현자 자신의 후속 fixture를
구분한다. 모든 검사를 독자적으로 새로 작성했다거나 전체 프로토콜 인증을
완료했다고 주장하지 않는다. 미완 기록 주체는 이번 작업자이며 2026-11-02에
기록했다. 전체 계획의 범위 제외 승인은 없고, 해당 계약·실행 환경을 갖춘
후 재검증해야 한다.

## v5 큰 사본 준비의 독립 구현

같은 독립 구현자에게 aafd6dc 동결본의 공개 v5 묶음만 제공했다. 새 코드는
별도 v5 파일 6개이며 기존 v2/v3 소스와 결과는 보존했다. 구현자 보고에서
완료 토큰과 활성 슬롯을 혼동한 첫 slot fixture 실패가 있었고, 실제 활성/
완료·여러 owner 조합으로 관찰 가능한 handle 수 16개를 대조한 뒤 수정했다.
실패와 진단은 independent-participant-results-v5/에 남았다. 보존기간이 명확하지
않다는 지적은 완료 토큰을 새 업로드 슬롯 확보 때 먼저 회수할 수 있고 영속
준비는 request ID로 복구한다는 계약으로 보완했다. 서버 동작을 바꾼 것은 아니다.

부모 작업자는 제공한 동결 서버와 같은 공개 묶음에서 verify_v5.py를 다시 실행해
공개 suite 159회(lifecycle 16/messaging 33/events 36/decisions 35/uploads 39)와
자체 시나리오 7개·checkpoint 123개 통과·종료 코드 0을 확인했다. 반복 lifecycle을
고유 요구로 합산하지 않는다. 별도 helper mock 9개와 변이 4개도 재실행해 통과했다.
증거는 independent-parent-results-v5/summary.json, independent-parent-v5.log,
independent-parent-local-v5.json이다. 기본 v3 mock 16개/변이 4개와 새 v5 9개/
변이 4개를 공통 120초 명령에 함께 포함했다. v5의 기존 v3 회귀 90 checkpoint는
구현자 실행 결과이며 부모 재실행의 123개에 중복 합산하지 않았다.

이 표본은 뒤에 추가한 manifest_bytes/file-result schema 전이다. 그 계약까지
독립 구현이 확인했다고 확대하지 않는다. native runtime/UI/모델/remote/messenger,
quota/retention 전수와 backend fault 전체도 이 표본의 통과 범위가 아니다.

## 실제 서버 시계의 만료 표본

부모 작업자는 a1e4804 동결 서버에서 합성 host 질문 2개를 만들고, 서버 시계를
바꾸지 않고 expiresAt까지 실제로 대기했다. 1801.033초 뒤 10개 검사가 통과했다
(real-decision-expiry-run2/progress.json). 만료 전 받은 답의 exact replay는 expired,
만료 후 도착한 미응답 질문의 답은 -32003, 두 상태는 expired/application 없음,
기존 invocation 재시도는 -32003이었다. 실제 사용자 UI나 실제 사람 승인으로
계산하지 않는다. 첫 probe는 일반 SDK의 decision.response 차단으로 실패했고,
정상 trusted host helper를 쓰는 두 번째 표본과 분리해 보존했다.

이는 v3/v5 독립 구현자가 수행한 검사가 아니다. clock rollback·application 경합·
실제 native 질문 수집까지 검증한 것으로 확대하지 않는다.
