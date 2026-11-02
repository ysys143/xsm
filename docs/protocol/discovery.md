# Registered participants in local and P2P discovery

The directory accepts runtime slugs, not a list of individual new harness names.
Legacy Claude/Codex records retain their configured-home/native checks. Other
runtimes must have a current live protocol registration: the persisted identity,
private profile namespace, PID/start, execution generation and held conversation
lease must agree. A flag in an arbitrary record is not sufficient.

Protocol profile homes are virtual identity namespaces below the isolated xsm state
root, not permission to inspect a runtime's real configuration directory. Registration
does not add them to homes.json, publish a conversation, link repositories, or grant
communication to another project. Visibility remains an explicit publication or the
existing same-repository rule. UID, exclusions and deny policy still apply, including
at the final selection boundary.

Name and idle/busy observations come from session.open/update and are labeled with
protocol sources. Native transcript data is not guessed from another harness's files.
A closed conversation is not available merely because the shared host PID remains
alive. On resume the conversation address is stable, while the execution generation
changes. Selection rechecks the current registration and policy; same-PID replacement
during lookup must not silently reuse the previous execution.

P2P endpoints accept the same runtime slugs. Opaque machine/home IDs and the native
conversation field stay distinct; remote records still cannot carry private local
home paths. Protocol generation participates in remote execution binding. The legacy
native generation bytes remain unchanged for existing Claude/Codex records.

A P2P receive for a protocol participant stays in canonical storage for its host's
subscription/inbox and real native admission. The broker does not send it to a legacy
Codex queue because the runtime is unfamiliar. Queued, admitted, ACK, reply and task
outcome remain different observations.

The new fixture coverage includes two private services using actual QUIC and public
protocol actors: body/reply, explicit claims/ACK and accepted originals after same-
conversation resume. This is process/transport integration, not physical-machine,
real model, native UI, messenger or the full six-runtime matrix certification.

## Result structure and independent readers

[discovery-result.schema.json](discovery-result.schema.json) defines successful
`operation.call` results for `xsm_discover`. Correlate the response ID with the
operation request, validate the JSON-RPC envelope, then validate its `result`
against this schema. JSON-RPC errors use the separate output error envelope.
[Examples](discovery-result-examples.json) cover an empty result, mixed local
and authenticated remote candidates, and partial observations. Remote examples
are structures, not evidence of a physical-machine test.

The required top-level fields are `candidates`, `status`, `reason` and
`unanswered`. Status is `ok` or `unknown`. Unknown can contain usable candidates;
it must not be interpreted as a complete listing or proof that absent sessions
do not exist. `unanswered` values are positive probe counts or diagnostic
strings from the network boundary. Optional `inbox_pending`, `inbox_notice`,
`inbox_pending_known` and `inbox_pending_diagnostics` retain the common operation
diagnostics; they do not change discovery or consume messages.

Each candidate has an opaque `id`, selectable `target`, `handle`, runtime,
machine, display metadata and discovery basis. Local handles contain runtime,
session ID, opaque home ID and `machine: "local"`. Remote handles additionally
require the authenticated machine ID and execution `generation`; remote
candidates identify their authenticated-member origin and repository mapping
status. These IDs are not local paths. Use the returned target for selection
instead of inventing an address from a display name or short ref. Selection
still rechecks the current identity and policy; schema validity grants nothing.

`title`, `branch`, `summary`, `todo`, `activity`, `state` and `receive` are
observations with `value`, `status`, `source`, `timestamp`, `observed_at` and
`freshness`. An unknown observation has a null value. Source time can be a
native timestamp string, numeric time or null; `observed_at` is numeric sampling
time. Freshness is `fresh`, `stale` or `unknown`, separate from whether a value
is known. A cached name does not prove a current task. `receive: available`
is an observation, not proof of native queue admission or consumption. Todo
values are null or up to eight step/status objects, with optional `truncated`.

## Public discovery conformance

```sh
python3 scripts/conform-host-protocol.py --suite discovery --capture \
  --output /tmp/xsm-discovery-wire.json \
  --command /absolute/path/to/xsm/bin/xsm protocol serve --stdio
python3 scripts/check-protocol-schema.py \
  --wire-trace /tmp/xsm-discovery-wire.json \
  --output /tmp/xsm-discovery-schema.json
```

The discovery suite adds eight checks to the sixteen lifecycle checks. It uses
a private Git repository and two actual protocol participants, checks exact
local targets, privacy, observation provenance, work/branch filters and removal
after close. It does not publish sessions, connect repositories or send messages.
The schema checker validates captured discovery results and rejects missing
remote generations, private home fields and malformed observations. Physical
remote discovery, all native runtimes and native UI remain separate requirements.
