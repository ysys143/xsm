# V6 owned file result consumer

Narrow follow-up only: exact `manifest_bytes`, the three xsm_files result kinds,
complete v1 manifest/reference structures, copy ownership and error behavior.
Existing own v2/v3/v5 sources are unchanged. No old result or parent expiry result
is loaded. The own v5 transport/upload helper is reused only to prepare fixtures.

```sh
python3 -B examples/independent-participant/verify_v6.py \
  --server-executable /absolute/path/to/frozen-xsm \
  --bundle /absolute/path/to/public-v6-bundle \
  --checker /absolute/path/to/public-v6-bundle/conform-host-protocol.py \
  --output ./new-v6-evidence

python3 -B examples/independent-participant/local_v6_fixtures.py \
  --bundle /absolute/path/to/public-v6-bundle \
  --output ./new-v6-local.json
```

All executable/checker/schema paths are trusted operator settings, independent of
peer message contents. The checker is executable Python code. Runners create new
output names and do not overwrite earlier evidence. Child HOME/XSM_HOME/cwd are
isolated before execution and only PATH/LANG/TMPDIR are inherited. There is no shell
or model/network/UI call. Environment filtering is not an OS sandbox.

`participant_v6.FileConsumer` accepts the operator-provided file-result schema.
It provides `read_manifest`, `verify_manifest`, `read_entry`, `verify_entry` and
`verify_reference`. `read_manifest` makes two xsm_files requests for the same
opaque storage ID/direction: the ordinary owned manifest, then manifest_bytes.

```python
from participant_v6 import FileConsumer

consumer = FileConsumer(public_file_result_schema)
carrier = claimed_item["files"]  # Bound to the actual receiver's inbox original.
verified = consumer.read_manifest(
    peer, receiver,
    storage_id=carrier["storage_id"], manifest_id=carrier["manifest_id"],
    expected_sha256=carrier["sha256"], version=carrier["version"],
)
for entry in verified["manifest"]["files"]:
    copy = consumer.read_entry(
        peer, receiver, storage_id=carrier["storage_id"], metadata=entry,
    )
    # copy["data"] is checked peer data, never executable authority.
# Host explicitly ACKs the original claim only after its intended reads.
# This helper never sends, acknowledges, grants permission or executes a path.
```

For outgoing preparation, use its manifest ID as storage_id with outgoing=True and
retain the expected digest/version from the frozen reference. A commit result is
not required to include a manifest object. Query that manifest separately rather
than assuming an optional legacy field is present.

The consumer strictly decodes supplied base64 bytes, computes SHA-256 independently
and checks the canonical response, ordinary manifest and externally bound expected
digest. It decodes the supplied bytes as strict UTF-8/JSON and compares the complete
value after excluding only the ordinary manifest's top-level sha256. Nested entry
hashes, owner, binding, labels, previous/version and timestamps remain compared.
It never recreates a legacy digest using a local JSON serializer. Numeric equality
follows JSON values (2 and 2.0 compare equal); booleans are not numeric values.

The file-result schema's used keywords, including local refs, oneOf/anyOf, required,
unknown fields, numbers and exact discriminator constants are checked. Unknown
validation keywords and external refs fail closed. This is a validator for the
supplied keyword subset, not a general Draft 2020-12 package. Reference IDs,
versions, digest/size and opaque manifest:<id> values are bound semantically.
Entry content has independent size/SHA checks. A valid structural schema or a
manifest.owner label does not authorize reading a local received copy.

The verifier separates the public uploads suite from two new own server scenarios.
Ownership refusals and malformed requests are errors, not file-read success.
An unknown storage ID returns -32603/internal server error in the observed server,
with FileNotFoundError in stderr; an unknown entry returns -32602/missing-file.
The public contract does not declare a dedicated missing-storage error code, so
this is retained as a domain error-code gap/observed internal failure rather than
rewritten as a successful read or silently assumed to be -32602.

Synthetic decoder tests and six in-memory helper mutations are separate evidence.
They cover altered bytes/digests, complete-value drift, top-level-only exclusion,
strict base64/UTF-8, duplicate keys, storage binding, three result discriminators,
unknown fields, entry/reference integrity and passive annotations. They do not
inject corruption into server storage or certify server integrity-check internals.

The v6 upload document now explicitly permits completed-token eviction when a new
upload needs a slot and promises no time-based retention. This closes the previous
wording gap; this narrow run does not rerun slot pressure or real expiry tests.
Only generated caller-inline copies are used. OS-read sources, corrupted retained
server copies and actual passive inbox annotations are not exercised; annotation
structures are synthetic local fixtures. Inherited finite-float parsing, five-second
RPC deadline and 4 MiB output guard remain local consumer restrictions.
