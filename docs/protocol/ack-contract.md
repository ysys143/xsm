# Explicit acknowledgement results

`xsm_ack` consumes only claims whose token, conversation, owner and participation
generation match. Its successful [result schema](ack-result.schema.json) requires
`acked`, an ordered array of canonical message IDs, and `inbox_pending`. The IDs
are not claim tokens or native platform message IDs. A successful operation may
also include the existing pending diagnostics and notice.

`inbox_pending: null` means the pending count could not be fully determined;
`inbox_pending_known` and diagnostics preserve what the pending scan could
observe. Zero and unknown are distinct. ACK does not passively read another
message or introduce an `incoming` claim packet.

A repeated valid token is idempotent. If supplied twice, its ID can occur twice
in `acked`, in input order. Consumers must not infer two distinct messages from
two identical IDs. No uniqueness constraint is imposed on this result array.

A token batch is processed in order and is not transactional. If an invalid,
expired or foreign token follows a valid one, the operation can return an error
after the earlier acknowledgement has durably committed. The error has no
successful `acked` array and does not imply rollback. Recover known original
IDs with targeted `xsm_inbox(message_ids=[...])`, then ACK the returned current
owned tokens after reading. Do not rerun the task because an ACK response was
lost. The same still-valid token may also be retried idempotently.

This contract distinguishes consumption from storage, notification, native queue
admission, replies and task outcomes. A successful ACK is not task success. It
does not grant a permission or convert quoted peer text into a user answer.

The development schema checker validates examples, rejects malformed results,
and validates captured `operation=xsm_ack` success frames. Error-frame validation
remains in the common output schema. This covers one operation family; other
operation result contracts and complete native certification remain unfinished.
