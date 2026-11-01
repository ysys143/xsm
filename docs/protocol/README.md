# Experimental xsm host protocol

Status: implementation in progress, **not a stable public compatibility promise**.
This is a local host protocol, separate from the existing `[xsm v1 ...]` message
envelope. A successful protocol test does not certify a native runtime.

Native binding notes: [Pi 1.4.0](pi.md), [OpenCode 1.19.5](opencode.md),
[Hermes 0.22.5 API prototype](hermes.md), [OpenClaw 2026.10.9 prototype](openclaw.md).
Host coordination: [Python](python-host.md).

Start `python3 -m xsm protocol serve --stdio` from an installed checkout.
Frames are UTF-8 JSON Lines, JSON-RPC 2.0 objects, at most 1 MiB characters per
input frame. Stdout is protocol only. Diagnostics belong on stderr. Requests
require string/integer/null IDs; state-changing notifications are ignored.
JSON batches are unsupported. `initialize` must precede other methods:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"1"}}
```

## Participation and identity

The pipe is owned by a trusted local host extension, not a model-facing tool or
network client. It provides the same local user trust boundary as installed
hooks; it does not authenticate against malicious processes under that uid.
No listener, login, cloud service or orchestration wrapper is required.

`session.open` takes `runtime`, `profile`, `conversation`, an existing absolute
`cwd`, and optional `capabilities` (`messaging`, `inbox`, `events`, `user-decisions`). Runtime is a
lowercase slug; `claude` and `codex` are reserved until verified native bindings
exist. Profile and conversation are nonempty opaque host identifiers. Local
profile namespaces and addresses are derived without putting raw routing keys
or private configuration directories in responses. Registration is explicit
participation, not consent to widen repository policy.

The response contains connection-local `session`, `generation`, and stable `ref`.
Use `ref:<ref>` to address a peer. Every subsequent session-bound request carries
`session`. Another connection cannot reuse the handle. Only one live connection
may own a conversation. A lifetime file lock arbitrates concurrent owners.
`session.update` accepts `state` (`idle`/`busy`) and `name`; identity is immutable.
`session.close` unregisters this execution without deleting message originals.
EOF also closes sessions; crash recovery uses process generation and existing
claim leases. Reopening the same profile/conversation keeps its address, but
gets a new participation generation, even inside one shared host process.
Previous approvals and consumer claim tokens are not inherited.

## Operations and delivery

`operations/list` returns the existing public MCP tool names, argument schemas
and descriptions. `operation.call` takes `session`, `operation` and `arguments`.
This uses the existing policy/decision dispatcher; it does not invoke arbitrary
Python functions or shell commands. Existing enum, type, required-field and
numeric minimum/maximum checks are applied. A listed operation is **not proof of feature support** in
this experimental host. Native runtime and worker paths are not generalized
yet. Explicit blocking `wait`/`wait_secs` are rejected. Omitted `wait` is set
to zero on this transport, without changing CLI/MCP defaults.

`xsm_inbox` accepts an optional integer `limit` from 1 to 100. It bounds the
rendered messages or notices returned by one read; it is not a byte budget.
Omitting it retains the existing unbounded read. Unselected originals stay
pending, and selected originals still require explicit consumption ACK.
The CLI exposes the same option as `xsm inbox --limit 2 --json`.

`max_bytes` optionally targets 1–1048576 UTF-8 bytes of the joined rendered
messages, including the two-newline separators. The first oversized item is
returned whole and alone so it cannot starve; this is not a hard JSON frame
limit. Results include `rendered_bytes` and `batch_limited`. Bounded reads
return `next_after` when more scanning is needed. Pass it as `after_id` to
continue within this conversation, or omit it to restart. A missing/pruned
cursor is refused rather than silently selecting another inbox.
The CLI exposes `--max-bytes` and `--after-id`.

`events.subscribe` enables `events/available` notifications with the bound session
and pending message IDs. Notifications neither claim nor acknowledge messages.
The initialization response advertises `limits.claimLeaseSeconds`. Inbox results
include structured `items` (`id`, `priority`, `kind`, `wake`) alongside rendered
messages and claims, so native bindings need not parse prose for delivery mode.
The common host checks canonical inboxes every 200 ms. This is a proposed
latency mechanism, not measured native p95 acceptance.

Read `xsm_inbox`, inject its messages into the native session, and preserve the
returned claim tokens. Only after actual reading/consumption may the consumer
call `xsm_ack`. A queue operation or stdout flush is not consumption. The
existing 120-second claim lease and at-least-once recovery apply; this is not
exactly-once execution of task side effects.

`delivery.report` takes `session`, message `id`, and `state` (`queued`, `admitted`,
`refused`, `unknown`). `queued` is a queue report only. `admitted` additionally
requires that receiver's exact claim `token` and asserts observed native context
admission. The host helper uses it only after its native callback observes the
message. Neither state acknowledges consumption.

A broker inbox fetch does not write a delivered receipt for protocol participants.
Native `admitted` or explicit consumption ACK supplies that stronger receiver
receipt. If the receipt mirror fails after a committed canonical ACK, waits and
resends still recognize the authoritative consumption record.
Sending to a protocol participant stores a canonical original without calling
Codex or manufacturing a native queue success.

`inbox.release` takes a bound session and nonempty claim `tokens`. A failed
native admission may release its own claims without ACK; the next eligible
notification is rearmed. Owner and participation-generation checks still apply.

FYI (`wake: "never"`) produces no unsolicited event. It is read at the next
natural tool/prompt boundary. Claimed messages retain their recoverable originals.

## Host user questions

Only a trusted host UI bridge opens a session with `user-decisions`. Ordinary
model-facing clients keep `decision.response` blocked. The host handle and
challenge are private transport data and must never be included in model tool
results or peer messages.

An operation requiring a human answer returns
`{"status":"waiting-for-user","decision_id":"...","question_id":"..."}` without applying its effect.
The host then receives `decision/request` containing `session`, `decisionId`,
`questionId`, a one-use `challenge`, the exact `question`, `requestedSchema`,
and Unix `expiresAt`.
This event is independent of message subscriptions and never claims the person
has seen the question.

After actually displaying the question and collecting that question's response,
the host-only `XsmHostClient` reports `decision.response`: the same session,
question ID and challenge, exact `displayed` text, `action`, `answer`, and a
question-specific native callback `source_id`. A peer's or model's statement
that a person approved is not a host callback. This contract trusts the installed
host extension within the same local uid boundary as existing hooks; it does
not authenticate against malicious local plugin code.

The server checks the active owner, participation generation, display, choices,
expiry and single-use source before storing the answer as `host-user`.
It does **not** relabel it `native-user` transcript evidence. A duplicate exact
response is idempotent; a different response cannot overwrite it or answer
another pending question. Closing a host discards its pending response routes.

The host must explicitly retry the **same** operation and arguments after an
answer; the existing durable decision lifecycle revalidates scope before
applying the effect. Do not poll by repeatedly asking the person. The same
pending invocation returns its existing ID without emitting another question.
`decision.abandon` takes the same session, question ID and challenge to give
up a display without answering, denying, revoking the question or applying an
effect. An explicit subsequent retry obtains a new display route. Old callbacks
are rejected. The shared host helper keeps independent waiters: cancelling one
does not cancel others; cancelling all abandons the display. Transport failure
rejects pending waits and aborts their UI callbacks instead of forging answers.

The response callback itself never applies the operation. Native UI behavior
still needs each runtime's separate certification.

## Unsupported boundaries

Hosts without the UI capability return `-32004` for interactive operations.
Explicit native transcript `answer_request` recovery, blocking waits, generic
remote identities and native worker launches remain open acceptance items.
They are not silently substituted with another approval or launch path.

Protocol errors: `-32700` JSON parse, `-32600` invalid frame/lifecycle,
`-32601` unknown method/operation, `-32602` invalid arguments, `-32001` unknown
session, `-32002` version/initialization, `-32003` registration conflict/policy,
`-32004` unsupported capability. Unknown version negotiation changes no state.

## Verification

Run `python3 scripts/check-protocol.py` for the credential-free, isolated-home
core gate with a 120-second deadline. Native runtime, Linux and external
messenger certification are separate gates in the implementation record.

## Runtime host helper

[`xsm-host.mjs`](../../clients/typescript/xsm-host.mjs) coordinates Node hosts
without runtime-specific policy. Bindings supply native `deliver` and `present`
callbacks, lifecycle events and tool registration. It reads operation schemas
from the server, handles question correlation and cancellation, and reports
queue acceptance only after the binding observes admission. It never
automatically acknowledges message consumption.

Native bindings share `renderInboxPacket` / `inboxAcknowledgement`. ACK
instructions are appended only when the packet contains claims. A notice-only
packet preserves its text without inventing an empty `xsm_ack` request.

Without `deliver`, the helper is pull-only: it does not advertise or subscribe
to `events`. Tools can explicitly read `xsm_inbox` and acknowledge consumption
with `xsm_ack`. `naturalBoundary()` rejects before fetching any claim when native
delivery is absent. A delivery callback must resolve only after observed native
admission; an explicit `false` rejects admission and releases the claims without
writing an admitted report. `present` remains independent of native delivery.

The helper currently rejects waits on a failed connection; automatic reconnect
without restarting the native session is still an open acceptance item.

`inboxBatchSize` (Python: `inbox_batch_size`) configures bounded automatic
reads. After a full batch that acquired originals, the helper keeps draining
without requiring a fresh availability notification. A notice-only batch stops
instead of repeating without progress. `naturalBoundary()` reads one configured
batch. These options require a server that advertises `xsm_inbox.limit`.
`inboxMaxBytes` (Python: `inbox_max_bytes`) configures the UTF-8 target and
requires server advertisement. Bounded automatic reads follow `next_after`,
including notice-only progress, so temporarily deferred originals do not hide
later eligible messages. Successful limited boundary reads schedule their
remainder in the background. OpenClaw uses implementation defaults of 16 items
and 512 KiB; the other binding defaults are unchanged.

A native delivery callback may throw `RetryAdmission(message, delayMs)` for a
definite transient refusal. The automatic loop releases its own claims first,
waits without blocking RPC/UI processing, and reacquires pending originals with
fresh tokens. The default delay is 250 ms; a delay must be positive and no more
than 60000 ms. Closing the host or losing the connection cancels the wait.
Ordinary errors and `false` retain the existing suspended-delivery behavior;
permission failures and server error strings do not opt into retry.
Wake decisions require explicit metadata in the packet actually acquired, so a
stale normal notification or missing metadata cannot wake an FYI-only packet.
Direct `naturalBoundary()` still raises the refusal to its caller, and now
schedules a cancellable background retry. Native hooks recognize that scheduled
refusal and let the current turn proceed. No admitted report is emitted until
the retry actually observes native acceptance.
