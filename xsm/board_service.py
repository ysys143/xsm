"""Transport-neutral team board actions; human answers use the decision controller."""
from __future__ import annotations

from . import board, board_notice, board_sync


def execute(me, arguments):
    action, name = arguments.get('action'), arguments.get('team') or ''
    if action == 'show':
        return {'action': action, 'text': board.show(me, name)}
    if action == 'log':
        return {'action': action, 'nodes': board.log(me, name, arguments.get('item'))}
    if action == 'set':
        node = board.set_item(me, name, arguments.get('item') or '', arguments.get('text') or '',
                              tag=arguments.get('tag'))
        return {'action': action, 'node': node, 'sync_notes': node.get('sync_notes') or []}
    if action in ('decisions', 'mute', 'unmute', 'sync'):
        team = board._require_member(me, name)
        if action == 'decisions':
            # Authorization must not mark unrelated board nodes as observed.
            return {'action': action, 'decisions': board.decisions(team['name'])}
        if action == 'sync':
            return {'action': action, 'team': team, 'sync_notes': board_sync.sync(team)}
        board_notice.mute(me, team['name'], on=action == 'mute')
        return {'action': action, 'team': team}
    raise board.BoardError('action is show, set, log, decisions, mute, unmute or sync')
