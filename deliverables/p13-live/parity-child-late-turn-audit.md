# parity child의 늦은 두 번째 turn 원문 대조

두 번째 시작의 직접 근거는 native `turn_trigger=queue`와 그 뒤에 기록된 같은 reply 원문이다. 첫 turn에서 실제 MCP로 반환·명시 ACK된 파일 답 `a9f12c77eb524f65`가 native queue 입력으로 다시 나타났다. 새 logical send나 추가 모델 실행을 단정하지 않는다.

## 관측

| UTC | 근거 |
|---|---|
| 2026-10-29T02:05:54.035Z | same reply stored canonical |
| 2026-10-29T02:05:54.216Z | native queue accepted |
| 2026-10-29T02:06:00.685Z | first exec turn tools.wait returned actual MCP final reply |
| 2026-10-29T02:06:04.458Z | canonical ACK saved |
| 2026-10-29T02:06:04.564Z | first exec turn actual MCP ACK result returned |
| 2026-10-29T02:06:21.227Z | first exec task_complete |
| 2026-10-29T02:06:21.235Z | second task_started trigger queue |
| 2026-10-29T02:06:21.251Z | native response_item role=user/input_text contains same reply envelope |
| 2026-10-29T02:06:21.254Z | second queued turn aborted: interrupted, 19ms |

원 reply_to는 `aa1c99bcd11e4018`이다. MCP 반환 body와 native queued envelope에서 추출한 body가 byte 단위로 같으며 SHA256은 `3e738024d3533b0053659cd044656b6f524f692e6e3b878396fe829b5c3f249a`이다. canonical semantic digest는 `3b3e88cc0206e52c0b399457503417e5e43fe6c9881592bd4883d62b6d9d4051`로 body SHA와 구분했다. native input은 response_item/message의 role=user/content=input_text지만 peer cross-session reply이며 사람의 새 지시라는 뜻이 아니다. 두 번째 native input의 mcp_attribution에도 첫 turn의 xsm_ask/xsm_ack가 연결돼 있다.

## 추론

원 queue 등록은 MCP final reply 반환과 ACK보다 먼저였고, 실행 중인 첫 exec turn이 끝난 뒤 queue-triggered task가 시작됐다. 이 순서와 같은 ID/reply_to/본문은 한 답이 MCP와 native queue 두 수신 표면에 나타났음을 뒷받침한다. 별도 업무 질문 또는 reply 재발행을 관측한 것은 아니다.

## 미관측과 분리

보존 snapshot에는 같은 reply native user 입력 뒤 ordinal73의 harness-authored developer 중단 알림과 ordinal74의 turn_aborted가 있다. 두 번째 queued turn은 02:06:21.254Z에 reason=interrupted/duration_ms=19로 중단됐다. 후속 turn_context·assistant/tool 출력·provider token/model 요청·task_complete는 없으므로 추가 모델 추론은 입증되지 않았으며 unknown이다. 실제 중단 주체와 lifecycle 원인도 기록만으로 확정하지 않는다. 앞선 plain 답의 queue 처리·합침/소비 정책과 backend row 소비 원인은 이 표본으로 확정하지 않는다.

collector의 post-exit PID assertion은 별개다. 이는 답/ACK 이후 종료된 child PID를 재검사한 수집기 경로이며, queue-triggered task와 같은 reply native 입력이 존재한다는 원문 사실을 설명하거나 지우지 않는다. 기존 raw/result/script/보고서/ledger는 수정하지 않았다.

## 증거 보존

새 모델·런타임 재실행0. 원 audit manifest의 private raw SHA 전부를 확인했고 읽은 원파일의 전후 SHA가 동일하다. 세부 ordinal, attribution, canonical/queue 시각 및 원 증거 SHA는 같은 이름의 JSON에 있다. 이번에 새 JSON/MD 두 파일만 작성했다.

| 원 증거 | SHA256 |
|---|---|
| /private/tmp/persistent-parity-v3-host-9xxw5alo/sender-rollout.jsonl | d93686ca722b4c35e3472e13d66d9857dac9560488b036126fdbd28c78af6bd4 |
| /private/tmp/persistent-parity-v3-host-9xxw5alo/initiator.jsonl | 52c7afe55ae49bd74be07a8f3fb6935ed7790586487b777257f811c41d0053fc |
| /private/tmp/persistent-parity-v3-host-9xxw5alo/state/handoffs/c1e9f4f4d9675bb54afbced4462195435647c3ae3c9a2291eb3cd378751d57cb/a9f12c77eb524f65.json | 19d6e7464b48d2b070f981e30f4e9e1aa0b1fa9631932405a03380c3e397e24d |
| /private/tmp/persistent-parity-v3-host-9xxw5alo/state/ledger/a9f12c77eb524f65.json | 049181a79633ca8802d4595ebdcd1f00450b1638501b48379c65baf41a923071 |
| /private/tmp/persistent-parity-v3-host-9xxw5alo/state/ledger/a9f12c77eb524f65.recv.json | d21f46b1ad03e7fcffc9ca18cc3f81eccbaccd3642635e7c6a797aa1ec2052e1 |
| /private/tmp/persistent-parity-v3-host-9xxw5alo/state/ledger/a9f12c77eb524f65.handoff.json | 9475be247bdcc36db20ed7b36bf1c6f944d0b8bf0bc7f92f5d4325729ceb1920 |
| /private/tmp/persistent-parity-v3-host-9xxw5alo/result.json | 22ba97647bbcbf388c816ee5f6f34852d7b09e31a7ecaf7c13b0dcba7ae18ec1 |
| deliverables/p13-live/persistent-parity-native-v3-20261029.json | 22ba97647bbcbf388c816ee5f6f34852d7b09e31a7ecaf7c13b0dcba7ae18ec1 |
| deliverables/p13-live/persistent-parity-native-v3-20261029.audit.json | 8399e0add4603c443757484af2083771950f05574018f4567d05e911af3b2d39 |
| deliverables/p13-live/persistent-parity-native-v3-20261029.audit-manifest.json | c3821a74457d3c1827d22caaebb9d2b24faed0ae87476df2bf93f8b780865348 |
| deliverables/p13-live/persistent-parity-native-v3-20261029.py | ee13617f7eca7e679e6cb710010a73a3f89af899ce7b5ee83b68417be644d7cc |
