------------------------- MODULE XsmHandoverTeamSync -------------------------
(***************************************************************************)
(* FIXED SEMANTICS (docs/plan/state-model-fixes/spec.md F8, D3, 3.4).     *)
(* The team record after a handover, on two machines                       *)
(* (xsm/handover.py _teams + team_sync.publish, xsm/team_sync.py receive). *)
(*                                                                         *)
(* Machines X and Y hold the same team. A (lead) and B live on X. X hands  *)
(* A's seat to B: the record gets generation+1, A leaves, B takes the seat *)
(* and the lead's place (op replace(A, B), kept in `pend` until the other  *)
(* machine's record contains it), and X publishes the whole record to Y.   *)
(* Meanwhile Y makes some other change (op `ext`, generation+1) and        *)
(* publishes it.                                                           *)
(*                                                                         *)
(* receive() in the fixed form:                                            *)
(*  - the origin of a locally written record is the machine's OWN key;     *)
(*  - an incoming record with a higher generation is taken;                *)
(*  - on equal generation: same content = echo, ignored (generation stays);*)
(*    different content: the record whose origin key is larger wins on     *)
(*    both machines; the loser takes it and RE-APPLIES its own unconfirmed *)
(*    ops on top, generation+1, and sends the result again;               *)
(*  - an op counts as confirmed (leaves `pend`) once a record that holds it*)
(*    is taken.  The model carries the confirmation as record content: `hand`*)
(*    and `ext` each stand for one op, so "the record holds the op" is the*)
(*    flag; the spec's `acked_by {machine: generation}` is not modelled.   *)
(* Re-applying never conflicts here (the two ops touch different members); *)
(* the conflict log of spec 3.4 is not modelled.                           *)
(* Y's machine key is larger than X's.                                     *)
(*                                                                         *)
(* Org: 1 = X, 2 = Y (the machine key of the origin, own key if local).    *)
(***************************************************************************)
EXTENDS Naturals

Machines == {"X", "Y"}
Key == [m \in Machines |-> IF m = "X" THEN 1 ELSE 2]
Other == [m \in Machines |-> IF m = "X" THEN "Y" ELSE "X"]

VARIABLES
  rec,       \* rec[m] = [gen, org, hand, ext, pend]
  msgs,      \* records in flight
  handDone,  \* X has made the handover
  yDone      \* Y has made its own change

vars == <<rec, msgs, handDone, yDone>>

Init ==
  /\ \E o \in {<<1, 1>>, <<2, 2>>, <<2, 1>>} :
       \* created on X (own key on X, Y got it from X); created on Y; or both have
       \* since received one change from the other
       rec = [m \in Machines |-> [gen |-> 1, org |-> IF m = "X" THEN o[1] ELSE o[2],
                                  hand |-> FALSE, ext |-> FALSE, pend |-> {}]]
  /\ msgs = {} /\ handDone = FALSE /\ yDone = FALSE

\* hand_over: _teams writes generation+1 with B in A's place (op replace(A, B),
\* pending); team_sync.publish sends it.
HandOver ==
  /\ ~handDone
  /\ LET r == [rec["X"] EXCEPT !.gen = @ + 1, !.org = Key["X"], !.hand = TRUE,
                                !.pend = @ \cup {"hand"}] IN
       /\ rec' = [rec EXCEPT !["X"] = r]
       /\ msgs' = msgs \cup {[from |-> "X", to |-> "Y", gen |-> r.gen, hand |-> r.hand, ext |-> r.ext]}
  /\ handDone' = TRUE /\ UNCHANGED yDone

\* Another change on Y (a member added, say), published the same way.
YChanges ==
  /\ ~yDone
  /\ LET r == [rec["Y"] EXCEPT !.gen = @ + 1, !.org = Key["Y"], !.ext = TRUE,
                                !.pend = @ \cup {"ext"}] IN
       /\ rec' = [rec EXCEPT !["Y"] = r]
       /\ msgs' = msgs \cup {[from |-> "Y", to |-> "X", gen |-> r.gen, hand |-> r.hand, ext |-> r.ext]}
  /\ yDone' = TRUE /\ UNCHANGED handDone

\* The ops of m that the incoming record x does not hold yet.
Unconfirmed(cur, x) ==
  {o \in cur.pend : (o = "hand" /\ ~x.hand) \/ (o = "ext" /\ ~x.ext)}

\* team_sync.receive.
Receives(m) ==
  /\ \E x \in msgs :
       /\ x.to = m
       /\ LET cur == rec[m]
              echo == x.gen = cur.gen /\ x.hand = cur.hand /\ x.ext = cur.ext
              newer == x.gen > cur.gen \/ (x.gen = cur.gen /\ Key[x.from] > cur.org)
              left == Unconfirmed(cur, x)
              taken == [gen |-> x.gen, org |-> Key[x.from], hand |-> x.hand, ext |-> x.ext, pend |-> {}]
              reapplied == [gen |-> x.gen + 1, org |-> Key[m],
                            hand |-> x.hand \/ "hand" \in left, ext |-> x.ext \/ "ext" \in left,
                            pend |-> left]
          IN IF echo \/ ~newer
               THEN /\ msgs' = msgs \ {x} /\ rec' = rec
               ELSE IF left = {}
                 THEN /\ msgs' = msgs \ {x} /\ rec' = [rec EXCEPT ![m] = taken]
                 ELSE /\ rec' = [rec EXCEPT ![m] = reapplied]
                      /\ msgs' = (msgs \ {x}) \cup
                            {[from |-> m, to |-> Other[m], gen |-> reapplied.gen,
                              hand |-> reapplied.hand, ext |-> reapplied.ext]}
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
