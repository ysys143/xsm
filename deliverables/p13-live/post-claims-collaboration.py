"""P13 J03/J04 natural-goal observation. No controller message/ACK/index repair.

The only controller product operation is one initial native registration per
actor, from provider thread.started + actual MCP ancestor PID. Models receive
only the role/business goal below; protocol choices come from installed tools.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata

REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / 'deliverables/p13-live'
MANIFEST = REPO / 'deliverables/p13-live/post-qa-source-manifest.json'
REVIEWER_GOAL = '이 저장소 검토 담당 a1입니다. 동료 질문을 받아 3차례 검토가 끝날 때까지 세션을 유지하세요.'
INITIATOR_GOAL = ('xsm으로 동료 a1을 찾아 2+2=5 제안을 검토받고 반례를 고쳐 재검토받으세요. '
                  '0+0=0 경계도 독립 검토받아 결과를 보고하세요.')
FORBIDDEN = {'xsm_link', 'xsm_join', 'xsm_reach', 'xsm_grant', 'xsm_approve',
             'xsm_publish', 'xsm_setup', 'xsm_owned'}


def sha(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def source_readback(root, expected=None):
    files = expected or {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob('*'))
                        if p.is_file() and p.suffix != '.pyc' and '__pycache__' not in p.parts}
    changed = [name for name, digest in files.items()
               if not (root / name).is_file() or sha((root / name).read_bytes()) != digest]
    return {'file_count': len(files), 'manifest_sha256': sha(json.dumps(files, sort_keys=True)),
            'matches': not changed, 'changed_paths': changed}, files


def profile_guard():
    result = {}
    for profile in ('.codex', '.codex-3'):
        home = Path.home() / profile
        for name in ('config.toml', 'hooks.json', 'settings.json'):
            p = home / name
            result[str(p)] = sha(p.read_bytes()) if p.is_file() else None
        p = home / 'auth.json'
        if p.exists():
            st = p.stat()
            result[str(p) + ':metadata-only'] = [st.st_size, st.st_mtime_ns, st.st_ino]
    return result


def read_json(p):
    try:
        with Path(p).open() as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def events(path):
    result = []
    if not path.exists():
        return result
    with path.open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                result.append(row)
    return result


def args_object(item):
    value = item.get('arguments') or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def payloads(item):
    value = item.get('result')
    result = []
    if isinstance(value, dict):
        result.append(value)
        for block in value.get('content', []):
            if not isinstance(block, dict) or not isinstance(block.get('text'), str):
                continue
            try:
                result.append(json.loads(block['text']))
            except ValueError:
                result.append(block['text'])
    elif isinstance(value, str):
        try:
            result.append(json.loads(value))
        except ValueError:
            result.append(value)
    return result


def math_kind(body):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', body or ''))
    if re.search(r'0\+0(?:=|는|가)0', text):
        return 'boundary'
    if (re.search(r'2\+2(?:=|는|가)4', text) and
            re.search(r'수정안|고쳤|철회|재검토|correct|revis', text, re.I)):
        return 'correction'  # a revision may quote the rejected 2+2=5 proposal
    if re.search(r'2\+2(?:=|는|가)5', text):
        return 'proposal'
    if re.search(r'2\+2(?:=|는|가)4', text):
        return 'correction'
    return 'other'


def error_kind(item):
    if item.get('error'):
        return 'native-tool-error'
    for value in payloads(item):
        if isinstance(value, dict):
            if value.get('isError'):
                return 'mcp-error'
            if value.get('status') in ('error', 'refused', 'not-found', 'selection-required'):
                return value['status']
        elif isinstance(value, str):
            if re.search(r'sandbox.blocked|sandboxed.*cannot|read.only database|EPERM', value, re.I):
                return 'sandbox-blocked'
            if value.lower().startswith(('error:', 'refused:', 'xsm failed:')):
                return 'application-error'
    return None


class Actor:
    def __init__(self, role, profile, runtime, state, root, source_modules):
        self.role, self.profile, self.runtime = role, profile, runtime
        self.state, self.root, self.modules = state, root, source_modules
        self.out, self.err = root / (role + '.jsonl'), root / (role + '.stderr')
        self.peer = None
        self.mcp = None
        self.calls = {}
        self.first_agent_at = None
        self.registered_at = None
        self.first_reply_at = None

    def start(self):
        self.started_at = time.monotonic()
        goal = REVIEWER_GOAL if self.role == 'reviewer' else INITIATOR_GOAL
        args = ['codex', 'exec', '--ignore-user-config', '--json', '--sandbox', 'workspace-write',
                '-c', 'approval_policy="never"',
                '-c', 'mcp_servers.xsm.command="/usr/bin/python3"',
                '-c', 'mcp_servers.xsm.args=["-m","xsm","mcp"]',
                '-c', 'mcp_servers.xsm.cwd=' + json.dumps(str(self.runtime))]
        for key, value in {'XSM_HOME': str(self.state), 'CODEX_HOME': str(self.profile),
                           'PYTHONPATH': str(self.runtime), 'PYTHONDONTWRITEBYTECODE': '1'}.items():
            args += ['-c', 'mcp_servers.xsm.env.' + key + '=' + json.dumps(value)]
        args.append(goal)
        env = dict(os.environ, CODEX_HOME=str(self.profile), XSM_HOME=str(self.state),
                   PYTHONPATH=str(self.runtime), PYTHONDONTWRITEBYTECODE='1',
                   PATH=str(self.runtime / 'bin') + os.pathsep + os.environ.get('PATH', ''))
        for key in ('CODEX_THREAD_ID', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_SESSION_ID',
                    'CLAUDE_CODE_MESSAGING_SOCKET', 'CLAUDECODE',
                    'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY'):
            env.pop(key, None)
        self.streams = [self.out.open('w'), self.err.open('w')]
        for p in (self.out, self.err):
            p.chmod(0o600)
        self.proc = subprocess.Popen(args, cwd=str(REPO), env=env, stdin=subprocess.DEVNULL,
                                     stdout=self.streams[0], stderr=self.streams[1], start_new_session=True)
        self.start_generation = self.modules['identity'].lstart(self.proc.pid)
        return {'role': self.role, 'profile': str(self.profile), 'goal': goal,
                'pid': self.proc.pid, 'lstart': self.start_generation,
                'invocation_without_goal': args[:-1], 'goal_sha256': sha(goal)}

    def refresh(self, used_beacons):
        rows = events(self.out)
        sid = next((r.get('thread_id') for r in rows if r.get('type') == 'thread.started'), None)
        if sid and self.peer is None:
            candidates = []
            for path in (self.state / 'mcp').glob('*.json'):
                row = read_json(path)
                if (not isinstance(row, dict) or row.get('pid') in used_beacons or
                        row.get('cwd') != str(self.runtime)):
                    continue
                if self.modules['identity'].pid_alive(row['pid']):
                    candidates.append(row)
            if len(candidates) == 1:
                self.mcp = candidates[0]
                # The only controller operation on product state: initial real
                # thread/PID/home registration, with the permitted role label.
                self.peer = self.modules['registry'].upsert('codex', str(self.profile), sid,
                    self.mcp['ppid'], str(REPO), name='a1' if self.role == 'reviewer' else None,
                    mcp_pid=self.mcp['pid'])
                used_beacons.add(self.mcp['pid'])
                self.registered_at = time.monotonic()
        for index, row in enumerate(rows):
            item = row.get('item') or {}
            kind = item.get('type')
            if kind in (None, 'agent_message', 'reasoning'):
                continue
            key = item.get('id') or 'event-' + str(index)
            if key not in self.calls:
                self.calls[key] = {'kind': kind, 'started_at': time.monotonic(), 'item': item,
                                   'complete': False}
                if self.first_agent_at is None:
                    self.first_agent_at = self.calls[key]['started_at']
            if row.get('type') == 'item.completed':
                self.calls[key].update(item=item, complete=True, completed_at=time.monotonic())
        return rows

    def summary(self):
        calls = []
        for call in self.calls.values():
            item = call['item'];kind = call['kind']
            row = {'kind': kind, 'complete': call['complete'],
                   'seconds_from_actor_start': round(call['started_at'] - self.started_at, 3)}
            if kind == 'mcp_tool_call':
                arguments = args_object(item)
                row.update(server=item.get('server'), tool=item.get('tool'), error=error_kind(item),
                           argument_keys=sorted(arguments))
                # No claim tokens, raw bodies, request handles or endpoint IDs.
                row['arguments_sha256'] = sha(json.dumps(arguments, sort_keys=True))
            if kind == 'command_execution':
                command = item.get('command') or ''
                row.update(command_sha256=sha(command), exit_code=item.get('exit_code'),
                           sandbox_shell_send_attempt=bool(re.search(r'\bxsm\s+(?:send|ask)\b', command)),
                           skill_read='SKILL.md' in command,
                           sandbox_failure=bool(item.get('exit_code') not in (None, 0) and re.search(r'sandbox.blocked|sandboxed.*cannot|EPERM|read.only',
                                                        item.get('aggregated_output') or '', re.I)))
            calls.append(row)
        wrong = next((r for r in calls if r.get('error') or r.get('sandbox_shell_send_attempt')), None)
        return {'role': self.role, 'native_session_id': (self.peer or {}).get('session_id'),
                'registered_name': (self.peer or {}).get('name'), 'mcp_pid': (self.mcp or {}).get('pid'),
                'setup_registration_seconds': round(self.registered_at-self.started_at, 3) if self.registered_at else None,
                'registration_preceded_first_agent_call': bool(self.registered_at and
                    (self.first_agent_at is None or self.registered_at <= self.first_agent_at)),
                'calls': calls, 'item_type_counts': dict(collections.Counter(c['kind'] for c in calls)),
                'agent_mcp_call_count': sum(c['kind']=='mcp_tool_call' for c in calls),
                'agent_shell_call_count': sum(c['kind']=='command_execution' for c in calls),
                'tool_error_count': sum(bool(c.get('error') or c.get('sandbox_failure')) for c in calls),
                'first_wrong_choice': wrong, 'exit_code': self.proc.poll(),
                'events_path': str(self.out), 'stderr_path': str(self.err),
                'events_sha256': sha(self.out.read_bytes())}

    def finish(self):
        actions = []
        if self.proc.poll() is None:
            try:
                if os.getpgid(self.proc.pid) == self.proc.pid:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                    actions.append({'pid': self.proc.pid, 'kind': 'owned-native-group', 'signal': 'TERM'})
                else:
                    self.proc.terminate()
                    actions.append({'pid': self.proc.pid, 'kind': 'owned-native-root', 'signal': 'TERM'})
            except ProcessLookupError:
                pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with __import__('contextlib').suppress(ProcessLookupError):
                if os.getpgid(self.proc.pid) == self.proc.pid:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                else:
                    self.proc.kill()
            self.proc.wait(timeout=10)
        if self.mcp:
            pid = self.mcp['pid'];identity = self.modules['identity']
            if identity.pid_alive(pid) and identity.lstart(pid) == self.mcp['lstart']:
                try:
                    os.kill(pid, signal.SIGTERM)
                    actions.append({'pid': pid, 'kind': 'owned-mcp', 'signal': 'TERM'})
                except ProcessLookupError:
                    pass
        for stream in self.streams:
            stream.close()
        return actions


def product_messages(state, actors, modules):
    """Read-only observation, never receive/poll/ACK/index mutation."""
    peers = {a.role: a.peer for a in actors if a.peer}
    if len(peers) != 2:
        return {}, []
    by_ref = {p['ref']: role for role,p in peers.items()}
    result = {}
    for path in (state / 'handoffs').glob('*/*.json'):
        record = read_json(path)
        if not isinstance(record, dict):continue
        msg = record.get('message') or {};source=msg.get('sender') or {};target=record.get('receiver') or {}
        sender = next((role for role,p in peers.items() if all(source.get(k)==p.get(k)
                     for k in ('runtime','home','session_id'))),None)
        recipient = next((role for role,p in peers.items() if all(target.get(k)==p.get(k)
                     for k in ('runtime','home','session_id'))),None)
        if sender and recipient:
            result[record['id']]={'id':record['id'],'sender':sender,'recipient':recipient,
                'kind':msg.get('kind'),'reply_to':msg.get('reply_to'),'body':msg.get('body',''),
                'outcome':msg.get('outcome'),'evidence':'canonical native-endpoint-bound body'}
    # Legacy same-goal comparison: use the actual per-native MCP call's body
    # and its own ledger ID/ref, not an invented answer or a receipt.
    for actor in actors:
        for call in actor.calls.values():
            item=call['item'];args=args_object(item)
            if call['kind']!='mcp_tool_call' or item.get('tool')!='xsm_send' or not call['complete'] or error_kind(item):continue
            text=args.get('text') or ''
            for path in (state/'ledger').glob('*.json'):
                if path.name.endswith(('.recv.json','.handoff.json')):continue
                record=read_json(path)
                if not isinstance(record,dict) or record.get('id') in result:continue
                if (record.get('from') or {}).get('ref')!=(actor.peer or {}).get('ref'):continue
                preview=record.get('preview')
                if not isinstance(preview,str) or not preview or not text.startswith(preview):continue
                if record.get('kind')!=args.get('kind','note'):continue
                if args.get('reply_to') and record.get('reply_to') is not None and record['reply_to']!=args['reply_to']:continue
                recipient=by_ref.get((record.get('to') or {}).get('ref'))
                if recipient:
                    result[record['id']]={'id':record['id'],'sender':actor.role,'recipient':recipient,
                        'kind':args.get('kind','note'),'reply_to':args.get('reply_to'),'body':text,
                        'outcome':args.get('outcome'),'evidence':'actual completed MCP send + matching ledger'}
    replies=[r for r in result.values() if r['sender']=='reviewer' and r['recipient']=='initiator'
             and r['kind']=='reply' and r.get('reply_to') in result
             and result[r['reply_to']]['sender']=='initiator']
    return result,replies


def received_reply_ids(initiator, replies):
    known={r['id']:r for r in replies};received=set()
    for call in initiator.calls.values():
        if not call['complete'] or call['kind']!='mcp_tool_call':continue
        for payload in payloads(call['item']):
            if isinstance(payload,dict):
                for claim in payload.get('claims',[]):
                    if claim.get('id') in known:received.add(claim['id'])
                for reply in payload.get('replies',[]):
                    if reply.get('id') in known:received.add(reply['id'])
            elif isinstance(payload,str):
                for rid,reply in known.items():
                    if reply['body'] and reply['body'] in payload:received.add(rid)
    return received


def run_condition(label, runtime, timeout, root):
    state=root/'state';state.mkdir(parents=True)
    os.environ['XSM_HOME']=str(state)
    # Import only this condition's immutable product; no current checkout leak.
    for name in list(sys.modules):
        if name=='xsm' or name.startswith('xsm.'):del sys.modules[name]
    sys.path.insert(0,str(runtime));sys.dont_write_bytecode=True
    modules={name:importlib.import_module('xsm.'+name) for name in ('registry','paths','identity','envelope')}
    modules['paths'].HOME=str(state)
    before=profile_guard();actors=[];used=set();start=time.monotonic();first_reply=None
    record={'condition':label,'runtime':str(runtime),'status':'running','fixture_state':str(state),
            'source_before':source_readback(runtime)[0], 'setup_registry_calls':0,
            'controller_message_calls':0,'controller_ack_calls':0,'controller_index_corrections':0,
            'factory_only_ignore_user_config':True,'standard_server_name':'xsm',
            'skills':'native home discovery left unchanged; no injected skill text or per-eval procedure',
            'model_override':False,'allowed_tools_override':False,'user_clicks':0,'user_commands':0,
            'user_approvals':0,'os_ui_actions':0,'bootstrap_protocol_calls':'not exposed in native event stream'}
    try:
        reviewer=Actor('reviewer',Path.home()/'.codex',runtime,state,root,modules)
        actors.append(reviewer);record['reviewer_invocation']=reviewer.start()
        deadline=time.monotonic()+60
        while time.monotonic()<deadline and reviewer.peer is None:
            reviewer.refresh(used)
            if reviewer.proc.poll() is not None:break
            time.sleep(.1)
        if reviewer.peer is None:raise RuntimeError('reviewer native registration unavailable; no goal correction attempted')
        record['setup_registry_calls']+=1
        initiator=Actor('initiator',Path.home()/'.codex-3',runtime,state,root,modules)
        actors.append(initiator);record['initiator_invocation']=initiator.start()
        deadline=time.monotonic()+timeout;initiator_exited_at=None
        while time.monotonic()<deadline:
            for actor in actors:
                was=actor.peer is not None;actor.refresh(used)
                if not was and actor.peer is not None:record['setup_registry_calls']+=1
            messages,replies=product_messages(state,actors,modules)
            received=received_reply_ids(initiator,replies)
            if received and first_reply is None:first_reply=time.monotonic()-initiator.started_at
            for actor in actors:
                for call in actor.calls.values():
                    if call['kind']=='mcp_tool_call' and call['item'].get('tool') in FORBIDDEN:
                        raise RuntimeError('privilege/discovery-widening operation attempted: '+call['item']['tool'])
            cfg=read_json(state/'config.json') or {}
            if cfg.get('links') or cfg.get('reaches') or cfg.get('projects'):
                raise RuntimeError('fixture scope widened; no bypass or rollback attempted')
            if any(call['kind']=='file_change' for actor in actors for call in actor.calls.values()):
                raise RuntimeError('unexpected model file-change event; original sample preserved')
            if initiator.proc.poll() is not None:
                initiator_exited_at=initiator_exited_at or time.monotonic()
                if reviewer.proc.poll() is not None or time.monotonic()-initiator_exited_at>20:break
            time.sleep(.2)
        messages,replies=product_messages(state,actors,modules)
        received=received_reply_ids(initiator,replies)
        reviewed=[]
        for reply in replies:
            request=messages[reply['reply_to']]
            reviewed.append({'request_sha256':sha(request['id']),'reply_sha256':sha(reply['id']),
                'request_body_sha256':sha(request['body']),'reply_body_sha256':sha(reply['body']),
                'proposal_kind':math_kind(request['body']),'outcome':reply['outcome'],
                'initiator_received_actual_body':reply['id'] in received,
                'reply_mentions_4':'4' in reply['body'],'reply_mentions_0':'0' in reply['body'],
                'evidence':reply['evidence']})
        categories={r['proposal_kind'] for r in reviewed if r['initiator_received_actual_body']}
        record.update(reviews=reviewed,received_review_categories=sorted(categories),
             first_actual_reply_seconds=round(first_reply,3) if first_reply is not None else None,
             duration_seconds=round(time.monotonic()-start,3),
             status='passed' if categories >= {'proposal','correction','boundary'} and initiator.proc.poll()==0
                    else 'not-completed-original-sample')
    except Exception as exc:
        record.update(status='not-completed-original-sample',boundary=str(exc),error_type=type(exc).__name__)
    finally:
        record['actors']=[a.summary() for a in actors]
        record['cleanup']=[]
        for actor in actors:
            try:record['cleanup'].extend(actor.finish())
            except Exception as exc:record['cleanup'].append({'error_type':type(exc).__name__,'role':actor.role})
        record['owned_processes_after']=[{'role':a.role,'native_alive':a.proc.poll() is None,
            'mcp_same_generation_alive':bool(a.mcp and modules['identity'].pid_alive(a.mcp['pid']) and
                modules['identity'].lstart(a.mcp['pid'])==a.mcp['lstart'])} for a in actors]
        record['profile_settings_and_auth_metadata_unchanged']=before==profile_guard()
        record['source_after']=source_readback(runtime)[0]
        record['source_unchanged']=record['source_before']==record['source_after']
        if not record['profile_settings_and_auth_metadata_unchanged'] or not record['source_unchanged']:
            record['status']='failed-protected-input-changed'
        if any(r['native_alive'] or r['mcp_same_generation_alive'] for r in record['owned_processes_after']):
            record['status']='cleanup-not-verified'
    return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--timeout',type=float,default=300)
    parser.add_argument('--no-baseline',action='store_true');parser.add_argument('--audit-existing',action='store_true');args=parser.parse_args()
    if args.audit_existing:return audit_existing()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(MANIFEST.read_text());current=Path(manifest['snapshot'])
    validated,_=source_readback(current,manifest['files'])
    if not validated['matches']:raise RuntimeError('post-QA source manifest differs; no model started')
    root=Path(tempfile.mkdtemp(prefix='p13-post-claims-',dir='/private/tmp'));root.chmod(0o700)
    report={'scope':'one post-claims current natural-goal sample; not full J03/J04 or old-product speed comparison',
            'fixture_root':str(root),'post_qa_manifest':validated,
            'goals':{'reviewer':REVIEWER_GOAL,'initiator':INITIATOR_GOAL},'conditions':[]}
    conditions=[('post-claims-current',current)]
    if not args.no_baseline:conditions.append(('old-0.4.20',Path.home()/'.xsm/runtime/2389da782089'))
    for label,runtime in conditions:
        condition_root=root/label;condition_root.mkdir(mode=0o700)
        print(json.dumps({'phase':'condition-started','condition':label,'root':str(condition_root)}),flush=True)
        result=run_condition(label,runtime,args.timeout,condition_root)
        report['conditions'].append(result)
        (OUTPUT/'post-claims-collaboration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'phase':'condition-finished','condition':label,'status':result['status'],
              'first_actual_reply_seconds':result.get('first_actual_reply_seconds'),
              'received_review_categories':result.get('received_review_categories'),
              'actor_counts':[{k:a[k] for k in ('role','agent_mcp_call_count','agent_shell_call_count','tool_error_count')}
                              for a in result['actors']]}),flush=True)
        if result['status'] in ('failed-protected-input-changed','cleanup-not-verified'):break
    return 0




def audit_existing():
    """Post-hoc collector repair only. Never starts native processes or writes product state."""
    import types
    import shlex
    from xsm import identity
    raw_path=OUTPUT/'post-claims-collaboration.json';raw=raw_path.read_bytes();report=json.loads(raw)
    audit={'original_result_sha256':sha(raw),'raw_result_preserved':True,'native_reruns':0,
           'message_ack_index_corrections':0,'common_cwd':str(REPO),
           'common_documents':'development-tree skills/xsm, selected by agents themselves',
           'old_condition':'old MCP 0.4.20 + common new skill/guide; not unchanged old-product baseline',
           'collector_corrections':['v2 may quote revoked false proposal',
             'old ledger has no reply_to; bind actual completed MCP args plus matching ledger body/actor',
             'documentation mentioning sandbox is not a command failure',
             'check MCP liveness again after finalizer exit race'], 'conditions':[]}
    for original in report['conditions']:
        root=Path(original['fixture_state']).parent;actors=[]
        for summary in original['actors']:
            peer=next((row for path in (root/'state/sessions').glob('*.json')
                if isinstance((row:=read_json(path)),dict) and row.get('session_id')==summary['native_session_id']),None)
            calls={}
            for i,event in enumerate(events(root/(summary['role']+'.jsonl'))):
                item=event.get('item') or {};kind=item.get('type')
                if kind in (None,'agent_message','reasoning'):continue
                key=item.get('id') or 'event-'+str(i)
                calls.setdefault(key,{'kind':kind,'item':item,'complete':False})
                if event.get('type')=='item.completed':calls[key].update(item=item,complete=True)
            actors.append(types.SimpleNamespace(role=summary['role'],peer=peer,calls=calls))
        messages,replies=product_messages(root/'state',actors,{})
        received=received_reply_ids(next(a for a in actors if a.role=='initiator'),replies)
        reviews=[]
        for reply in replies:
            question=messages[reply['reply_to']]
            qdoc=read_json(root/'state/questions'/(question['id']+'.json')) or {}
            category='handshake' if qdoc.get('purpose')=='handshake' else math_kind(question['body'])
            reviews.append({'request_sha256':sha(question['id']),'reply_sha256':sha(reply['id']),
                'category':category,'outcome':reply['outcome'],'received_actual_body':reply['id'] in received,
                'request_body_sha256':sha(question['body']),'reply_body_sha256':sha(reply['body']),
                'quotes_retracted_5':bool(re.search(r'2\s*\+\s*2\s*=\s*5',question['body'])),
                'states_correct_4':bool(re.search(r'2\s*\+\s*2\s*=\s*4',question['body']))})
        rows=[]
        for actor in actors:
            prior=next(a for a in original['actors'] if a['role']==actor.role)
            shell=[];mcp_errors=[];tool_counts=collections.Counter()
            for call in actor.calls.values():
                item=call['item'];kind=call['kind']
                if kind=='mcp_tool_call':
                    tool_counts[item.get('tool')]+=1
                    if call['complete'] and error_kind(item):mcp_errors.append(error_kind(item))
                if kind=='command_execution':
                    command=item.get('command') or ''
                    try:
                        parts=shlex.split(command);inner=parts[-1] if any(x in parts for x in ('-lc','-c')) else command
                    except ValueError:inner=command
                    if 'SKILL.md' in inner:purpose='skill-read'
                    elif 'references/' in inner and ('cat ' in inner or 'sed ' in inner):purpose='guide-read'
                    elif re.search(r'python\d?\s+-c',inner):purpose='independent-arithmetic-check'
                    elif 'bin/xsm list' in inner:purpose='current-checkout-cli-discovery'
                    else:purpose='workspace-or-skill-discovery'
                    shell.append({'purpose':purpose,'exit_code':item.get('exit_code'),'complete':call['complete'],
                        'command_sha256':sha(command),'shell_send_attempt':bool(re.search(r'(?:\bxsm|/xsm)["\x27]?\s+(?:send|ask)\b',inner))})
            invocation=original[actor.role+'_invocation'];pid,start=invocation['pid'],invocation['lstart']
            mpid=prior['mcp_pid']
            kernel=subprocess.run(['ps','-p',str(mpid),'-o','stat='],capture_output=True,text=True)
            mcp_alive=bool(kernel.stdout.strip() and not kernel.stdout.strip().startswith('Z'))
            rows.append({'role':actor.role,'mcp_calls_started':sum(tool_counts.values()),'mcp_by_tool':dict(tool_counts),
                'mcp_errors':mcp_errors,'shell_calls':shell,
                'shell_errors':sum(s['exit_code'] not in (None,0) for s in shell),
                'sandbox_shell_send_attempts':sum(s['shell_send_attempt'] for s in shell),
                'native_terminal_events':[e['type'] for e in events(root/(actor.role+'.jsonl'))
                                          if e.get('type') in ('turn.completed','turn.failed')],
                'native_same_generation_alive_after':identity.pid_alive(pid) and identity.lstart(pid)==start,
                'mcp_execution_alive_after':mcp_alive,
                'registration_preceded_agent_call':prior['registration_preceded_first_agent_call'],
                'events_sha256':sha((root/(actor.role+'.jsonl')).read_bytes())})
        categories={r['category'] for r in reviews if r['received_actual_body']}
        audit['conditions'].append({'condition':original['condition'],
            'original_automatic_status':original['status'],
            'audited_business_goal':'passed' if categories>={'proposal','correction','boundary'} else 'not-verified',
            'reviews':reviews,'actors':rows,
            'actual_math_review_count':sum(r['category']!='handshake' and r['received_actual_body'] for r in reviews),
            'actual_handshake_count':sum(r['category']=='handshake' and r['received_actual_body'] for r in reviews),
            'original_first_actual_reply_seconds':original.get('first_actual_reply_seconds'),
            'first_reply_scope':'includes readiness handshake' if original['condition']=='B05-final' else
                                 'original exact latency unavailable because legacy collector mismatched',
            'cleanup_after_exit_race_verified':all(not a['native_same_generation_alive_after'] and
                                                    not a['mcp_execution_alive_after'] for a in rows),
            'profile_unchanged':original['profile_settings_and_auth_metadata_unchanged'],
            'runtime_source_unchanged':original['source_unchanged'],
            'controller_interventions':{'initial_registry':original['setup_registry_calls'],
                'message':0,'ack':0,'index':0,'user_clicks':0,'user_commands':0,'user_approvals':0}})
    manifest=json.loads(MANIFEST.read_text())
    audit['workspace_documents_at_audit']={}
    for name in ('skills/xsm/SKILL.md','skills/xsm/references/messaging.md','skills/xsm/references/guide.md'):
        digest=sha((REPO/name).read_bytes())
        audit['workspace_documents_at_audit'][name]={'sha256':digest,'equals_B05_frozen':digest==manifest['files'].get(name)}
    assert raw_path.read_bytes()==raw
    (OUTPUT/'post-claims-collaboration-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps([{'condition':c['condition'],'business_goal':c['audited_business_goal'],
        'math_reviews':c['actual_math_review_count'],'handshake':c['actual_handshake_count'],
        'mcp_calls':sum(a['mcp_calls_started'] for a in c['actors']),
        'mcp_errors':sum(len(a['mcp_errors']) for a in c['actors']),
        'shell_errors':sum(a['shell_errors'] for a in c['actors']),
        'shell_send_attempts':sum(a['sandbox_shell_send_attempts'] for a in c['actors']),
        'all_owned_gone':c['cleanup_after_exit_race_verified']} for c in audit['conditions']],ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
