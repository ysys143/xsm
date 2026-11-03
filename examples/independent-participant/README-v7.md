# 독립 v7 후속 — 595d784 공개 packet

현재 Python 3개는 새 공개 action 계약에 맞춘 후속 구현이다. 원래 cf01 제출은 부모가 `b027a4d`에 보존했다고 알렸으며, 아래 원래 제출 기록과 이번 후속 결과를 분리했다. 이번 작업에서 이전 입력·결과나 부모 계획 문서는 다시 읽지 않았다.

## 후속 실행

```sh
python3 -B examples/independent-participant/verify_v7.py   --operator deliverables/protocol-foundation/independent-v7-followup/operator.json   --output deliverables/protocol-foundation/independent-v7-followup/agent-results/새로운-실행-디렉터리
```

검증기에는 개발 의존성 `jsonschema`가 필요하다. Consumer/Transport 본체는 stdlib만 import하며 공개 schema validator를 명시적으로 주입한다. 실행 파일은 operator.json에서만 선택하고 backend/SDK/native/model/외부 네트워크를 호출하지 않는다. 서버 프로세스는 기존과 같은 격리 환경을 사용하며 owned는 명시적 model0 fixture에서만 실행한다. 자동 ACK와 mutation retry는 추가하지 않았다.

## 이번 변경

- `participant_v7.py`: 원래 operation/action에 따라 `x-actionResults`를 선택한다. action 생략은 공개 input catalog의 `default` 또는 결과 schema의 `x-defaultAction`으로만 해결하며 둘이 다르면 거부한다. 명시적 null과 원래 arguments 유실은 default로 간주하지 않는다. 결과 body에서 action을 추측하지 않는다.
- owned status는 원래 `request_id`가 없으면 `requestListing`, 있으면 `taskResult`를 추가 적용한다. 제공된 request_id와 다른 task도 거부한다. facts의 `result_kind`는 service/history/task를 구분한다.
- `verify_v7.py`: 예제 action annotation을 보존하고 원본 annotation과 비교한다. status 예제에 원래 request_id annotation이 없는 경우에만 결과 id를 검증용 context로 공급하며 `inferred_context`에 명시한다. 이를 원래 request 또는 실제 실행 증거로 취급하지 않는다.
- `local_v7_fixtures.py`: root union에는 유효하지만 원래 action에는 맞지 않는 owned service/listing/task 및 handover show/applied/pending/legacy 조합을 만든다. 이들은 로컬 합성 결과 소비 검사이며 실제 서버 실행 수에 포함하지 않는다.

`Consumer.operation`은 원래 arguments dict를 요구한다. `{}`는 호출자가 실제로 인자를 생략했다는 뜻이며 수집기가 원래 인자를 잃어버렸다는 뜻으로 대체해서는 안 된다. `Consumer.action`은 검증과 실제 action coverage 집계에 동일하게 사용된다.

## 이번 검증 결과

실제 명령은 위 output을 `followup-20261103-a`로 지정했으며 exit 0이다. 새 frozen server와 owned/error fixture를 사용했다.

| 범주 | 결과 |
|---|---:|
| 독립 정상 서버 시나리오 | 1/1 통과 |
| 독립 owned/error model0 시나리오 | 2/2 통과 |
| 공개 검사기 | 19/19 suite, 584개 검사 통과 |
| 실제 서버/fixture RPC | 751회 |
| 실제 결과를 소비한 표면 | operation 22/22, action 30/30, wire method 16/16 |
| 공개 예제/fragment | 132/132 통과 |
| 기존 잘못된 응답/의미 변이 | 188/188 거부 |
| 추가 action/default 양성 | 17/17 통과 |
| 추가 action/default 음성 | 23/23 거부 |
| 명시적 예제 action annotation 보존 | 42/42 통과 |
| 고의 구현 변이의 검사 민감도 | 2/2 통과 |
| 새 공개 schema checker | exit 0, 742 observation 통과 |

추가 action 검사는 root-valid 조합 37건에 catalog-only/result-schema-only default 수용 2건과 상충 default 거부 1건을 더한 40건이다. owned run의 listing/create 결과 거부, create의 task 거부, status의 history/exact 혼동 거부, handover default의 applied/pending/legacy 수용 및 show 거부, 명시적 show의 applied/pending 거부를 포함한다.

