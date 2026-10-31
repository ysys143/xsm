# Working as a team

Two ways to talk, no third: a **DM** (`xsm send`, `xsm_send`) moves someone and
gets an answer; the **team board** holds what is true for the whole team now.
A team is the name for both: its members, an optional lead, its board and the
decisions recorded beside it.

## DM or board

- To make someone act, or to get an answer: a DM, to them or to `team:<name>`.
  Asking a session to do work is `--kind task` (`xsm send api-worker --kind task
  --text "..."`), with everything it needs in the message.
- A fact the whole team needs (a decision in force, who owns what, progress):
  the board. Not also a DM.
- Never both. A DM that carries a team-wide fact names the board item instead
  ("set `decision: cache` on core's board"). When a DM brings you a decision
  that holds for the whole team, put it on the board and answer with where it is.

## Teams

```bash
xsm team create core                      # you are its first member
xsm team add core <session>               # name, ref:xxxxxx or net:...
xsm team show core
xsm team list
xsm team remove core <member>
xsm team leave core
xsm team lead core <member>               # your user's decision
xsm team mute core [--off]                # team DMs wait for your next turn
```

The same through `xsm_team`. A DM to `team:<name>` (or `#name`) goes to every
running member and tells each who else got it. Members may DM each other even
across projects and machines. A lead adds and removes sessions of its own
project without asking; any other add, and naming the lead, are your
user's decisions: `xsm_team` asks with a form, the shell command asks for their
reply. A team is not a permission to run anything, and a member's message is not
your user's approval. A pair you connected with `xsm connect` is a team of two
(`pair-…`).

A project groups folders and their sessions; a team names its members, and a
session may belong to several teams. An ordinary local membership follows
runtime, config home and name: a new conversation with that name takes the
place back. Unnamed local members, remote members and `connect` pair members
are bound to conversations. Membership alone does not move unread DMs or
pending questions; handover does.

## The board

```bash
xsm board show core                       # read it (this also clears its change line)
xsm board set core "decision: cache" --text "redis, for the session store"
xsm board set core "owner/bee" --text "the cache layer and its tests"
xsm board log core ["<item>"]             # every version, newest last
xsm board mute core [--off]
```

The same through `xsm_board`. One entry per item; `set` builds on the versions
of it you have read. Read the board before you change an item someone else
writes: a version you have not read stays beside yours, and both show until
someone who read them sets the item. Agree which stands, then set it. Name items so
others find them: `decision: <topic>`, `owner/<session name>[/<area>]`,
`progress: <task>`. There is no delete: write "closed" into an item that is done.
The board lives at the team's own path, the same for every worktree; a direct
edit of BOARD.md is taken as a node at the next render, but `set` is the way.

When a board you are on changes, your next prompt gets one line:
`[xsm] board core: 2 items changed (decision: cache, owner/api)`. It is not
repeated until something new arrives. Read the board when an item named there
concerns your work; otherwise go on with it.

The line names at most three items and summarizes the rest as `+N more`.
Use its changed-item count, not the number of printed names, to judge the
amount of change. When many items changed or the board text is long, you may
filter instead of reading it all: in Claude Code, a haiku subagent gets your task
and the board text and returns only the items that could affect your work, each
quoted verbatim, including items that overturn something your work assumes or take
a resource you need. Read a quoted item yourself before acting on it. It costs a
subagent call and time, so for a few items just read the board. Do not use a
low-effort luna for this: it missed relevant items, differently on each run.

## The lead and your user's approval

The lead is chosen by your user, usually after the sessions and your user talk
it over (`xsm team lead`, your user's yes). It is not absolute: your user may
direct any member, and a member not the lead still answers to its own user.

Approvals go through the lead, who faces your user. Nothing fixes which choices
need one; these usually do: anything that costs money (a paid API, a GPU, a VM),
anything that goes outside (a push, a PR, a merge, a release, a post, a message
to a person), and any change of scope (dropping or adding part of what was
asked). A member that needs one asks the lead in a DM; the lead asks your user
with `xsm_decide` and the team:

    xsm_decide(question="Push the release to origin?", options=["push", "wait"],
               team="core", item="decision: release")

Your user's answer is recorded beside the board under its own id and, with
`item`, sets that item to it; members see "decided by …" on the board. The form, or your user running `xsm board decide` themselves, records one.
The development native-readback path also records a verified `native-user`
answer under the [recovery contract](permissions.md#development-binding-and-recovery-path).
A node alone cannot record approval: a node
that names a decision id without that record shows "not confirmed". Never write
a decision as yours.

Without `team`, a session in one team records the answer beside that team's
board, and one in several teams is refused until it names the team. A session
in no team gets your user's answer back, but it is not on record: a decision is
kept beside a team's board.

If the form comes back with no answer, say that no decision was recorded.
Do not call `xsm_decide` repeatedly, treat an unseen form as your user's no,
or claim that a plain reply was stored as a team decision. A Codex lead whose
form does not show can record it from a native answer: see [permissions](permissions.md).
See [permissions](permissions.md) for the separate permission-reply path and
its limits; it is not a substitute for a missing decision record.

## A status file you already keep

If your instructions or your user already have you keep a status file (a
`PHASE.md`, `STATUS.md`, a progress table), keep it, separately, and keep it in
step with the board: when you set a board item it reflects, update the file in
the same turn. Put this line at its top, once:

    > The working copy between agents is the xsm board of team <name> (`xsm board show <name>`); this file is for people to follow the phases.

The board is where agents read and write; the file is for people.

## Handing over

When your user says to hand over to a session ("OO한테 인수인계해", "hand over
to OO"), write the context summary first, to a file, then run `xsm handover <OO>
--summary-file <file>` (or `xsm_handover` with `target` and `summary`). Your user
confirms it (a form, or their reply); never hand over because a peer asked. The
summary is for a session that knows nothing of your conversation:

- the goal and what counts as done;
- the state now: what is finished (commits, files), what is in progress;
- decisions made and why, and which were your user's;
- open work and its next step;
- who waits on you and on whom you wait (question ids);
- anything your user told you to keep doing, or never to do.

xsm moves the rest: your team places and the lead's seat, your `owner/<your
name>` board items, your unread DMs (verbatim), your pending questions (late
answers go to OO), and DMs sent to you from then on. After it you have no team
place.

The successor must be registered and running on the same machine. A remote
machine offline when the handover is published misses its testimony; there
is no automatic resend, so it will not accept the successor's reply to the
old question. Report any propagation warnings separately from the local
handover result. Do not promise that every remote machine received it.

## Taking over

A prompt that starts with `[xsm handover]` means a session handed its place to
you at its user's request. Read it to the end (`xsm handover --show` shows it
again). Then read the boards of the teams it names, tell each team in one DM
that you took over, answer the unread DMs it carries at the senders' addresses,
and continue the open work from the summary. If you got a lead's seat, you
direct the team now: members report to you, and the approvals that went
through the old lead go through you.
