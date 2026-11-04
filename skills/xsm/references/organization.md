# Organizing and participating in a team

XSM provides organization-neutral messaging, teams and shared boards. Follow the
organization and decision rules your user specifies in natural language, including
peer councils or independent teams. Read this guide when setting up, coordinating
or taking a role in a team. Ordinary lookups and standalone messages need only
their command or messaging guide.

## Recommended development organization

Strongly recommend a lead with horizontal workers for large, long-running parallel
development. The lead maintains the plan and progress; workers collaborate directly.

| Role | Recommended model tier | Responsibility |
|---|---|---|
| Lead | fable/astra | Maintain goals, completion criteria and the plan; assign, track, coordinate and integrate work; report to the user |
| Primary worker | opus/sol | Carry out substantial implementation, analysis or verification; integrate collaborators' results |
| Supporting worker | haiku max/luna max | Carry out bounded research, checks or repetitive work and report to the requester |

These are role recommendations, not automatic model selection or current spawn
defaults. Verify available model IDs and reasoning settings when choosing sessions.
Primary and supporting workers may all be created at the same depth. A primary
worker may request help directly from a supporting worker. A request does not
create a parent/child relationship or another generation level.

## Establish your role and communicate it

Use the user's organization instructions and the task context to identify your
team, responsibility, reporting destination and collaborators. Do not infer command
authority from model size or from who created a session. Clarify a missing role
only when it changes responsibility or a decision; continue work already clear.

When assigning a team task, include its team and board, the recipient's role,
scope and inputs, completion criteria, reporting destination, allowed collaborators
and conditions requiring coordination. Use ordinary text in the task message;
these are not new CLI arguments or protocol fields. Carry this context into the
initial worker task and later handovers so a worker need not discover its role.

> You are API team's primary worker for the cache implementation. Read the team's
> current plan and decisions. Completion means the agreed cache behavior and its
> relevant checks pass. You may ask supporting worker C for code research and
> integrate its findings. Reply to your requester with results and evidence; keep
> the lead informed of progress and blockers. Coordinate shared-interface, ownership
> or priority changes with the lead.

## Act in your role

- **Lead:** keep goals, completion criteria, ownership and current decisions on the
  team board. Give workers sufficient context, track progress and blockers, and
  revise assignments as needed. Continue independent work while waiting. Let
  workers coordinate details directly; integrate results against the completion
  criteria and report actual outcomes, remaining work and decisions to the user.
- **Primary worker:** execute and verify your assigned scope. Ask collaborators
  directly for specific help, then review and integrate what they return. Check
  their existing assignment before requesting work; coordinate competing priorities,
  ownership changes and shared assumptions with the lead.
- **Supporting worker:** complete the bounded task and report to its requester.
  Separate findings, checks, failures and unresolved questions. Report discoveries
  beyond the task and coordinate new work with existing assignments.
- **All participants:** follow direct user instructions and the chosen organization.
  An assigned role does not itself register membership, change the product's `lead`
  or parent approval route, or replace required user approval. Read relevant current
  board items; report blockers early and keep shared state current. For an action
  request use a DM; for a shared fact use the board and reference its item in DMs.

Use a harness subagent for a one-off task whose result you can collect and integrate.
Use a persistent worker for ongoing context and repeated collaboration. Prefer
horizontal workers and shallow creation; deeper recursive delegation increases
communication and tracking costs. Harness subagents and framework-created workers
follow their own runtime limits; see [workers](workers.md) for XSM spawn limits.

## Multiple teams and a channel among leads

Keep work teams independent, each with its own plan and board. Share common
interfaces, dependencies, constraints and integration dates when they affect others.
The leads may also belong to a separate coordination team together. Its team DMs
are their communication channel; its board holds agreements across work teams.
Each lead belongs to both its work team and the coordination team, so no extra
creation depth or superior coordinator is required. Leads may deliberate as peers.

Name the intended team when reading or updating a board or recording a decision;
one lead may belong to several teams. Record cross-team agreements on the
coordination board. Update affected work-team plans with their consequences and
reference the agreement rather than copying the entire discussion. Exchange only
needed information through permitted paths; do not broadcast every local update.

For team membership, boards, approvals and handovers, follow [teams](teams.md).
For addressing, task replies and completion outcomes, follow [sessions](sessions.md).