검사 민감도 2건은 기존 validator 제거 변이와 이번 root-only selector 변이다. 후자는 owned run에 listing을 넣었을 때 거부해야 하는 검사가 실제로 실패함을 확인하고 `deliberate-root-only-failure.json`에 예상 assertion 실패와 반환 facts를 저장했다.

원시 요청/응답을 추가 감사한 결과, 실제 handover action 생략 결과 3건, owned status history 결과 1건과 exact 결과 6건을 확인했다. 로컬 양성/음성 검사와 별개의 실제 실행 증거다. `followup-audit.json`에 집계를 보존했다.

본 검증 407개 로컬/독립 check와 공개 584개 check의 예상 밖 실패는 0건이고 operation/action 누락도 0건이다. 공개 검사 수에는 공통 lifecycle 검사가 suite별 반복된다. 독립 시나리오 내부의 여러 RPC/assertion을 별도 시나리오로 세지 않았다.

후처리 감사 도구의 첫 실행은 고의로 잘못된 JSON batch를 dict로 읽어 AttributeError로 실패했다. `audit-first-attempt-failure.txt`에 보존했고, non-object local frame을 제외한 수정 감사만 재실행했다. 참여자/검증기 실행과 공개 checker는 이 오류와 별개로 이미 통과했다. 민감도 검사의 의도된 실패 2건도 실제 검증 실패와 분리했다.

## 후속 입력 출처와 남은 한계

- source commit: `595d78410840ad8386b3767e7c696401a9a4bfd7`
- manifest SHA-256: `51280af9448961c367d94ea384981d0abdf843f2f857445f0222ad239efca89b`
- 공개 입력 파일 64개 SHA-256: 전부 일치
- operator archive SHA-256: `0a1d5e64d8f2d1b84e44ffa7b091aed6190c3d81ef5762b274c1b7fc0e791781` (운영자 제공 값; archive/실행 파일 소스는 읽거나 재검증하지 않음)

Python 3개의 최종 hash는 실행 시작 때 저장한 `implementation-hashes.json`과 모두 일치한다. transport 원시 stdout/stderr/stdin/wire, 예제/negative 입력, action 관측, 예상 실패, suite 보고서 및 checker stdout/stderr를 새 결과 디렉터리에 보존했다. 부모의 다른 파일을 수정하거나 커밋하지 않았다.

새 공개 문서는 원래 지적했던 method 16개, owned run의 nonempty text/work_context 조건과 owned/handover action selector를 명시한다. status 결과 schema의 union은 원래 request_id에 의한 listing/exact 분기를 자체적으로 표현하지 않으므로 소비자에서 공개 문서 조건을 추가 적용했다. 예제에 원래 request_id가 없는 한계는 위와 같이 검증용 context 표시로 남겼다. 실제 인자가 유실된 trace를 action 인증 자료로 사용하지 않는다.

실제 LLM/model/native 실행·UI·lifecycle·실행 중 취소·gateway 재시작 복구·Linux·외부 network/messenger는 이번에도 미실행·미완이다. owned 결과/취소/복구 관측은 operator의 model0 fixture 범위이며 native 인증을 뜻하지 않는다.

상세 증거: [summary.json](../../deliverables/protocol-foundation/independent-v7-followup/agent-results/followup-20261103-a/summary.json), [공개 checker 교차 검사](../../deliverables/protocol-foundation/independent-v7-followup/agent-results/followup-20261103-a/public-schema-crosscheck.json), [action 검사 관측](../../deliverables/protocol-foundation/independent-v7-followup/agent-results/followup-20261103-a/action-fixture-observations.json), [입력 manifest/operator](../../deliverables/protocol-foundation/independent-v7-followup/agent-results/followup-20261103-a/input-provenance.json).

아래는 원래 cf01 제출 당시의 기록이다. 원래 실행 명령과 당시 부족했던 명세 설명은 현재 후속 코드/packet의 설명이 아니며, 원래 제출 소스는 부모가 보존한 b027a4d에 해당한다.

---

