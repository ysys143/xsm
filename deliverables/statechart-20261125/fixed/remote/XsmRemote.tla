------------------------------ MODULE XsmRemote ------------------------------
(***************************************************************************)
(* FIXED SEMANTICS (docs/plan/state-model-fixes/spec.md F9, F10, D5, S12).*)
(* An answer to a question that another machine asked of A, after A      *)
(* handed its place over (handover.py, ADR-0025 D27).                      *)
(*                                                                         *)
(* Machine M1 holds A, B, C.  Machine R (the asker) holds the question.    *)
(* A hands over to B; later B may hand over to C.                          *)
(* M1 tells machines about a hop by "testimony" {old, new}                 *)
(*   (handover._publish -> network.publish_handover): to the remote        *)
(*   members of A's teams (`member`) and to the machines whose message to  *)
(*   `old` is kept at `old` (Gateway.origins_for: inbound record local ==  *)
(*   old).  There is still no retry; the push is unchanged.                *)
(* R accepts an answer if its endpoint succeeds the endpoint the question  *)
(*   was sent to (handover.endpoint_succeeds): B needs hop 1 A->B, C needs *)
(*   hop 1 and hop 2 B->C, read from the testimony R stored.               *)
(*                                                                         *)
(* What is new:                                                            *)
(*  - F10: hand_to copies every unacknowledged original to the successor,  *)
(*    so the successor can verify the original (`origAt` follows the       *)
(*    holder) and Unreplyable is no longer reachable.                      *)
(*  - F9 (D5): when R's reverse check fails and the sender's machine is    *)
(*    the machine the question was sent to, Gateway.receive PULLS the      *)
(*    whole succession chain from that machine (`succession {old, new}`)   *)
(*    and stores it as testimony.  If the machine cannot be reached        *)
(*    (Lossy) the answer is recorded with the mark "unconfirmed" (P*,      *)
(*    spec 12); a later testimony or a later successful pull makes it      *)
(*    "recorded" (confirmed).  A reply is therefore never refused for      *)
(*    good; the Resend action is gone because nothing is refused.          *)
(*  - X, the stranger, is a session of ANOTHER machine: it is never pulled *)
(*    for and never recorded.  A same-machine stranger being recorded as   *)
(*    "unconfirmed" is the trade-off of spec 12 and is not in this model.  *)
(* Messages in flight are unordered and may be lost.                       *)
(***************************************************************************)
EXTENDS Naturals

Answerers == {"B", "C", "X"}      \* X: a session that is neither A nor its successors

CONSTANTS
  WithStranger,   \* TRUE: also let a session outside A's chain reply (multiplies the states)
  Lossy,          \* TRUE: a testimony message may be lost on the way (machine offline, no retry)
  MaxHops,        \* 1: only A -> B; 2: B may hand over to C as well
  MemberChoices,  \* the values `member` may start with
  AskedChoices,   \* the values `asked` may start with (TRUE: asked before the handover)
  QReadChoices    \* the values `qRead` may start with

VARIABLES
  holder,     \* who holds A's place on M1: "A" | "B" | "C"
  qRead,      \* the session the question was kept for reads it before it hands over
  member,     \* R is a remote member of A's team (told of every hop)
  asked,      \* R's question to A exists
  recLocal,   \* the session M1 kept R's message for when it arrived: "-" | "A" | "B" | "C"
  origAt,     \* the session whose handoffs folder holds the question's original: "-" | "A" | "B" | "C"
  t1, t2,     \* R's view of hop 1 (A->B) and hop 2 (B->C)
  ans         \* per answerer: "none" | "inflight" | "refused" | "unconfirmed" | "recorded"

vars == <<holder, qRead, member, asked, recLocal, origAt, t1, t2, ans>>

Init ==
  /\ holder = "A"
  /\ qRead \in QReadChoices
  /\ member \in MemberChoices
  /\ asked \in AskedChoices
  /\ recLocal = IF asked THEN "A" ELSE "-"
  /\ origAt = IF asked THEN "A" ELSE "-"
  /\ t1 = "none" /\ t2 = "none"
  /\ ans = [s \in Answerers |-> "none"]

\* hand_to (hand_over -> originals) COPIES every message the handing session has not
\* acknowledged to the successor, so Gateway._ingress finds the original there and
\* Gateway.prepare lets the successor reply.  The original follows the holder
\* (origAt); a reply is refused only when the original is somewhere else.
Unreplyable ==
  /\ asked /\ ~qRead
  /\ origAt /= holder

(* ---------------- what R accepts ---------------- *)
\* handover.endpoint_succeeds on R: stored testimony followed hop by hop.
Accepts(s) ==
  CASE s = "B" -> t1 = "stored"
    [] s = "C" -> t1 = "stored" /\ t2 = "stored"
    [] OTHER -> FALSE

(* ---------------- M1: handovers and testimony ---------------- *)
\* hand_over writes the handover, then _publish runs in the same call: the service sends the
\* testimony to the remote members of A's teams (`member`) and to the machines whose message
\* is kept at the old session (Gateway.origins_for: inbound record local == old).
\* A message that arrives after the record is written is kept for the successor, so
\* the window between the two steps changes nothing.
HandOver1 ==
  /\ holder = "A"
  /\ holder' = "B"
  /\ origAt' = IF origAt = "A" THEN "B" ELSE origAt
  /\ t1' = IF member \/ recLocal = "A" THEN "inflight" ELSE "none"
  /\ UNCHANGED <<qRead, member, asked, recLocal, t2, ans>>

\* the same for B -> C: recipients are members and machines whose message is kept at B.
HandOver2 ==
  /\ MaxHops >= 2 /\ holder = "B"
  /\ holder' = "C"
  /\ origAt' = IF origAt = "B" THEN "C" ELSE origAt
  /\ t2' = IF member \/ recLocal = "B" THEN "inflight" ELSE "none"
  /\ UNCHANGED <<qRead, member, asked, recLocal, t1, ans>>

DeliverT1 ==
  /\ t1 = "inflight" /\ t1' = "stored"
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t2, ans>>
LoseT1 ==
  /\ Lossy /\ t1 = "inflight" /\ t1' = "lost"
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t2, ans>>
DeliverT2 ==
  /\ t2 = "inflight" /\ t2' = "stored"
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t1, ans>>
LoseT2 ==
  /\ Lossy /\ t2 = "inflight" /\ t2' = "lost"
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t1, ans>>

(* ---------------- R asks A (the only address it knows) ---------------- *)
\* M1's gate keeps it for whoever holds A's place at that moment (for_handle / follow).
Ask ==
  /\ ~asked
  /\ asked' = TRUE /\ recLocal' = holder /\ origAt' = holder
  /\ UNCHANGED <<holder, qRead, member, t1, t2, ans>>

(* ---------------- answers ---------------- *)
\* the current holder answers over the P2P gateway (Gateway.prepare on M1 passes: M1 follows its own handovers)
Answer(s) ==
  /\ asked /\ ans[s] = "none"
  /\ ((s = "B" /\ holder = "B") \/ (s = "C" /\ holder = "C"))
  /\ ~Unreplyable
  /\ ans' = [ans EXCEPT ![s] = "inflight"]
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t1, t2>>

\* a forged or stray reply from a session that is not in A's chain (judged at once)
Stranger ==
  /\ WithStranger /\ asked /\ ans["X"] = "none"
  /\ ans' = [ans EXCEPT !["X"] = IF Accepts("X") THEN "recorded" ELSE "refused"]
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t1, t2>>

\* Gateway.receive on R: the reverse check uses R's stored testimony.
DeliverAnswer(s) ==
  /\ s \in {"B", "C"} /\ ans[s] = "inflight" /\ Accepts(s)
  /\ ans' = [ans EXCEPT ![s] = "recorded"]
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t1, t2>>

\* The succession chain M1 would return right now: every hop that exists.
PulledT1 == IF holder /= "A" THEN "stored" ELSE t1
PulledT2 == IF holder = "C" THEN "stored" ELSE t2

\* The reverse check failed and the sender's machine is the machine the question went
\* to: R pulls `succession {old, new}` (whole chain), stores it as testimony, and judges
\* again.  The pulled testimony replaces anything still in flight.
DeliverAnswerPull(s) ==
  /\ s \in {"B", "C"} /\ ans[s] = "inflight" /\ ~Accepts(s)
  /\ t1' = PulledT1 /\ t2' = PulledT2
  /\ ans' = [ans EXCEPT ![s] = "recorded"]
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt>>

\* The pull cannot reach the machine (offline): the answer is recorded with the
\* mark "unconfirmed" instead of being refused (P*).
DeliverAnswerUnconfirmed(s) ==
  /\ Lossy /\ s \in {"B", "C"} /\ ans[s] = "inflight" /\ ~Accepts(s)
  /\ ans' = [ans EXCEPT ![s] = "unconfirmed"]
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t1, t2>>

\* The testimony arrives (push) after the answer was marked unconfirmed: confirmed.
Confirm(s) ==
  /\ s \in {"B", "C"} /\ ans[s] = "unconfirmed" /\ Accepts(s)
  /\ ans' = [ans EXCEPT ![s] = "recorded"]
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt, t1, t2>>

\* A later pull reaches the machine and fetches the chain: confirmed.
ConfirmByPull(s) ==
  /\ s \in {"B", "C"} /\ ans[s] = "unconfirmed" /\ ~Accepts(s)
  /\ t1' = PulledT1 /\ t2' = PulledT2
  /\ ans' = [ans EXCEPT ![s] = "recorded"]
  /\ UNCHANGED <<holder, qRead, member, asked, recLocal, origAt>>

Done ==
  /\ (\E s \in {"B", "C"} : ans[s] = "recorded") \/ Unreplyable
  /\ UNCHANGED vars

Next ==
  \/ HandOver1 \/ HandOver2
  \/ DeliverT1 \/ LoseT1 \/ DeliverT2 \/ LoseT2
  \/ Ask
  \/ \E s \in {"B", "C"} : Answer(s)
  \/ Stranger
  \/ \E s \in {"B", "C"} : DeliverAnswer(s) \/ DeliverAnswerPull(s) \/ DeliverAnswerUnconfirmed(s)
                          \/ Confirm(s) \/ ConfirmByPull(s)
  \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------- rules ---------------- *)
