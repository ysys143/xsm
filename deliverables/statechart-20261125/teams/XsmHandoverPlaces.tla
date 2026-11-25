--------------------------- MODULE XsmHandoverPlaces ---------------------------
(***************************************************************************)
(* xsm 0.6.1: a handover from A to B when A is in several teams            *)
(* (xsm/handover.py hand_over, _boards, _teams; xsm/teams.py teams_of).    *)
(*                                                                         *)
(* hand_over asks teams_of(A) TWICE: once for the board moves of every team *)
(* (a list made before the first board is touched), and again, later, for  *)
(* the membership swap. Between the two, other people keep working: a lead *)
(* adds A to a team without any approval when it is its own project        *)
(* (teams.add_rule), or removes it.                                        *)
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
  boardTodo,\* teams in the list made before the board moves
  teamTodo, \* teams in the list made before the membership swap
  phase,    \* idle | boards | teams | done
  churn     \* how many outside changes have happened

vars == <<aIn, bIn, moved, swapped, boardTodo, teamTodo, phase, churn>>

Init ==
  /\ aIn = [t \in Teams |-> t = "t1"] /\ bIn = [t \in Teams |-> FALSE]
  /\ moved = {} /\ swapped = {} /\ boardTodo = {} /\ teamTodo = {}
  /\ phase = "idle" /\ churn = 0

\* hand_over: `for team in teams.teams_of(me)` -> _boards(me, target, team)
StartBoards ==
  /\ phase = "idle"
  /\ boardTodo' = {t \in Teams : aIn[t]} /\ phase' = "boards"
  /\ UNCHANGED <<aIn, bIn, moved, swapped, teamTodo, churn>>

\* _boards for one team.
MoveBoard(t) ==
  /\ phase = "boards" /\ t \in boardTodo /\ aIn[t]
  /\ moved' = moved \cup {t} /\ boardTodo' = boardTodo \ {t}
  /\ UNCHANGED <<aIn, bIn, swapped, teamTodo, phase, churn>>

\* board.show -> _require_member raises BoardError when A is no longer in the team:
\* hand_over stops; nothing undoes the boards it already moved, nothing is recorded.
Abort(t) ==
  /\ phase = "boards" /\ t \in boardTodo /\ ~aIn[t]
  /\ phase' = "aborted"
  /\ UNCHANGED <<aIn, bIn, moved, swapped, boardTodo, teamTodo, churn>>

\* `teams_moved = _teams(me, target, approval)`: teams_of(me) asked again.
StartTeams ==
  /\ phase = "boards" /\ boardTodo = {}
  /\ teamTodo' = {t \in Teams : aIn[t]} /\ phase' = "teams"
  /\ UNCHANGED <<aIn, bIn, moved, swapped, boardTodo, churn>>

\* _teams: under the lock, remove A, add B, move the lead's seat.
SwapPlace(t) ==
  /\ phase = "teams" /\ t \in teamTodo
  /\ aIn' = [aIn EXCEPT ![t] = FALSE] /\ bIn' = [bIn EXCEPT ![t] = TRUE]
  /\ swapped' = swapped \cup {t} /\ teamTodo' = teamTodo \ {t}
  /\ UNCHANGED <<moved, boardTodo, phase, churn>>

Finish ==
  /\ phase = "teams" /\ teamTodo = {}
  /\ phase' = "done"
  /\ UNCHANGED <<aIn, bIn, moved, swapped, boardTodo, teamTodo, churn>>

\* A lead of the same project adds A to a team (teams.add): no approval needed.
OutsideAdds(t) ==
  /\ phase \in {"boards", "teams"} /\ churn = 0 /\ ~aIn[t] /\ ~bIn[t]
  /\ aIn' = [aIn EXCEPT ![t] = TRUE] /\ churn' = 1
  /\ UNCHANGED <<bIn, moved, swapped, boardTodo, teamTodo, phase>>

\* The lead removes A from a team (teams.remove).
OutsideRemoves(t) ==
  /\ phase \in {"boards", "teams"} /\ churn = 0 /\ aIn[t]
  /\ aIn' = [aIn EXCEPT ![t] = FALSE] /\ churn' = 1
  /\ UNCHANGED <<bIn, moved, swapped, boardTodo, teamTodo, phase>>

Done == phase \in {"done", "aborted"} /\ UNCHANGED vars

Next ==
  \/ StartBoards \/ StartTeams \/ Finish
  \/ \E t \in Teams : MoveBoard(t) \/ Abort(t) \/ SwapPlace(t) \/ OutsideAdds(t) \/ OutsideRemoves(t)
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
=============================================================================
