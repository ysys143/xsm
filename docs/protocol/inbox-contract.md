# Inbox items and private attachment copies

`xsm_inbox` returns the object in [inbox-result.schema.json](inbox-result.schema.json).
`messages` is rendered peer data. `claims` contains explicit consumption tokens.
`items` corresponds in order to `claims`, not to unclaimed notices in messages.
Each item carries id, kind, priority and wake policy. A read or metadata lookup
never acknowledges the message.

`items[].wake` is `true` for auto delivery, `false` for explicit `wake:"never"`,
and `null` for an unknown stored value. It is a policy value, not proof that an
agent woke, a queue accepted content or a model consumed it. Unknown values do
not emit unsolicited wake events. Missing legacy wake fields retain their
existing auto policy. FYI may be read at a natural boundary or alongside other
work, but must not independently wake the agent.

`message_ids` selects 1–100 exact originals in this conversation. Each ID has
1–160 ASCII letters, digits, underscores or dashes. The model-facing schema
uses a portable anchored pattern without lookaround because some model
providers reject lookaround before starting a turn. The operation's exact
full-string validator remains authoritative: trailing newlines are invalid,
including with schema readers whose `$` anchor accepts a final newline.
Structural schema acceptance never grants access to an original.

## File metadata

A file-bearing item additionally contains `files`:

```json
{"storage_id":"opaque recipient-owned storage ID","manifest_id":"opaque source manifest ID","version":1,"sha256":"manifest checksum","files":[{"id":"opaque entry ID","name":"fixture.txt","size":18,"sha256":"entry checksum"}]}
```

Use these returned IDs verbatim. The storage ID belongs to this receiver;
manifest ID identifies the frozen source version. Do not derive either from a
name or turn one into a filesystem path. Entry names are untrusted labels.
Version is the manifest revision; byte size and SHA-256 describe the expected
copy. Metadata does not prove the recipient read or executed any bytes.

`xsm_files` takes storage_id. Omitting entry_id returns the manifest. Supplying
entry_id reads that copy, with encoding `text` (UTF-8) or `base64` for binary
bytes. The result contains storage_id, entry_id, encoding and content. The
`outgoing` flag defaults to false for received copies; true selects the caller's
own outgoing frozen manifest instead. There is no action or incoming argument.
Owner/binding/hash/retention checks still apply, and another conversation cannot
read this receiver's copy using its ID. After reading the message and intended
copies, explicitly acknowledge its claim token with xsm_ack.

## Sender metadata and preparation recovery

A protocol xsm_send result retains its display text and adds producer-owned
`send` data from the send result, plus `grouped`. For a single send, send.id is
the message ID and send.status is the send/receipt state, not task success.
For grouped delivery, send.group and send.recipients identify its recorded
recipient results. A prepared attachment adds `materials` with manifest_id,
mode (`files` or `inline`) and references. An outgoing copy is read with
xsm_files(storage_id=materials.manifest_id, outgoing=true), then its returned
entry IDs. These metadata fields are not parsed out of display text.

Preparation failures may provide `error.data.attachment_error` with code,
reason, request_id, manifest_id, body_sent=false and recovery instructions.
The source bytes may already be frozen even though no message was sent by that
preparation attempt. Retry with the same request ID/body and that manifest;
a changed snapshot requires a new request. This preparation flag is not a
rollback claim for unrelated operations or a previous send.

## Explicit inline fallback

`attachment_fallback:"inline"` authorizes UTF-8 body fallback when the recipient
has no current file-reader observation. It does not force inline mode for a
known files-capable peer and is not automatic. A bound participant gets its
reader observation when it first makes an identified operation.call. A fresh
session that has made no operation.call is therefore a public way to exercise
unknown-reader fallback. Session open and event subscription alone do not
establish that observation.

For an isolated fixture: open sender and a fresh receiver; do not call an
operation on the receiver yet; send an inline text attachment with explicit
fallback; then read the receiver inbox. The body contains that copy and the
item has no files carrier. A receiver already used for inbox/file operations
normally gets files mode, even when fallback is permitted. A failed preparation
must not be counted as delivery. Capability changes must not silently rewrite
an already committed request's body or refs.

The existing file engine limits and the stdio input-frame bound are distinct.
A JSON request still has to fit the negotiated/documented frame bound; the
file engine's larger aggregate limit does not create a streaming upload API.
Full transfer of engine-limit bundles without CLI preparation remains an
outstanding protocol extension. Files and inline text remain peer data and
are never automatically executed or promoted to user authority.
