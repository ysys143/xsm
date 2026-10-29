# 기존 native subagent 업무 왕복 미완 진단

**최초 질문 두 건은 native queue의 `unloaded spawned sub-agents (-32600)` 거부로 소비 경로에 진입하지 못했다.** 이후 passive note 한 건만 실제 수신·claim·ACK됐고, 그 note에 대한 reply와 새 passive 질문은 상대가 마지막 inbox 조회를 마친 뒤 저장됐다. 실제 질문의 부분/최종 reply는 0건이다. **shared 서버 미확보는 별도 축이며 이 업무 미완의 원인으로 사용하지 않는다.**

기존 raw 29호출·부모/자식 최종 발언·질문/원장/영수증/handoff/첨부 사본과 고정 source만 읽었다. 새 모델·runtime·메타 변경·재전송·상태 보정은 없고 이 Markdown만 추가했다. 시간은 UTC다. F는 `review_five`, Z는 `review_zero`다. F의 MCP는 44002, Z는 44222였다.

## 1. 초기 등록 전 2호출은 별도

| 역할 | 최초 실제 호출 | 실제 등록 setup | 응답 / 본 업무와의 관계 |
|---|---|---|---|
| F | 20:47:13.674, `xsm_discover(work=<작업 폴더 경로>)` | 20:47:13.694 | `unknown / native_filter_unknown`. work는 경로 필터가 아니므로 이 조회를 후보 부재·권한 거부로 해석하지 않음 |
| Z | 20:47:18.063, 같은 형태의 discover | 20:47:18.100 | 같은 unknown. 등록보다 앞선 호출의 확정 caller 판정까지 성공했다고 확대하지 않음 |

둘 다 이후 필터 없는 discover로 후보를 얻었다. 최초 질문은 각각 20:47:32/33으로 실제 등록 뒤다. 질문 원장/사본의 sender·target은 서로 다른 실제 F/Z native CID와 일치한다. 초기 두 호출과 이후 queue 거부를 하나의 실패로 합치지 않는다.

## 2. 요청 ID별 경로

아래 `저장`은 canonical 원문/사본 저장이며 모델 도달·본문 읽기·ACK와 구분한다. token 및 ACK 원시 payload는 옮기지 않았다.

| 요청/메시지 ID | send → 도달 근거 | inbox / claim / ACK | 부분·최종 reply / 질문 인덱스 | 보존된 최종 상태 |
|---|---|---|---|---|
| `ee9446d42af749fd` Z→F, 원 질문+Z 메모 | Z#4, 20:47:32.776, `wait=0`. 원문·첨부 저장 성공; queue/add가 **-32600**으로 거부. `runtime_reached=false` | F inbox 4회 모두 비어 있음. 이 ID의 claim·receipt·ACK 없음 | 부분/최종 reply 0. 질문 인덱스 replies=[]·final=false. Z#6 status도 error | ledger=error; handoff state=pending, **delivery_state=error**, claim 없음 |
| `60a12d9d0f2b4baf` F→Z, 원 질문+F 메모 | F#6, 20:47:33.576, `wait=0`. 같은 queue 거부; 원문·첨부는 저장됨 | Z inbox에는 원 질문이 아닌 뒤의 note만 들어옴. 이 ID의 claim·receipt·ACK 없음 | 부분/최종 reply 0. F#8/#13 status는 error·final=false. `wait=10` 조회도 약 0.061초에 error 반환 | ledger=error; handoff state=pending, **delivery_state=error**, claim 없음 |
| 위 Z 원 ID의 재사용 시도 | Z#12, 20:48:59.137. 동일 ID/body/manifest지만 `wake=never`로 변경 | `request ID content or endpoints differ`로 **refused**. 새 전송·새 claim 없음 | 기존 질문이 성공/회신 상태로 바뀌지 않음. 이 거부 응답 자체는 purpose/recover_at 없음 | 기존 error 레코드는 그대로 보존 |
| `4cc2970a45e54c3f` F→Z, passive 신원/오류 안내 note | F#11, 20:48:34.811, `kind=note,wake=never`; 저장됨. native queue 시도 없음 | Z#10 inbox가 20:48:50.36 무렵 메시지/claim 각 1개 반환. receipt=delivered. Z#11, 20:48:59.073 **실제 ACK** | 아래 `00fb…`가 이 **note**에 답함. 원 수학 질문의 reply가 아님 | handoff=acknowledged. raw ledger의 queued와 별도 receipt/ACK 축을 함께 확인 |
| `00fb13fe6f6c4519` Z→F, note에 대한 reply | Z#13, 20:48:59.244, `kind=reply,reply_to=4cc2970a45e54c3f,wake=never`. 저장 성공 | F의 마지막 inbox는 **20:48:38.936**. 저장 이후 F inbox 호출 없음. claim·receipt·ACK 없음 | outcome 없음. 원 질문 ID를 참조하지 않으므로 그 질문 인덱스의 부분/최종 reply가 아님. 참조 대상 note에는 질문 인덱스 자체가 없음 | handoff pending/delivery pending. 원문 유지 |
| `49179de2df37403e` Z→F, 새 passive 질문+Z 메모 | Z#14, 20:49:07.350, `wake=never`; `stored/pending`, queue 미시도 | F 마지막 inbox보다 약 28초 늦게 생성. 이후 F 소비 없음. claim·receipt·ACK 없음 | replies=[]·final=false. `wait_end_reason=timeout`은 기본 wait=0의 즉시 대기 종료이지 전송 실패가 아님 | ledger queued; handoff pending/delivery pending |

