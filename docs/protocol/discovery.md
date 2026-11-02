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
