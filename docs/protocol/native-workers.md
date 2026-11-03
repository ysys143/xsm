# Experimental owned native worker providers

`xsm_owned` and `xsm owned` share the durable owned-request service. The installed
catalog currently contains the legacy Claude/Codex paths and experimental
Hermes 0.22.5, OpenCode 1.19.5, Pi 1.4.0 and OpenClaw 2026.10.9 providers. This
does not extend the classic `xsm spawn` pane/TUI path or certify every runtime's
workers. The full runtime lifecycle matrix remains unfinished.

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

OpenCode and Pi likewise require a managed profile and an operator executable
from PATH or absolute `XSM_OPENCODE` / `XSM_PI`. Their admitted binding hash and
runtime root are retained. OpenCode resumes the exact `ses_...` ID with
`run --format json --session`; Pi uses an exact UUID with `--session-id` and a
worker-specific native session directory. Neither selects the most recent
conversation or adds automatic permission/trust approval flags.

OpenClaw requires a managed profile and operator-selected `XSM_OPENCLAW` and
`XSM_OPENCLAW_NODE` paths, or their PATH equivalents. Native `agents.list` supplies
the default agent; explicit `XSM_OPENCLAW_AGENT_ID` must match a native roster row.
A selection-required roster is not silently replaced. The public native SDK owns
profile/auth/transport policy. Fresh sessions use an empty `sessions.create` and
native-assigned key/ID before private binding; resumes resolve the exact saved ID
then describe that key. No default-list page or most-recent selection is used.
Agent admission retains exact native ID and lifecycle revision constraints.

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

Hermes stdout must contain an initialization event and one final terminal
result with integer exit zero, actual answer text and the bound conversation ID.
OpenCode requires the bound session, actual text and a final `step_finish` whose
reason is `stop`. Pi requires the exact session header, a final assistant `stop`
answer, `agent_end(willRetry=false)` and `agent_settled(aborted=false)`. In
particular, Pi can exit zero after an input was handled without a model turn;
process exit alone is insufficient.
OpenClaw validates the bound native admission and completed run/turn/session
receipt with its actual terminal reply. Its stdout can have a bound-context JSONL
record followed by one final record; their context, epoch, locator and run must
agree. A bound record alone is neither model admission nor an answer. Legacy
single-object final output remains readable.
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

Pi binds at its native `input` boundary and returns `{action: "handled"}` when
binding fails. A hook exception alone is insufficient because Pi logs it and
continues. Its additional `before_agent_start` check requests `ctx.abort()` on
refusal. Actual SDK/CLI counter fixtures verify acceptance reaches the provider
boundary and refusal does not. These are not real model-inference results.

Hosts may negotiate `native-lineage` and provide their observed
`parent_conversation` when opening a native child. This retains an owned budget
without transferring repository scope, team membership or approvals. Missing or
cyclic ancestry refuses worker operations. Hermes native children have macOS
execution evidence; root-worker evidence must not be generalized to every native
delegation path or operating system. See the linked evidence for exact limits.

## Cancellation

`xsm_owned` with `action: "cancel"`, `name` and `request_id`, or
`xsm owned cancel <name> --request-id <id>`, records sender- and worker-specific
cancellation intent. Only the request's original native sender may cancel it;
repository scope alone does not authorize cancelling someone else's request.
Queued/reserved work can be proven `cancelled` before execution. Process creation
and its durable child record share a journal lock; cancellation cannot pass
between them. An execution-side observer of prior intent records `not-started`
without creating the child. A private native binding also refuses pending intent.

Recording intent alone does not prove native quiescence, roll back effects or
synthesize a reply. Inspect the returned `cancellation` and subsequent status:

- `status: requested`, `native_state: unverified`: intent is durable; no stop claim.
- `status: not-started`, `native_state: not-started`: execution was prevented;
  the request itself is `cancelled`.
- `status: native-stopped`, `native_state: stopped`: the bound frontend observed
  native quiescence. The request can still be `unknown`, with no result or reply,
  because interruption does not resolve possible side effects.

`native_supported` describes the admitted execution plan's running-turn support.
Pi 1.4.0, OpenCode 1.19.5, Hermes 0.22.5 and OpenClaw 2026.10.9 newly admitted bindings support this confirmation. Other current providers
can record intent and cancel pre-launch work, but their running native stop paths
remain unfinished. Do not treat an unsupported pending request as stopped.

The private descriptor adds `native.cancellation` with empty parameters and a
strict boolean `requested` result. `native.cancelled` reports only its bound
`native_session_id`; the engine verifies a pending request, reservation, live PID
and start generation before durably acknowledging it. These are not model-facing
methods or a human decision channel.

