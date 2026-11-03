# Error and retry contract

Version 1 uses the JSON-RPC error object in [error.schema.json](error.schema.json).
[Examples](error-examples.json) cover all nine emitted codes through actual stdio.
Numeric code and structured data are machine inputs; message text is diagnostic
and must not be parsed as permission, consumption or completion evidence.

| Code | Meaning | Recovery boundary |
|---|---|---|
| -32700 | Invalid JSON/UTF-8 | Correct this frame; earlier requests are unaffected |
| -32600 | Invalid frame/lifecycle, including duplicate initialize | Correct frame or connection lifecycle |
| -32601 | Unknown method/operation | Use the negotiated catalog; initialization is still required first |
| -32602 | Invalid arguments or a domain refusal, including a closed decision | Inspect the exact operation/request; do not assume no partial effects |
| -32603 | Internal error or an invalid backend result | Outcome may be unknown; inspect durable state before retry |
| -32001 | Unknown/closed connection-local session | Reopen the actual conversation and use its current handle |
| -32002 | Initialize/version negotiation required or unsupported | Negotiate a supported version before participation |
| -32003 | Registration conflict, identity, policy or question binding refusal | Correct ownership/scope; never substitute another session's answer |
| -32004 | Unsupported capability/mode | Use an explicitly supported mode; do not manufacture native admission |

After initialization, an unknown method is classified before session lookup.
A stale session on a known method remains -32001. Rejected initialization does
not create participation. Codes do not imply that a logical task was rolled back.
In particular -32602 can follow earlier durable ACKs in a batch, and -32603 can
follow a stored document node or an acquired inbox claim. No error automatically
acknowledges a message, repeats a mutation, changes its request id, or cancels the
peer's task.

Recover an unknown result through the operation's existing state: question or
decision status, targeted inbox/current claim, owned status/reconcile, document
log, team/board query, or scope policy. Preserve the original immutable inputs
and request/reply ids where supported. A renewed user decision uses a new
`decision_key`; an unknown outcome alone is not a renewed user request.

Optional `data` remains compatible with existing backend details. Attachment
failures are additionally checked by the file/send domain contracts. This generic
error schema does not certify every operation-specific data payload. Arbitrary
backend exceptions expose a fixed internal-error message and no traceback or
backend detail on stdout. Clients must preserve unknown peer errors rather than
coercing them into a successful operation result.

Cancellation remains operation-specific. Closing a host question display is not
a denial; a stored answer applies only when the original operation is retried.
Cancelling a waiter does not revoke a stored answer, ACK a message or cancel the
peer's work. Owned cancellation distinguishes not-started, unverified and an
observed native stop; it does not assert rollback or exactly-once side effects.
See [decision lifecycle](decision-lifecycle.md), [owned/native work](native-workers.md)
and [delivery/ACK](inbox-contract.md) for the relevant state transitions.

The `errors-fixture` suite uses an explicit isolated fault candidate. It writes
one real document node and then raises an internal exception. A subsequent log
must retain exactly that node without automatic replay. A production candidate
without the fixture marker is refused before the injected-write scenario.
This is local protocol/error evidence, not a native runtime or external UI test.
