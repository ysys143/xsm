# XsmHandoverPlaces

TLC reached 24 states and 32 steps. The chart draws 16 states and 21 arrows.
The chart does not draw 1 steps that stay in one chart state.
The view hides 6 steps, so the chart does not draw them.

## PlaceAndItemsMoveTogether breaks
The shortest path has 5 steps:
0. Not started: A in t1; boards moved in no team; B took A's place in no team
1. the handover lists A's teams for the boards: Running: A in t1; boards moved in no team; B took A's place in no team
2. A's items in one team are moved to B: Running: A in t1; boards moved in t1; B took A's place in no team
3. someone removes A from a team: Running: A in no team; boards moved in t1; B took A's place in no team
4. the handover lists A's teams again: Running: A in no team; boards moved in t1; B took A's place in no team
5. the handover is recorded: Handover done: A in no team; boards moved in t1; B took A's place in no team

## BCanReachWhatMoved breaks
The shortest path has 5 steps:
0. Not started: A in t1; boards moved in no team; B took A's place in no team
1. the handover lists A's teams for the boards: Running: A in t1; boards moved in no team; B took A's place in no team
2. A's items in one team are moved to B: Running: A in t1; boards moved in t1; B took A's place in no team
3. someone removes A from a team: Running: A in no team; boards moved in t1; B took A's place in no team
4. the handover lists A's teams again: Running: A in no team; boards moved in t1; B took A's place in no team
5. the handover is recorded: Handover done: A in no team; boards moved in t1; B took A's place in no team

## NoPlaceLeftBehind breaks
The shortest path has 6 steps:
0. Not started: A in t1; boards moved in no team; B took A's place in no team
1. the handover lists A's teams for the boards: Running: A in t1; boards moved in no team; B took A's place in no team
2. A's items in one team are moved to B: Running: A in t1; boards moved in t1; B took A's place in no team
3. the handover lists A's teams again: Running: A in t1; boards moved in t1; B took A's place in no team
4. someone adds A to another team: Running: A in t1 and t2; boards moved in t1; B took A's place in no team
5. B takes A's place in one team: Running: A in t2; boards moved in t1; B took A's place in t1
6. the handover is recorded: Handover done: A in t2; boards moved in t1; B took A's place in t1

## Rules that hold
NoDeadlock
