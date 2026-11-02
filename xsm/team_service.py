"""Transport-neutral team effects. Frontends supply authenticated callers and user decisions."""
from __future__ import annotations

from . import probe, resolve, team_sync, teams


class DecisionRefused(teams.TeamError):
    """A trusted frontend declined or could not collect the required user decision."""


def execute(me, arguments, *, authorize=None):
    action = arguments.get('action')
    if action == 'list':
        teams.adopt_pairs()
        return {'action': action, 'teams': teams.all_teams(), 'sync_notes': []}
    if not me:
        raise teams.TeamError('this session is not registered')
    name = (arguments.get('team') or '').strip()
    if not name:
        raise teams.TeamError("team: the team's name")
    if action == 'create':
        return {'action': action, 'team': teams.create(me, name), 'sync_notes': []}
    team = teams.require(name)
    if action == 'show':
        return {'action': action, 'team': team, 'sync_notes': []}
    if action in ('mute', 'unmute'):
        if not teams.is_member(team, me):
            raise teams.TeamError('you are not in team %s' % team['name'])
        teams.mute(team['name'], me, on=action == 'mute')
        return {'action': action, 'team': team, 'sync_notes': []}
    if action == 'leave':
        team = teams.remove(me, name, teams.member_of(me), None)
        return {'action': action, 'team': team, 'sync_notes': team_sync.publish(team)}
    if action not in ('add', 'remove', 'lead'):
        raise teams.TeamError('unknown action %r' % action)
    word = (arguments.get('member') or '').strip()
    if not word:
        raise teams.TeamError('member: the session to %s' % action)

    def approval(subject):
        if authorize is None:
            raise DecisionRefused('this team change requires your user approval')
        source = authorize(action, team, subject)
        if not isinstance(source, str) or not source.strip():
            raise DecisionRefused('this team change requires your user approval')
        return source

    if action == 'add':
        with probe.quick():
            found = resolve.resolve(word, caller=me) if word.startswith(('net:', 'candidate:')) else resolve.resolve(word)
        if not found.ok:
            raise teams.TeamError(found.reason)
        target = found.record
        source = approval(target) if teams.add_rule(me, team, target) == 'user' else 'lead'
        team = teams.add(me, name, target, source)
        member = teams.member_of(target)
    else:
        member = teams.find_member(team, word)
        if action == 'remove':
            source = None if teams.matches(member, me) or teams.is_lead(team, me) else approval(member)
            team = teams.remove(me, name, member, source)
        else:
            source = approval(member)
            team = teams.set_lead(me, name, member, source)
    return {'action': action, 'team': team, 'member': member, 'approval': source,
            'sync_notes': team_sync.publish(team)}