원 질문 두 건의 incoming 첨부 사본도 생성돼 있었지만, **본문 전달이나 상대의 사본 열람을 증명하지 않는다.** 실제 `xsm_files` 4호출은 모두 `outgoing=true`였다. F/Z 각각 자기 manifest와 자기 entry 내용을 읽은 것이며 상대 자료 교차 열람은 없었다.

## 3. 확인된 직접 원인과 아닌 것

### A. native 전송 제약 — 실제 관측

두 최초 ask의 결과는 약 0.3/0.5초 만에 다음 오류를 반환했다.

> direct app-server input is not allowed for unloaded spawned sub-agents (code -32600)

이는 실제 native app-server의 queue/add 제한이다. **OS EPERM, 사용자 승인 거절, 프로젝트 scope/deny 거부가 아니다.** 이번 29호출에 그런 OS/업무 권한 거부는 관측되지 않았다. `not-loaded` wake 결과와도 구분한다. 여기서는 queue/add 자체가 실패했고 별도의 wake 성공/실패를 그 오류 대신 사용하지 않는다.

MCP JSON-RPC의 `isError=false`는 모두 성공이라는 뜻이 아니다. 실제 내부 결과에는 초기 ask의 `status=error`와 뒤의 wake 변경 `status=refused`가 있다. 이전 요약의 startup/provider/tool-host 준비 실패 0은 이 실제 **업무 전송 오류 2건**을 없애는 근거가 아니다.

### B. 보존된 error 원문이 inbox에 안 나온 이유 — 기록과 source가 일치

[`send.py:526`](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/send.py:526)는 전송 오류를 canonical handoff의 delivery_state=error와 ledger error에 기록하고 legacy export를 제거한다. [`handoff.py:260`](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/handoff.py:260)의 claim은 state=pending이면서 **delivery_state가 pending/delivered인 것만** 선택한다. 따라서 두 원문이 디스크에 남아 있어도 이 조건의 일반 inbox가 claim하지 않는 현상은 현재 코드와 일치한다. 원문 삭제나 잘못된 receiver ownership으로 설명할 증거는 없다.

이는 재현된 **native subagent 기본 queue 경로/오류 후 회수의 통합 공백**이다. 모든 error를 자동 claim하도록 바꾸라는 뜻은 아니다. 권한 실패 등 다른 오류까지 우회하면 안 되며, 이 표본만으로 안전한 수정 정책을 확정하지 않는다.

### C. wake 변경 거부 — 현재 immutable 요청 계약과 모델 선택 마찰

[`questions.py:239`](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/questions.py:239)는 auto 이외 wake를 질문 identity에 넣고, [:245](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/questions.py:245)에서 기존 digest와 비교한다. Z가 같은 ID를 `wake=never`로 바꾼 시도는 현재 계약상 다른 요청이라 거부됐다. 잘못된 상대·home으로 바뀌었다는 관측은 없고, 실제 바뀐 인자는 wake다.

Z의 뒤 note-reply에는 같은 ID를 wake never로 재사용했다고 적었지만, 그 직전 실제 결과는 refused였다. **시도와 성공을 혼동한 중간 설명**이다. Z 최종 발언은 이 거부를 정확히 인정했다. guide/모델의 실패 복구 경로 마찰로 기록하며 digest 검사를 깨진 권한 검사로 단정하지 않는다.

### D. 양쪽 동시 ask 대기 교착은 확인되지 않음

원 ask 두 개 모두 `wait=0`이어서 대기 교착이 아니라 즉시 error였다. 이어진 두 inbox wait(30초/40초)는 실제 빈 결과였다. 실패 원문의 delivery_state=error가 claim 대상에서 제외된다는 원인이 별도로 확인된다. F의 question-status(wait=10)도 error가 terminal이라 즉시 끝났다([`questions.py:174`](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/questions.py:174)).

passive note는 Z의 30초 inbox wait 도중 저장됐으나 반환은 wait 만료 때였다. [`inbox.py:142`](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/inbox.py:142)는 legacy export 수를 기다리고, MCP는 그 뒤 claim한다([`mcp.py:1021`](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/mcp.py:1021)). no-wake 원문에는 export가 없어 이 지연은 현재 경로와 부합한다. 다만 note는 실제 수신·ACK됐으므로 이것만으로 전체 실패를 설명하지 않는다.

