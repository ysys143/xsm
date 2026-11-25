# XsmHandoverBoard

TLC reached 76 states and 90 steps. The chart draws 26 states and 33 arrows.
The chart does not draw 3 steps that stay in one chart state.
The view hides 16 steps, so the chart does not draw them.

## EveryOwnerItemClosed breaks
The shortest path has 4 steps:
0. A has not started: owner/A shows 2 versions at once
1. A reads the board: A has read the board: owner/A shows 2 versions at once
2. A lists the items [one has two versions]: A took the list of items: owner/A shows 2 versions at once; owner/B gets nothing (item was in conflict)
3. A leaves the conflicted item alone: A closed owner/A: owner/A shows 2 versions at once; owner/B gets nothing (item was in conflict)
4. A writes the handover/A item: A wrote handover/A: owner/A shows 2 versions at once; owner/B gets nothing (item was in conflict)

## MovedItemIsClosed breaks
The shortest path has 6 steps:
0. A has not started: owner/A holds one version
1. A reads the board: A has read the board: owner/A holds one version
2. A lists the items: A took the list of items: owner/A holds one version
3. A copies owner/A into owner/B: A wrote owner/B: owner/A holds one version; owner/B holds A's items
4. a member writes owner/A: A wrote owner/B: owner/A shows 2 versions at once; owner/B written, but misses a later version
5. A overwrites owner/A with 'handed over': A closed owner/A: owner/A shows the handover note beside 1 unforwarded version; owner/B written, but misses a later version
6. A writes the handover/A item: A wrote handover/A: owner/A shows the handover note beside 1 unforwarded version; owner/B written, but misses a later version

## NoContentLeftBehind breaks
The shortest path has 6 steps:
0. A has not started: owner/A holds one version
1. A reads the board: A has read the board: owner/A holds one version
2. A lists the items: A took the list of items: owner/A holds one version
3. A copies owner/A into owner/B: A wrote owner/B: owner/A holds one version; owner/B holds A's items
4. a member writes owner/A: A wrote owner/B: owner/A shows 2 versions at once; owner/B written, but misses a later version
5. A overwrites owner/A with 'handed over': A closed owner/A: owner/A shows the handover note beside 1 unforwarded version; owner/B written, but misses a later version
6. A writes the handover/A item: A wrote handover/A: owner/A shows the handover note beside 1 unforwarded version; owner/B written, but misses a later version

## Rules that hold
NoDeadlock
