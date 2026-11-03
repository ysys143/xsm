"""Wire-level fault proxy for conformance tests; candidate is the actual stdio server."""
import json
from pathlib import Path
import subprocess
import queue
import threading
import sys

root = Path(__file__).resolve().parents[2]
fault = sys.argv[1]
command = [sys.executable, '-B', '-c',
           "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
           str(root), 'protocol', 'serve', '--stdio']
process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
first_token = None
pending_publication = None
seen_grant = False


replies = queue.Queue()
output_lock = threading.Lock()


def emit(value):
    with output_lock:
        print(json.dumps(value), flush=True)


def read_output():
    try:
        for line in process.stdout:
            value = json.loads(line)
            if 'id' not in value:
                emit(value)
            else:
                replies.put(value)
    finally:
        replies.put(None)


reader = threading.Thread(target=read_output, daemon=True)
reader.start()


def exchange(request, notifications=True):
    process.stdin.write(json.dumps(request) + '\n')
    process.stdin.flush()
    reply = replies.get(timeout=5)
    if reply is None:
        raise RuntimeError('candidate closed during proxy call')
    if reply.get('id') != request['id']:
        raise RuntimeError('candidate returned an unrelated response')
    return reply


try:
    for line in sys.stdin:
        request = json.loads(line)
        params = request.get('params', {})
        if fault == 'ignore-inbox-filter' and params.get('operation') == 'xsm_inbox':
            params.get('arguments', {}).pop('message_ids', None)
        reply = exchange(request)
        if fault == 'selection-auto-apply-publication' and request['method'] == 'decision.response' and pending_publication:
            saved, question_id = pending_publication
            if params.get('questionId') == question_id and params.get('answer') == 'allow' and reply.get('result', {}).get('status') == 'answered':
                exchange({'jsonrpc':'2.0','id':'fault-auto-publication','method':'operation.call','params':saved})
                pending_publication = None
        if request['method'] == 'operation.call':
            if fault == 'selection-auto-apply-publication' and params.get('operation') == 'xsm_publish' and reply.get('result', {}).get('status') == 'waiting-for-user':
                pending_publication = (params, reply['result']['question_id'])
            if fault == 'selection-stale-handshake' and params.get('operation') == 'xsm_connect' and params.get('arguments', {}).get('request_id') and reply.get('result', {}).get('handshake') == 'completed':
                reply['result']['handshake'] = 'pending'
            if params.get('operation') == 'xsm_question_status' and reply.get('result', {}).get('group'):
                value = reply['result']
                if fault == 'questions-foreign-internal' and value.get('status') == 'refused':
                    reply.pop('result')
                    reply['error'] = {'code': -32603, 'message': 'synthetic internal error'}
                if fault == 'questions-erases-acked-answer' and value.get('status') == 'replied' and value.get('claims') == []:
                    value['replies'] = []
            if params.get('operation') == 'xsm_team' and 'team_change' in reply.get('result', {}):
                if fault == 'team-missing-change': reply['result'].pop('team_change')
                if fault == 'team-empty-members': reply['result']['team_change']['members']=[]
            if params.get('operation') == 'xsm_board' and reply.get('result', {}).get('board', {}).get('action') == 'set':
                if fault == 'board-missing-change': reply['result'].pop('board')
                if fault == 'board-wrong-body': reply['result']['board']['node']['body']='unrelated contribution'
            if params.get('operation') == 'xsm_handover' and reply.get('result', {}).get('handover', {}).get('action') == 'hand_over':
                if fault == 'handover-missing-producer': reply['result'].pop('handover')
                if fault == 'handover-wrong-successor': reply['result']['handover']['transfer']['to_ref']='unrelated-successor'
            if params.get('operation') == 'xsm_doc_endorse' and 'endorsement' in reply.get('result', {}):
                if fault == 'endorsement-missing-producer': reply['result'].pop('endorsement')
                if fault == 'endorsement-wrong-parent': reply['result']['endorsement']['parent']='000000000000'
            if params.get('operation') in ('xsm_link', 'xsm_join', 'xsm_reach') and 'scope' in reply.get('result', {}):
                value = reply['result']['scope']
                if fault == 'scope-missing-producer':
                    reply['result'].pop('scope')
                if fault == 'scope-wrong-root':
                    value['root'] = '/unrelated-root'
                if fault == 'scope-stale-active' and value['active'] is False:
                    value['active'] = True
            if params.get('operation') == 'xsm_decide' and 'decision' in reply.get('result', {}):
                if fault == 'decision-missing-producer':
                    reply['result'].pop('decision')
                if fault == 'decision-recorded-flipped':
                    value = reply['result']['decision']
                    value['recorded'] = not value['recorded']
            if params.get('operation') == 'xsm_approve' and 'approval' in reply.get('result', {}):
                if fault == 'approval-missing-producer':
                    reply['result'].pop('approval')
                if fault == 'approval-wrong-id':
                    reply['result']['approval']['id'] = 'unrelated-request'
            if params.get('operation') == 'xsm_grant' and 'grant' in reply.get('result', {}):
                if fault == 'grant-missing-producer':
                    reply['result'].pop('grant')
                if fault == 'grant-replay-id' and seen_grant:
                    current = reply['result']['grant']['id']
                    reply['result']['grant']['id'] = '00000000' if current != '00000000' else '11111111'
                seen_grant = True
            if params.get('operation') == 'xsm_send':
                value = reply.get('result', {})
                if fault == 'send-storage-as-arrival' and not value.get('grouped') and value.get('send', {}).get('status') == 'stored':
                    value['send']['runtime_reached'] = True
                if fault == 'send-group-shared-id' and value.get('grouped') and len(value['send']['recipients']) >= 2:
                    value['send']['recipients'][1]['id'] = value['send']['recipients'][0]['id']
                if fault == 'send-failure-body-sent' and 'attachment_error' in reply.get('error', {}).get('data', {}):
                    reply['error']['data']['attachment_error']['body_sent'] = True
            if params.get('operation') == 'xsm_doc' and params.get('arguments', {}).get('action') == 'next' and 'result' in reply:
                if fault == 'doc-wip-hides-candidate':
                    reply['result']['candidates'] = [c for c in reply['result']['candidates'] if not c.get('wip')]
                if fault == 'doc-limit-changes-total':
                    reply['result']['total'] = len(reply['result']['candidates'])
            if params.get('operation') == 'xsm_board' and 'result' in reply:
                if fault == 'board-lost-parent' and len(reply['result'].get('nodes', [])) == 2:
                    for node in reply['result']['nodes']:
                        node['parents'] = []
                if fault == 'board-wrong-source':
                    for record in reply['result'].get('decisions', []):
                        record['via'] = 'model'
            if params.get('operation') == 'xsm_discover' and 'result' in reply:
                for candidate in reply['result'].get('candidates', []):
                    if fault == 'discovery-private-home':
                        candidate['home'] = '/synthetic/private-profile'
                    if fault == 'discovery-missing-source':
                        candidate.get('title', {}).pop('source', None)
            if params.get('operation') == 'xsm_inbox' and 'result' in reply:
                claims = reply['result'].get('claims', [])
                if claims:
                    if fault == 'reuse-token' and first_token:
                        claims[0]['token'] = first_token
                    first_token = first_token or claims[0]['token']
            if fault == 'accept-foreign-ack' and params.get('operation') == 'xsm_ack' and 'error' in reply:
                reply.pop('error')
                reply['result'] = {'acked': []}
        if (fault == 'auto-consume-admitted' and request['method'] == 'delivery.report' and
                params.get('state') == 'admitted' and 'result' in reply):
            consumed = exchange({'jsonrpc': '2.0', 'id': 'fault-ack', 'method': 'operation.call',
                'params': {'session': params['session'], 'operation': 'xsm_ack',
                           'arguments': {'tokens': [params['token']]}}}, notifications=False)
            if 'error' in consumed:
                raise RuntimeError(consumed)
        emit(reply)
finally:
    process.stdin.close()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    reader.join(timeout=1)
    process.stdout.close()
