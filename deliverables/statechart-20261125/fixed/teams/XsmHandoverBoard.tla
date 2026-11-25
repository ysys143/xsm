---------------------------- MODULE XsmHandoverBoard ----------------------------
(***************************************************************************)
(* FIXED SEMANTICS (docs/plan/state-model-fixes/spec.md F7, P5).          *)
(* What handover._boards does to one `owner/A` board item.  Same variables *)
(* and rules as deliverables/statechart-20261125/teams/XsmHandoverBoard,  *)
(* with two differences:                                                   *)
(*  - after A closes owner/A it looks at the heads again (ARechecks): any  *)
(*    content head that is not the forwarding note (a member's write made  *)
(*    between the snapshot and the close) is carried to owner/B and the    *)
(*    item is closed over it with one more forwarding note.                *)
(*  - an item left alone because it had more than one head is REPORTED     *)
(*    (`reported`): in the result's `skipped`, the letter and handover/A.  *)
(*                                                                         *)
(* A hands its place over to B. M is another team member who may write     *)
(* `owner/A` while the handover runs.                                      *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

Ids == 1..5   \* one more id than before: the recheck may write a second forwarding note

VARIABLES
  nodes,    \* node ids on item owner/A
  par,      \* par[n]: the nodes n builds on
  kind,     \* "c" content, "n" the forwarding note A writes, "-" unused
  readA,    \* nodes A has read (board_notice.read_ids)
  readM,    \* nodes M has read
  phase,    \* idle | shown | snapped | moved | forwarded | rechecked | recorded
  snap,     \* the heads of owner/A in the snapshot
  skipped,  \* the snapshot had more than one head, so the item was left alone
  reported, \* the skipped item is named in the result, the letter and handover/A
  carried,  \* content nodes copied into owner/B
  mWrites   \* writes M has made

vars == <<nodes, par, kind, readA, readM, phase, snap, skipped, reported, carried, mWrites>>

Heads(S) == {n \in S : ~\E m \in S : n \in par[m]}
Fresh == CHOOSE i \in Ids : i \notin nodes

Init ==
  /\ \/ /\ nodes = {1} /\ par = [i \in Ids |-> {}] /\ kind = [i \in Ids |-> IF i = 1 THEN "c" ELSE "-"]
        /\ readM \in {{}, {1}}
     \/ /\ nodes = {1, 2} /\ par = [i \in Ids |-> {}] /\ kind = [i \in Ids |-> IF i \in {1, 2} THEN "c" ELSE "-"]
        /\ readM \in {{}, {1, 2}}
  /\ readA = {} /\ phase = "idle" /\ snap = {} /\ skipped = FALSE /\ reported = FALSE
  /\ carried = {} /\ mWrites = 0

\* board.show(A): render, then mark every node read.
AReadsBoard ==
  /\ phase = "idle"
  /\ phase' = "shown" /\ readA' = nodes
  /\ UNCHANGED <<nodes, par, kind, readM, snap, skipped, reported, carried, mWrites>>

\* board.current(): the heads of every item, once.
ASnapshot ==
  /\ phase = "shown"
  /\ phase' = "snapped" /\ snap' = Heads(nodes) /\ skipped' = (Cardinality(Heads(nodes)) # 1)
  /\ UNCHANGED <<nodes, par, kind, readA, readM, reported, carried, mWrites>>

\* `if rest is None or len(heads) != 1: continue`, else write owner/B.
AWritesNewOwner ==
  /\ phase = "snapped"
  /\ IF skipped THEN /\ phase' = "forwarded" /\ UNCHANGED carried
     ELSE /\ phase' = "moved" /\ carried' = snap
  /\ UNCHANGED <<nodes, par, kind, readA, readM, snap, skipped, reported, mWrites>>

\* set_item(owner/A, "handed over"): builds on the heads among nodes A has read.
AForwardsOldItem ==
  /\ phase = "moved"
  /\ LET n == Fresh IN
       /\ nodes' = nodes \cup {n}
       /\ par' = [par EXCEPT ![n] = Heads(nodes \cap readA)]
       /\ kind' = [kind EXCEPT ![n] = "n"]
       /\ readA' = readA \cup {n}
  /\ phase' = "forwarded"
  /\ UNCHANGED <<readM, snap, skipped, reported, carried, mWrites>>

\* After the close: look at the heads again.  A content head that is not the
\* forwarding note (a member wrote after the snapshot, so A had not read it) is
\* carried to owner/B, and owner/A is closed over everything with one more note.
\* A skipped (multi-head) item is not touched.
ARechecks ==
  /\ phase = "forwarded"
  /\ LET extra == {h \in Heads(nodes) : kind[h] = "c"} IN
       IF skipped \/ extra = {}
         THEN UNCHANGED <<nodes, par, kind, readA, carried>>
         ELSE LET n == Fresh IN
                /\ carried' = carried \cup extra
                /\ nodes' = nodes \cup {n}
                /\ par' = [par EXCEPT ![n] = Heads(nodes)]
                /\ kind' = [kind EXCEPT ![n] = "n"]
                /\ readA' = readA \cup {n}
  /\ phase' = "rechecked"
  /\ UNCHANGED <<readM, snap, skipped, reported, mWrites>>

\* set_item(handover/A, ...): another item.  A skipped item is named in the
\* result, the letter and handover/A.
ARecordsHandover ==
  /\ phase = "rechecked"
  /\ phase' = "recorded"
  /\ reported' = skipped
  /\ UNCHANGED <<nodes, par, kind, readA, readM, snap, skipped, carried, mWrites>>

\* A member writes owner/A on top of the heads among the nodes it has read.
MWritesItem ==
  \* Only before A's own close of owner/A: a write after it is any member's late
  \* write to a closed item, not something the handover's order decides.
  /\ phase \in {"idle", "shown", "snapped", "moved"} /\ mWrites < 1
  /\ LET n == Fresh IN
       /\ nodes' = nodes \cup {n}
       /\ par' = [par EXCEPT ![n] = Heads(nodes \cap readM)]
       /\ kind' = [kind EXCEPT ![n] = "c"]
       /\ readM' = readM \cup {n}
  /\ mWrites' = mWrites + 1
  /\ UNCHANGED <<readA, phase, snap, skipped, reported, carried>>

Done ==
  /\ phase = "recorded"
  /\ UNCHANGED vars

Next ==
  \/ AReadsBoard \/ ASnapshot \/ AWritesNewOwner \/ AForwardsOldItem \/ ARechecks \/ ARecordsHandover
  \/ MWritesItem
  \/ Done

Spec == Init /\ [][Next]_vars

(* ---------------- rules ---------------- *)

\* xsm/handover.py docstring: "the board items it owns: owner/<its name> ...
\* become owner/<the successor's name>"; docs/xsm/PROTOCOL.md 5.15: an owner
\* item with ONE head is written to owner/<new> and the old item is recorded
\* ("옛 항목과 handover/<옛 이름> 항목에 기록"). So once the handover is recorded,
\* an item it chose to move has nothing but the forwarding note as head.
MovedItemIsClosed ==
  (phase = "recorded" /\ ~skipped) => (\A h \in Heads(nodes) : kind[h] = "n")

\* Same sources: what was in owner/A reaches owner/B. A head of the old item
\* that is content and was not copied is content nobody carried over.
NoContentLeftBehind ==
  (phase = "recorded" /\ ~skipped) => (\A h \in Heads(nodes) : kind[h] = "n" \/ h \in carried)

\* handover.py docstring takes every owner/<name> item; PROTOCOL 5.15 limits the
\* move to single-head items ("머리가 하나인 것만"). CHANGED (see README): an item
\* with more than one head is still not moved (spec 3.2, P5); it must be REPORTED.
\* So after the handover every owner/A item is closed, or it was skipped and named.
EveryOwnerItemClosed ==
  phase = "recorded" => ((\A h \in Heads(nodes) : kind[h] = "n") \/ (skipped /\ reported))
=============================================================================
