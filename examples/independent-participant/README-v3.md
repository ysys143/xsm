# V3 contract follow-up

The v2 participant, verifier, mock tests and README remain unchanged. This follow-up adds `participant_v3.py`, `verify_v3.py` and `local_v3_fixtures.py`. Before creating them, the previous files were copied into the new result archive's `preserved-v2-code/` directory. V2 results are historical evidence, not retroactively upgraded to v3 coverage.

Trusted operator invocation, with no built-in personal or repository-specific input paths:

```sh
python3 -B examples/independent-participant/verify_v3.py \
  --server-executable /absolute/path/to/xsm \
  --bundle /absolute/path/to/public-contract-bundle \
  --checker /absolute/path/to/public-contract-bundle/conform-host-protocol.py \
  --output ./v3-evidence-new

python3 -B examples/independent-participant/local_v3_fixtures.py \
  --bundle /absolute/path/to/public-contract-bundle \
  --output ./v3-local-new.json

python3 -B examples/independent-participant/participant_v3.py \
  --server-executable /absolute/path/to/xsm
```

`--checker` is optional. Omitting it means public suites are not run; its omission is not a pass. It loads trusted operator-selected Python code. `--bundle` provides the inbox schema. Output directories/files require new names and are never overwritten by the runners. Run with `-B` to avoid bytecode writes next to the checker. Server selection remains host configuration, separate from JSON requests, attachments and peer message contents. Only the fixed `protocol serve --stdio` argv is appended to the selected absolute executable. All server processes, including the fixture-only raw probe, use isolated HOME/XSM_HOME/cwd with only PATH/LANG/TMPDIR inherited.

The v3 participant keeps v2 transport hardening, adds duplicate-key rejection, `inbox(session, schema, **arguments)` validation, and `fixture_response(event, action, source_id, answer=None)` for explicit synthetic decline/cancel/accept fixtures. These callbacks are not real UI or human approval. `fixture_answer` and `abandon` remain available.

The inbox validator implements the keywords used by the supplied inbox-result schema and the documented ordered item/claim ID binding. It rejects unknown validation keywords; it is not a general Draft 2020-12 implementation or a replacement for the public schema's development checker. Wake values are exactly booleans or null. No conversion of strings/numbers to wake policy is performed. It validates only the schema supplied by the trusted operator, not all operation-specific outputs.

Follow-up fixtures cover received text and binary bytes, metadata size/SHA-256, incoming/outgoing manifest and byte queries, foreign-owner refusal, explicit ACK after intended copy reads, structured preparation failure/recovery with frozen IDs/body, refusal of changed body, and fresh-reader explicit inline fallback. All file identifiers come from structured results; display prose is not parsed and identifiers never become local paths. Manifest digest agreement is checked across metadata; no undocumented canonical manifest serialization is invented to recompute a manifest hash.

A successful JSON-RPC response may still contain `send.status="refused"`. The committed inline retry fixture treats that as a domain refusal and verifies the original inbox item is unchanged. A capability observation must not silently rewrite a previously committed original.

Other fixtures distinguish form decline, dismissal, abandonment, explicit withdrawal, a business answer `no` and a permission answer `deny`. They inspect stored state and retry only the corresponding original invocation. Unknown legacy wake-null behavior on the real server and real expiry/clock rollback are explicitly not run: valid public sends cannot create an unknown stored wake policy, and no server clock/storage manipulation is used.

The verifier returns nonzero for a contract mismatch, even if unrelated scenarios pass. The observed v3 snapshot returns -32004 for negative waits on xsm_send/xsm_inbox, while request-contract.md says -32602. The expected values are retained so this discrepancy stays visible. The operation catalog declares minimum=0 for a comparison status operation but omits it on those two waits; this observation is not a claim about private implementation code.

Local tests inherit the unchanged v2 mock transport suite and add duplicate-key, inbox binding, wake typing and metadata tests. Four in-memory defects are deliberately inserted and rejected. Null wake schema fixtures are labeled synthetic, not server observations. Existing finite-float/4 MiB output/five-second observation limits remain participant restrictions rather than universal protocol certification.
