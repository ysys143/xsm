# P03 준비: 질문·비동기 인터페이스 경계 명세 초안

- 기준 코드: xsm 0.4.20, 커밋 `4fd7c9f` (작업 디렉터리 = 저장소 루트)
- 성격: 읽기 전용 조사. 제품 코드·테스트를 실행하거나 수정하지 않았다. 게이트 G03은 아직
  열리지 않았고, 이 문서는 P03의 완료나 선행 게이트 통과로 세지 않는다
  (근거: `docs/plan/reason-inspired-adrs/execution.md` 13행, 138행).
- 확인한 것은 파일:줄로 적고, 확인하지 못한 것은 "미확인"으로 남긴다.

## 1. MCP 서버의 도구 목록과 호출 분배

도구 스키마는 모듈 상수 `TOOLS` 하나이고 서버 시작 시 한 번만 읽힌다
(`xsm/mcp.py:50` 선언, `xsm/mcp.py:745-746`의 `tools/list`가 이 상수를 그대로 반환).
현재 이름과 선언 위치:

| 도구 | 선언 | annotations |
|---|---|---|
| `xsm_post` | mcp.py:51 | MESSAGING (mcp.py:61) |
| `xsm_channel` | mcp.py:62 | READ_ONLY (mcp.py:68) |
| `xsm_grant` | mcp.py:69 | 없음 |
| `xsm_send` | mcp.py:85 | MESSAGING (mcp.py:108) |
| `xsm_inbox` | mcp.py:109 | MESSAGING (mcp.py:120) |
| `xsm_link` | mcp.py:121 | 없음 |
| `xsm_join` | mcp.py:131 | 없음 |
| `xsm_reach` | mcp.py:138 | 없음 |
| `xsm_doc_endorse` | mcp.py:147 | 없음 |
| `xsm_approve` | mcp.py:153 | 없음 |
| `xsm_decide` | mcp.py:159 | 없음 |

annotations 키를 아예 두지 않는 도구가 여섯이다(위 표의 "없음"). 주석(mcp.py:33-40)은
`xsm_send`·`xsm_post`·`xsm_inbox`만 명시적으로 언급한다.

호출 분배는 문자열 비교 사슬이다. `Server.serve()`가 한 줄씩 읽어 `tools/call`이면
`Server.call(name, args)`로 넘기고(mcp.py:747-753), `Server.call`이 세션 확인·채널 해석·
author 구성 뒤 `Server._call`로 넘긴다(mcp.py:354-375). `_call`은 `if name == ...` 연쇄로
각 도구 함수에 분배한다(mcp.py:377-418). 등록되지 않은 이름은 "이 서버가 시작할 때 없던
도구" 오류로 처리한다(mcp.py:420-423).

**단일 reader의 코드상 의미.** 서버가 표준입력을 읽는 지점은 하나다 — `Server.read()`가
`self.inp.readline()`을 하는 단일 함수(mcp.py:282-284). 이 함수를 두 루프가 번갈아 쓴다:
(a) `serve()`의 메시지 루프(mcp.py:731), (b) 양식을 띄울 때의 `ask_client()` 대기 루프
(mcp.py:286-298). "단일 reader 유지"란 stdin 소비 지점이 하나이고, 그 하나를 두 루프가
상황에 따라 점유한다는 뜻이다. spec P03 3항(`docs/plan/reason-inspired-adrs/spec.md:244`)이
요구하는 "양식 응답·tool 호출·취소·ping을 ID로 분배"는 이 단일 read 지점에 분배기를 두라는
요구로 읽힌다(해석).

## 2. `send --wait`이 답을 기다리는 경로 (호출 순서)

