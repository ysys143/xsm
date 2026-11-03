# Hermes local gateway FIFO 전달 연결

상태: P4 부분 구현. 전체 계획과 실제 interactive wake는 미완이다.

NativeGateway는 native manager가 게시한 gateway owner, hook 문맥의 실제 route/SID,
프로필 authority와 epoch를 고정한다. Native loop에서 현재 profile·권한·owner·
대화를 다시 확인하고 원문을 internal bot automation으로 FIFO에 넣는다. 실제
receipt의 admission ID/profile/epoch/원문/producer identity/target/bot author를
DB와 대조한 뒤에만 SDK delivery.report가 실행된다. ACK는 별도다.

`native_wake`는 기본 off이고 bool만 허용한다. `native_context`와 native
`allow_gateway_injection`도 true여야 한다. 사용자 설정을 자동으로 바꾸지 않는다.
현재 연결된 것은 gateway의 local 세션이다. Classic standalone CLI와 messaging
route는 이 모드에서 명시적으로 거부하며 지원 완료로 표시하지 않는다.

실제 FIFO까지 실행한 이유는 일반 inject_message의 예약 bool로는 queue acceptance나
정확한 SID를 증명할 수 없기 때문이다. `probe-hermes-gateway-target.py`는 실제
XSM stdio 저장소/SDK/Binding/NativeGateway와 Hermes GatewayRunner/authority/SQLite를
함께 실행한다. Context facade로 native gateway owner와 session 함수를 제공하며
drain scheduling은 비활성화한다. Actual native plugin hook dispatch나 모델/UI
증거로 계산하지 않는다.

구현 전 red-second는 automatic gateway delivery가 false라 실패했다. 첫 red는
프로브 자체의 chdir 뒤 상대 __file__ 처리 오류였으며 해당 실패도 남겼다.
정상 실행은31개 checkpoint를 통과했다. XSM 원문 저장에서 callback, 정확한
native FIFO 1건과 bot author, SDK admitted 보고, 원문 미ACK를 확인했다.
권한 철회·owner 교체·대화 교체·다른 profile과 원문이 다른 receipt를 거부했다.
Native epoch fence/replay/conflict 검사도 포함한다.

Binding의 conversation/receipt guard를 메모리에서 각각 제거한 변이2개는
`changed native conversation ... unexpectedly accepted`와
`corrupt native receipt accepted`로 exit1이 됐다. Upstream이나 production 파일은
변이 때문에 수정하지 않았다. 기존 context/binding28개는16.014초에 통과했다.
추가한 config 의존 검사를 포함한 전체959개와 schema/v7 검사는58.849초에
통과했다. 이 core는 새 외부 native probe를 실행하는 명령과 구별한다.

원시는 `deliverables/protocol-foundation/hermes-gateway-wake/`에 red/green/변이와
core.log를 분리해 보존한다. Linux 고정 source 실행, 실제 drain/model/hook/UI,
busy/now·FYI 혼합·재시작과 p95 100표본 및 원래 전체 행렬은 미완이다.
