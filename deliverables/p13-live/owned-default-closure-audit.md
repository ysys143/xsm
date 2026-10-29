# A16-06 / A23-06 기본 owned 경로 증거 종결 감사

A16-06의 일반/owned 후속 대조는 기존 실제 Codex 표본으로 충족한다. A23-06의 기본 공개 구성 전체 종결은 보류한다. 공개 MCP를 통한 기본 owned Codex 실행·회신·기억은 이미 존재하며, 이를 private API만의 표본이나 `serve` 미실행으로 지우지 않는다.

제품·ledger·plan을 바꾸지 않았고 네트워크·새 모델·시험 runner를 실행하지 않았다. 요청된 감사 JSON/MD만 작성했다. 아래는 당시 표본 판정이며 현재 통합 revision 전체 통과 선언이 아니다.

## 판정 근거

- ADR-0016 A16-06과 acceptance는 일반/owned 각각 후속 질문·native ID·기억·권한 대조를 요구한다. 두 런타임 전수 행렬이나 특정 `serve` 명령 철자를 요구하지 않는다. 퇴출 뒤 기억 소실은 A16-08이다.
- ADR-0023 A23-06은 기본 구성의 MCP·실제 회신·후속 문맥·권한과 보정 조건을 구분한다. 설치된 기본 MCP와 임시 `xsm_eval` 주입을 동일하게 처리하지 않는다. shell `owned` 미실행은 관측 사실이나, 공개 MCP 실행까지 미실행이라는 뜻은 아니다.

| 기준/측면 | 판정 | 근거 |
|---|---|---|
| A16-06 / 일반/owned 각 2턴·native ID·기억 대조 | satisfied-observed-codex-pair | 일반 Codex와 owned Codex가 별도 native ID로 각각 2턴을 실행했고 각 경로 안에서 같은 ID·기억을 유지했다. 일반 Claude까지의 전수 행렬은 증명하지 않는다. |
| A16-06 / owned Claude native memory | satisfied-with-reply-adjustment | 기억·native ID·default permission은 raw로 확인. quiet callback의 전송 보정은 이 기억 판정 자체를 무효화하지 않으며 기본 회신 성공으로 확대하지 않는다. |
| A23-06 / public owned MCP default executor, actual reply, followup | satisfied-observed-codex-with-fixture-wiring | 공개 xsm_owned 실제 3회 호출, child 기본 argv, 기본 reply callback, 원 request/reply ID와 실제 반환 본문 확인. native queue delivery runtime_reached=false와 MCP 결과 반환 성공은 별개다. |
| A23-06 / installed default MCP wiring without eval override | not-demonstrated | producer가 xsm_eval command/args/env 및 임시 snapshot/state를 -c로 주입했다. 격리 fixture이지 권한 확대는 아니지만 설치 기본 MCP 선택·연결 검증으로 재분류할 수 없다. 이 보정이 실패를 수리한 것인지는 증거 없음. |
| A23-06 / actual shell xsm owned create/run default entry | not-executed-in-reviewed-native-evidence | cmd_owned는 같은 함수로 연결되지만 두 producer는 Python 직접 호출/공개 MCP 호출이다. 기존 CLI 시험 소스는 executor/reply mock을 사용한다. shell 실행 공백은 존재하되 serve라는 철자 부재가 공백의 이유는 아니다. |
| A23-06 / Claude default owned reply without quiet callback | not-demonstrated | native-memory producer는 private _reply_owned(wake=False)를 명시 주입했다. 실제 Claude MCP inbox 성공과 2턴 기억은 존재하지만 기본 reply 경로 표본은 아니다. |
| A23-06 / permission posture and ownership boundary | partial | 실제 argv에 Claude default/Codex never+workspace-write, Claude denial=[]; owner와 child native ID 분리 확인. profile 설정 전체의 당시 정본·native 금지 동작/타 owner 거절은 이 raw에 없다. hook permission_mode=bypassPermissions를 native 권한 확대나 승인 증거로 쓰지 않는다. |
| A16-06/A23-06 / eviction-memory and task finality requirements | not-a-blocker-for-memory-comparison | 퇴출 후 기억 소실은 A16-08 별도 기준이다. 두 번째 child outcome=null은 과제 finality unknown이며 기억값·실제 회신을 부정하지 않는다. 별도 기준을 A16-06에 덧붙이지 않는다. |

## 실제 경로와 native ID

공개 CLI는 `xsm/cli.py:cmd_owned`에서 `workers.create_owned/run_owned`를 호출한다. 공개 MCP는 `Server.owned`에서 같은 함수를 호출한다. 하위 경로는 `_execute_owned → _owned_argv`와 `_reply_owned`다. 별도 xsm `serve` 명령이 없어도 headless owned 계약은 존재한다.

