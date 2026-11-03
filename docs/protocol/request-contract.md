# Request envelope contract

The experimental [request schema](request.schema.json) binds all 16 currently
exposed methods to parameter definitions. [Request examples](request-examples.json)
contain one structural example per method. The `cwd` example is a placeholder;
`session.open` requires an existing absolute directory at execution time. Opaque
handles and user-decision challenges are examples, not usable authorization.

`initialize` requires a protocol version string; the server separately negotiates
supported versions. `operations/list` accepts omitted params or an empty object.
Session-bound methods require `session`. `session.update` only accepts state and
name changes. `operation.call` requires an operation name; omitted arguments
default to an empty object. The actual operation schemas come from
`operations/list` and are validated before business dispatch. The
[structural operation catalog](operations-contract.md) makes those inputs and
host transport restrictions available as a separate installed artifact.

All known methods reject unrecognized parameter names with `-32602`, before
changing state. An already initialized connection still rejects a repeated
initialize with `-32600`, and other methods before initialization fail with
`-32002`. These ordering rules are separate from structural schema validation.
The schema's method enum describes supported requests; an unknown method is
invalid according to this schema rather than a declaration that the wire
cannot carry an error-producing request.

JSON Schema validation alone does not establish a live handle, capabilities,
claim ownership, directory access, generation, pending question, or exact UI
binding. It also does not certify operation-specific arguments or results.
Runtime restrictions and JSON parsing rules in the protocol README still apply.
The schema remains experimental. [Output definitions](output-contract.md) cover
response/notification structures separately; full operation schemas remain outstanding.

## Artifact verification

The development checker uses the external `jsonschema` package implementing
Draft 2020-12. It is not a server or SDK dependency and is not required by the
stdlib protocol gate. It must already be available in the selected development
Python environment:

```sh
python3 scripts/check-protocol-schema.py --output /tmp/xsm-request-schema.json
```

It validates the meta-schema, requires one example for every declared method,
checks all positive examples, and rejects unknown fields, missing required
parameters, invalid envelopes and admitted reports without a token. The recorded
run used jsonschema 4.26.0, accepted 11 examples and rejected 41 negative cases
(`request-schema-validation.json`). Removing the `operation.call` binding in an
isolated artifact copy makes the checker fail (`request-schema-binding-mutant.json`).

The stdlib fast gate independently compares public method/field bindings with
the server's `REQUEST_FIELDS` table. Runtime regression tests demonstrate that
unknown parameters cannot initialize, close a session or subscribe to events.
Before the server fix, the close request actually closed the participation;
that failure is preserved in `request-fields-red.log`.

## Error precedence in this implementation

Framing/JSON errors precede method dispatch. Before initialization, non-initialize
requests fail with -32002; repeated initialize is -32600. Unknown fields of a
known method are refused with -32602 before its state change. Global
operations/list and session.open do not need a session handle. Other dispatch
paths validate the connection-local handle first: an unknown method without a
valid session can therefore return -32001 before method-not-found. With a valid
handle, unknown methods and unknown operation names return -32601.

Known operation argument types/ranges are validated before recognized host
transport restrictions. A negative wait is invalid parameters (-32602); a valid
positive blocking wait is unsupported here (-32004). Nonempty native transcript
answer recovery is also -32004. The structural schema describes accepted input,
not the precise error code for every rejected combination. Unexpected request
or output failures are -32603 and do not establish rollback.

The five [bounded upload methods](file-uploads.md) prepare caller-read copies,
without sending a body or acknowledging consumption. Their input schemas also
limit indices, sizes, hashes, base64 chunks and unknown fields. UTF-8 input is
decoded strictly; the existing frame limit counts characters. A bounded raw
read allows up to four UTF-8 bytes per character without shrinking that limit.

After initialization, unknown method names are rejected as -32601 before
connection-local session lookup. Known methods still validate their session and
arguments. Before initialization, -32002 remains the lifecycle boundary. The
[error contract](error-contract.md) distinguishes these codes from effect and
retry semantics; a rejected mutation may still require state inspection.
