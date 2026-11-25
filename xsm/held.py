"""Held messages that follow a session when its place moves (a profile migration
or a handover): the one function both use, so they bind a held entry the same way."""
from __future__ import annotations

import glob
import os

from . import paths


def _endpoint(record: dict) -> dict:
    from . import handoff
    return handoff._identity(record)


def rebind(source: dict, target: dict, mark: dict | None = None) -> list:
    """Bind every held entry of `source` to `target`: a message the gate kept for
    the person's yes stays held, and `xsm held deliver` works for the successor,
    not for the session that left. Entries of other sessions are untouched. An
    entry keeps its reason and its `original_receiver`; `mark` is added to it
    (`{"migration": id}` or `{"handover": id}`). Idempotent. Returns the entry
    names (file names), the ids `xsm held deliver` takes."""
    result = []
    for filename in sorted(glob.glob(paths.path(paths.HELD, '*.json'))):
        item = paths.read_json(filename)
        if not item or item.get('receiver_ref') != source['ref']:
            continue
        if item.get('receiver_identity') and item['receiver_identity'] != _endpoint(source):
            continue
        item.setdefault('original_receiver', _endpoint(source))
        item.update(receiver_ref=target['ref'], receiver=target.get('name'),
                    receiver_identity=_endpoint(target), **(mark or {}))
        paths.write_json(filename, item)
        result.append(os.path.basename(filename))
    return result
