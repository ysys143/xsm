"""Document node operations shared by trusted CLI and model frontends."""
from __future__ import annotations

import os
from . import doc


def execute(me, arguments, *, author=None, base=None):
    args = dict(arguments)
    action = args.get('action')
    if action not in ('add', 'render', 'log', 'next', 'leaves', 'show'):
        raise doc.DocError('unsupported document action')
    path = args.get('doc')
    if not isinstance(path, str) or not path.strip():
        raise doc.DocError('document path is required')
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(base or (me or {}).get('cwd') or os.getcwd(), path)
    path = os.path.realpath(path)
    if action == 'add':
        if author is None:
            if not me:
                raise doc.DocError('registered conversation required')
            author = {'kind': 'agent', 'name': me.get('name'), 'alias': me.get('alias'),
                      'ref': me.get('ref'), 'runtime': me.get('runtime')}
        node = doc.add(path, author, args.get('text') or '', args.get('tags') or ['result'],
                       args.get('parents') or [],
                       approved=('verdict: %s' % author['verdict']) if author.get('via') == 'verdict' else None)
        return {'node': node}
    if action == 'render':
        text = doc.render(path)
        return {'text': text, 'nodes': len(doc.read(path))}
    if action == 'next':
        limit = args.get('limit', 0)
        if type(limit) is not int or limit < 0:
            raise doc.DocError('limit must be a nonnegative integer')
        nodes = doc.read(path)
        return dict(doc.next_json(path, limit, nodes=nodes), text=doc.next_text(path, limit, nodes=nodes))
    nodes = doc.read(path)
    if action == 'show':
        node = next((node for node in nodes if node['id'] == args.get('node')), None)
        if node is None:
            raise doc.DocError('no node %s' % args.get('node'))
        return {'node': node}
    if action == 'leaves':
        nodes = doc.leaves(nodes)
    return {'nodes': nodes}
