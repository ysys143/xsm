# XsmConcurrentHandover

TLC reached 17 states and 22 steps. The chart draws 25 states and 19 arrows.
The view hides 4 steps, so the chart does not draw them.
The step A to B writes its handover record changes Handover A to B, Records and Address at the same time.
The step B to A writes its handover record changes Handover B to A and Records at the same time.
The step A to B moves the team seat changes Handover A to B and Team at the same time.
The step A to B moves the pending question changes Handover A to B and Question at the same time.

## Rules that hold
AtMostOneHandoverPerSession, AddressLeadsAway, HandedOverHoldsNoPlace, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded, NoDeadlock
