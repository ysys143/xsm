지정한 수정 범위에서는 Medium 이상의 구체 결함을 찾지 못했습니다(지정수정범위 Medium이상지적없음). 코드만 읽고 내린 판단이며, 테스트를 실행하거나 실측하지는 않았습니다. 판단 근거는 다음과 같습니다.

- **권한 우회 없음:** `_old_p2p_copy_receipt`(`xsm/receive.py:1134-1151`)가 참이 되면 영수증 때문에 건너뛰던 것만 해제됩니다. 실제 body와 claim은 그 뒤 `check()`(`:1211`)를 통과해야 나갑니다. P2P 경로(`:700-723`)는 `network.inbound_record`(`xsm/network.py:175-209`)에서 다음을 매번 새로 검증합니다. 따라서 판별식이 혹시 넓게 잡혀도 현재의 거절이 그대로 적용됩니다.
  - ingress record와 header·body·scope·kind·reply_to·outcome·attachments의 정확한 일치
  - 수신자 identity
  - broker의 fresh `admission` 응답(`allowed is True`)
  - 이어서 blocked, files manifest, traffic 검사
- **구형 사유는 현재 코드에서 나오지 않음:** 현재 `check()`는 `p2p:` origin을 먼저 처리하므로 "remote message from %s was not received by this machine's xsm" 사유는 p2p가 아닌 remote origin에서만 만들어집니다(`:727`). 판별식은 p2p origin을 요구하므로, 현재 코드가 p2p에 대해 쓴 held 영수증은 이 사유와 겹칠 수 없습니다.
- **canonical 실제 hold는 유지:** 현재 경로의 hold는 `delivery_state`를 held/refused로 바꿉니다(`:1219-1226`). 판별식은 status와 delivery가 모두 pending일 때만 참이므로 해제되지 않습니다. 이는 두 번째 테스트의 `ids[0]`이 실제 서비스로 확인합니다.
- **digest-bound 거절은 유지:** `ledger.receipt`(`xsm/ledger.py:296-303`)는 `body_sha`가 있으면 `from_ref`/`body_sha`를, `req_digest`가 있으면 `req_digest`/`req_version`을 기록합니다. 판별식은 이 키 가운데 하나라도 있으면 거짓입니다. 두 번째 테스트의 `ids[1]`이 이를 확인합니다.
- **ACK·재전송 경계 유지:** 재검사가 통과해도 `handoff.handoff`까지만 가고 ACK는 별도 토큰으로만 됩니다. 첫 테스트가 ACK 전 비acknowledged 상태와 held 사본 바이트 불변을 확인합니다. admission이 일시적으로 불가하면 release 후 pending으로 남고 구형 영수증도 그대로라서 다음 시도에 다시 검사합니다. 멤버 제거 후 재검사하면 held/refused가 됩니다(`ids[2]`).

```json
{
  "verdict": "approved",
  "findings": [],
  "reviewed_scope": [
    "xsm/receive.py:1134-1151 _old_p2p_copy_receipt",
    "xsm/receive.py:1154-1272 take_inbox_claims (receipt 선검사 1194-1198 및 이후 check/hold/release/delivered 영수증 경로)",
    "xsm/receive.py:681-723 check()의 p2p 분기 및 727 구형 사유 생성 위치",
    "xsm/network.py:175-209 inbound_record (fresh admission 호출 포함)",
    "xsm/ledger.py:284-304 receipt, 330-333 receipt_of",
    "tests/test_network_receive.py:34-88 test_old_hook_unknown_origin_receipt_cannot_hide_an_admitted_pending_original, test_old_hook_recheck_preserves_real_holds_and_current_membership_refusal"
  ],
  "limitations": [
    "Read/Grep 정적 검토만 했으며 테스트, 회귀, 실측은 실행하지 않았다. '양 Python에서 새 2개 통과'와 '수정 전 claims0 실패'는 사용자 보고를 그대로 옮긴 것이고 독립 확인하지 않았다. 전체 회귀 통과로 간주하지 않았다.",
    "handoff.claim과 Daemon.admission의 내부 구현은 읽지 않았다. 판단은 inbound_record가 fresh admission의 allowed is True를 요구한다는 호출부 계약에 근거한다.",
    "판별식은 영수증 reason을 원본 origin 문자열로 정확히 비교한다. 구 코드가 provenance.display_text(peer)를 적용했을 때 p2p origin 문자열이 달라지면 판별식이 거짓이 되어 숨김이 계속될 수 있다. 이는 fail-closed 쪽 가용성 한계이며 보안 결함은 아니다.",
    "status가 claimed/handoff-recorded인 상태에서 같은 consumer가 targeted 재회수하는 경로(1200-1202)는 판별식이 pending을 요구하므로 구형 영수증이 계속 숨긴다. 가용성 한계이며 범위 밖이다.",
    "poll_replies(receive.py:232-234)는 여전히 held 영수증을 그대로 믿는다. 지정 범위 밖이라 감사하지 않았다.",
    "재검사로 canonical이 delivered/ACK된 뒤에도 구 hook이 만든 held 사본은 남는다. 이후 사용자가 그 사본을 명시적으로 승인해 deliver할 때의 중복 여부는 기존 held/repeat 경로의 문제로, 이번 범위에서 감사하지 않았다.",
    "과거 Opus 판정과 1933 회귀 결과를 이번 승인 근거로 사용하지 않았다. 실제 모델 업무에서의 성공은 별도 실측 사항이다."
  ]
}
```
