# 사용자 답과 팀 결정 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

`xsm_decide`는 기존 text를 보존하고 검증된 답의 structured receipt를 추가한다.
팀이 없으면 recorded=false와 question/answer/options/via를 반환한다. 팀에
기록했으면 recorded=true와 공개 board record projection, node, sync_notes를
반환한다. 내부 record 전체를 복사하지 않고 필드를 명시적으로 선택한다.
이는 전략 실행·업무 완료·일반 권한·원격 동기화 완료 증거가 아니다.

공개 schema는 두 receipt와 host 대기, 기존 unanswered text를 정의한다.
팀 record 정의는 board의 로컬 projection과 일치해야 하고 pending은 question
정의와 같아야 한다. 필수 schema/예제를 bundle과 누락 거부 검사에 연결했다.

실제 격리 stdio collaboration31개와 decisions46개를 실행했다. 두 trace에서
관측 frame95개를 schema checker로 검증했다. 팀 기록은 board 조회와 같은
projection을 반환하고 같은 작업 retry가 원 receipt를 보존하는지 확인했다.
팀 없는 답은 recorded=false인지 검사한다. 예제4개·잘못된 구조9개를 검증하고,
ID 제약 제거 변이는 경로형 ID 허용을 검출했다(mutant.json).
Receipt 제거와 recorded 반전의 wire 결함2종을 주입하는 회귀 검사도 추가했다.

원시는 `deliverables/protocol-foundation/decision-contract/`다. 사용자 답은
합성 host가 반환했고 실제 사람/native UI·worker 실행 인증은 아니다.
나머지6개 operation, team/board의 남은 action 및 원래 전체 행렬은 미완이다.

Mac/Python3.14.6 core909개(Python527+외부 적합성41+SDK56+native133+Node152)는
77.157초에 통과했다(core.log, exit0). Wire 결함2종도 의도한 recorded receipt
검사에서 실패했다. 독립 mock39/변이14는 별도 수치다. Linux는 별도 후속 검증이다.
