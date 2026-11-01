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