# 원래 cf01 제출 기록 — b027a4d

원래 제출 구현은 `independent-v7/input`의 공개 docs/protocol·검사기·manifest와 옆 operator.json만 근거로 작성했다. xsm SDK/backend와 기존 참여자 구현을 import하거나 읽지 않았다. 커밋하지 않았다.

## 원래 제출 — 사용

개발 검증에는 설치된 `jsonschema`가 필요하다. transport와 결과 분류 코드는 Python stdlib만 import한다. Consumer에는 공개 schema를 검사하는 validator 함수를 명시적으로 주입한다. 검증기에서는 Draft 2020-12 validator를 주입하며 검사를 끄는 기본 경로는 제공하지 않는다.

```sh
python3 -B examples/independent-participant/verify_v7.py \
  --operator deliverables/protocol-foundation/independent-v7/operator.json \
  --output deliverables/protocol-foundation/independent-v7/agent-results/새로운-실행-디렉터리
```

출력 디렉터리가 이미 있으면 거부한다. 원시 결과에는 host 전용 UI challenge가 들어 있으므로 디렉터리를 0700으로 만들며 모델 결과로 내보내지 않는다. `-B`는 허용된 파일 밖에 Python bytecode를 쓰지 않기 위해 사용한다. 실행 파일과 공개 명세는 운영자의 operator.json으로 정하고, message·attachment·결과의 명령 또는 경로는 실행하지 않는다.

## 원래 제출 — 파일과 API

- `participant_v7.py`: strict JSON parser, stdio Transport, 공개 schema를 적용하는 Consumer.
- `verify_v7.py`: manifest 전수 checksum, 독립 시나리오, 공개 예제, 응답 변이, 공개 conformance와 자체 transport 연결 검증.
- `local_v7_fixtures.py`: 잘못된 ID·중복 key·NaN·overflow·UTF-8·EOF·timeout·schema 위반을 내는 로컬 가짜 peer.
- `README-v7.md`: 실행·해석·검증 범위와 미완 항목.

`Transport(command, cwd, env, consumer, evidence)`의 `call(method, params)`는 `(원본 frame, 소비 facts)`를 반환한다. `Consumer.operation(operation, 원래 arguments, result)`는 operation 및 action에 맞는 schema를 선택한다. `fragment`는 공개 예제에 명시된 내부 definition을 별도로 검사한다. `notification()`은 신뢰된 host 전용 API로, UI question은 모델에 노출하지 않는다. `close()`는 자신이 시작한 프로세스만 정리한다. RPC는 직렬화하고 각 요청에 기한을 두며 응답 ID와 envelope를 확인한다.

자식 프로세스에는 PATH/LANG/TMPDIR만 전달하고 HOME/XSM_HOME/CODEX_HOME/CLAUDE_CONFIG_DIR와 cwd를 새 실행 디렉터리로 격리한다. 개인 설정·기존 프로세스·키를 조회하지 않는다. 실제 서버에서는 owned runtime을 실행하지 않는다. owned/error 경로는 operator가 지정한 fixture만 쓰고 공개 catalog의 model0/fault marker를 확인한다.

## 원래 제출 — 의미 구분

text-only 결과는 `legacy-unconfirmed`, UI 질문은 `pending-human`이다. 공개 notification을 검증한 뒤 Consumer.frame은 challenge가 없는 최소 facts만 반환한다. 답의 저장과 원래 operation의 명시적 재호출에 따른 적용을 분리한다. 자동 승인·자동 ACK·mutation 자동 재시도는 없다. 검증 시나리오의 synthetic host 응답은 실제 사람의 승인 또는 native UI 증거가 아니다.

scope receipt는 변경 직후 snapshot이며 현재 권한을 증명하지 않는다. team/board snapshot, DM mute, board notice mute, sync 시도와 실제 전달을 구분한다. send의 storage·native admission·canonical ACK·업무 outcome은 서로 다른 관측이다. owned task의 상태, result outcome, reply ID/transport와 cancellation observation을 별도 필드로 보존한다. error는 rollback 또는 재시도 안전성을 보장하지 않는다.

