# Common operation services

CLI, MCP and the public host protocol share team orchestration through
`xsm.team_service.execute`. Transport adapters provide the authenticated caller,
parse input, collect a user decision when requested, and render their existing
output. The shared service resolves a target, checks membership/lead policy,
performs the mutation, and publishes the resulting team state. A model argument
cannot supply its own approval receipt.

`authorize(action, team, subject)` is a trusted frontend callback. It must return
the actual approval source or refuse; omitting it never grants a user-required
change. A pending host question unwinds before the mutation and is retried only
through its existing scoped decision controller. CLI terminal consent and MCP/
host decision binding remain their own frontend contracts.

The team result is internal structured data; CLI and MCP output shapes are
preserved. CLI team leave now publishes the changed record as MCP already did,
so remote members do not keep the old membership solely because of the entry
point. Publication failures remain explicit sync notes; local mutation is not
proof of remote receipt.

Other operation families still need their corresponding CLI service extraction.
This shared team path does not establish completion of that larger requirement.

## Board actions

CLI and model hosts use `xsm.board_service.execute` for show, set, log,
decisions, mute/unmute and sync. Membership is checked before reading decisions
or publishing nodes. The model interface now exposes decisions and sync as
well as the existing actions; it does not expose the terminal-only human
`board decide` route. Actual user answers still use the decision controller.

A decisions listing checks membership without rendering the whole board. The
old CLI used `board.show` only as an authorization check, which marked unseen
item versions as read. A following set could then replace another member's
version that the caller had never seen. The common path preserves that unread
version beside the new one until it is actually read and reconciled.

## Result framing

The shared operation catalog also declares which operation/actions return JSON.
Structured team and board reads carry passive inbox annotations as JSON fields.
The host protocol preserves a text operation verbatim in a text envelope instead
of interpreting JSON-looking display content as machine result fields. CLI and
MCP display behavior remains in their adapters.

## Send and attachment preparation

`xsm.send_service.execute` now orchestrates single-recipient and group sends for
CLI and model hosts. The CLI still reads its own stdin/text-file arguments and
renders its existing exit codes; the model host still supplies its exact caller
context and structured inline attachment data. Neither transport duplicates the
send policy, request-ID selection, material preparation or multi-send dispatch.

CLI path reads are selected by a trusted adapter parameter. A field in model
arguments cannot choose that authority. Attachment preparation is also shared
with question sending. Frozen material intent conflicts are detected before a
second send, and CLI group resend continues through the owned group recovery
path. Full legacy CLI extraction beyond these families remains in progress.

## Questions, handshakes and status

`xsm.question_service` shares ask/connect/status orchestration across the CLI,
MCP and host protocol. It normalizes group targets, prepares frozen materials,
selects the handshake peer, and reconciles existing question/network state.
Frontends supply their authenticated caller, wait budget, cancellation observer
and input pump; rendering and consumption claims remain frontend responsibilities.
Cancelling a wait does not cancel the peer task or acknowledge its original.

The selected local handshake is addressed by its complete opaque conversation
address. A name reassigned during selection cannot redirect the subsequent
question. Teams still follow their name membership when choosing the current
member, then address that exact conversation. Legacy short refs remain accepted
with collision refusal. These addresses are selectors, not authorization.

## Document nodes

`xsm.doc_service.execute` handles add/render/log/next/leaves/show for CLI and
`xsm_doc`. Relative model paths use the authenticated conversation's working
folder; CLI paths retain the shell's folder. Nodes are immutable and parents
must exist in that document. Next is informational, ordered by creation; it
does not assign work. Its text and structured fields use one node snapshot.

A model host derives an agent author from its authenticated session, even if the
host process is attached to a human terminal. Neither arguments nor a missing
runtime environment marker can make it a human author. The CLI may provide its
own verified human/verdict author through an internal parameter. Endorsed nodes
still require the existing `xsm_doc_endorse` user-decision route. Guessed model
callers are refused before document reads or writes.

`xsm_doc` returns `{node}` for add/show, `{nodes:[...]}` for log/leaves,
`{text,nodes:<count>}` for render, and the existing next fields plus `text` for
next. Passive inbox fields may also be present. Render writes the generated
file; it is not a read-only preview. These are local file operations, not proof
of remote document replication or every native runtime's validation.

## Handover selection and mutation

`xsm.handover_service.execute` shares show, target selection, validation and mutation.
CLI and model frontends retain their own real user-verdict collection and display.
An absent/empty/non-string approval source cannot move a place. After the user UI
returns, the service rechecks the exact selected opaque conversation address; it
neither follows a reassigned name nor transfers to a successor that has stopped.
Existing teams, board ownership, questions and unread-original migration still use
the established handover engine. This does not implement remote handover or certify
native UI collection.

## Owned worker actions

`xsm.owned_service.execute` shares create/status/retry/reconcile dispatch and run
request-ID selection. CLI synchronous execution and MCP wait/cancellation pumping
remain frontend responsibilities. The MCP path submits the durable request before
starting its existing background execution; a cancelled waiter still does not stop
that request. CLI/MCP replay the same journaled ID and recover the same saved reply.
This refactor does not add native runtime providers beyond the existing ones.

## Project membership, links and session reach

`xsm.scope_service` prepares a frozen project root before the frontend collects
its existing typed consent or real user decision. CLI join/leave and xsm_join
share membership application. CLI link/unlink and xsm_link share link writes;
CLI reach and xsm_reach share session-bound reach writes and removals. A widened
scope is still authorized by the frontend's existing decision controller, not
by a model argument or a service-generated approval.

Before applying an approved join, leave, link or reach, the service checks the
prepared folder's current project root again. A changed root requires a fresh
decision. Reach preparation copies the selected holder fields so frontend
mutation cannot redirect the stored grant to a different conversation. Existing
config policy validation and session-bound reach storage remain authoritative.
This extraction does not add native runtime UI or worker providers.
