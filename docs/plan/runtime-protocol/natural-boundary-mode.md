# 명시적 자연 경계 전용 SDK 전달

상태: P2/P4의 부분 진척이다. 전체 계획은 미완이다.

Python/Node host에 automatic_delivery/automaticDelivery bool 옵션을 추가했다.
기본은 기존 동작이며 false이면 callback은 유지하되 events capability/subscription과
이벤트 기반 수신을 끈다. 명시적인 natural_boundary/naturalBoundary만 native callback을
호출하며 wake=False다. 소비 ACK는 자동으로 하지 않는다.

실제 protocol subprocess 검사에서 callback을 제공해도 events를 광고하지 않고,
수동 subscribe로 들어온 event도 무시했다. 명시적 경계에서 원문/claim을 전달하고,
현재 token이 유지되며 별도 ACK가 필요함을 확인했다. API 부재/원치 않는 events
광고 때문에 수정 전 Python/Node가 각각 실패했다(before 로그).

추가 retry/batch 검사도 수정 전3 != 2로 실패했다. false 모드에서 경계가 거부되거나
batch가 남아도 background 재시도/후속 drain을 만들지 않게 했다. 다음 명시적
경계에서 새 claim으로 같은 원문을 재인수하고 다음 batch도 전달한다. Bool이 아닌
옵션은 자식 프로세스 시작 전에 거부한다. 기존 active 기본값의 retry/batch 의미는 유지한다.

각 언어 focused4개가 통과했다(Python2.301초, Node약2.678초). Mac core952개
(Python551+외부 적합성54+SDK59+native133+Node155)와 schema/기존 mock/v7 local은
56.991초에 통과했다(core.log). 원시는
`deliverables/protocol-foundation/natural-boundary-mode/`다.

이 SDK 모드만으로 Hermes 실제 hook 전달이나 idle wake를 완료했다고 하지 않는다.
고정 v0.22.5 source를 새 임시 경로에 풀어 tag/clean/dependency 경로를 확인했고,
다음 구현은 실제 pre_llm_call context와 pre_api_request 관측에 연결한다. Native
wake/UI·다른 runtime·원격·메신저·설치와 원래 전체 계획은 미완이다.
