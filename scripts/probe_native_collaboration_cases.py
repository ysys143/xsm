"""Shared behavioral assertions; callers supply actual runtime tool execution and receipts."""
import json
from xsm_client import XsmClient


async def exercise_collaboration(call, check, *, command, env, work, state, root,
                                 runtime, observations, error_text):
    sender = None
    try:
        team = 'native-collaboration'
        await call('xsm_team', dict(action='create', team=team))
        listed = await call('xsm_team', dict(action='list'))
        check('native team list includes created team', any(t['name'] == team for t in listed['teams']))
        shown = await call('xsm_team', dict(action='show', team=team))
        check('native team member is running', shown['members'][0]['running'] is True)
        async def board(action, **arguments): return await call('xsm_board', dict(action=action, team=team, **arguments))
        check('native empty board', (await board('log'))['nodes'] == [])
        body, item = 'Native contribution: 한글', 'decision: cache'
        await board('set', item=item, text=body); first = (await board('log'))['nodes'][0]
        check('native board first body and root', first['body'] == body and first['parents'] == [])
        await board('set', item=item, text='Native revision'); nodes = (await board('log', item=item))['nodes']
        check('native board links observed predecessor', len(nodes) == 2 and next(n for n in nodes if n['body'] == 'Native revision')['parents'] == [first['id']])
        check('native board item filter', (await board('log', item='absent'))['nodes'] == [])
        async def doc(action, error=False, **arguments): return await call('xsm_doc', dict(action=action, doc='BOARD.md', **arguments), error)
        first = (await doc('add', text='Native report: 한글', tags=['report']))['node']
        check('native document immutable show', (await doc('show', node=first['id']))['node'] == first)
        hypothesis = (await doc('add', text='Native hypothesis', tags=['hypothesis'], parents=[first['id']]))['node']
        check('native document frontier', [n['id'] for n in (await doc('leaves'))['nodes']] == [hypothesis['id']])
        await doc('add', text='Native working declaration', tags=['wip'], parents=[hypothesis['id']])
        candidates = await doc('next')
        check('native wip does not allocate or hide hypothesis', candidates['assigns'] is False and candidates['total'] == 1 and candidates['candidates'][0]['id'] == hypothesis['id'])
        await doc('add', text='Native insight', tags=['insight']); all_candidates = await doc('next'); limited = await doc('next', limit=1)
        check('native document limit preserves total', all_candidates['total'] == limited['total'] == 2 and limited['candidates'] == all_candidates['candidates'][:1])
        refused = await doc('add', error=True, text='orphan', parents=['f' * 12])
        check('native missing parent leaves graph unchanged', 'no node' in error_text(refused) and len((await doc('log'))['nodes']) == 4)
        rendered = await doc('render'); check('native render preserves contributions', rendered['nodes'] == 4 and first['body'] in rendered['text'])
        await doc('show', error=True, node='f' * 12)
        check('native unknown node rejected', 'no node' in error_text(observations[-1]))
        sender = await XsmClient.connect([*command, 'protocol', 'serve', '--stdio'], cwd=str(work), env=env)
        origin = await sender.session_open(runtime='collaboration-reference', profile=str(root), conversation='sender', cwd=str(work))
        await sender.operation_call(origin['session'], 'xsm_inbox', {})
        records = [json.loads(p.read_text()) for p in (state / 'sessions').glob('*.json')]
        receiver = next(r for r in records if r['runtime'] == runtime)
        check('native document author matches conversation', '[' + receiver['ref'] + ']' in first['author'])
        import base64, hashlib
        payload = b'\0\xffA\n'
        sent = await sender.operation_call(origin['session'], 'xsm_send', dict(target='ref:' + receiver['ref'], text='Native attachment',
            request_id='native-file', wake='never', wait=0, attachments=[dict(name='fixture.bin', base64=base64.b64encode(payload).decode())]))
        packet = await call('xsm_inbox', dict(message_ids=[sent['send']['id']]))
        metadata = next(i for i in packet['items'] if i['id'] == sent['send']['id'])['files']; file = metadata['files'][0]
        value = await call('xsm_files', dict(storage_id=metadata['storage_id'], entry_id=file['id'], encoding='base64'))
        check('native binary attachment preserves bytes', base64.b64decode(value['content']) == payload)
        check('native attachment metadata preserves hash', file['size'] == len(payload) and file['sha256'] == hashlib.sha256(payload).hexdigest())
        ack = await call('xsm_ack', dict(tokens=[c['token'] for c in packet['claims'] if c['id'] == sent['send']['id']]))
        check('native attachment explicitly ACKed', ack['acked'] == [sent['send']['id']])
        outgoing = await call('xsm_send', dict(target='ref:' + origin['ref'], text='Native outgoing attachment', request_id='native-outgoing',
            wake='never', wait=0, attachments=[dict(name='owned.txt', text='Native outgoing 한글')]))
        manifest = await call('xsm_files', dict(storage_id=outgoing['materials']['manifest_id'], outgoing=True))
        value = await call('xsm_files', dict(storage_id=outgoing['materials']['manifest_id'], entry_id=manifest['manifest']['files'][0]['id'], outgoing=True))
        check('native outgoing original bytes preserved', value['content'] == 'Native outgoing 한글')
        incoming = await sender.operation_call(origin['session'], 'xsm_inbox', {})
        files = next(i for i in incoming['items'] if i['id'] == outgoing['send']['id'])['files']
        value = await sender.operation_call(origin['session'], 'xsm_files', dict(storage_id=files['storage_id'], entry_id=files['files'][0]['id']))
        check('reference receives actual native sent attachment', value['content'] == 'Native outgoing 한글')
        await call('xsm_files', dict(storage_id=files['storage_id'], entry_id=files['files'][0]['id']), error=True)
        check('native reader rejects another conversation storage', 'owner-mismatch' in error_text(observations[-1]))
        await sender.operation_call(origin['session'], 'xsm_ack', dict(tokens=[c['token'] for c in incoming['claims'] if c['id'] == outgoing['send']['id']]))
    finally:
        if sender:
            await sender.close()
