---
type: llm
weight: 1
---

A good answer treats it as the user's decision, not the lead's: a scope change
goes through the lead to the user, who answers in the `xsm_decide` form, called
with the team (and an item such as `decision: cache`), so the answer is recorded
beside team core's board and the board item shows who decided. Members then
read it on the board (`xsm board show core`); they are not told the same thing
again by DM.

It is wrong if the lead records the decision as its own (writing it on the
board as decided without the user's answer), says a member's agreement is the
user's approval, or invents commands, tools or flags that are not xsm's.
