"""Own schema/framing regressions, inherited hardening and targeted mutations."""
import argparse
import copy
import io
import json
import types
import unittest
from pathlib import Path
import participant_v3
import transport_fixtures


def build_suite(module, schema):
    # Reuse our v2 mock machinery and its exact hardening assertions, unchanged.
    inherited = transport_fixtures.suite(module)
    base = type(inherited._tests[0])
    class Added(base):
        def packet(self):
            return {'messages':['fixture'], 'claims':[{'id':'m','token':'t','generation':'g',
                'digest':'a'*64,'owner':{'type':'fixture','id':'o'}}],
                'items':[{'id':'m','priority':'next','kind':'note','wake':None}], 'inbox_pending':0}

        def test_duplicate_top_level_keys_terminal(self):
            self.reject_wire(b'{"jsonrpc":"2.0","id":1,"result":{},"result":{}}\n')

        def test_duplicate_nested_keys_terminal(self):
            self.reject_wire(b'{"jsonrpc":"2.0","id":1,"result":{"x":1,"x":2}}\n')

        def test_inbox_null_boolean_and_false_numeric_separation(self):
            for value in (True,False,None):
                packet=self.packet();packet['items'][0]['wake']=value
                module.validate_inbox(packet,schema)
            for value in ('never',0,1,[],{}):
                packet=self.packet();packet['items'][0]['wake']=value
                with self.assertRaises(ValueError):module.validate_inbox(packet,schema)

        def test_inbox_claim_item_order_binding(self):
            packet=self.packet();packet['items'][0]['id']='different'
            with self.assertRaises(ValueError):module.validate_inbox(packet,schema)

        def test_inbox_file_hashes_and_unknown_fields(self):
            packet=self.packet()
            packet['items'][0]['files']={'storage_id':'s','manifest_id':'m','version':1,'sha256':'b'*64,
                'files':[{'id':'e','name':'fixture.bin','size':1,'sha256':'c'*64}]}
            module.validate_inbox(packet,schema)
            mutations=[lambda p:p['items'][0]['files'].__setitem__('sha256','bad'),
                       lambda p:p['claims'][0].__setitem__('digest','a'*64+'\n'),
                       lambda p:p.__setitem__('unknown','no'),
                       lambda p:p['items'][0]['files']['files'][0].__setitem__('size',True),
                       lambda p:p['items'][0]['files']['files'][0].__setitem__('size',-1)]
            for mutate in mutations:
                bad=copy.deepcopy(packet);mutate(bad)
                with self.assertRaises(ValueError):module.validate_inbox(bad,schema)
    return unittest.defaultTestLoader.loadTestsFromTestCase(Added)


def run(module,schema):
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(build_suite(module,schema))
    return {'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'output':stream.getvalue()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    schema=json.loads((args.bundle/'inbox-result.schema.json').read_text(encoding='utf-8'))
    source=Path(participant_v3.__file__).read_text(encoding='utf-8')
    records={'baseline':run(participant_v3,schema),'mutants':{}}
    mutations={
        'duplicate_key_acceptance':("object_pairs_hook=unique_object", "object_pairs_hook=dict"),
        'lost_claim_item_binding':("if [i['id'] for i in packet['items']] != [c['id'] for c in packet['claims']]:", "if False:"),
        'numeric_wake_accepted_as_boolean':("'boolean': type(value) is bool", "'boolean': type(value) in (bool,int)"),
        'lost_hash_pattern_validation':("if 'pattern' in rule and re.search(rule['pattern'], value) is None:","if False:"),
    }
    for name,(before,after) in mutations.items():
        if source.count(before)!=1:raise AssertionError('missing mutation binding '+name)
        module=types.ModuleType('own_v3_mutant_'+name)
        exec(compile(source.replace(before,after),'<own v3 in-memory mutant>','exec'),module.__dict__)
        records['mutants'][name]=run(module,schema)
    records['status']='passed' if records['baseline']['passed'] and all(not r['passed'] for r in records['mutants'].values()) else 'failed'
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(records,handle,ensure_ascii=False,indent=2);handle.write('\n')
    print(json.dumps({'status':records['status'],'baseline_tests':records['baseline']['tests'],
                      'mutants_detected':sum(not r['passed'] for r in records['mutants'].values())}))
    return 0 if records['status']=='passed' else 1

if __name__=='__main__':
    raise SystemExit(main())