inbox item/claim association, scope kind/removal count, material manifest binding, question final/history/handshake/group aggregate, network reply/packet/file binding, decision digest/native-question/application observation과 handover action도 확인한다. 일반 error object 및 attachment_error를 공개 schema로 검증한다.

## 원래 제출 — 실행 증거와 합성 검사의 분리

`summary.json`의 publicSuites는 공개 검사기가 작성한 시나리오를 **이 구현의 Transport/Consumer**로 실행한 결과다. 이것을 독립적으로 작성한 시나리오 수에 합치지 않는다. 독립 시나리오는 다음 세 개이며 각 시나리오 안에 여러 RPC와 assertion이 있다.

1. 정상 frozen server: UTF-8 FYI 저장, 실제 원문 확인, claim release와 새 token 재인수, 명시적 ACK, 문서 add/show, synthetic answer 저장과 publication 적용 분리, 같은 conversation 재등록의 address/generation.
2. model0 owned fixture: logical create, queued/not accepted, 실행 전 cancellation/not-started, 저장된 answer/outcome/reply, retry/reconcile의 reply ID·결과 보존.
3. error fixture: 문서 write 뒤 -32603, 자동 mutation replay 없이 log/show에서 단 하나의 durable node 복구.

공개 예제는 실행 증거가 아니다. local peer의 잘못된 응답과 의미 변이는 deliberate-mutant 범주에만 센다. validator를 고의로 제거한 consumer가 잘못된 결과를 통과시키면 원래 acceptance assertion이 실패하는지도 실행하고 그 예상 실패를 별도 JSON에 저장한다.

각 peer의 stdin.raw/stdout.raw/stderr.raw/wire.jsonl, 공개 suite 보고서, 예제 및 변이 입력, 중간 checks, 원본 manifest/operator와 입력 hash 판정을 보존한다. 초기 검증기 오류와 실패 실행도 남긴다. `missingOperations`/`missingActions`는 성공 결과를 실제로 소비한 표면을 기준으로 산출하며 누락 또는 검증 실패 시 최종 CLI는 exit 1이다.

## 원래 제출 — 명세 부족과 미완

- `xsm_owned.run`은 공개 input schema에서 `work_context`가 필수가 아니지만 독립 실행에서 누락 시 `-32602: explicit work_context required`로 거부됐다. 구조 검사와 domain 검사의 차이는 공개 문서가 설명하지만, 이 구체적인 필요 조건은 operation 설명/schema에서 드러나지 않는다. 명시적 context를 넣어 후속 시나리오를 검증했다.
- 공개 README의 describe 절은 wire method 11개라고 쓰지만 request/output schema의 method mapping은 16개다. operations-contract의 과거 검증 수 21개도 현재 catalog 22개와 구분해서 읽어야 한다.
- action별 result mapping은 team/board/doc에 명시돼 있다. owned/handover는 공통 union이며 action-result 결합을 완전히 기술한 별도 mapping은 없다. 구현은 handover action과 owned create/task 혼동을 추가 거부하지만 모든 domain 전이를 증명하지 않는다.
- schema 구조 검증은 현재 권한·서명/진위·파일 bytes/digest 전체·TTL·네트워크 membership·native 실행 증거를 인증하지 않는다. 공개 문서 자체도 이 한계를 명시한다.
- 실제 native UI, 실제 모델, Claude/Codex/Hermes/Pi/OpenCode/OpenClaw의 native lifecycle/실행 중 중단/재시작 복구, Linux와 remote/messenger 표면은 **미완·미실행**이다. owned 실행·출판·취소 증거는 명시적 model0 fixture 범위에 한정된다. macOS local stdio 결과를 native 인증으로 일반화하지 않는다.

초기 실패는 verifier의 상대 HOME, 공개 fragment 분류, schema에 없는 publication 인자, 함수 인자 충돌, 의미 변이 생성기의 scope 오분류, owned context 누락이었다. 해당 원시 결과를 보존했고, 최종 검증 결과와 섞지 않는다.

## 원래 제출 — 최종 검증 결과

최종 명령은 위 실행 명령의 output을 `deliverables/protocol-foundation/independent-v7/agent-results/v7-independent-20261103-f`로 지정했다. exit 0이며 peer stderr와 실패를 포함한 앞선 실행 디렉터리 a–e도 보존했다. 최종 실행 후 implementation-hashes.json과 Python 소스 3개의 SHA-256이 모두 일치함을 확인했다.

