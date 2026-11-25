--------------------------- MODULE XsmHandoverPlaces ---------------------------
(***************************************************************************)
(* FIXED SEMANTICS (docs/plan/state-model-fixes/spec.md F6, D9, P1).      *)
(* A handover from A to B when A is in several teams                       *)
(* (xsm/handover.py hand_over, _boards, _teams; xsm/teams.py teams_of).    *)
(*                                                                         *)
(* The place list is computed ONCE, in _begin (`places`), and both the     *)
(* board move and the membership swap of a team work on it.  For each team *)
(* the board move and the swap happen under that team's lock and A's       *)
(* membership is RE-CHECKED there: a team A has been removed from is       *)
(* skipped (neither items moved nor B added) and listed.  While the        *)
(* handover record exists a lead who adds A to a team gets the successor B *)
(* added instead (D9, follow()).  There is no abort.                       *)
(*                                                                         *)
(* Board move and swap of one team are ONE step here (see README, finding  *)
(* 3): spec 3.2 lists `boards` and `teams` as two steps that each re-check;*)
(* a removal between them would move the items without seating B.          *)
(*                                                                         *)
(* Each team t has an owner/A item on its board.                           *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

Teams == {"t1", "t2"}

VARIABLES
  aIn,      \* A is a member of team t
  bIn,      \* B is a member of team t
  moved,    \* teams whose owner/A items were moved to owner/B
  swapped,  \* teams where B took A's place
  places,   \* teams in the list made once, in _begin
  todo,     \* teams of that list not handled yet
  skipped,  \* teams of the list A had left by the time they were handled
  left,     \* teams A was removed from while the handover ran (history, for NoSeatInATeamALeft)
  added,    \* teams B was added to while the handover ran (D9: the successor is added instead of A)
  phase,    \* idle | begun | done
  churn     \* how many outside changes have happened

vars == <<aIn, bIn, moved, swapped, places, todo, skipped, left, added, phase, churn>>

Init ==
  /\ aIn = [t \in Teams |-> t = "t1"] /\ bIn = [t \in Teams |-> FALSE]
  /\ moved = {} /\ swapped = {} /\ places = {} /\ todo = {} /\ skipped = {}
  /\ left = {} /\ added = {}
  /\ phase = "idle" /\ churn = 0

\* _begin: the handover record exists (follow(A) = B) and the teams of A are
\* listed, once.
Begin ==
  /\ phase = "idle"
  /\ places' = {t \in Teams : aIn[t]} /\ todo' = {t \in Teams : aIn[t]} /\ phase' = "begun"
  /\ UNCHANGED <<aIn, bIn, moved, swapped, skipped, left, added, churn>>

\* One team of the list, under the team lock: A is still a member -> its items
\* move and B takes A's place; A has been removed meanwhile -> skipped, listed.
MoveTeam(t) ==
  /\ phase = "begun" /\ t \in todo
  /\ todo' = todo \ {t}
  /\ IF aIn[t]
       THEN /\ moved' = moved \cup {t} /\ swapped' = swapped \cup {t}
            /\ aIn' = [aIn EXCEPT ![t] = FALSE] /\ bIn' = [bIn EXCEPT ![t] = TRUE]
            /\ UNCHANGED skipped
       ELSE /\ skipped' = skipped \cup {t}
            /\ UNCHANGED <<aIn, bIn, moved, swapped>>
  /\ UNCHANGED <<places, left, added, phase, churn>>

Finish ==
  /\ phase = "begun" /\ todo = {}
  /\ phase' = "done"
  /\ UNCHANGED <<aIn, bIn, moved, swapped, places, todo, skipped, left, added, churn>>

\* A lead of the same project adds A to a team (teams.add): no approval needed.
\* Once the handover record exists the successor B is added instead of A (D9).
OutsideAdds(t) ==
  /\ phase = "begun" /\ churn = 0 /\ ~aIn[t] /\ ~bIn[t]
  /\ bIn' = [bIn EXCEPT ![t] = TRUE] /\ added' = added \cup {t} /\ churn' = 1
  /\ UNCHANGED <<aIn, moved, swapped, places, todo, skipped, left, phase>>

\* The lead removes A from a team (teams.remove).
OutsideRemoves(t) ==
  /\ phase = "begun" /\ churn = 0 /\ aIn[t]
  /\ aIn' = [aIn EXCEPT ![t] = FALSE] /\ left' = left \cup {t} /\ churn' = 1
  /\ UNCHANGED <<bIn, moved, swapped, places, todo, skipped, added, phase>>

Done == phase = "done" /\ UNCHANGED vars

Next ==
  \/ Begin \/ Finish
  \/ \E t \in Teams : MoveTeam(t) \/ OutsideAdds(t) \/ OutsideRemoves(t)
  \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------- rules ---------------- *)

\* handover.py docstring: "What moves, at once: team places ...; the board items
\* it owns". PROTOCOL 5.15 lists both moves for each team. In every team the
\* board items and the place move together.
PlaceAndItemsMoveTogether == phase = "done" => moved = swapped

\* handover.py docstring: "The old session keeps running as an ordinary session
\* with no team place."
NoPlaceLeftBehind == phase = "done" => (\A t \in Teams : ~aIn[t])

\* The letter and the board tell B the items are its own (owner/B): B can read
\* and write the board only as a member (board._require_member).
BCanReachWhatMoved == phase = "done" => (\A t \in moved : bIn[t])

\* spec 5 SM-F6 / README finding 4: "a team A left is not joined by B". B is in a team
\* only if A was in it when the handover began and was not removed from it since, or
\* B was added while the handover ran (D9). Without the membership re-check in
\* MoveTeam, B is seated in a team A was removed from after Begin.
NoSeatInATeamALeft == \A t \in Teams : bIn[t] => (t \in added \/ (t \in places /\ t \notin left))
=============================================================================
