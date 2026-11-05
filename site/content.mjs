export const repository = 'https://github.com/ysys143/xsm';
export const installPrompt = `Install xsm from ${repository} for Claude Code and Codex on this machine.
Verify the installation and tell me if I need to start a new session or trust a hook.`;
export const teamPrompt = `Put together a team to ship notifications.
You own the goal, acceptance criteria, plan and progress.
Assign the API to Opus, the UI to Sol, and verification to Luna.
Keep the workers at the same depth and let them collaborate directly.
Record current decisions, owners and progress on the team board.`;

const message = (at, from, text, kind = 'reply', detail = {}) => ({ at, from, text, kind, ...detail });
const tool = (at, name, input, result) => message(at, name, JSON.stringify(input, null, 2), 'tool', { result, resultAt: at + 550 });
const inbox = (at, from, id, text, kind = 'note') => message(at, from, `[xsm v1 id=${id} from="${from}" scope="repo:notifications" kind=${kind}]\n${text}`, 'inbox');
const item = (state, text) => ({ state, text });
const waiting = { at: 0, title: 'plan', items: [item('waiting', 'Waiting for the coordinator to record the plan.')] };
const actors = { lead: ['Claude Code', 'Fable', 'coordinator'], api: ['Claude Code', 'Opus', 'API'], ui: ['Codex', 'Sol', 'UI'], qa: ['Codex', 'Luna', 'verification'] };

