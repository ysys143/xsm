"""Operator-selected isolated verification; public examples != execution evidence."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
from jsonschema import Draft202012Validator
from participant_v7 import Consumer, Transport, ContractError, strict_json


def validation(schema, value):
    Draft202012Validator(schema).validate(value)


def load(path):
    spec = importlib.util.spec_from_file_location('public_conformance', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


class Verification:
    def __init__(self, operator, output):
        self.operator = operator; self.output = output; self.counter = 0; self.checks = []
        self.consumer = Consumer(operator['input'], validation)
        dump(output/'implementation-hashes.json',{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['participant_v7.py','verify_v7.py','local_v7_fixtures.py']})
        self.coverage = {}; self.rpcs = 0

    def check(self, name, function, category):
        try:
            function(); self.checks.append(dict(name=name, category=category, passed=True))
        except Exception as exc:
            self.checks.append(dict(name=name, category=category, passed=False, error=repr(exc), traceback=traceback.format_exc()))

        dump(self.output/'checks-progress.json',self.checks)

    def require(self, condition):
        if not condition: raise AssertionError('independent assertion failed')

    def root(self, label):
        self.counter += 1
        path = self.output / ('%03d-' % self.counter + label); path.mkdir()
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'TMPDIR') if k in os.environ}
        env.update(HOME=str(path/'home'), XSM_HOME=str(path/'state'), CODEX_HOME=str(path/'codex'), CLAUDE_CONFIG_DIR=str(path/'claude'))
        return path, env

    def transport(self, command, root, env, timeout=8):
        self.counter += 1
        return Transport(command, root, env, self.consumer, self.output/('%03d-wire' % self.counter), timeout)

    def record(self, method, params, frame):
        self.rpcs += 1
        if method == 'operation.call' and 'result' in frame:
            op = params['operation']; action = params.get('arguments', {}).get('action', 'hand_over' if op == 'xsm_handover' else '(none)')
            self.coverage.setdefault(op, {})[action] = self.coverage.setdefault(op, {}).get(action, 0)+1

    def independent(self):
        root, env = self.root('independent-server')
        peer = self.transport([self.operator['server'], 'protocol', 'serve', '--stdio'], root, env)
        def rpc(method, **params):
            frame, facts = peer.call(method, params); self.record(method, params, frame)
            if 'error' in frame: raise AssertionError(frame['error'])
            return frame['result']
        def scenario():
            rpc('initialize', protocolVersion='1')
            catalog = rpc('operations/list')['operations']
            self.require({r['name'] for r in catalog} == set(self.consumer.inventory))
            base = dict(runtime='independent-v7', profile='isolated', cwd=str(root), capabilities=['inbox','messaging','user-decisions'])
            a = rpc('session.open', **base, conversation='sender')
            b = rpc('session.open', **base, conversation='receiver')
            def op(owner, name, **args): return rpc('operation.call', session=owner['session'], operation=name, arguments=args)
            op(b, 'xsm_inbox')
            sent = op(a, 'xsm_send', target=b['address'], text='Independent UTF-8 한글', wake='never', request_id='v7-original')
            self.require(sent['send']['status'] == 'stored')
            packet = op(b, 'xsm_inbox', message_ids=['v7-original'])
            self.require(packet['claims'] and '한글' in packet['messages'][0])
            token = packet['claims'][0]['token']
            rpc('inbox.release', session=b['session'], tokens=[token])
            again = op(b, 'xsm_inbox', message_ids=['v7-original'])
            self.require(again['claims'][0]['id'] == 'v7-original' and again['claims'][0]['token'] != token)
            # Explicit acknowledgement occurs only after assertions on actual original.
            op(b, 'xsm_ack', tokens=[again['claims'][0]['token']])
            self.require(not op(b, 'xsm_inbox', message_ids=['v7-original'])['claims'])
            node = op(a, 'xsm_doc', action='add', doc='INDEPENDENT.md', text='independent node')['node']
            self.require(op(a, 'xsm_doc', action='show', doc='INDEPENDENT.md', node=node['id'])['node'] == node)
            args = dict(visible=True)
            pending = op(a, 'xsm_publish', **args)
            self.require(pending['status'] == 'waiting-for-user')
            event = peer.notification()['params']
            self.require('challenge' not in self.consumer.operation('xsm_publish', args, pending))
            stored = rpc('decision.response', session=a['session'], questionId=event['questionId'], challenge=event['challenge'], displayed=event['question'], action='accept', answer='allow', source_id='independent-synthetic-host')
            # Synthetic host answer is stored, explicit original re-invocation applies.
            status = op(a, 'xsm_decision_status', id=pending['decision_id'])
            self.require(status['status'] != 'applied')
            applied = op(a, 'xsm_publish', **args)
            self.require(applied['visible'] is True)
            rpc('session.close', session=b['session'])
            resumed = rpc('session.open', **base, conversation='receiver')
            self.require(resumed['address'] == b['address'] and resumed['generation'] != b['generation'])
        try: self.check('independent storage/release/reclaim/ACK/document/answer-application/reopen', scenario, 'independent-real-server')
        finally: peer.close()

    def independent_fixtures(self):
        for kind, executable in [('owned', self.operator['ownedFixture']), ('error', self.operator['errorFixture'])]:
            root, env = self.root('independent-'+kind)
            peer = self.transport([executable,'protocol','serve','--stdio'],root,env)
            def rpc(method, expected_error=None, **params):
                frame, facts = peer.call(method,params); self.record(method,params,frame)
                if expected_error is not None:
                    self.require(frame.get('error',{}).get('code')==expected_error); return frame['error']
                if 'error' in frame: raise AssertionError(frame['error'])
                return frame['result']
            def scenario():
                rpc('initialize',protocolVersion='1')
                tools = {r['name']:r for r in rpc('operations/list')['operations']}
                marker = 'XSM_CONFORMANCE_MODEL0_ONLY' if kind=='owned' else 'XSM_CONFORMANCE_ERROR_FIXTURE'
                self.require(marker in tools['xsm_owned' if kind=='owned' else 'xsm_doc']['description'])
                owner = rpc('session.open',runtime='independent-v7',profile='isolated',conversation=kind,cwd=str(root),capabilities=['inbox','messaging'])
                def op(tool, expected_error=None, **args):
                    return rpc('operation.call',expected_error=expected_error,session=owner['session'],operation=tool,arguments=args)
                if kind=='error':
                    op('xsm_doc',expected_error=-32603,action='add',doc='ERROR-FIXTURE.md',text='Independent durable effect',tags=['report'])
                    nodes = op('xsm_doc',action='log',doc='ERROR-FIXTURE.md')['nodes']
                    self.require(len(nodes)==1 and nodes[0]['body']=='Independent durable effect')
                    self.require(op('xsm_doc',action='show',doc='ERROR-FIXTURE.md',node=nodes[0]['id'])['node']==nodes[0])
                else:
                    op('xsm_owned',action='create',name='independent-owned',runtime='codex')
                    queued = op('xsm_owned',action='run',name='independent-owned',request_id='independent-cancel',work_context='independent-context',text='model0 only')
                    self.require(queued['status']=='queued' and queued['accepted'] is False)
                    cancelled = op('xsm_owned',action='cancel',name='independent-owned',request_id='independent-cancel')
                    self.require(cancelled['status']=='cancelled' and cancelled['cancellation']['native_state']=='not-started')
                    (Path(env['XSM_HOME'])/'owned-fixture-capacity').write_text('4')
                    op('xsm_owned',action='run',name='independent-owned',request_id='independent-ready',work_context='independent-context',text='model0 only')
                    deadline=time.monotonic()+5
                    while True:
                        ready=op('xsm_owned',action='status',name='independent-owned',request_id='independent-ready')
                        if ready['status']=='reply-stored' or time.monotonic()>deadline: break
                        time.sleep(.02)
                    self.require(ready['status']=='reply-stored' and ready['result']['outcome']=='succeeded')
                    for action in ('retry','reconcile'):
                        recovered=op('xsm_owned',action=action,name='independent-owned',request_id='independent-ready')
                        self.require(recovered['reply_id']==ready['reply_id'] and recovered['result']==ready['result'])
            try: self.check('independent-'+kind+'-recovery',scenario,'independent-model0-fixture')
            finally: peer.close()

    def public_suites(self):
        module = load(Path(self.operator['input'])/'scripts/conform-host-protocol.py')
        verification = self
        class Peer:
            def __init__(self, command, cwd, env, observations=None):
                self.client = verification.transport(command, cwd, env)
                self.process = self.client.process; self.frames = self.client.frames
                self.notifications = self.client.notifications; self.observations = observations
            def call(self, method, params=None, error=None):
                frame, facts = self.client.call(method, params or {})
                verification.record(method, params or {}, frame)
                if self.observations is not None:
                    row = dict(method=method, frame=frame)
                    if method == 'operation.call': row.update(operation=params['operation'], action=params.get('arguments',{}).get('action'))
                    self.observations.append(row)
                if error is not None:
                    verification.require(frame.get('error',{}).get('code') == error); return frame['error']
                if 'error' in frame: raise AssertionError(frame['error'])
                return frame['result']
            def notification(self):
                frame = self.client.notification()
                if self.observations is not None: self.observations.append({'frame': frame})
                return frame
            def close(self): return self.client.close()
        class RetainedDirectory:
            def __init__(self, *args, **kwargs): self.path = verification.root('public-scenario')[0]
            def __enter__(self): return str(self.path)
            def __exit__(self, *args): return False
        module.Peer = Peer
        original_temp = module.tempfile.TemporaryDirectory
        module.tempfile.TemporaryDirectory = RetainedDirectory
        suites = ['lifecycle','messaging','events','decisions','uploads','discovery','collaboration','documents','sending','questions','selection','grants','approvals','scopes','endorsements','handovers','team-board-actions','owned-fixture','errors-fixture']
        reports = []
        try:
            for suite in suites:
                executable = self.operator['ownedFixture' if suite=='owned-fixture' else 'errorFixture' if suite=='errors-fixture' else 'server']
                report = module.run([executable,'protocol','serve','--stdio'], suite, True)
                dump(self.output/('public-'+suite+'.json'), report)
                reports.append(dict(suite=suite, status=report['status'], checks=len(report['checks']), activeCheck=report.get('activeCheck'), error=report.get('error')))
                print(json.dumps(reports[-1]), flush=True)
        finally: module.tempfile.TemporaryDirectory = original_temp
        return reports

    def examples(self):
        root = Path(self.operator['input'])/'docs/protocol'
        results = []
        for file in sorted(root.glob('*-result-examples.json')):
            family = file.name.removesuffix('-result-examples.json')
            ops = ['xsm_'+k for k,v in self.consumer.names.items() if v==family]
            for index, item in enumerate(strict_json(file.read_text())):
                value = item.get('result', item)
                op = item.get('operation', ops[0])
                arguments = {'action': item['action']} if 'action' in item else {}
                if op == 'xsm_owned': arguments['action'] = 'create' if value.get('owned') else 'status'
                if op == 'xsm_handover': arguments['action'] = value.get('handover',{}).get('action','hand_over')
                self.check(f'{file.name}:{index}', lambda op=op,arguments=arguments,value=value,item=item,family=family:self.consumer.fragment(family,item['definition'],value) if 'definition' in item else self.consumer.operation(op, arguments, value), 'published-example')
                results.append(dict(file=file.name,index=index,operation=op,arguments=arguments,value=value))
        dump(self.output/'examples-inputs.json', results)
        return results

    def mutants(self, examples):
        trials = []
        def rejection(name, action):
            def test():
                try: action()
                except Exception: return
                raise AssertionError('mutant survived')
            self.check(name, test, 'deliberate-mutant')
        for index, item in enumerate(examples):
            # Each actual result is replaced by a non-object through the same API.
            rejection('scalar-result-'+str(index), lambda item=item:self.consumer.operation(item['operation'],item['arguments'], True))
            trials.append(dict(name='scalar-result-'+str(index),operation=item['operation'],value=True))
        semantic_trials = []
        for item in examples:
            op=item['operation']; value=copy.deepcopy(item['value']); args=item['arguments']
            if 'team_change' in value:
                changed=copy.deepcopy(args); changed['action']='mute' if args['action']!='mute' else 'unmute'
                semantic_trials.append(('cross-team-action',op,changed,value))
            if 'board' in value:
                changed=copy.deepcopy(args); changed['action']='sync' if args['action']!='sync' else 'set'
                semantic_trials.append(('cross-board-action',op,changed,value))
            if op in ('xsm_link','xsm_join','xsm_reach') and 'scope' in value:
                value['scope']['kind']='reach' if value['scope']['kind']!='reach' else 'link'
                semantic_trials.append(('cross-scope-kind',op,args,value))
            if 'items' in value and value.get('claims'):
                value['items'][0]['id']='wrong-original'
                semantic_trials.append(('claim-association',op,args,value))
            if 'question_digest' in value:
                value['question_digest']='f'*64
                semantic_trials.append(('decision-digest',op,args,value))
            if op=='xsm_owned' and value.get('status')=='reply-stored':
                value['result']=None
                semantic_trials.append(('owned-reply-without-result',op,args,value))
            if op=='xsm_handover' and 'handover' in value:
                changed={'action':'show' if value['handover']['action']=='hand_over' else 'hand_over'}
                semantic_trials.append(('cross-handover-action',op,changed,value))
        for index,(name,op,args,value) in enumerate(semantic_trials):
            rejection(name+'-'+str(index),lambda op=op,args=args,value=value:self.consumer.operation(op,args,value))
        dump(self.output/'semantic-mutants-inputs.json',semantic_trials)
        for mode in ['wrong-id','boolean-id','both','missing-result','bad-result','unknown-error','notification-id','duplicate','nan','overflow','invalid-utf8','truncated','batch','oversized','timeout','eof']:
            root, env = self.root('local-'+mode)
            peer = self.transport([sys.executable,str(Path(__file__).with_name('local_v7_fixtures.py').resolve()),mode],root,env,timeout=.3 if mode=='timeout' else 8)
            try: rejection('wire-'+mode, lambda:peer.call('session.close', {'session':'local'}))
            finally: peer.close()
        # Deliberately disable validation: the malformed-result test MUST fail.
        class MutantConsumer:
            def frame(self, *args): return {'state':'unchecked'}
        root, env = self.root('disabled-validator')
        peer = self.transport([sys.executable,str(Path(__file__).with_name('local_v7_fixtures.py').resolve()),'bad-result'],root,env)
        peer.consumer = MutantConsumer()
        try:
            frame, facts = peer.call('session.close', {'session':'local'})
            def expected_failure():
                try:
                    self.require(type(frame['result']['closed']) is bool)
                except AssertionError as exc:
                    dump(self.output/'deliberate-disabled-validator-failure.json',dict(expected=True,error=repr(exc),traceback=traceback.format_exc(),frame=frame))
                    return
                raise AssertionError('test failed to kill disabled-validator mutant')
            self.check('test-kills-disabled-validator', expected_failure, 'test-mutation-sensitivity')
        finally: peer.close()
        dump(self.output/'mutants-inputs.json',trials)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operator',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    operator = strict_json(args.operator.read_text())
    args.output.mkdir(parents=True, exist_ok=False); args.output.chmod(0o700)
    manifest = strict_json((Path(operator['input'])/'manifest.json').read_text())
    hashes = {name:hashlib.sha256((Path(operator['input'])/name).read_bytes()).hexdigest()==digest for name,digest in manifest['files'].items()}
    dump(args.output/'input-provenance.json',dict(operator=operator,manifest=manifest,verified=hashes,manifestSha256=hashlib.sha256((Path(operator['input'])/'manifest.json').read_bytes()).hexdigest()))
    if not all(hashes.values()) or operator['sourceCommit'] != manifest['sourceCommit']: raise ContractError('input provenance mismatch')
    v = Verification(operator,args.output)
    examples = v.examples(); v.mutants(examples); v.independent(); v.independent_fixtures(); reports = v.public_suites()
    declared = {op:s.get('properties',{}).get('action',{}).get('enum',[]) for op,s in v.consumer.schemas['operations.schema.json']['$defs'].items()}
    missing = {op:[a for a in actions if a not in v.coverage.get(op,{})] for op,actions in declared.items() if actions}
    missing = {k:x for k,x in missing.items() if x}
    summary = dict(sourceCommit=manifest['sourceCommit'],checks=v.checks,publicSuites=reports,rpcCount=v.rpcs,operationCoverage=v.coverage,missingOperations=sorted(set(v.consumer.inventory)-v.coverage.keys()),missingActions=missing,
                   limitations=['Linux/native runtime/native UI/real model/network/external messenger not executed; model0 owned fixture only','Public scenarios are public-checker-authored, separate from independent scenario','Synthetic UI callback is not a real human approval'])
    dump(args.output/'summary.json',summary)
    counts = {category:dict(passed=sum(r['passed'] for r in v.checks if r['category']==category),failed=sum(not r['passed'] for r in v.checks if r['category']==category)) for category in {r['category'] for r in v.checks}}
    print(json.dumps(dict(counts=counts,publicChecks=sum(r['checks'] for r in reports),failedSuites=[r for r in reports if r['status']!='passed'],missingOperations=summary['missingOperations'],missingActions=missing)),flush=True)
    if any(not r['passed'] for r in v.checks) or any(r['status']!='passed' for r in reports) or summary['missingOperations'] or missing:
        raise SystemExit(1)


if __name__ == '__main__': main()
