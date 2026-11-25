# Fixed-semantics models (SM-MODEL)

Models of `docs/plan/state-model-fixes/spec.md` (sections 0, 3, 8, 12). Each spec is a copy of the original in
`../<lane>/` whose actions follow the fixed semantics. The rules (INVARIANTs) are the originals, same names, same
definitions, except the rows marked CHANGED or ADDED below. Every config reports no `## <Rule> breaks` and keeps
`NoDeadlock`.

Run one config (the output folder must be new):

    SC=~/.jstack/marketplaces/jstack/plugins/jstack/payload/skills/statechart/repos/pstack/skills/statechart/scripts/statechart
    $SC <abs>/fixed/round1/XsmHandover.tla --config <abs>/fixed/round1/XsmHandover.cfg --view <abs>/fixed/round1/view.ts --out <abs>/fixed/round1/out-XsmHandover-2

Run all: `python3 docs/plan/state-model-fixes/req.py check SM-MODEL`. Layout: one spec per folder, except `migration/`
and `teams/`, where the views are named after their specs (`XsmHandoverBoard.ts`) so the discovery in `req.py` pairs them.
`out-<cfg>/` folders hold the last report (and chart when TLC stays under 500 states).

## What changed in each spec

| Lane | Spec | Fixed actions |
|---|---|---|
| round1 | XsmHandover | `HandOverQuestions` (sender swap) now runs before `HandOverBegin` (record, follow(A)=B); `HandOverOriginals` copies A's non-acked DM, held DM stays held (D2), and a reply still at A moves to B; the letter has no body; A's readers stay off during the call; B's gate holds only on deny list (`dmDeny`, new) or a DM already held |
| concurrent | XsmConcurrentHandover | machine-wide `lock`; `Check` re-judges under the lock (double handover and cycle give `refused`, nothing written); effective target `Eff(p)` = follow(Dst), so A->B after B->C seats and asks for C |
| scope-groups | XsmScopeGroups | children move with the group even when final; `copied` (D1) gives P-B scope for the four bases that did not carry |
| migration | XsmHeldDeliver | `HeldDeliver` acknowledges the original |
| migration | XsmTransfer | `HoldWrites` binds to `Owner(s)` (current owner, B once the held list moved); delivered receipt written after `RecordsHandoff` |
| remote | XsmRemote | `origAt` follows the holder (hand_to), `Unreplyable` = original not at the holder; refused reply triggers a pull (`DeliverAnswerPull`); pull failure records `unconfirmed` (`DeliverAnswerUnconfirmed`); `Confirm`, `ConfirmByPull`; `Resend` removed (nothing is refused) |
| teams | XsmHandoverBoard | `ARechecks` after the close carries later heads to owner/B and closes again; skipped item is `reported`; `Ids` 1..5 |
| teams | XsmHandoverPlaces | places listed once in `Begin`; board move and seat swap of a team are one locked step with membership re-check (`MoveTeam`); adds during the handover add B (D9); no abort |
| teams | XsmHandoverTeamSync | origin of a local record is the own key; echo ignored; ties by origin key; loser re-applies unconfirmed ops (`pend`) at generation+1 and resends |

## Verdicts per rule

"Original" = the verdict of the unfixed model (`../*/verify*/report.md`, confirmed by `req.py red SM-MODEL`). "Holds" = holds in
the fixed model, rule text unchanged unless the comment says CHANGED.