먼저 용어를 코드로 고정한다. 지금 기다리는 것은 **답이 아니라 전달 영수증**이다.
`ledger.wait_for`는 `status`가 `queued`에서 벗어나기를 기다린다(ledger.py:144-152, 특히
148행). 영수증의 `decision`은 `delivered|held|blocked`(ledger.py:77-91)이므로, 기다려서
얻는 값은 "수신 측이 이 메시지를 어떻게 처리했는가"이지 "상대가 무슨 말로 답했는가"가
아니다. `ledger.py`에 `reply_to` 필드나 답 인덱스는 없다(3절 참조).

CLI 경로:

1. `cmd_send`가 `send.send(... wait=args.wait ...)`를 부른다(cli.py:664-692, 684-687행).
   `--wait` 기본값은 0.0이다(cli.py:2334).
2. `send.send` → `_send`(send.py:64, send.py:114). 전송 뒤 `wait > 0`이면
   `ledger.wait_for(msg_id, wait)`를 부른다(send.py:248-249).
3. `ledger.wait_for`는 0.4초 간격으로 `ledger.status`를 폴링한다(ledger.py:144-152).
   `status`는 메시지 엔트리 JSON과 `<id>.recv.json` 영수증을 합친다(ledger.py:131-141).
4. 결과 매핑: `delivered`면 `SendResult("delivered")`(send.py:250-251), `held|blocked`면
   그 상태(send.py:252-254), 그 밖(시간 초과 포함)은 `sent-unconfirmed`(send.py:255-267).

MCP 경로(`xsm_send`):

1. `_call`이 `wait = args.get("wait", 15)`를 읽고 `float(15 if wait is None else wait)`로
   `send.send`에 넘긴다(mcp.py:398-407). 스키마 기본값도 15이다(mcp.py:107).
2. 이후는 CLI와 같은 `send._send` → `ledger.wait_for` 경로다. **상한 없음**: MCP 경로의
   `wait`는 여기서 클램프되지 않는다(mcp.py:400-401). 원격 경로만
   `remote.MAX_SEND_WAIT`(300초)로 잘린다(remote.py:449-450, remote.py:526). 즉 같은 기계의
   로컬 대상에는 모델이 임의로 긴 `wait`를 넣을 수 있다(코드 경로상 상한 부재를 확인한
   것이고, 실제로 그런 호출이 일어나는지는 미확인).

수신 대기(inbox) 경로는 별개이며 답 대기가 아니다:

- CLI `cmd_inbox`: `inbox.wait_for(session_id, args.wait)`(cli.py:703-707)는 **개수만** 세다가
  반환하고(inbox.py:69-100, 85-87행), 그 뒤 `receive.take_inbox(me)`가 실제로 꺼낸다
  (cli.py:708). 꺼내기는 rename 선점이다(inbox.py:103-126).
- MCP `xsm_inbox`: `inbox.wait_for(..., min(wait, inbox.MCP_MAX_WAIT))` 후
  `receive.take_inbox(me)`(mcp.py:410-416). 상한은 60초이다(inbox.py:24).

## 3. 재사용할 기존 함수와 새로 필요한 상태

**그대로 재사용 가능(확인).**

- 봉투: `envelope.build(reply_to=...)`가 `reply-to=<id>`를 헤더에 쓴다(envelope.py:58-75).
  파싱은 `envelope.parse` → `_fields`(envelope.py:48-55)로 `header["reply-to"]`가 나온다.
- 원장: `ledger.queued/status/receipt_of/received`(ledger.py:25, 131, 115, 110).
  `queued`는 `preview`로 본문 앞 200자만 남긴다(ledger.py:33).
- 수신: `receive.check`(receive.py:487)와 `receive.take_inbox`(receive.py:718).
  inbox 경로도 훅과 **같은** `check`를 통과하고 같은 영수증을 남긴다(receive.py:748-766).
- 과제 종결: `receive._close_task`가 `header["reply-to"]`를 과제 ID로 삼아 `ledger.close`를
  부른다(receive.py:174-181). `kind == "reply"`일 때만 호출된다(receive.py:465-466,
  receive.py:763-766).
