# Owned file results and manifest digest bytes

[file-result.schema.json](file-result.schema.json) describes the three xsm_files
response kinds and the complete v1 manifest/reference field structures. Paths in
manifest references are opaque `manifest:<id>` values, not filesystem paths.
Authorization, digest correctness, total sizes, matching versions and claim identity
still require semantic checks; passing a structural schema is not permission.

| Request | Result fields before optional passive inbox annotations |
|---|---|
| storage_id, optional outgoing=true | storage_id, manifest |
| storage_id, entry_id, optional encoding=text/base64 | storage_id, entry_id, encoding, content |
| storage_id, manifest_bytes=true, optional outgoing=true | storage_id, canonical_format, manifest_sha256, encoding=base64, content |

The last form cannot select a file entry. It returns owned manifest metadata,
not original source bytes or filesystem authority. CLI uses `files <storage_id>
--manifest-bytes`, with --outgoing for the caller's frozen outgoing copy. The
existing manifest and entry result shapes remain unchanged when the flag is omitted.

## Existing v1 digest contract

The v1 manifest hash is SHA-256 over the compact UTF-8 JSON serialization of every
manifest field except sha256. The existing writer sorts object keys, uses comma
and colon separators without spacing, and emits Unicode directly. The existing
Python finite-number rendering is part of those stored v1 bytes; this addition
does not convert old manifests to RFC 8785 or change their hashes. In particular,
re-serializing a parsed manifest with another language's default float formatter
is not a reliable way to reproduce every legacy digest.

manifest_bytes exposes the exact bytes that were hashed. A consumer can verify
them without implementing Python's number formatting:

1. Read the ordinary owned manifest and retain its expected digest from the bound
   message metadata or frozen preparation.
2. Read manifest_bytes for the same storage ID. Decode its base64 strictly.
3. Verify SHA-256(decoded bytes) equals manifest_sha256 and the expected digest.
4. Parse the decoded UTF-8 JSON and compare its complete value with the ordinary
   manifest after removing only the top-level sha256 field. Do not drop other fields.
5. Verify each copied entry's size/hash separately when using its contents.

The byte query alone does not authenticate a peer or prove the content was consumed.
Keep its reference bound to the actual message and use the original claim token
for explicit ACK after the intended read. The copy owner and original manifest
owner can differ for a received copy; permission to read is checked against the
local copy's authenticated owner, not a peer-supplied manifest owner label.

Input source is cli-os-read or caller-inline, and source_version is a caller label
or null. Neither is a new permission. source paths remain private metadata outside
the wire manifest. Readable retained copies are distinct from permission to resend
an expired frozen packet. Canonical-byte lookup performs the same copy ownership
and integrity checks as the existing manifest read.

## Lookup failures

A missing retained copy is an operation-domain refusal, returned as -32602 with
`error.data.file_error.code="copy-not-found"`. Other known file failures keep their
machine-readable FileError code in the same field, for example owner-mismatch or
digest-mismatch. They do not expose server paths and do not acknowledge an inbox
original. A truly unexpected storage/IO exception still follows the generic internal
error contract. Missing-copy refusal does not establish rollback, permission to
replace a frozen intent, or permission to resend the body automatically.
