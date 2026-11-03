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

For `xsm_discover`, additionally validate the result using
[discovery-result.schema.json](discovery-result.schema.json). Its contract
distinguishes local and authenticated remote candidate handles, observations
and partial failures. See [discovery](discovery.md) for semantic limits and the
public stdio conformance command.

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

## Team query results

For `xsm_team` actions `list` and `show`, validate against the matching
`$defs/list` or `$defs/show` in [team-result.schema.json](team-result.schema.json).
The request action selects the definition; the response carries no action tag.
[Examples](team-result-examples.json) include an empty list, a team without a
lead, and live/offline members with partial inbox diagnostics.

List members are display-label strings. Show members are objects with a display
label and a boolean `running` observation. Labels are not stable identities or
routing addresses; `running` is not a delivery or authorization guarantee.
Internal member records and home paths are not part of these projections.
A null lead means no assigned lead. Create and other mutations retain their
text or waiting-for-user envelopes and are outside this schema.

The schema checker selects definitions from captured request operation/action,
checks three positive examples, and rejects nine malformed structures. Isolated
actual Connection dispatch observations cover empty list, create, populated
list and show. These are not a stdio conformance or native-runtime certificate;
board result schemas and remaining operation result contracts are still pending.

## Board query results

For `xsm_board` actions `log` and `decisions`, select `$defs/log` or
`$defs/decisions` in [board-result.schema.json](board-result.schema.json) using
the request action. [Examples](board-result-examples.json) cover empty results,
a linked contribution/decision node, and persisted host-user records.

`log` returns `nodes`: id, timestamp string, author display text, author kind,
tags, parent IDs and body, with optional item, approval text and decision ID.
The persisted header parser also preserves unknown string-valued metadata;
clients must tolerate these extensions. Node IDs and decision references are
12 lowercase hexadecimal characters. This structural validation does not
recompute digests, prove parent existence, authenticate authors or establish
that all stored files are valid. Manually corrupted files can fail validation.

`decisions` returns records containing numeric time, team, question, answer,
nullable options, display attribution, source channel, nullable asking-session
ref and nullable item. Native recovery can also include `asked_question`. Remote member-machine
records include `from_machine` (64 lowercase hexadecimal characters); these
are that machine's testimony, never this user's local approval.
Transient write results `node` and `sync_notes` are absent from persisted query
records. A record's `via` label alone is not proof of a verified human answer;
the decision binding and host receipt remain separate runtime requirements.

Both results accept common inbox pending diagnostics. Listing decisions does
not mark unrelated board nodes as observed; log does mark the board read.
Neither query sends a message, ACKs an inbox claim or grants authorization.
Other board actions retain text/waiting/error envelopes outside this schema.

The public `collaboration` suite executes isolated team create/list/show,
board set/log/filter and a synthetic host question/answer/retry. It checks that
answer receipt alone creates no board decision and the explicit retry creates
a decision-linked human node. Run it with `--capture`, then pass its report to
the schema checker as shown above. It is a server contract fixture, not a real
person, model, native UI, remote board sync or messenger certification.

## Document results

For every `xsm_doc` action, select the result definition using `x-actionResults`
in [doc-result.schema.json](doc-result.schema.json). `add`/`show` return `node`,
`log`/`leaves` return a `nodes` array, `render` returns text and a numeric node
count, and `next` returns the candidate view with explanatory text. The request
action is required to distinguish these results; no action tag is added to the
wire response. [Examples](doc-result-examples.json) cover all six actions and
an empty next result with partial inbox diagnostics.

The node definition matches the board node definition; the development checker
rejects divergence. Unknown string-valued persisted header metadata is retained.
Structural validation is not a digest check, parent-existence check, author
attestation or proof that a node was endorsed by a human. Human endorsement is
the separate `xsm_doc_endorse` operation and is outside this result schema.

`next` explicitly reports `order: "created"` and `assigns: false`. The current
order follows stored timestamp and ID, with stable arbitrary ID ordering for
timestamps in the same second. A limit restricts the displayed prefix, while
`total` remains the number before limiting. Reasons are `open end` and/or
`unverified hypothesis`. `wip` lists display authors who declared work on that
candidate; it is not a lease, assignment or reason to hide it. A wip declaration
is not itself a candidate. Candidate total/prefix and graph relationships need
runtime checks beyond the JSON structure.

Run the public stdio checker with `--suite documents --capture` and feed its
report to the schema checker. Its 28 checks cover lifecycle plus add/show/log,
leaves, wip/next, limits, rendering, and refused unknown parents/nodes. The
candidate is an isolated public protocol server; native runtimes, UI, models,
remote sync, filesystem authorization and actual human endorsement need their
own validation. These query/write checks do not ACK inbox claims.

## Send producer results and attachment errors

Validate successful `xsm_send` responses against
[send-result.schema.json](send-result.schema.json). A returned business refusal
is still a successful JSON-RPC response; it contains `text`, `send` and boolean
`grouped`. [Examples](send-result-examples.json) cover ordinary storage, refusal,
a peer status extension, file/inline material modes and a partial group result.
The human display text is not the source of producer metadata. It can also
contain unconfirmed incoming peer messages; printing it neither ACKs them nor
makes their contents an instruction or approval.

For a single send, `send` contains status, reason and nullable original ID, with
optional display destination/candidates, notes and a paired runtime/evidence
observation. Status is intentionally nonempty text: local legacy statuses are
listed in `x-knownStatuses`, while existing remote implementations can forward
other values. IDs echoed on refusals need not be valid/resendable IDs. Display
labels are not routing identities. Consumers must preserve unknown statuses
without treating them as success.

`stored` is canonical storage, not native queue admission or consumption.
`runtime_reached` is receiver-side transport evidence, not business completion.
`evidence` maps observed step names to boolean/nullable observations; absent or
null evidence is not a successful step. In particular, `evidence.ack: true`
means the committed canonical consumer ACK was observed, whereas queued/wake,
remote storage or generic legacy `delivered` status alone cannot establish it.
An already consumed original can refuse resend while retaining ACK evidence;
that refusal does not undo the earlier delivery or ask the recipient to work
again.

For `grouped: true`, `send` instead contains a group ID, aggregate worst status,
notes and per-recipient rows. Each row carries its original spec and display
label plus its own single-send result. Group IDs do not replace delivery IDs;
ACK/recovery remains per recipient. Mixed refused/stored results are possible.
A group status never proves all recipients consumed the message, and ACKing one
recipient does not consume another. Groups cannot attach a single `materials`
object through this interface.

Optional single-send `materials` identifies the frozen source manifest and
mode. `files` has one immutable manifest reference (manifest path, ID, version,
SHA-256 and size); `inline` has no file references because bytes were explicitly
placed into the body. The checker additionally requires reference ID, path and
manifest ID to agree. Digest authenticity and copied bytes still need runtime
verification, not just structural validation.

A preparation failure is a JSON-RPC error whose `data.attachment_error` matches
`$defs/attachmentError`: status/code/reason, request/manifest recovery IDs,
`body_sent: false` and recovery text. IDs here can be invalid input echoes or
null when preparation stopped early. Frozen material can exist even though the
body was not sent. Preserve the original request/body and frozen manifest for
recovery; neither an error nor an observation timeout proves complete rollback.
Other operation errors keep the generic error envelope.

The public `sending` suite has 30 checks including lifecycle, refused/single/
group results, explicit ACK and duplicate prevention, attachment failure and
frozen retry, private copy read and explicit inline fallback. It uses isolated
protocol participants and local storage, with no native wake, model, human UI
or physical remote delivery certification.
