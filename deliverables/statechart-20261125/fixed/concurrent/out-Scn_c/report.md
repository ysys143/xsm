# XsmConcurrentHandover

TLC reached 33 states and 38 steps. The chart draws 28 states and 26 arrows.
The view hides 5 steps, so the chart does not draw them.
The step A to B writes its handover record changes Handover A to B, Records and Address at the same time.
The step B to C writes its handover record changes Handover B to C and Records, or Handover B to C, Records and Address, at the same time.
The step B to C moves the team seat changes Handover B to C and Team at the same time.
The step A to B moves the team seat changes Handover A to B and Team at the same time.
The step B to C moves the pending question changes Handover B to C and Question at the same time.
The step A to B moves the pending question changes Handover A to B and Question at the same time.

## Rules that hold
AtMostOneHandoverPerSession, AddressLeadsAway, HandedOverHoldsNoPlace, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded, NoDeadlock
