# 문서 승인 결과 계약

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

`xsm_doc_endorse`의 기존 text에 endorsement receipt를 추가했다. Caller가 지정한
문서 경로, 새 immutable node ID, 정확한 부모 ID, 답 출처를 반환한다. 이것은
node 추가 결과이며 render·다른 agent 수락·업무 실행이나 원격 전달 증거가 아니다.
공개 schema/예제를 필수 bundle과 누락 거부 검사에 연결했다. Pending 구조는
question 계약과 같아야 한다.

격리 stdio endorsements25개 검사와 관측 frame35개를 검증했다. Agent 노드를
추가한 뒤 host 답 저장만으로 node가 늘지 않고 retry 뒤에 human/endorsed child가
생기는지 확인했다. Child는 원본 body/parent를 보존하며 재시도는 같은 receipt와
node2개를 유지한다. 거부 후 graph에는 추가 endorsed child가 생기지 않는다.
Render도 실제로 실행했다. 답은 합성 host이며 실제 사람/native UI 인증은 아니다.

예제3개·잘못된 결과7개를 검사했다. Metadata 제거와 잘못된 parent의 wire 결함
2종을 회귀 검사에 추가했다. 원시는
`deliverables/protocol-foundation/endorsement-contract/`다. 나머지2개 operation과
team/board의 남은 action 및 원래 전체 계획은 미완이다.

Mac/Python3.14.6 core913개(Python527+외부 적합성45+SDK56+native133+Node152)는
77.295초에 통과했다(core.log, exit0). Wire 결함2종은 의도한 원본 결속 검사에서
실패했고 node ID 제약 제거 변이도 검출했다(mutant.json). 독립 mock39/변이14는
별도 수치다. Linux는 후속 고정 source 검증이다.