export const scenes = [
  {
    id: 'team', number: '01', short: 'Form a team', title: 'Roles and working relationships',
    day: 'DAY 01', duration: 18000, topic: 'team', status: 'Define owners and acceptance criteria',
    caption: 'Form a team in natural language',
    description: 'Give the coordinator a goal and working relationships. It records the plan, assigns owners and works with the sessions you already have.',
    actors,
    messages: {
      lead: [
        message(0, 'you', 'Ship notifications. Own the plan and progress; split API, UI and checks between the workers.', 'user'),
        tool(2500, 'xsm_team', { action: 'show', team: 'notifications' }, JSON.stringify({ name: 'notifications', lead: 'lead', members: ['lead', 'api-worker', 'ui-worker', 'qa-worker'].map(member => ({ member, running: true })) })),
        message(3600, 'assistant', 'I will define acceptance checks first. Opus owns the API, Sol the UI, and Luna verification.'),
        tool(5900, 'xsm_board', { action: 'set', team: 'notifications', item: 'owner/api', text: 'Opus: notification schema and API.' }, 'set owner/api (node d3ca218b7e04)'),
        tool(7900, 'xsm_send', { target: 'api-worker', kind: 'task', text: 'Implement the API. Coordinate the contract with ui-worker; report evidence and blockers.' }, 'sent-unconfirmed: queued (id 6d8f2a9b41e7c503)'),
      ],
      api: [
        inbox(8600, 'lead', '6d8f2a9b41e7c503', 'Implement the API. Coordinate the contract with ui-worker; report evidence and blockers.', 'task'),
        message(9500, 'assistant', 'I will check the existing API and coordinate the event schema.'),
      ],
      ui: [inbox(9000, 'lead', '879ae5f48a10c2d3', 'Own the notification UI. Coordinate the API contract with api-worker.', 'task'), message(11500, 'assistant', 'I will build the notification list and read-state UI.')],
      qa: [inbox(12500, 'qa-worker', '09f6e1d7a82b4c30', 'Acceptance criteria read. Preparing the regression checks.')],
    },
    boards: [waiting, { at: 6100, title: 'plan: notifications', items: [item('done', 'Goal: create, deliver and mark notifications as read.'), item('active', 'Owners: Opus API / Sol UI / Luna verification.'), item('waiting', 'Acceptance: agreed behavior and regression checks.')] }],
    flows: [{ at: 7900, text: 'lead -> api-worker: task queued' }, { at: 12500, text: 'qa-worker -> lead: role confirmed' }],
  },
  {
    id: 'direct', number: '02', short: 'Work directly', title: 'Workers exchange requests and replies',
    day: 'DAY 02', duration: 16000, topic: 'messages', status: 'API and UI in parallel',
    caption: 'Ask the worker who has the answer',
    description: 'Workers talk directly about implementation details. Shared decisions go on the board, where the coordinator can account for them in the plan.',
    actors,
    messages: {
      lead: [message(0, 'assistant', 'API and UI can proceed in parallel. Coordinate implementation details directly; record changes to the shared contract.')],
      api: [
        tool(2300, 'xsm_send', { target: 'ui-worker', text: 'I added read_at to the event. Can the UI handle it?' }, 'sent-unconfirmed: queued (id a153c0e9287b4d16)'),
        inbox(7000, 'ui-worker', 'eb2047ca9d3618f5', 'Yes. I will use read_at for read state, then update the list.'),
        tool(9000, 'xsm_board', { action: 'set', team: 'notifications', item: 'decision: read-state', text: 'Use read_at for read state in the event contract.' }, 'set decision: read-state (node 728fa614dc03)'),
      ],
      ui: [
        inbox(3900, 'api-worker', 'a153c0e9287b4d16', 'I added read_at to the event. Can the UI handle it?'),
        message(5200, 'assistant', 'Yes. I can map read_at to the read state and update the list.'),
        tool(6500, 'xsm_send', { target: 'api-worker', text: 'Yes. I will use read_at for read state, then update the list.' }, 'sent-unconfirmed: queued (id eb2047ca9d3618f5)'),
      ],
      qa: [inbox(11000, 'qa-worker', 'bd38a60e291f7c45', 'Adding read-state changes to the regression checks.')],
    },
    boards: [{ at: 0, title: 'progress: notifications', items: [item('done', 'Schema and API contract agreed.'), item('active', 'API and UI implementation in parallel.'), item('waiting', 'Luna: integration and regression checks.')] }, { at: 9600, title: 'decision: read-state', items: [item('done', 'Use read_at to represent read state.'), item('active', 'Sol: UI / Opus: API implementation.'), item('waiting', 'Luna: read-state regression checks.')] }],
    flows: [{ at: 2300, text: 'api-worker -> ui-worker: DM queued' }, { at: 7000, text: 'ui-worker -> api-worker: reply received' }, { at: 9600, text: 'api-worker: shared decision recorded' }],
  },
  {
    id: 'progress', number: '03', short: 'Keep the plan', title: 'Fable maintains the long-term plan',
    day: 'DAY 03', duration: 18000, topic: 'progress', status: '8 / 12 verified · 2 in progress · 2 waiting',
    caption: 'Plans, decisions, owners and progress',
    description: 'The coordinator checks worker reports against acceptance criteria. It records verified work, blockers and the next steps so the plan survives a long-running task.',
    actors,
    messages: {
      lead: [
        message(0, 'you', 'Where are we against the plan? Report blockers and next steps, then keep going.', 'user'),
        tool(2100, 'xsm_board', { action: 'show', team: 'notifications' }, '# notifications board\n## progress: notifications\nAPI checks recorded; integration checks in progress.'),
        message(10500, 'assistant', '8 of 12 checks are verified. Duplicate notifications on reconnect remain. I am scheduling the UI fix before the next regression run.'),
        tool(13300, 'xsm_board', { action: 'set', team: 'notifications', item: 'progress: notifications', text: '8/12 verified. Sol fixes reconnect duplicates; Luna reruns regression checks after the fix.' }, 'set progress: notifications (node 48d631ab9c20)'),
      ],
      api: [message(2200, 'assistant', 'Schema and API checks pass. I will send the evidence to the coordinator.'), tool(4300, 'xsm_send', { target: 'lead', text: 'Schema and API verified. Evidence is recorded on the team board.' }, 'sent-unconfirmed: queued (id 74c0a83d2e916bf5)')],
      qa: [inbox(4800, 'qa-worker', '6a892d10b47f3c05', 'Reproduced duplicate notifications after reconnect. Sending the reproduction to Sol.')],
      ui: [inbox(6000, 'qa-worker', '3b7de84a12c065f9', 'Duplicate notifications after reconnect. Reproduction: reconnect after reading an event.'), message(8200, 'assistant', 'I will fix deduplication, then ask Luna to rerun the checks.')],
    },
    boards: [{ at: 0, title: 'progress: notifications', items: [item('done', 'API and schema evidence recorded.'), item('active', 'UI and integration checks in progress.'), item('waiting', 'Review results against the acceptance criteria.')] }, { at: 14000, title: 'progress: notifications — 8 / 12 verified', progress: 8 / 12, items: [item('done', 'Verified: schema and API integration checks.'), item('active', 'In progress: reconnect duplicate fix.'), item('blocked', 'Waiting: regression run after the fix.')] }],
    flows: [{ at: 4800, text: 'qa-worker -> ui-worker: reproduction shared' }, { at: 10500, text: 'Fable: compare reports with acceptance criteria' }, { at: 14000, text: 'Fable: plan updated on the board' }],
  },
  {
    id: 'teams', number: '04', short: 'Coordinate teams', title: 'Independent teams coordinate their work',
    day: 'API TEAM × UI TEAM', duration: 16000, topic: 'teams', status: 'Independent execution · shared agreements',
    caption: 'Cross-team agreements and local plans',
    description: 'Each team keeps its own plan and board. Leads share a coordination team for interfaces, dependencies and integration dates, then update their own teams.',
    actors: { lead: ['Claude Code', 'Fable', 'API lead'], api: ['Claude Code', 'Fable', 'UI lead'], ui: ['Codex', 'Sol', 'UI worker'], qa: ['Coordination', 'Team leads', 'agreement'] },
    messages: {
      lead: [message(0, 'you', 'Let the API and UI teams work independently. Agree the shared contract and integration date, then update each team.', 'user'), inbox(4100, 'ui-lead', 'ade7024bc681f935', 'Use the v2 read_at contract. Can we integrate on Friday?'), tool(8500, 'xsm_send', { target: 'ui-lead', text: 'Agreed: v2 contract, Friday integration. I will update the API team plan.' }, 'sent-unconfirmed: queued (id 81b0a64de9372cf5)')],
      api: [tool(3000, 'xsm_send', { target: 'api-lead', text: 'Use the v2 read_at contract. Can we integrate on Friday?' }, 'sent-unconfirmed: queued (id ade7024bc681f935)'), message(6500, 'assistant', 'I will record our agreement on the coordination board.')],
      ui: [inbox(11000, 'ui-lead', '9b03516c8da427ef', 'The coordination board has the v2 contract. Apply it to the UI.'), message(13000, 'assistant', 'Contract read. Updating the UI against the agreed version.')],
      qa: [inbox(12500, 'ui-lead', 'ac509e81f4d2b673', 'v2 contract and Friday integration agreed. Both team plans updated.')],
    },
    boards: [{ at: 0, title: 'coordination: open items', items: [item('active', 'Shared notification event contract.'), item('waiting', 'Reflect changes in each team plan.'), item('waiting', 'Agree an integration date.')] }, { at: 9500, title: 'decision: integration', items: [item('done', 'Contract: notification events v2.'), item('active', 'Each lead updates its own team plan.'), item('waiting', 'Integration checks: Friday.')] }],
    flows: [{ at: 3000, text: 'ui-lead -> api-lead: coordinate directly' }, { at: 9500, text: 'Team leads: agreement recorded' }, { at: 11000, text: 'Each team: apply the agreement locally' }],
  },
];

