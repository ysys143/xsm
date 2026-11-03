# Worker 개별 승인 요청 결속과 결과 metadata

상태: P1의 부분 진척이다. 전체 계획과 approve 결과 schema는 미완이다.

## 발견과 수정

xsm_approve에서 id를 생략하면 decision key는 빈 인자로 먼저 만들어지고 실제
첫 요청은 나중에 골랐다. 첫 승인 뒤 다음 요청이 있어도 이전 결과를 재사용했다.
답을 저장한 뒤 첫 요청이 별도로 끝나고 같은 요약의 다음 요청이 생기면 이전
답을 그 요청에 적용했다. 같은 id의 input 변경도 질문 문장만 같으면 적용했다.
세 재현은 각각 failure로 확인했다(before.log).

승인 요청을 decision key 생성 전에 선택하고 실제 id로 정규화한다. Request와
worker의 immutable invocation 필드 fingerprint를 resource에 포함한다. 답변/
진행 필드는 제외해 정상 재조회는 유지한다. 요청 snapshot을 호출에 보존하므로
선택 뒤 새 요청이 들어와도 결정이 다른 요청으로 옮겨가지 않는다.

실제 반영은 request lock 안에서 fingerprint와 현재 parent/scope/deadline을 다시
검증한다. 바뀐 scope는 승인하지 않고 expected WorkerError를 ToolError로 전달한다.
동일 summary의 다른 요청, 새 첫 요청, 변경된 input은 새 결정이다. 질문에도 요청
id를 넣어 표시한다. Existing CLI input 경로와 parent 검사는 유지한다.

승인 요청 id도 경로 검증 없이 파일 작업에 들어가는 것을 재현했다(path-before.log).
Opaque id의 영문/숫자/밑줄/하이픈1–160자만 허용해 다른 상태 파일 접근을 막았다.
실제 hex8/hex16 id와 기존 r1 등의 legacy fixture id는 유지한다.

응답에 approval id/worker/status/summary/tool/answered_at/via/reason을 producer
metadata로 추가했다. 이는 답변 반영 snapshot이며 worker가 실행했다는 증거가 아니다.
적용된 허용의 명시적 id 재조회는 같은 snapshot을 보존한다. 표시 문장은 유지하며 worker 입력
전체나 private native identity를 metadata에 복사하지 않는다.

## 검사와 한계

관련 protocol/worker/MCP128개가11.001초에 통과했다(hardening-final.log).
명시적 snapshot 재조회, 첫 요청 변경, 동일 요약, input 변경, request lock 직전의
변경 주입과 경로 거부를 포함한다. 모두 격리 상태/합성 host 응답이며 실제
worker·사람·native permission 화면을 실행하지 않았다.

중간 편집 script의 문자열 치환 assertion이 실패해 파일을 쓰지 못한 실행이
있었다. 그 뒤 실행된 중간 focused/core 로그를 최종 metadata 검증으로 쓰지 않는다.
최종 source의 core-final.log와 별도 hardening-final.log로 구분한다. 기존 worker
시험 ResourceWarning은 보존했고 PID41907은 ps 후속 조회에서 존재하지 않았다.
이 warning을 고쳤다고 주장하지 않는다.

원시는 deliverables/protocol-foundation/worker-approval-binding/다. 고정 Linux core는 아래에서 확인했다. Approve 결과 schema 및 실제
native/runtime/원격/설치/p95 행렬은 확인 전까지 미완이다. 구현 담당 세션이 각 근거를 실행해 갱신한다.

## 명시적 host deny 전달

Host가 accept/deny를 저장하면 decision은 denied로 닫힌다. 공통 closed 검사 때문에
재호출이 worker의 개별 요청에 거부를 전달하지 못하던 경우도 오류로 재현했다
(deny-before.log). 같은 scope와 complete display, 검증된 deny reply를 확인한 경우만
negative 답을 읽어 해당 worker 요청에 반영한다. Allow는 기존 엄격한 form/application
경로를 그대로 쓴다. 거부의 재조회는 새 승인이 아니며 이미 끝난 요청은 no-waiting을
반환할 수 있다.

최종 관련129개가11.792초에 통과했다(denial-final.log). 이전125/128개 표본과
합산하지 않으며 최종 core는 core-complete.log로 구분한다.

Mac/Python3.14.6 최종 core906개(Python527+외부 적합성38+SDK56+native133+Node152)가
78.316초에 통과했다(core-complete.log, exit0). 독립 mock39/변이14는 별도 수치다.

## 고정 source Linux core

fd5229dd37a1b717693336abd863317ee09f162f의 archive SHA256은
e84ba7437dbd1dd543b59f05b4e2d9120e08ec50816ffac792c20340dff6b355다.
Python3.11.2에서89.581초, Python3.14.10에서112.965초로 core906개
(Python527+외부 적합성38+SDK56+native133+Node152)를 각각 통과했다.
독립 mock39/변이14는 별도 수치다. Model0/network none/cpu2/memory3g,
미실행 case0, VM stopExit0이다. 원시는 worker-approval-binding-linux의
result.json과 환경별 output/protocol.log다. 실제 사람/native worker 권한 UI나
원격 전체를 검증한 표본은 아니다.
