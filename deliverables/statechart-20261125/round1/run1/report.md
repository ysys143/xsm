# XsmHandover

TLC reached 318 states and 610 steps. The chart draws 27 states and 28 arrows.
The view hides 74 steps, so the chart does not draw them.
The step the person approves the handover changes Answer and Handover at the same time.
The step unread DMs go into the letter changes DM and Handover, or DM, Answer and Handover, or Answer and Handover, at the same time.
The step B reads the letter changes DM and Handover at the same time.

## AnswerRecorded breaks
The shortest path has 4 steps:
0. DM DM waiting at A, Wait A waits, Answer No answer yet, Handover A holds its place
1. P answers: DM DM waiting at A, Wait A waits, Answer Answer waiting at A, Handover A holds its place
2. the wait times out: DM DM waiting at A, Wait Wait ended: timeout, Answer Answer waiting at A, Handover A holds its place
3. the person approves the handover: DM DM waiting at A, Wait Wait ended: timeout, Answer Answer waiting at A, Handover Handing over: questions moved
4. unread DMs go into the letter: DM DM in the letter, Wait Wait ended: timeout, Answer Answer only in the letter, question open, Handover Handing over: unread DMs moved

## HeldStaysHeld breaks
The shortest path has 6 steps:
0. DM DM waiting at A, Wait A waits, Answer No answer yet, Handover A holds its place
1. A's gate refuses the DM: DM DM held by A's gate, Wait A waits, Answer No answer yet, Handover A holds its place
2. the wait times out: DM DM held by A's gate, Wait Wait ended: timeout, Answer No answer yet, Handover A holds its place
3. the person approves the handover: DM DM held by A's gate, Wait Wait ended: timeout, Answer No answer yet, question is B's, Handover Handing over: questions moved
4. unread DMs go into the letter: DM Held DM in the letter, Wait Wait ended: timeout, Answer No answer yet, question is B's, Handover Handing over: unread DMs moved
5. the handover is recorded: DM Held DM in the letter, Wait Wait ended: timeout, Answer No answer yet, question is B's, Handover B holds A's place
6. B reads the letter: DM Held DM read by B, Wait Wait ended: timeout, Answer No answer yet, question is B's, Handover B read the letter

## Rules that hold
AckedOnce, WaitHonest, OneHolder, NoDeadlock
