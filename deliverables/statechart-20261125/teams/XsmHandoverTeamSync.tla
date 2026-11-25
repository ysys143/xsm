------------------------- MODULE XsmHandoverTeamSync -------------------------
(***************************************************************************)
(* xsm 0.6.1: the team record after a handover, on two machines            *)
(* (xsm/handover.py _teams + team_sync.publish, xsm/team_sync.py receive). *)
(*                                                                         *)
(* Machines X and Y hold the same team. A (lead) and B live on X. X hands  *)
(* A's seat to B: the record gets generation+1, A leaves, B takes the seat *)
(* and the lead's place, and X publishes the whole record to Y. Meanwhile  *)
(* Y makes some other change to the team (generation+1) and publishes it.  *)
(*                                                                         *)
(* receive() takes an incoming record only when                             *)
(*   (incoming.generation, sending machine) > (local.generation, local.origin) *)
(* where local.origin is the machine this record was LAST RECEIVED FROM    *)
(* (absent, i.e. "", on the machine that created it; a local change does   *)
(* not touch it). The whole record is replaced, never merged.              *)
(* Y's machine key is larger than X's.                                      *)
(*                                                                         *)
(* Org: 0 = none, 1 = X, 2 = Y.                                             *)
(***************************************************************************)
EXTENDS Naturals

Machines == {"X", "Y"}
Key == [m \in Machines |-> IF m = "X" THEN 1 ELSE 2]
Other == [m \in Machines |-> IF m = "X" THEN "Y" ELSE "X"]

VARIABLES
  rec,       \* rec[m] = [gen, org, hand, ext]
  msgs,      \* records in flight
  handDone,  \* X has made the handover
  yDone      \* Y has made its own change

vars == <<rec, msgs, handDone, yDone>>

Init ==
  /\ \E o \in {<<0, 1>>, <<2, 0>>, <<2, 1>>} :
       \* created on X (X none, Y got it from X); created on Y; or both have since
       \* received one change from the other
       rec = [m \in Machines |-> [gen |-> 1, org |-> IF m = "X" THEN o[1] ELSE o[2],
                                  hand |-> FALSE, ext |-> FALSE]]
  /\ msgs = {} /\ handDone = FALSE /\ yDone = FALSE

\* hand_over: _teams writes generation+1 with B in A's place; team_sync.publish sends it.
HandOver ==
  /\ ~handDone
  /\ LET r == [rec["X"] EXCEPT !.gen = @ + 1, !.hand = TRUE] IN
       /\ rec' = [rec EXCEPT !["X"] = r]
       /\ msgs' = msgs \cup {[from |-> "X", to |-> "Y", gen |-> r.gen, hand |-> r.hand, ext |-> r.ext]}
  /\ handDone' = TRUE /\ UNCHANGED yDone

\* Another change on Y (a member added, say), published the same way.
YChanges ==
  /\ ~yDone
  /\ LET r == [rec["Y"] EXCEPT !.gen = @ + 1, !.ext = TRUE] IN
       /\ rec' = [rec EXCEPT !["Y"] = r]
       /\ msgs' = msgs \cup {[from |-> "Y", to |-> "X", gen |-> r.gen, hand |-> r.hand, ext |-> r.ext]}
  /\ yDone' = TRUE /\ UNCHANGED handDone

\* team_sync.receive.
Receives(m) ==
  /\ \E x \in msgs :
       /\ x.to = m
       /\ msgs' = msgs \ {x}
       /\ LET cur == rec[m]
              newer == x.gen > cur.gen \/ (x.gen = cur.gen /\ Key[x.from] > cur.org)
          IN rec' = IF newer
                      THEN [rec EXCEPT ![m] = [gen |-> x.gen, org |-> Key[x.from], hand |-> x.hand, ext |-> x.ext]]
                      ELSE rec
  /\ UNCHANGED <<handDone, yDone>>

Done ==
  /\ handDone /\ yDone /\ msgs = {}
  /\ UNCHANGED vars

Next == HandOver \/ YChanges \/ Receives("X") \/ Receives("Y") \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------- rules ---------------- *)

\* handover.py docstring: "The old session keeps running as an ordinary session
\* with no team place"; PROTOCOL 5.15: the team's member and lead seat are swapped.
\* The machine that made the handover keeps A out of the team and B in its seat.
HandoverStands == handDone => rec["X"].hand

\* team_sync.py docstring: "A team ... is kept on each of those machines as the
\* same record"; once nothing is in flight the two machines hold the same team.
SameTeamAtRest == msgs = {} => (rec["X"].hand = rec["Y"].hand /\ rec["X"].ext = rec["Y"].ext)

\* handover.py docstring and PROTOCOL 5.15: after a handover B holds A's seat on
\* every machine that has the team.
BHoldsTheSeatEverywhere == (handDone /\ msgs = {}) => (rec["X"].hand /\ rec["Y"].hand)
=============================================================================
