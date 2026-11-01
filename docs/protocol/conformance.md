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
