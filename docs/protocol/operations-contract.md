# Structural operation inputs

[operations.schema.json](operations.schema.json) defines `operation.call` params:
`session`, `operation` and optional `arguments`. It contains a separate definition
for each of the 22 advertised operations. [Validation-only examples](operation-examples.json)
cover all 22; their opaque handles and placeholder arguments are not executable
requests or authorization to perform effects.

Validate the JSON-RPC envelope with request.schema.json, then validate its params
against operations.schema.json. Definitions derive from the same tool schemas
used by the server, with the host transport's restrictions made explicit:

- Unknown arguments are refused, including nested attachment-object fields.
- Declared string length bounds count Unicode code points, not UTF-8 bytes,
  and are checked before service dispatch. An empty `xsm_doc.doc` is invalid.
- When a tool has required arguments, the arguments object and those fields must
  be present. Omitting arguments otherwise means an empty object.
- Blocking waits are unsupported on this transport: supplied wait/wait_secs must
  be zero, and omitted wait defaults to zero rather than MCP/CLI defaults.
- Native transcript answer recovery is unavailable. A nonempty answer_request is
  refused; host decisions require the separate verified display-response route.

Structural validity does not establish repository policy, directory existence,
peer reachability, membership, permission, claim ownership or native support.
For example, xsm_owned includes admitted native providers for Hermes, Pi,
OpenCode and OpenClaw beside Claude/Codex. Catalog presence does not certify
every provider's lifecycle/UI mode. See the
[native worker boundary](native-workers.md).
Operation-specific result schemas cover inbox, explicit ACK, received files,
[discovery](discovery.md), [team queries](team-result.schema.json),
[board queries](board-result.schema.json), [documents](doc-result.schema.json)
[send producer results](send-result.schema.json) and
[correlated questions](question-results.md) and
[publication results](publication-result.schema.json) and
[human decision status](decision-status-result.schema.json) and
[worker grant issuance](grant-result.schema.json). The other operation result contracts remain
incomplete; input validity does not certify their results.

## Generation and consistency

Maintainers regenerate source artifacts with:

```sh
python3 scripts/generate-protocol-operations.py
python3 scripts/check-protocol-schema.py --output /tmp/operation-contract.json
```

The generator imports the tool-schema source and does not call operations. The
standard checker only validates files. Recorded validation accepted 21 examples
and rejected 73 invalid inputs (`operation-schema-final-validation.json`).
Isolated schema mutations allowing extra arguments or blocking waits fail the
checker (`operation-schema-mutants.json`).

The stdlib gate compares the committed catalog with the runtime-generated
structure and confirms that generation does not mutate the public tool objects.
`protocol describe` also refuses a catalog differing from its installation's
code (`operation-schema-stale-export.json`). The catalog and examples ship in
immutable snapshots. Update/reinstall an inconsistent installation rather than
editing its immutable artifacts. This remains an experimental structural
contract, not full operation or runtime certification.

## 이미 소유한 inbox claim의 token 재조회

`xsm_inbox`의 선택적 `message_ids`는 현재 대화의 canonical 원문 ID
1–100개 배열이다. 각 ID는 영문·숫자·밑줄·하이픈 1–160자다. 이를
지정하면 해당 원문만 조회하며 같은 host·generation이 이미 소유한
active claim도 현재 token과 함께 반환한다. Lease를 연장하거나
acknowledge하지 않는다. 일반 조회는 소유 중인 claim을 다시 반환하지
않으므로 자동 전달 loop의 중복 소비를 막는 기존 동작을 유지한다.
다른 대화·다른 owner의 claim을 가져오지 않으며, 선택하지 않은 원문의
lease를 회수하지 않는다. 만료/이전 generation의 회수는 일반 inbox의
기존 명시적 recovery 경로를 따른다.

```json
{"session":"opaque-session","operation":"xsm_inbox","arguments":{"message_ids":["original-1"]}}
```

원문을 이미 읽었지만 ACK token이 바뀌었다면 현재 token만 재조회해
ACK하고 작업은 반복하지 않는다. Byte budget으로 반환되지 않은 기존
소유 claim도 해제하지 않는다.

## Board parity with CLI

`xsm_board` supports show, set, log, decisions, mute, unmute and sync. Decisions
returns the member-visible decision list without marking other board items as
read. Sync republishes retained board nodes to the team's existing remote
members; sync notes are observations, not proof that a remote consumer read
them. Both require membership. `decide` remains outside this model operation: a
user answer must come through the scoped decision flow, not a supplied answer
argument. CLI and model hosts use the same board service for these effects.

## Question groups and explicit consumption

`xsm_question_status` refuses a foreign group before child polling. A group
result's top-level `claims` aggregates the available reply claims from its
recipient rows, each bound to the child request ID. ACK those exact tokens
after reading the replies. Previously indexed replies remain visible after
ACK, without issuing a new claim for the acknowledged original. Group history
is not a new permission grant or evidence that every recipient finished.

The public `questions` conformance suite observes these paths, including late
and partial replies and a selected-peer handshake. Ask/status/connect now have a dedicated
[result schema](question-result.schema.json); select its operation definition
using the original request. Structure is not authorization or native certification. See [conformance](conformance.md).
