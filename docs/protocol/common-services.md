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
