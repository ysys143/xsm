# Server output contract

The experimental [output schema](output.schema.json) defines the success and
error response envelopes and the two emitted notification types. A response
contains its request ID and exactly one of `result` or `error`. Error objects
require integer `code` and string `message`; optional `data` is arbitrary JSON.
The framing and parsing rules in the protocol README still apply.

Notifications have no request ID, result or error. `events/available` binds an
opaque session handle to a nonempty message-ID array. `decision/request`
requires the session, decision ID, question ID, challenge, exact question,
requested answer schema and expiration time. A notification is not consumption,
and a pending question is not approval.

The `x-methodResults` schema annotation maps every public request method to its
result definition. Consumers correlate the response ID with their request's
method, validate the response envelope, then validate `result` against that
method's referenced definition. Method names do not occur in response frames.
For example, `delivery.report` returns its recorded state and always
`acknowledged: false`; `session.close` returns `closed: true`.

`operation.call` returns an object: a declared structured operation result, a
`text` envelope, or a waiting-for-user object. Full operation-specific field
schemas are still outstanding. Decision result status
is structurally a string; pending-display and effect-application invariants are
additional runtime requirements. These artifacts do not certify those semantics.

## Examples and observations

[Output examples](output-examples.json) include all 11 method results, one error
and the two notification types: 14 positive structures. The schema checker also
rejects invalid structures, including a mixed success/error, boolean ID,
malformed errors, notification IDs, empty available-message IDs, a missing
question challenge and an admission reporting consumption.

```sh
python3 scripts/conform-host-protocol.py --suite events --capture \
  --output /tmp/xsm-wire.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
python3 scripts/check-protocol-schema.py --wire-trace /tmp/xsm-wire.json \
  --output /tmp/xsm-output-schema.json
```

The optional capture contains temporary session/claim handles from the isolated
probe. The development schema checker uses `jsonschema`, separate from server,
SDK and stdlib fast-gate dependencies.

The events suite includes the 29 lifecycle/messaging checks and three more:
receiver-bound pending IDs, an original still claimable after notification, and
explicit ACK of that original. The actual server passed all 32 checks. The
resulting 38 wire observations include successful responses from nine methods
and one actual `events/available` notification; all match the schema
(`output-schema-final-validation.json`). Human question notifications and
success responses for decision.response/decision.abandon are example-validated
only in this run. Native user UI, queues, wake timing and full decision semantics
remain unverified by this suite.

Weakening the required question challenge or permitting acknowledged=true on
admission in isolated schema copies makes the checker fail in both cases
(`output-schema-mutants.json`). Full operation results and independent complete
implementations remain required by the overall plan.

## Actual decision-route observations

The later decision fixture suite observes `decision/request` and successful
`decision.response`/`decision.abandon` responses through the actual stdio server.
It adds 45 validated frames including four question notifications
(`decisions-output-final-validation.json`). It supplies explicit synthetic host
answers; it is not human UI evidence.

The schema checker accepts repeated `--wire-trace` arguments. Combining the
38-frame events run and the 45-frame decisions run validates 83 frames, successful
responses for all 11 public methods and both notification types
(`combined-output-validation.json`). This supersedes the earlier example-only
coverage of decision routes, without completing operation-specific results,
all decision semantics or native UI certification.

The SDK handshake additionally requires claimLeaseSeconds to be a finite,
positive native numeric value, excluding booleans and numeric strings. Python
integers too large for a finite native numeric representation are refused. The
JSON Schema number definition alone does not establish that representation or
the full host initialization contract.

## Unexpected request failures

An unexpected request exception, including backend `OSError` or `KeyError`,
returns the original request ID with `error.code: -32603` and the generic
message `internal server error`. A non-JSON backend result also produces this
error instead of blaming the client's arguments. Backend exception text and
tracebacks are not included in this response; stderr diagnostics identify only
the exception class. A failing diagnostic writer does not replace the response.
The server can process subsequent requests on the same connection. Broken
transport output still ends the transport.

This error does not prove rollback. A durable claim or another effect may have
committed before the exception. The server does not retry the operation or
implicitly ACK it. Reconcile the original operation's state before repeating
work. Known message IDs can be used with `xsm_inbox(message_ids=[...])` to
recover the current owned token, then acknowledge explicitly. This contract
does not yet cover every notification-loop failure or domain-specific error.

## Operation result encoding

The result encoding is declared by operation and action, never guessed from
whether display text happens to parse as JSON. Text operations return
`{"text":"the exact display text"}` even when that text is `true`, a number, an
array, or a JSON-looking object. A malformed or non-object result from a declared
JSON operation is an internal server error, not a fallback text result.

| Encoding | Operations/actions |
|---|---|
| JSON object | xsm_ask, xsm_question_status, xsm_connect, xsm_discover, xsm_publish, xsm_decision_status, xsm_inbox, xsm_ack, xsm_files, xsm_owned |
| JSON object | xsm_team list/show; xsm_board log/decisions |
| Text envelope | Other actions and xsm_send, xsm_grant, xsm_approve, xsm_join, xsm_reach, xsm_link, xsm_handover, xsm_doc_endorse, xsm_decide |
| Waiting-for-user object | A scoped host question can suspend an operation and return status, decision_id and question_id |

Structured team/board queries retain their fields when passive incoming messages
are attached. The pending counter and optional `incoming` packet are JSON fields;
they do not turn the whole result into display text. Incoming claim tokens still
require explicit ACK after reading. This object-envelope contract does not fill
in all operation-specific domain schemas.

The [inbox result schema](inbox-result.schema.json) additionally specifies the
claimed items and target-owned file metadata. Wire observations tagged with
operation=xsm_inbox are checked against it, including item/claim ID correlation.
[Inbox semantics](inbox-contract.md) also defines sender metadata and structured
attachment preparation recovery. This adds one domain result contract; other
operation-specific schemas are still incomplete.

The [file result schema](file-result.schema.json) covers owned manifest, entry
and exact digest-preimage replies. It also types manifests/references inside
upload status/results. [Checksum semantics](files-contract.md) require actual
byte/hash and value comparison in addition to JSON Schema. Other operation-domain
result schemas remain incomplete; the generic object envelope is not their full
contract.

The [ACK result schema](ack-result.schema.json) specifies canonical acknowledged
IDs and pending-count diagnostics. [ACK semantics](ack-contract.md) preserves
ordered idempotent tokens and makes partial durable effects on a failed batch
explicit. Captured successful `xsm_ack` results are checked against this schema;
its presence does not complete the remaining operation result families.
