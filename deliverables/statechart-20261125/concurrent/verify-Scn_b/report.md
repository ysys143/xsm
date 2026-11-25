# XsmConcurrentHandover

TLC reached 48 states and 70 steps. The chart draws 24 states and 22 arrows.
The view hides 6 steps, so the chart does not draw them.
The step A to B moves the team seat changes Handover A to B and Team at the same time.
The step B to A moves the team seat changes Handover B to A and Team at the same time.
The step B to A moves the pending question changes Handover B to A and Question at the same time.
The step A to B moves the pending question changes Handover A to B and Question at the same time.
The step B to A writes its handover record changes Handover B to A and Records, or Handover B to A, Records and Address, at the same time.
The step A to B writes its handover record changes Handover A to B, Records and Address at the same time.

## AddressAndPlaceAgree breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves B to A and it passes its check: Handover A to B approved and checked, Handover B to A approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. B to A moves the team seat: Handover A to B approved and checked, Handover B to A team seat moved, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the team seat: Handover A to B team seat moved, Handover B to A team seat moved, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
5. A to B moves the pending question: Handover A to B pending question moved, Handover B to A team seat moved, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
6. B to A moves the pending question: Handover A to B pending question moved, Handover B to A pending question moved, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
7. B to A writes its handover record: Handover A to B pending question moved, Handover B to A record written, Team members: B; lead seat: B, Records B handed to A, Address DMs to A reach A, Question open, asked by A
8. A to B writes its handover record: Handover A to B record written, Handover B to A record written, Team members: B; lead seat: B, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question open, asked by A

## AddressLeadsAway breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves B to A and it passes its check: Handover A to B approved and checked, Handover B to A approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover B to A approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover B to A approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover B to A approved and checked, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. B to A moves the team seat: Handover A to B record written, Handover B to A team seat moved, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. B to A moves the pending question: Handover A to B record written, Handover B to A pending question moved, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by A
8. B to A writes its handover record: Handover A to B record written, Handover B to A record written, Team members: A; lead seat: A, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question open, asked by A

## HandedOverHoldsNoPlace breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves B to A and it passes its check: Handover A to B approved and checked, Handover B to A approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover B to A approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. A to B moves the pending question: Handover A to B pending question moved, Handover B to A approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by B
5. A to B writes its handover record: Handover A to B record written, Handover B to A approved and checked, Team members: B; lead seat: B, Records A handed to B, Address DMs to A reach B, Question open, asked by B
6. B to A moves the team seat: Handover A to B record written, Handover B to A team seat moved, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by B
7. B to A moves the pending question: Handover A to B record written, Handover B to A pending question moved, Team members: A; lead seat: A, Records A handed to B, Address DMs to A reach B, Question open, asked by A
8. B to A writes its handover record: Handover A to B record written, Handover B to A record written, Team members: A; lead seat: A, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question open, asked by A

## QuestionHolderIsAddressTarget breaks
The shortest path has 8 steps:
0. Handover A to B not started, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves B to A and it passes its check: Handover A to B approved and checked, Handover B to A approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover B to A approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. B to A moves the team seat: Handover A to B team seat moved, Handover B to A team seat moved, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
5. B to A moves the pending question: Handover A to B team seat moved, Handover B to A pending question moved, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
6. A to B moves the pending question: Handover A to B pending question moved, Handover B to A pending question moved, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by B
7. B to A writes its handover record: Handover A to B pending question moved, Handover B to A record written, Team members: A; lead seat: A, Records B handed to A, Address DMs to A reach A, Question open, asked by B
8. A to B writes its handover record: Handover A to B record written, Handover B to A record written, Team members: A; lead seat: A, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question open, asked by B

## LateAnswerRecorded breaks
The shortest path has 9 steps:
0. Handover A to B not started, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
1. the person approves A to B and it passes its check: Handover A to B approved and checked, Handover B to A not started, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
2. the person approves B to A and it passes its check: Handover A to B approved and checked, Handover B to A approved and checked, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
3. A to B moves the team seat: Handover A to B team seat moved, Handover B to A approved and checked, Team members: B; lead seat: B, Records no handover record, Address DMs to A reach A, Question open, asked by A
4. B to A moves the team seat: Handover A to B team seat moved, Handover B to A team seat moved, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
5. B to A moves the pending question: Handover A to B team seat moved, Handover B to A pending question moved, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by A
6. A to B moves the pending question: Handover A to B pending question moved, Handover B to A pending question moved, Team members: A; lead seat: A, Records no handover record, Address DMs to A reach A, Question open, asked by B
7. B to A writes its handover record: Handover A to B pending question moved, Handover B to A record written, Team members: A; lead seat: A, Records B handed to A, Address DMs to A reach A, Question open, asked by B
8. A to B writes its handover record: Handover A to B record written, Handover B to A record written, Team members: A; lead seat: A, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question open, asked by B
9. the peer's late answer arrives and is refused: Handover A to B record written, Handover B to A record written, Team members: A; lead seat: A, Records A handed to B, B handed to A, Address DMs to A loop back to A, Question late answer sent to A, not stored: the question is B's

## Rules that hold
AtMostOneHandoverPerSession, NoDeadlock
