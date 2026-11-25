# XsmTransfer

TLC reached 98 states and 133 steps. The chart draws 26 states and 37 arrows.
The chart does not draw 23 steps that stay in one chart state.
The view hides 11 steps, so the chart does not draw them.
The step A's hook refuses the DM and keeps a held copy changes AtA, HeldList and Receipt at the same time.
The step xsm copies A's unconfirmed DMs to B changes Migration, AtA and AtB at the same time.
The step A's gate refuses it and keeps a held copy changes HeldList and Receipt, or AtB, HeldList and Receipt, at the same time.
The step xsm moves A's held list to B changes Migration and HeldList at the same time.
The step B's gate refuses it and keeps a held copy changes HeldList and Receipt at the same time.

## DeliveredMeansShown breaks
The shortest path has 4 steps:
0. Migration not started, AtA waiting, AtB no copy, HeldList no held entry, Receipt no receipt
1. A's reader takes the DM: Migration not started, AtA reader is about to show it, AtB no copy, HeldList no held entry, Receipt no receipt
2. the person approves the move; A is fenced: Migration A fenced, AtA reader is about to show it, AtB no copy, HeldList no held entry, Receipt no receipt
3. A's gate passes it and writes a delivered receipt: Migration A fenced, AtA reader is about to show it, AtB no copy, HeldList no held entry, Receipt receipt: delivered
4. recording the handoff is refused: Migration A fenced, AtA reader failed mid-way, claim stuck, AtB no copy, HeldList no held entry, Receipt receipt: delivered

## HeldFollowsOwner breaks
The shortest path has 6 steps:
0. Migration not started, AtA waiting, AtB no copy, HeldList no held entry, Receipt no receipt
1. A's reader takes the DM: Migration not started, AtA reader is holding it back, AtB no copy, HeldList no held entry, Receipt no receipt
2. the person approves the move; A is fenced: Migration A fenced, AtA reader is holding it back, AtB no copy, HeldList no held entry, Receipt no receipt
3. xsm copies A's unconfirmed DMs to B: Migration DMs copied to B, AtA moved to B, AtB waiting, HeldList no held entry, Receipt no receipt
4. xsm moves A's held list to B: Migration held list moved, AtA moved to B, AtB waiting, HeldList no held entry, Receipt no receipt
5. the move is committed: Migration committed, AtA moved to B, AtB waiting, HeldList no held entry, Receipt no receipt
6. A's gate refuses it and keeps a held copy: Migration committed, AtA moved to B, AtB waiting, held, HeldList held entry bound to A, Receipt receipt: held

## Rules that hold
AckedOnce, NoStrandedOriginal, NoLostCopy, HeldNotShown, NoDeadlock
