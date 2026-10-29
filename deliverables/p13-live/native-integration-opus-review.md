# Native MCP integration delta review

# 검토 결과: (1)은 범위대로 구현됐고, (2)에서 Medium 결함 1건이 나와 고친 뒤 승인을 권합니다

- (1) unloaded subagent `-32600` 처리: 정확한 오류 하나만 fallback으로 보내고, 권한·수신 검사를 우회하지 않습니다. ID·본문·wake·digest도 유지되고 ACK도 되살아나지 않습니다.
- (2) pending 집계: 반례 1건을 찾았습니다. 이 수정으로 새로 생긴 회귀입니다.
- 한계: 도구가 Read/Glob/Grep뿐이라 테스트·실행·hash 재계산은 하지 못했습니다. 실제 회귀와 native 후속 실행의 결과는 보지 않았고, 성공으로 간주하지 않았습니다. `test_xsm.py`의 변경분은 diff가 없어 대조하지 못했습니다.

## Medium — native hook이 차단한 메시지가 pending 수에 계속 남음

**위치**
- `xsm/handoff.py:219-259` (`pending_ids`)
- `xsm/receive.py:597-621` (`_gate`의 차단 분기)
- `xsm/receive.py:1130-1133` (`take_inbox_claims`의 receipt 제외)

**실제 반례**
1. Codex 수신자에게 일반 auto 메시지가 native queue로 정상 도착합니다. canonical 상태는 `state=pending`, `delivery_state=pending`입니다(`send.py:481`).
2. native hook `_gate`가 `check()`에서 traffic이 아닌 이유로 차단합니다.
3. 이 분기는 `hold()`와 `ledger.receipt(held|blocked)`만 기록하고 export를 지웁니다(`:595`). traffic 분기(`:600`)나 take 경로(`:1156`)와 달리 `handoff.delivery`를 바꾸지 않습니다.
4. `take_inbox_claims`는 receipt가 held/blocked이면 이 메시지를 영구히 건너뜁니다.
5. 그런데 새 `pending_ids`는 receipt를 보지 않으므로 이 메시지를 계속 셉니다.

**결과**
- Codex MCP 도구를 부를 때마다 "1 message … before waiting again"이 붙습니다.
- `xsm_inbox wait`와 `xsm inbox --wait`가 매번 바로 끝나고, 돌려주는 메시지는 없습니다.
- 새 instructions가 "대기 전에 inbox를 확인하라"고 안내하므로, 모델이 빈 확인과 즉시 끝나는 대기를 반복할 수 있습니다.
- 이전 코드는 export 수로 셌고 hook이 export를 지웠으므로 0이었습니다. 따라서 이 delta가 만든 회귀입니다.
- 전용 테스트(`test_pending_excludes_failed_delivery…`)는 `delivery_state`를 직접 바꾼 경우만 다루고, 이 경로는 다루지 않습니다.

**필요한 수정 (둘 중 하나)**
- `pending_ids` 또는 `pending_status`에 `take_inbox_claims:1130-1133`과 같은 조건을 넣습니다. 즉 receipt가 held/blocked이고 traffic 재시도 대상이 아니면 제외합니다. `receipt_of`만 읽으면 되므로 읽기 전용이 유지됩니다.
- 또는 `_gate`의 차단 분기에서 `handoff.delivery(me, id, 'held' if stored else 'refused')`를 기록해 take 경로와 맞춥니다.

어느 쪽이든 "hook 차단 뒤 count가 0"인지 보는 회귀 테스트가 필요합니다.

## Low

- **L1 — notice 대상 변경 (`cli.py:2980-2984`)**
  - CLI notice가 `CODEX_THREAD_ID` 대신 `registry.last_identity()`가 확정(sure)일 때만 나옵니다.
  - caller 조회를 하지 않는 명령이나 신원이 확정되지 않은 Codex 호출에서는 이전과 달리 notice가 사라집니다.
  - 반대로 Claude 세션에서는 이제 notice가 나옵니다.
  - 의도된 변경일 수 있지만, 어느 명령이 영향을 받는지는 확인하지 못했습니다.