| 범주 | 결과 | 증거 |
|---|---:|---|
| 독립 정상 frozen server 시나리오 | 1/1 통과 | summary.json의 independent-real-server |
| 독립 owned/error model0 시나리오 | 2/2 통과 | independent-model0-fixture |
| 공개 검사기 시나리오 | 19/19 suite, 584개 검사 통과 | public-*.json |
| 공개 예제·내부 fragment | 132/132 통과 | published-example; 실행 수에 포함하지 않음 |
| 잘못된 응답·의미 변이 | 188/188 거부 | deliberate-mutant; 16종 실제 로컬 peer 포함 |
| 검사 민감도 | 1/1 통과 | deliberate-disabled-validator-failure.json에 예상 assertion 실패 보존 |
| 공개 schema checker 교차 검사 | exit 0, 742개 observation | public-schema-crosscheck.json 및 원시 stdout/stderr |

최종 서버/fixture RPC는 751회다. 22/22 operation, 선언된 action 30/30, wire method 16/16의 성공 결과를 소비했다. observation 수에는 notification과 error가 포함되므로 RPC 또는 assertion 수와 다르다. 공개 검사기의 검사 수에는 공통 lifecycle 검사의 suite별 반복이 포함된다. 독립 시나리오 3개를 assertion 3개보다 더 큰 수로 부풀리지 않았다.

| action 있는 operation | 실제 결과 소비한 action |
|---|---|
| xsm_owned | cancel, create, reconcile, retry, run, status |
| xsm_team | add, create, lead, leave, list, mute, remove, show, unmute |
| xsm_handover | hand_over, show |
| xsm_board | decisions, log, mute, set, show, sync, unmute |
| xsm_doc | add, leaves, log, next, render, show |

최종 실패 0건, operation/action 미실행 0건이다. 앞선 실패는 b의 예제 오분류 4건·독립 인자 오류 1건, c의 함수 인자 충돌 1건, d의 변이 생성 중 KeyError, e의 owned context 거부 1건이며 a의 초기 상대 HOME 거부도 기록했다. 이 실패들을 최종 통과 수에 포함하지 않았다. 실제 native 및 Linux 등 위 미완 표면은 여전히 미완이다.

입력 출처:

- source commit: `cf01df596367768b35a4f7fe060e3d70e78f8eb9`
- manifest SHA-256: `2cbb4244c05811a7abcb83869fcde8aa5b340e80cfb375320752a81743368098`
- manifest의 공개 입력 64개 파일 SHA-256: 전부 일치
- operator archive SHA-256: `f5493aa7d94f5b389fc80f749f5b15ca2f5eed98cb7d453ca266ff7e2235b535` (운영자 제공 값이며 실행 파일 디렉터리나 archive를 읽어 재검증하지 않음)

상세 결과: [summary.json](../../deliverables/protocol-foundation/independent-v7/agent-results/v7-independent-20261103-f/summary.json), [공개 schema 교차 검사](../../deliverables/protocol-foundation/independent-v7/agent-results/v7-independent-20261103-f/public-schema-crosscheck.json), [입력 출처](../../deliverables/protocol-foundation/independent-v7/agent-results/v7-independent-20261103-f/input-provenance.json).

되돌릴 때는 이 작업에서 만든 Python 3개와 README-v7.md만 작업 대상에서 제외하면 된다. 원시 결과 디렉터리는 실패 증거 보존 대상으로 남겼으며 자동 삭제하지 않았다.

## 원래 제출 — 부모 재실행

제출된 Python3개 checksum을 대조한 뒤 부모가 수정 없이 같은 frozen source에서
`parent-results-cf01`로 재실행해 exit0을 확인했다.22개 operation/30개 action의
미실행0개, 공개19개 suite/584개 검사와 독립3개 시나리오를 통과했다. 별도 공개
schema checker도742개 observation을 검증했다. 원시와 해석은
[부모 검증 기록](../../docs/plan/runtime-protocol/independent-v7.md)을 따른다.
