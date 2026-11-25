# XsmHandoverTeamSync

TLC reached 30 states and 42 steps. The chart draws 27 states and 36 arrows.
The view hides 4 steps, so the chart does not draw them.

## HandoverStands breaks
The shortest path has 3 steps:
0. X: A leads (created here); Y: A leads (last received from X); no record in flight
1. X hands A's seat to B and sends the team: X: B leads, A is out (created here); Y: A leads (last received from X); 1 in flight
2. Y changes the team and sends it: X: B leads, A is out (created here); Y: A leads, Y's change in (last received from X); 2 in flight
3. X takes Y's record, replacing its own: X: A leads, Y's change in (last received from Y); Y: A leads, Y's change in (last received from X); 1 in flight

## BHoldsTheSeatEverywhere breaks
The shortest path has 4 steps:
0. X: A leads (created here); Y: A leads (last received from X); no record in flight
1. X hands A's seat to B and sends the team: X: B leads, A is out (created here); Y: A leads (last received from X); 1 in flight
2. Y changes the team and sends it: X: B leads, A is out (created here); Y: A leads, Y's change in (last received from X); 2 in flight
3. a machine refuses the record as not newer: X: B leads, A is out (created here); Y: A leads, Y's change in (last received from X); 1 in flight
4. X takes Y's record, replacing its own: X: A leads, Y's change in (last received from Y); Y: A leads, Y's change in (last received from X); no record in flight

## SameTeamAtRest breaks
The shortest path has 4 steps:
0. X: A leads (last received from Y); Y: A leads (last received from X); no record in flight
1. X hands A's seat to B and sends the team: X: B leads, A is out (last received from Y); Y: A leads (last received from X); 1 in flight
2. Y changes the team and sends it: X: B leads, A is out (last received from Y); Y: A leads, Y's change in (last received from X); 2 in flight
3. a machine refuses the record as not newer: X: B leads, A is out (last received from Y); Y: A leads, Y's change in (last received from X); 1 in flight
4. a machine refuses the record as not newer: X: B leads, A is out (last received from Y); Y: A leads, Y's change in (last received from X); no record in flight

## Rules that hold
NoDeadlock