- **L2 — 옛 export와 진단 (`inbox.py`의 `pending_status` 중 unbound 분기)**
  - receiver도 `codex_home`도 없는 옛 CID export가 있으면 `_import_handoff`가 끝내 채택하지 않습니다. 그래서 count가 계속 null이고 `legacy-receiver-unbound` 진단이 붙습니다.
  - 이전에도 count가 0이 아니어서 대기는 바로 끝났으므로 대기 회귀는 아닙니다. 바뀐 것은 notice 문구뿐입니다. 기록만 합니다.

## 확인한 정상 경로 (근거 위치)

- **오류 판별:** 정확한 문구만 `fullmatch`로 받습니다. 접두어 하나만 허용합니다(`adapters.py:21-25, 210`). 다른 `-32600`, Permission/readonly/Operation not permitted, 여러 줄로 된 오류, 타입이 아닌 문자열, 다른 capability는 모두 기존 error로 남습니다(`send.py:529-555`; 테스트 `test_no_broad_error_fallback`, `test_string_reason_alone…`).
- **sandbox:** wake 대상 Codex의 sandbox 거부는 저장 전에 refused로 끝납니다(`send.py:393`). fallback이 켜지지 않습니다.
- **load/resume/steer와 wake:** native thread를 load·resume·steer하지 않습니다. `queue_direct`와 `wake_codex`도 부르지 않습니다(테스트 `:37-52`).
- **불변성:** wake·identity·digest는 바뀌지 않습니다. route는 레코드 최상위에만 저장됩니다(`handoff.py:194-216`). ACK된 레코드는 갱신을 건너뛰므로 되살아나지 않습니다.
- **수신 검사:** 수신 측 `check()`를 claim 시점에 다시 실행합니다. scope를 회수하면 held로 처리됩니다(테스트 `:204-213`). deny는 전송 전에 refused로 끝납니다.
- **전송 결과:** ledger는 `queued`(`ok=False`)로 남고 `runtime_reached`·`acknowledged`는 false입니다. 질문 상태는 terminal이 아닌 pending이고, `SendResult`는 `stored`입니다.
- **공통 후처리:** reply cache 보관과 `ledger.wait_for`가 fallback에서도 유지됩니다(`send.py:557-576`).
- **legacy export:** export가 유지되고, export가 사라져도 ACK로 처리되지 않습니다.
- **기존 동작 유지:** 명시 `wake=never`는 transport를 시도하지 않고 logical wake=false를 유지합니다. 정상 queue에서 wake가 not-loaded인 경우는 route가 native로 남고 미확정입니다. 이 수정을 wake 성공으로 주장하지 않습니다.
- **pending 집계가 쓰기를 하지 않음:**
  - `pending_ids`와 `status`는 lock·mkdir·recover·claim을 하지 않습니다.
  - 살아 있는 lease는 세지 않고, 소유자가 죽었거나 lease가 만료된 레코드는 셉니다.
  - 다른 home은 `_folder` digest와 receiver 비교로 걸러져 진단에도 나오지 않습니다.
  - ACK된 ID의 낡은 export는 count를 되살리지 못합니다.
- **wait:** claim하지 않고 세기만 합니다. pump·cancel·EOF가 오면 0을 반환하고, 이어서 ChannelError가 납니다(`mcp.py:1027-1032`). 아직 claim 전이므로 풀어 줄 claim이 없습니다.
- **재진입:** `call_owner`를 캡처하고 `dispatch`가 컨텍스트를 저장·복원하므로 정합합니다.
- **count 실패:** 실제 답은 유지되고 `inbox_pending=null`과 진단이 붙습니다. CLI도 "비어 있음"이라고 잘못 출력하지 않습니다.

참고로, fallback 뒤 같은 ID를 명시적으로 `--resend`하면 route가 native로 돌아가 다시 시도합니다. 그때 일반 오류가 나면 원본이 error로 바뀌어 회수 대상에서 빠집니다(`send.py:481, 548`). "다른 오류는 fallback 금지" 규칙과 일치하므로 결함으로 보지 않았습니다.

## Verdict

Medium 1건만 고치고 회귀 테스트를 추가하면 승인합니다. 고칠 곳은 `pending_ids`가 held/blocked receipt를 제외하도록 하거나, `_gate`가 `delivery_state`를 기록하도록 하는 것입니다. 보안 쪽 결함(권한·수신 우회, 잘못된 fallback, ID 변경, ACK 부활)은 찾지 못했습니다.