| 표본 | native ID | 관측 |
|---|---|---|
| owned-claude-memory | `12b3ae0a-c541-455c-8c79-b3319c803fc8` | real-native-execution-with-quiet-reply-adjustment |
| owned-codex-memory | `01a18322-fbb5-7fd0-b6db-1bae94e4c3aa` | real-native-execution-with-quiet-reply-adjustment |
| ordinary-codex-parent | `01a18369-3994-7161-a478-487332cef06e` | real-ordinary-native-with-isolated-xsm_eval-MCP-injection |
| owned-codex-public-mcp | `01a18369-9184-7ea2-874d-561c14ed1869` | public-MCP-real-default-owned-executor-and-reply; parent server wiring injected for fixture |

일반 부모와 owned 자식은 서로 다른 ID이며 각각 자기 ID로 resume했다. 자식 두 번째 요청 본문에는 기억값이 없고, 일반 부모의 두 번째 prompt도 값을 다시 제공하지 않는다. raw에서 8개 실제 turn을 파싱하고 journal 6개 요청 및 부모에게 반환된 MCP 결과 2개를 대조했다.

### 보정·권한·회신의 구분

- `eval_native_memory.py`는 Python 직접 호출과 private `_reply_owned(wake=False)`를 쓴다. Claude/Codex 모두 실제 기본 native argv와 MCP inbox 성공은 있으나 기본 wake/회신의 end-to-end 증거로 쓰지 않는다.
- `eval_native_owned_mcp.py`는 부모의 `mcp_servers.xsm_eval.command/args/env`를 `-c`로 설정하고 격리 snapshot/state를 지정한다. child는 추가 executor/reply callback 없이 기본 함수를 사용한다. fixture 설정 주입이 권한 확대나 실패 뒤 수리였다는 증거는 없다. 동시에 무보정 설치 기본 MCP 연결의 증거도 아니다.
- Claude argv는 `--permission-mode default`, Codex는 `approval_policy="never"`, `sandbox_mode="workspace-write"`다. Claude final의 permission_denials는 두 turn 모두 빈 배열이다. Codex에 대응 denial 필드가 없다는 것을 0건으로 바꾸지 않는다.
- journal sender의 `permission_mode=bypassPermissions`는 hook metadata다. producer argv와 충돌하는 이 필드만으로 native 권한 확대를 단정하지 않는다. 당시 profile 전체 설정과 금지 동작/타 owner에 대한 실제 거절 도전은 이 표본에 없다.
- MCP child 결과 2개는 부모 raw 12·14행에 원 request ID·reply ID·실제 본문으로 반환됐다. journal 전송은 `sent-unconfirmed`, `runtime_reached=false`이며 native queue 자연 소비의 증거는 아니다. 공개 MCP 결과 회수와 전송 확인을 분리한다.
- child 두 번째 `outcome=null`은 과제 finality unknown이다. 실제 기억 JSON과 회신 본문은 맞으므로 이를 기억 실패나 미회신으로 처리하지 않는다.

## Source 결속

실행 snapshot `e2f8b7859e5c`가 남아 있으며 workers/mcp/cli/owned_requests 네 파일을 saved manifest SHA256과 대조했다. 현재 workers/owned_requests는 파일 전체가 동일하다. cli/mcp는 파일 전체가 달라 선택 함수 AST를 추가 대조했다. 하위 의존성 전부나 최신 통합 실행을 증명하는 비교는 아니다.

| 파일 / 함수 | 당시 행 | 현재 행 | 함수 AST 동일 |
|---|---:|---:|---|
| xsm/workers.py / create_owned | 1339 | 1339 | True |
| xsm/workers.py / _owned_argv | 1381 | 1381 | True |
| xsm/workers.py / _execute_owned | 1508 | 1508 | True |
| xsm/workers.py / _reply_owned | 1561 | 1561 | True |
| xsm/workers.py / run_owned | 1644 | 1644 | True |
| xsm/mcp.py / owned | 1024 | 1045 | True |
| xsm/cli.py / cmd_owned | 2050 | 2078 | True |
| xsm/owned_requests.py / submit | 120 | 120 | True |
| xsm/owned_requests.py / reserve | 267 | 267 | True |

`native-memory.json`에는 당시 snapshot manifest가 없다. 해당 시험의 당시 source 전체를 현재 소스로 소급 확정하지 않았다. summary의 추가 MCP 관측·기억값 정규화는 producer 원문과 차이가 있어 raw에서 직접 확인했다.

## 정확한 raw / SHA256

아래 해시는 이번 offline 열람에서 원본 바이트로 계산했다. JSON에는 모든 source·criterion·producer·reply ledger/inbox도 포함한다. `/private/tmp` raw는 현재 존재하지만 durable 보존을 보장하지 않으며 이번 조사에서 복제하지 않았다.

