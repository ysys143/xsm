# XsmHeldDeliver

TLC reached 54 states and 121 steps. The chart draws 13 states and 11 arrows.
The view hides 4 steps, so the chart does not draw them.

## YesIsFinal breaks
The shortest path has 3 steps:
0. DM1 waiting at A, DM2 waiting at A, Scope no link
1. A's hook holds DM1: DM1 held, waiting for the person's yes, DM2 waiting at A, Scope no link
2. person says yes: held deliver DM1: DM1 person said yes; the original is still pending, DM2 waiting at A, Scope no link
3. A's inbox holds DM1: DM1 held again, waiting for the person's yes, DM2 waiting at A, Scope no link

## Rules that hold
HeldNeedsYes, NoDeadlock
