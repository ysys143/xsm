---
type: llm
weight: 1
---

A good answer makes a team with xsm (`xsm team create <name>` and `xsm team
add <name> <session>`, or the `xsm_team` MCP tool), and then keeps the two
things apart: the release branch is a fact the whole team needs, so it goes on
the team board (`xsm board set <team> "<item>" --text ...` or `xsm_board`; or,
because the user made the decision, recorded as the user's through `xsm_decide`
with the team and an item, or `xsm board decide`),
while starting the migration is asking one session to act, so it is a DM (a
task) to api-worker (`xsm send api-worker --kind task --text ...` or
`xsm_send`). A DM to the whole team is `team:<name>`.

It is wrong if it puts the same fact both in a DM and on the board, invents a
channel or chat room for the announcement, invents commands or flags that are
not xsm's, or says adding a session from outside this project needs no
approval from the user.
