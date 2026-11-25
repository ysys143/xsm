# XsmConcurrentHandover

TLC reached 95 states and 122 steps. The chart draws 48 states and 49 arrows.
The view hides 17 steps, so the chart does not draw them.
The step A to B writes its handover record changes Handover A to B, Records and Address at the same time.
The step A to C writes its handover record changes Handover A to C, Records and Address at the same time.
The step B to A writes its handover record changes Handover B to A and Records at the same time.
The step B to C writes its handover record changes Handover B to C and Records, or Handover B to C, Records and Address, at the same time.
The step B to C moves the team seat changes Handover B to C and Team at the same time.
The step A to B moves the team seat changes Handover A to B and Team at the same time.
The step A to C moves the team seat changes Handover A to C and Team at the same time.
The step B to C moves the pending question changes Handover B to C and Question at the same time.
The step A to B moves the pending question changes Handover A to B and Question at the same time.
The step A to C moves the pending question changes Handover A to C and Question at the same time.

## Rules that hold
AtMostOneHandoverPerSession, AddressLeadsAway, HandedOverHoldsNoPlace, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded, NoDeadlock
