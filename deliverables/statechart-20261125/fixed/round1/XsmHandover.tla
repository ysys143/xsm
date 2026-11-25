---------------------------- MODULE XsmHandover ----------------------------
(***************************************************************************)
(* FIXED SEMANTICS (docs/plan/state-model-fixes/spec.md F1, F2, D2, D6).   *)
(* Same sessions, same rules as deliverables/statechart-20261125/round1;   *)
(* only the handover actions differ.                                       *)
(*                                                                         *)
(* Sessions: A (asks, holds a DM, may hand over), B (A's successor),       *)
(* P (the peer A asked).                                                   *)
(*                                                                         *)
(* Handover A -> B in the fixed order (hand_over, spec 3.2), with ONE      *)
(* change of order, found by this model (see README, finding 1):           *)
(*   _questions  sender of unanswered questions becomes B. Runs BEFORE the *)
(*            record: spec 3.2 writes _begin first, and then a reply that  *)
(*            P sends after the record goes to B's folder while the        *)
(*            question's sender is still A; B's reader takes it and        *)
(*            record_reply (receiver == sender) silently does not index it.*)
(*   _begin   writes handovers/<A>.json (state "moving"): follow(A) = B    *)
(*            from this step on, so P's later reply goes to B (F2b).       *)
(*   hand_to  every non-acked original of A is COPIED to B (state pending, *)
(*            handover_history) and A's copy is closed as moved_to. This   *)
(*            includes P's unanswered reply sitting in A's folder (F2a),   *)
(*            and a DM A's gate held: it stays held at B (D2, held.rebind).*)
(*   letter   carries counts and ids only, never a message body (D6).      *)
(* A does not consume anything while the handover call runs (AFree).       *)
(* B's gate judges handed-over originals (spec 3.3): deny list blocks,     *)
(* an original A already held stays held, everything else is passed.       *)
(*                                                                         *)
(* Model-level choices:                                                    *)
(*  - dmDeny: the DM's sender is on the deny list (implies dmBad). A DM    *)
(*    that is only out of scope (dmBad, not dmDeny) passes at B (D8). The  *)
(*    release of a scope-held DM when scope appears at B is not modelled.  *)
(*  - dmAt: where the DM original lives ("A" before hand_to, "B" after).   *)
(*  - the letter holds no body, so there is no dmInLetter and r never      *)
(*    becomes "inLetter"; the rule text is kept verbatim.                  *)
(***************************************************************************)
EXTENDS Naturals

Readers == {"hook", "inbox"}

VARIABLES
  dmBad,      \* A's gate will refuse the DM
  dmDeny,     \* the sender is on the deny list (dmDeny => dmBad)
  dmAt,       \* "A" | "B": where the DM original lives
  dmState,    \* "pending" | "shown" (claimed + handoff-recorded) | "acked"
  dmHolder,   \* "none" or the reader holding the claim
  dmLease,    \* "live" | "expired"
  dmHeld,     \* the gate held it (receipt held, original kept pending)
  dmSeen,     \* sessions whose model has read the DM body
  dmAcks,     \* number of successful consumption ACKs
  wait,       \* A's ask wait: "waiting" | "answered" | "timedOut"
  qAsker,     \* the question record's sender: "A" | "B"
  qReplied,   \* the question record holds P's final reply
  r,          \* the reply: "unsent" | "atA" | "atB" | "usedA" | "usedB" | "inLetter"
  hStep,      \* handover: "none" | "questions" | "begun" | "originals" | "recorded"
  letterRead  \* B has read the handover letter

vars == <<dmBad, dmDeny, dmAt, dmState, dmHolder, dmLease, dmHeld, dmSeen, dmAcks,
          wait, qAsker, qReplied, r, hStep, letterRead>>

Init ==
  /\ dmBad \in BOOLEAN /\ dmDeny \in BOOLEAN /\ (dmDeny => dmBad)
  /\ dmAt = "A"
  /\ dmState = "pending" /\ dmHolder = "none" /\ dmLease = "live"
  /\ dmHeld = FALSE /\ dmSeen = {} /\ dmAcks = 0
  /\ wait = "waiting" /\ qAsker = "A" /\ qReplied = FALSE /\ r = "unsent"
  /\ hStep = "none" /\ letterRead = FALSE

\* A runs its readers only outside the handover call.  B's readers always run.
Free == dmAt = "B" \/ hStep \in {"none", "recorded"}

\* A reply sits in the folder of the session it was sent to.
Reader(x) == IF x = "A" THEN "atA" ELSE "atB"

qVars == <<wait, qAsker, qReplied, r>>
dmVars == <<dmBad, dmDeny, dmAt, dmState, dmHolder, dmLease, dmHeld, dmSeen, dmAcks>>
hVars == <<hStep, letterRead>>

(* ---------------- the DM at its current owner ---------------- *)

\* The gate of the session that holds the original: A's gate on dmBad,
\* B's gate only on the deny list.  hold() keeps a copy, the original stays
\* pending, the ledger receipt says held, so pending_ids/inbox skip it.
GateHolds ==
  /\ Free /\ ~dmHeld /\ dmState = "pending"
  /\ IF dmAt = "A" THEN dmBad ELSE dmDeny
  /\ dmHeld' = TRUE
  /\ UNCHANGED <<dmBad, dmDeny, dmAt, dmState, dmHolder, dmLease, dmSeen, dmAcks>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.claim + handoff.handoff, then the body goes to the owner's model.
Take(c) ==
  /\ Free /\ ~dmHeld /\ dmState = "pending"
  /\ IF dmAt = "A" THEN ~dmBad ELSE ~dmDeny
  /\ dmState' = "shown" /\ dmHolder' = c /\ dmLease' = "live"
  /\ dmSeen' = dmSeen \cup {dmAt}
  /\ UNCHANGED <<dmBad, dmDeny, dmAt, dmHeld, dmAcks>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.ack: only the token holder, only inside the lease.
Ack(c) ==
  /\ Free /\ dmState = "shown" /\ dmHolder = c /\ dmLease = "live"
  /\ dmState' = "acked" /\ dmHolder' = "none" /\ dmAcks' = dmAcks + 1
  /\ UNCHANGED <<dmBad, dmDeny, dmAt, dmLease, dmHeld, dmSeen>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.release after a cancel or output error.
Release(c) ==
  /\ Free /\ dmState = "shown" /\ dmHolder = c /\ dmLease = "live"
  /\ dmState' = "pending" /\ dmHolder' = "none"
  /\ UNCHANGED <<dmBad, dmDeny, dmAt, dmLease, dmHeld, dmSeen, dmAcks>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

LeaseExpires ==
  /\ dmState = "shown" /\ dmLease = "live"
  /\ dmLease' = "expired"
  /\ UNCHANGED <<dmBad, dmDeny, dmAt, dmState, dmHolder, dmHeld, dmSeen, dmAcks>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.recover: lease expired (or owner proven dead) -> pending again.
Recover ==
  /\ Free /\ dmState = "shown" /\ dmLease = "expired"
  /\ dmState' = "pending" /\ dmHolder' = "none" /\ dmLease' = "live"
  /\ UNCHANGED <<dmBad, dmDeny, dmAt, dmHeld, dmSeen, dmAcks>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

(* ---------------- the question and its reply ---------------- *)

\* P answers with outcome (final). send.py resolves A through handover.follow,
\* which answers B as soon as the handover record exists (_begin).
PReplies ==
  /\ r = "unsent"
  /\ r' = IF hStep \in {"begun", "originals", "recorded"} THEN "atB" ELSE "atA"
  /\ UNCHANGED <<wait, qAsker, qReplied>> /\ UNCHANGED dmVars /\ UNCHANGED hVars

\* receive.poll_replies(X): reads X's own folder; record_reply needs
\* receiver == the question record's sender.
Poll(x) ==
  /\ (x = "A" => Free)
  /\ r = Reader(x)
  /\ qAsker = x /\ ~qReplied
  /\ qReplied' = TRUE
  /\ UNCHANGED <<wait, qAsker, r>> /\ UNCHANGED dmVars /\ UNCHANGED hVars

\* The hook (or inbox) takes the reply: claim, _index_reply, show, ack.
TakeReply(x) ==
  /\ (x = "A" => Free)
  /\ r = Reader(x)
  /\ r' = IF x = "A" THEN "usedA" ELSE "usedB"
  /\ qReplied' = (qReplied \/ qAsker = x)
  /\ UNCHANGED <<wait, qAsker>> /\ UNCHANGED dmVars /\ UNCHANGED hVars

WaitAnswered ==
  /\ wait = "waiting" /\ qReplied
  /\ wait' = "answered"
  /\ UNCHANGED <<qAsker, qReplied, r>> /\ UNCHANGED dmVars /\ UNCHANGED hVars

WaitTimesOut ==
  /\ wait = "waiting"
  /\ wait' = "timedOut"
  /\ UNCHANGED <<qAsker, qReplied, r>> /\ UNCHANGED dmVars /\ UNCHANGED hVars

(* ---------------- the handover ---------------- *)

\* User approves; _check passes; _questions: unanswered questions get sender B;
\* a question with a final reply stays A's.  This happens BEFORE the record is
\* written (see the header): a reply that reaches B must find B already the
\* question's sender.  Until the record exists a reply still goes to A's folder,
\* where hand_to will move it.
HandOverQuestions ==
  /\ hStep = "none" /\ wait # "waiting"
  /\ hStep' = "questions"
  /\ qAsker' = IF qReplied THEN "A" ELSE "B"
  /\ UNCHANGED <<wait, qReplied, r, letterRead>> /\ UNCHANGED dmVars

\* _begin: handovers/<A>.json (state "moving"): follow(A) = B from here on.
HandOverBegin ==
  /\ hStep = "questions"
  /\ hStep' = "begun"
  /\ UNCHANGED <<wait, qAsker, qReplied, r, letterRead>> /\ UNCHANGED dmVars

\* hand_to + held.rebind: every non-acked original of A moves to B (a shown
\* one is released), a held DM stays held, and a reply still sitting in A's
\* folder moves with them.  The letter gets counts and ids only.
HandOverOriginals ==
  /\ hStep = "begun"
  /\ hStep' = "originals"
  /\ IF dmState \in {"pending", "shown"}
       THEN /\ dmAt' = "B" /\ dmState' = "pending" /\ dmHolder' = "none" /\ dmLease' = "live"
       ELSE UNCHANGED <<dmAt, dmState, dmHolder, dmLease>>
  /\ r' = IF r = "atA" THEN "atB" ELSE r
  /\ UNCHANGED <<dmBad, dmDeny, dmHeld, dmSeen, dmAcks>>
  /\ UNCHANGED <<wait, qAsker, qReplied, letterRead>>

\* _finish: state "done", letter written.
HandOverRecorded ==
  /\ hStep = "originals"
  /\ hStep' = "recorded"
  /\ UNCHANGED letterRead /\ UNCHANGED dmVars /\ UNCHANGED qVars

\* handover.notice: additionalContext on B's next prompt, no gate.  The
\* letter has counts and ids, so reading it shows B no message body.
BReadsLetter ==
  /\ hStep = "recorded" /\ ~letterRead
  /\ letterRead' = TRUE
  /\ UNCHANGED hStep /\ UNCHANGED dmVars /\ UNCHANGED qVars

(* ---------------- end states ---------------- *)

Done ==
  /\ hStep = "recorded" /\ letterRead /\ wait # "waiting"
  /\ r \in {"usedA", "usedB", "inLetter"}
  /\ (dmState \in {"acked", "moved"} \/ dmHeld)
  /\ UNCHANGED vars

Next ==
  \/ GateHolds \/ LeaseExpires \/ Recover
  \/ \E c \in Readers : Take(c) \/ Ack(c) \/ Release(c)
  \/ PReplies \/ WaitAnswered \/ WaitTimesOut
  \/ \E x \in {"A", "B"} : Poll(x) \/ TakeReply(x)
  \/ HandOverBegin \/ HandOverQuestions \/ HandOverOriginals \/ HandOverRecorded \/ BReadsLetter
  \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------- rules (verbatim from round1) ---------------- *)

\* Without the person's yes (`xsm held deliver`), a held DM reaches no model.
HeldStaysHeld == dmHeld => dmSeen = {}

\* A DM is consumed at most once.
AckedOnce == dmAcks <= 1

\* Once P's answer has been delivered, the question shows it as answered.
AnswerRecorded == r \in {"usedA", "usedB", "inLetter"} => qReplied

\* A wait never reports an answer the record does not hold.
WaitHonest == wait = "answered" => qReplied

\* Only the current claim holder, inside its lease, holds the DM.
OneHolder == (dmState = "shown") <=> (dmHolder \in Readers)
=============================================================================
