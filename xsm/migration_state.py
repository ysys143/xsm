"""Idempotent domain steps of a profile transfer; journaled by migration.py."""
from __future__ import annotations

import copy
import glob
import hashlib
import os
import time

from . import handoff, migration, paths


def snapshot(source, target):
    from . import board, consent, decisions, handover, question_groups, questions as service, registry, teams
    team_records = copy.deepcopy(teams.teams_of(source))
    boards = []
    old, new = source.get('name') or source['ref'], target.get('name') or target['ref']
    for team in team_records:
        plans = []
        for item, heads in board.current(team['name']).items():
            suffix = handover._owned(item, old)
            if suffix is not None and len(heads) == 1 and old != new:
                plans.extend([{'item': 'owner/' + new + suffix, 'body': heads[0]['body'], 'parents': [heads[0]['id']]},
                              {'item': item, 'body': 'handed over to ' + new, 'parents': [heads[0]['id']]}])
        plans.append({'item': 'handover/' + old,
                      'body': 'Profile migration from %s to %s' % (source['ref'], target['ref']), 'parents': []})
        boards.append({'team': team['name'], 'nodes': plans})
    permissions = []
    for filename in migration._json_files(decisions.DIRECTORY):
        record = paths.read_json(filename)
        if record and record.get('owner') == decisions.owner(source) and record['status'] not in decisions.TERMINAL:
            permissions.append({'id': record['id'], 'tool': record['scope']['tool'],
                                'arguments': record['scope'].get('arguments', {}),
                                'question': record['question'], 'previous_status': record['status'],
                                'outcome_unknown': (record.get('application') or {}).get('phase') == 'started'})
    legacy = []
    matches = [r for r in registry.raw_records() if r.get('ref') == source['ref']]
    if len(matches) == 1:
        for filename in consent.pending_files(source['ref']):
            record = paths.read_json(filename)
            if record and record.get('session_id') == source['session_id']:
                legacy.append(copy.deepcopy(record))
    contacts = {}
    for folder in glob.glob(paths.path(handoff.DIRECTORY, '*')):
        if not os.path.isdir(folder):
            continue
        for filename in glob.glob(os.path.join(folder, '*.json')):
            record = paths.read_json(filename)
            if not record or not record.get('message'):
                continue
            sender = record['message'].get('sender')
            receiver = record.get('receiver')
            for mine, other in ((sender, receiver), (receiver, sender)):
                try:
                    if handoff._identity(mine) == migration.endpoint(source):
                        contact_key = hashlib.sha256(str(handoff._identity(other)).encode()).hexdigest()
                        contacts[contact_key] = other
                except (ValueError, AttributeError):
                    continue
    pending = [r['id'] for filename in migration._json_files(service.DIRECTORY)
               if (r := paths.read_json(filename)) and service._native(r['sender']) == service._native(source)
               and not any(reply.get('outcome') for reply in r.get('replies', []))]
    groups = [r['id'] for filename in migration._json_files(question_groups.DIRECTORY)
              if (r := paths.read_json(filename)) and r.get('sender') == service._native(source)]
    return {'teams': team_records, 'boards': boards, 'permissions': permissions,
            'questions': pending, 'question_groups': groups,
            'history': [{'id': r['id'], 'digest': r['digest'], 'status': r['status']}
                        for r in handoff.records(source)],
            'legacy_consent_history': legacy, 'contacts': list(contacts.values())}


def messages(record):
    from . import inbox, receive, registry
    with registry.lock_records([record['source'], record['target']]):
        for item in inbox.legacy_items(record['source']['session_id']):
            if item.get('receiver') == migration.endpoint(record['source']) or (
                    item.get('codex_home') and os.path.realpath(item['codex_home']) == record['source']['home']):
                if handoff.status(record['source'], item['id']).get('moved_to'):
                    continue
                receive._import_handoff(record['source'], item)
        return handoff.transfer(record['source'], record['target'], record['id'])


def verify(record):
    for original in handoff.records(record['source']):
        if original['status'] == 'acknowledged' or original.get('moved_to') != migration.endpoint(record['target']):
            if original['status'] != 'acknowledged' and not original.get('moved_to'):
                raise migration.MigrationError('pending original was not transferred; source stays fenced')
            continue
        successor = handoff.status(record['target'], original['id'])
        if successor.get('digest') != original['digest'] or not migration.proves_copy(successor, record['target']):
            raise migration.MigrationError('successor copy is missing or different; original retained')


def boards(record):
    from . import board, doc
    result = []
    for plan in record['snapshot']['boards']:
        path = board.path(plan['team'])
        for node in plan['nodes']:
            mark = '[xsm migration %s:%s]' % (record['id'], hashlib.sha256(node['item'].encode()).hexdigest()[:12])
            known = [n for n in doc.read(path) if n['body'].endswith(mark)]
            if known:
                if len(known) != 1 or doc.node_digest(known[0]) != known[0]['id']:
                    raise migration.MigrationError('migration board node conflicts; original retained')
                result.append(known[0]['id'])
                continue
            node = doc.add(path, board.author(record['source']), node['body'] + '\n\n' + mark,
                           ['update'], node['parents'], item=node['item'])
            result.append(node['id'])
        board.render(plan['team'])
    return result


