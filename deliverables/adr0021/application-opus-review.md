# ADR-0021 메시징 통합 Opus5.5 검토

실제 `claude-opus-5-5` 한 번 호출의 고정 소스 판정은 `changes_required`다. 도구는 Read/Glob/Grep만 사용했으며 리뷰 모델은 검사를 실행하지 않았다. 67개 파일의 고정 manifest와 원 응답 SHA는 [원 판정](application-opus-review.json)에 보존했다. 아래 지적은 당시에는 정적 호출 경로 분석이었으며 후속 실행 증거와 구분한다.

## F1: 원격 send의 확정 ID 충돌이 operation-failed/unknown으로 바뀌고, 이후 상태 조회가 충돌한 기존 메시지의 상태를 이번 전송 결과처럼 보고함

Medium · `xsm/network.py:483-498, 199-205, 930-936`

이미 로컬 ledger에 있는 ID(이전 로컬 send나 다른 network send)를 써서 `xsm send net:... --request-id X --text ... [--wait N]`를 실행하는 경우. --resend는 쓰지 않음

정적 호출 경로이며 실행 증거가 아님: cli.cmd_send(xsm/cli.py:905,924)가 msg_id=X로 send._send를 부름 → send.py:279 network.call op=send → Daemon.send_remote가 prepared_intent=bool(ledger.status(X))=True를 넘겨 gateway.prepare를 호출(network.py:493-498) → network_messages.py:391-419에서 기존 outbound는 _same을 거쳐 GatewayError('message-id-conflict'), ledger row만 있으면 _intent_matches 실패로 GatewayError('prepared-intent-unverified')를 던짐 → GatewayError는 NetworkError가 아니므로 serve Handler(network.py:935-936)가 'operation-failed'로 응답함 → send.py:285-288의 refused 목록에 없어서 status='unknown'이 됨 → wait>0이면 network.reconcile(X)(send.py:293-298)으로 감. 충돌한 ledger row의 scope가 network:가 아니면 network.py:203-204가 그 row를 그대로 돌려주고, send.py:296-297이 그 status('delivered' 등)를 이번 전송 결과로 채택함. network: row라면 옛 to.ref로 message-status를 조회함

전송되지 않은 원격 메시지가 delivered로 보고되거나(CLI exit OK), 확정 거부가 unknown으로 남아 '같은 ID로 status 조회' 안내를 따르면 다른 메시지의 증거를 읽게 됨. PUBLIC_CODES와 send.py에 정의된 'message-id-conflict'→refused 계약은 실제 경로에서 한 번도 만들어지지 않음. ledger.queued가 prepare 뒤에 있어서 기존 row가 덮어써지지는 않음

## F2: P2P admission이 일시적으로 확인되지 않으면(서비스 중단, 2초 타임아웃) 영구 held/refused 영수증이 남고, 서비스가 복구돼도 원본이 다시 제공되지 않음

Medium · `xsm/receive.py:690-694, 1160-1163, 1176-1189, 600-615`

P2P 메시지가 저장된 뒤 수신 기기의 네트워크 서비스가 멈췄거나 admission RPC가 2초 안에 답하지 못한 상태(resolve_local/git probe 지연 등)에서 MCP inbox, `xsm inbox` 또는 네이티브 훅이 그 메시지를 처리하는 경우

정적 경로: network.inbound_record(network.py:190-196)가 call(op=admission, timeout=2)에서 NetworkError를 받아 None을 반환함 → receive.check(receive.py:692-694)가 'block'을 반환함 → take_inbox_claims(receive.py:1176-1189)가 hold() 후 ledger.receipt(id,'held'|'blocked')를 쓰고 delivery_state='held'|'refused'로 release함. 훅 경로인 _gate(receive.py:606-615)도 같은 영수증을 씀 → 서비스를 재시작해도 take_inbox_claims는 traffic 사유가 아닌 held/blocked 영수증을 건너뜀(receive.py:1160-1163). 자동 재평가 경로가 없음. 송신 측 reconcile은 gateway._delivery의 'held'/'refused'를 종료 상태로 받아들임(network.py:228)

유효하게 승인·저장된 원격 작업이나 질문 답변이 일시적인 서비스 장애 하나로 사람의 `held deliver`가 있어야만 전달됨. 그 경로도 4000자에서 잘린 사본이고, 정식 ACK와 파일 context가 없음. 송신자에게는 거부로 보임. 원본은 남아 있지만 정상 소비 경로로 복구되지 않아, 문서의 '서비스 중단 시 원격 큐 보존'과 맞지 않음

## F3: 소비 시점 admission이 배달 당시의 수신 generation에 묶여 있어, 수신 대화가 resume/재시작되면 이미 받은 P2P 메시지와 답변을 소비할 수 없음

Medium · `xsm/network.py:652-668`

wake=False FYI나 mcp-inbox 경로로 저장된 P2P 메시지(또는 질문 답변)를 읽기 전에, 수신 Codex/Claude 대화가 같은 session_id로 resume되거나 pid/lstart/mcp_pid가 바뀌는 경우

정적 경로: admission op가 resolve_local(record['packet']['receiver'], ...)를 호출하는데(network.py:659), packet.receiver에는 배달 당시 generation이 들어 있음 → resolve_local(network_directory.py:376)은 public_endpoint(r)==handle의 정확한 일치를 요구하고, generation은 pid/lstart/mcp_pid/mcp_lstart/native_start/app_server의 digest임(network_directory.py:72-82) → 새 실행에서는 None이 나와 {'allowed': False} → inbound_record가 None → receive.check가 block → F2와 같은 held/refused 처리. 송신자가 같은 ID로 resend하면 send_remote가 새 generation을 resolve하지만, Gateway.prepare는 기존 outbound가 있으면 _same만 거치고, receive는 기존 inbound record(옛 generation packet)의 committed 경로를 반환함(network_messages.py:582-595). 그래서 admission 근거는 갱신되지 않음

선택된 협업 쌍과 멤버십이 그대로인데도, 수신 측 대화의 정상적인 resume만으로 대기 중인 원격 작업과 questions 답변이 영구 차단/보류됨. collaboration.drop 문서가 '일시적 offline/resume은 철회가 아니다'라고 한 의도와 어긋남

## 수정 중인 경로

F1은 gateway의 확정 충돌을 IPC의 `message-id-conflict`로 보존해 이전 요청의 전달 증거를 새 전송 결과로 읽지 않게 바꿨다. F2는 일시적인 admission 불가를 명시적 권한 거부와 분리해 원문을 pending으로 유지하고 영구 held 영수증을 쓰지 않게 바꿨다. F3는 저장 당시의 실행 세대 대신 실제 현재 호출자의 네이티브 신원을 재검증하고 같은 안정된 대화 신원에 속한 원문을 소비하도록 바꿨다. 이 변경은 원문·wire fingerprint·ACK·다른 CID의 신원을 덮어쓰지 않는다.

새 반례의 실행·회귀 검증은 진행 중이다. 원 검토 판정을 승인으로 바꾸지 않았으며, 이후 모델 검토를 했다고 주장하지 않는다.
