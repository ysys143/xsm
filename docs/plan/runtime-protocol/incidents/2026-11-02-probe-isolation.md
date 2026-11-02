# Standalone conformance probe isolation failure

A coordinator-written standalone stdio probe supplied PATH/LANG/TMPDIR to the
public checker Peer but omitted HOME and XSM_HOME. The shell launcher therefore
used the account's real default state directory. This was a coordinator error;
the run is not valid isolated-test evidence.

The identified footprint is three ended `contract-fixture` sessions, two
acknowledged fixture messages, two outgoing attachment bundles and one incoming
bundle. An exact-path/hash manifest identifies 36 fixture-owned files proposed
for reversible quarantine. The global file-store lock, shared logs, prune stamp
and existing consent records are excluded from that proposal. Runtime source,
credentials and native profile settings were not changed by the probe's
requested operations. The actual state configuration file had no modification
time in the observed execution window.

Opportunistic housekeeping was called on the CLI startup path, and the prune
stamp was updated in the same window. There was no pre-run state copy or
per-deletion journal, so the scope of older records pruned in that window cannot
be established. Consent recent-record and shared telemetry changes cannot be
rolled back by guessing their earlier values. No consent text is reconstructed
from conversation history. Current modern handoff originals are protected by
the housekeeping implementation; this is not proof about every older record.

`unisolated-probe-impact.json` under the private deliverable directory records
the metadata audit, fixture IDs, exact cleanup candidates and uncertainty.
The user explicitly approved quarantine of the exact 36 files. Each hash and
UID-private regular-file identity was rechecked before moving. All 36 moved
with matching hashes, and none remained at the original exact paths. The
quarantine manifest retains their paths and modes for conflict-safe restoration.
Shared logs, prune stamp, existing consent records and the global file-store
lock were preserved. This does not establish rollback of any older pruning.
The two original wire artifacts are retained with `public-inbox-wire-isolation-invalid.json`
marking them invalid as isolation evidence.

The public checker Peer now requires explicit absolute HOME and XSM_HOME below
its fixture working directory before spawning a candidate. Missing variables or
paths outside that directory fail before Popen. This guards accidental misuse;
it is not a sandbox against a candidate that ignores its environment. The
regression reproduced the unsafe launch path before the guard; the full public
checker regression then passed 14 cases. A new explicitly isolated run passed
file-copy retrieval, body-only fallback and explicit ACK, with 12 actual wire
responses including three schema-validated inbox packets.
