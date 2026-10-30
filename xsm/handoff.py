"""Recoverable local handoff ownership, independent of transport receipts.

Message schema: id, sender (full native record), body; optional kind, reply_to,
outcome, scope, priority, attachments, content and delivery_state. Store the
canonical original before creating any legacy inbox export. The only final
consumption evidence is ack, never stdout flush or an export disappearing.

The user-approved default claim lease is 120 seconds. Explicit fixture leases
override it; retention=None preserves indefinitely. Recovery is explicit and never
removes originals, including acknowledged messages. Public adapters decide when
an authenticated runtime can acknowledge; this module does not infer it.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
import re
import time
import uuid

from . import envelope, paths

DIRECTORY = 'handoffs'
CLAIM_LEASE = 120  # D05 user approval; never a body-deletion or retention TTL.
DELIVERY_STATES = ('pending', 'delivered', 'held', 'offline', 'unknown', 'refused', 'error')
DELIVERY_ROUTES = ('native', 'mcp-inbox')


def _monotonic():
    # Python 3.9 on macOS gives time.monotonic() a per-process baseline;
    # a persisted lease must use the same POSIX clock in every reader process.
    return time.clock_gettime(time.CLOCK_MONOTONIC)


def _identity(record):
    if not isinstance(record, dict):
        raise ValueError('full native identity required')
    if record.get('home') is None and ('machine' in record or 'home_id' in record):
        from .network_identity import endpoint
        return endpoint(record)
    result = {key: record.get(key) for key in ('runtime', 'home', 'session_id')}
    if any(not isinstance(v, str) or not v.strip() for v in result.values()):
        raise ValueError('runtime, home and session_id required')
    result['home'] = os.path.realpath(os.path.expanduser(result['home']))
    return result


def _folder(receiver):
    endpoint = _identity(receiver)
    digest = hashlib.sha256(json.dumps(endpoint, sort_keys=True).encode('utf-8')).hexdigest()
    return paths.path(DIRECTORY, digest)


def _id(message_id):
    if not isinstance(message_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', message_id):
        raise ValueError('invalid message ID')
    return message_id


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ' must be finite seconds')
    if value < 0 or (positive and value == 0):
        raise ValueError(name + ' must be positive' if positive else name + ' must be nonnegative')
    return float(value)


def _owner(owner, generation):
    if not isinstance(owner, dict) or owner.get('type') not in ('native', 'legacy-export'):
        raise ValueError('owner requires type native or legacy-export')
    if not isinstance(owner.get('id'), str) or not owner['id'].strip():
        raise ValueError('owner ID required')
    if not isinstance(generation, str) or not generation.strip():
        raise ValueError('owner execution generation required')
    return {'type': owner['type'], 'id': owner['id']}, generation


@contextmanager
def _locked(receiver):
    folder = _folder(receiver)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(folder, '.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield folder
    finally:
        os.close(fd)


def _write(filename, record):
    paths.write_json(filename, record)
    # paths supplies atomic replacement; fsync makes a returned transition
    # durable before the adapter exports or deletes a transport duplicate.
    fd = os.open(filename, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(os.path.dirname(filename), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read(folder, message_id, receiver):
    filename = os.path.join(folder, _id(message_id) + '.json')
    if not os.path.exists(filename):
        return None
    record = paths.read_json(filename)
    if (not isinstance(record, dict) or record.get('version') != 1 or
            record.get('id') != message_id or record.get('receiver') != _identity(receiver)):
        raise ValueError('invalid handoff record; original retained')
    return record


def _records(folder, receiver):
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return []
    records = []
    for name in names:
        if not name.endswith('.json'):
            continue
        # Fail rather than overwrite/re-export corrupt ownership evidence.
        record = _read(folder, name[:-5], receiver)
        if record is not None:
            records.append(record)
    return sorted(records, key=lambda r: (r['stored_at'], r['id']))


def _expiry(record, now, retention=None):
    duration = record.get('retention') if retention is None else retention
    if duration is None:
        return 'unbounded'
    _number(duration, 'retention')
    if now < record['stored_at']:
        return 'unknown'
    return 'expired' if now >= record['stored_at'] + duration else 'active'


def _view(record, now=None, retention=None):
    result = copy.deepcopy(record)
    result['status'] = result.pop('state')
    result['expiry'] = _expiry(record, time.time() if now is None else now, retention)
    result['recoverable'] = result['status'] != 'acknowledged'
    return result


def store(receiver, message, *, retention=None):
    """Persist original and full canonical digest. Same ID conflicts refuse.

    Duplicate canonical content returns the original verbatim and never resets
    ownership. retention is explicit seconds; None means no automatic expiry.
    """
    endpoint = _identity(receiver)
    if not isinstance(message, dict) or not isinstance(message.get('body'), str):
        raise ValueError('message body and full sender required')
    message = copy.deepcopy(message)
    message_id = _id(message.get('id'))
    _identity(message.get('sender'))
    if message.get('target') is not None and _identity(message['target']) != endpoint:
        raise ValueError('message targets another native conversation')
    if retention is not None:
        retention = _number(retention, 'retention')
    delivery = message.get('delivery_state', 'pending')
    if delivery not in DELIVERY_STATES:
        raise ValueError('invalid delivery state')
    if message.get('outcome') not in (None,) + envelope.OUTCOMES:
        raise ValueError('invalid outcome')
    identity = envelope.request_identity(
        message_id, message['sender'], receiver, message['body'],
        kind=message.get('kind', 'note'), reply_to=message.get('reply_to'),
        outcome=message.get('outcome'), scope=message.get('scope'),
        priority=message.get('priority'), attachments=message.get('attachments'))
    digest = envelope.request_digest(identity)
    with _locked(receiver) as folder:
        original = _read(folder, message_id, receiver)
        if original is not None:
            if original['digest'] != digest:
                raise ValueError('same message ID has different content or endpoints')
            return _view(original)
        record = {'version': 1, 'id': message_id, 'receiver': endpoint,
                  'identity': identity, 'digest': digest, 'message': message,
                  'stored_at': time.time(), 'retention': retention, 'state': 'pending',
                  'delivery_state': delivery, 'outcome': message.get('outcome'), 'claim': None}
        _write(os.path.join(folder, message_id + '.json'), record)
        return _view(record)


def delivery(receiver, message_id, state, *, route=None):
    """Record transport state/route, never mutate the immutable request.

    Route is internal handoff metadata, not message wake/identity/digest. An
    omitted route preserves the prior route; an explicit new native attempt
    can replace a prior MCP-inbox route. ACK is never resurrected.
    """
    if state not in DELIVERY_STATES:
        raise ValueError('invalid delivery state')
    if route is not None and route not in DELIVERY_ROUTES:
        raise ValueError('invalid delivery route')
    with _locked(receiver) as folder:
        record = _read(folder, message_id, receiver)
        if record is None:
            return {'status': 'not-found'}
        # A concurrent confirmed reader is stronger evidence than a late
        # transport error. Never resurrect an acknowledged message on retry.
        if record['state'] != 'acknowledged':
            record['delivery_state'] = state
            if route is not None:
                record['delivery_route'] = route
            _write(os.path.join(folder, record['id'] + '.json'), record)
        return _view(record)


def old_p2p_copy_receipt(record, receipt, receiver):
    """Identify an unsupported-origin copy, not a canonical policy hold.

    Only eligibility for a fresh receive check is established here. Both raw
    records and status views are accepted; no admission, claim or ACK occurs.
    """
    if (record.get("state", record.get("status")) != "pending"
            or record.get("delivery_state") != "pending"
            or receipt.get("id") != record.get("id")
            or any(key in receipt for key in ("req_digest", "req_version", "body_sha", "from_ref"))):
        return False
    recipient = receipt.get("receiver") or {}
    if (not isinstance(recipient, dict) or not receiver.get("ref")
            or recipient.get("ref") != receiver.get("ref")
            or recipient.get("runtime") != receiver.get("runtime")):
        return False
    content = record.get("message", {}).get("content")
    if not isinstance(content, str):
        return False
    origin = envelope.parse(content).header.get("origin", "")
    return (origin.startswith("p2p:") and receipt.get("reason") ==
            "remote message from %s was not received by this machine's xsm" % origin)


def pending_ids(receiver, *, owner_alive=None):
    """Read-only snapshot of claimable or recoverable IDs for this endpoint.

    No mkdir/lock creation, recover, claim, ACK or lease writes. A subsequent
    consumer must recover/claim under its normal lock and recheck receive
    authorization. Unknown ownership is not dead; lease expiry follows recover.
    Corrupt/unreadable state propagates rather than opening a fallback.
    """
    folder = _folder(receiver)
    try:
        records = _records(folder, receiver)
    except (KeyError, TypeError) as exc:
        raise ValueError('invalid handoff record; original retained') from exc
    now, mono = time.time(), _monotonic()
    result = []
    for record in records:
        if (record.get('delivery_state') not in DELIVERY_STATES or
                record.get('state') not in ('pending', 'claimed', 'handoff-recorded', 'acknowledged')):
            raise ValueError('invalid handoff state; original retained')
        _number(record.get('stored_at'), 'stored_at')
        if record['delivery_state'] not in ('pending', 'delivered'):
            continue
        # Native gates may retain a pending original after rejecting its export.
        # Match inbox eligibility without rewriting records or reviving errors.
        from . import ledger
        receipt = ledger.receipt_of(record['id'])
        if (receipt and receipt.get('decision') in ('held', 'blocked') and
                not (str(receipt.get('reason') or '').startswith('traffic ') and
                     record['delivery_state'] == 'pending') and
                not old_p2p_copy_receipt(record, receipt, receiver)):
            continue
        if _expiry(record, now) in ('expired', 'unknown'):
            continue
        if record['state'] == 'pending':
            result.append(record['id'])
            continue
        if record['state'] not in ('claimed', 'handoff-recorded'):
            continue
        current = record.get('claim')
        if not isinstance(current, dict):
            raise ValueError('invalid claim; original retained')
        owner, generation = _owner(current.get('owner'), current.get('generation'))
        started = _number(current.get('started_mono'), 'claim started')
        deadline = _number(current.get('deadline_mono'), 'claim deadline')
        if deadline < started:
            raise ValueError('invalid claim deadline; original retained')
        alive = owner_alive(copy.deepcopy(owner), generation) if owner_alive is not None else None
        if alive is False or mono >= deadline:
            result.append(record['id'])
    return result


def traffic_admission(receiver, message_id, policy_key, evaluate, *, now=None):
    """Charge one logical message once; read-only polls do not consume quota.

    Failed admissions can be reevaluated after their recorded retry window.
    A changed policy invalidates the cache. This metadata never changes the
    immutable request or acknowledges consumption.
    """
    now=time.time() if now is None else now
    with _locked(receiver) as folder:
        record=_read(folder,message_id,receiver)
        if record is None:
            raise ValueError('canonical original required for traffic admission')
        cached=record.get('traffic_admission') or {}
        observation=cached.get('observation') or {}
        if cached.get('policy_key')==policy_key:
            if observation.get('allowed') is True and observation.get('status')!='unknown':
                return copy.deepcopy(observation)
            stamp,delay=observation.get('at'),observation.get('retry_after')
            if (isinstance(stamp,(int,float)) and isinstance(delay,(int,float)) and
                    stamp<=now<stamp+delay):
                return dict(observation,retry_after=stamp+delay-now)
        result=evaluate()
        record['traffic_admission']={'policy_key':policy_key,'observation':copy.deepcopy(result)}
        _write(os.path.join(folder,record['id']+'.json'),record)
        return result


def reply_copies(receiver, request_id):
    """Read matching immutable originals without claiming or acknowledging them."""
    copies=[]
    with _locked(receiver) as folder:
        for record in _records(folder,receiver):
            message=record['message']
            if message.get('kind')=='reply' and message.get('reply_to')==request_id and message.get('content'):
                copies.append({'id':record['id'],'content':message['content'],'receiver':record['receiver']})
    return copies


def claim(receiver, owner, generation, lease=CLAIM_LEASE, *, message_id=None):
    """Claim one oldest eligible original exclusively, or return empty.

    owner={type: native|legacy-export, id: reader ID}; generation is the reader's
    execution generation, not a session display name. Expired claims require an
    explicit recover call, not an implicit second consumer.
    """
    owner, generation = _owner(owner, generation)
    lease = _number(lease, 'lease', positive=True)
    with _locked(receiver) as folder:
        for record in _records(folder, receiver):
            if message_id is not None and record['id'] != _id(message_id):
                continue
            if (record['state'] != 'pending' or
                    record['delivery_state'] not in ('pending', 'delivered') or
                    _expiry(record, time.time()) in ('expired', 'unknown')):
                continue
            now = _monotonic()
            record.update(state='claimed', claim={
                'token': uuid.uuid4().hex, 'owner': owner, 'generation': generation,
                'started_mono': now, 'deadline_mono': now + lease,
                'started_at': time.time(), 'lease': lease, 'clock': 'CLOCK_MONOTONIC'})
            _write(os.path.join(folder, record['id'] + '.json'), record)
            return _view(record)
    return {'status': 'empty'}


def _transition(receiver, token, owner, generation, action, delivery_state=None):
    owner, generation = _owner(owner, generation)
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('invalid claim token')
    if delivery_state is not None and delivery_state not in DELIVERY_STATES:
        raise ValueError('invalid delivery state')
    with _locked(receiver) as folder:
        for record in _records(folder, receiver):
            current = record.get('claim') or {}
            if current.get('token') != token:
                continue
            if current.get('owner') != owner or current.get('generation') != generation:
                raise ValueError('claim belongs to another owner or generation')
            if record['state'] == 'acknowledged':
                if action != 'acknowledged':
                    raise ValueError('acknowledged message cannot be released or handed off')
                return _view(record)
            if record['state'] not in ('claimed', 'handoff-recorded'):
                raise ValueError('claim is no longer active')
            now = _monotonic()
            if now < current['started_mono'] or now >= current['deadline_mono']:
                raise ValueError('claim lease expired or clock is unknown; recover before retry')
            if action == 'pending':
                record['previous_claim'] = current
                record['claim'] = None
            record['state'] = action
            record[action + '_at'] = time.time()
            if delivery_state is not None:
                record['delivery_state'] = delivery_state
            _write(os.path.join(folder, record['id'] + '.json'), record)
            return _view(record)
    raise ValueError('claim token is not owned by this native endpoint')


def handoff(receiver, token, owner, generation):
    """Record an output attempt, not consumption; preserve the original."""
    return _transition(receiver, token, owner, generation, 'handoff-recorded')


def ack(receiver, token, owner, generation):
    """Explicit confirmed consumption. Same valid token ack is idempotent."""
    return _transition(receiver, token, owner, generation, 'acknowledged')


def release(receiver, token, owner, generation, *, delivery_state=None):
    """Return an unconfirmed claim after cancel/error; invalidate its token."""
    return _transition(receiver, token, owner, generation, 'pending', delivery_state)


def recover(receiver, *, owner_alive=None, retention=None):
    """Explicitly recover dead-owner or lease-expired claims; never delete.

    owner_alive(owner, generation) returns False only for proven dead owners,
    True for live, None for unknown. Unknown ownership alone never authorizes
    reclamation. Explicit lease expiry can reclaim a live slow reader; the old
    token then cannot ack. Backward clocks stay unknown, not expired.
    retention optionally classifies expiry for this recovery, without cleanup.
    """
    if retention is not None:
        _number(retention, 'retention')
    results = []
    with _locked(receiver) as folder:
        for record in _records(folder, receiver):
            current = record.get('claim')
            reason = None
            if current and record['state'] in ('claimed', 'handoff-recorded'):
                alive = owner_alive(copy.deepcopy(current['owner']), current['generation']) \
                    if owner_alive is not None else None
                now = _monotonic()
                if alive is False:
                    reason = 'owner-dead'
                elif now >= current['deadline_mono']:
                    reason = 'lease-expired'
                if reason:
                    record.update(state='pending', previous_claim=current, claim=None,
                                  recovered_at=time.time(), recovery_reason=reason)
                    _write(os.path.join(folder, record['id'] + '.json'), record)
            view = _view(record, retention=retention)
            if current and not reason and record['state'] in ('claimed', 'handoff-recorded'):
                view['recovery_reason'] = 'clock-unknown' if now < current['started_mono'] else 'owned'
            results.append(view)
    return results


def move_out(receiver, to):
    """Close every message not yet acknowledged here as moved to `to` (a
    handover, handover.py) and return their records. Nothing is deleted: the
    original stays, marked with where it went."""
    target = _identity(to)
    moved = []
    with _locked(receiver) as folder:
        for record in _records(folder, receiver):
            if record['state'] == 'acknowledged':
                continue
            moved.append(copy.deepcopy(record))
            record.update(state='acknowledged', claim=None, moved_to=target, moved_at=time.time())
            _write(os.path.join(folder, record['id'] + '.json'), record)
    return moved


def status(receiver, message_id):
    """Read only this endpoint's message. Other homes/CIDs see not-found."""
    record = _read(_folder(receiver), _id(message_id), receiver)
    return _view(record) if record is not None else {'status': 'not-found', 'id': message_id}
