------------------------ MODULE XsmConcurrentHandover ------------------------
(***************************************************************************)
(* FIXED SEMANTICS (docs/plan/state-model-fixes/spec.md F5, D7).          *)
(* Same sessions and rules as deliverables/statechart-20261125/concurrent. *)
(*                                                                         *)
(* Sessions A, B, C. A holds the team place (member + lead's seat) and is  *)
(* the asker of one pending question (peer P, outside the set, has not     *)
(* answered yet).                                                          *)
(*                                                                         *)
(* A handover p = Src -> Dst follows the fixed hand_over:                  *)
(*   Check    takes the one machine-wide handover lock (waiting), then     *)
(*            re-judges _check under it: Src has not handed over yet, and  *)
(*            the target, followed to its successor, is not Src (no cycle).*)
(*            A refused plan ends in "refused" and writes nothing.         *)
(*   Begin    _begin: writes handovers/<Src>.json = {to: Dst}              *)
(*   Teams    re-reads teams_of(Src) under the lock; if Src is a member,   *)
(*            Src leaves, the EFFECTIVE target joins, and takes the lead's *)
(*            seat only if Src still holds it                              *)
(*   Questions a pending question whose sender is Src gets the effective   *)
(*            target as its sender; a question with a final answer stays   *)
(*   Finish   _finish: the lock is released                                *)
(* The effective target is follow(Dst): a target that already handed over  *)
(* is followed to its successor, so A->B after B->C places A's seat and    *)
(* question with C, and the chain A->B->C resolves to C either way round.  *)
(* The unread-DM step and the network publish are left out as before.      *)
(*                                                                         *)
(* A late answer from P is routed to handover.follow(A): the end of the    *)
(* chain successor_identity() walks (CHAIN = 8, seen set), or A itself if  *)
(* there is no record. The receiver stores it only if it is the question   *)
(* record's sender (questions.record_reply).                               *)
(*                                                                         *)
(* A handover may start only while at most MaxStarted handovers have       *)
(* started, so the state space stays small. P answers only once no         *)
(* handover is in flight and at least one record exists (the answer-       *)
(* during-handover paths belong to the first round).                       *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS Plans, MaxStarted

Sessions == {"A", "B", "C"}
AllPlans == {"AtoB", "AtoC", "BtoA", "BtoC"}
Src == [p \in AllPlans |-> CASE p = "AtoB" -> "A" [] p = "AtoC" -> "A"
                             [] p = "BtoA" -> "B" [] p = "BtoC" -> "B"]
Dst == [p \in AllPlans |-> CASE p = "AtoB" -> "B" [] p = "AtoC" -> "C"
                             [] p = "BtoA" -> "A" [] p = "BtoC" -> "C"]

VARIABLES
  pc,        \* per plan: "idle" | "refused" | "checked" | "begun" | "teams" | "questions" | "recorded"
  lock,      \* the machine-wide handover lock: "none" or the plan holding it
  rec,       \* handovers/<s>.json: the successor written for s, or "none"
  seats,     \* sessions that are members of the team
  lead,      \* the lead's seat holder
  qSender,   \* sender of the pending question record
  reply,     \* P's late answer: "unsent" | "recorded" | "refused"
  replyAt,   \* the session the answer was routed to
  wrote      \* how many times handovers/<s>.json was written

vars == <<pc, lock, rec, seats, lead, qSender, reply, replyAt, wrote>>

Started == {p \in Plans : pc[p] # "idle"}
InFlight == {p \in Plans : pc[p] \in {"checked", "begun", "teams", "questions"}}

\* handover.successor_identity, step for step (seen set, CHAIN = 8).
RECURSIVE Trace(_, _, _, _)
Trace(cur, seen, last, n) ==
  IF n = 0 THEN last
  ELSE IF cur \in seen THEN last
  ELSE IF rec[cur] = "none" THEN last
  ELSE Trace(rec[cur], seen \cup {cur}, rec[cur], n - 1)

Resolve(s) == Trace(s, {}, "none", 8)
Dest(s) == IF Resolve(s) = "none" THEN s ELSE Resolve(s)   \* follow()

\* The session a plan really hands over to: its target, followed to the end
\* of the chain.  Stable while the plan holds the lock.
Eff(p) == Dest(Dst[p])

Init ==
  /\ pc = [p \in Plans |-> "idle"] /\ lock = "none"
  /\ rec = [s \in Sessions |-> "none"]
  /\ seats = {"A"} /\ lead = "A" /\ qSender = "A"
  /\ reply = "unsent" /\ replyAt = "none"
  /\ wrote = [s \in Sessions |-> 0]

\* Waits for the lock, then re-judges under it.  A plan that fails the re-check
\* is refused with a next step to take ("A already handed over to B; hand B
\* over from B", "that would make a cycle"); it changes nothing.
Check(p) ==
  /\ pc[p] = "idle" /\ Cardinality(Started) < MaxStarted /\ lock = "none"
  /\ IF rec[Src[p]] = "none" /\ Eff(p) # Src[p]
       THEN /\ pc' = [pc EXCEPT ![p] = "checked"] /\ lock' = p
       ELSE /\ pc' = [pc EXCEPT ![p] = "refused"] /\ UNCHANGED lock
  /\ UNCHANGED <<rec, seats, lead, qSender, reply, replyAt, wrote>>

Begin(p) ==
  /\ pc[p] = "checked"
  /\ rec' = [rec EXCEPT ![Src[p]] = Dst[p]]
  /\ wrote' = [wrote EXCEPT ![Src[p]] = @ + 1]
  /\ pc' = [pc EXCEPT ![p] = "begun"]
  /\ UNCHANGED <<lock, seats, lead, qSender, reply, replyAt>>

Teams(p) ==
  /\ pc[p] = "begun"
  /\ IF Src[p] \in seats
       THEN /\ seats' = (seats \ {Src[p]}) \cup {Eff(p)}
            /\ lead' = IF lead = Src[p] THEN Eff(p) ELSE lead
       ELSE UNCHANGED <<seats, lead>>
  /\ pc' = [pc EXCEPT ![p] = "teams"]
  /\ UNCHANGED <<lock, rec, qSender, reply, replyAt, wrote>>

Questions(p) ==
  /\ pc[p] = "teams"
  /\ qSender' = IF qSender = Src[p] /\ reply # "recorded" THEN Eff(p) ELSE qSender
  /\ pc' = [pc EXCEPT ![p] = "questions"]
  /\ UNCHANGED <<lock, rec, seats, lead, reply, replyAt, wrote>>

Finish(p) ==
  /\ pc[p] = "questions"
  /\ pc' = [pc EXCEPT ![p] = "recorded"] /\ lock' = "none"
  /\ UNCHANGED <<rec, seats, lead, qSender, reply, replyAt, wrote>>

PeerAnswers ==
  /\ reply = "unsent" /\ InFlight = {} /\ \E s \in Sessions : rec[s] # "none"
  /\ replyAt' = Dest("A")
  /\ reply' = IF Dest("A") = qSender THEN "recorded" ELSE "refused"
  /\ UNCHANGED <<pc, lock, rec, seats, lead, qSender, wrote>>

Done ==
  /\ reply # "unsent" /\ InFlight = {}
  /\ UNCHANGED vars

Next ==
  \/ \E p \in Plans : Check(p) \/ Begin(p) \/ Teams(p) \/ Questions(p) \/ Finish(p)
  \/ PeerAnswers
  \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------------------- rules -----------------------------------
   The place/address/question rules are checked when no handover call is
   running (InFlight = {}): inside one call the pieces move one after the
   other, and even a single handover is out of step between its steps. *)

\* PROTOCOL 5.15 "old session ... must not have handed over already";
\* handover._check "this session has already handed over".
AtMostOneHandoverPerSession == \A s \in Sessions : wrote[s] <= 1

\* handover.py docstring: "the old conversation's address leads to the
\* successor"; follow() says "A handed its place over to A" otherwise.
AddressLeadsAway ==
  InFlight = {} => \A s \in Sessions : rec[s] # "none" => Resolve(s) # s

\* handover.py docstring: "The old session keeps running as an ordinary
\* session with no team place".
HandedOverHoldsNoPlace ==
  InFlight = {} =>
    \A s \in Sessions : rec[s] # "none" => (s \notin seats /\ lead # s)

\* handover.py docstring + letter: the team places and "DMs sent to A from now
\* on reach you" go to the same session.
AddressAndPlaceAgree ==
  (InFlight = {} /\ rec["A"] # "none") =>
    (Resolve("A") \in seats /\ lead = Resolve("A"))

\* handover.py docstring: "pending asks ... now belong to the successor, so
\* late answers are recorded for it". Late answers go to follow(A), and
\* questions.record_reply stores them only for the record's sender.
QuestionHolderIsAddressTarget ==
  (InFlight = {} /\ rec["A"] # "none" /\ reply # "recorded") =>
    qSender = Resolve("A")

\* Same promise, seen from the answer.
LateAnswerRecorded == reply # "unsent" => reply = "recorded"
=============================================================================
