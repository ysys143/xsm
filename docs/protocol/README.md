# Experimental xsm host protocol

Status: implementation in progress, **not a stable public compatibility promise**.
This is a local host protocol, separate from the existing `[xsm v1 ...]` message
envelope. A successful protocol test does not certify a native runtime.

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
`cwd`, and optional `capabilities` (`messaging`, `inbox`, `events`). Runtime is a
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
claim leases. Reopening the same profile/conversation keeps its address.

## Operations and delivery

`operations/list` returns the existing public MCP tool names, argument schemas
and descriptions. `operation.call` takes `session`, `operation` and `arguments`.
This uses the existing policy/decision dispatcher; it does not invoke arbitrary
Python functions or shell commands. Existing enum, type and required-field
checks are applied. A listed operation is **not proof of feature support** in
this experimental host. The native runtime/worker/UI paths are not generalized
yet. Explicit blocking `wait`/`wait_secs` are rejected. Omitted `wait` is set
to zero on this transport, without changing CLI/MCP defaults.

`events.subscribe` enables `events/available` notifications with the bound session
and pending message IDs. Notifications neither claim nor acknowledge messages.
The common host checks canonical inboxes every 200 ms. This is a proposed
latency mechanism, not measured native p95 acceptance.

Read `xsm_inbox`, inject its messages into the native session, and preserve the
returned claim tokens. Only after actual reading/consumption may the consumer
call `xsm_ack`. A queue operation or stdout flush is not consumption. The
existing 120-second claim lease and at-least-once recovery apply; this is not
exactly-once execution of task side effects.

`delivery.report` takes `session`, message `id`, and `state` (`queued`, `refused`,
`unknown`). It records only this receiver's host observation, never final ACK.
Sending to a protocol participant stores a canonical original without calling
Codex or manufacturing a native queue success.

FYI (`wake: "never"`) produces no unsolicited event. It is read at the next
natural tool/prompt boundary. Claimed messages retain their recoverable originals.

## Unsupported boundaries

`decision.response` and interactive user requests currently return `-32004`.
No claimed answer becomes a human approval. UI display, exact question-response
binding, asynchronous waits, generic remote identities and native worker
launches remain open acceptance items, not fallback successes.

Protocol errors: `-32700` JSON parse, `-32600` invalid frame/lifecycle,
`-32601` unknown method/operation, `-32602` invalid arguments, `-32001` unknown
session, `-32002` version/initialization, `-32003` registration conflict/policy,
`-32004` unsupported capability. Unknown version negotiation changes no state.

## Verification

Run `python3 scripts/check-protocol.py` for the credential-free, isolated-home
core gate with a 120-second deadline. Native runtime, Linux and external
messenger certification are separate gates in the implementation record.