| Lane | Spec | Cfg | Rule | Original | Fixed | Comment |
|---|---|---|---|---|---|---|
| round1 | XsmHandover | XsmHandover | HeldStaysHeld | breaks | holds | |
| round1 | XsmHandover | XsmHandover | AnswerRecorded | breaks | holds | needs the order change in finding 1 |
| round1 | XsmHandover | XsmHandover | AckedOnce, WaitHonest, OneHolder | holds | holds | |
| concurrent | XsmConcurrentHandover | Scn_a | AtMostOneHandoverPerSession, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded | breaks | holds | A->B and A->C: the second is refused |
| concurrent | XsmConcurrentHandover | Scn_b | AddressLeadsAway, HandedOverHoldsNoPlace, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded | breaks | holds | A->B and B->A: the cycle is refused |
| concurrent | XsmConcurrentHandover | Scn_c | HandedOverHoldsNoPlace, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded | breaks | holds | A->B and B->C: both can succeed (chain), either order |
| concurrent | XsmConcurrentHandover | XsmConcurrentHandover | all six | breaks | holds | all four plans, two started |
| scope-groups | XsmScopeGroups | XsmScopeGroups | LateAnswerReachesSuccessor, GroupShowsEveryAnswer, GroupStatusTruthful | breaks | holds | copy failure not modelled (finding 2) |
| scope-groups | XsmScopeGroups | XsmScopeGroups | WaitingOnHonest, OpenQuestionsBelongToHolder, TypeOK | holds | holds | |
| migration | XsmHeldDeliver | XsmHeldDeliver | YesIsFinal | breaks | holds | |
| migration | XsmHeldDeliver | XsmHeldDeliver | HeldNeedsYes | holds | holds | |
| migration | XsmTransfer | XsmTransfer | HeldFollowsOwner | breaks | holds | assumes current_owner(A)=B once the held list moved (mig held or committed) |
| migration | XsmTransfer | XsmTransfer | DeliveredMeansShown | breaks | holds | |
| migration | XsmTransfer | XsmTransfer | AckedOnce, NoStrandedOriginal, NoLostCopy, HeldNotShown | holds | holds | |
| remote | XsmRemote | XsmRemote, XsmRemoteStranger, scenarioAskedAfter, scenarioChain, scenarioLost | AnswerRecorded | breaks | holds | text unchanged; holds because a successor answer is never refused. A recorded answer may carry `unconfirmed` (spec 12) |
| remote | XsmRemote | same five | ViewsAgree | breaks | holds | CHANGED: premise adds `ans[holder] \in {recorded, unconfirmed, refused}`, conclusion adds `\/ ans[holder] = "unconfirmed"`. R reads its stored testimony only when it judges an answer and the pull repairs it then, so the rule is checked from that moment |
| remote | XsmRemote | scenarioUnread | QuestionAnswerable | breaks | holds | rule text unchanged; `Unreplyable` redefined as `asked /\ ~qRead /\ origAt /= holder` (hand_to moves the original) |
| remote | XsmRemote | all eight | StrangerNeverRecorded, QuestionAnswerable | holds / holds | holds | stranger X is a session of another machine (never pulled for, never recorded); a same-machine stranger recorded as unconfirmed (spec 12) is not modelled |
| remote | XsmRemote | all eight | SuccessorAnswerKept | (not in original) | holds | ADDED: no successor answer is ever `refused` |
| remote | XsmRemote | scenarioMember, scenarioOrdering | all | holds | holds | no break before either |
| teams | XsmHandoverBoard | XsmHandoverBoard | MovedItemIsClosed, NoContentLeftBehind | breaks | holds | |
| teams | XsmHandoverBoard | XsmHandoverBoard | EveryOwnerItemClosed | breaks | holds | CHANGED: `(all heads are notes) \/ (skipped /\ reported)`. Spec P5 does not move a multi-head item, it reports it (SM-F7) |
| teams | XsmHandoverPlaces | XsmHandoverPlaces | PlaceAndItemsMoveTogether, NoPlaceLeftBehind, BCanReachWhatMoved | breaks | holds | needs finding 3 |
| teams | XsmHandoverPlaces | XsmHandoverPlaces | NoSeatInATeamALeft | (not in original) | holds | ADDED (F17): B is in a team only if it was added while the handover ran, or A was in the team when the handover began and was not removed from it since. History variables `left` and `added` carry the facts. Last report: `out-XsmHandoverPlaces-2/` |
| teams | XsmHandoverTeamSync | XsmHandoverTeamSync | HandoverStands, SameTeamAtRest, BHoldsTheSeatEverywhere | breaks | holds | `acked_by` and the conflict log are not modelled (op confirmation = the record holds the op) |

