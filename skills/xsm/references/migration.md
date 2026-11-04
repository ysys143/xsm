# Continuing a copied conversation in another profile

Use this when the user copied the native conversation to a different config
home and wants this copy to take over its xsm work. This feature is available
in 0.6.0; update both sessions before transferring.

In the new copy, run `xsm migrate ref:<old-ref>`, or call `xsm_migrate` with
`source: "ref:<old-ref>"`. The target is always this conversation. Both copies
must have the same runtime, native conversation ID and working folder. A
matching conversation ID alone does not transfer anything.

The permission question identifies both profiles and the effect. Follow
[permissions](permissions.md): keep the same operation and arguments after the
native answer; retry that MCP operation to recover its verified answer. Never
reuse a permission answer from the old profile. A denied transfer changes nothing.
The client can show and complete its form while the model waits on the tool.
Report the receipt; a successful tool return does not prove no form was shown.

After commit, the original cannot register, send, claim or ACK work. Old names,
refs and exact P2P endpoints forward for **24 hours from commit**. Expiry does
not revive the original. Reclaiming the place needs a separate user decision.
Normal `handover` remains the path for a different conversation and does not
retire its source.

Before continuing, run `xsm migrate` without a source, or `xsm_migrate` without
arguments. Read its catch-up list: original message IDs/bodies, previous claim
and delivery state, transferred questions, held messages, permission requests,
and failed sends. Use `since` (CLI `--since`, Unix timestamp) for a period view.
Claim and ACK through the normal inbox path; a transfer itself is never an ACK.
Held messages remain held. Native transcript/queue contents are not removed.

Pending human permissions need fresh questions in this profile. An operation
already started in the original may have an unknown outcome: inspect its
`inspect-outcome` entry before repeating it. The status does not certify that
the copied transcript contains every message.

If interrupted, retry the same source and inspect the same migration ID.
Incomplete state is not completion. Receipt notices distinguish stored,
unconfirmed and failed delivery; retry does not rerun completed steps. A
remote machine that missed publication has not acknowledged the successor.
`xsm doctor` shows profile copies, generations, retirement, forwarding expiry
and known successor state. Missing registration is reported as unknown.
