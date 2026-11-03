# External stdio lifecycle conformance

Status: experimental, partial coverage. This suite tests the public stdio
boundary without importing xsm, either SDK, or inspecting server storage.
It accepts any executable command that implements the lifecycle contract.
Passing is not certification of the complete protocol, native runtimes,
operations, delivery, approvals, remote identity or performance.

```sh
python3 scripts/conform-host-protocol.py \
  --output /tmp/host-conformance.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
```

`--command` must be last; its remaining arguments are passed directly to the
candidate, without a shell. A shell launcher such as `bin/xsm` must be executed
directly, not passed as Python source. The candidate runs twice concurrently,
with shared isolated HOME/XSM_HOME and a temporary workspace. Credentials,
caller runtime identities and native profile settings are not inherited.
Do not use this runner with a command that ignores these isolated homes.

## Checked contract

The JSON report includes completed check names and the failing `activeCheck`.
The process exits zero only when all 16 checks pass:

1. Requests before initialization fail with `-32002`.
2. An unsupported version fails with `-32002`, without initializing the pipe.
3. Version `1` is negotiated explicitly.
4. Repeated initialization fails with `-32600`.
5. Operation descriptors have names and input schema objects.
6. The reserved native runtime `codex` is refused with `-32602`.
7. Session, generation and address are nonempty opaque strings.
8. Session identity updates fail with `-32602`.
9. Busy state updates return the new state.
10. A handle from another pipe fails with `-32001`.
11. A second live owner of the same conversation fails with `-32003`.
12. A different profile has a different address.
13. Explicit close reports `closed: true`.
14. A closed handle fails with `-32001`.
15. Reopening preserves the address and changes generation and handle.
16. EOF releases ownership and reopening changes generation.

Each response must be JSON-RPC 2.0, match the integer request ID and contain
exactly one of result/error. Notifications must have a method and object params.
Responses have a five-second observation deadline; subprocesses are closed and
reaped on success or failure. Candidate stderr excerpts are included in the
report. Assertions remain active when the runner uses Python `-O`.

## Evidence and limitations

The actual server passed 16 checks in
`deliverables/protocol-foundation/blackbox-lifecycle-server-final.json`.
The first invocation incorrectly passed the shell launcher to Python; its
failure and diagnostics remain in `blackbox-lifecycle-first.json`.

`tests/fixtures/minimal_protocol_host.py` is a separate stdlib lifecycle fixture.
It imports no xsm modules and is deliberately incomplete: it has no actual xsm
operations or message store. It verifies that the runner can inspect a different
implementation, rather than certifying third-party interoperability. Tests
confirm that constant generations, cross-pipe handle acceptance and missing
lifetime locks fail at their respective checks. A marker credential in the
parent is explicitly rejected by the fixture if inherited. All four checker
tests also pass under Python `-O`.

Full normative method/result/error schemas, decision and delivery contracts,
independently authored complete implementations and the complete P0/P2
conformance matrix remain outstanding.

`--suite discovery` runs the sixteen lifecycle checks and eight local directory
checks through the public stdio interface. It creates an isolated Git repository
and checks two participants, target/privacy metadata, observation provenance,
work/branch filtering and close visibility. See the [discovery contract](discovery.md)
for the result schema and capture-validation command. Tests inject private home
disclosure and missing observation provenance into actual server responses;
each must fail its corresponding check. This does not certify remote or native
runtime discovery.

## Claim and delivery recovery suite

```sh
python3 scripts/conform-host-protocol.py --suite messaging \
  --output /tmp/host-messaging-conformance.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
```

The messaging suite includes the 16 lifecycle checks, then exercises 17 more
contracts through `operation.call`, `delivery.report` and `inbox.release`:

1. A stored Unicode original is returned whole with one claim.
2. Another consumer's ACK is refused with `-32602`.
3. Native admission with a forged token is refused with `-32003`.
4. A queued report returns `acknowledged: false`.
5. The receiver can release its own claim.
6. The same original and body are recoverable after release.
7. A replacement claim has a different token.
8. The released token cannot ACK (`-32602`).
9. An admitted report with the exact current token returns `acknowledged: false`.
10. A resumed receiver cannot use its previous generation's token (`-32602`).
11. The admitted original remains recoverable after that generation change.
12. An ordinary inbox read omits the current consumer's owned claims.
13. A targeted `message_ids` read returns the current owned token.
14. A targeted read cannot read another conversation's original.
15. The new consumer's explicit ACK commits that message ID.
16. The consumed original is absent from the inbox.
17. A targeted read also omits that acknowledged original.

The isolated sender uses `wake: never`; this suite does not certify the native
queue, event timing, idle wake, priority, remote delivery or a human consumer.
`admitted` is a deliberate host report, rather than an observed native admission.
The recovery checks verify state through public reads, without inspecting files.

The actual server passed 29 checks in `blackbox-messaging-final.json`. The first
run expected a foreign ACK to return an empty list rather than a protocol error;
its failure remains in `blackbox-messaging-first.json`. The contract now checks
the actual refusal code explicitly.

A test proxy runs the actual server and injects three defects: consuming at
admission while still reporting `acknowledged: false`, reusing a released claim
token, and returning success for a foreign ACK. The suite rejects all three.
The automatic-consumption defect is detected by the missing original after
resumption, so changing a report field alone cannot satisfy that check. The
proxy is a test fixture and is not used by the external runner. These checks
still cover only this defined contract subset, not the full operations or
user-decision protocol.

## Host decision binding fixture suite

```sh
python3 scripts/conform-host-protocol.py --suite decisions --capture \
  --output /tmp/xsm-decisions.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
```

This suite includes the 16 lifecycle checks and 19 decision checks. It opens
isolated `user-decisions` participants and acts as an explicit host-answer
fixture. It does not ask a human, exercise native UI, or authorize real project
membership, permissions or deployment.

The public wire checks cover:

- A pending operation, question notification and host route refer to one question;
  the model-facing result excludes the private challenge.
- A foreign host, wrong challenge, changed display or unlisted choice cannot
  answer, and refused answers leave the decision pending.
- A valid answer is recorded with `host-user` source without applying the effect.
  Identical replay is idempotent and a changed answer cannot overwrite it.
- Retrying the original operation applies that recorded answer. Its answer-source
  ID cannot subsequently answer another question.
- Abandoning the display leaves a pending, unanswered decision; retry creates a
  fresh display, and the abandoned route cannot answer later.
- A closed host rejects a late answer, and a new participation generation cannot
  inherit the old answered decision.

The actual server passed all 35 checks (`decisions-wire-final.json`). Two isolated
fault servers skip the exact-display check or automatically apply the operation
after answer storage. The suite rejects each at its relevant invariant.
The fault servers are test-only and are not imported by the external checker.

The fixture checks application of the color decision record, not a domain
permission effect. Expiry, decline/cancel semantics, full native UI trust,
all domain operation effects, remote requester identity and complete independent
implementations remain outside this suite's current certification scope and
remain required by the overall plan.

## Targeted inbox recovery coverage

The messaging suite now has 33 checks; the events suite has 36. Both include
current owned-token recovery through `message_ids`, conversation isolation,
and exclusion after ACK. The wire proxy that silently removes this filter
fails at `targeted inbox returns current owned token`. These checks use only
the public stdio boundary, without importing xsm or reading server storage.
Captured runs are `inbox-owned-token-external-messaging.json` and
`inbox-owned-token-external-events.json` under `deliverables/protocol-foundation/`.
Earlier 29-check messaging results above describe the earlier suite. These
checks do not prove lease preservation; the canonical-state regression covers
that invariant separately.

## Upload preparation extension

`--suite uploads` adds the bounded preparation/copy/ACK checks described in
[file-uploads.md](file-uploads.md), including an actual 4 MiB bundle over public
stdio. It requires the advertised upload extension; the default lifecycle suite
does not certify it. Capture includes received base64 copy data, so keep fixture
artifacts local and use only generated, non-sensitive test bytes.

## Correlated questions and group ownership

`--suite questions --capture` exercises 32 checks: lifecycle plus correlated
single/group questions, scoped foreign-group refusal, partial/final answers,
explicit reply ACK, retained answer history, private-handle projection and an
existing-scope handshake. The participants are isolated protocol fixtures,
not people, native agents or a physical remote deployment.

