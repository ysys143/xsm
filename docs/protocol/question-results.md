# Correlated question results

`xsm_ask`, `xsm_question_status` and `xsm_connect` use
[question-result.schema.json](question-result.schema.json). Select the definitions
in `x-operationResults` using the originating request; a response does not carry
its operation name. [Examples](question-result-examples.json) identify actual
isolated stdio observations, local Gateway fixtures and synthetic structures.
They are not executable requests or authorization. Generic JSON-RPC errors use
the output contract; attachment preparation errors share `attachmentError` with
the send contract.

## Result families

- `qSingle`: one correlated question or handshake, its indexed reply history,
  terminal outcome, send/delivery evidence, explicit reply claims and recovery
  location. Refused/not-found results can have null purpose/timestamps/evidence
  and an invalid input ID echo. An interrupted claimed send can have only
  status/reason as send evidence; it must not be resent merely because no answer
  has been observed.
- `qGroup`: owner-visible recipient results, skips, counters, waiting labels,
  flattened replies and aggregated claims. Each non-skipped row has a separate
  child request ID. `reply_received` means other recipients still wait;
  `replied` can contain only partial answers. `final` requires every asked child
  to have a terminal reply. Skipped recipients are counted separately.
- `qDeniedGroup`: foreign or vanished groups return empty recipient/reply/claim
  arrays, without owner counters or child IDs. Current owner checks precede
  child polling. Loss of group metadata does not cancel retained child work.
- `qListing`: metadata-only IDs belonging to this exact native conversation.
  Reply bodies are not included. This supports recovery when a caller lost an
  automatically generated request ID.
- `qSelection`: connect was refused or still needs user selection. It is not a
  handshake result or a permission grant. An existing communication scope also
  does not complete a handshake without the selected peer's actual final reply.

The host transport's wait budget is requested=effective=0, cap=60. Timeout ends
the wait, not the task or its retained original. `wait_end_reason` is not an
outcome or permission. Reply outcomes are `succeeded`/`failed` or absent/null;
the last terminal outcome in the history determines `final_outcome`. A handshake
is completed for succeeded, declined for failed, reply_received for nonterminal
answers and otherwise pending. An ordinary question remains not-started on the
handshake axis. None of these peer replies is a human approval for another
operation.

## Claims, identity and evidence

Each claim identifies an actually returned reply. A group's root claims are the
ordered concatenation of available recipient claims, bound to child IDs, not
the group ID. A cached reply can remain readable with no claim if its canonical
copy was already acknowledged or is unavailable; claim diagnostics describe
availability, not a substitute token. Read the real answer before explicitly
ACKing the returned token. ACK preserves the indexed answer history and does
not tell a peer to perform the task again.

Reply handles use opaque `home_id` and never a private `home` field. A remote
handle additionally has a machine key. Display name/ref/alias and a structurally
valid handle are not fresh routing authority. Context, owner, generation and
current scope still require runtime validation. Group IDs, child IDs, reply IDs,
claim tokens and human decision IDs have different roles.

Send evidence is the send producer projection; delivery evidence contains named
step observations with timestamps/legacy flags. Storage, queue/wake, receiver
arrival, canonical ACK and business outcome remain distinct. Missing or null
observations are not success. A step or a `final` string alone cannot authenticate
who answered or grant a new permission.

## Remote evidence and file payloads

`network_delivery` follows `qNetworkDelivery`, including not-found, prepared,
unknown/stored states, metadata-only replies and at most one final reply. A final
reply may carry its P2P v1 packet, or explicit payload-unavailable metadata when
the retained file copy can no longer be read. It must not invent a body-only
replacement or regenerate expired bytes from original files.

`qPacket` declares opaque endpoints plus generations, request/reply bindings,
network scope, body/kind/outcome/priority/wake, immutable attachment references,
optional file packet and semantic fingerprint. A false wake only supports next
priority. Reply packets carry their reverse request binding. File packet data
maps entry IDs to base64 strings and the complete v1 manifest, reusing the
[file result definitions](file-result.schema.json). Content encoding is a JSON
Schema annotation, not proof that bytes decode or match a digest.

The development checker additionally checks reply/history/final associations,
group counters/claims, packet metadata/request/scope association, and file
reference/manifest/request/body-hash agreement. It does not verify TLS, membership,
current generation, receiver policy, all packet/manifest fingerprints, decoded
file bytes, quota, expiration or native delivery. The Gateway and file runtime
checks remain mandatory. Packet byte/frame limits and UTF-8 byte counts cannot
be inferred from character counts in these schemas. A prepared reverse packet
is not proof of remote receipt or consumption.

## Validation scope

Run `conform-host-protocol.py --suite questions --capture`, then pass its report
to `check-protocol-schema.py --wire-trace ...`. The schema checker requires the
same common claim/file/material definitions as the other result contracts and
refuses drift. These artifacts complete the declared result structures for the
three operations; whole error semantics, independent full implementation,
physical remote/native/user-UI/runtime certification and the full plan remain
separate requirements.
