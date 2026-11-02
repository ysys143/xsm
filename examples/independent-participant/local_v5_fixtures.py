"""Own upload-helper regressions and in-memory fault mutations, stdlib only."""
import argparse
import base64
import hashlib
import io
import json
import sys
import types
import unittest
from pathlib import Path
import participant_v5


def suite(module):
    class Fake(module.Peer):
        def __init__(self):
            self.upload_limits={'fileUploadChunkBytes':196608,'fileUploadBudgetBytes':4194304,'fileUploadSlots':16}
            self.calls=[];self.buffers=None;self.specs=None;self.fail_once=False;self.bad_write=False;self.frozen=False
            self.token='a'*32;self.request_id=None
        def call(self,method,params=None,error=None):
            self.calls.append((method,params))
            if method=='files.upload.open':
                self.request_id=params['request_id']
                if self.buffers is None:
                    self.specs=params['entries'];self.buffers=[bytearray() for s in self.specs]
                if self.frozen:return {'state':'frozen','request_id':self.request_id,'manifest_id':'b'*32}
                return {'state':'uploading','request_id':self.request_id,'upload':self.token,
                        'offsets':[len(b) for b in self.buffers],'chunk_bytes':196608}
            if method=='files.upload.write':
                data=base64.b64decode(params['base64'],validate=True)
                if len(data)>196608:raise ValueError('mock chunk overflow')
                target=self.buffers[params['entry']]
                if params['offset']!=len(target):raise ValueError('mock append requires exact resume offset')
                target.extend(data)
                if self.fail_once:
                    self.fail_once=False
                    raise module.RpcError({'code':-32603,'message':'synthetic ambiguous write failure'})
                return {'upload':self.token,'entry':params['entry'],'offset':len(target)+(1 if self.bad_write else 0)}
            if method=='files.upload.commit':
                for data,spec in zip(self.buffers,self.specs):
                    if len(data)!=spec['size'] or hashlib.sha256(data).hexdigest()!=spec['sha256']:
                        raise ValueError('mock incomplete/corrupt commit')
                self.frozen=True
                return {'state':'frozen','request_id':self.request_id,'manifest_id':'b'*32,'body_sent':False}
            raise AssertionError('helper attempted forbidden or unexpected method '+method)

    class Helper(unittest.TestCase):
        def snapshot(self,data=b'caller bytes'):
            return module.UploadPlan.snapshot('ref:fixture','local-helper','fixture body',[{'name':'fixture.bin','data':data}])
        def test_mutable_caller_bytes_are_snapshotted(self):
            original=bytearray(b'abc');plan=self.snapshot(original);original[0]=ord('z')
            self.assertEqual(plan.files[0].data,b'abc')
            self.assertIs(type(plan.files[0].data),bytes)
            self.assertEqual(plan.params({'session':'s'})['entries'][0]['sha256'],hashlib.sha256(b'abc').hexdigest())
        def test_no_reader_paths_or_implicit_body_send(self):
            for value in ({'name':'x','path':'/not-read','data':b'x'}, {'name':'x','data':'/not-read'}):
                with self.assertRaises(ValueError):module.UploadPlan.snapshot('ref:f','r','body',[value])
            peer=Fake();peer.prepare_files({'session':'s'},self.snapshot())
            self.assertEqual({m for m,p in peer.calls},{'files.upload.open','files.upload.write','files.upload.commit'})
        def test_absent_or_invalid_extension_fails_before_any_rpc(self):
            for change in ({},{'fileUploadChunkBytes':True},{'fileUploadChunkBytes':0}):
                peer=Fake();peer.upload_limits=change
                with self.assertRaises(module.UploadUnavailable):peer.prepare_files({'session':'s'},self.snapshot())
                self.assertEqual(peer.calls,[])
        def test_four_mib_chunk_bounds_and_exact_bytes(self):
            data=[bytes([i])*1048576 for i in range(4)]
            plan=module.UploadPlan.snapshot('ref:f','four','body',[{'name':str(i),'data':d} for i,d in enumerate(data)])
            peer=Fake();result=peer.prepare_files({'session':'s'},plan)
            self.assertFalse(result.result['body_sent'])
            self.assertEqual([bytes(b) for b in peer.buffers],data)
            writes=[p for m,p in peer.calls if m=='files.upload.write']
            self.assertEqual(len(writes),24)
            self.assertTrue(all(len(p['base64'])<=262144 for p in writes))
        def test_explicit_resume_after_ambiguous_write(self):
            data=b'x'*400000;peer=Fake();plan=self.snapshot(data);peer.fail_once=True
            with self.assertRaises(module.RpcError):peer.prepare_files({'session':'s'},plan)
            self.assertFalse(peer.frozen)
            self.assertEqual(sum(m=='files.upload.write' for m,p in peer.calls),1)
            peer.prepare_files({'session':'s'},plan)
            writes=[p for m,p in peer.calls if m=='files.upload.write']
            self.assertEqual([p['offset'] for p in writes],[0,196608,393216])
            self.assertEqual(bytes(peer.buffers[0]),data)
        def test_wrong_write_offset_is_not_treated_as_success(self):
            peer=Fake();peer.bad_write=True
            with self.assertRaises(ValueError):peer.prepare_files({'session':'s'},self.snapshot())
            self.assertFalse(any(m=='files.upload.commit' for m,p in peer.calls))
        def test_bad_resume_offsets_rejected(self):
            for bad in ([True],[-1],[999],[],[0,0]):
                peer=Fake();plan=self.snapshot()
                result={'state':'uploading','upload':'a'*32,'request_id':plan.request_id,'offsets':bad,'chunk_bytes':196608}
                with self.assertRaises(ValueError):peer._progress_or_frozen(result,plan)
        def test_file_bundle_entry_bounds(self):
            for files in ([{'name':'large','data':b'x'*1048577}],
                [{'name':str(i),'data':b'x'*1048576} for i in range(5)],
                [{'name':str(i),'data':b''} for i in range(17)]):
                with self.assertRaises(ValueError):module.UploadPlan.snapshot('ref:f','r','body',files)
        def test_frozen_reopen_never_reuploads_or_sends(self):
            peer=Fake();plan=self.snapshot();first=peer.prepare_files({'session':'s'},plan)
            count=len(peer.calls);again=peer.prepare_files({'session':'s'},plan)
            self.assertEqual(peer.calls[count:],[('files.upload.open',plan.params({'session':'s'}))])
            self.assertEqual(first.result['manifest_id'],again.result['manifest_id'])
            self.assertIsNone(again.upload)
    return unittest.defaultTestLoader.loadTestsFromTestCase(Helper)


