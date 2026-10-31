---
type: llm
weight: 1
---

A good answer writes a context summary for a session that knows nothing of
this conversation (the goal, the state now, decisions and why, open work, who
waits on whom) and hands over with `xsm handover night-shift --summary-file
<file>` (or the `xsm_handover` MCP tool), which the user confirms. It says that
xsm then moves the team place and the lead's seat, the session's own board
items, its unread DMs and its pending questions to night-shift, and that DMs to
this session reach night-shift afterwards; night-shift reads the handover at its
next prompt and continues, directing the team as its lead.

It is wrong if it only sends night-shift a DM with a summary and calls that the
handover, invents commands or flags that are not xsm's, or says the handover
needs no confirmation from the user.
