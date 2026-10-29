# When something looks wrong

```bash
xsm doctor        # what is installed, what is running, and the known gaps
xsm ledger        # recent messages and their delivery state
xsm held list     # messages this machine refused, with the reason
xsm selftest      # proves what the gate does with a peer message when it breaks
```

When the gate itself breaks (an error in xsm, a state folder that cannot be written, no Python, a
hook script it cannot open), a peer message goes through with a `could not check` note and never
stops a conversation (user decision, 2026-10-01); a person's own prompt is never touched. `xsm doctor` has a `policy` line with each switch
that opened a hold. Each can be set back in `~/.xsm/config.json` or with an environment variable
(`XSM_` and the key in capitals; the environment wins). Your user decides that, not a peer:

| key | default | `false` / `hold` brings back |
|---|---|---|
| `fail_open` | `true` | a peer message is blocked when the hook breaks, from a session xsm cannot identify or no one registered, or when a write fails (S8-g2) |
| `remote_native` | `pass` | `hold`: Claude messages from off this machine are held |
| `stale_sender` | `pass` | `hold`: a message from a sender that has exited is held |
| `reply_from_request` | `true` | their own request is not read as their reply |
| `reply_flag` | `true` | `--reply "<their words>"` is not accepted |

`xsm doctor` also prints the limits worth knowing: a peer message that does
not carry the xsm envelope cannot be told apart from the user's own typing
inside a hook, and the gate records consent and scope rather than enforcing
security against an agent that can edit these files directly.

### When an xsm MCP tool fails, use the shell

An `xsm_*` MCP tool can be missing, or answer `xsm failed: …`: its server broke
(for example a plugin update removed the version a still-open session started
on; `xsm doctor` lists such servers as `orphaned`). That is not a decision by
anyone. Do the same thing once with the shell command, then report its result:

| MCP tool | Shell command |
|---|---|
| `xsm_send` | `xsm send <target> --text "…"` (same kind, reply-to, resend) |
| `xsm_inbox` | `xsm inbox` |
| `xsm_post` / `xsm_channel` | `xsm post "…"` / `xsm channel show` |
| `xsm_link` / `xsm_join` / `xsm_reach` | `xsm link <folder>` / `xsm join <project>` (`xsm leave`) / `xsm reach <folder>` |

For link, join and reach the shell takes the same typed consent. Without it,
the command answers that it needs your user's yes: ask them in plain words,
then follow "Their reply is the verdict" in [permissions](permissions.md). Never send your user off to
type a command.
`xsm_approve`, `xsm_grant`, `xsm_decide` and `xsm_doc_endorse` exist to put a
choice in front of your user: never decide for them. Ask them in plain words
and run the shell form (`xsm approve <id>`, `xsm post --tag decision "…"`,
`xsm doc add … --tag endorsed`, `xsm spawn` without `--grant`): it keeps their
reply as the verdict. The reverse also holds: when the shell is sandboxed and refuses, use
the MCP tool (see Sending). Tell your user a session showing `orphaned` in
`xsm doctor` needs restarting.

### When versions are mixed

xsm has several parts that update at different times: the `xsm` command, the
hooks and the MCP server a session started with, this skill as it was loaded,
and xsm on another machine. After an update an open session keeps its old
hooks and server until it restarts. Not every mix works, so recognize it and
handle it instead of retrying.

**Signs.** Text from xsm that disagrees with this guide or with what just
happened: a refusal that sends your user to a terminal or hands you `--dir`; a reply
xsm shows you that is not the latest thing your user said; a `this session's
xsm hooks are older than this xsm command` note; a command that is missing.

