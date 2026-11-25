---------------------------- MODULE XsmTransfer ----------------------------
(***************************************************************************)
(* xsm 0.6.1 (HEAD 2a858d3): one DM at session A while the person moves   *)
(* A's place to B with `xsm migrate` (xsm/migration.py, migration_state.py)*)
(*                                                                         *)
(* Real code per action:                                                   *)
(*  Fence      migration.execute: source index "retired" + target index.   *)
(*             From now on migration.assert_active(A) raises in            *)
(*             handoff.claim and handoff._transition (ack/release/handoff) *)
(*             and in take_inbox_claims' first line. assert_active(B)      *)
(*             raises until the job is committed ("incomplete").           *)
(*  Messages   migration_state.messages -> handoff.transfer: every original*)
(*             that is not acknowledged is copied to B as state pending,   *)
(*             claim None, delivery_state copied; A's original becomes     *)
(*             pending + moved_to, claim None. The ledger receipt is keyed *)
(*             by message id only, so it is shared by both copies.         *)
(*  HeldStep   migration_state.held rebinds held/ entries whose            *)
(*             receiver_ref is A to B (only the ones that exist then).     *)
(*  Commit     final drain + status committed.                             *)
(*  Reader     receive.take_inbox_claims, in code order:                   *)
(*    claim -> check()                                                     *)
(*      block: hold() writes held/ bound to the reader's own ref,          *)
(*             ledger.receipt held, handoff.release(delivery_state held)   *)
(*      pass : ledger.receipt delivered, handoff.handoff, text returned    *)
(*    hold() and ledger.receipt take no migration check; claim, release    *)
(*    and handoff do. A failed release is swallowed (MigrationError is a   *)
(*    ValueError); the caller gets the exception, not the message.         *)
(*  HookHolds  receive._gate on A's native queue copy: hold + receipt held,*)
(*             the original stays pending/pending.                         *)
(***************************************************************************)
EXTENDS Naturals

Site == {"A", "B"}

VARIABLES
  bad,    \* the gate refuses the DM (same verdict at A and B)
  mig,    \* "none" | "fenced" | "messages" | "held" | "committed"
  st,     \* original at each site: "none"|"pending"|"claimed"|"shown"|"acked"|"moved"
  rs,     \* reader pipeline at each site (see below)
  ds,     \* handoff delivery_state: "pending" | "held"
  rc,     \* ledger receipt: "none" | "held" | "delivered"
  he,     \* held/ entry and the session it is bound to: "none" | "A" | "B"
  seen,   \* how many times a model was shown the text (reader or held deliver), capped at 2
  acks    \* number of successful ACKs across both sites

vars == <<bad, mig, st, rs, ds, rc, he, seen, acks>>

Active(s) == IF s = "A" THEN mig = "none" ELSE mig = "committed"
Set(f, k, v) == [f EXCEPT ![k] = v]
Cap(n) == IF n >= 2 THEN 2 ELSE n
Live == {"pending", "claimed", "shown"}

Init ==
  /\ bad \in BOOLEAN /\ mig = "none"
  /\ st = [s \in Site |-> IF s = "A" THEN "pending" ELSE "none"]
  /\ rs = [s \in Site |-> "idle"]
  /\ ds = "pending" /\ rc = "none" /\ he = "none"
  /\ seen = 0 /\ acks = 0

(* ---- readers ---- *)

ReaderClaims(s) ==
  /\ Active(s) /\ rs[s] = "idle" /\ st[s] = "pending" /\ ds = "pending" /\ rc # "held"
  /\ st' = Set(st, s, "claimed")
  /\ rs' = Set(rs, s, IF bad THEN "toHold" ELSE "toReceipt")
  /\ UNCHANGED <<bad, mig, ds, rc, he, seen, acks>>

HoldWrites(s) ==
  /\ rs[s] = "toHold"
  /\ he' = s /\ rc' = "held" /\ rs' = Set(rs, s, "toRelease")
  /\ UNCHANGED <<bad, mig, st, ds, seen, acks>>

ReleaseHeld(s) ==
  /\ rs[s] = "toRelease"
  /\ IF Active(s)
     THEN st' = Set(st, s, "pending") /\ ds' = "held" /\ rs' = Set(rs, s, "done")
     ELSE UNCHANGED <<st, ds>> /\ rs' = Set(rs, s, "dead")
  /\ UNCHANGED <<bad, mig, rc, he, seen, acks>>

WritesReceipt(s) ==
  /\ rs[s] = "toReceipt"
  /\ rc' = "delivered" /\ rs' = Set(rs, s, "toHandoff")
  /\ UNCHANGED <<bad, mig, st, ds, he, seen, acks>>

RecordsHandoff(s) ==
  /\ rs[s] = "toHandoff"
  /\ IF Active(s)
     THEN st' = Set(st, s, "shown") /\ seen' = Cap(seen + 1) /\ rs' = Set(rs, s, "done")
     ELSE UNCHANGED <<st, seen>> /\ rs' = Set(rs, s, "dead")
  /\ UNCHANGED <<bad, mig, ds, rc, he, acks>>

Acks(s) ==
  /\ Active(s) /\ st[s] = "shown"
  /\ st' = Set(st, s, "acked") /\ acks' = acks + 1
  /\ UNCHANGED <<bad, mig, rs, ds, rc, he, seen>>

HookHolds ==
  /\ mig = "none" /\ bad /\ st["A"] = "pending" /\ rc = "none"
  /\ he' = "A" /\ rc' = "held"
  /\ UNCHANGED <<bad, mig, st, rs, ds, seen, acks>>

(* ---- the migration ---- *)

Fence ==
  /\ mig = "none" /\ mig' = "fenced"
  /\ UNCHANGED <<bad, st, rs, ds, rc, he, seen, acks>>

Transfers ==
  /\ mig = "fenced" /\ mig' = "messages"
  /\ IF st["A"] \in Live
     THEN st' = [st EXCEPT !["A"] = "moved", !["B"] = "pending"]
     ELSE UNCHANGED st
  /\ UNCHANGED <<bad, rs, ds, rc, he, seen, acks>>

MovesHeld ==
  /\ mig = "messages" /\ mig' = "held"
  /\ he' = IF he = "A" THEN "B" ELSE he
  /\ UNCHANGED <<bad, st, rs, ds, rc, seen, acks>>

Commits ==
  /\ mig = "held" /\ mig' = "committed"
  /\ UNCHANGED <<bad, st, rs, ds, rc, he, seen, acks>>

Done ==
  /\ mig = "committed"
  /\ \A s \in Site : rs[s] \in {"idle", "done", "dead"}
  /\ \A s \in Site : st[s] \in {"none", "acked", "moved"}
       \/ (s = "B" /\ st[s] = "pending" /\ (ds = "held" \/ rc = "held"))
  /\ UNCHANGED vars

Next ==
  \/ \E s \in Site : ReaderClaims(s)
  \/ \E s \in Site : HoldWrites(s)
  \/ \E s \in Site : ReleaseHeld(s)
  \/ \E s \in Site : WritesReceipt(s)
  \/ \E s \in Site : RecordsHandoff(s)
  \/ \E s \in Site : Acks(s)
  \/ HookHolds
  \/ Fence \/ Transfers \/ MovesHeld \/ Commits
  \/ Done

Spec == Init /\ [][Next]_vars

(* Rules *)

\* handoff.ack docstring "Explicit confirmed consumption"; plan
\* docs/plan/runtime-protocol/session-profile-migration.md section 4 row
\* "claim / ACK in progress" ("an old token's late ACK must not close the
\* successor's message") and acceptance item 5.
AckedOnce == acks <= 1

\* plan section 4 row "unread DM" and verify(): every original is acknowledged
\* at the source or has a live copy at the target once the job is committed.
NoStrandedOriginal == mig = "committed" => st["A"] \in {"acked", "moved"}
NoLostCopy == st["A"] = "moved" => st["B"] # "none"

\* plan section 4 row "held message": held reason and source move with it;
\* the transfer is not a release. The target reader must not show it.
HeldNotShown == rc = "held" => seen = 0

\* plan section 4 row "held message" ("reason and source are moved together"),
\* migration_state.held docstring-level intent: after the job is committed no
\* held/ entry is still bound to the retired source, because the source
\* session cannot run `xsm held deliver` and the successor's agent is refused
\* for another session's hold (cli._held_deliver, receiver_ref check).
HeldFollowsOwner == mig = "committed" => he # "A"

\* handoff.transfer docstring "without inventing delivery or ACK evidence";
\* ADR-0018 evidence table: a delivered receipt says the runtime path took the
\* message. It must not exist while nobody has shown the message.
DeliveredMeansShown ==
  rc = "delivered" =>
    (seen > 0 \/ rs["A"] = "toHandoff" \/ rs["B"] = "toHandoff")


=============================================================================
