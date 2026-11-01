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

`operation.call` deliberately has an unconstrained JSON result in this artifact.
Full operation-specific result schemas are outstanding. Decision result status
is structurally a string; pending-display and effect-application invariants are
additional runtime requirements. These artifacts do not certify those semantics.

## Examples and observations

[Output examples](output-examples.json) include all 11 method results, one error
and the two notification types: 14 positive structures. The schema checker also
rejects nine invalid structures, including a mixed success/error, boolean ID,
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