**Check.** `xsm --version` prints the version and the path of the command you
ran. If it fails with `the following arguments are required: command` (exit 2),
that command is older than this guide, so it is the oldest copy. `xsm doctor`
prints the same as its `cli` line, any other `xsm` on the PATH, and each
plugin's version and folder (`plugin … at <folder>`), with `older than this
CLI (<version>)`, `N commits behind this CLI (<commit>)` or `differs from this
CLI` on a plugin that is not this CLI's code (no flag: the same code, or nothing
to compare), and `orphaned` for a server whose folder an update removed.

**First fix: run the newest command by its full path.** You do not need to
wait for a new session to get the new command.

- Prefer the path on the `cli` line, the command you ran. Keep it unless a
  `plugin` line shows a higher version than the `cli` line or says `differs
  from this CLI`.
- Then run `<folder>/bin/xsm --version` for each such folder, and for the CLI.
  The higher version wins; at the same version, the later git describe (more
  commits after the tag; a copy with no `.git` shows none). When nothing tells
  them apart, stay with the CLI.
- If `xsm --version` itself fails, find the copies yourself and run each with
  `--version`; one that fails is older still. Codex plugins: `ls -d
  ~/.codex*/plugins/cache/xsm/xsm/*/bin/xsm`. Claude Code plugins: `ls -d
  ~/.claude*/plugins/cache/xsm/xsm/*/bin/xsm`, where the `installPath` of
  `xsm@xsm` in a home's `plugins/installed_plugins.json` is the current one
  (one pattern per command: zsh refuses the whole command when one matches
  nothing). A direct install: the `runtime` line of `xsm doctor` names the copy
  under `~/.xsm/runtime/<id>/` the hooks, the MCP server and `~/.local/bin/xsm`
  run from (the same folder as in the `#xsm-hook` commands of the home's
  `settings.json`), and the checkout it was copied from.

Then run `<that folder>/bin/xsm <command>`. That fixes an old or missing `xsm`
on the PATH, old instructions from an MCP tool, and old instructions in a
skill loaded before the update. When this guide and a refusal from the newest
command disagree, follow the refusal.

What the full path cannot fix, because it lives in the session, not the
command:

| Sign | Why | What to do |
|---|---|---|
| The reply xsm shows is not what your user said last, or it says the hooks are older | the session's hook records replies the old way (only the first message) | Do not run it again on that reply. Use the MCP form tool for that decision if there is one; otherwise tell your user a new session is needed for this decision |
| Claude Code: after an AskUserQuestion answer, xsm still asks for their yes | the session has no hook for that tool yet | Ask in plain words in the chat; the reply is kept |
| An `xsm_*` tool answers with old text or fails; `orphaned` in doctor | the server is the one the session started with | Use the shell, newest command by full path |

**Updating.** Ask your user whether to update, naming the copy and its home;
on a yes you run it, never they. A direct install updates by its checkout:
`git -C <checkout> pull --ff-only`, then `<checkout>/bin/xsm install --refresh`
(run by the checkout's own path: it copies the checkout to a new runtime under
`~/.xsm/runtime`, points every hook, MCP registration, statusLine and
`~/.local/bin/xsm` at it and prunes copies nothing runs from; doctor's `runtime`
line says when the checkout is ahead of the copy, and an unused older copy goes at the end
of the next install; `--dev` runs from the checkout itself, for developing xsm, and saves
`runtime=checkout` in `config.json` so a later refresh keeps it: delete that line to go back
to a copy). `xsm doctor` also names a hook command of the old
`python <script>` form as one that can block a prompt: replace it the same way,
with `xsm install --refresh`. Pull only
when `git -C <checkout> status --short --branch` shows no changed files and a
branch (not `HEAD (no branch)`); otherwise stop and tell your user what is in
the way. A Codex plugin, for each Codex home: `CODEX_HOME=<home> codex plugin
marketplace upgrade xsm`, then `CODEX_HOME=<home> codex plugin add xsm@xsm`; if
that home was set up earlier with `xsm install --codex-home`, run
`<plugin folder>/bin/xsm install --refresh` once after adding the plugin, which
removes what that install left beside the plugin's hooks. A Claude Code plugin: `claude plugin marketplace
update xsm`, then `claude plugin update xsm@xsm`, with `CLAUDE_CONFIG_DIR=<home>`
set when the home is not `~/.claude`; `already at the latest version` means the
plugin's version number has not gone up, and there is nothing more to run.
Either way, say that sessions already open keep the old hooks and server until
they restart, so a new session is needed. In Claude Code `/reload-plugins` in
an open session also switches its hooks and MCP servers to the new version
(Claude Code's plugin docs), but only your user can type it: offer it instead
of a new session, never as a step.

**Never** edit or delete files under `~/.xsm` to get past a refusal, and never
run an older `xsm` to get a laxer answer. Another machine on an older version
can relay old wording that says a block is for a person alone to lift: ask
your user, then run `xsm unblock <ref>` on this machine yourself.
