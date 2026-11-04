# Workers

For a development team, read [organization](organization.md) before assigning roles.
Strongly recommend a fable/astra-tier lead, opus/sol-tier primary workers and
haiku max/luna max-tier supporting workers for large, long-running parallel work.
Keep primary and supporting workers at the same creation depth when possible;
specify their direct collaboration and reporting relationships in ordinary text.
Use a harness subagent for a one-off task, or a persistent worker for ongoing
context and repeated collaboration. Choose actual model IDs and reasoning settings
from the runtime's available choices; these recommendations do not change defaults.

## Workers: starting a session to hand work to

`xsm workers --policy` prints what a background worker does without asking:
every shell command (all of them sandboxed), reads anywhere, writes inside its
folder, and the xsm MCP tools to reach a peer. Everything else goes to a person.
If a worker reports that it was refused something, that list is what to check —
do not widen it yourself.

```bash
xsm spawn claude --model <primary-model> --task "You are core team's primary worker. Implement the agreed cache behavior; report checks and blockers to your requester."
xsm spawn codex --model <support-model> --effort <effort> --once --task "You support core team's primary worker. Check ./pkg and return failures with evidence to your requester."
xsm workers                 # what xsm started and whether it is running
xsm workers read <worker>   # what its screen says — is it working or stuck?
xsm attach <worker>         # go to its tmux pane (a person; read only looks)
xsm stop <worker>           # stop it; task history remains
```

- Inside tmux the worker opens as the real TUI in a pane next to yours; its
  user can watch and answer its prompts there. Elsewhere (or with
  `--background`) it runs as the same real TUI in a window of the detached tmux
  session `xsm-workers`. A worker is never `claude -p` or `codex exec`. The
  statusline shows each of your workers and whether one is waiting on a person.
- `--task` sends the task as `--kind task` once the worker is up; the answer
  comes back to you as a reply. The first correlated reply closes its attempt
  record, including one without a final outcome; `--once` also stops the worker.
  Use the board or a separate note for progress before that task answer. Put everything it needs in the task. For team work, include
  its team and board, role, scope and inputs, completion criteria, reporting
  destination and collaborators as described in [organization](organization.md).
  Tell it which changes require coordination; creating a session alone does not
  tell it how to participate in the organization.
- **A worker must never sit idle on a permission.** When you are told a
  worker is waiting, call the `xsm_approve` MCP tool right away: it shows the
  request to your user, who allows or denies it in a form. When a worker
  reports a step it could not do for lack of permission, get the permission
  (`xsm_approve` when it asks again, `xsm_grant` for full access) and send the
  step back; do not accept "no permission" as the end of the task.
- A background worker works unasked inside its folder's sandbox (Codex
  workspace-write; Claude acceptEdits plus its own OS sandbox). Past that, a
  Claude worker's request goes to your user; a Codex worker cannot go past it.
- From inside a background worker, `xsm send` to a session of the other
  runtime fails with a sandbox error; use the `xsm_send` MCP tool then (same
  target, kind, text). The MCP server runs outside the shell sandbox.
- If a background worker stops at a folder-trust screen, `spawn` returns at
  once saying `waiting: … Call the xsm_approve MCP tool with id …`. Do that
  now: the question goes to your user in a form. Once they answer, the worker
  starts and its `--task` reaches it on its own. Never send your user to the
  tmux screen. You get a note saying what it is waiting for. **Never approve
  it on your own** — that is permission laundering. Ask your user, saying
  what is waiting and why. If the MCP form returns no usable answer, follow
  [native recovery](permissions.md): ask its exact marked question once and
  retry that same MCP call. Do not bounce to a shell or a worker terminal.
  The CLI approval route remains available when the MCP tool itself is absent;
  only the starting session may relay its own user's verified answer there.
- `--full-access` and `--trust-hooks` remove your user's protections. Use them
  only when the work needs it, and only with their explicit permission: call
  the `xsm_grant` MCP tool with the reason, and pass the id it returns as
  `--grant <id>`.
