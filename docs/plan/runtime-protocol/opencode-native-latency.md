# OpenCode canonical store→native readback 지연

상태: Mac smoke2개와 관측 제거 변이를 검증했다. Mac100개는 실행 중이며 Linux는
아직 미실행이다. 실제 모델/UI와 전체 기능 행렬은 미완이다.

`probe-opencode-protocol.py --canonical-latency`는 실제 설치 binding과 native
OpenCode1.19.5 server를 쓴다. 원래 SDK session.message를 호출한 뒤 반환된
실제 session/message/part와 xsmDelivery를 기록하는 임시 loader 관측기다.
제품 binding은 기존과 같이 noReply prompt로 저장하고 실제 message readback의
원문·세션·admission을 확인한 후 깨운다. SDK 성공만으로 수락 증거를 만들지 않는다.
이 loader는 일반 설치 ownership 검사의 대체 표본이 아니다.

송신은 실제 handoff.store 성공 반환 뒤 Python clock tick이다. 이 OpenCode
프로세스에서 process.hrtime은 Python의 MONOTONIC/RAW와 모두 불일치했다.
최초 smoke는 이를 감지해 plugin 초기화가 거부됐고 표본0개로 실패했다. 그 값을
지연으로 계산하지 않았다. 원시 clock.json과 실패 결과를 보존했다.

수정된 관측기는 native Bun FFI로 libc clock_gettime을 직접 호출한다. Darwin의
libSystem/Linux의 libc에서 clock ID를 Python과 동일하게 선택하고 Python
before/after 사이에 native tick이 있는지5번 확인한다. Native message readback
직후 같은 함수를 호출하므로 서로 다른 clock origin을 빼지 않는다.
Provider는 loopback scripted assistant이고 실제 native xsm_ack 도구가 실행된다.
합성 context capacity262144를 명시하며 실제 모델 규격·추천으로 취급하지 않는다.

실제 SDK readback 관측만 제거한 변이는 native ACK 후에도
`exact canonical store and native readback observations`로 실패했다.
수정된 canonical smoke2개와 기존 기본 모드 smoke2개도 통과했다.
기존 검사기의 native 도구 수21은 현재 공개 도구22개와 달라22로 맞췄다.
각 표본의 유휴 상태·native transcript·실제 도구 ACK를 확인하며, source/end
원시값과 native item ID를 보존한다. p95는 정렬한 값의 ceil(0.95*n)번째다.
원시는 `deliverables/protocol-foundation/opencode-canonical-latency/`에 있다.