A group's owner is checked before polling its child requests. Foreign queries
return a scoped refusal with no recipient/reply/claim data. Missing or vanished
groups return not-found without cancelling their child requests. An owned group
can still poll late answers after a terminal transport result.

Group reply claims are collected under each child's request ID and returned
both on that row and in the top-level aggregate. The common output path must
not claim them again under the group ID. Read the actual replies and explicitly
ACK the returned tokens; ACK does not erase the indexed history. A partial
answer or `replied` aggregate is not a final successful task outcome. Permission
or an existing collaboration scope does not complete a handshake without the
selected peer's correlated final reply.

The output schema checker validates the per-operation
[question result schema](question-result.schema.json) and its association checks
in this capture. See [question semantics](question-results.md). Passing the suite
does not certify human approval, physical remote/native delivery or whole runtime support.

## Host publication and selected-pair permission

`--suite selection --capture` runs 28 lifecycle/selection checks with synthetic
host answers. It verifies publication versus messaging permission, sealed foreign
host refusal, answer storage before explicit retry, a live selected-peer handshake,
withdrawal and fresh publication approval, denial and UI-less fallback. This is
not a real person or a native UI certificate.

MCP elicitation and host user-decisions share the coordinator. CLI callers keep
the existing input-consent path. The permission scope binds exact native endpoints
and the domain revision; display names do not renew denial or retarget approval.
Repeated hidden withdrawals are no-ops and do not renew permission. A real
published-to-hidden transition requires fresh approval before publishing again.
An unknown started application requires inspection rather than replay.

## Decision status contract extension

The current `decisions` suite has 45 checks, extending the earlier 35-check
sample with owned history/listing, foreign read refusal, cancellation semantics
and separate pending/closed legacy consent markers. The
[decision status result schema](decision-status-result.schema.json) validates
these observations. The checker does not turn source labels, display complete,
OS-call success or a recorded result into fresh permission.

## Worker grant issuance

`--suite grants --capture` runs 24 checks including lifecycle and synthetic host
approval. It observes no applied issuance before retry, structured scope,
original snapshot preservation on replay, journal application and denial.
It neither starts a worker nor applies full-access/trust-hooks to a runtime.
[Grant result definitions](grant-result.schema.json) describe issuance metadata,
not current usability or runtime capability. Actual consumption must validate
the stored grant and remains one-use. Removing producer data or changing an ID
on replay fails the public suite. Text-only legacy outcomes do not establish an
issuance receipt for a structured client.

### Individual worker permission answers

`--suite approvals --capture` checks pending questions, allow/deny snapshots,
exact request persistence and allow replay through real stdio. It seeds synthetic
worker records in the isolated state directory and inspects their answer status;
this suite is not storage-independent participant certification. It launches no
worker and certifies no native UI, actual person, or execution effect.
The offline [approval schema](approval-result.schema.json) validates these wire
results and rejects unknown/private fields and malformed request identifiers.

The `decisions` suite requires an explicit unrecorded answer receipt when there
is no team. The `collaboration` suite requires a recorded decision receipt equal
to the persisted public board projection and unchanged on retry. Fault proxies
that remove the receipt or flip `recorded` must fail the recorded-receipt check.
These remain synthetic host answers, not real-user UI certification.

`--suite scopes --capture` creates two isolated git roots. It checks link/unlink,
session reach/revocation, project join/leave and host denial through stdio. Actual
send operations must be refused before application and after revocation, and
stored while the scope is active. The checker injects no global permissions,
launches no model and uses synthetic host answers. Wire proxies that erase the
scope receipt, replace its root, or report an active revoked link must fail.

`--suite endorsements --capture` adds an agent-authored document node, collects a
synthetic host answer, applies an immutable human endorsement child, verifies its
body/parent/tag and then renders it. Answer storage alone must add no node;
replay must preserve the receipt without duplication, and denial must not add an
endorsement. Missing receipts or wrong parent ids are deliberate failing proxies.
No actual user UI, native model or remote synchronization is certified.