- worker: `workers.on_reply(sender_ref, reply_to, receiver, outcome)`가 `task_id == reply_to`로
  소유 worker를 찾는다(workers.py:1176-1190).
- 조회 일원화 대상: CLI `cmd_status`(cli.py:716-722)와 MCP가 같은 `ledger.status/wait_for`를
  쓸 수 있다. 현재 MCP에는 대응 조회 도구가 없다(`xsm_inbox`는 수신함 조회이고 메시지 상태
  조회가 아니다).

**새로 필요한 상태(확인 못 한 것 포함).**

- 답 인덱스: "요청 ID → 그 요청에 달린 회신들". `ledger.py`에 없고, 다른 어디에도 없다.
  `reply_to`는 `envelope`의 헤더 문자열로만 존재하고 조회용 인덱스가 없다. grep으로 확인한
  `reply-to` 소비 지점은 receive.py:178, receive.py:466, receive.py:766, envelope.py:208뿐이고
  모두 `kind == "reply"` 분기 안이다.
- `wait_end_reason`·`recover_at`·`evidence`·`reply` 축: spec 4.3이 요구하며(spec.md:128,
  spec.md:132), 현재 원장에는 없다. `status`는 영수증의 `decision` 문자열을 그대로 노출한다
  (ledger.py:131-141).
- pending 요청 맵: 모델이 건 `wait` 단위가 아니라 요청 ID 단위의 대기·취소 상태. 현재는
  `send` 호출 안의 로컬 `wait` 값뿐이다(send.py:248).

**원 요청 ID·reply_to 대조 검사 — 현재 있는 것과 없는 것.**

- 있는 것: (a) 수신 중복 방지 — `receive._repeat`이 `from_ref`와 `body_sha`를 대조해 같은
  수신자의 같은 메시지 재실행만 통과시킨다(receive.py:375-395). (b) 재전송 대조 —
  `send.resend_refusal`이 발신 세션 ref, 대상 ref, kind, `body[:200]`을 대조한다
  (send.py:273-312). (c) 원격 inbound 기록 — `remote.recorded_inbound`(receive.py:505).
  (d) 과제 종결 대조 — `_close_task`와 `workers.on_reply`(위 참조).
- 없는 것: **수신한 회신이 실제로 그 `reply_to`의 요청에 대한 답인지 대조하는 검사**.
  `check`(receive.py:487-526)는 봉투·발신자·범위를 보고 `reply-to`가 가리키는 요청의
  존재·소유·발신자를 확인하지 않는다. `_close_task`는 `reply-to`가 이 기계 원장에 있으면 그냥
  `ledger.close`를 부르고, 없으면 `ledger.close`가 조용히 반환한다(ledger.py:96-99,
  `if not entry: return`). 즉 다른 요청에 대한 답이나 존재하지 않는 요청을 가리키는 답을
  걸러내는 코드는 지금 없다(확인).

## 4. MCP에서 긴 대기 중 입력 유실 위험 (코드 근거)

1. **동기 단일 루프.** `serve()`는 `tools/call`을 그 자리에서 실행하고 결과를 보낸 뒤에야
   다음 `read()`로 간다(mcp.py:747-773). 스레드 풀·비동기 처리가 없다(mcp.py 전체에
   `threading`·`asyncio`·`concurrent`가 없다 — grep으로 확인). 따라서 `xsm_send`의 `wait`
   (`ledger.wait_for`의 sleep 폴링, ledger.py:144-152)나 `xsm_inbox`의 최대 60초
   `inbox.wait_for`(mcp.py:414) 동안 서버는 다른 입력을 읽지 않는다.
2. **ping 지연.** `serve()`의 ping 처리는 루프 본문에 있다(mcp.py:774-775). 긴 대기 중에는
   루프가 `call` 안에 머물러 있어 ping이 파이프에 쌓이고 응답이 지연된다. 클라이언트가 응답
   없는 서버를 죽은 것으로 보면 연결이 끊길 수 있다 — `inbox.py:24` 주석이 같은 이유로 MCP
   상한을 60초로 둔다. `ask_client` 대기 중에는 ping이 처리된다(mcp.py:297-298). 즉 ping
   처리 여부가 "어느 루프가 stdin을 쥐고 있는가"에 따라 달라진다.
