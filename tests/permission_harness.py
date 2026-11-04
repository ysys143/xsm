"""MCP dispatch plus synthetic native completion events; no model or human UI."""
import io
import json
from datetime import datetime, timezone
from pathlib import Path


def invoke(me, name, arguments, reply=None, client=None):
    from xsm import mcp
    initialization = {'protocolVersion': '2025-06-18',
                      'capabilities': {} if reply is None else {'elicitation': {}}}
    if client:
        initialization['clientInfo'] = {'name': client}
    messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': initialization},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                 'params': {'name': name, 'arguments': dict(arguments)}}]
    if reply is not None:
        messages.append(dict({'jsonrpc': '2.0', 'id': 'xsm-1'}, **reply))
    stream = io.StringIO()
    server = mcp.Server(io.StringIO(''.join(json.dumps(row) + '\n' for row in messages)), stream)
    server.session = lambda: dict(me)
    server.serve()
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    return next(row for row in rows if row.get('id') == 2)['result'], rows


def pending(me, text):
    from xsm import decisions
    records = [decisions.read(row['id']) for row in decisions.public_status(me)['decisions']]
    matches = [record for record in records if record.get('native_question')
               and record['native_question'] in text]
    if len(matches) != 1:
        raise AssertionError('expected exactly one identity-bound displayed question: ' + text)
    return matches[0]


def answer(me, record, choice, request=None, timestamp=None):
    from xsm import consent
    request = request or 'fixture-native-' + record['id']
    if me.get('runtime') == 'codex':
        directory = Path(me['home']) / 'sessions' / '2026' / '11' / '05'
        directory.mkdir(parents=True, exist_ok=True)
        filename = directory / ('rollout-fixture-' + me['session_id'] + '.jsonl')
        rows = []
        if not filename.exists():
            rows.append({'type': 'session_meta', 'payload': {'id': me['session_id']}})
        reply = '<send_user_message_question_reply>' + json.dumps([{
            'questionItemId': request, 'question': record['native_question'], 'answer': choice,
        }]) + '</send_user_message_question_reply>'
        rows.append({'type': 'response_item', 'timestamp': timestamp or datetime.now(timezone.utc).isoformat(),
                     'payload': {'type': 'message', 'role': 'user',
                                 'content': [{'type': 'input_text', 'text': reply}]}})
        with filename.open('a') as stream:
            for row in rows:
                stream.write(json.dumps(row) + '\n')
        return
    consent.record(me, {'hook_event_name': 'PostToolUse', 'tool_name': 'AskUserQuestion',
                        'tool_use_id': request,
                        'tool_response': {'answers': {record['native_question']: choice}}})
