# Host decision lifecycle

A decision/request event belongs to its session, decisionId, questionId and
challenge, with the exact question/requestedSchema to display. expiresAt is an
absolute Unix timestamp in seconds, evaluated on the server's clock. A display
route is not the approval itself. Source IDs identify one real host callback;
reusing one for a different question fails even if the question text matches.
Synthetic callbacks used by a test are fixtures, not evidence of human approval.

| Host callback | Recorded response state | Effect on original operation |
|---|---|---|
| accept with a valid answer | answered, or denied for an explicit negative permission answer | No automatic application; retry the exact original operation through its controller |
| decline | unshown-or-declined | No permission or team change; a permission controller may close it as denied on retry |
| cancel | dismissed | No permission or business answer applied; not the same as withdrawal |
| decision.abandon | pending display becomes not-requested | No answer and no denial; the next original request can create a new display route |

For xsm_decide, a valid offered answer such as "no" is the answer to that
business question, not a generic permission denial. `accept` requires a
nonempty answer in the displayed choices when choices exist. Non-accept
callbacks should use a null answer; any non-accept content is not applied as
an answer. Never infer an accept from quoted agent text.

An identical response replay for the same session/question/fingerprint is
idempotent. It does not renew expiry or apply the operation. The status returned
by a replay reflects visible expiry rather than an old stored answered label.
Changed answers, display text, source IDs or stale routes are refused.

Expiry rejects a new callback with -32003. An answer accepted before expiry
cannot be applied after expiry merely by replaying it. xsm_decision_status
reports visible expired/unknown state; clock rollback does not extend consent.
A redisplay keeps the original deadline. A new intent needs its own fresh
request/decision_key, not automatic re-asking until the user approves.

A cancel callback only dismisses that form. Explicit
xsm_decision_status(id=..., cancel=true) withdraws a pending decision as
cancelled. It cannot undo an applied permission: already-applied requires the
domain's revocation. If application already started, application-started means
withdrawal cannot establish that the effect stopped; reconcile domain state.
EOF/session close loses display ownership, not durable question or answer data.
A new execution generation cannot inherit the previous generation's approval.