def run(module):
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite(module))
    return {'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'output':stream.getvalue()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    source=Path(participant_v5.__file__).read_text(encoding='utf-8')
    results={'baseline':run(participant_v5),'mutants':{}}
    mutations={
        'mutable_snapshot':("data=bytes(item['data'])","data=item['data']"),
        'missing_extension_ignored':("raise UploadUnavailable('v5 upload extension missing or incompatible: '+field)","return expected"),
        'resume_offset_ignored':("zip(plan.files,opened['offsets'])","zip(plan.files,[0]*len(plan.files))"),
        'write_offset_not_checked':("if result.get('upload')!=token or result.get('entry')!=entry or result.get('offset')!=offset+len(data):","if False:"),
    }
    for name,(before,after) in mutations.items():
        if source.count(before)!=1:raise AssertionError('missing mutation binding '+name)
        module=types.ModuleType('own_v5_mutant_'+name)
        sys.modules[module.__name__]=module
        try:
            exec(compile(source.replace(before,after),'<own v5 in-memory mutant>','exec'),module.__dict__)
            results['mutants'][name]=run(module)
        finally:sys.modules.pop(module.__name__,None)
    results['status']='passed' if results['baseline']['passed'] and all(not r['passed'] for r in results['mutants'].values()) else 'failed'
    with args.output.open('x',encoding='utf-8') as f:json.dump(results,f,indent=2);f.write('\n')
    print(json.dumps({'status':results['status'],'baseline_tests':results['baseline']['tests'],'mutants_detected':sum(not r['passed'] for r in results['mutants'].values())}))
    return 0 if results['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
