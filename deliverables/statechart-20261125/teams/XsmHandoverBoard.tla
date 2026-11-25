---------------------------- MODULE XsmHandoverBoard ----------------------------
(***************************************************************************)
(* xsm 0.6.1: what handover._boards does to one `owner/A` board item       *)
(* (xsm/handover.py _boards, xsm/board.py set_item/heads/current).         *)
(*                                                                         *)
(* A hands its place over to B. M is another team member who may write     *)
(* `owner/A` while the handover runs (a window of several file writes,     *)
(* renders and network publishes, or a node arriving from another machine).*)
(*                                                                         *)
(* Code order in _boards, per team:                                        *)
(*   board.show(A)              A has now read every node there is         *)
(*   board.current()            ONE snapshot of every item's heads         *)
(*   for each item owner/A...:  skipped unless the snapshot has one head   *)
(*     set_item(owner/B, body + "(taken over)")                            *)
(*     set_item(owner/A, "handed over to B")   its parents = the heads of  *)
(*                                             the nodes A has READ        *)
(*   set_item(handover/A, ...)                                             *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

Ids == 1..4

VARIABLES
  nodes,    \* node ids on item owner/A
  par,      \* par[n]: the nodes n builds on
  kind,     \* "c" content, "n" the forwarding note A writes, "-" unused
  readA,    \* nodes A has read (board_notice.read_ids)
  readM,    \* nodes M has read
  phase,    \* idle | shown | snapped | moved | forwarded | recorded
  snap,     \* the heads of owner/A in the snapshot
  skipped,  \* the snapshot had more than one head, so the item was left alone
  carried,  \* content nodes copied into owner/B
  mWrites   \* writes M has made

vars == <<nodes, par, kind, readA, readM, phase, snap, skipped, carried, mWrites>>

Heads(S) == {n \in S : ~\E m \in S : n \in par[m]}
Fresh == CHOOSE i \in Ids : i \notin nodes

Init ==
  /\ \/ /\ nodes = {1} /\ par = [i \in Ids |-> {}] /\ kind = [i \in Ids |-> IF i = 1 THEN "c" ELSE "-"]
        /\ readM \in {{}, {1}}
     \/ /\ nodes = {1, 2} /\ par = [i \in Ids |-> {}] /\ kind = [i \in Ids |-> IF i \in {1, 2} THEN "c" ELSE "-"]
        /\ readM \in {{}, {1, 2}}
  /\ readA = {} /\ phase = "idle" /\ snap = {} /\ skipped = FALSE
  /\ carried = {} /\ mWrites = 0

\* board.show(A): render, then mark every node read.
AReadsBoard ==
  /\ phase = "idle"
  /\ phase' = "shown" /\ readA' = nodes
  /\ UNCHANGED <<nodes, par, kind, readM, snap, skipped, carried, mWrites>>

\* board.current(): the heads of every item, once.
ASnapshot ==
  /\ phase = "shown"
  /\ phase' = "snapped" /\ snap' = Heads(nodes) /\ skipped' = (Cardinality(Heads(nodes)) # 1)
  /\ UNCHANGED <<nodes, par, kind, readA, readM, carried, mWrites>>

\* `if rest is None or len(heads) != 1: continue`, else write owner/B.
AWritesNewOwner ==
  /\ phase = "snapped"
  /\ IF skipped THEN /\ phase' = "forwarded" /\ UNCHANGED carried
     ELSE /\ phase' = "moved" /\ carried' = snap
  /\ UNCHANGED <<nodes, par, kind, readA, readM, snap, skipped, mWrites>>

\* set_item(owner/A, "handed over"): builds on the heads among nodes A has read.
AForwardsOldItem ==
  /\ phase = "moved"
  /\ LET n == Fresh IN
       /\ nodes' = nodes \cup {n}
       /\ par' = [par EXCEPT ![n] = Heads(nodes \cap readA)]
       /\ kind' = [kind EXCEPT ![n] = "n"]
       /\ readA' = readA \cup {n}
  /\ phase' = "forwarded"
  /\ UNCHANGED <<readM, snap, skipped, carried, mWrites>>

\* set_item(handover/A, ...): another item.
ARecordsHandover ==
  /\ phase = "forwarded"
  /\ phase' = "recorded"
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
  /\ UNCHANGED <<readA, phase, snap, skipped, carried>>

Done ==
  /\ phase = "recorded"
  /\ UNCHANGED vars

Next ==
  \/ AReadsBoard \/ ASnapshot \/ AWritesNewOwner \/ AForwardsOldItem \/ ARecordsHandover
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
\* move to single-head items ("머리가 하나인 것만"). Read as the docstring does:
\* after the handover no owner/A item has a head that is not the forwarding note.
EveryOwnerItemClosed ==
  phase = "recorded" => (\A h \in Heads(nodes) : kind[h] = "n")
=============================================================================
