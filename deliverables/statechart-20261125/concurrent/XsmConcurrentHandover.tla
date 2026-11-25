------------------------ MODULE XsmConcurrentHandover ------------------------
(***************************************************************************)
(* xsm 0.6.1 (HEAD 2a858d3): two handovers running at the same time.       *)
(*                                                                         *)
(* Sessions A, B, C. A holds the team place (member + lead's seat) and is  *)
(* the asker of one pending question (peer P, outside the set, has not     *)
(* answered yet).                                                          *)
(*                                                                         *)
(* A handover p = Src -> Dst follows xsm/handover.py hand_over, split in   *)
(* the steps that other handovers can interleave with. There is no lock    *)
(* across them (only per-team and per-question file locks inside steps):   *)
(*   Check    _check(me, target): load(target) and load(me) are both empty *)
(*   Teams    _boards/_teams: re-reads teams_of(me); if me is a member,    *)
(*            me leaves, target joins, and target takes the lead's seat    *)
(*            only if me still holds it                                    *)
(*   Questions _questions/_groups: a pending question whose sender is me   *)
(*            gets target as its sender; a question with a final answer    *)
(*            stays                                                        *)
(*   Record   write handovers/<me>.json = {to: target}, overwriting        *)
(* The unread-DM step (_unread) and the network publish are left out: they *)
(* do not touch these variables.                                           *)
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
  pc,        \* per plan: "idle" | "checked" | "teams" | "questions" | "recorded"
  rec,       \* handovers/<s>.json: the successor written for s, or "none"
  seats,     \* sessions that are members of the team
  lead,      \* the lead's seat holder
  qSender,   \* sender of the pending question record
  reply,     \* P's late answer: "unsent" | "recorded" | "refused"
  replyAt,   \* the session the answer was routed to
  wrote      \* how many times handovers/<s>.json was written

vars == <<pc, rec, seats, lead, qSender, reply, replyAt, wrote>>

Started == {p \in Plans : pc[p] # "idle"}
InFlight == {p \in Plans : pc[p] \in {"checked", "teams", "questions"}}

\* handover.successor_identity, step for step (seen set, CHAIN = 8).
RECURSIVE Trace(_, _, _, _)
Trace(cur, seen, last, n) ==
  IF n = 0 THEN last
  ELSE IF cur \in seen THEN last
  ELSE IF rec[cur] = "none" THEN last
  ELSE Trace(rec[cur], seen \cup {cur}, rec[cur], n - 1)

Resolve(s) == Trace(s, {}, "none", 8)
Dest(s) == IF Resolve(s) = "none" THEN s ELSE Resolve(s)   \* follow()

Init ==
  /\ pc = [p \in Plans |-> "idle"]
  /\ rec = [s \in Sessions |-> "none"]
  /\ seats = {"A"} /\ lead = "A" /\ qSender = "A"
  /\ reply = "unsent" /\ replyAt = "none"
  /\ wrote = [s \in Sessions |-> 0]

Check(p) ==
  /\ pc[p] = "idle" /\ Cardinality(Started) < MaxStarted
  /\ rec[Src[p]] = "none" /\ rec[Dst[p]] = "none"
  /\ pc' = [pc EXCEPT ![p] = "checked"]
  /\ UNCHANGED <<rec, seats, lead, qSender, reply, replyAt, wrote>>

Teams(p) ==
  /\ pc[p] = "checked"
  /\ IF Src[p] \in seats
       THEN /\ seats' = (seats \ {Src[p]}) \cup {Dst[p]}
            /\ lead' = IF lead = Src[p] THEN Dst[p] ELSE lead
       ELSE UNCHANGED <<seats, lead>>
  /\ pc' = [pc EXCEPT ![p] = "teams"]
  /\ UNCHANGED <<rec, qSender, reply, replyAt, wrote>>

Questions(p) ==
  /\ pc[p] = "teams"
  /\ qSender' = IF qSender = Src[p] /\ reply # "recorded" THEN Dst[p] ELSE qSender
  /\ pc' = [pc EXCEPT ![p] = "questions"]
  /\ UNCHANGED <<rec, seats, lead, reply, replyAt, wrote>>

Record(p) ==
  /\ pc[p] = "questions"
  /\ rec' = [rec EXCEPT ![Src[p]] = Dst[p]]
  /\ wrote' = [wrote EXCEPT ![Src[p]] = @ + 1]
  /\ pc' = [pc EXCEPT ![p] = "recorded"]
  /\ UNCHANGED <<seats, lead, qSender, reply, replyAt>>

PeerAnswers ==
  /\ reply = "unsent" /\ InFlight = {} /\ \E s \in Sessions : rec[s] # "none"
  /\ replyAt' = Dest("A")
  /\ reply' = IF Dest("A") = qSender THEN "recorded" ELSE "refused"
  /\ UNCHANGED <<pc, rec, seats, lead, qSender, wrote>>

Done ==
  /\ reply # "unsent" /\ InFlight = {}
  /\ UNCHANGED vars

Next ==
  \/ \E p \in Plans : Check(p) \/ Teams(p) \/ Questions(p) \/ Record(p)
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
