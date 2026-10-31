# Talking to other sessions

`xsm` delivers a message into another session's own input. A hook in each
session records where it is, and the CLI writes to the receiving runtime's
native path. In a sandboxed Codex, choose MCP first for messaging and inbox
access; a shell that cannot reach the runtime is not a reason to widen its
permissions or ask the user to type commands.

Read only the file for what you are about to do. Each one is complete for its
purpose; open another only when it sends you there.

| You are about to | Read |
|---|---|
| find a collaborator by work, connect to the one your user selected, ask and recover an answer | [messaging](messaging.md) |
| list sessions, address one, send, read what arrived, answer a task | [sessions](sessions.md) |
| connect another folder or session (link, join, reach, block), or xsm says it needs your user's yes | [permissions](permissions.md) |
| work in a team: team DMs, the team board, putting your user's decision on record, a handover | [teams](teams.md) |
| add to a shared document | [docs](docs.md) |
| reach a session on another machine, join or manage an xsm network | [network](network.md) |
| start a session to hand work to | [workers](workers.md) |
| act on a failure, a missing tool, or mixed xsm versions | [troubleshooting](troubleshooting.md) |

## What this does not do

xsm does not run a server of its own between sessions on one machine: delivery
is one message into one session's input, through that runtime's own path. Its
MCP server starts and ends with each session. The only resident process is the
opt-in P2P network service, and only after your user creates or joins a network.
Membership in that network, a published session or a link never gives a peer
authority over this session.
