# Active goal handoff: 계획 완수

2026-11-05. Goal remains active. The full objective is the two plans in
`docs/plan/runtime-protocol/approval-recovery-test-alignment.md` and
`docs/plan/runtime-protocol/session-profile-migration.md`, including all 14 migration
acceptance items, actual isolated two-home Claude verification, required gates and docs.
Do not redefine completion around the work already committed.

## Committed work

- `ccec308`: registry uses runtime/home/session_id, imports legacy files exactly,
  home-aware caller/end/prune/worker/protocol/handover lookups; MCP own-home preference.
  New 13 regression tests; owning 342 tests OK. Two pre-fix faults caught in temp copies.
- `0de57f3`: same-MCP native recovery for dismissed/unshown/unknown forms, fresh-evidence
  cutoff, explicit denial/race guards and response history; usable outside-scope grant;
  aligned old 16 failures and a 9-operation allow/deny matrix. New 27 tests including
  uncertainty, wrong question, stale answer, denial races, repeat receipts and grant use.
  Current focused 139 tests OK; broader 356 tests OK before final case additions.
  Five planned permission/gate faults caught; source hashes match current files.
- `97afd3f`: preserve raw CLI profiler whitespace with a scoped .gitattributes.

`scripts/check-protocol.py` now requires the formerly omitted approval tests plus
registry/native permission cases. First expanded gate passed in 66.464 seconds;
several final regression test additions came later, so this is not the final goal gate.
The final gate and full unittest discovery remain required after migration integration.

## Next implementation work (not done)

1. Implement explicit profile migration in one shared service, CLI/MCP/native entry,
   with exact endpoint/generation approval and recoverable durable phases.
2. Fence source registration/adoption/sending/claims/late ACK; ordinary handover and
   ordinary same-home resume remain supported. A source can only reclaim via a new
   explicit user decision. Mixed unsupported versions must not be silently accepted.
3. Forward old ref/name/P2P endpoint for 24 hours from commit; expiration never restores
   the source. Keep forwarding distinct from immutable ownership/succession evidence.
4. Preserve canonical unread messages, held records, peer questions/groups, worker
   coordinator links and pending project requests. Pending human permissions transfer
   their requests, not old allow answers/consumption markers/claim tokens.
5. Catch-up view, resolution-failure audit with exact visibility, duplicate-home doctor
   diagnostics, idempotent notices and crash/retry verification.
6. Required schema/SDK/tool list/docs/skills and test-gate changes for the new operation.
7. Five planned migration fault checks, all 14 acceptance items, complete local suite,
   and a small real isolated Claude same-ID/two-home case. No actual migration UI/model
   testing has run in this goal so far. User profiles must not be changed.

Existing handover.py already moves team places, boards, unread DMs, peer questions and
follows addresses. It intentionally leaves the old actor ordinary and does not move
human permission requests or worker-links: reuse it carefully, do not claim it fences.
handoff.move_out currently closes originals as moved; migration requires preserving
delivery and ACK meaning, plus new claims at the successor. Legacy inbox files are keyed
by SID and need exact receiver filtering for same-SID copies.

## Workspace and authority

- Current branch main. User authorized local intermediate commits; no push, issue
  comments, PR/merge, global installation, profile permission edits or release performed.
- No real models/providers were called in this goal; all native evidence in new tests
  is synthetic and clearly labelled. Test homes and state are temporary.
- Preserve unrelated docs/references/README.md, herdr-core.md and the two docs-051
  deliverable directories. Shared approval plan includes another investigator's
  cctrace section; preserve it and do not claim this agent executed that investigation.
- Plan files and earlier planning evidence remain untracked intentionally so far;
  implementation evidence is committed under this directory.
- Dedicated private task record: issue27-implementation-codex2-20261105, revision 1,
  four code requirements. No passing workflow/code completion assessments yet.
- Earlier shared planning task had concurrent changes; do not mutate that private
  task ID. The goal is independent and remains active.

Keep failed runs and ineffective mutation attempts in the evidence. The first denial
mutator did not reach the faulty branch; final mutation changes actual answer decoding.
The first raw profiler log triggered whitespace checking; its bytes are preserved and
the exception is scoped to this artifact directory's logs.
