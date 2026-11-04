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

## Core migration checkpoint (second goal turn)

Core service is now implemented in xsm/migration.py and xsm/migration_state.py.
CLI: xsm migrate SOURCE, no source reads status. MCP/protocol: xsm_migrate.
It journals prepare/fence/move/commit, freezes exact executions, forwards for
24 hours, retains unread canonical bodies/digests, revokes old claims, transfers
team/board/question/worker state and holds. Human permissions transfer as requests;
an unknown already-started application stays inspect-outcome, never a new grant.
Source registration is blocked, including old generations after restoring a newer
execution. CLI narrowing writes and stale exit hooks are also fenced.

Implemented source-history ID snapshots prevent an old receipt reading later work
after the source was reclaimed. New inputs addressed through old refs carry internal
profile_forwarding metadata and appear in catch-up. Incoming file bytes remain
accessible only through verified migration ownership without renewing retention.

Evidence: migration-core-final.log has 187 targeted tests OK under explicit
Python 3.14. Python SDK real stdio migration/claim/ACK and Node SDK migration each
pass. Schema examples5/invalid11 pass. This is not full-goal verification.
Default python3 externally changed to 3.15.2 and lacks jsonschema; use
/opt/homebrew/opt/python@3.14/bin/python3.14 for comparable gate/schema results.
Several earlier unpinned logs cannot establish an exact interpreter version.

Remaining before completion:

- Finish diagnostic wiring: migration.diagnostics exists but doctor does not use it.
- Preserve/look up retired name/ref aliases if their registry pointer is cleared.
- Implement refusal/outgoing-attempt audit and its caller-scoped catch-up projection.
- Test and finish P2P migration paths, especially already-admitted originals: the
  gateway inbound record currently names its original local endpoint; successor
  receive/admission must recognize the verified transferred canonical copy. Test
  queue/store races and cross-profile protocol actors too.
- Verify remaining crash/retry/notification edge cases and all 14 plan requirements;
  add five scoped migration fault injections. Publication failures are retained as
  pending and resumed on explicit same-transfer retry, not reported as delivered.
- Add user README/skills migration guidance and docs; plan files remain untracked.
- Full current gate and complete unittest discovery, then small actual isolated
  Claude same-ID/two-home test. No real model or migration user UI has run yet.
- Add/finalize contract/workflow receipts for the code task, then requirement-by-
  requirement goal completion audit. Do not mark complete from this checkpoint.

Native generation fences use the source index's blocked_generations. _caller_record
keeps a retired CLI process from borrowing a restored pointer. Some APIs intentionally
keep diagnostic access; migration status never grants old human permissions.
If a user opens simultaneous processes for the same home/SID, an obsolete instance
cannot replace a newer registered instance while retired; use the selected window.

The original remaining-work outline follows; the implementation above supersedes
its status, not its acceptance scope.

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

## Remote ingress and diagnostics checkpoint (third goal turn)

- Added sender-owned failure audit (including unresolved refs), source-epoch scoped
  catch-up, archived aliases after registry pruning, and doctor generations/expiry/owner state.
- Real gateway fixtures caught P2P migrated ingress/admission/ACK/duplicate evidence issues.
  Fixed verified copy traversal and preserved native generation metadata, global reservation
  checks and profile locks. Initial failing network logs are retained.
- Refused sends now keep a supplied request ID. Expanded gate exposed an owned reply
  mismatch caused by allocating a fresh audit ID, then conformance's legacy null-ID
  expectation. Fixed the former and aligned the latter with retained-ID behavior.
- Migration mutation suite caught all five planned faults in temp source copies.
- Current actual Claude 2.1.318 test uses isolated a/b homes with a copied transcript
  and native ID f55ac2bc-7ee6-4e96-9ced-9b5b6fb0e775. Existing subscription OAuth is
  injected only into the child; no API key, keychain or real-profile settings change.
  First launch inherited CHILD_SESSION and disabled transcript; interrupted and not counted.
  Corrected launcher strips inherited harness markers. Both native sessions registered
  distinct refs/sockets, B resumed copied history, actual native MCP form accepted
  the user's allow, and migration committed with an exact 86400-second lease.
  Native A's xsm_send was refused as retired. SDK model0 peer sent to the old ref and
  stored at B. B native read/ACK and final config/hash audit are still being checked.
- First complete unittest discovery is still running (not final-source evidence).
  Final gate has been rerun after compatibility fixes; read logs for the outcome.
- README/KO and routed migration skill guide now cover explicit transfer, catch-up,
  approval rebinding, 24h expiry and unknown outcomes. No push/release/issue posting.

## Local implementation completion audit

- See verification.md for all 14 migration criteria, 18 approval cases and raw evidence.
- 148 discovered modules / 2774 tests: zero failures or errors, 3 documented conditional
  skips. No test inventory omitted. Group 1 was rechecked after expanding MCP denial
  and peer-group late-reply/crash assertions; final acceptance bundle is 77 tests.
- Native Claude two-home test completed (real form/real user allow, source send refused,
  old-ref delivery at B, native hook token ACK). Both processes exited; real config
  hashes unchanged. Unused opaque credential copies removed from temporary profiles.
- Latest full protocol gate: exit 0 in 57.856s, Python3.14.6. SDK/schema/independent
  consumer and required native binding fixtures passed. No fresh model/messenger runs
  on Pi/OpenCode/Hermes/OpenClaw. Historical cctrace observations are not our native test.
- Identity2 + permission5 + migration5 deliberate regressions were detected.
- Actual old capacity raw replay, supplied private log replay and opt-in official
  relay test remain explicitly unexecuted; none is reported as passed.
- Legacy full-discovery failures were catalogued before edits; fixture source/home,
  API error/ID expectations and tool inventory were aligned without removing tests.
- No .jstack task.json exists in this checkout; workflow status reported ENOENT,
  so no separate workflow receipt is claimed. Protected oracle accepted with a
  recorded explanation for the conditional historical fixture skip.
- External publish/push/PR/merge/release/issue close remain unperformed.
