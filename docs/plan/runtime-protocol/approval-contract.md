# 개별 worker 승인 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

`xsm_approve`의 text+approval snapshot, host 질문 대기, 기존 text-only 결과를
공개 JSON Schema로 정의했다. Snapshot은 정확한 요청에 저장된 승인/거부 답이며,
worker 실행·효과·현재 권한 또는 실제 사람/native UI 검증을 보장하지 않는다.
ID/worker/status/summary/tool/answered_at/via/reason을 검증하며 내부 challenge나
임의 필드를 허용하지 않는다. Pending 구조는 question 계약과 같아야 한다.
두 필수 JSON을 공개 bundle 및 누락 거부 검사에 연결했다.

`--suite approvals --capture`는 격리 상태에 합성 worker 요청을 만들고 실제
stdio에서 대기→답 저장→원 작업 retry→승인/거부 snapshot→승인 replay를 검사한다.
저장된 요청의 상태도 대조하므로 저장소 독립 적합성 인증으로 부르지 않는다.
Worker나 모델은 실행하지 않는다. 정상 검사26개, 관측 frame28개 중 approval
결과6개(text-only1, pending2, approved2, denied1)를 검증했다.
예제4개와 잘못된 구조12개를 검사했다. 승인 ID 제약을 제거한 schema 변이는
경로형 ID 허용을 검출하며 실패했다(mutant.json).

정상 wire에 approval metadata 누락·다른 요청 ID를 주입하는 결함2종을
회귀 검사에 추가했고 둘 다 의도한 snapshot 검사에서 실패했다.
Mac/Python3.14.6 core908개(Python527+외부 적합성40+SDK56+native133+Node152)는
76.030초에 통과했다(core.log, exit0). 독립 mock39/변이14는 별도 수치다.

원시는 `deliverables/protocol-foundation/approval-contract/`다. 첫 실행은 임시
cwd에서 xsm 모듈을 찾지 못해 initialize 전에 실패했다. 이 기록은
wire-invalid-launch.json에 보존했고 성공 수치에 포함하지 않았다. 이후 저장소를
명시한 격리 stdio 실행의 wire.json/schema.json을 사용한다.

Linux와 실제 사용자/native UI, 나머지7개 operation 및 team/board의 남은 action,
전체 런타임·원격·설치·p95 행렬은 이 변경만으로 완료되지 않는다.

