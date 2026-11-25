# XsmRemote

TLC reached 11 states and 17 steps. The chart draws 8 states and 12 arrows.
The chart does not draw 2 steps that stay in one chart state.
The view hides 1 steps, so the chart does not draw them.

## ViewsAgree breaks
The shortest path has 2 steps:
0. A holds its place.R waits for an answer
1. the person approves; M1 tells R's machine: A handed over to B.R waits for the handover news; R waits for an answer
2. the handover news is lost on the way (no retry): A handed over to B.R will never accept its answer; R waits for an answer

## AnswerRecorded breaks
The shortest path has 4 steps:
0. A holds its place.R waits for an answer
1. the person approves; M1 tells R's machine: A handed over to B.R waits for the handover news; R waits for an answer
2. B answers R: A handed over to B.R waits for the handover news; R waits for an answer
3. R refuses the answer: A handed over to B.R waits for the handover news; answer refused
4. the handover news is lost on the way (no retry): A handed over to B.R will never accept its answer; answer refused

## Rules that hold
StrangerNeverRecorded, QuestionAnswerable, NoDeadlock