\* No testimony will ever come: that hop was sent (it goes with the handover) and R did not get it.
Forever(s) ==
  CASE s = "B" -> holder /= "A" /\ t1 \in {"none", "lost"}
    [] s = "C" -> holder = "C" /\ (t1 \in {"none", "lost"} \/ t2 \in {"none", "lost"})
    [] OTHER -> FALSE

\* handover.py header + PROTOCOL 5.15: "the machine ... tells the machines it talks to,
\* and they accept the successor's answer".  An answer from the successor is never
\* refused for good (refused with no testimony left to come).  Fixed semantics: the
\* answer is recorded, with an "unconfirmed" mark while no testimony is known.
AnswerRecorded ==
  \A s \in {"B", "C"} : ans[s] = "refused" => ~Forever(s)

\* handover.py: "After that the old conversation's address leads to the successor:
\* ... a message from another machine for it ... go to the successor".  Once every hop
\* is handed over and no testimony is in flight, the asker accepts the session M1 routes
\* its question to.  CHANGED (see README): R reads its stored testimony only when it
\* judges an answer, and the pull repairs that view at that moment, so the rule is
\* checked from the moment R has judged the holder's answer: it is either accepted on
\* stored testimony, or it carries the "unconfirmed" mark.
ViewsAgree ==
  (asked /\ holder /= "A" /\ t1 /= "inflight" /\ t2 /= "inflight"
         /\ ans[holder] \in {"recorded", "unconfirmed", "refused"})
    => (Accepts(holder) \/ ans[holder] = "unconfirmed")

\* handover.py: "After that the old conversation's address leads to the successor: ... an answer to a
\* question it was asked all go to the successor"; the letter tells the successor to "answer each
\* sender at the address it shows".  A question put to the old session can still be answered.
QuestionAnswerable == ~Unreplyable

\* handover.py: "that machine accepts an answer only from that endpoint" (or its successor);
\* questions.record_reply: "store only a reply from the selected peer".
StrangerNeverRecorded == ans["X"] /= "recorded"

\* ADDED (not in the original): the successor's answer is never refused at all; it is
\* recorded, possibly with the "unconfirmed" mark (spec 3.4, 12).
SuccessorAnswerKept == \A s \in {"B", "C"} : ans[s] /= "refused"

=============================================================================
