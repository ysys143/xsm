# XsmConcurrentHandover

TLC reached 56 states and 78 steps. The chart draws 26 states and 24 arrows.
The view hides 10 steps, so the chart does not draw them.
The step A to B moves the team seat changes Handover A to B and Team at the same time.
The step A to C moves the team seat changes Handover A to C and Team at the same time.
The step A to B moves the pending question changes Handover A to B and Question at the same time.
The step A to C moves the pending question changes Handover A to C and Question at the same time.
The step A to B writes its handover record changes Handover A to B, Records and Address at the same time.
The step A to C writes its handover record changes Handover A to C, Records and Address at the same time.

## AtMostOneHandoverPerSession breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B

## AddressAndPlaceAgree breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B

## QuestionHolderIsAddressTarget breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B

## LateAnswerRecorded breaks
The shortest path has 9 steps:
0. Handover A to B not started, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover A to C not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves A to C and it passes its check: Handover A to B approved and checked, Handover A to C approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover A to C approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover A to C approved and checked, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. A to C moves the team seat: Handover A to B record written, Handover A to C team seat moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. A to C moves the pending question: Handover A to B record written, Handover A to C pending question moved, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
8. A to C writes its handover record: Handover A to B record written, Handover A to C record written, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question open, asked by B
9. the peer's late answer arrives and is refused: Handover A to B record written, Handover A to C record written, Team members: B; lead seat: B, Records A handed to C, Address DMs to A reach C, Question late answer sent to C, not stored: the question is B's

## Rules that hold
AddressLeadsAway, HandedOverHoldsNoPlace, NoDeadlock
