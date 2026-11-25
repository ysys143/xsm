# XsmScopeGroups

TLC reached 91 states and 126 steps. The chart draws 12 states and 11 arrows.
The view hides 28 steps, so the chart does not draw them.

## LateAnswerReachesSuccessor breaks
The shortest path has 2 steps:
0. A holds its place, 0 of 2 answered; group view: pending, showing 0 of the 0 final answers given
1. the person approves the handover [P may not talk to B]: B holds the place; 2 still waiting; group view: pending, showing 0 of the 0 final answers given
2. P answers late: the send is refused, out of scope: B holds the place; 1 late answer refused as out of scope, 1 still waiting; group view: pending, showing 0 of the 0 final answers given

## GroupShowsEveryAnswer breaks
The shortest path has 2 steps:
0. A holds its place, 0 of 2 answered; group view: pending, showing 0 of the 0 final answers given
1. P answers a question: A holds its place, 1 of 2 answered; group view: reply_received, showing 1 of the 1 final answer given
2. the person approves the handover [P may talk to B]: B holds the place; 1 answered before the handover, record left with A, 1 still waiting; group view: pending, showing 0 of the 1 final answer given

## GroupStatusTruthful breaks
The shortest path has 2 steps:
0. A holds its place, 0 of 2 answered; group view: pending, showing 0 of the 0 final answers given
1. P answers a question: A holds its place, 1 of 2 answered; group view: reply_received, showing 1 of the 1 final answer given
2. the person approves the handover [P may talk to B]: B holds the place; 1 answered before the handover, record left with A, 1 still waiting; group view: pending, showing 0 of the 1 final answer given

## Rules that hold
WaitingOnHonest, OpenQuestionsBelongToHolder, TypeOK, NoDeadlock