- If the `xsm_grant` call itself is blocked (Claude Code's auto mode can deny
  it), do not stop there and do not work around it: ask your user with your
  question tool whether to request the permission, saying what the worker
  needs and why. If they agree, call `xsm_grant` again; their answer in the
  form it shows is the permission. Never ask them to type shell commands. If
  no choice came back from the form, follow [native recovery](permissions.md)
  and retry the same `xsm_grant` call with the same arguments. Do not switch
  to spawn as a second approval route for that pending MCP question.
- If your user answers the grant form with deny, do not start that worker with
  those options; carry on without them or ask what they prefer.
- **Count failures since the latest success.** When a worker answers
  `--outcome failed`, that failure is recorded against the task. After three
  counted failures, `spawn` refuses with `task-attempts-exhausted` and lists what was
  tried. Do not reword it and send it again — the lineage follows the task, and
  `--retry-of <task id>` is how you say a reworded try belongs to it. Tell your
  user what failed and what the worker said it needed, and ask whether to
  clear it; on their yes run `xsm attempts clear <key>` (it keeps their reply
  as the verdict). `xsm attempts` and
  `xsm attempts show <key>` show what has been tried.
- An explicit `xsm stop <worker>` closes an unanswered attempt without a final
  outcome. It neither adds a failure nor clears earlier failures, and it is not
  success. A recorded reply keeps its outcome. Automatic stops keep their
  existing classification; `--once` cleanup preserves the reply it follows.
  A worker still waiting for trust has no dispatched attempt to close. Stopping
  it must not close a peer's task. Compaction preserves counted older failures.
- Workers cannot start workers unless the depth limit allows it (`max_depth`,
  default 1), and one session runs at most `max_workers` (default 4) at once.
  If spawn refuses for either, report it; do not raise the limit. Workers stop
  by themselves when the session that started them ends.
- Inside Orca or herdr, `spawn` and `stop` refuse: that framework manages
  workers there. Use its own tools; xsm only carries messages between sessions.
  To start xsm workers there anyway, ask your user; on their yes run
  `xsm frameworks ignore orca` (their reply is kept as the verdict). Never
  decide it on your own. `xsm frameworks` shows
  the current setting.

## Questions from unattended workers

A background worker has no person at its terminal. Ask its parent, or the
team lead, in a DM when a user decision is needed; do not open an unattended
question or form. A runtime PermissionRequest to allow AskUserQuestion is
permission to invoke that tool, not an answer to its question. A pane worker
with a person in the pane can still use forms unless linked to a coordinator; linked workers route decisions to that coordinator. Registration failures in a
Claude background job are separate: another message is not a promised fix.

A background AskUserQuestion PermissionRequest is denied with
parent/lead guidance; it does not create a permission form that nobody can answer.
Plugin and worker hooks for one invocation share a request only after the exact
native tool-use ID is verified. Worker-local PreToolUse stores identity before
native transcript flushing; PostToolUse and PostToolUseFailure retire calls.
Older workers can use a bounded native transcript fallback.
Identical inputs from different invocations stay separate. Missing or ambiguous
identity fails closed. Duplicate callbacks keep the original deadline and cannot
reopen an answered or expired request. These changes preserve worker permissions.

## Project membership for coordinator-created workers

After starting workers (including through Orca), the creator resolves their actual registered
refs with `list` and calls `xsm_join` once with `project` and `workers` (registered refs or
Orca `term_` launch handles). If registration is pending, retry after the first prompt; do not
start replacement workers. The folder-list approval
is collected in the creator session. This also registers the coordinator/worker relationship.
Do not send a join instruction to each worker or ask the user to visit worker terminals.
Already approved folders automatically cover later sessions in the same folders. A linked worker's
new project request is returned to its parent; handle it there with the same group operation.
New roots need one parent-side confirmation. A folder move or a new conversation requires a new link.
For a new conversation in an approved folder, the parent confirmation names
the coordinator relationship; it does not ask to join the folder again.

The worker's `xsm join PROJECT` CLI follows the same routing as `xsm_join`:
an approved folder returns immediately without another question. A new project
produces one parent request and returns its pending ID; repeating it preserves
that ID and does not open a worker-local question. Wait for the coordinator's
result rather than switching to a second approval path.
