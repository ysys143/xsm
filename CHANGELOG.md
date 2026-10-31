# Changelog

What changed in xsm, newest first. Each released version's full notes, with its verification and upgrade
steps, are on [GitHub Releases](https://github.com/ysys143/xsm/releases) (in Korean).

## [0.5.2](https://github.com/ysys143/xsm/releases/tag/v0.5.2) - 2026-11-01


Update a plugin install with `claude plugin marketplace update xsm` and `claude plugin update xsm@xsm`
(Codex, in each home: `codex plugin marketplace upgrade xsm`, then `codex plugin add xsm@xsm`),
and a direct install with `xsm install --refresh` from an updated checkout. Open a new session afterward:
already-running sessions keep their old hooks and MCP server. Codex can require hook review after a plugin
content change; `xsm doctor` cannot verify that content trust.

- One answer, one request ([#25](https://github.com/ysys143/xsm/issues/25)). Every refusal gives the ask's mark,
  `[xsm:<id>]`, for the head of the question. A question-tool answer reaches the ask its question names, by id, mark
  or target, question by question; a plain reply binds when one decision is open or when it names one. An answer
  that binds to nothing approves nothing, `--reply` cannot use it, and the next run shows it once. A question asked
  before its ask counts once, by name. Replies an older hook wrote to several asks pass neither. `--reply` takes words
  from before the ask only if they name what is being decided, and cannot replace an answer the hook kept.
- `xsm decision-status --pending-consent` lists open asks and unbound answers, `--drop-consent <mark>` closes one
  (MCP `pending_consent`, `drop_consent`). Codex is told `request_user_input_async`, never the synchronous tool.
- Recover permission replies inside the same MCP operation. Verify exact native question evidence for
  team decisions and record `native-user` separately. Persist application start and refuse uncertain replay.
- A Codex worker in an untrusted folder asks its parent again: Codex 0.165 reworded its trust screen, the screen went
  unseen, and the worker died. Workers pass `CODEX_HOME` to their MCP server.
- Redirect unattended questions to the parent or lead, recognising a worker by its record too, so Codex and owned
  workers are covered and `xsm_connect` and `xsm_publish` no longer leak past it. Deduplicate worker permission hooks by native
  invocation ID, observed in worker-local hooks before transcript flushing; preserve deadlines and denial notices.
  Global hook registrations and worker permission rules are unchanged.

- MCP tool annotations let Codex never reach the permission server. In on-request, this removes Codex's
  extra tool-call confirmation for the permission tools; xsm still requires the user's answer on the server.
- Known limit: a Claude session moved to the background during a conversation can lose its xsm registration.
  Its cause remains unresolved; a newly started `claude --bg` job was verified separately (TESTPLAN §15).

## [0.5.1](https://github.com/ysys143/xsm/releases/tag/v0.5.1) - 2026-10-31

Update a plugin install with `claude plugin marketplace update xsm` and `claude plugin update xsm@xsm` (Codex:
`codex plugin marketplace upgrade xsm`, then `codex plugin add xsm@xsm`), and a direct install with
`xsm install --refresh` from an updated checkout. Sessions that were already running keep the hooks and MCP
server they started with; open a new session to use 0.5.1. Codex 0.165 asks to review the hooks again after the
plugin's content changes: open Codex in that home and trust them in `/hooks`. `xsm doctor` cannot see this and says so.

Two ways to talk, no third: a DM moves someone, a team board holds what is true for the whole team. The channel
is gone.

### Added

- **Several recipients** (ADR-0025). `xsm send A B C` and `xsm ask A B C` (MCP `targets`) send one DM or question
  to each under its own id and tell each who else got it. A recipient outside your scope is skipped and named; the
  others are sent. The exit code is the worst recipient's. `--resend <group id>` and `question-status <group id>`.
- **Teams** (ADR-0025). `xsm team` / `xsm_team`: named sessions with an optional lead. A session may be in several
  teams, and members may DM each other across projects and machines. `team:<name>` (or `#name`) addresses every
  running member. A lead adds and removes sessions of its own project; any other add, and naming the lead, are the
  user's. `xsm connect` now makes a team of two. Teams replicate to the machines of their remote members.
- **Team boards** (ADR-0026). `xsm board` / `xsm_board`: one entry per item, owned by xsm doc, at
  `~/.xsm/teams/<team>/BOARD.md`. A write builds only on the versions its writer has read, so a version nobody read is
  never buried: both show until someone who read them settles it. A direct edit of the file is taken as a node.
  Nodes replicate to remote members. Each member's next prompt gets one line naming what changed, once
  (`xsm board mute` turns it off).
- **Decisions beside the board** (ADR-0026). `xsm_decide` with a team, or the person's `xsm board decide`, records the
  user's answer under its own id. A node that only names a decision shows "not confirmed". Decisions from another
  machine are shown as that machine's testimony.
- **Handover** (ADR-0025). When the user says "hand over to OO", `xsm handover` / `xsm_handover` moves the session's
  team places and lead's seat, `owner/<name>` board items, unread DMs, pending questions and a context summary to the
  successor, which reads them at its next prompt. DMs and answers to the old address reach the successor, on
  this machine and from other machines, whose question records accept the successor's answer.
- Skill guide `teams.md`: DM or board, approvals through the lead, keeping a status file beside the board, handing
  over, and filtering a large change with a haiku subagent (S12c met the user's criteria; low-effort luna did not).

### Removed

- **The channel**: `xsm post`, `xsm channel`, MCP `xsm_post`, `xsm_channel` (ADR-0005 is superseded). `install --refresh`
  removes their allow rules. Existing posts stay in `~/.xsm/channels/`; nothing reads them now.
- `xsm_decide` without a team records beside the board of the one team the session is in, refuses if it is in several,
  and in no team returns the answer and says it was not recorded.

### Fixed

- A plugin MCP server took `~/.codex` for its home, because Codex passes it no `CODEX_HOME`, and refused its own thread
  in any other home ("not registered yet"). It now reads its home from its own path.
- `xsm ack` and `xsm_ack` take a claim object as shown, and the receive context shows the exact form.
- A session name with a line break could add a forged head line to a doc node.

### Known limits

- A Claude background job (`claude bg-spare`) is not found by xsm, so tools that need the user's answer are refused there.
- A machine that was off when a handover was published does not accept the successor's answer; there is no resend.
- One reply to a yes-or-no request is attached to every request open in that session, so it can pass more than one
  (present since before 0.5.0; fixed after 0.5.1, [#25](https://github.com/ysys143/xsm/issues/25)).

## [0.5.0](https://github.com/ysys143/xsm/releases/tag/v0.5.0) - 2026-10-30

Merged in #20 and #21. Update a plugin install with `claude plugin marketplace update xsm` and
`claude plugin update xsm@xsm` (Codex: `codex plugin marketplace upgrade xsm`, then `codex plugin add xsm@xsm`),
and a direct install with `xsm install --refresh` from an updated checkout. Sessions that were already running
keep the hooks and MCP server they started with; open a new session to use 0.5.0.

The concept moves from "address a session and put a message in it" to "find a peer by its work, connect to
the one you pick, ask it, and get the actual answer back with evidence". Everything that worked in 0.4.20
still works: no command or flag was removed.

### Added

- **Work discovery** (ADR-0017, ADR-0024). `xsm publish` (`--off` to withdraw) makes a conversation
  discoverable, only on the user's word. `xsm discover` (`--machine`, `--work`, `--branch`) lists the
  candidates: published sessions plus sessions in the same Git repository, linked worktrees included. Each
  shows machine, runtime, name, repository, branch, work summary and state, with each field's source and
  freshness; unreadable values are reported as unknown. Discovery grants no permission. MCP: `xsm_publish`,
  `xsm_discover`.
- **Selection and handshake** (ADR-0024). `xsm connect <target>` connects exactly the conversation the user
  selected, not its folder or the other candidates. The handshake is complete only when that peer replies with
  `outcome=succeeded`; a failed outcome is a decline, and no reply leaves it unconfirmed. `--request-id`
  resumes the same handshake. MCP: `xsm_connect`.
- **Correlated questions** (ADR-0016, ADR-0018). `xsm ask` returns a request ID at once (or waits with
  `--wait`); `xsm question-status <id>` collects the answer later, including late and partial replies, and
  `question-status` with no ID lists your own requests after a lost response. A lost response is recovered
  under the same ID, never resent under a new one. MCP: `xsm_ask`, `xsm_question_status`; MCP waits are capped
  at 60 seconds.
- **Acknowledgement** (ADR-0018). Inbox reads and answers come with claim tokens; `xsm ack` / `xsm_ack`
  marks them read. Until then the original stays recoverable; after it, the original is kept but not delivered
  again. Results report how many messages are still pending for the conversation. Stored, delivered,
  acknowledged and answered are reported as separate evidence.
- **Quiet delivery**. `send --wake never` and `ask --wake never` store a message without queueing or waking the
  peer; it is read at the peer's next natural turn.
- **Attachments** (ADR-0019). `send` and `ask` take `--attachment PATH`, snapshotted with the CLI's own read
  permission; MCP takes only content the agent has read. Receivers read copies with `xsm files` / `xsm_files`.
  Retries reuse `--manifest`; a revision takes a new request and `--previous-manifest`. A peer without file
  support is refused unless `--attachment-fallback inline` is given. Defaults: 1 MiB per file, 4 MiB and
  16 files per message, 256 MiB of copies, 7 days.
- **Recorded human decisions** (ADR-0020). Questions to the user and their answers are kept word for word;
  `xsm decision-status` / `xsm_decision_status` recovers or withdraws a pending question. A peer message is
  never the user's approval.
- **Owned headless workers**. `xsm owned create|run|status|retry|reconcile` / `xsm_owned`: each request is
  journaled before the worker starts, contexts are partitioned by sender and unit of work (`--work`,
  `--fresh`), and a stored answer can be recovered or republished without rerunning the model.
- **Opt-in P2P network** (ADR-0021). `xsm network build|init|invite|join|members|status|start|stop|configure|
  remove|revoke-invite|leave|sessions|map-repository|requests|export|archive`, with the Rust engine in
  `native/xsm-net` (iroh). Machines join with device keys and a private invitation file (single-use or
  expiring), with no xsm account and no SSH setup. Every active member can invite and remove; there is no admin
  tier. A public relay is the default, a self-hosted relay can be configured, and a Tailscale address can be
  added as another path. Same-repository discovery across machines needs an explicit mapping on both sides.
  Your own outgoing originals stay recoverable after stopping the service or switching networks. Joining
  grants no session permission. Guide: [docs/xsm/NETWORK.md](docs/xsm/NETWORK.md).
- **Traffic control** (ADR-0022). Traffic is observed per sender and recipient. `traffic_control` in
  `~/.xsm/config.json` throttles only with explicit limits (`mode: strict`, `window_seconds`, and
  `max_messages` or `max_same_body`); there are no built-in blocking numbers.
- **Documents**: ADR-0015 to ADR-0024, the [collaboration plan](https://github.com/ysys143/xsm/blob/ab8f173a90172f8564196467c5d952173ecaaacc/docs/plan/collaboration/execution.md)
  with its acceptance criteria and evidence ledger, and recorded runs under `deliverables/`.
- **Evals**: `work-with-another-machine` (an agent explains joining a network without SSH).

### Changed

- The skill's guide is split by purpose (`sessions`, `permissions`, `channel`, `network`, `workers`,
  `troubleshooting`), and `references/guide.md` is a table that names one file per task. `SKILL.md` links the
  network guide directly, its usage reply lists every command `argument-hint` offers (`network` included), and
  its description mentions other machines without naming a file. Tests check these stay in agreement.
- The installer's Claude allow list adds `connect`, `ask`, `question-status`, `decision-status`, `discover`,
  `ack`, `files` and `owned`, and the matching MCP tools. `publish` and `network` are not added and stay with
  the runtime's permission check.
- `send` gained `--request-id`, `--wake`, `--attachment`, `--manifest`, `--previous-manifest` and
  `--attachment-fallback`.
- README and README_ko describe the new flow first; the earlier "in development" section is folded into the
  main text. The plugin version moves from 0.4.20 to 0.5.0.
- The collaboration plan moves to [docs/plan/collaboration/](https://github.com/ysys143/xsm/blob/ab8f173a90172f8564196467c5d952173ecaaacc/docs/plan/collaboration/README.md), with a README
  for outside readers and the agents' working notes under `records/`. Its audit is now
  `scripts/audit-collaboration-plan.py`. Recorded runs under `deliverables/` keep the paths of the time.
- The Reason research is published as one [comparison note](https://github.com/ysys143/xsm/blob/ab8f173a90172f8564196467c5d952173ecaaacc/docs/references/reason.md) built on the public engine,
  the official docs and using both tools. The detailed research, including analysis of the non-public CLI, is
  no longer in the repository.

### Fixed

- An older receive hook could hide a valid P2P canonical copy from the MCP inbox, the unread count and the
  answer lookup. All three now apply the same classification.
- Owned-interface tests failed when the suite ran inside an Orca terminal: they did not clear the inherited
  pane markers, as the other worker tests do.

### Known limits

- ADR-0021 and ADR-0024 are accepted. ADR-0015 to ADR-0020, ADR-0022 and ADR-0023 are still proposed, and
  their open parameters are not user decisions yet.
- The plan's completion ledger is at 4 proven and 95 partial criteria. Runs on the real human UI are not
  observed yet, and earlier native and physical runs were made on sources before the last receive change.
- Remote paths were tested on two physical Macs and a phone on another NAT. The HTTPS proxy and self-hosted
  relay were tested on one host only, IPv6 absence was injected per process, and hosted MCP internals were
  not observed. Details: [ADR-0021 closure record](https://github.com/ysys143/xsm/blob/ab8f173a90172f8564196467c5d952173ecaaacc/docs/plan/collaboration/adr-0021-closure.md).
- The P2P network is a model for machines that trust each other; it does not isolate a hostile member.

## 0.4.x

| Version | Date | Highlights |
|---|---|---|
| [0.4.20](https://github.com/ysys143/xsm/releases/tag/v0.4.20) | 2026-10-12 | Session lookups filter before probing and share a bounded budget (#17); sends to a registered address skip global discovery, and the result line carries the message ID (#18) |
| [0.4.19](https://github.com/ysys143/xsm/releases/tag/v0.4.19) | 2026-10-08 | Guidance for readable agent message text (#15) |
| [0.4.18](https://github.com/ysys143/xsm/releases/tag/v0.4.18) | 2026-10-05 | Background workers on a plugin-installed Codex home no longer die before registering (#12 follow-up) |
| [0.4.17](https://github.com/ysys143/xsm/releases/tag/v0.4.17) | 2026-10-05 | Workers can be started on a plugin-installed Codex home (#12) |
| [0.4.16](https://github.com/ysys143/xsm/releases/tag/v0.4.16) | 2026-10-04 | `xsm held drop` can no longer delete the config file; a "yes" is used only once (#11); an unopenable hook script is reported |
| [0.4.15](https://github.com/ysys143/xsm/releases/tag/v0.4.15) | 2026-10-01 | Hooks never block a prompt; an out-of-scope send connects and delivers on one "yes"; human decisions (#9) |
| [0.4.14](https://github.com/ysys143/xsm/releases/tag/v0.4.14) | 2026-10-01 | Native messages from this machine's Claude sessions all pass (ADR-0013); a linked worktree is the same repository; the agent asks and runs the link |
| [0.4.13](https://github.com/ysys143/xsm/releases/tag/v0.4.13) | 2026-10-01 | The sender learns about a held `SendMessage` (#8); approval-form tools join the Claude allow list |
| [0.4.12](https://github.com/ysys143/xsm/releases/tag/v0.4.12) | 2026-09-30 | Already-read messages no longer repeat as "Blocked by hook" (#7) |
| [0.4.11](https://github.com/ysys143/xsm/releases/tag/v0.4.11) | 2026-09-30 | A failing MCP tool falls back to the shell command; `doctor`'s `orphaned` line tells healthy servers from broken ones |
| [0.4.10](https://github.com/ysys143/xsm/releases/tag/v0.4.10) | 2026-09-30 | Sessions running from a deleted version are told why they fail (#6) |
| [0.4.9](https://github.com/ysys143/xsm/releases/tag/v0.4.9) | 2026-09-29 | The MCP server preloads its modules, so a plugin update no longer breaks open sessions |
| [0.4.8](https://github.com/ysys143/xsm/releases/tag/v0.4.8) | 2026-09-29 | This machine's Claude sessions connect even when xsm does not know them (ADR-0013 revised) |
| [0.4.7](https://github.com/ysys143/xsm/releases/tag/v0.4.7) | 2026-09-29 | Claude's own messages are judged by scope (ADR-0013); a header must arrive from the sender's own socket |
| [0.4.6](https://github.com/ysys143/xsm/releases/tag/v0.4.6) | 2026-09-29 | Codex plugin |
| [0.4.5](https://github.com/ysys143/xsm/releases/tag/v0.4.5) | 2026-09-28 | Wakes a Codex session stopped with Esc |
| [0.4.4](https://github.com/ysys143/xsm/releases/tag/v0.4.4) | 2026-09-28 | `/xsm link`: one side, once |
| [0.4.3](https://github.com/ysys143/xsm/releases/tag/v0.4.3) | 2026-09-28 | Repository renamed to `xsm`; `reach` |
| [0.4.2](https://github.com/ysys143/xsm/releases/tag/v0.4.2) | 2026-09-27 | A worker started outside the scope can talk with its parent |
| [0.4.1](https://github.com/ysys143/xsm/releases/tag/v0.4.1) | 2026-09-27 | The Claude inbox socket path comes from the documented `CLAUDE_CODE_MESSAGING_SOCKET` |
| [0.4.0](https://github.com/ysys143/xsm/releases/tag/v0.4.0) | 2026-09-27 | One `xsm` skill with commands as arguments (`/xsm list`, `$xsm list`) instead of eight command files |