Pi polls the private state while its native turn runs, calls its native abort API,
and reports only a matching `agent_settled(aborted=true)`. Normal completion and a
changed conversation do not produce a stop confirmation. CLI exit alone cannot
confirm a detached gateway stopped; an unknown cancelled request retains capacity
until native confirmation. A completed stored result is preserved if completion
won the race with cancellation.

OpenCode uses the bound input message ID and the latest native assistant with that
same parent. It aborts through the native session API and confirms only a completed
`MessageAbortedError` together with native idle. A newer assistant for another
input is not selected. Disposal gives an in-flight abort/report a bounded grace
period before closing the private channel.

OpenCode can exit zero without printing its own abort error. After observing the
native conditions, the binding therefore writes a distinct `xsm_native_cancelled`
observation before requesting the private acknowledgement. This is an xsm host
observation, not a synthesized OpenCode error or model answer. Its source, bound
session, native input/assistant IDs, completion time and idle flag are validated
by the cancellation parser.

Hermes records the admission returned by its original finite submission. The
observer pins that receipt's authority epoch/ref and uses the exact admission's
`execution_generation`, never the view's latest generation, for `session.interrupt`.
Queued work uses `prompt.cancel`. Confirmation requires that same admission's
terminal receipt; started work additionally requires its stored native execution
result to say `interrupted=true`. Administrative resolution of unknown work is
not sufficient. A queued cancellation with no execution generation is recorded
separately as native not-started. No shared gateway process is killed.

OpenClaw uses `chat.abort` with the exact native run and canonical key. Started
work requires its final `rpc` stop, matching session/revision/last-run identity,
settlement times and native inactivity. Accepted queued work instead requires
explicit native `providerStarted=false`, no start time, an accepted exact abort
and the unchanged session incarnation with no active run. Before agent submission,
the controlled frontend can record that it did not submit the task. These phases
remain distinct. Acceptance alone or a generic provider error proves no stop.

Cancelling a waiting transport still does not cancel its saved owned task.
Service removal refuses queued, active, unpublished or unconfirmed work. An
explicit stop may remove only the logical service metadata after native cancellation
is confirmed and the child has exited, while retaining unknown task effects,
journals, native profiles and original output. Submission/reservation and removal
share the service lock; a stale worker generation cannot launch after removal.
Retained status is authorized by the original sender even when another owner
later reuses the display name. Native stop/recovery for
the other runtimes remains an incomplete part of the full plan.

For Pi, OpenCode, Hermes and OpenClaw, `reconcile` can recover a lost stop confirmation after the execution child
has exited. Pi parses the retained native session header and final
`agent_end` / `agent_settled(aborted=true)` pair; OpenCode parses its typed abort
error or validated xsm observation. Hermes uses its typed admission/generation
observation and actual interrupted-result or queued-withdrawal proof. The engine reads only its exact
owned output through no-follow directory/file descriptors, checks the file owner,
reservation, bound PID/start identity and context generation, and records
`cancellation.recovered_from: "native-output"`. Running children, symlinked
files/directories and mismatched native IDs are refused. File-only normal result
recovery still requires a successful exit. Cancellation-only parsers may declare
`CANCELLATION_EXIT_CODES`: OpenCode's observed abort exits are 0 and 1, but an
arbitrary exit-1 API error is not stop evidence. Hermes permits its native 0/130
exits only with receipt evidence; Pi retains its exit-zero requirement. These
codes never authorize a business answer.

OpenClaw permits 1/130 only with its validated native stop observation. Its bound
header and final marker must agree; neither an exit code nor a partial header
substitutes for that proof.

This does not execute another native turn, manufacture an answer, or clear unknown
side effects. The task can remain `unknown` with null result/reply while its native
stop is confirmed and its physical execution slot is released. Repeated readback
preserves the same confirmation. Providers may implement the optional
`cancellation_result(worker, context, output)` parser; common ownership and safe
output access remain in the engine.

## Native host result recovery after frontend loss

An admitted provider can declare `execution_lifetime: "native-host"` in its frozen
descriptor. For a bound unknown request, frontend exit then does not release its
execution lease before completion or native stop is confirmed. Child-owned
providers retain the existing dead-child slot behavior. Unknown effects and the
recorded child execution state remain separate from native-host activity.

OpenClaw fsyncs its bound context/epoch, native locator and intended run ID before
submitting the native task. On explicit `reconcile`, the engine can invoke the
optional installation-local `recover_result(worker, context, output, execution,
env)` hook when both the provider and frozen descriptor declare result recovery
protocol 1. This is not a public host method or a model-controlled code path.
`RESULT_RECOVERY_EXIT_CODES` selects eligible observed frontend exits for the
query; a nonzero exit itself still proves no answer.

