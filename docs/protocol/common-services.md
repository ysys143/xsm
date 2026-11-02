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
