# Worker 승인 발급 metadata와 ID 경계

상태: P1의 부분 진척이다. 전체 계획과 grant 결과 schema는 미완이다.

xsm_grant의 승인 ID는 표시 문장에만 있었다. 실제 Connection 재현은 grant 필드가
없어 KeyError로 실패했다(before.log). 기존 표시 문장을 유지하면서 grant의 id,
runtime/cwd/options/asked_by, issued_at/expires_at/single_use를 producer metadata로
반환한다. 이는 발급 당시 snapshot이며 현재 사용 가능성이나 runtime 지원 보증이 아니다.

적용된 form 결과를 재조회할 때도 metadata가 남도록 내부 _xsm_display=1 snapshot을
journal한다. 기존 문자열 기록은 그대로 읽는다. 같은 승인 재조회는 새 grant를
만들지 않으며, 소비 후에도 원래 발급 snapshot을 돌려줄 뿐 재발급하지 않는다.
application.result는 관측 기록이지 API 재실행 template이 아니다.

조사 중 명시적 grant ID가 검증 전에 경로에 들어가는 결함도 재현했다.
../victim을 주면 거부가 나더라도 다른 상태 파일이 .used로 먼저 이동했다
(id-before.log). use_grant의 소비자는 legacy spawn, owned 생성, remote pairing
3곳이다. 실제 발급 형식인 소문자 hex8자를 파일 작업 전에 검증해 경로 해석을 막았다.
등록된 기존 ID의 caller/runtime/cwd/options/expiry 및 일회성 소비 의미는 유지한다.

초기 metadata 회귀1개는 오류로, 경로 회귀1개는 assertion failure로 실패했다.
수정 후 metadata/MCP form26개가4.126초, protocol/worker/person/MCP 관련202개가
20.110초에 통과했다(focused.log/hardening.log). Worker를 실제 시작하거나 dangerous
옵션을 실제 runtime에 적용하지 않았다. 모두 격리 fixture의 grant 파일과 실제
consume 함수로 확인했다.

Hardening 로그에는 기존 worker 시험의 unclosed-file/subprocess ResourceWarning이
있어 보존했다. 경고의 PID25038은 후속 ps 조회에서 존재하지 않았다. 이 경고들을
고쳤다고 주장하지 않는다. 원시는 deliverables/protocol-foundation/grant-result-contract/다.

고정 source Linux 검증은 결과 확인 전까지 미완이다. 실제 native
worker 모든 모드·사용자 UI·원격·설치/p95 행렬과 결과 schema 등 원래 계획은 남아 있다.

Mac/Python3.14.6의 core895개(Python519+외부 적합성35+SDK56+native133+Node152)는
75.611초에 통과했다(core.log, exit0). 독립 mock39/변이14는 별도 수치다.
이 단일 실행을 이전 source와의 통계적 성능 비교로 쓰지 않는다.
