# Experimental owned native worker providers

`xsm_owned` and `xsm owned` share the durable owned-request service. The installed
catalog currently contains the legacy Claude/Codex paths and an experimental
Hermes 0.22.5 provider. This does not extend the classic `xsm spawn` pane/TUI path
or certify every runtime's workers. Pi/OpenCode/OpenClaw worker providers remain
unfinished parts of the full runtime plan.

## Admission and launch

The installation's `integrations/worker-providers.json` selects trusted provider
modules. Runtime arguments cannot supply Python import names, executable paths
or native control methods. Listing the catalog executes no provider. Imports are
serialized and isolated by installation/engine instance so concurrent first use
and different immutable roots cannot share partially initialized code.

Hermes requires an xsm-managed native profile, operator activation of its plugin,
and its native console on the operator's PATH or absolute `XSM_HERMES`. The
provider locates the native Python from the admitted console launcher (including
the standard quoted venv trampoline), or absolute operator
`XSM_HERMES_PYTHON`. It verifies Hermes 0.22.5 through both the console and that
interpreter. It does not choose an executable from a model-supplied home path.
The frontend path/hash and native interpreter are stored in the worker definition
and included in the request's frozen plan. Legacy plans without a provider field
keep their existing digest bytes.

A first turn uses the admitted workspace. Followups resume only the saved opaque
native conversation ID; Hermes IDs are not required to be UUIDs. Resume does not
override the native frozen cwd, route or model. No permission/trust bypass flags
are introduced. Native account/route configuration stays in the selected profile;
verification in this repository uses isolated subscription-proxy profiles.

## Pre-turn identity binding

Each admitted new native provider uses a private JSON-RPC socket descriptor
inherited by its one execution frontend. The model-facing operation catalog and
public host methods do not expose this channel. `native.bind` accepts only the
host-observed native conversation ID; the engine supplies the owner, request,
reservation and live child generation from the durable execution record.

The Hermes frontend calls the original native CLI entry point. Its only local
observer is `StreamJsonEmitter.bind_session`: after the native CLI creates or
resumes a session, and before its gateway view submits the model turn, the
observer waits for the private binding result. Native flag parsing, startup
consent, provider resolution, permissions, tools, gateway execution and terminal
result generation remain in the original CLI. The observer is scoped to the
frontend process and restores the native class on exit.

The engine rejects an ordinary existing conversation before accepting a fresh
binding. It durably fixes the native ID and records it in the owned index before
confirming the observer. Another context cannot borrow that ID. Caller depth is
matched by full runtime/profile/conversation identity, including the existing v1
protocol projection. A model cannot reset inherited depth by clearing an ambient
worker variable. Ordinary sessions in another profile do not inherit that budget.

A shared gateway receives no process-global worker label or control descriptor.
The Hermes model-tool backend uses the native profile's subprocess-secret scope,
sets its own profile home and drops ambient worker/control hints. Registration
identity and native UI replies remain separate authorities: binding a worker is
not a user approval, native input admission or consumption ACK.

## Results and recovery

The native stdout must contain an initialization event and one final terminal
result with integer exit zero, actual answer text and the bound conversation ID.
Invalid JSON, duplicate keys, non-JSON numbers, changed IDs, failed/incomplete
results and valid-looking output without pre-turn binding are not answers.
JSON inside the model's text cannot choose native execution metadata. Only the
existing common structured body/outcome convention supplies an explicit task
outcome; a completed model turn alone is not task success.

Requests are journaled before launch. A known preflight refusal records no model
execution; an uncertain started effect remains unknown. Lost controller/send
ownership is reconciled and the saved reply ID is reused. Replaying a stored
request or retrying its publication does not rerun the model. CLI process death
alone does not prove a gateway turn stopped.

`result-ready` can be observed between result storage and publication. It is not
proof that the sender thread ended. Structured status replies can include an
`incoming` packet: read it and explicitly ACK the returned claims. A second
ordinary inbox read omits claims already owned by that consumer; targeted
`message_ids` can recover the current owned token.

Idle logical services retain their admitted frontend runtime root even when no
child PID is running. Uncertain or corrupt reference metadata preserves cached
snapshots. Explicit service removal can release that reference; journals and
native results remain separate retained data.

The macOS native run, failure/recovery boundaries and remaining criteria are in
[native worker evidence](../plan/runtime-protocol/native-worker-boundary.md).
This is experimental installed-provider dispatch. Complete public third-party
worker extensibility, all native workers/UI/lifecycle modes, Linux native-model
runs and the full runtime/remote/messenger matrix remain unfinished.

## Node/Bun frontend control

The shared TypeScript control client uses the same inherited-descriptor protocol
as the Python frontend. The environment hint is removed on adoption; a changed
conversation, malformed confirmation, boolean ID, duplicate JSON member or closed
channel cannot establish ownership. The SDK and private client share strict JSON
member parsing while retaining ordinary JSON values and independent object keys.

The OpenCode binding awaits private control before its `chat.message` input hook
continues. Ordinary launches with no private descriptor retain their existing
path. Actual OpenCode 1.19.5 tests confirmed one scripted provider request after
acceptance and zero after refusal. The Bun descriptor path uses `net.connect({fd})`,
which is illustrated in [Bun's descriptor documentation](https://bun.sh/reference/bun/Spawn/BaseOptions/stdio);
the pinned runtime test is the evidence for this integration, rather than a claim
about every Bun release.

OpenCode is not yet registered as an owned execution provider. The current private
channel selects one owned native conversation. Native subagent lineage, admission,
launch/result/recovery and full worker/UI behavior must be completed before its
worker support is certified. Native descendant budget inheritance is also a
remaining explicit audit item across the new runtime providers; root owned-worker
budget evidence must not be generalized to every native delegation path.
