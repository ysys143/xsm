# Python 공통 호스트

상태: 실험 구현. Python 3.9 이상이며 Native runtime 인증과는 별도다.

`clients/python/xsm_host.py`는 stdio client 위에서 참여 수명, 수신 알림,
실제 native 수락 뒤 보고, 질문 표시와 원 작업 재호출을 처리한다.
`XsmHost.open(runtime=..., profile=..., conversation=..., cwd=...)`로 열고
`call(operation, arguments)`, `update(state)`, `close()`를 사용한다.

기본은 pull-only다. `deliver` callback이 없으면 events를 구독/광고하지 않는다.
Native 수신기를 연결할 때는 async `deliver(packet, options)`를 제공한다.
이는 실제 native 입력 수락을 확인한 뒤 반환해야 한다. 단순 작업 예약은 그
근거가 아니다. False를 반환하거나 예외를 내면 claim을 release하고 자동 전달을
중지한다. 이후 `natural_boundary()`가 원본을 다시 확인한다. ACK는 자동으로
보내지 않는다. options에는 wake, cancelled Event, lease_seconds가 있다.

`inbox_batch_size=2`처럼 지정하면 자동 수신 한 번에 반환할 메시지·notice 수를
제한한다. 범위는 1–100이며, 생략하면 기존처럼 건수 제한 없이 읽는다.
원문을 인수한 가득 찬 배치는 새 알림 없이 이어 읽는다. Notice만 반환돼 인수가
없는 경우에는 반복하지 않는다. `natural_boundary()`는 설정된 배치 하나를 읽는다.
이 설정은 바이트 예산이나 native queue의 용량 재시도를 대신하지 않는다.

UI는 async `present(event, cancelled)`를 제공한 경우에만 광고한다. 반환값의
키는 displayed, source_id, action, answer이다. 실제 native callback만 연결한다.
답 저장 뒤 원래 작업을 동일 인자로 재호출해 적용하며, UI 출력이나 전송 성공을
승인으로 취급하지 않는다. 취소는 대기자를 끝내며 이미 보낸 일반 작업을
rollback한다는 뜻이 아니다.

질문 응답을 연결하는 동안 다른 대기자가 취소해도 아직 RPC를 마무리하는
대기자를 잃지 않도록 응답 등록과 취소 판단을 직렬화한다. 일반 작업 자체를
합치지 않으므로 같은 전송을 두 번 요청한 것을 한 번으로 바꾸지 않는다.
마지막 대기자의 취소는 표시를 포기하며 거부나 철회로 기록하지 않는다.
질문 Future도 실제 취소 상태로 끝낸다. CancelledError를 일반 예외처럼 저장해
Python 3.14의 shield가 오류로 보고하던 경로를 수정했다. 서버의 질문은 답이
없는 pending 상태를 유지하며, 같은 질문의 다른 대기자가 있으면 취소하지 않는다.

검사는 실제 protocol subprocess에서 UI 응답/재호출, 동시 대기와 취소,
수락 실패/회복, FYI, 명시적 ACK, peer 종료, snapshot SDK namespace 분리를
포함한다. 실제 native UI와 모델 응답은 각 binding에서 별도로 검증한다.