const source = path => `${repository}/blob/main/${path}`;
export const topics = [
  {
    id: 'start', label: 'Getting started', scene: 0, title: 'Install and start working together',
    intro: 'Connect xsm to Claude Code and Codex, then ask in ordinary language. Your agent reads the instructions, finds the right session and contacts it.',
    sections: [
      { title: '01  Ask your agent to connect', paragraphs: ['Send the following request to the agent you already use. It installs xsm, checks the setup and tells you about any remaining steps, such as trusting a hook or starting a new session.'], prompt: installPrompt, copy: 'Copy installation request' },
      { title: '02  Start the first conversation', paragraphs: ['In a new session, ask the agent to find a collaborator. It shows candidates so you can choose one. Connecting another folder or session follows the required user confirmation.'], prompt: 'Find the sessions working on the UI and show me the candidates.\nAsk the session I choose to review the notification API contract.', copy: 'Copy collaboration request' },
      { title: '03  Assign roles and continue', paragraphs: ['For long-running parallel development, use a coordinator that keeps the plan and workers at the same depth. The coordinator owns the goal and acceptance criteria; workers collaborate directly within their assignments.'], link: ['team', 'Set up roles and relationships'] },
    ], references: [['Installation and usage', source('README.md')], ['Troubleshooting', source('skills/xsm/references/troubleshooting.md')]],
  },
  {
    id: 'team', label: 'Form a team', scene: 0, title: 'Roles and working relationships',
    intro: 'Describe the organization in natural language: who maintains the plan, who owns each task, and who should collaborate directly.',
    sections: [
      { title: 'The coordinator maintains the goal and plan', paragraphs: ['Choose Fable in the runtime and give that session the coordinator role. State the goal, acceptance criteria and constraints. It divides the work, checks results and maintains progress. Model selection happens in each runtime.'] },
      { title: 'Workers operate at the same depth', paragraphs: ['Primary and supporting workers are working roles. Opus or Sol can own implementation and verification; a supporting worker such as Luna can handle a bounded investigation or check. Asking a peer for help does not create another level of delegation.', 'Use a harness subagent for a small, one-off task. Use a persistent worker session when it needs its own context, address and ongoing collaboration.'], prompt: teamPrompt, copy: 'Copy team request' },
      { title: 'Choose the organization for the work', paragraphs: ['This is the recommended pattern for long-running parallel development. A group of peers discussing a design, or agents reviewing each other, can follow different rules you specify. xsm provides communication and shared state; it does not automatically enforce an organization or voting process.', 'A role description is separate from team membership and communication permissions. Agents perform the setup steps and ask for the decisions that require your confirmation.'] },
    ], references: [['Organizational patterns', source('README.md#recommended-use-long-running-parallel-development')], ['Teams and boards', source('skills/xsm/references/teams.md')]],
  },
  {
    id: 'messages', label: 'Requests and replies', scene: 1, title: 'Send a DM and get the answer back',
    intro: 'A DM asks someone to act or answer. Workers contact the session with the relevant information and return their results to the requester.',
    sections: [
      { title: 'Ask the worker who has the answer', paragraphs: ['Include the context and the specific answer you need. The coordinator does not need to relay every API-to-UI implementation question. If a shared assumption or owner changes, tell the coordinator and update the board.'], prompt: 'Ask the UI worker whether read_at works for read state.\nUse the reply to update the API contract and record the shared decision on the team board.', copy: 'Copy direct request' },
      { title: 'Stored, delivered, acknowledged and answered are different', paragraphs: ['Saving a message, reaching the runtime, receiving an acknowledgement after it is read, and getting an answer are distinct facts. A delivery receipt is not proof that the task is complete.', 'Replies return to the requesting session. The agent can continue other work and recover the result by request ID instead of running a long shell polling loop. Wake behavior depends on the runtime and binding.'] },
      { title: 'Discovery does not grant permission', paragraphs: ['Sessions in the same repository and explicitly published sessions can be discovered. Discovery and permission to collaborate are separate. Publishing a session does not connect every session or folder to it.'] },
    ], references: [['Discovery and messaging', source('skills/xsm/references/messaging.md')], ['Confirmation and communication scope', source('skills/xsm/references/permissions.md')]],
  },
  {
    id: 'board', label: 'The team board', scene: 1, title: 'Keep the current plan and decisions on the board',
    intro: 'Use a DM to request action. Use the board for the plan, decisions, owners and progress that apply to the whole team.',
    sections: [
      { title: 'Shared state you can read again', paragraphs: ['The board shows the current state of each item. Record the goal, acceptance criteria, current decisions, owners, progress and blockers so they do not live only in one coordinator conversation.'] },
      { title: 'Read before updating', paragraphs: ['Read the current item before changing another member\'s work. An unseen concurrent update stays alongside yours instead of being silently overwritten. Read both versions and settle the current state.'], prompt: 'Read the current plan and owners on the team board.\nRecord the agreed API contract change and tell the affected workers.', copy: 'Copy board update request' },
      { title: 'Connect decisions to the action they require', paragraphs: ['When a decision requires someone to act, send a DM that points to the board item and makes a concrete request. Avoid maintaining competing copies of the plan in messages and on the board.'] },
    ], references: [['Team board reference', source('skills/xsm/references/teams.md')]],
  },
  {
    id: 'progress', label: 'Plans and progress', scene: 2, title: 'Fable maintains the long-term plan',
    intro: 'The coordinator compares worker reports with the acceptance criteria. It accounts for finished work, blockers and the next steps in the plan.',
    sections: [
      { title: 'Define how completion will be checked', paragraphs: ['Give each task an owner, the required inputs, an expected output and a way to verify it. Receiving a reply and verifying a finished task are different events.'], prompt: 'Report the plan as verified, in progress and blocked.\nInclude the evidence for completed items and the remaining work.\nCheck dependencies and update the next steps.', copy: 'Copy progress request' },
      { title: 'Progress is a judgment based on evidence', paragraphs: ['The demo\'s 8 / 12 count summarizes completed items in an example plan. xsm does not automatically estimate development progress. The coordinator checks results and verification evidence before recording what is complete, active or waiting.'] },
      { title: 'Update the plan when work is blocked', paragraphs: ['When verification finds duplicate notifications, the UI and verification workers exchange the reproduction directly. The coordinator records that regression checks depend on the fix and collects decisions that require your input.'] },
      { title: 'Continue from the record the next day', paragraphs: ['Keep the goal, current decisions, owners and progress on the board. When a session changes, prepare the working context and use the handover procedure to continue.'], link: ['handover', 'Hand over the session and its work'] },
    ], references: [['Coordinator and worker responsibilities', source('README.md#recommended-use-long-running-parallel-development')]],
  },
  {
    id: 'teams', label: 'Multiple teams', scene: 3, title: 'Coordinate independent teams',
    intro: 'Split large work by goal or responsibility. Each team keeps its own plan and board and shares the information other teams need.',
    sections: [
      { title: 'Leads also belong to a coordination team', paragraphs: ['API and UI leads can belong to their own work team and a separate coordination team. They use it to agree on shared contracts, dependencies and integration dates. This overlapping membership does not add another level of delegation.'], prompt: 'Let the API and UI teams work independently.\nBoth leads should also join a coordination team.\nAgree the shared contract and integration date there,\nthen reflect the agreement in each team\'s plan and board.', copy: 'Copy coordination request' },
      { title: 'Bring agreements back into each team', paragraphs: ['Leads coordinate as peers and record shared decisions on the coordination board. Each lead then references the agreement when updating its own owners and plan. There is no need to repeat every implementation detail to every team.'] },
      { title: 'Keep communication scope explicit', paragraphs: ['Having several teams does not automatically grant access to every message or board. Connect the collaborators you need and work within the scope the user has allowed.'] },
    ], references: [['Multi-team organization', source('README.md#recommended-use-long-running-parallel-development')], ['Team operations', source('skills/xsm/references/teams.md')]],
  },
  {
    id: 'handover', label: 'Hand over work', scene: 2, title: 'Hand over the session and its context',
    intro: 'Before another session takes over, record the current goal, decisions, verified results, remaining work and relevant board items.',
    sections: [
      { title: 'Leave enough context to continue', paragraphs: ['Explain what was checked against which criteria, whose answer is still pending, and what the next step needs. The successor should be able to read the board and artifacts and continue.'], prompt: 'Prepare a handover summary. Include the goal, current decisions,\nverification evidence, remaining work, pending requests,\nand relevant board items and files.', copy: 'Copy handover request' },
      { title: 'Work handover and profile migration are different', paragraphs: ['Handing work and a team position to another conversation differs from moving the same native conversation to another configuration home. Verify the actual target and follow the user confirmation required by the relevant procedure.'] },
    ], references: [['Handover reference', source('skills/xsm/references/teams.md')], ['Profile migration', source('skills/xsm/references/migration.md')]],
  },
  {
    id: 'runtimes', label: 'Supported runtimes', scene: 0, title: 'Runtimes and bindings',
    intro: 'The main replay uses Claude Code and Codex. xsm 0.6.0 also includes experimental bindings for Pi, OpenCode, Hermes and OpenClaw.',
    sections: [
      { title: 'Keep working in your existing runtime', paragraphs: ['Install the xsm plugin or binding and restart or reload the runtime. Your work stays in its existing sessions; xsm does not require a separate agent runtime or a wrapper around them.'] },
      { title: 'Delivery follows the runtime\'s own path', paragraphs: ['Bindings share messaging and inbox/ACK operations, while wake behavior, question UI and messenger gateways depend on the runtime and configuration. The replay does not imply that every runtime supports every feature identically.'] },
    ], references: [['Claude Code and Codex setup', source('README.md')], ['Pi', source('docs/protocol/pi.md')], ['OpenCode', source('docs/protocol/opencode.md')], ['Hermes', source('docs/protocol/hermes.md')], ['OpenClaw', source('docs/protocol/openclaw.md')]],
  },
];