def teams(record):
    from . import teams as service
    result = []
    source, target = record['source'], record['target']
    member = service.member_of(target)
    for original in record['snapshot']['teams']:
        with service._locked(original['name']) as filename:
            current = paths.read_json(filename)
            marker = 'profile-migration:' + record['id']
            if not any(entry.get('approval') == marker for entry in current.get('log', [])):
                if not service.is_member(current, source):
                    raise migration.MigrationError('team membership changed during migration')
                was_lead = service.is_lead(current, source)
                current['members'] = [m for m in current['members'] if not service.matches(m, source)]
                if not any(service._same(m, member) for m in current['members']):
                    current['members'].append(member)
                if was_lead:
                    current['lead'] = member
                service._log(current, 'handover', source, member, marker)
                paths.write_json(filename, current)
            result.append(original['name'])
    return result


def questions(record):
    from . import handover, questions as service
    handover._questions(record['source'], record['target'])
    handover._groups(record['source'], record['target'])
    completed = []
    for ident in record['snapshot']['questions']:
        current = paths.read_json(service._filename(ident))
        if not current:
            raise migration.MigrationError('a pending question disappeared; inspect before resuming')
        if service._native(current['sender']) != service._native(record['target']):
            if any(reply.get('outcome') for reply in current.get('replies', [])):
                completed.append(ident)
            else:
                raise migration.MigrationError('a pending question belongs to another actor')
    return {'questions': record['snapshot']['questions'], 'groups': record['snapshot']['question_groups'],
            'completed_during_transfer': completed}


def permissions(record):
    from . import consent, decisions
    source = record['source']
    for item in record['snapshot']['permissions']:
        current = decisions.read(item['id'])
        if current and not item['outcome_unknown'] and current['status'] not in ('applied', 'cancelled', 'expired', 'denied'):
            decisions.supersede(item['id'])
        consent.cancel_bound_requests(source, item['id'])
    for item in record['snapshot']['legacy_consent_history']:
        consent.drop_request(source, item['ask_id'])
    return {'fresh_answers_required': sum(not item['outcome_unknown'] for item in record['snapshot']['permissions']),
            'unresolved_outcomes': sum(item['outcome_unknown'] for item in record['snapshot']['permissions']),
            'legacy_requests': len(record['snapshot']['legacy_consent_history'])}


def links(record):
    from . import delegation, registry, workers
    source, target = record['source'], record['target']
    moved = []
    for filename in migration._json_files('worker-links'):
        link = paths.read_json(filename)
        if not link or link.get('migrated_to'):
            continue
        if migration.endpoint(link['parent']) == migration.endpoint(source):
            link['parent'] = {k: target.get(k) for k in link['parent']}
            link['migration'] = record['id']
            paths.write_json(filename, link)
            moved.append(link['child']['ref'])
        if migration.endpoint(link['child']) == migration.endpoint(source):
            new = copy.deepcopy(link)
            new['child'] = {k: target.get(k) for k in link['child']}
            new['migration'] = record['id']
            paths.write_json(paths.path('worker-links', delegation.key(target) + '.json'), new)
            link['migrated_to'] = delegation.key(target)
            paths.write_json(filename, link)
    for filename in migration._json_files('worker-project-requests'):
        request = paths.read_json(filename)
        if not request or request.get('parent') != source['ref'] or request.get('migrated_to'):
            continue
        child = next((r for r in registry.raw_records()
                      if r.get('ref') == request['worker']), None)
        if not child:
            continue
        # Predecessor request files predate an explicit leaving field. New
        # requests store it; older records are matched to their original key.
        for leaving in (False, True):
            old = delegation.request_id(child, source, request['project'], leaving)
            if old == request['id']:
                new_id = delegation.request_id(child, target, request['project'], leaving)
                new = dict(request, id=new_id, parent=target['ref'], migration=record['id'],
                           original_request=request['id'])
                paths.write_json(paths.path('worker-project-requests', new_id + '.json'), new)
                request['migrated_to'] = new_id
                paths.write_json(filename, request)
                break
    for worker in workers.all_workers():
        if worker.get('parent_ref') == source['ref']:
            worker.update(parent_ref=target['ref'], parent=target['session_id'], migration=record['id'])
            workers.save(worker)
    return moved


def held(record):
    result = []
    for filename in migration._json_files(paths.HELD):
        item = paths.read_json(filename)
        if not item or item.get('receiver_ref') != record['source']['ref']:
            continue
        if item.get('receiver_identity') and item['receiver_identity'] != migration.endpoint(record['source']):
            continue
        item.setdefault('original_receiver', migration.endpoint(record['source']))
        item.update(receiver_ref=record['target']['ref'], receiver=record['target'].get('name'),
                    receiver_identity=migration.endpoint(record['target']), migration=record['id'])
        paths.write_json(filename, item)
        result.append(os.path.basename(filename))
    return result


