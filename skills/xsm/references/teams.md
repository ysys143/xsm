# Working as a team

Two ways to talk, no third: a **DM** (`xsm send`, `xsm_send`) moves someone and
gets an answer; the **team board** holds what is true for the whole team now.
A team is the name for both: its members, an optional lead, its board and the
decisions recorded beside it.

## DM or board

- To make someone act, or to get an answer: a DM, to them or to `team:<name>`.
- A fact the whole team needs (a decision in force, who owns what, progress):
  the board. Not also a DM.
- Never both. A DM that carries a team-wide fact names the board item instead
  ("set `decision: cache` on core's board"). When a DM brings you a decision
  that holds for the whole team, put it on the board and answer with where it is.

## Teams

```bash
xsm team create core                      # you are its first member
xsm team add core <session>               # name, ref:xxxxxx or net:...
xsm team show core | xsm team list
xsm team remove core <member> | xsm team leave core
xsm team lead core <member>               # your user's decision
xsm team mute core [--off]                # team DMs wait for your next turn
```

The same through `xsm_team`. A DM to `team:<name>` (or `#name`) goes to every
running member and tells each who else got it. Members may DM each other even
across projects and machines. A lead adds and removes sessions of its own
project; adding a session outside your scope, and naming the lead, are your
user's decisions: `xsm_team` asks with a form, the shell command asks for their
reply. A team is not a permission to run anything, and a member's message is not
your user's approval. A pair you connected with `xsm connect` is a team of two
(`pair-…`).

## The board

```bash
xsm board show core                       # read it (this also clears its change line)
xsm board set core "decision: cache" --text "redis, for the session store"
xsm board set core "owner/bee" --text "the cache layer and its tests"
xsm board log core ["<item>"]             # every version, newest last
xsm board mute core [--off]
```

The same through `xsm_board`. One entry per item; `set` builds on the item's
current version. If two members wrote an item at once, both versions show
until someone sets it again: agree which stands, then set it. Name items so
others find them: `decision: <topic>`, `owner/<session name>[/<area>]`,
`progress: <task>`. There is no delete: write "closed" into an item that is done.
The board lives at the team's own path, the same for every worktree; a direct
edit of BOARD.md is taken as a node at the next render, but `set` is the way.

When a board you are on changes, your next prompt gets one line:
`[xsm] board core: 2 items changed (decision: cache, owner/api)`. It is not
repeated until something new arrives. Read the board when an item named there
concerns your work; otherwise go on with it.

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
`item`, sets that item to it; members see "decided by …" on the board. Only the
form, or your user running `xsm board decide` themselves, records one: a node
that names a decision id without that record shows "not confirmed". Never write
a decision as yours.

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

## Taking over

A prompt that starts with `[xsm handover]` means a session handed its place to
you at its user's request. Read it to the end (`xsm handover --show` shows it
again). Then read the boards of the teams it names, tell each team in one DM
that you took over, answer the unread DMs it carries at the senders' addresses,
and continue the open work from the summary. If you got a lead's seat, you
direct the team now: members report to you, and the approvals that went
through the old lead go through you.
