---------------------------- MODULE XsmScopeGroups ----------------------------
(***************************************************************************)
(* xsm 0.6.1 (HEAD 2a858d3): a question group of two questions to P, A     *)
(* hands its place over to B, P answers late.                              *)
(*                                                                         *)
(* A = the asker, B = A's successor, P = the peer asked (both children).   *)
(*                                                                         *)
(* Code paths mirrored:                                                    *)
(*  question_groups.ask_many: group record sender = A, children G-1, G-2   *)
(*     are ordinary questions (questions.ask), sender A.                   *)
(*  handover._questions: every child with NO outcome-bearing reply gets    *)
(*     sender B; a child with a final reply stays A's ("it stays the       *)
(*     asker's").                                                          *)
(*  handover._groups: the group record's sender becomes B, always,         *)
(*     whatever the children hold.                                         *)
(*  question_groups.status(B, group): for each child it calls              *)
(*     questions.status(B, child); that returns "refused" (request belongs *)
(*     to another conversation) when the child's sender is still A.        *)
(*  send.send(P -> A's address): resolve, handover.follow gives B, then    *)
(*     config.scope_for(P, B); no scope -> "out of scope", reply not sent. *)
(*                                                                         *)
(* `basis` is what gave P and A their scope. Whether the same basis still  *)
(* gives P and B a scope was measured with config.scope_for before the     *)
(* model was written (probe_test.py):                                      *)
(*   team            carries: handover._teams puts B into A's teams        *)
(*   repo_B_same     carries: B is in the same repository / directory      *)
(*   repo_B_other    does not: B is in another folder                      *)
(*   link_B_covered  carries: B sits inside a linked / joined folder       *)
(*   link_B_outside  does not                                              *)
(*   reach_by_A      does not: reach_holds() is bound to A's session id    *)
(*   worker_of_A     does not: matched on the worker/parent refs of A      *)
(*                                                                         *)
(* Out of this lane (found in round 1, not modelled): an answer in flight  *)
(* during the handover call, and an answer already stored at A and not     *)
(* yet polled.  Here a reply that arrives is recorded at once.             *)
(***************************************************************************)
EXTENDS Naturals

Bases == {"team", "repo_B_same", "repo_B_other", "link_B_covered",
          "link_B_outside", "reach_by_A", "worker_of_A"}
CarriesOver(b) == b \in {"team", "repo_B_same", "link_B_covered"}

Kids == {1, 2}

VARIABLES
  basis,       \* what gave P and A their scope
  handed,      \* A has handed over to B
  kid,         \* kid[i]: "open" | "final"  (the child question's reply record)
  kidOwner,    \* kidOwner[i]: "A" | "B"    (the child record's sender)
  groupOwner,  \* the group record's sender
  refused      \* children whose late answer P's send refused (out of scope)

vars == <<basis, handed, kid, kidOwner, groupOwner, refused>>

Holder == IF handed THEN "B" ELSE "A"

Init ==
  /\ basis \in Bases
  /\ handed = FALSE
  /\ kid = [i \in Kids |-> "open"]
  /\ kidOwner = [i \in Kids |-> "A"]
  /\ groupOwner = "A"
  /\ refused = {}

(* P answers child i for good (outcome set). Before the handover the reply  *)
(* is recorded for A; after it, it is resolved to B and needs scope(P, B).  *)
PAnswers(i) ==
  /\ kid[i] = "open" /\ i \notin refused
  /\ \/ /\ ~handed
        /\ kid' = [kid EXCEPT ![i] = "final"]
        /\ UNCHANGED refused
     \/ /\ handed /\ CarriesOver(basis)
        /\ kidOwner[i] = "B"
        /\ kid' = [kid EXCEPT ![i] = "final"]
        /\ UNCHANGED refused
     \/ /\ handed /\ ~CarriesOver(basis)
        /\ refused' = refused \cup {i}
        /\ UNCHANGED kid
  /\ UNCHANGED <<basis, handed, kidOwner, groupOwner>>

(* handover._questions then ._groups, as one step (answers in flight inside *)
(* the call are round 1's subject).                                          *)
HandOver ==
  /\ ~handed
  /\ handed' = TRUE
  /\ kidOwner' = [i \in Kids |-> IF kid[i] = "final" THEN kidOwner[i] ELSE "B"]
  /\ groupOwner' = "B"
  /\ UNCHANGED <<basis, kid, refused>>

Done ==
  /\ handed /\ \A i \in Kids : kid[i] = "final" \/ i \in refused
  /\ UNCHANGED vars

Next == \/ \E i \in Kids : PAnswers(i)
        \/ HandOver
        \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------- what the holder's `question-status <group>` shows ----- *)
(* Mirrors question_groups.status line by line.                              *)

RowView(i) == IF kidOwner[i] # Holder THEN "refused"
              ELSE IF kid[i] = "final" THEN "final" ELSE "pending"

AnsweredView == {i \in Kids : RowView(i) = "final"}
EndedView    == {i \in Kids : RowView(i) \in {"final", "refused"}}
OpenView     == Kids \ EndedView            \* waiting_on

Overall(answered, ended) ==
  IF answered = Kids THEN "final"
  ELSE IF answered # {} THEN (IF Kids \ ended # {} THEN "reply_received" ELSE "replied")
  ELSE IF ended = Kids THEN "refused"
  ELSE "pending"

ViewStatus == IF groupOwner # Holder THEN "refused" ELSE Overall(AnsweredView, EndedView)

TrueAnswered == {i \in Kids : kid[i] = "final"}
TrueStatus == Overall(TrueAnswered, TrueAnswered)

(* ------------------------------ rules --------------------------------- *)

\* docs/xsm/PROTOCOL.md 5.12: `question-status <group>` returns "각자의 답"
\* (each recipient's answer); question_groups.py header: "`question-status
\* <group>` reads them all". 5.15: the group's sender is replaced so the
\* holder reads it.
GroupShowsEveryAnswer == groupOwner # Holder \/ AnsweredView = TrueAnswered

\* PROTOCOL 5.12: the group status is one of pending, reply_received,
\* replied, final, refused; `final` when every recipient's answer is final
\* (question_groups.status line `all(r.get("final") ...)`).
GroupStatusTruthful == ViewStatus = TrueStatus

\* PROTOCOL 5.12: "대기 중인 수신자" (waiting_on) are the recipients that have
\* not answered.
WaitingOnHonest == OpenView = Kids \ TrueAnswered

\* PROTOCOL 5.15: "최종 답이 없는 질문과 질문 묶음의 발신자 교체"; handover.py
\* docstring: "the questions it asked that have no final answer now belong to
\* the successor, so late answers are recorded for it".
OpenQuestionsBelongToHolder ==
  \A i \in Kids : (kid[i] = "open" /\ handed) => kidOwner[i] = "B"

\* handover.py docstring: "an answer to a question it was asked ... go[es] to
\* the successor (follow())"; the letter: "pending question[s] it asked (late
\* answers come to you ...)"; PROTOCOL 5.15; TESTPLAN 14-11: "A가 B에게
\* 물었던 질문의 늦은 답이 D에게 간다".
LateAnswerReachesSuccessor == refused = {}

TypeOK ==
  /\ basis \in Bases /\ handed \in BOOLEAN
  /\ kid \in [Kids -> {"open", "final"}] /\ kidOwner \in [Kids -> {"A", "B"}]
  /\ groupOwner \in {"A", "B"} /\ refused \subseteq Kids
=============================================================================