STEPS = [('messages', messages), ('boards', boards), ('teams', teams), ('questions', questions),
         ('permissions', permissions), ('links', links), ('held', held)]


def notify(record):
    from . import handover, identity, registry, send, team_sync, teams as service
    current = migration.retirement(record['source'])
    if not current or current['id'] != record['id'] or migration.active_error(record['target']):
        return  # A superseding transfer must not emit an obsolete address notice.
    for contact in record['snapshot']['contacts']:
        if not contact.get('home'):
            continue
        if migration.endpoint(contact) in (migration.endpoint(record['source']), migration.endpoint(record['target'])):
            continue
        ident = migration.key(contact)
        if ident in record['notices']:
            continue
        current = registry.by_session(contact['runtime'], contact['session_id'], home=contact['home'])
        if not current:
            record['notices'][ident] = {'status': 'unavailable'}
        else:
            result = send.send(identity.address(current),
                'XSM profile migration %s: session [%s] moved to [%s]. Old addresses forward until %s.' %
                (record['id'], record['source']['ref'], record['target']['ref'],
                 time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(record['forward_until']))),
                sender=record['target'], kind='note', wake=False,
                msg_id='migration-' + record['id'][:24] + '-' + ident[:24])
            record['notices'][ident] = {'status': result.status, 'id': result.msg_id, 'reason': result.reason}
        migration._persist(record)
    if not record.get('published'):
        from . import board, board_sync, doc
        moved = [{'record': service.require(t['name'])} for t in record['snapshot']['teams']]
        notes = []
        for team in moved:
            notes += team_sync.publish(team['record'])
            nodes = [node for node in doc.read(board.path(team['record']['name'])) if node['id'] in record['steps']['boards']]
            notes += board_sync.publish(team['record'], nodes)
        remote_contacts = [contact for contact in record['snapshot']['contacts'] if contact.get('machine') and not contact.get('home')]
        publication = moved + ([{'record': {'members': remote_contacts}}] if remote_contacts else [])
        notes += handover._publish({'from_identity': migration.endpoint(record['source']),
            'to_identity': migration.endpoint(record['target'])}, publication)
        record['notes'] = notes
        record['published'] = not notes
        migration._persist(record)


def view(record, since=None):
    from . import decisions, identity, ledger, network_identity
    messages = []
    history = {item['id']: item for item in record['snapshot']['history']}
    retained = set(history) | set(record['steps'].get('messages', []))
    originals = {r['id']: r for r in handoff.records(record['source']) if r['id'] in retained}
    for current in handoff.records(record['target']):
        if current['id'] in retained or record['id'] in current['message'].get('profile_forwarding', {}).get('ids', []):
            originals.setdefault(current['id'], current)
    for original in sorted(originals.values(), key=lambda r: (r['stored_at'], r['id'])):
        if since is not None and original['stored_at'] < since:
            continue
        if original['id'] in history and original['digest'] != history[original['id']]['digest']:
            raise migration.MigrationError('historical original changed; inspect retained state')
        moved = handoff.status(record['target'], original['id'])
        messages.append({'id': original['id'], 'body': original['message']['body'],
                         'sender': identity.address(original['message']['sender']) if original['message']['sender'].get('home')
                                   else network_identity.target(original['message']['sender']),
                         'original_status': history[original['id']]['status'] if original['id'] in history else None,
                         'successor_status': moved['status'],
                         'original_target': identity.address(original['message']['target']),
                         'addressed_via': identity.address(original['message']['profile_forwarding']['source'])
                                          if original['message'].get('profile_forwarding') else None,
                         'processing_history': [hop.get('previous_state', 'unknown') for hop in original.get('migration_history', [])],
                         'stored_at': original['stored_at'], 'delivery': ledger.evidence_of(original['id'])})
    permissions = []
    for item in record['snapshot']['permissions']:
        current = decisions.read(item['id'])
        phase = (current.get('application') or {}).get('phase') if current else None
        action = ('wait-for-migration' if record['status'] != 'committed' else
                  'inspect-outcome' if phase == 'started' else
                  'effect-recorded' if phase == 'completed' else 'fresh-answer-required')
        permissions.append(dict(item, action=action, current_status=current['status'] if current else 'unknown'))
    return {'id': record['id'], 'status': record['status'], 'created_at': record['created_at'],
            'committed_at': record.get('committed_at'), 'forward_until': record.get('forward_until'),
            'source': identity.address(record['source']), 'target': identity.address(record['target']),
            'steps': record['steps'], 'messages': messages,
            'permissions': permissions,
            'legacy_permissions': [{k: item.get(k) for k in ('ask_id', 'verb', 'target', 'here')}
                                   for item in record['snapshot']['legacy_consent_history']],
            'notices': record['notices'], 'notes': record['notes']}
