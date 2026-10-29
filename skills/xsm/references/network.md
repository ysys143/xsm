# Other machines

Read this when your user wants sessions on another machine: the opt-in P2P
network below, or a machine paired over SSH (last section). Local messaging and
existing SSH peers keep working without the network service.

An opted-in P2P network merges permitted remote candidates into `xsm discover` /
`xsm_discover`. Show the machine and work metadata, let the user select one,
then use its returned target with connect/ask/send. Same-repository visibility
across machines requires an explicitly verified repository binding. Publication
or a shared network never supplies collaboration permission.

## Optional P2P networking

Create, join or change a network only on your user's instruction.
Device keys and a valid invitation establish membership; no xsm account is
required. Every active member may invite, add or remove devices. The founder is
the trust root, not a privileged administrator.

`xsm network build` builds the bundled locked Rust source into this user's xsm
state. It requires an available Rust toolchain and does not install one.
`xsm network init NAME --machine-name NAME` creates the network and starts its
owned service. `xsm network invite` writes a private invitation file and prints
only its location. `--once --expires SECONDS` issues a one-time invitation;
`--expires` also bounds a reusable invitation. Transfer the file through the
user's chosen private channel, then join with `xsm network join --ticket-file PATH`
or `--ticket-stdin`. Never put the invitation secret into a message, model
context, command arguments or ordinary diagnostics. Do not ask the user to
operate a UI when an authorized CLI path is available.

Membership does not publish sessions, select collaborators or authorize file
access/execution. Discover through `xsm_discover`, display permitted candidates,
and use the exact returned target. Same repository means an operator-verified
mapping: `xsm network map-repository PATH --repository-id ID --peer PUBLIC_KEY`
on the corresponding machines. Names and remote URLs are not proof. Other
explicitly published sessions are also candidates; selecting one uses the
ordinary user's exact-pair consent and correlated handshake. Never manufacture
an approval or treat peer readiness as the user's decision.

`xsm network status` and `members` show public state, not invitation secrets.
`configure --port PORT`, `--relay public|off|HTTPS_URL`, and
`--direct-address IP:PORT` take effect on the next start. Literal loopback HTTP
relay URLs are allowed for local tests. Tailscale is an optional direct path,
not membership. Report an observed selected path separately from configuration.
`stop` closes only xsm's service/engine; `start` retains its device key and
membership. `remove PUBLIC_KEY`, `revoke-invite HASH`, and `leave` require the
user's instruction. Removing a member also revokes existing reusable invitations.

P2P `wake=never` preserves the canonical message without native queue/wake.
Automatic wake requires an actually executed current receiving hook; otherwise
the original remains on the MCP inbox route. Receiving files requires the
target's actual current capability observation. Copies remain untrusted data.
Use status/question-status with the original ID after unknown delivery; do not
invent a new ID to resend. A temporary admission outage leaves the original
pending for revalidation. A legitimate same-conversation resume keeps its
stored originals; a different conversation never inherits them.

`xsm network requests` lists only the current sure caller's saved originals,
including old teams without starting a service. Use `export ID --output PATH`
to create a new private JSON file; it never overwrites a file and contains
the original body and immutable attachment references, not an unmetered byte
cache. `archive ID` hides it from this recovery list and refuses another
dispatch of that ID. `requests --archived` includes archived originals.
Archiving retains question history, originals and late replies; it is not
remote cancellation or evidence that model side effects stopped.

For a sandbox refusal, use the supported MCP path; do not widen the sandbox,
change permission rules or bypass hook trust. A missing network management MCP
tool is not authority to change the agent's permissions. Report the concrete
blocked operation after checking the available authorized CLI path.

## Machines paired over SSH

If your user paired this project with another machine (`xsm remote list`),
`xsm remote sessions <peer>` shows its live sessions and
`xsm send <name>@<home>@<peer>` reaches them over SSH; replies come back the
same way. Pairing a machine is your user's decision (`xsm_grant`, option
`remote`).
