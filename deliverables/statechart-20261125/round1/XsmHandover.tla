---------------------------- MODULE XsmHandover ----------------------------
(***************************************************************************)
(* xsm 0.6.1: message exchange, waiting, and handover of a session's place *)
(*                                                                         *)
(* Sessions: A (asks, holds a DM, may hand over), B (A's successor),       *)
(* P (the peer A asked).                                                   *)
(*                                                                         *)
(* DM m: sent by P to A before anything else; its canonical original sits  *)
(*   in A's handoffs folder (xsm/handoff.py).                              *)
(*   dmBad: A's receive gate will refuse it (scope, deny, check failure).  *)
(*   Two readers of A (the prompt hook and `xsm inbox`) claim it with a    *)
(*   120 s lease, show it (handoff-recorded), and ack it.                  *)
(* Question q: A asked P (xsm/questions.py) and waits (wait_for).          *)
(*   P's reply r goes to whatever follow(A) resolves at send time.         *)
(* Handover A -> B (xsm/handover.py hand_over), in code order:             *)
(*   _questions (sender of unanswered questions becomes B),                *)
(*   _unread (handoff.move_out: every non-acked original of A is closed    *)
(*            as acknowledged+moved_to and pasted into the letter),        *)
(*   write handovers/<A>.json (from now on follow(A) = B),                 *)
(*   letter shown at B's next prompt (handover.notice).                    *)
(* A is busy inside the handover tool call, so A's readers do not run      *)
(* between the first and the last step.                                    *)
(***************************************************************************)
EXTENDS Naturals

Readers == {"hook", "inbox"}

VARIABLES
  dmBad,      \* A's gate will refuse the DM
  dmState,    \* "pending" | "shown" (claimed + handoff-recorded) | "acked" | "moved"
  dmHolder,   \* "none" or the reader holding the claim
  dmLease,    \* "live" | "expired"
  dmHeld,     \* the gate held it (receipt held, original kept pending)
  dmSeen,     \* sessions whose model has read the DM body
  dmAcks,     \* number of successful consumption ACKs
  dmInLetter, \* the DM body is pasted into the handover letter
  wait,       \* A's ask wait: "waiting" | "answered" | "timedOut"
  qAsker,     \* the question record's sender: "A" | "B"
  qReplied,   \* the question record holds P's final reply
  r,          \* the reply: "unsent" | "atA" | "atB" | "usedA" | "usedB" | "inLetter"
  hStep,      \* handover: "none" | "questions" | "unread" | "recorded"
  letterRead  \* B has read the handover letter

vars == <<dmBad, dmState, dmHolder, dmLease, dmHeld, dmSeen, dmAcks, dmInLetter,
          wait, qAsker, qReplied, r, hStep, letterRead>>

Init ==
  /\ dmBad \in BOOLEAN
  /\ dmState = "pending" /\ dmHolder = "none" /\ dmLease = "live"
  /\ dmHeld = FALSE /\ dmSeen = {} /\ dmAcks = 0 /\ dmInLetter = FALSE
  /\ wait = "waiting" /\ qAsker = "A" /\ qReplied = FALSE /\ r = "unsent"
  /\ hStep = "none" /\ letterRead = FALSE

\* A runs its readers only outside the handover call.
AFree == hStep \in {"none", "recorded"}

qVars == <<wait, qAsker, qReplied, r>>
dmVars == <<dmBad, dmState, dmHolder, dmLease, dmHeld, dmSeen, dmAcks, dmInLetter>>
hVars == <<hStep, letterRead>>

(* ---------------- the DM at A ---------------- *)

\* receive.check blocks it: hold() keeps a copy, the original stays pending,
\* the ledger receipt says held, so pending_ids/inbox skip it.
GateHolds ==
  /\ AFree /\ dmBad /\ ~dmHeld /\ dmState = "pending"
  /\ dmHeld' = TRUE
  /\ UNCHANGED <<dmBad, dmState, dmHolder, dmLease, dmSeen, dmAcks, dmInLetter>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.claim + handoff.handoff, then the body goes to A's model.
Take(c) ==
  /\ AFree /\ ~dmBad /\ dmState = "pending"
  /\ dmState' = "shown" /\ dmHolder' = c /\ dmLease' = "live"
  /\ dmSeen' = dmSeen \cup {"A"}
  /\ UNCHANGED <<dmBad, dmHeld, dmAcks, dmInLetter>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.ack: only the token holder, only inside the lease.
Ack(c) ==
  /\ AFree /\ dmState = "shown" /\ dmHolder = c /\ dmLease = "live"
  /\ dmState' = "acked" /\ dmHolder' = "none" /\ dmAcks' = dmAcks + 1
  /\ UNCHANGED <<dmBad, dmLease, dmHeld, dmSeen, dmInLetter>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.release after a cancel or output error.
Release(c) ==
  /\ AFree /\ dmState = "shown" /\ dmHolder = c /\ dmLease = "live"
  /\ dmState' = "pending" /\ dmHolder' = "none"
  /\ UNCHANGED <<dmBad, dmLease, dmHeld, dmSeen, dmAcks, dmInLetter>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

LeaseExpires ==
  /\ dmState = "shown" /\ dmLease = "live"
  /\ dmLease' = "expired"
  /\ UNCHANGED <<dmBad, dmState, dmHolder, dmHeld, dmSeen, dmAcks, dmInLetter>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

\* handoff.recover: lease expired (or owner proven dead) -> pending again.
Recover ==
  /\ AFree /\ dmState = "shown" /\ dmLease = "expired"
  /\ dmState' = "pending" /\ dmHolder' = "none" /\ dmLease' = "live"
  /\ UNCHANGED <<dmBad, dmHeld, dmSeen, dmAcks, dmInLetter>>
  /\ UNCHANGED qVars /\ UNCHANGED hVars

(* ---------------- the question and its reply ---------------- *)

\* P answers with outcome (final). send.py resolves A through handover.follow.
PReplies ==
  /\ r = "unsent"
  /\ r' = IF hStep = "recorded" THEN "atB" ELSE "atA"
  /\ UNCHANGED <<wait, qAsker, qReplied>> /\ UNCHANGED dmVars /\ UNCHANGED hVars

\* receive.poll_replies(X): reads X's own folder; record_reply needs
\* receiver == the question record's sender.
Poll(x) ==
  /\ (x = "A" => AFree)
  /\ r = IF x = "A" THEN "atA" ELSE "atB"
  /\ qAsker = x /\ ~qReplied
  /\ qReplied' = TRUE
  /\ UNCHANGED <<wait, qAsker, r>> /\ UNCHANGED dmVars /\ UNCHANGED hVars

\* The hook (or inbox) takes the reply: claim, _index_reply, show, ack.
\* Indexing fails silently when the record's sender is someone else.
TakeReply(x) ==
  /\ (x = "A" => AFree)
  /\ r = IF x = "A" THEN "atA" ELSE "atB"
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

\* User approves; _check passes; _questions moves questions without a final reply.
HandOverQuestions ==
  /\ hStep = "none" /\ wait # "waiting"
  /\ hStep' = "questions"
  /\ qAsker' = IF qReplied THEN "A" ELSE "B"
  /\ UNCHANGED <<wait, qReplied, r, letterRead>> /\ UNCHANGED dmVars

\* _unread: handoff.move_out closes every non-acked original of A, whatever
\* its gate verdict, and its content goes verbatim into the letter.
HandOverUnread ==
  /\ hStep = "questions"
  /\ hStep' = "unread"
  /\ IF dmState \in {"pending", "shown"}
       THEN /\ dmState' = "moved" /\ dmHolder' = "none" /\ dmInLetter' = TRUE
       ELSE UNCHANGED <<dmState, dmHolder, dmInLetter>>
  /\ r' = IF r = "atA" THEN "inLetter" ELSE r
  /\ UNCHANGED <<dmBad, dmLease, dmHeld, dmSeen, dmAcks>>
  /\ UNCHANGED <<wait, qAsker, qReplied, letterRead>>

HandOverRecorded ==
  /\ hStep = "unread"
  /\ hStep' = "recorded"
  /\ UNCHANGED letterRead /\ UNCHANGED dmVars /\ UNCHANGED qVars

\* handover.notice: additionalContext on B's next prompt, no gate.
BReadsLetter ==
  /\ hStep = "recorded" /\ ~letterRead
  /\ letterRead' = TRUE
  /\ dmSeen' = IF dmInLetter THEN dmSeen \cup {"B"} ELSE dmSeen
  /\ UNCHANGED hStep
  /\ UNCHANGED <<dmBad, dmState, dmHolder, dmLease, dmHeld, dmAcks, dmInLetter>>
  /\ UNCHANGED qVars

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
  \/ HandOverQuestions \/ HandOverUnread \/ HandOverRecorded \/ BReadsLetter
  \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------- rules ---------------- *)

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