| 경로 | bytes | SHA256 |
|---|---:|---|
| `deliverables/p08-live/native-memory.json` | 8711 | `3c78606b7d52baf20564c87cc62cb7bad398c49f1496cc0ade505dd5e90241db` |
| `deliverables/p08-live/native-owned-mcp.json` | 15011 | `427caa56d8d86a598c5dc1b00cdee6ccc5bc07e8aa80ba255d3f3c0436ad6ff5` |
| `deliverables/p08-live/eval_native_memory.py` | 3429 | `fe2177e04ddd5a8b42c92485b404c9edb01138db77b2b7b56de1f3b9681458cd` |
| `deliverables/p08-live/eval_native_owned_mcp.py` | 5253 | `1dcf6adf4dfbe4eb06071c63e487fde736d71d592982482e1c292ad196a375ea` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-requests/edb213838f65f5acef39cf4c8cdf2716f5dbb029aa4237cf0730f0e1950e178b.json` | 58809 | `b11678d6beaa44d13726a7252b0385d94e0b41405b79b91f14182bbf61c27ae1` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/state/owned-requests/d4fccef5c1066794b92a5584dfe7df1452ed4a4d758d78c57c1d8979df77bb9c.json` | 11918 | `abf39495c92a5d8f8d6942bfc0bf9fb908f17fd033bd78731563dcdd61ef7c41` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/a880c4aade174414a8967f37a2eab43e/memory-claude-first.jsonl` | 31346 | `6b96c107279c9748a72b8249a1f9c4276a0135bf0a9da8cbd5debca334fab563` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/a880c4aade174414a8967f37a2eab43e/memory-claude-first.stderr` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/a880c4aade174414a8967f37a2eab43e/memory-claude-second.jsonl` | 24749 | `616c987f3b0ba1944577669c475858e827448a85e01bfc2ec251eb4f6a957b3c` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/a880c4aade174414a8967f37a2eab43e/memory-claude-second.stderr` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/memory-codex-first.jsonl` | 45612 | `c0e66e0823db10bb9dff7204799e1ea39cfa993d490e607721a4ecf7611ce749` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/memory-codex-first.stderr` | 181 | `2a8dbe3a78dd3467d4b1bca2f55727d9b9d4c049e981d7547b586a404bd0e14b` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/memory-codex-second.jsonl` | 428 | `e9d49b74e84b6d6a3dff0a1b853c49006cc8b4acff516c6366a13510fa761c61` |
| `/private/tmp/p08-native-memory-cn0y8j6u/state/owned-runs/d97a626982844501a7bdc8ec43befe75/memory-codex-second.stderr` | 181 | `5419e5eabd8512ebab4d029fdbd7974823570e640c97171575c3ddc985bb9776` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/first.jsonl` | 60961 | `72e27105424e2294989a7fac7de369a78194a52c406d17c02ac90c0c75142d13` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/first.err` | 220 | `fd2e320058fed7974e8ce90dc788711826af49e7763d6ce7763873827dc89d8c` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/followup.jsonl` | 413 | `79378ddc91bc683a5c9d2e0a264998db69fce06c78e41cc5a6d3cf25e65a4c9f` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/followup.err` | 181 | `c5a8c2ff5e4aacaa58768a9d47b6a60aed43e1d73e1e4e63ab380f7ca30b1d8d` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/state/owned-runs/fa311c9931cb417698dd21edfeb30cf0/1e5fc71fee55-first.jsonl` | 423 | `c10c3417251ebb79f0863e543693f7761973249d1f3eb7dd5b2443f78936c995` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/state/owned-runs/fa311c9931cb417698dd21edfeb30cf0/1e5fc71fee55-first.stderr` | 181 | `ebb2b722c14d95751f4920dd26c1c77c23846bfb2c6fa2e6f2a901007332fa11` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/state/owned-runs/fa311c9931cb417698dd21edfeb30cf0/1e5fc71fee55-second.jsonl` | 407 | `dd054ac60d37e046288808ae05334ef64faf1d8b3bebac9b94049650073ebe97` |
| `/private/tmp/p08-mcp-owned-0q8nu4is/state/owned-runs/fa311c9931cb417698dd21edfeb30cf0/1e5fc71fee55-second.stderr` | 181 | `4251a1af7244bb807820741c8be3bf78c577d1e7088ff26cd2705d19f123aeb5` |

## 미충족과 종결 범위

A16-06은 관측한 일반 Codex/owned Codex 대조의 독립 증거 종결이 가능하다. 일반 Claude를 포함한 전수 조합의 완료를 주장하지 않는다. 기존 ledger의 퇴출 뒤 기억 공백은 A16-08과 구분해야 하며 이번 조사에서는 ledger를 수정하지 않았다.

A23-06은 public MCP 표본의 실제 기본 executor/reply 성공까지 인정하되, 기본 설치 구성을 주입 없이 사용한 표본·실제 shell owned 진입·Claude 기본 reply는 미실행/미입증으로 남긴다. 이 미실행을 source 동등성이나 mock CLI 시험으로 native 실행으로 바꾸지 않았다. 기본 공개 CLI 전체 종결은 현재 증거로 불가하다.

검증: 실제 turn 8개, journal 요청 6개, MCP 실제 반환 결과 2개 및 snapshot 네 파일 SHA256 대조 assertion이 모두 통과했다. 모델 재실행·새 테스트 실행은 없었다.
