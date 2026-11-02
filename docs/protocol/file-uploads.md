# Bounded file preparation over stdio

Status: experimental. This extension prepares caller-read copies without increasing
any message, file, bundle or frame limit. It sends no message and acknowledges no
original. A prepared manifest is passed to the existing xsm_send/xsm_ask path.

The server advertises `fileUploadChunkBytes`, `fileUploadBudgetBytes` and
`fileUploadSlots` in initialize.limits. A client must check the extension before
using it. A server without these fields has not promised chunk preparation.
Current limits are 192 KiB of decoded bytes per chunk, 1 MiB per file, 4 MiB per
bundle and aggregate reserved raw buffers per connection, 16 entries per bundle,
and 16 concurrent upload handles including retained completion metadata. These
are buffer/entry limits, not a claim that total process memory is 4 MiB. Metadata,
serialization, the bounded input queue and frozen-copy storage have their own costs.
The existing 256 MiB copy-store quota and seven-day retention still apply.

## Methods

All methods require a connection-local session handle. They are host methods,
not model tools. Runtime identity, generation and working paths come from that
bound session; no sender identity or source path is accepted in these methods.

| Method | Other required params | Successful result |
|---|---|---|
| files.upload.open | target, request_id, text, entries | uploading progress or an existing frozen preparation |
| files.upload.write | upload, entry, offset, base64 | upload, entry, next byte offset |
| files.upload.commit | upload | frozen manifest ID/material metadata, request ID and body_sent=false |
| files.upload.status | request_id | uploading progress, frozen indexed manifest, or unknown |
| files.upload.abort | upload | aborted=true, request ID and body_sent=false |

Each entry declares name, size and lowercase SHA-256; optional source_version is a
caller label. Open may also carry previous_manifest and attachment_fallback=inline,
with their existing material-preparation meanings. Metadata cannot authorize a
server filesystem read. Unknown fields, including path, are rejected.

The upload token is opaque and belongs to this execution of this conversation.
Entry is a zero-based index. Offset counts decoded bytes. A write appends at the
current end, or replays an already present exact byte range. It cannot leave a
gap, extend beyond the declared size, or replace earlier bytes. Changed replay
bytes are refused. Base64 is strict, with at most 262144 encoded characters.
An incomplete or hash-mismatched active buffer remains uploading until aborted
or closed; this state is separate from the durable frozen-intent lookup.

Commit checks every declared size and digest before invoking the existing owned
material preparation. Incomplete/corrupt uploads do not create a new indexed
preparation. A successful commit frees the raw buffer and retains small completion
metadata for exact replay. Frozen material intent, request/body binding, version,
quota, capability negotiation and explicit fallback use the same engine as CLI/MCP.
The returned references are manifest references, not local paths or permissions.

## Recovery and cancellation

Opening the same active request with the same metadata resumes its offsets; changed
metadata is refused. The Python prepare_files and TypeScript prepareFiles helpers
snapshot supplied bytes, reopen/resume progress, write bounded chunks and commit.
They do not read paths, send the body, retry unknown body delivery, or ACK anything.
After preparation, call xsm_send/xsm_ask with the same request ID, original text and
manifest_id; supply the same explicit fallback if one was authorized.

If the peer has no observed file reader, preparation may fail after the frozen
manifest is indexed. error.data.attachment_error carries its manifest ID when
available. Status can recover that index, and the same commit or an ordinary send
using that manifest can revalidate it after the capability/explicit fallback issue
is resolved. A JSON-RPC success is not proof of body delivery or task completion.

Connection loss or session close discards only volatile buffers. A new execution
cannot use the old token; it queries status with its own request ID. A durable
indexed manifest remains owned by the same conversation and can be recovered.
Unknown means no valid index was found; it is not proof that every prior storage
step rolled back. Copy creation and intent-index creation are separate existing
storage steps. Preserve the original bytes/body/ID when resolving an unknown.

Abort frees one owned preparation buffer/completion token. It does not delete a
frozen copy, withdraw a permission, cancel a peer task, remove an inbox original,
or acknowledge consumption. body_sent=false describes this preparation operation;
it does not assert that another invocation never sent the same request.

## Structural artifacts and evidence

request.schema.json includes the five methods. output.schema.json describes progress,
write/abort responses, and frozen/unknown status shapes. The nested legacy manifest
and reference objects still need their complete independent result schema; the
extension's structural schema is not full file/operation certification.

The public checker has an uploads suite: lifecycle plus a four-file 4 MiB transfer,
exact replay, wrong owner, changed metadata, generation recovery, no implicit send,
all received bytes/digests, buffer abort and explicit ACK. It uses only public stdio.
Python and TypeScript helpers also have real-server wire tests. Synthetic fixtures
and copy transport do not certify native runtime admission, human UI, remote hosts,
models or external messengers.

The server reads UTF-8 bytes strictly and preserves the existing 1 MiB-character
input frame limit. Raw reads are bounded at four times that count, the maximum
UTF-8 bytes needed for those characters.
A malformed UTF-8 frame is -32700. An oversized frame is -32600 and ends that input
stream; unfinished requests require status-based recovery. Output copies are read
one entry at a time, at most 1 MiB decoded per entry; their base64 responses can be
larger than the request-frame limit. The public checker's own 4 MiB output-frame
limit is a verifier restriction, not a new engine file limit.
