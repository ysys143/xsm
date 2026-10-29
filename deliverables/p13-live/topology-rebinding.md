# A22-04 topology 재결속

판정: **부분 — 실제로 승인된 서로 다른 repository native 쌍 1셀만 미확보**. 일반 N:N·형제·다른 부모의 직접 통신 성공은 보존하며 준비 fixture를 native로 세지 않았다. 기준 source는 `/private/tmp/xsm-doctor-privacy-v2-frozen-i7xbamec`이고 primary135/manifest 일치를 확인했다. 현재1700 양Python OK는 별도 회귀 근거다.

원criterion은 “부모 없는 일반 세션, 형제 워커, 다른 저장소 동료가 승인 범위 안에서 직접 소통한다.” positive에는 다른 부모도 포함되고 negative는 부모 계보를 통신 허용 근거로 강제하는 것이다. evidence는 harness/native다. shared MCP·모든 하네스·장시간부하는 추가하지 않았다.

| 셀 | 실제 근거 | 판정 |
|---|---|---|
| 일반 N:N | P09 실제 provider source=exec 2CID, 직접3round의 원reply_to/양쪽ACK/final. 후속 frozen postclaims math3·handshake1·답ACK4와 원로그SHA | 성공 유지. P09 cli/mcp drift를 uniform source 성공으로 부르지 않음 |
| 형제 | 완료된 subagent-followup 실제 parent1/child2, 같은 provider parent·서로 다른 CID/cwd 기록·동일 Gitcommon, direct final3·canonical8/실제ACK8 | positive 재사용 가능. 초기 shared 표본 미완으로 후속 성공을 지우지 않음 |
| 다른 부모 | 실제 parent2/child2, 각각 다른 provider parent_thread_id, 같은 Gitcommon, 직접 final3·canonical8/실제ACK8 | 현재 통신 함수/ABI 동일한 positive 재사용 가능 |
| 승인 연결폴더 / 다른 repo | G02 실제 사용자 승인·link scope·request/reply delivered·원reply_to 일치. 역사적 두 native endpoint CID/cwd와 distinct Gitcommon 결속 없음 | 연결폴더 성공은 유지. distinct repository 셀 전체는 미확보 |

형제 manifest152파일·다른부모168파일의 SHA를 대조했다. 실제 xsm_ack 요청 token과 canonical claim·metadata CID와 receiver를 함께 검사했고 [JSON](topology-rebinding.json)에 ACK별 boolean/hash·원파일SHA를 남겼다. provider parent는 표시이름/공유PID로 추정하지 않고 기록된 native source.thread_spawn을 대조했다. 원 token은 공개하지 않았다.

G02 임시 폴더는 현재 비어 있으나 현재 .git 부재를 과거 repository 부재로 단정하지 않는다. 반대로 폴더명/link scope만으로 distinct repository라고 할 수도 없다. G02-LIVE-ACK는 답 본문이며 현대 claim ACK 증거가 아니다. 실제 승인·직접회신을 부정하지 않고 **서로 다른 Gitcommon native 쌍의 증거 missing**만 남긴다.

## source/ABI 차이

- 다른 부모 표본(final1697)과 현재는 비교한 config/send/MCP/receive/handoff/questions/envelope/abuse/provenance/adapters/inbox/CLI 함수 AST/ABI가 동일하다. privacy install.stuck/worker fixture 수정은 해당 경로와 별개다.
- 형제 표본(native-integration) 이후 비교 함수 차이는 handoff.pending_ids의 held/blocked receipt 제외뿐이다. positive canonical8/receipt는 그 음성 분기에 해당하지 않는다. 이를 음성 guard 실측 성공으로 확대하지 않는다.
- 일반 frozen postqa 이후 handoff.delivery에 optional route=None, _send에 exact typed unsupported fallback, passive inbox route 허용, MCP pending notice/finite cancellable wait가 추가됐다. 정상/quiet 원 ID/digest/reply_to/claim/ACK ABI는 유지되고 config scope·봉투·수신 gate·질문 상관 함수는 그대로다. 새 fallback 실행을 과거 일반 native가 증명했다고 하지 않는다.

JSON은 source별 변경 함수의 line·AST SHA·signature와 file SHA, 원 raw/hash 및 endpoint 역방향 reply/ACK를 결속한다. 준비 test_peer_roundtrip은 보조 fixture뿐이다. 현재1700의 no-broad-fallback·scope-revoked·deny-before-send·held/blocked-pending 반례 selector는 기존 근거로만 인용했고 실행하지 않았다.

P09 source drift, 초기 shared-MCP 미확보, 형제 최초 FileNotFoundError, profile drift writer unknown, G02 hardening 전/legacy receipt 한계를 보존한다. 확인 범위를 넓혀 새로운 실험이나 원문 없는 행렬을 만들지 않았다. **전체 A22-04 완료는 보류하되 남는 셀은 distinct-repository 승인 native 쌍 하나다.**

새 모델·승인·실험·제품/script/plan/ledger/기존 artifact 수정은0이며 요청 JSON/Markdown만 작성했다.

시간 제한: 요청10분을 약36초 초과했다. 추가 조사는 중단했으며 확인한 범위와 위 missing1셀로 종결했다.
