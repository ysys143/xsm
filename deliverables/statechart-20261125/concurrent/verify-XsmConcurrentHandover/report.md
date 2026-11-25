# XsmConcurrentHandover

TLC reached 208 states and 327 steps. The chart draws 208 states and 300 arrows.
The view hides 27 steps, so the chart does not draw them.
In Handover A to B, the person approves A to B and it passes its check from not started depends on the other regions in a way that one "and" or "or" condition cannot say. So the chart draws parent states in place of regions.

## AtMostOneHandoverPerSession breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B

## AddressAndPlaceAgree breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B

## QuestionHolderIsAddressTarget breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B

## AddressLeadsAway breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves B to A and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. B to A moves the team seat: Handover A to B record written, Handover A to C not started, Handover B to A team seat moved, Handover B to C not started, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. B to A moves the pending question: Handover A to B record written, Handover A to C not started, Handover B to A pending question moved, Handover B to C not started, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by A
8. B to A writes its handover record: Handover A to B record written, Handover A to C not started, Handover B to A record written, Handover B to C not started, Team members: A; lead seat: A, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question open, asked by A

## HandedOverHoldsNoPlace breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves B to A and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C not started, Handover B to A approved and checked, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. B to A moves the team seat: Handover A to B record written, Handover A to C not started, Handover B to A team seat moved, Handover B to C not started, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. B to A moves the pending question: Handover A to B record written, Handover A to C not started, Handover B to A pending question moved, Handover B to C not started, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by A
8. B to A writes its handover record: Handover A to B record written, Handover A to C not started, Handover B to A record written, Handover B to C not started, Team members: A; lead seat: A, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question open, asked by A

## LateAnswerRecorded breaks
The shortest path has 9 steps:
0. Handover A to B not started, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B
9. the peer's late answer arrives and is refused: Handover A to B record written, Handover A to C record written, Handover B to A not started, Handover B to C not started, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question late answer sent to C, not stored: the question is B's

## Rules that hold
NoDeadlock