### E. 후기 passive 메시지에는 더 이상 상대 소비가 없었음

F는 마지막 inbox를 20:48:38.936에 호출하고 **20:48:58.317**에 최종 보고했다. Z의 note-reply는 약 0.9초 뒤인 20:48:59.244, 새 질문은 20:49:07.350에 저장됐다. 따라서 이 두 메시지의 미수신은 이후 F 소비가 없다는 기록으로 설명된다. 저장 실패나 인덱스 손상이라는 증거는 없다.

Z는 20:50:10.603 최종 발언에서 부모 종료 지시에 따라 대기를 끝냈다고 말했다. 부모의 native `send_message` 호출은 20:49:41에 있지만 그 인자의 본문은 보존 로그에서 opaque 문자열이므로 본 대조에서 지시 내용까지 독립 확정하지 않았다. 부모 최종 발언은 20:50:22.662이고 평가 run은 **20:50:23에 native completed, cleanup signal 없음**으로 끝났다. 평가기의 20분 상한이나 강제 종료가 업무를 잘랐다고 볼 근거는 없다. native 작업자의 completed/대기 종료는 xsm 질문의 final/outcome/ACK 종결과 별개다.

## 4. 부모·자식 최종 발언과 질문 인덱스

| 발언 주체 | 실제 최종 발언의 요지 | 기록 대조 |
|---|---|---|
| F | queue 오류·실제 답/상대 메모 미확인·inbox empty·ACK 없음 | 원 질문 error, reply 0과 일치. 자기 사본 읽기를 상대 열람으로 주장하지 않음 |
| Z | note 수신/ACK, wake 변경 거부, 직접 reply와 새 passive 질문 저장; 상호 확인 미완 | note ACK 1건과 일치. 두 후기 메시지의 상대 수신은 없음 |
| 부모 | 독립 산술 검토는 수행했으나 실제 질문/메모 교차 확인은 미완 | 전체 미완 판단은 맞음. 다만 모든 미응답 기록을 pending이라고 뭉뚱그리면 안 됨: 원 질문 2건은 공개 status=error, 새 passive 질문만 pending |

[`questions.record_reply:302`](/private/tmp/xsm-p13-postqa-frozen-bukwksw6/xsm/questions.py:302)는 검문된 `kind=reply`와 해당 질문의 reply_to가 필요하다. 관측된 유일한 reply는 note ID를 가리키며 상대가 읽지도 않았다. **질문 인덱스 replies=0은 현재 입력과 일치**한다. 인덱스가 실제 도착한 원 질문 reply를 잃었다는 재현은 없다.

## 5. 확인에 필요한 수정 제안의 범위만

1. **제품 adapter/회수 경계:** unloaded spawned subagent의 queue/add -32600, 보존 handoff delivery_state=error, 일반 inbox 미회수까지가 실제 재현이다. 영향은 이 native subagent 조건에서 기본 auto-wake 질문과 오류 후 원 ID 회수다. native 일반 세션 전체·권한 오류 전체로 확대하지 않는다. subagent 능력 판정과 명시적 안전 회수/대체 경로가 필요한지 검토하되 전체 error를 무조건 소비시키거나 새 ID 자동 재전송으로 고치지 않는다.
2. **guide/결과 안내:** `work`에 경로를 넣은 초기 discover 마찰, wake를 바꾸면서 같은 ID를 유지하려 한 거부, 저장을 전송 성공으로 읽기 쉬운 표현을 실제 사례로 보완할 수 있다. 기존 요청 계약을 바꾸려면 별도 설계·재현이 필요하다.
3. **모델 업무 수명:** F가 최종 보고한 뒤 Z가 답/새 질문을 저장한 시간차가 재현됐다. 독립 검토 완료와 상호 수신 완료를 분리해야 한다. 이는 shared-MCP 유무로 설명하지 않는다.

현재 source·guide·메타·상태·기존 요약은 수정하지 않았다. 새 실행 없이 이 관측의 원인/영향 범위만 제안한다.

## 근거 위치

- 원 호출: `/private/tmp/shared-mcp-native-yjfl3mjl/proxies/44000-c68b12b2/{client-wire,server-wire,events}.jsonl`의 F #2–15, `44220-393c36eb/`의 Z #2–16. 합계 14+15=29다.
- 각 ID의 `state/questions/<id>.json`, `state/ledger/<id>{,.recv}.json`, `state/handoffs/<receiver-hash>/<id>.json`, `state/file-copies/`를 함께 대조했다.
- 부모/자식 발언: 같은 root의 `native.jsonl`, `native-rollouts/` 사본과 `native-rollout-manifest.json`의 원 경로/hash. 원문을 다시 쓰거나 token을 공개 문서에 복사하지 않았다.