The engine first verifies the original native binding, exact PID/start identity,
proven child exit and anchored owned stdout file. The provider checks the bound
record against the immutable execution argv and original context generation.
Environment handling uses the common admitted-profile and billing-key policy.
No original task body is resubmitted.

OpenClaw queries only the original `agent.wait` and exact `sessions.describe`.
Recovery requires a completed native receipt for the same run/turn/session, the
original lifecycle revision and workspace, and actual reply text. Pending or
unconfirmed observations retain unknown state. Successful recovery preserves the
original child exit and records `execution.recovered_from: "native-host-status"`
before normal durable publication. The native turn's completion alone does not
declare task success. Missing historical run/revision evidence is not fabricated.

Frontend-loss recovery while the native host remains alive has model0 native
and [macOS subscription-model evidence](../plan/runtime-protocol/openclaw-subscription-model.md).
The full runtime/UI/model/messenger matrix remains unfinished; see the
following sections and evidence notes for exact restart and settlement scope.

### Persisted transcript recovery after gateway restart

The pinned OpenClaw gateway can lose `agent.wait` receipts on restart while its
session and canonical transcript remain durable. A timeout is never itself
completion. Recovery first requires the original session/key/agent/revision and
workspace with the same last run, `done`, no aborted run and no active work.

It then reads public `chat.history` pages back to that run's canonical input.
Native input idempotency metadata and the assistant's persisted
`__openclaw.runId` must identify the original run; message text cannot supply that
identity. Exactly one complete final assistant message must follow the input on
the same transcript source with increasing native sequence positions. Truncated,
ambiguous, partial or different-run messages are refused. Pending input or a
changed execution/history snapshot also prevents recovery.

The provider rechecks the original closed session after the read. Evidence names
the native input/assistant message IDs and transcript source with
`source: "native-chat.history"`; it does not fabricate a terminal receipt or pick
the latest unrelated assistant text. The original task is not resubmitted.
Gateway restart after completed native execution has model0 and macOS
subscription-model evidence. Interrupted
native work during restart and the full UI/model/messenger matrix remain unfinished.

Persisted failed runs can close only their lease after restart. The original
input must precede one native-owned failure occurrence on the same transcript
source and with increasing native sequence positions. Supported occurrences are
the native custom `run-failed-before-reply` and the host-generated assistant
`:terminal-error` idempotency record, each bound to the original run. An error
sentence or an ordinary assistant message is not sufficient.

The closed failed session identity/revision, last run and inactive state must
remain unchanged before and after reading. Occurrence ordering is checked against
its native lifecycle: the custom notice follows the failed interval; the terminal
assistant error is persisted within that interval. No arbitrary clock tolerance
is used. The observation retains IDs and kind, not error text; task state stays
unknown with no result/reply and no manufactured cancellation.

## Native execution settlement without an answer

A result-recovery provider can instead return an observation with
`native_evidence.native_state: "settled"` and no `body` field. This closes only
the execution lease. The engine verifies the original reservation, exited bound
child and current context generation again before storing `native_execution`.
It does not create a cancellation request, model answer or task outcome.

For OpenClaw native failures, an exact final error observation must agree with
the session identity/revision, last run, inactive state and closed execution
interval. Native session end and final job settlement can have different times:
the session interval must be contained within that run's final interval, without
an arbitrary time tolerance. Retryable/yielded/pending observations do not qualify.
Provider error text is not retained in the observation or published as a reply.

The request remains `unknown` with null result/reply, and its work context stays
fenced. Its execution slot can be released. Repeated reconciliation retains the
same observation. Explicit service removal may then remove only metadata while
preserving journals, native profiles and unknown effects. Missing or changed
binding/generation evidence cannot authorize this transition.

## Public observations and operator-only process control

Model-facing owned results expose task/context/reply facts, not the backend
journal. A native execution that settles without a task answer may return
`native_execution` with only state, observed_at, native_session_id and
context_epoch. State `settled` releases the execution lease while task status
remains unknown with null result/reply. Cancellation readback may identify
`recovered_from: "native-output"` without exposing its raw process evidence.

Child PIDs, process start keys, argv/output paths, reservation tokens, provider
configuration and raw native evidence remain private. Native test operators
read those only through an observer bound to their isolated state root, parent
ref and immutable service id. The model result cannot select an OS process.
Linux owned process keys use boot identity/start ticks; termination rechecks the
recorded generation before each signal and while waiting. Unknown/reused PIDs
are not signalled. Legacy process records keep their supported comparison path.