3. **ask_client의 비-ping 입력 폐기.** `ask_client`는 `id == rid`면 반환하고, `ping`이면
   응답하고, 그 밖의 메시지는 어느 조건에도 걸리지 않아 그대로 버려진다(mcp.py:291-298).
   폼(elicitation) 대기 중 다른 `tools/call`이나 `notifications/cancelled`가 도착하면 그
   메시지는 재처리 없이 사라진다 — 되돌려 넣는 코드도 큐도 없다. spec이 지목한 "단일 stdin을
   여러 reader가 읽거나 ask_client가 tool/cancel을 버림"(spec.md:535)과 같은 결함이다.
4. **취소 처리 부재.** `notifications/cancelled`를 인식하는 분기가 `serve()`에 없다.
   `serve()`의 분기는 `initialize`·`tools/list`·`tools/call`·`ping`뿐이고(mcp.py:735-777),
   `notifications/*`는 `mid`가 없어 마지막 `elif`에도 걸리지 않아 조용히 무시된다. 진행 중
   `wait`를 취소할 경로가 없다.
5. **프로세스 전역 상태.** 동시 대기를 도입하면 다음이 서로 덮인다:
   `probe._quick/_deadline/_memo`(probe.py:37-63; `Server.call`이 `probe.quick()`으로 사용,
   mcp.py:358-359), `consent.supplied/used_via`(consent.py:568, 572; 784에서 매
   `take_or_request`마다 초기화), `Server.call_thread`(mcp.py:273; 751에서 호출마다 대입 —
   호출별이 아니라 서버 필드). spec 4.1도 같은 지점을 지목한다(spec.md:110).
6. **stdout 직렬화.** 응답은 `Server.send`가 `out.write + flush`로 쓴다(mcp.py:277-280).
   지금은 단일 스레드라 안전하지만, spec 4.1이 요구하는 thread pool 방식으로 바뀌면 이
   지점의 직렬화가 필요하다(추측 — 현재 코드에 잠금이 없다).

## 5. 미확인으로 남기는 것

- 실제 하네스(Codex TUI, Claude Code)에서 긴 `xsm_send wait` 중 다른 도구 호출·취소·ping이
  클라이언트 측에서 어떻게 큐잉·폐기되는지. 코드는 서버 쪽 경계만 보여 준다. 이 문서를 쓰는
  동안 시험을 실행하지 않았다(제약).
- `notifications/cancelled`를 클라이언트가 실제로 보내는지, 보낸다면 어떤 `id`를 참조하는지.
  `mcp.py`에 파서가 없다는 사실만 확인했다.
- MCP `xsm_send`의 `wait`가 상한 없이 `ledger.wait_for`로 들어가는 것이 실제 클라이언트
  타임아웃이나 연결 종료로 이어지는지(코드상 상한 부재만 확인).
- `inbox.take`가 rename 선점 뒤 `.taking`을 즉시 지우므로(inbox.py:113-123) 그 사이 프로세스가
  죽었을 때의 회수 가능성. P04의 claim/ack 계약에서 다룰 문제로 남긴다(여기서 확인하지 않음).
- 질문 API의 공개 이름·기본 대기값·부분/최종 답 표현(결정 D02, spec.md:510)과 도구 목록 갱신
  방식(동적 목록 캐시 호환). 사용자·인터페이스 담당의 결정 사항으로 남긴다.
- `xsm/mcp.py` 밖의 상세(remote.py의 원격 `wait` 경로, codex_daemon.py의 wake 응답)는 이번
  조사 범위 밖이다. codex_daemon.py:325-331이 알림을 "건너뛰는" 패턴을 쓴다는 것만 확인했다.
