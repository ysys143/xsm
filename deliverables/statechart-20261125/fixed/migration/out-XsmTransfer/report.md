# XsmTransfer

TLC reached 100 states and 145 steps. The chart draws 26 states and 36 arrows.
The chart does not draw 22 steps that stay in one chart state.
The view hides 9 steps, so the chart does not draw them.
The step A's hook refuses the DM and keeps a held copy changes AtA, HeldList and Receipt at the same time.
The step xsm copies A's unconfirmed DMs to B changes Migration, AtA and AtB at the same time.
The step A's gate refuses it and keeps a held copy changes HeldList and Receipt, or AtB, HeldList and Receipt, at the same time.
The step xsm moves A's held list to B changes Migration and HeldList at the same time.
The step B's gate refuses it and keeps a held copy changes HeldList and Receipt at the same time.

## Rules that hold
AckedOnce, NoStrandedOriginal, NoLostCopy, HeldNotShown, HeldFollowsOwner, DeliveredMeansShown, NoDeadlock
