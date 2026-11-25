---------------------------- MODULE XsmHeldDeliver ----------------------------
(***************************************************************************)
(* xsm 0.6.1 (HEAD 2a858d3): two DMs to session A, A's receive gate may    *)
(* refuse them, the person may release a held DM with `xsm held deliver`.  *)
(*                                                                         *)
(* Code paths modelled (one real function per action):                     *)
(*  HookHolds   receive._gate: check says block -> hold() writes held/,    *)
(*              receipt "held"; the handoff original stays pending and its *)
(*              delivery_state stays "pending". A receipt that already     *)
(*              exists makes the hook answer "already received" (no effect)*)
(*  HookShows   receive._gate pass: receipt "delivered", _native_handoff   *)
(*              claims + handoff-records the original, text goes to the    *)
(*              model.                                                     *)
(*  InboxTakes  receive.take_inbox_claims: skips originals whose receipt   *)
(*              is held/blocked, claims only delivery_state pending or     *)
(*              delivered, re-runs check(); block -> hold(), receipt held, *)
(*              release(delivery_state="held"); pass -> receipt delivered, *)
(*              handoff-recorded, text returned. One message per step      *)
(*              (a batch of two is two steps; limit=1 is the same).        *)
(*  HeldDeliver cli._held_deliver on the person's yes: receipt becomes     *)
(*              "delivered", held/ entry removed, text printed. It never   *)
(*              touches the handoff original.                              *)
(*  Ack         handoff.ack of a shown claim.                              *)
(*  GateOpens   the person links the sessions: check() now passes.         *)
(***************************************************************************)
EXTENDS Naturals

M == {1, 2}

VARIABLES
  bad,    \* bad[m]: A's gate refuses m while the scope is not opened
  open,   \* the person opened the scope (a link): the gate passes everything
  st,     \* handoff original: "pending" | "shown" (claim, handoff-recorded) | "acked"
  ds,     \* handoff delivery_state: "pending" | "held"
  rc,     \* ledger receipt: "none" | "held" | "delivered"
  hl,     \* a held/ entry for m exists
  holds,  \* how many held/ entries were ever written for m (capped at 2)
  shows,  \* how many times the model was shown m (capped at 2)
  yes     \* the person said yes to `held deliver` for m

vars == <<bad, open, st, ds, rc, hl, holds, shows, yes>>

Blocked(m) == bad[m] /\ ~open
Cap(n) == IF n >= 2 THEN 2 ELSE n
Set(f, m, v) == [f EXCEPT ![m] = v]

Init ==
  /\ bad = [m \in M |-> m = 1] /\ open = FALSE   \* DM1 is out of scope, DM2 passes
  /\ st = [m \in M |-> "pending"] /\ ds = [m \in M |-> "pending"]
  /\ rc = [m \in M |-> "none"] /\ hl = [m \in M |-> FALSE]
  /\ holds = [m \in M |-> 0] /\ shows = [m \in M |-> 0] /\ yes = [m \in M |-> FALSE]

HookHolds(m) ==
  /\ st[m] = "pending" /\ rc[m] = "none" /\ Blocked(m)
  /\ hl' = Set(hl, m, TRUE) /\ holds' = Set(holds, m, Cap(holds[m] + 1))
  /\ rc' = Set(rc, m, "held")
  /\ UNCHANGED <<bad, open, st, ds, shows, yes>>

HookShows(m) ==
  /\ st[m] = "pending" /\ rc[m] = "none" /\ ~Blocked(m)
  /\ rc' = Set(rc, m, "delivered") /\ st' = Set(st, m, "shown")
  /\ shows' = Set(shows, m, Cap(shows[m] + 1))
  /\ UNCHANGED <<bad, open, ds, hl, holds, yes>>

Eligible(m) == st[m] = "pending" /\ ds[m] = "pending" /\ rc[m] # "held"

InboxTakes(m) ==
  /\ Eligible(m)
  /\ IF Blocked(m)
     THEN /\ hl' = Set(hl, m, TRUE) /\ holds' = Set(holds, m, Cap(holds[m] + 1))
          /\ rc' = Set(rc, m, "held") /\ ds' = Set(ds, m, "held")
          /\ UNCHANGED <<st, shows>>
     ELSE /\ rc' = Set(rc, m, "delivered") /\ st' = Set(st, m, "shown")
          /\ shows' = Set(shows, m, Cap(shows[m] + 1))
          /\ UNCHANGED <<ds, hl, holds>>
  /\ UNCHANGED <<bad, open, yes>>

HeldDeliver(m) ==
  /\ hl[m]
  /\ hl' = Set(hl, m, FALSE) /\ rc' = Set(rc, m, "delivered")
  /\ shows' = Set(shows, m, Cap(shows[m] + 1)) /\ yes' = Set(yes, m, TRUE)
  /\ UNCHANGED <<bad, open, st, ds, holds>>

Ack(m) ==
  /\ st[m] = "shown" /\ st' = Set(st, m, "acked")
  /\ UNCHANGED <<bad, open, ds, rc, hl, holds, shows, yes>>

GateOpens ==
  /\ ~open /\ open' = TRUE
  /\ UNCHANGED <<bad, st, ds, rc, hl, holds, shows, yes>>

\* End states: nothing left that any actor can still do.
Done ==
  /\ \A m \in M : st[m] = "acked" \/ (st[m] = "pending" /\ ~hl[m] /\ ~Eligible(m) /\ rc[m] # "none")
  /\ open
  /\ UNCHANGED vars

Next ==
  \/ \E m \in M : HookHolds(m)
  \/ \E m \in M : HookShows(m)
  \/ \E m \in M : InboxTakes(m)
  \/ \E m \in M : HeldDeliver(m)
  \/ \E m \in M : Ack(m)
  \/ GateOpens
  \/ Done

Spec == Init /\ [][Next]_vars

(* Rules *)

\* PROTOCOL.md section 5.1 "held" paragraph (line ~283) and cli._held_deliver
\* docstring (user decision 2026-10-01, "a hold is a stop for the person to
\* decide, never a wall"): the person's yes releases the message once. After
\* it, the same message is not held again (the person is not asked twice) and
\* is not handed to the model a second time.
YesIsFinal == \A m \in M : yes[m] => (holds[m] <= 1 /\ shows[m] <= 1)

\* PROTOCOL.md section 5.1 + cli._held_deliver: a held message reaches the model
\* only through the person's yes.
HeldNeedsYes == \A m \in M : (holds[m] > 0 /\ ~yes[m]) => shows[m] = 0

=============================================================================
