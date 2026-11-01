# Structural operation inputs

[operations.schema.json](operations.schema.json) defines `operation.call` params:
`session`, `operation` and optional `arguments`. It contains a separate definition
for each of the 21 advertised operations. [Validation-only examples](operation-examples.json)
cover all 21; their opaque handles and placeholder arguments are not executable
requests or authorization to perform effects.

Validate the JSON-RPC envelope with request.schema.json, then validate its params
against operations.schema.json. Definitions derive from the same tool schemas
used by the server, with the host transport's restrictions made explicit:

- Unknown arguments are refused, including nested attachment-object fields.
- When a tool has required arguments, the arguments object and those fields must
  be present. Omitting arguments otherwise means an empty object.
- Blocking waits are unsupported on this transport: supplied wait/wait_secs must
  be zero, and omitted wait defaults to zero rather than MCP/CLI defaults.
- Native transcript answer recovery is unavailable. A nonempty answer_request is
  refused; host decisions require the separate verified display-response route.

Structural validity does not establish repository policy, directory existence,
peer reachability, membership, permission, claim ownership or native support.
For example, xsm_owned still declares only its implemented native worker runtimes;
listing it does not generalize workers to Pi, OpenCode, Hermes or OpenClaw.
Operation-specific results remain outside the completed schema coverage.

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
