# XsmRemote

TLC reached 29 states and 63 steps. The chart draws 9 states and 16 arrows.
The chart does not draw 24 steps that stay in one chart state.
The view hides 4 steps, so the chart does not draw them.

## ViewsAgree breaks
The shortest path has 3 steps:
0. A holds its place.R waits for an answer
1. the person approves; M1 tells R's machine: A handed over to B.R waits for the handover news; R waits for an answer
2. R's machine keeps the handover news: A handed over to B.R accepts its answer; R waits for an answer
3. B hands over to C; M1 has no reason to tell R's machine: A handed over to B, B to C.R will never accept its answer; R waits for an answer

## AnswerRecorded breaks
The shortest path has 4 steps:
0. A holds its place.R waits for an answer
1. the person approves; M1 tells R's machine: A handed over to B.R waits for the handover news; R waits for an answer
2. B hands over to C; M1 has no reason to tell R's machine: A handed over to B, B to C.R will never accept its answer; R waits for an answer
3. C answers R: A handed over to B, B to C.R will never accept its answer; R waits for an answer
4. R refuses the answer: A handed over to B, B to C.R will never accept its answer; answer refused

## Rules that hold
StrangerNeverRecorded, QuestionAnswerable, NoDeadlock
