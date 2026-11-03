# Owned·handover의 원 action에 따른 결과 선택

상태: P0/P2의 부분 진척이다. 전체 계획은 미완이다.

독립 v7 피드백에 따라 root union 검사의 범위를 조사했다. 합성 trace에서
owned run의 결과를 requests listing으로 바꾸거나 hand_over의 결과를 show로
바꿔도 기존 checker가 각각1개 observation을 승인했다. 실제 backend가 이런
결과를 냈다는 뜻이 아니라, 잘못된 응답을 검사기가 구별하지 못한 증거다.

두 schema에 x-actionResults를 추가해 owned6개/handover2개 action의 결과를
선택한다. Creation과 task/listing을 구분하고 handover는 input catalog의 기본
hand_over를 x-defaultAction으로 명시한다. Selector/default가 catalog와 같아야
한다. 예제에도 action을 명시했다. 이미 action 필드를 잃은 옛 trace에서 추정해
인증하지 않으며 새 capture나 원 request가 필요하다. Owned status의 listing과
exact request 선택 조건은 원 request_id에 따른 별도 문서 규칙도 유지한다.

같은 잘못된 trace2개가 수정 후 각각 ValidationError로 거부됐다
(after-rejections.json). Action 검사를 root 검사로 되돌린 변이2개도 실패했다
(mutants.json). 기존 negative15/9개 외에 owned action 혼동3개/handover2개를
별도로 거부한다. Frozen sourcecf01의 실제 owned/handover70개 observation은
새 checker로 통과했다(schema.json). 기존 기본 action 생략도 포함된다.

원시는 `deliverables/protocol-foundation/owned-action-results/`다. Backend/CLI/SDK의
result producer와 wire payload는 바꾸지 않았다. 독립 v7의 frozen 입력 검증은
원래 source를 유지하며 최신 selector/default에 대한 독립 소비자 재검증은 후속이다.
전체 operation 의미·오류 data·native/UI/원격·메신저·설치 행렬은 미완이다.