## Findings for the plan (the fixed spec, as written, leaves these open)

1. **Order of `_begin` and `_questions` (round1).** Spec 3.2 writes the record first (follow(A)=B) and `_questions` later. Run in that
   order, TLC finds `AnswerRecorded` broken: P's reply goes to B's folder while the question's sender is still A, B's
   reader takes it, `record_reply` (receiver == sender) does not index it. The model passes only with the sender swap before the
   record write (the reply then lands at A, where `hand_to` moves it) or an equivalent guard that keeps B from consuming
   replies of a `moving` handover before the swap. Confirmed by mutation (`round1-order`).
2. **Link copy window and copy failure (scope-groups).** The model copies links in the same step as the question move. Per spec 3.2 the
   record exists (follow(A)=B) before `_copy_links`; a late answer in that window meets `scope_for(P, B)` without the copy and is
   refused. A failed copy (spec 6) leaves P without scope to B, so `LateAnswerReachesSuccessor` would not hold for that connection;
   neither case is in the model.
3. **Boards and teams as two re-checking steps (places).** Spec 3.2 has `boards` and `teams` as separate steps that each re-check
   membership. With a removal of A between the two, items move to owner/B and B is not seated: `PlaceAndItemsMoveTogether` and
   `BCanReachWhatMoved` break (checked with a scratch two-step variant). The model keeps both per team in one locked step. The
   implementation needs the same, or one step must decide membership and the other must follow it.
4. Rules that no mutation caught (not evidence of absence): in `XsmHandoverPlaces`, dropping the membership re-check alone keeps all
   three rules true (B joins a team A just left); the acceptance sentence "B does not join a team A left" has no rule.
   **Closed (F17, spec 2.1):** the rule `NoSeatInATeamALeft` now states it. Mutation: with the re-check dropped in `MoveTeam`
   (`IF aIn[t]` replaced by `IF TRUE`, scratch copy) TLC reports `NoSeatInATeamALeft breaks` in 3 steps (Begin, OutsideRemoves, MoveTeam)
   and the other three rules keep holding; restored, all four hold. Code: `handover._teams` re-checks membership under the team's
   lock, and `handover._revert_board` takes the board move back for a team A left between the boards step and the teams step (F16).
5. Spec gaps 1 to 3 became code in this phase: F14 (finding 1: `questions.record_reply` takes the successor of the record's sender,
   and a final answer the successor read inside the window moves with the question), F15 (finding 2: a reply to a question of a
   handed-over conversation passes `send` and the receiving gate on the scope the peer had with A, marker `handover:<id>`; the copy
   also carries the named projects A joined), F16 (finding 3: the revert above).

## Mutation checks (rule detects its fix being removed)

Reverting one piece of each fix in a scratch copy broke the named rule: concurrent without lock (Scn_a: four rules), held deliver without
ack (YesIsFinal), transfer hold bound to A (HeldFollowsOwner), board without recheck (MovedItemIsClosed, NoContentLeftBehind,
EveryOwnerItemClosed), remote without originals moved (QuestionAnswerable), remote without pull and without unconfirmed
(SuccessorAnswerKept, AnswerRecorded, ViewsAgree), team sync without re-apply (HandoverStands, BHoldsTheSeatEverywhere), scope
groups without copy (LateAnswerReachesSuccessor), scope groups with final children left (GroupShowsEveryAnswer,
GroupStatusTruthful), round1 without the sender swap (AnswerRecorded), places without the membership re-check
(NoSeatInATeamALeft, F17). Not caught by these rules: concurrent Scn_c without the lock
(effective target following already covers it).

## Note on `req.py red SM-MODEL`

It pairs each original cfg with `views[0]` when no view name matches the cfg stem. In `migration/` and `teams/` of the originals
the pairing is wrong for three configs (`XsmHeldDeliver`, `XsmHandoverBoard`, `XsmHandoverPlaces`), which then do not report their
breaks (the command still succeeds because other configs break). Not changed here (outside `fixed/`).
